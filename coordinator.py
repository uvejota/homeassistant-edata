"""Data update coordinator definitions"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from dateutil.relativedelta import relativedelta
from edata.connectors import DatadisConnector
from edata.processors import DataUtils as du
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    day_start_end,
    get_last_statistics,
    list_statistic_ids,
    month_start_end,
    statistics_during_period,
)
from homeassistant.const import CURRENCY_EURO, ENERGY_KILO_WATT_HOUR, POWER_KILO_WATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
)
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
    PRICE_ELECTRICITY_TAX,
    PRICE_IVA,
    PRICE_MARKET_KW_YEAR,
    PRICE_METER_MONTH,
    PRICE_P1_KW_YEAR,
    PRICE_P1_KWH,
    PRICE_P2_KW_YEAR,
    PRICE_P2_KWH,
    PRICE_P3_KWH,
    STAT_ID_ENERGY_EUR,
    STAT_ID_EUR,
    STAT_ID_KW,
    STAT_ID_KWH,
    STAT_ID_P1_KW,
    STAT_ID_P1_KWH,
    STAT_ID_P2_KW,
    STAT_ID_P2_KWH,
    STAT_ID_P3_KWH,
    STAT_ID_POWER_EUR,
    STAT_TITLE_EUR,
    STAT_TITLE_KW,
    STAT_TITLE_KWH,
    STATE_LOADING,
    STORAGE_ELEMENTS,
    STORAGE_KEY_PREAMBLE,
    STORAGE_VERSION,
    WARN_INCONSISTENT_STORAGE,
    WARN_MISSING_STATS,
    WARN_STATISTICS_CLEAR,
    WS_CONSUMPTIONS_DAY,
    WS_CONSUMPTIONS_MONTH,
)
from .data import PricingRules, calculate_cost, init_consumption, init_maxpower
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
        self._billing = None
        if billing is not None:
            self._billing = PricingRules(
                p1_kw_year_eur=billing[PRICE_P1_KW_YEAR],
                p2_kw_year_eur=billing[PRICE_P2_KW_YEAR],
                p1_kwh_eur=billing[PRICE_P1_KWH],
                p2_kwh_eur=billing[PRICE_P2_KWH],
                p3_kwh_eur=billing[PRICE_P3_KWH],
                meter_month_eur=billing[PRICE_METER_MONTH],
                market_kw_year_eur=billing[PRICE_MARKET_KW_YEAR],
                electricity_tax=billing[PRICE_ELECTRICITY_TAX],
                iva_tax=billing[PRICE_IVA],
            )

        self.cups = cups.upper()
        self.id = self.cups[-4:].lower()

        # init data shared store
        hass.data[DOMAIN][self.id.upper()] = {}

        # the api object
        self._datadis = DatadisConnector(username, password, data=prev_data)

        # shared storage
        # making self._data to reference hass.data[DOMAIN][self.id.upper()] so we can use it like an alias
        self._data = hass.data[DOMAIN][self.id.upper()]
        self._data.update(
            {DATA_STATE: STATE_LOADING, DATA_ATTRIBUTES: {x: None for x in ATTRIBUTES}}
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
        if self._billing is not None:
            self.sid.update(
                {
                    "eur": STAT_ID_EUR(self.id),
                    "power_eur": STAT_ID_POWER_EUR(self.id),
                    "energy_eur": STAT_ID_ENERGY_EUR(self.id),
                }
            )

        # stats id grouping
        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "kW"]
        self.cost_stats = ["power_eur", "energy_eur", "eur"]

        super().__init__(
            hass,
            _LOGGER,
            name=COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API."""

        # preload attributes if first boot
        if (
            not self.reset
            and self._data.get(DATA_STATE, STATE_LOADING) == STATE_LOADING
        ):
            if False is await self.load_data():
                self.reset = True
                _LOGGER.warning(
                    WARN_INCONSISTENT_STORAGE,
                    self.id.upper(),
                )

        if self.reset:
            await self._clear_all_statistics()

        # fetch last stats
        last_stats = {
            x: await get_instance(self.hass).async_add_executor_job(
                get_last_statistics, self.hass, 1, self.sid[x], True
            )
            for x in self.sid
        }

        # get last record local datetime and eval if any stat is missing
        full_update = False
        last_record_dt = {}
        try:
            last_record_dt = {
                x: dt_util.parse_datetime(last_stats[x][self.sid[x]][0]["end"])
                for x in self.sid
            }
        except KeyError as _:
            if not self.reset:
                _LOGGER.warning(WARN_MISSING_STATS, self.id)
            full_update = True

        # fetch last month or last 365 days
        await self.hass.async_add_executor_job(
            self._datadis.update,
            self.cups,
            min(
                (last_record_dt["kWh"].replace(tzinfo=None)),
                (last_record_dt["kW"].replace(tzinfo=None)),
                datetime.today() - relativedelta(months=1),
            )
            if not full_update
            else datetime.today() - timedelta(days=365),
            datetime.now(),
        )

        new_stats = {x: [] for x in self.sid}

        new_stats.update(
            self._build_consumption_and_cost_stats(
                dt_from=last_record_dt.get("kWh", None),
                last_stats=last_stats,
            )
        )

        new_stats.update(
            self._build_maximeter_stats(dt_from=last_record_dt.get("kW", None))
        )

        await self._add_statistics(new_stats)

        # schedule state and attributes reload
        async def reload(*args):
            if False is await self.load_data() and not self.reset:
                _LOGGER.warning(
                    WARN_INCONSISTENT_STORAGE,
                    self.id.upper(),
                )
                await self._async_update_data()

        async_track_point_in_utc_time(
            self.hass, reload, dt_util.utcnow() + timedelta(minutes=5)
        )

        # put reset flag down
        if self.reset:
            self.reset = False

        return self._data

    async def load_data(self):
        """Load data found in built-in statistics into state, attributes and websockets"""

        # reference to attributes shared storage
        attrs = self._data[DATA_ATTRIBUTES]

        # anonymous function to sort dicts based of datetime key, and return a list of dicts for using in websockets
        build_ws_data = lambda dict_shaped_data: sorted(
            [dict_shaped_data[element] for element in dict_shaped_data],
            key=lambda item: dt_util.parse_datetime(item["datetime"]),
        )

        # add supplies-related attributes
        attrs.update(
            {
                "cups": self.cups
                if self.cups in [x["cups"] for x in self._datadis.data[DATA_SUPPLIES]]
                else None
            }
        )

        # add contract-related attributes
        attrs.update(
            {
                "contract_p1_kW": self._datadis.data[DATA_CONTRACTS][-1].get(
                    "power_p1", None
                )
                if len(self._datadis.data[DATA_CONTRACTS]) > 0
                else None,
                "contract_p2_kW": self._datadis.data[DATA_CONTRACTS][-1].get(
                    "power_p2", None
                )
                if len(self._datadis.data[DATA_CONTRACTS]) > 0
                else None,
            }
        )

        # read last statistics
        last_stats = {
            x: await get_instance(self.hass).async_add_executor_job(
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
            _stats = await get_instance(self.hass).async_add_executor_job(
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
            for key in ("", "_p1", "_p2", "_p3"):
                attrs[f"yesterday{key}_kWh"] = consumptions["day"][_date_str][
                    f"value{key}_kWh"
                ]
            attrs["yesterday_hours"] = round(
                last_record_dt["kWh"].hour
                if last_record_dt["kWh"]
                < day_start_end(dt_util.as_local(datetime.today()))[0]
                else 24,
                2,
            )
        # current month attributes
        this_month_start = month_start_end(datetime.now().replace(day=1))[0]
        _date_str = dt_util.as_local(this_month_start).isoformat()
        if _date_str in consumptions["month"]:
            for key in ("", "_p1", "_p2", "_p3"):
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
            for key in ("", "_p1", "_p2", "_p3"):
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
        _stats = await get_instance(self.hass).async_add_executor_job(
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
        self._data["state"] = last_record_dt["kWh"].strftime("%d/%m/%Y")

        for update_callback in self._listeners:
            update_callback()

        await Store(
            self.hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREAMBLE}_{self.id.upper()}",
            encoder=DateTimeEncoder,
        ).async_save({x: self._datadis.data[x] for x in STORAGE_ELEMENTS})

        return True

    async def _clear_all_statistics(self):
        # get all ids starting with edata:xxxx
        all_ids = await get_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_clear = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(f"{DOMAIN}:{self.id}")
        ]
        if len(to_clear) > 0:
            # wipe them
            _LOGGER.warning(
                WARN_STATISTICS_CLEAR,
                to_clear,
            )
            await get_instance(self.hass).async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                to_clear,
            )

    async def _add_statistics(self, new_stats):
        for scope in new_stats:
            if scope in self.consumption_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=STAT_TITLE_KWH(self.id, scope),
                    source=DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                )
            elif scope in self.cost_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=STAT_TITLE_EUR(self.id, scope),
                    source=DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif scope in self.maximeter_stats:
                metadata = StatisticMetaData(
                    has_mean=True,
                    has_sum=False,
                    name=STAT_TITLE_KW(self.id, scope),
                    source=DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=POWER_KILO_WATT,
                )
            else:
                break
            async_add_external_statistics(self.hass, metadata, new_stats[scope])

    def _build_consumption_and_cost_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        if dt_from is None:
            dt_from = dt_util.as_local(datetime(1970, 1, 1))

        # retrieve sum for summable stats (consumptions)
        _significant_stats = []
        _significant_stats.extend(self.consumption_stats)
        if self._billing is not None:
            _significant_stats.extend(self.cost_stats)
        _sum = {
            x: last_stats[x][self.sid[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in _significant_stats
        }

        new_stats = {x: [] for x in _significant_stats}

        _pwr = [
            self._datadis.data[DATA_CONTRACTS][-1]["power_p1"],
            self._datadis.data[DATA_CONTRACTS][-1]["power_p2"],
        ]

        _label = "value_kWh"
        for data in self._datadis.data.get("consumptions", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["kWh"] += data[_label]
                new_stats["kWh"].append(
                    StatisticData(
                        start=dt_found,
                        state=data[_label],
                        sum=_sum["kWh"],
                    )
                )
                _sum[_p + "_kWh"] += data[_label]
                new_stats[_p + "_kWh"].append(
                    StatisticData(
                        start=dt_found,
                        state=data[_label],
                        sum=_sum[_p + "_kWh"],
                    )
                )
                if self._billing is not None:
                    cost = calculate_cost(
                        self._billing,
                        _pwr,
                        [
                            data[_label] if _p == "p1" else 0,
                            data[_label] if _p == "p2" else 0,
                            data[_label] if _p == "p3" else 0,
                        ],
                    )

                    _sum["power_eur"] += (
                        cost["power_term"]
                        if "power_eur" in _sum
                        else cost["power_term"]
                    )
                    _sum["energy_eur"] += (
                        cost["energy_term"]
                        if "energy_eur" in _sum
                        else cost["energy_term"]
                    )
                    _sum["eur"] += (
                        cost["value_eur"] if "eur" in _sum else cost["value_eur"]
                    )

                    new_stats["power_eur"].append(
                        StatisticData(
                            start=dt_found,
                            state=cost["power_term"],
                            sum=_sum["power_eur"],
                        )
                    )

                    new_stats["energy_eur"].append(
                        StatisticData(
                            start=dt_found,
                            state=cost["energy_term"],
                            sum=_sum["energy_eur"],
                        )
                    )

                    new_stats["eur"].append(
                        StatisticData(
                            start=dt_found,
                            state=cost["value_eur"],
                            sum=_sum["eur"],
                        )
                    )

        return new_stats

    def _build_maximeter_stats(self, dt_from: datetime | None):
        _label = "value_kW"
        new_stats = {x: [] for x in self.maximeter_stats}
        if dt_from is None:
            dt_from = dt_util.as_local(datetime(1970, 1, 1))
        for data in self._datadis.data.get("maximeter", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = "p1" if du.get_pvpc_tariff(data["datetime"]) == "p1" else "p2"
                new_stats["kW"].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        mean=data[_label],
                    )
                )
                new_stats[_p + "_kW"].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        mean=data[_label],
                    )
                )

        return new_stats
