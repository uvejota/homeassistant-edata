"""Data update coordinator definitions"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from edata.helpers import EdataHelper
from edata.processors import DataUtils as du
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.const import CURRENCY_EURO, ENERGY_KILO_WATT_HOUR, POWER_KILO_WATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const

from .data import PricingRules, calculate_cost
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
        authorized_nif: str,
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
                p1_kw_year_eur=billing[const.PRICE_P1_KW_YEAR],
                p2_kw_year_eur=billing[const.PRICE_P2_KW_YEAR],
                p1_kwh_eur=billing[const.PRICE_P1_KWH],
                p2_kwh_eur=billing[const.PRICE_P2_KWH],
                p3_kwh_eur=billing[const.PRICE_P3_KWH],
                meter_month_eur=billing[const.PRICE_METER_MONTH],
                market_kw_year_eur=billing[const.PRICE_MARKET_KW_YEAR],
                electricity_tax=billing[const.PRICE_ELECTRICITY_TAX],
                iva_tax=billing[const.PRICE_IVA],
            )

        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.id = self.cups[-4:].lower()

        # init data shared store
        hass.data[const.DOMAIN][self.id.upper()] = {}

        # the api object
        self._datadis = EdataHelper(
            username, password, self.cups, self.authorized_nif, data=prev_data
        )

        # shared storage
        # making self._data to reference hass.data[const.DOMAIN][self.id.upper()] so we can use it like an alias
        self._data = hass.data[const.DOMAIN][self.id.upper()]
        self._data.update(
            {
                const.DATA_STATE: const.STATE_LOADING,
                const.DATA_ATTRIBUTES: {x: None for x in const.ATTRIBUTES},
            }
        )

        if prev_data is not None:
            self._load_data(preprocess=True)

        # stat id aliases
        self.sid = {
            "kWh": const.STAT_ID_KWH(self.id),
            "p1_kWh": const.STAT_ID_P1_KWH(self.id),
            "p2_kWh": const.STAT_ID_P2_KWH(self.id),
            "p3_kWh": const.STAT_ID_P3_KWH(self.id),
            "kW": const.STAT_ID_KW(self.id),
            "p1_kW": const.STAT_ID_P1_KW(self.id),
            "p2_kW": const.STAT_ID_P2_KW(self.id),
        }
        if self._billing is not None:
            self.sid.update(
                {
                    "eur": const.STAT_ID_EUR(self.id),
                    "power_eur": const.STAT_ID_POWER_EUR(self.id),
                    "energy_eur": const.STAT_ID_ENERGY_EUR(self.id),
                }
            )

        # stats id grouping
        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "kW"]
        self.cost_stats = ["power_eur", "energy_eur", "eur"]

        super().__init__(
            hass,
            _LOGGER,
            name=const.COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API."""

        # preload attributes if first boot
        if (
            not self.reset
            and self._data.get(const.DATA_STATE, const.STATE_LOADING)
            == const.STATE_LOADING
        ):
            if False is await self._test_statistics_integrity():
                self.reset = True
                _LOGGER.warning(
                    const.WARN_INCONSISTENT_STORAGE,
                    self.id.upper(),
                )

        if self.reset:
            await self.clear_all_statistics()

        # fetch last month or last 365 days
        await self.hass.data[DATA_INSTANCE].async_add_executor_job(
            self._datadis.update,
            datetime.today() - timedelta(days=365),  # since: 1 year ago
            datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(minutes=1),  # to: yesterday midnight
        )

        await self.update_statistics()

        self._load_data()

        await Store(
            self.hass,
            const.STORAGE_VERSION,
            f"{const.STORAGE_KEY_PREAMBLE}_{self.id.upper()}",
            encoder=DateTimeEncoder,
        ).async_save(self._datadis.data)

        # put reset flag down
        if self.reset:
            self.reset = False

        return self._data

    def _load_data(self, preprocess=False):
        """Load data found in built-in statistics into state, attributes and websockets"""

        try:
            if preprocess:
                self._datadis.process_data()

            # reference to attributes shared storage
            attrs = self._data[const.DATA_ATTRIBUTES]
            attrs.update(self._datadis.attributes)

            # load into websockets
            self._data[const.WS_CONSUMPTIONS_DAY] = self._datadis.data[
                "consumptions_daily_sum"
            ]
            self._data[const.WS_CONSUMPTIONS_MONTH] = self._datadis.data[
                "consumptions_monthly_sum"
            ]
            self._data["ws_maximeter"] = self._datadis.data["maximeter"]

            # update state
            self._data["state"] = self._datadis.attributes[
                "last_registered_kWh_date"
            ].strftime("%d/%m/%Y")

        except Exception:
            _LOGGER.warning("Some data is missing, will try to fetch later")
            return False

        return True

    async def _test_statistics_integrity(self):
        """Test statistics integrity"""

        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            _stats = await self.hass.data[DATA_INSTANCE].async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_local(datetime(1970, 1, 1)),
                None,
                [self.sid[x] for x in self.consumption_stats],
                aggr,
            )
            for key in _stats:
                # for each stat key (p1, p2, p3...)
                _sum = 0
                for stat in _stats[key]:
                    for scope in [
                        matching_stat
                        for matching_stat in self.consumption_stats
                        if self.sid[matching_stat] == stat["statistic_id"]
                    ]:
                        _inc = round(stat["sum"] - _sum, 1)
                        _sum = stat["sum"]
                        if _inc < 0:
                            # if negative increment, data has to be wiped
                            return False
        return True

    async def clear_all_statistics(self):
        """Clear edata long term statistics"""

        # get all ids starting with edata:xxxx
        all_ids = await self.hass.data[DATA_INSTANCE].async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_clear = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(f"{const.DOMAIN}:{self.id}")
        ]
        if len(to_clear) > 0:
            # wipe them
            _LOGGER.warning(
                const.WARN_STATISTICS_CLEAR,
                to_clear,
            )
            await self.hass.data[DATA_INSTANCE].async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                to_clear,
            )

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data"""
        # fetch last stats
        last_stats = {
            x: await self.hass.data[DATA_INSTANCE].async_add_executor_job(
                get_last_statistics, self.hass, 1, self.sid[x], True
            )
            for x in self.sid
        }

        # get last record local datetime and eval if any stat is missing
        last_record_dt = {}
        try:
            last_record_dt = {
                x: dt_util.parse_datetime(last_stats[x][self.sid[x]][0]["end"])
                for x in self.sid
            }
        except KeyError as _:
            if not self.reset:
                _LOGGER.warning(const.WARN_MISSING_STATS, self.id)

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

    async def _add_statistics(self, new_stats):
        """Add new statistics"""

        for scope in new_stats:
            if scope in self.consumption_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=ENERGY_KILO_WATT_HOUR,
                )
            elif scope in self.cost_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif scope in self.maximeter_stats:
                metadata = StatisticMetaData(
                    has_mean=True,
                    has_sum=False,
                    name=const.STAT_TITLE_KW(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=self.sid[scope],
                    unit_of_measurement=POWER_KILO_WATT,
                )
            else:
                break
            async_add_external_statistics(self.hass, metadata, new_stats[scope])

    def _build_consumption_and_cost_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for consumptions and cost"""
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

        if len(self._datadis.data[const.DATA_CONTRACTS]) == 0:
            return {}

        _pwr = [
            self._datadis.data[const.DATA_CONTRACTS][-1]["power_p1"],
            self._datadis.data[const.DATA_CONTRACTS][-1]["power_p2"],
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
                    # TODO migrate billing processing to python-edata package
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
        """Build long-term statistics for maximeter"""

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
