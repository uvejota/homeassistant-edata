import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import voluptuous as vol
from edata.helpers import EdataHelper
from edata.processors import DataUtils as du
from homeassistant.core import HomeAssistant
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    statistics_during_period,
    month_start_end,
    day_start_end,
)
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    ENERGY_KILO_WATT_HOUR,
    EVENT_HOMEASSISTANT_START,
    POWER_KILO_WATT,
)
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .const import *
from .store import DateTimeEncoder, async_load_storage
from .websockets import *
from edata.connectors import DatadisConnector

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=60)


PLATFORM_SCHEMA = vol.All(
    cv.deprecated(CONF_USERNAME),
    cv.deprecated(CONF_PASSWORD),
    cv.deprecated(CONF_CUPS),
    cv.deprecated(CONF_EXPERIMENTAL),
    cv.deprecated(CONF_PROVIDER),
    PLATFORM_SCHEMA.extend(
        (
            {
                vol.Optional(CONF_DEBUG): cv.boolean,
                vol.Optional(CONF_PROVIDER): cv.string,
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_CUPS): cv.string,
                vol.Optional(CONF_EXPERIMENTAL): cv.boolean,
            }
        ),
    ),
)


VALID_ENTITY_CONFIG = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional(CONF_EXPERIMENTAL, default=False): cv.boolean,
        # vol.Optional(CONF_PROVIDER): cv.string
    },
    extra=vol.REMOVE_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import edata configuration from YAML."""
    hass.data.setdefault(DOMAIN, {})

    if config.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)

    if any(
        key in config
        for key in [
            CONF_USERNAME,
            CONF_PASSWORD,
            CONF_CUPS,
            CONF_EXPERIMENTAL,
            CONF_PROVIDER,
        ]
    ):
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
    await async_setup_reload_service(hass, DOMAIN, ["sensor"])
    hass.data.setdefault(DOMAIN, {})

    usr = config_entry.data[CONF_USERNAME]
    pwd = config_entry.data[CONF_PASSWORD]
    cups = config_entry.data[CONF_CUPS]
    scups = cups[-4:]
    experimental = config_entry.data[CONF_EXPERIMENTAL]

    # load old data if any

    store = Store(
        hass,
        STORAGE_VERSION,
        f"{STORAGE_KEY_PREAMBLE}_{scups}",
        encoder=DateTimeEncoder,
    )
    storage = await async_load_storage(store)
    prev_data = (
        {x: storage.get(x, []) for x in ["supplies", "contracts"]} if storage else None
    )

    coordinator = EdataCoordinator(hass, usr, pwd, cups, prev_data)
    if prev_data is not None:
        await coordinator.compile_attributes()

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
        try:
            return self.coordinator.data.get("state", None)
        except Exception as _:
            return STATE_LOADING if self.coordinator.data is None else STATE_ERROR

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        try:
            return self.coordinator.data.get("attributes", {})
        except Exception as _:
            return {}


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        prev_data=None,
    ) -> None:
        """Initialize the data handler."""
        self.hass = hass
        self.reset = prev_data is None

        self._experimental = False
        self._cups = cups.upper()
        self.id = self._cups[-4:].lower()

        self._data = {
            "state": STATE_LOADING,
            "attributes": {x: None for x in ATTRIBUTES},
        }
        if prev_data is not None:
            self._data.update(prev_data)

        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "p3_kW", "kW"]

        hass.data[DOMAIN][self.id.upper()] = {}

        self.stat_ids = {
            "kWh": f"{DOMAIN}:{self.id}_consumption",
            "p1_kWh": f"{DOMAIN}:{self.id}_p1_consumption",
            "p2_kWh": f"{DOMAIN}:{self.id}_p2_consumption",
            "p3_kWh": f"{DOMAIN}:{self.id}_p3_consumption",
            "kW": f"{DOMAIN}:{self.id}_maximeter",
            "p1_kW": f"{DOMAIN}:{self.id}_p1_maximeter",
            "p2_kW": f"{DOMAIN}:{self.id}_p2_maximeter",
            "p3_kW": f"{DOMAIN}:{self.id}_p3_maximeter",
        }

        self._datadis = DatadisConnector(username, password, data=prev_data)

        super().__init__(
            hass,
            _LOGGER,
            name=f"edata_{self.id}",
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via API."""
        # reset stats if no storage file was found
        if self.reset:
            _LOGGER.warning(
                "Clearing statistics for %s",
                [self.stat_ids[x] for x in self.stat_ids],
            )
            await self.hass.async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                [self.stat_ids[x] for x in self.stat_ids],
            )

        # fetch last statistics found
        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.stat_ids[x], True
            )
            for x in self.stat_ids
        }

        # retrieve sum for summable stats (consumptions)
        _sum = {
            x: last_stats[x][self.stat_ids[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in self.consumption_stats
        }

        try:
            last_kWh_record = last_stats["kWh"][self.stat_ids["kWh"]][0]["end"]
            _LOGGER.info("Last consumptions record was at %s", last_kWh_record)
        except KeyError as _:
            last_kWh_record = None
            _LOGGER.warning("No consumption stats found")

        try:
            last_kW_record = last_stats["kW"][self.stat_ids["kW"]][0]["end"]
            _LOGGER.info("Last maximeter record was at %s", last_kW_record)
        except KeyError as _:
            last_kW_record = None
            _LOGGER.warning("No maximeter stats found")

        await self.hass.async_add_executor_job(
            self._datadis.update,
            self._cups,
            min(
                dt_util.parse_datetime(last_kWh_record).replace(tzinfo=None),
                dt_util.parse_datetime(last_kW_record).replace(tzinfo=None),
                datetime.today() - timedelta(days=30),
            )
            if last_kWh_record is not None and last_kW_record is not None
            else datetime(1970, 1, 1),
            datetime.today(),
        )

        self._data.update(self._datadis.data)

        new_stats = {x: [] for x in self.stat_ids}
        something_changed = False

        _LABEL_kWh = "value_kWh"
        for data in self._datadis.data.get("consumptions", {}):
            if last_kWh_record is None or dt_util.as_local(
                data["datetime"]
            ) >= dt_util.parse_datetime(last_kWh_record):
                something_changed = True
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["kWh"] += data[_LABEL_kWh]
                new_stats["kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_LABEL_kWh],
                        mean=data[_LABEL_kWh],
                        sum=_sum["kWh"],
                    )
                )
                _sum[_p + "_kWh"] += data[_LABEL_kWh]
                new_stats[_p + "_kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_LABEL_kWh],
                        mean=data[_LABEL_kWh],
                        sum=_sum[_p + "_kWh"],
                    )
                )

        _LABEL_kW = "value_kW"
        for data in self._datadis.data.get("maximeter", {}):
            if last_kW_record is None or dt_util.as_local(
                data["datetime"]
            ) >= dt_util.parse_datetime(last_kW_record):
                something_changed = True
                _p = du.get_pvpc_tariff(data["datetime"])
                new_stats["kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_LABEL_kW],
                        mean=data[_LABEL_kW],
                    )
                )
                new_stats[_p + "_kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_LABEL_kW],
                        mean=data[_LABEL_kW],
                    )
                )

        for _scope in self.consumption_stats:
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=True,
                name=f"{DOMAIN}_{self.id} {_scope} energy consumption",
                source=DOMAIN,
                statistic_id=self.stat_ids[_scope],
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            _LOGGER.info("adding new stats to %s", self.stat_ids[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        for _scope in self.maximeter_stats:
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=f"{DOMAIN}_{self.id} {_scope} maximeter",
                source=DOMAIN,
                statistic_id=self.stat_ids[_scope],
                unit_of_measurement=POWER_KILO_WATT,
            )
            _LOGGER.info("adding new stats to %s", self.stat_ids[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        # compile state and attributes
        if something_changed or self._data.get("state", STATE_LOADING) == STATE_LOADING:
            # update state and attributes
            self._data["state"] = STATE_READY
            if (
                False == await self.compile_attributes()
            ):  # wipe data if something got wrong
                _LOGGER.warning("Inconsistent data found, rebuilding statistics")
                self.reset = True
                await self._async_update_data()
            # store if 24hs

        return self._data

    async def compile_attributes(self) -> bool:
        """Load statistics and compile attributes and websockets, return false if failed"""
        compiled_stats = {}

        # load contractual data
        attrs = {
            "cups": self._cups
            if self._cups in [x["cups"] for x in self._data["supplies"]]
            else None,
            "contract_p1_kW": self._data["contracts"][-1].get("power_p1", None)
            if len(self._data["contracts"]) > 0
            else None,
            "contract_p2_kW": self._data["contracts"][-1].get("power_p2", None)
            if len(self._data["contracts"]) > 0
            else None,
        }

        # load consumptions
        for _aggr_method in ("month", "day"):
            _stats = await self.hass.async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_local(datetime(1970, 1, 1)),
                None,
                [self.stat_ids[x] for x in self.consumption_stats],
                _aggr_method,
            )
            compiled_stats[_aggr_method] = {}
            for hourly_stat in _stats:
                _sum = 0
                for i in _stats[hourly_stat]:
                    _dt = dt_util.as_local(dt_util.parse_datetime(i["start"]))
                    date = _dt.isoformat()
                    if date not in compiled_stats[_aggr_method]:
                        compiled_stats[_aggr_method][date] = {
                            "datetime": date,
                            "value_kWh": 0,
                            "value_p1_kWh": 0,
                            "value_p2_kWh": 0,
                            "value_p3_kWh": 0,
                        }
                    for _scope in self.consumption_stats:
                        if self.stat_ids[_scope] == i["statistic_id"]:
                            _key = f"value_{_scope}"
                            _inc = round(i["sum"] - _sum, 2)
                            compiled_stats[_aggr_method][date][_key] = _inc
                            _sum = i["sum"]
                            if _inc < 0:
                                return False
                            break

            # load into websockets
            self.hass.data[DOMAIN][self.id.upper()][
                f"ws_consumptions_{_aggr_method}"
            ] = sorted(
                [compiled_stats[_aggr_method][x] for x in compiled_stats[_aggr_method]],
                key=lambda d: dt_util.parse_datetime(d["datetime"]),
            )

        # load yesterday attributes
        ydates = day_start_end(datetime.now() - timedelta(days=1))
        _date_str = dt_util.as_local(ydates[0]).isoformat()
        if _date_str in compiled_stats["day"]:
            attrs["yesterday_kWh"] = compiled_stats["day"][_date_str]["value_kWh"]
            attrs["yesterday_p1_kWh"] = compiled_stats["day"][_date_str]["value_p1_kWh"]
            attrs["yesterday_p2_kWh"] = compiled_stats["day"][_date_str]["value_p2_kWh"]
            attrs["yesterday_p3_kWh"] = compiled_stats["day"][_date_str]["value_p3_kWh"]
        # load current month attributes
        cmdates = month_start_end(datetime.now().replace(day=1))
        _date_str = dt_util.as_local(cmdates[0]).isoformat()
        if _date_str in compiled_stats["month"]:
            attrs["month_kWh"] = compiled_stats["month"][_date_str]["value_kWh"]
            attrs["month_p1_kWh"] = compiled_stats["month"][_date_str]["value_p1_kWh"]
            attrs["month_p2_kWh"] = compiled_stats["month"][_date_str]["value_p2_kWh"]
            attrs["month_p3_kWh"] = compiled_stats["month"][_date_str]["value_p3_kWh"]
        # load last month attributes
        lmdates = month_start_end(cmdates[0] - relativedelta(months=1))
        _date_str = dt_util.as_local(lmdates[0]).isoformat()
        if _date_str in compiled_stats["month"]:
            attrs["last_month_kWh"] = compiled_stats["month"][_date_str]["value_kWh"]
            attrs["last_month_p1_kWh"] = compiled_stats["month"][_date_str][
                "value_p1_kWh"
            ]
            attrs["last_month_p2_kWh"] = compiled_stats["month"][_date_str][
                "value_p2_kWh"
            ]
            attrs["last_month_p3_kWh"] = compiled_stats["month"][_date_str][
                "value_p3_kWh"
            ]

        # update attributes
        self._data["attributes"].update(attrs)

        return True
