import logging
from datetime import datetime, timedelta

import voluptuous as vol
from edata.helpers import EdataHelper
from edata.processors import DataUtils as du
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import (StatisticData,
                                                      StatisticMetaData)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics, clear_statistics, get_last_statistics,
    statistics_during_period)
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.const import (CONF_PASSWORD, CONF_USERNAME,
                                 ENERGY_KILO_WATT_HOUR,
                                 EVENT_HOMEASSISTANT_START, POWER_KILO_WATT)
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import dt as dt_util

from .const import *
from .store import DateTimeEncoder, async_load_storage
from .websockets import *

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=30)

# Custom configuration entries
CONF_CUPS = 'cups'
CONF_PROVIDER = 'provider'
CONF_EXPERIMENTAL = 'experimental'
CONF_DEBUG = 'debug'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_PROVIDER): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional(CONF_EXPERIMENTAL): cv.boolean,
        vol.Optional(CONF_DEBUG): cv.boolean
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_reload_service(hass, DOMAIN, ['sensor'])
    hass.data.setdefault(DOMAIN, {})

    usr = config[CONF_USERNAME]
    pwd = config[CONF_PASSWORD]
    cups = config[CONF_CUPS]
    scups = cups[-4:]
    experimental = config.get(CONF_EXPERIMENTAL, False)

    if config.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)

    # load old data if any
    store = Store(hass, STORAGE_VERSION,
                  f"{STORAGE_KEY_PREAMBLE}_{scups}", encoder=DateTimeEncoder)
    prev_data = await async_load_storage(store)
    if prev_data:
        api = EdataHelper('datadis',  usr, pwd, cups,
                          data=prev_data, experimental=experimental)
        api.process_data()
        hass.data[DOMAIN][scups] = api.data
    else:
        api = EdataHelper('datadis', usr, pwd, cups, experimental=experimental)

    statistic_id = {}
    statistic_id["total"] = f"{DOMAIN}:{scups.lower()}_consumption"
    statistic_id["p1"] = f"{DOMAIN}:{scups.lower()}_p1_consumption"
    statistic_id["p2"] = f"{DOMAIN}:{scups.lower()}_p2_consumption"
    statistic_id["p3"] = f"{DOMAIN}:{scups.lower()}_p3_consumption"

    async def async_update_data():
        """Fetch data from edata endpoint."""

        try:
            last_changed = api.attributes.get('last_registered_kWh_date', None)
            await hass.async_add_executor_job(api.update)
            hass.data[DOMAIN][scups] = api.data
            if (last_changed is None or
                    (api.attributes.get('last_registered_kWh_date', datetime(1970, 1, 1)) - last_changed) > timedelta(hours=24)):
                await store.async_save(api.data)
            await _insert_statistics(last_changed is None)
            await _load_statistics()
            return {
                "state": STATE_READY,
                "attributes": api.attributes,
                "data": hass.data[DOMAIN][scups]
            }
        except Exception as e:
            _LOGGER.exception('unhandled exception when updating data %s', e)
            return {
                "state": STATE_ERROR,
                "attributes": api.attributes,
                "data": hass.data[DOMAIN][scups]
            }

    async def _insert_statistics(reset=False):
        """ Insert edata statistics """

        last_stats = {x: await hass.async_add_executor_job(
            get_last_statistics, hass, 1, statistic_id[x], True
        ) for x in ["total", "p1", "p2", "p3"]}

        _sum = {
            x: last_stats[x][statistic_id[x]][0].get(
                "sum", 0) if last_stats[x] and not reset else 0
            for x in ["total", "p1", "p2", "p3"]
        }

        statistics = {
            'total': [],
            'p1': [],
            'p2': [],
            'p3': []
        }

        if reset:
            _LOGGER.warning(
                f"clearing statistics for {[statistic_id[x] for x in statistic_id]}")
            await hass.async_add_executor_job(clear_statistics, hass.data[DATA_INSTANCE], [statistic_id[x] for x in statistic_id])

        try:
            last_stats_time = last_stats["total"][statistic_id["total"]][0]["end"]
        except KeyError as e:
            last_stats_time = None

        for data in api.data.get("consumptions", {}):
            if reset or last_stats_time is None or dt_util.as_local(data["datetime"]) >= dt_util.parse_datetime(last_stats_time):
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["total"] += data["value_kWh"]
                statistics["total"].append(StatisticData(
                    start=dt_util.as_local(data["datetime"]),
                    state=data["value_kWh"],
                    sum=_sum["total"]
                ))
                _sum[_p] += data["value_kWh"]
                statistics[_p].append(StatisticData(
                    start=dt_util.as_local(data["datetime"]),
                    state=data["value_kWh"],
                    sum=_sum[_p]
                ))

        for _scope in ["p1", "p2", "p3", "total"]:
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{DOMAIN}_{scups} {_scope} energy consumption",
                source=DOMAIN,
                statistic_id=statistic_id[_scope],
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            async_add_external_statistics(hass, metadata, statistics[_scope])

    async def _load_statistics():
        stats = {}
        for _aggr_method in ["month", "day", "hour"]:
            _stats = await hass.async_add_executor_job(statistics_during_period, hass, dt_util.as_local(datetime(1970, 1, 1)), None, [statistic_id[x] for x in statistic_id], _aggr_method)
            stats[_aggr_method] = {}
            for x in _stats:
                _data = _stats[x]
                _sum = 0
                for i in _data:
                    date = dt_util.as_local(
                        dt_util.parse_datetime(i['start'])).isoformat()
                    if date not in stats[_aggr_method]:
                        stats[_aggr_method][date] = {
                            'datetime': date, 'value_kWh': 0, 'value_p1_kWh': 0, 'value_p2_kWh': 0, 'value_p3_kWh': 0}
                    for x in ["total", "p1", "p2", "p3"]:
                        if statistic_id[x] == i['statistic_id']:
                            _key = 'value_kWh' if x == 'total' else f"value_{x}_kWh"
                            stats[_aggr_method][date][_key] = round(
                                i['sum'] - _sum, 2)
                            _sum = i['sum']
                            break
            hass.data[DOMAIN][scups.upper()][f"ws_consumptions_{_aggr_method}"] = sorted([
                stats[_aggr_method][x] for x in stats[_aggr_method]
            ], key=lambda d: dt_util.parse_datetime(d['datetime']))

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"edata_{scups}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=30),
    )

    if prev_data:
        coordinator.data = {
            "state": STATE_LOADING,
            "attributes": api.attributes,
            "data": hass.data[DOMAIN][scups]
        }

    # postpone first refresh to speed up startup
    @callback
    async def async_first_refresh(*args):
        """Force the component to assess the first refresh."""
        await coordinator.async_refresh()

    if hass.state == CoreState.running:
        await async_first_refresh()
    else:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_START, async_first_refresh)

    # build sensor entities

    entities = []
    entities.append(EdataSensor(coordinator))
    async_add_entities(entities)

    async_register_websockets(hass)

    return True


class EdataSensor(CoordinatorEntity, SensorEntity):
    """Representation of an e-data Sensor."""
    _attr_icon = "hass:flash"
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = coordinator.name

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get("state", None) if self.coordinator.data is not None else None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self.coordinator.data.get("attributes", {}) if self.coordinator.data is not None else {}
