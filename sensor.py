import logging, json
import voluptuous as vol
from collections import OrderedDict
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    EVENT_HOMEASSISTANT_START,
    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from datetime import datetime, timedelta
from edata.helpers import EdataHelper
from edata.processors import DataUtils as du
from .const import *
from .websockets import *
from .store import DateTimeEncoder, async_load_storage
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
    clear_statistics
)
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.util import dt as dt_util

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=30)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_PROVIDER): cv.string,
        vol.Optional(CONF_DEBUG): cv.boolean
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_reload_service(hass, DOMAIN, ['sensor'])
    hass.data.setdefault(DOMAIN, {})

    if config.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)

    return True

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(DOMAIN, {})

    usr = config_entry.data[CONF_USERNAME]
    pwd = config_entry.data[CONF_PASSWORD]
    cups = config_entry.data[CONF_CUPS]
    scups = cups[-4:]
    experimental = config_entry.data[CONF_EXPERIMENTAL]

    # load old data if any
    store = Store (hass, STORAGE_VERSION, f"{STORAGE_KEY_PREAMBLE}_{scups}", encoder=DateTimeEncoder)
    prev_data = await async_load_storage (store)
    if prev_data:
        api = EdataHelper ('datadis',  usr, pwd, cups, data=prev_data, experimental=experimental)
        api.process_data ()
        hass.data[DOMAIN][scups] = api.data
    else:
        api = EdataHelper ('datadis', usr, pwd, cups, experimental=experimental)

    async def async_update_data():
        """Fetch data from edata endpoint."""
        try:
            last_changed = api.attributes.get('last_registered_kWh_date', None)
            await hass.async_add_executor_job(api.update)
            hass.data[DOMAIN][scups] = api.data
            if ( last_changed is None or
                (api.attributes.get('last_registered_kWh_date', datetime(1970, 1, 1)) - last_changed) > timedelta (hours=24) ):
                await store.async_save(api.data)
            await _insert_statistics (last_changed is None)
            return {
                "state": STATE_READY,
                "attributes": api.attributes,
                "data": hass.data[DOMAIN][scups]
            }
        except Exception as e:
            _LOGGER.exception ('unhandled exception when updating data %s', e)
            return {
                "state": STATE_ERROR,
                "attributes": api.attributes,
                "data": hass.data[DOMAIN][scups]
            }

    async def _insert_statistics (reset=False):
        """ Insert edata statistics """
        statistic_id = {}
        statistic_id["total"] = f"{DOMAIN}:{scups.lower()}_consumption"
        statistic_id["p1"] = f"{DOMAIN}:{scups.lower()}_p1_consumption"
        statistic_id["p2"] = f"{DOMAIN}:{scups.lower()}_p2_consumption"
        statistic_id["p3"] = f"{DOMAIN}:{scups.lower()}_p3_consumption"

        last_stats = {x: await hass.async_add_executor_job(
                get_last_statistics, hass, 1, statistic_id[x], True
            ) for x in ["total", "p1", "p2", "p3"]}

        _sum = {
            x: last_stats[x][statistic_id[x]][0].get("sum", 0) if last_stats[x] and not reset else 0
            for x in ["total", "p1", "p2", "p3"]
            }

        statistics = {
            'total': [],
            'p1': [],
            'p2': [],
            'p3': []
        }

        if reset:
            _LOGGER.warning (f"clearing statistics for {[statistic_id[x] for x in statistic_id]}")
            await hass.async_add_executor_job(clear_statistics, hass.data[DATA_INSTANCE], [statistic_id[x] for x in statistic_id])

        try:
            last_stats_time = last_stats["total"][statistic_id["total"]][0]["end"]
        except KeyError as e:
            last_stats_time = None

        for data in api.data.get("consumptions", {}):
            if reset or last_stats_time is None or dt_util.as_local(data["datetime"]) >= dt_util.parse_datetime(last_stats_time):
                _p = du.get_pvpc_tariff (data["datetime"])
                _sum["total"] += data["value_kWh"]
                statistics["total"].append (StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data["value_kWh"],
                        sum=_sum["total"]
                    ))
                _sum[_p] += data["value_kWh"]
                statistics[_p].append (StatisticData(
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
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, async_first_refresh)

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
