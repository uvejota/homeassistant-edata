"""HA Long Term Statistics for e-data"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import homeassistant.components.recorder.util as recorder_util
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
from homeassistant.util import dt as dt_util

from . import const
from .edata.processors import utils

_LOGGER = logging.getLogger(__name__)


def get_db_instance(hass):
    """Workaround for older HA versions"""
    try:
        return recorder_util.get_instance(hass)
    except AttributeError:
        return hass


class EdataStatistics:
    """A helper for long term statistics in edata"""

    def __init__(self, hass, sensor_id, enable_billing, do_reset, edata_helper):
        self.id = sensor_id
        self.hass = hass
        self._billing = enable_billing
        self._reset = do_reset
        self._edata = edata_helper
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
        if self._billing:
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

    async def test_statistics_integrity(self):
        """Test statistics integrity"""

        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            _stats = await get_db_instance(self.hass).async_add_executor_job(
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
                    _inc = round(stat["sum"] - _sum, 1)
                    _sum = stat["sum"]
                    if _inc < 0:
                        # if negative increment, data has to be wiped
                        return False
        return True

    async def clear_all_statistics(self):
        """Clear edata long term statistics"""

        # get all ids starting with edata:xxxx
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
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
            await get_db_instance(self.hass).async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                to_clear,
            )

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data"""
        # fetch last stats
        last_stats = {
            x: await get_db_instance(self.hass).async_add_executor_job(
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
            if not self._reset:
                _LOGGER.warning(const.WARN_MISSING_STATS, self.id)

        new_stats = {x: [] for x in self.sid}

        new_stats.update(
            self._build_consumption_stats(
                dt_from=last_record_dt.get("kWh", None),
                last_stats=last_stats,
            )
        )

        if self._billing:
            new_stats.update(
                self._build_cost_stats(
                    dt_from=last_record_dt.get("eur", None),
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

    def _build_consumption_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for consumptions"""
        if dt_from is None:
            dt_from = dt_util.as_local(datetime(1970, 1, 1))

        # retrieve sum for summable stats (consumptions)
        _significant_stats = []
        _significant_stats.extend(self.consumption_stats)

        _sum = {
            x: last_stats[x][self.sid[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in _significant_stats
        }

        new_stats = {x: [] for x in _significant_stats}

        if len(self._edata.data[const.DATA_CONTRACTS]) == 0:
            return {}

        _label = "value_kWh"
        for data in self._edata.data.get("consumptions", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = utils.get_pvpc_tariff(data["datetime"])
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
        return new_stats

    def _build_cost_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for cost"""
        if dt_from is None:
            dt_from = dt_util.as_local(datetime(1970, 1, 1))

        # retrieve sum for summable stats (costs)
        _significant_stats = []
        _significant_stats.extend(self.cost_stats)

        _sum = {
            x: last_stats[x][self.sid[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in _significant_stats
        }

        new_stats = {x: [] for x in _significant_stats}

        for data in self._edata.data.get("cost_hourly_sum", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _sum["power_eur"] += (
                    data["power_term"] if "power_eur" in _sum else data["power_term"]
                )
                _sum["energy_eur"] += (
                    data["energy_term"] if "energy_eur" in _sum else data["energy_term"]
                )
                _sum["eur"] += data["value_eur"] if "eur" in _sum else data["value_eur"]

                new_stats["power_eur"].append(
                    StatisticData(
                        start=dt_found,
                        state=data["power_term"],
                        sum=_sum["power_eur"],
                    )
                )

                new_stats["energy_eur"].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                        sum=_sum["energy_eur"],
                    )
                )

                new_stats["eur"].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
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
        for data in self._edata.data.get("maximeter", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = "p1" if utils.get_pvpc_tariff(data["datetime"]) == "p1" else "p2"
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
