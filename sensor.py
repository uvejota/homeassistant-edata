import json
import logging
from calendar import monthrange
from collections import OrderedDict
from datetime import datetime, timedelta

import voluptuous as vol
from dateutil.relativedelta import relativedelta
from edata.connectors import DatadisConnector
from edata.helpers import EdataHelper
from edata.processors import DataUtils as du
from edata.processors import MaximeterProcessor
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import (StatisticData,
                                                      StatisticMetaData)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics, clear_statistics, day_start_end,
    get_last_statistics, month_start_end, same_day, same_month,
    statistics_during_period)
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT
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


PLATFORM_SCHEMA = vol.All(
        cv.deprecated(CONF_USERNAME),
        cv.deprecated(CONF_PASSWORD),
        cv.deprecated(CONF_CUPS),
        cv.deprecated(CONF_EXPERIMENTAL),
        cv.deprecated(CONF_PROVIDER),
        PLATFORM_SCHEMA.extend((
            {
                vol.Optional(CONF_DEBUG): cv.boolean,
                vol.Optional(CONF_PROVIDER): cv.string,
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_CUPS): cv.string,
                vol.Optional(CONF_EXPERIMENTAL): cv.boolean,
            }
        ),
    )
)


VALID_ENTITY_CONFIG = vol.Schema({
    vol.Required(CONF_USERNAME): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_CUPS): cv.string,
    vol.Optional(CONF_EXPERIMENTAL, default=False): cv.boolean,
    # vol.Optional(CONF_PROVIDER): cv.string
}, extra=vol.REMOVE_EXTRA)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import edata configuration from YAML."""
    hass.data.setdefault(DOMAIN, {})

    if config.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)

    if any(key in config for key in [CONF_USERNAME, CONF_PASSWORD, CONF_CUPS, CONF_EXPERIMENTAL, CONF_PROVIDER]):
        try:
            validated_config = VALID_ENTITY_CONFIG(config)
            _LOGGER.warning(
                "Loading edata sensor via platform setup is deprecated. It will be imported into Home Assistant integration. Please remove it from your configuration"
            )
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data=validated_config,
                )
            )
        except vol.Error as ex:
            _LOGGER.warning("Invalid config '%s': %s", config, ex)

    return True

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""
    await async_setup_reload_service(hass, DOMAIN, ['sensor'])
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
        api = EdataHelper('datadis',  usr, pwd, cups,
                          data=prev_data, experimental=experimental)
        api.process_data()
        hass.data[DOMAIN][scups] = api.data
    else:
        api = EdataHelper('datadis', usr, pwd, cups, experimental=experimental)

    # same but with connector
    # conn = DatadisConnector (usr, pwd)

    consumption_stats_id = {
        "total": f"{DOMAIN}:{scups.lower()}_consumption",
        "p1": f"{DOMAIN}:{scups.lower()}_p1_consumption",
        "p2": f"{DOMAIN}:{scups.lower()}_p2_consumption",
        "p3": f"{DOMAIN}:{scups.lower()}_p3_consumption",
    }

    async def async_update_data():
        """Fetch data from edata endpoint."""
        attributes = {
            x: None for x in ATTRIBUTES if x not in EXPERIMENTAL_ATTRS}
        state = STATE_LOADING
        try:
            await hass.async_add_executor_job(api.update)

            # read cups
            for i in api.data['supplies']:
                if i['cups'] == cups:
                    attributes["cups"] = cups
                    break

            # read latest contract
            most_recent_date = datetime(1970, 1, 1)
            for i in api.data['contracts']:
                if i['date_end'] > most_recent_date:
                    most_recent_date = i['date_end']
                    attributes['contract_p1_kW'] = i.get('power_p1', None)
                    attributes['contract_p2_kW'] = i.get('power_p2', None)
                    break

            # process maximeter data
            if len(api.data['maximeter']) > 0:
                processor = MaximeterProcessor(api.data['maximeter'])
                attributes['max_power_kW'] = processor.output['stats'].get(
                    'value_max_kW', None)
                attributes['max_power_date'] = processor.output['stats'].get(
                    'date_max', None)
                attributes['max_power_mean_kW'] = processor.output['stats'].get(
                    'value_mean_kW', None)
                attributes['max_power_90perc_kW'] = processor.output['stats'].get(
                    'value_tile90_kW', None)

            hass.data[DOMAIN][scups] = api.data  # old

            # load and process recent statistics
            if hass.data[DOMAIN][scups].get("attributes", None) is None:
                attrs = await async_load_statistics()
                last_record = attrs['last_registered_kWh_date']
            else:
                last_record = hass.data[DOMAIN][scups]["attributes"]["last_registered_kWh_date"]
            last_record = dt_util.parse_datetime(last_record)

            # update statistics
            attrs = await async_update_statistics(attrs is None)
            attrs.update({x: round(attrs[x], 2)
                         for x in attrs if ATTRIBUTES[x] is not None})
            attributes.update(attrs)
            hass.data[DOMAIN][scups]["attributes"] = attributes

            if (dt_util.parse_datetime(attributes['last_registered_kWh_date']) - last_record) > timedelta(hours=24):
                await store.async_save(api.data)

            state = STATE_READY
        except Exception as e:
            _LOGGER.exception('unhandled exception when updating data %s', e)
            state = STATE_ERROR

        return {
            "state": state,
            "attributes": attributes,
            "data": hass.data[DOMAIN][scups]
        }

    async def async_update_statistics(reset=False):
        """ Insert new edata statistics """
        # fetch latest stats
        last_stats = {x: await hass.async_add_executor_job(
            get_last_statistics, hass, 1, consumption_stats_id[x], True
        ) for x in ["total", "p1", "p2", "p3"]}
        # get sum
        _sum = {
            x: last_stats[x][consumption_stats_id[x]][0].get(
                "sum", 0) if last_stats[x] and not reset else 0
            for x in ["total", "p1", "p2", "p3"]
        }
        # build stats lists
        consumptions = {
            'total': [],
            'p1': [],
            'p2': [],
            'p3': []
        }
        # wipe data if needed
        if reset:
            _LOGGER.warning(
                f"clearing statistics for {[consumption_stats_id[x] for x in consumption_stats_id]}")
            await hass.async_add_executor_job(clear_statistics, hass.data[DATA_INSTANCE], [consumption_stats_id[x] for x in consumption_stats_id])
        # get last record time
        try:
            last_stats_time = last_stats["total"][consumption_stats_id["total"]][0]["end"]
        except KeyError as e:
            last_stats_time = None
        # prepare additive stats
        for data in api.data.get("consumptions", []):
            if reset or last_stats_time is None or dt_util.as_local(data["datetime"]) >= dt_util.parse_datetime(last_stats_time):
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["total"] += data["value_kWh"]
                consumptions["total"].append(StatisticData(
                    start=dt_util.as_local(data["datetime"]),
                    state=data["value_kWh"],
                    sum=_sum["total"]
                ))
                _sum[_p] += data["value_kWh"]
                consumptions[_p].append(StatisticData(
                    start=dt_util.as_local(data["datetime"]),
                    state=data["value_kWh"],
                    sum=_sum[_p]
                ))
        # insert stats
        for _scope in ["p1", "p2", "p3", "total"]:
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{DOMAIN}_{scups} {_scope} energy consumption",
                source=DOMAIN,
                statistic_id=consumption_stats_id[_scope],
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            async_add_external_statistics(hass, metadata, consumptions[_scope])
        return await async_load_statistics()

    async def async_load_statistics():
        """ Load existing statistics into attributes and websockets """
        stats_ok = True
        stats = {}
        attrs = {}
        last_stats = await hass.async_add_executor_job(
            get_last_statistics, hass, 1, consumption_stats_id["total"], True
        )
        if last_stats:
            last_record = dt_util.parse_datetime(
                last_stats[consumption_stats_id["total"]][0]["end"]) - timedelta(hours=1)
            for _aggr_method in ["month", "day"]:
                _stats = await hass.async_add_executor_job(statistics_during_period, hass, dt_util.as_local(datetime(1970, 1, 1)), None, [consumption_stats_id[x] for x in consumption_stats_id], _aggr_method)
                stats[_aggr_method] = {}
                for x in _stats:
                    _data = _stats[x]
                    _sum = 0
                    for i in _data:
                        _dt = dt_util.as_local(
                            dt_util.parse_datetime(i['start']))
                        date = _dt.isoformat()
                        if date not in stats[_aggr_method]:
                            stats[_aggr_method][date] = {
                                'datetime': date, 'value_kWh': 0, 'value_p1_kWh': 0, 'value_p2_kWh': 0, 'value_p3_kWh': 0}
                        for x in ["total", "p1", "p2", "p3"]:
                            if consumption_stats_id[x] == i['statistic_id']:
                                _key = 'value_kWh' if x == 'total' else f"value_{x}_kWh"
                                _inc = round(i['sum'] - _sum, 2)
                                stats[_aggr_method][date][_key] = _inc
                                _sum = i['sum']
                                if _inc < 0:
                                    stats_ok = False
                                break
                # load websockets data
                hass.data[DOMAIN][scups.upper()][f"ws_consumptions_{_aggr_method}"] = sorted([
                    stats[_aggr_method][x] for x in stats[_aggr_method]
                ], key=lambda d: dt_util.parse_datetime(d['datetime']))
            attrs["last_registered_kWh_date"] = dt_util.as_local(
                last_record).isoformat()
            # load yesterday attributes
            ydates = day_start_end(datetime.now() - timedelta(days=1))
            _date_str = dt_util.as_local(ydates[0]).isoformat()
            if _date_str in stats["day"]:
                attrs["yesterday_kWh"] = stats["day"][_date_str]["value_kWh"]
                attrs["yesterday_p1_kWh"] = stats["day"][_date_str]["value_p1_kWh"]
                attrs["yesterday_p2_kWh"] = stats["day"][_date_str]["value_p2_kWh"]
                attrs["yesterday_p3_kWh"] = stats["day"][_date_str]["value_p3_kWh"]
                attrs["yesterday_hours"] = (
                    (ydates[1] - ydates[0]).seconds / 3600.0) if last_record > ydates[1] else ((last_record - ydates[0]).seconds / 3600.0)
            # load current month attributes
            cmdates = month_start_end(datetime.now().replace(day=1))
            _date_str = dt_util.as_local(cmdates[0]).isoformat()
            if _date_str in stats["month"]:
                attrs["month_kWh"] = stats["month"][_date_str]["value_kWh"]
                attrs["month_p1_kWh"] = stats["month"][_date_str]["value_p1_kWh"]
                attrs["month_p2_kWh"] = stats["month"][_date_str]["value_p2_kWh"]
                attrs["month_p3_kWh"] = stats["month"][_date_str]["value_p3_kWh"]
                attrs["month_days"] = (
                    cmdates[1] - cmdates[0]).days if last_record > cmdates[1] else (last_record - cmdates[0]).days
            # load last month attributes
            lmdates = month_start_end(cmdates[0] - relativedelta(months=1))
            _date_str = dt_util.as_local(lmdates[0]).isoformat()
            if _date_str in stats["month"]:
                attrs["last_month_kWh"] = stats["month"][_date_str]["value_kWh"]
                attrs["last_month_p1_kWh"] = stats["month"][_date_str]["value_p1_kWh"]
                attrs["last_month_p2_kWh"] = stats["month"][_date_str]["value_p2_kWh"]
                attrs["last_month_p3_kWh"] = stats["month"][_date_str]["value_p3_kWh"]
                attrs["last_month_days"] = (
                    lmdates[1] - lmdates[0]).days if last_record > lmdates[1] else (last_record - lmdates[0]).days
            return attrs if stats_ok else None

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
