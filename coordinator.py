"""Data update coordinator definitions"""

import logging
from datetime import datetime, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta
from edata.connectors import DatadisConnector
from edata.processors import DataUtils as du
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    day_start_end,
    get_last_statistics,
    month_start_end,
    statistics_during_period,
)
from homeassistant.const import ENERGY_KILO_WATT_HOUR, POWER_KILO_WATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTES,
    COORDINATOR_ID,
    DATA_ATTRIBUTES,
    DATA_CONTRACTS,
    DATA_STATE,
    DATA_SUPPLIES,
    DOMAIN,
    STAT_ID_KW,
    STAT_ID_KWH,
    STAT_ID_P1_KW,
    STAT_ID_P1_KWH,
    STAT_ID_P2_KW,
    STAT_ID_P2_KWH,
    STAT_ID_P3_KWH,
    STAT_TITLE_KW,
    STAT_TITLE_KWH,
    STATE_LOADING,
    STATE_READY,
    STORAGE_ELEMENTS,
    STORAGE_KEY_PREAMBLE,
    STORAGE_VERSION,
    WARN_INCONSISTENT_STORAGE,
    WARN_MISSING_STATS,
    WARN_STATISTICS_CLEAR,
    WS_CONSUMPTIONS_DAY,
    WS_CONSUMPTIONS_MONTH,
)
from .data import init_consumption, init_maxpower
from .store import DateTimeEncoder

_LOGGER = logging.getLogger(__name__)


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        billing: dict[str, float] = None,
        prev_data=None,
    ) -> None:
        """Initialize the data handler."""
        self.hass = hass
        self.reset = prev_data is None

        self._experimental = False
        self._billing = billing
        self.cups = cups.upper()
        self.id = self.cups[-4:].lower()

        hass.data[DOMAIN][self.id.upper()] = {}

        # the api object
        self._datadis = DatadisConnector(username, password, data=prev_data)

        # shared storage
        # making self._data to reference hass.data[DOMAIN][self.id.upper()] so we can use it like an alias
        self._data = hass.data[DOMAIN][self.id.upper()]
        self._data.update(
            {
                DATA_STATE: STATE_LOADING,
                DATA_ATTRIBUTES: {x: None for x in ATTRIBUTES},
                DATA_SUPPLIES: self._datadis.data[DATA_SUPPLIES],
                DATA_CONTRACTS: self._datadis.data[DATA_CONTRACTS],
            }
        )

        # stat id aliases
        self.sid = {
            "kWh": STAT_ID_KWH(self.id),
            "p1_kWh": STAT_ID_P1_KWH(self.id),
            "p2_kWh": STAT_ID_P2_KWH(self.id),
            "p3_kWh": STAT_ID_P3_KWH(self.id),
            "kW": STAT_ID_KW(self.id),
            "p1_kW": STAT_ID_P1_KW(self.id),
            "p2_kW": STAT_ID_P2_KW(self.id),
        }

        # stats id grouping
        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "kW"]

        super().__init__(
            hass,
            _LOGGER,
            name=COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API."""

        # preload attributes if first boot
        if self._data.get(DATA_STATE, STATE_LOADING) == STATE_LOADING:
            if False is await self.load_data():
                self.reset = True
                _LOGGER.warning(
                    WARN_INCONSISTENT_STORAGE,
                    self.id.upper(),
                )

        # reset stats if no storage file was found
        if self.reset:
            _LOGGER.warning(
                WARN_STATISTICS_CLEAR,
                [*self.sid.values()],
            )
            await self.hass.async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                [*self.sid.values()],
            )

        # fetch last statistics found
        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.sid[x], True
            )
            for x in self.sid
        }

        # retrieve sum for summable stats (consumptions)
        _sum = {
            x: last_stats[x][self.sid[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in self.consumption_stats
        }

        stats_missing = False
        last_record_dt = {}
        try:
            last_record_dt = {
                x: dt_util.parse_datetime(last_stats[x][self.sid[x]][0]["end"])
                for x in self.sid
            }
        except KeyError as _:
            _LOGGER.warning(WARN_MISSING_STATS, self.id)
            stats_missing = True

        await self.hass.async_add_executor_job(
            self._datadis.update,
            self.cups,
            min(
                (last_record_dt["kWh"].replace(tzinfo=None)),
                (last_record_dt["kW"].replace(tzinfo=None)),
                datetime.today() - relativedelta(months=1),
            )
            if not stats_missing
            else datetime.today() - timedelta(days=365),
            datetime.now(),
        )  # fetch last month or last 365 days

        # store datadis data in shared data
        self._data.update({x: self._datadis.data[x] for x in STORAGE_ELEMENTS})

        new_stats = {x: [] for x in self.sid}
        something_changed = (
            self._datadis.data[DATA_SUPPLIES] != self._data[DATA_SUPPLIES]
        )

        _label = "value_kWh"
        for data in self._datadis.data.get("consumptions", {}):
            if (
                "kWh" not in last_record_dt
                or dt_util.as_local(data["datetime"]) >= last_record_dt["kWh"]
            ):
                something_changed = True
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["kWh"] += data[_label]
                new_stats["kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_label],
                        sum=_sum["kWh"],
                    )
                )
                _sum[_p + "_kWh"] += data[_label]
                new_stats[_p + "_kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_label],
                        sum=_sum[_p + "_kWh"],
                    )
                )

        _label = "value_kW"
        for data in self._datadis.data.get("maximeter", {}):
            if (
                "kW" not in last_record_dt
                or dt_util.as_local(data["datetime"]) >= last_record_dt["kW"]
            ):
                something_changed = True
                _p = "p1" if du.get_pvpc_tariff(data["datetime"]) == "p1" else "p2"
                new_stats["kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_label],
                        mean=data[_label],
                    )
                )
                new_stats[_p + "_kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_label],
                        mean=data[_label],
                    )
                )

        for _scope in self.consumption_stats:
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=STAT_TITLE_KWH(self.id, _scope),
                source=DOMAIN,
                statistic_id=self.sid[_scope],
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            _LOGGER.info("Adding new stats to %s", self.sid[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        for _scope in self.maximeter_stats:
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=STAT_TITLE_KW(self.id, _scope),
                source=DOMAIN,
                statistic_id=self.sid[_scope],
                unit_of_measurement=POWER_KILO_WATT,
            )
            _LOGGER.info("Adding new stats to %s", self.sid[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        # compile state and attributes
        if something_changed:
            ## Load contractual data
            if False is await self.load_data() and not self.reset:
                _LOGGER.warning(
                    WARN_INCONSISTENT_STORAGE,
                    self.id.upper(),
                )
                await self._async_update_data()

        # put reset flag down
        if self.reset:
            self.reset = False

        return self._data

    async def load_data(self):
        """Load data found in built-in statistics into state, attributes and websockets"""

        attrs = self._data[DATA_ATTRIBUTES]  # reference to attributes shared storage

        # anonymous function to sort dicts based of datetime key, and return a list of dicts for using in websockets
        build_ws_data = lambda dict_shaped_data: sorted(
            [dict_shaped_data[element] for element in dict_shaped_data],
            key=lambda item: dt_util.parse_datetime(item["datetime"]),
        )

        # add supplies-related attributes
        attrs.update(
            {
                "cups": self.cups
                if self.cups in [x["cups"] for x in self._data[DATA_SUPPLIES]]
                else None
            }
        )

        # add contract-related attributes
        attrs.update(
            {
                "contract_p1_kW": self._data[DATA_CONTRACTS][-1].get("power_p1", None)
                if len(self._data[DATA_CONTRACTS]) > 0
                else None,
                "contract_p2_kW": self._data[DATA_CONTRACTS][-1].get("power_p2", None)
                if len(self._data[DATA_CONTRACTS]) > 0
                else None,
            }
        )

        # read last statistics
        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.sid[x], True
            )
            for x in self.sid
        }

        # store last record datetime
        try:
            last_record_dt = {
                x: dt_util.as_local(
                    dt_util.parse_datetime(last_stats[x][self.sid[x]][0]["end"])
                )
                for x in self.sid
            }
        except KeyError as _:
            return False

        # Load consumptions
        consumptions = {}
        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            _stats = await self.hass.async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_local(datetime(1970, 1, 1)),
                None,
                [self.sid[x] for x in self.consumption_stats],
                aggr,
            )
            consumptions[aggr] = {}
            for key in _stats:
                # for each stat key (p1, p2, p3...)
                _sum = 0
                for stat in _stats[key]:
                    # for each stat record
                    dt_iso = dt_util.as_local(
                        dt_util.parse_datetime(stat["start"])
                    ).isoformat()
                    if dt_iso not in consumptions[aggr]:
                        # if first element, initialize a Consumption structure
                        consumptions[aggr][dt_iso] = init_consumption(dt_iso)
                    for scope in [
                        matching_stat
                        for matching_stat in self.consumption_stats
                        if self.sid[matching_stat] == stat["statistic_id"]
                    ]:
                        _key = f"value_{scope}"
                        _inc = round(stat["sum"] - _sum, 1)
                        consumptions[aggr][dt_iso][_key] = _inc
                        _sum = stat["sum"]
                        if _inc < 0:
                            # if negative increment, data has to be wiped
                            return False

            # load into websockets
            self._data[
                WS_CONSUMPTIONS_DAY if aggr == "day" else WS_CONSUMPTIONS_MONTH
            ] = build_ws_data(consumptions[aggr])

        # yesterday attributes
        _date_str = dt_util.as_local(
            day_start_end(datetime.now() - timedelta(days=1))[0]
        ).isoformat()
        if _date_str in consumptions["day"]:
            for key in ["", "_p1", "_p2", "_p3"]:
                attrs[f"yesterday{key}_kWh"] = consumptions["day"][_date_str][
                    f"value{key}_kWh"
                ]
            attrs["yesterday_hours"] = round(
                (
                    max(
                        last_record_dt["kWh"]
                        - day_start_end(dt_util.as_local(datetime.now()))[0],
                        timedelta(days=0),
                    )
                ).seconds
                / 3600,
                2,
            )
        # current month attributes
        this_month_start = month_start_end(datetime.now().replace(day=1))[0]
        _date_str = dt_util.as_local(this_month_start).isoformat()
        if _date_str in consumptions["month"]:
            for key in ["", "_p1", "_p2", "_p3"]:
                attrs[f"month{key}_kWh"] = consumptions["month"][_date_str][
                    f"value{key}_kWh"
                ]
            attrs["month_days"] = round(
                (last_record_dt["kWh"] - month_start_end(last_record_dt["kWh"])[0]).days
            )
            attrs["month_daily_kWh"] = round(
                attrs["month_kWh"] / attrs["month_days"], 1
            )

        # last month attributes
        last_month_start = month_start_end(this_month_start - relativedelta(months=1))[
            0
        ]
        _date_str = dt_util.as_local(last_month_start).isoformat()
        if _date_str in consumptions["month"]:
            for key in ["", "_p1", "_p2", "_p3"]:
                attrs[f"last_month{key}_kWh"] = consumptions["month"][_date_str][
                    f"value{key}_kWh"
                ]
            attrs["last_month_days"] = round(
                (
                    month_start_end(last_record_dt["kWh"])[0]
                    - (
                        month_start_end(last_record_dt["kWh"])[0]
                        - relativedelta(months=1)
                    )
                ).days,
                2,
            )
            attrs["last_month_daily_kWh"] = round(
                attrs["last_month_kWh"] / attrs["last_month_days"], 1
            )

        # Load maximeter
        _stats = await self.hass.async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.as_local(datetime(1970, 1, 1)),
            None,
            [self.sid[x] for x in self.maximeter_stats],
            "hour",
        )

        maximeter = {}
        for key in _stats:
            for stat in _stats[key]:
                dt_iso = dt_util.as_local(
                    dt_util.parse_datetime(stat["start"])
                ).isoformat()
                if dt_iso not in maximeter:
                    maximeter[dt_iso] = init_maxpower(dt_iso)
                for _scope in self.maximeter_stats:
                    if self.sid[_scope] == stat["statistic_id"]:
                        _key = f"value_{_scope}"
                        maximeter[dt_iso][_key] = round(stat["mean"], 1)
                        break

        # load into websockets
        self._data["ws_maximeter"] = build_ws_data(maximeter)

        # load maximeter attributes
        values = np.array([x["value_kW"] for x in self._data["ws_maximeter"]])
        max_idx = np.argmax(values)

        attrs["max_power_kW"] = self._data["ws_maximeter"][max_idx]["value_kW"]
        attrs["max_power_date"] = self._data["ws_maximeter"][max_idx]["datetime"]
        attrs["max_power_mean_kW"] = round(np.mean(values), 1)
        attrs["max_power_90perc_kW"] = round(np.percentile(values, 90), 1)

        # update state
        self._data["state"] = STATE_READY

        await Store(
            self.hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREAMBLE}_{self.id.upper()}",
            encoder=DateTimeEncoder,
        ).async_save({x: self._datadis.data[x] for x in STORAGE_ELEMENTS})

        return True
