"""HA Long Term Statistics for e-data"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import homeassistant.components.recorder.util as recorder_util
from edata.processors import utils
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.const import (
    CURRENCY_EURO,
    ENERGY_KILO_WATT_HOUR,
    MAJOR_VERSION,
    MINOR_VERSION,
    POWER_KILO_WATT,
)
from homeassistant.util import dt as dt_util

from . import const

_LOGGER = logging.getLogger(__name__)

ALIAS_KWH = "kWh"
ALIAS_P1_KWH = "p1_kWh"
ALIAS_P2_KWH = "p2_kWh"
ALIAS_P3_KWH = "p3_kWh"
ALIAS_KW = "kW"
ALIAS_P1_KW = "p1_kW"
ALIAS_P2_KW = "p2_kW"
ALIAS_EUR = "eur"
ALIAS_P1_EUR = "p1_eur"
ALIAS_P2_EUR = "p2_eur"
ALIAS_P3_EUR = "p3_eur"
ALIAS_POWER_EUR = "power_eur"
ALIAS_ENERGY_EUR = "energy_eur"
ALIAS_ENERGY_P1_EUR = "p1_energy_eur"
ALIAS_ENERGY_P2_EUR = "p2_energy_eur"
ALIAS_ENERGY_P3_EUR = "p3_energy_eur"


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
            ALIAS_KWH: const.STAT_ID_KWH(self.id),
            ALIAS_P1_KWH: const.STAT_ID_P1_KWH(self.id),
            ALIAS_P2_KWH: const.STAT_ID_P2_KWH(self.id),
            ALIAS_P3_KWH: const.STAT_ID_P3_KWH(self.id),
            ALIAS_KW: const.STAT_ID_KW(self.id),
            ALIAS_P1_KW: const.STAT_ID_P1_KW(self.id),
            ALIAS_P2_KW: const.STAT_ID_P2_KW(self.id),
        }
        if self._billing:
            self.sid.update(
                {
                    ALIAS_EUR: const.STAT_ID_EUR(self.id),
                    ALIAS_P1_EUR: const.STAT_ID_P1_EUR(self.id),
                    ALIAS_P2_EUR: const.STAT_ID_P2_EUR(self.id),
                    ALIAS_P3_EUR: const.STAT_ID_P3_EUR(self.id),
                    ALIAS_POWER_EUR: const.STAT_ID_POWER_EUR(self.id),
                    ALIAS_ENERGY_EUR: const.STAT_ID_ENERGY_EUR(self.id),
                    ALIAS_ENERGY_P1_EUR: const.STAT_ID_P1_ENERGY_EUR(self.id),
                    ALIAS_ENERGY_P2_EUR: const.STAT_ID_P2_ENERGY_EUR(self.id),
                    ALIAS_ENERGY_P3_EUR: const.STAT_ID_P3_ENERGY_EUR(self.id),
                }
            )

        # stats id grouping
        self.consumption_stats = [ALIAS_P1_KWH, ALIAS_P2_KWH, ALIAS_P3_KWH, ALIAS_KWH]
        self.maximeter_stats = [ALIAS_P1_KW, ALIAS_P2_KW, ALIAS_KW]
        self.cost_stats = [
            ALIAS_POWER_EUR,
            ALIAS_ENERGY_EUR,
            ALIAS_ENERGY_P1_EUR,
            ALIAS_ENERGY_P2_EUR,
            ALIAS_ENERGY_P3_EUR,
            ALIAS_EUR,
            ALIAS_P1_EUR,
            ALIAS_P2_EUR,
            ALIAS_P3_EUR,
        ]

    async def test_statistics_integrity(self):
        """Test statistics integrity"""

        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
                _stats = await get_db_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    dt_util.as_local(datetime(1970, 1, 1)),
                    None,
                    [self.sid[x] for x in self.consumption_stats],
                    aggr,
                )
            else:
                _stats = await get_db_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    dt_util.as_local(datetime(1970, 1, 1)),
                    None,
                    [self.sid[x] for x in self.consumption_stats],
                    aggr,
                    None,
                    set(["sum"]),
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
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            last_stats = {
                x: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics, self.hass, 1, self.sid[x], True
                )
                for x in self.sid
            }
        else:
            last_stats = {
                x: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics,
                    self.hass,
                    1,
                    self.sid[x],
                    True,
                    set(["max", "sum"]),
                )
                for x in self.sid
            }

        # get last record local datetime and eval if any stat is missing
        last_record_dt = {}
        try:
            if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
                last_record_dt = {
                    x: dt_util.parse_datetime(last_stats[x][self.sid[x]][0]["end"])
                    for x in self.sid
                }
            elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
                last_record_dt = {
                    x: dt_util.as_local(last_stats[x][self.sid[x]][0]["end"])
                    for x in self.sid
                }
            else:
                last_record_dt = {
                    x: dt_util.as_local(
                        dt_util.utc_from_timestamp(last_stats[x][self.sid[x]][0]["end"])
                    )
                    for x in self.sid
                }
        except KeyError:
            if not self._reset:
                _LOGGER.warning(const.WARN_MISSING_STATS, self.id)

        new_stats = {x: [] for x in self.sid}

        new_stats.update(
            self._build_consumption_stats(
                dt_from=last_record_dt.get(ALIAS_KWH, None),
                last_stats=last_stats,
            )
        )

        if self._billing:
            new_stats.update(
                self._build_cost_stats(
                    dt_from=last_record_dt.get(ALIAS_EUR, None),
                    last_stats=last_stats,
                )
            )

        new_stats.update(
            self._build_maximeter_stats(dt_from=last_record_dt.get(ALIAS_KW, None))
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
                continue
            async_add_external_statistics(self.hass, metadata, new_stats[scope])

    def _build_consumption_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for consumptions"""
        dt_from = (
            dt_util.as_local(datetime(1970, 1, 1))
            if dt_from is None
            else dt_util.as_local(dt_from)
        )

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
                _sum[ALIAS_KWH] += data[_label]
                new_stats[ALIAS_KWH].append(
                    StatisticData(
                        start=dt_found,
                        state=data[_label],
                        sum=_sum[ALIAS_KWH],
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
        dt_from = (
            dt_util.as_local(datetime(1970, 1, 1))
            if dt_from is None
            else dt_util.as_local(dt_from)
        )

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
                _p = utils.get_pvpc_tariff(data["datetime"])

                _sum[ALIAS_POWER_EUR] += data["power_term"]
                _sum[ALIAS_ENERGY_EUR] += data["energy_term"]
                _sum[ALIAS_EUR] += data["value_eur"]

                new_stats[ALIAS_POWER_EUR].append(
                    StatisticData(
                        start=dt_found,
                        state=data["power_term"],
                        sum=_sum[ALIAS_POWER_EUR],
                    )
                )

                new_stats[ALIAS_ENERGY_EUR].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                        sum=_sum[ALIAS_ENERGY_EUR],
                    )
                )
                _sum[_p + "_" + ALIAS_ENERGY_EUR] += data["energy_term"]
                new_stats[_p + "_" + ALIAS_ENERGY_EUR].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                        sum=_sum[_p + "_" + ALIAS_ENERGY_EUR],
                    )
                )

                new_stats[ALIAS_EUR].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                        sum=_sum[ALIAS_EUR],
                    )
                )

                _sum[_p + "_" + ALIAS_EUR] += data["value_eur"]
                new_stats[_p + "_" + ALIAS_EUR].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                        sum=_sum[_p + "_" + ALIAS_EUR],
                    )
                )

        return new_stats

    def _build_maximeter_stats(self, dt_from: datetime | None):
        """Build long-term statistics for maximeter"""

        _label = "value_kW"
        new_stats = {x: [] for x in self.maximeter_stats}
        dt_from = (
            dt_util.as_local(datetime(1970, 1, 1))
            if dt_from is None
            else dt_util.as_local(dt_from)
        )
        for data in self._edata.data.get("maximeter", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = "p1" if utils.get_pvpc_tariff(data["datetime"]) == "p1" else "p2"
                new_stats[ALIAS_KW].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )
                new_stats[_p + "_kW"].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

        return new_stats
