"""HA Long Term Statistics for e-data."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time
import typing
from typing import Any

from dateutil import relativedelta

from edata.processors import utils
from homeassistant.components.recorder.db_schema import Statistics
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    get_metadata,
    list_statistic_ids,
    statistics_during_period,
)
import homeassistant.components.recorder.util as recorder_util
from homeassistant.const import (
    CURRENCY_EURO,
    MAJOR_VERSION,
    MINOR_VERSION,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import const

_LOGGER = logging.getLogger(__name__)


def get_db_instance(hass: HomeAssistant):
    """Workaround for older HA versions."""
    try:
        return recorder_util.get_instance(hass)
    except AttributeError:
        return hass


class EdataStatistics:
    """A helper for long term statistics in edata."""

    def __init__(
        self, hass: HomeAssistant, sensor_id, enable_billing, do_reset, edata_helper
    ) -> None:
        """EdataStatistics constructor."""

        self.id = sensor_id
        self.hass = hass
        self._billing = enable_billing
        self._reset = do_reset
        self._edata = edata_helper

        # stat id aliases
        self.sid = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
            const.STAT_ID_SURP_KWH(self.id),
            const.STAT_ID_P1_SURP_KWH(self.id),
            const.STAT_ID_P2_SURP_KWH(self.id),
            const.STAT_ID_P3_SURP_KWH(self.id),
            const.STAT_ID_KW(self.id),
            const.STAT_ID_P1_KW(self.id),
            const.STAT_ID_P2_KW(self.id),
        }
        if self._billing:
            self.sid.update(
                {
                    const.STAT_ID_EUR(self.id),
                    const.STAT_ID_P1_EUR(self.id),
                    const.STAT_ID_P2_EUR(self.id),
                    const.STAT_ID_P3_EUR(self.id),
                    const.STAT_ID_POWER_EUR(self.id),
                    const.STAT_ID_ENERGY_EUR(self.id),
                    const.STAT_ID_P1_ENERGY_EUR(self.id),
                    const.STAT_ID_P2_ENERGY_EUR(self.id),
                    const.STAT_ID_P3_ENERGY_EUR(self.id),
                }
            )

        # stats id grouping
        self.consumption_stats = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
            const.STAT_ID_SURP_KWH(self.id),
            const.STAT_ID_P1_SURP_KWH(self.id),
            const.STAT_ID_P2_SURP_KWH(self.id),
            const.STAT_ID_P3_SURP_KWH(self.id),
        }
        self.maximeter_stats = {
            const.STAT_ID_KW(self.id),
            const.STAT_ID_P1_KW(self.id),
            const.STAT_ID_P2_KW(self.id),
        }
        self.cost_stats = {
            const.STAT_ID_EUR(self.id),
            const.STAT_ID_P1_EUR(self.id),
            const.STAT_ID_P2_EUR(self.id),
            const.STAT_ID_P3_EUR(self.id),
            const.STAT_ID_POWER_EUR(self.id),
            const.STAT_ID_ENERGY_EUR(self.id),
            const.STAT_ID_P1_ENERGY_EUR(self.id),
            const.STAT_ID_P2_ENERGY_EUR(self.id),
            const.STAT_ID_P3_ENERGY_EUR(self.id),
        }

    async def test_statistics_integrity(self):
        """Test statistics integrity."""

        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
                _stats = await get_db_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    dt_util.as_local(datetime(1970, 1, 1)),
                    None,
                    list(self.consumption_stats),
                    aggr,
                )
            else:
                _stats = await get_db_instance(self.hass).async_add_executor_job(
                    statistics_during_period,
                    self.hass,
                    dt_util.as_local(datetime(1970, 1, 1)),
                    None,
                    list(self.consumption_stats),
                    aggr,
                    None,
                    {"sum"},
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

    async def rebuild_recent_statistics(self):
        """Clear edata long term statistics."""

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

            old_metadata = await get_db_instance(self.hass).async_add_executor_job(
                get_metadata, self.hass
            )

            old_data = await get_db_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                datetime(1970, 1, 1),
                datetime.now().replace(day=1, hour=0, minute=0, second=0)
                - timedelta(hours=1)
                - relativedelta.relativedelta(years=1),
                set(to_clear),
                "hour",
                None,
                {"state", "sum"},
            )
            get_db_instance(self.hass).async_clear_statistics(to_clear)
            for stat_id in old_data:
                get_db_instance(self.hass).async_import_statistics(
                    old_metadata[stat_id][1],
                    [
                        StatisticData(
                            start=dt_util.utc_from_timestamp(x["start"]),
                            state=x["state"],
                            sum=x["sum"] if "sum" in x else None,
                            mean=x["mean"] if "mean" in x else None,
                            max=x["max"] if "max" in x else None,
                        )
                        for x in old_data[stat_id]
                    ],
                    Statistics,
                )

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data."""
        # fetch last stats
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            last_stats = {
                x: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics, self.hass, 1, x, True
                )
                for x in self.sid
            }
        else:
            last_stats = {
                x: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics,
                    self.hass,
                    1,
                    x,
                    True,
                    {"max", "sum"},
                )
                for x in self.sid
            }

        # get last record local datetime and eval if any stat is missing
        last_record_dt = {}
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            for x in self.sid:
                try:
                    last_record_dt[x] = dt_util.parse_datetime(
                        last_stats[x][x][0]["end"]
                    )
                except KeyError:
                    if not self._reset:
                        _LOGGER.info(const.WARN_MISSING_STATS, x)
        elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
            for x in self.sid:
                try:
                    last_record_dt[x] = dt_util.as_local(last_stats[x][x][0]["end"])
                except KeyError:
                    if not self._reset:
                        _LOGGER.info(const.WARN_MISSING_STATS, x)
        else:
            for x in self.sid:
                try:
                    last_record_dt[x] = dt_util.utc_from_timestamp(
                        last_stats[x][x][0]["end"]
                    )
                except KeyError:
                    if not self._reset:
                        _LOGGER.info(const.WARN_MISSING_STATS, x)

        _LOGGER.warning(last_record_dt)
        new_stats = {x: [] for x in self.sid}

        new_stats.update(
            self._build_consumption_stats(
                dt_from=last_record_dt.get(const.STAT_ID_KWH(self.id), None),
                last_stats=last_stats,
            )
        )

        if self._billing:
            new_stats.update(
                self._build_cost_stats(
                    dt_from=last_record_dt.get(const.STAT_ID_EUR(self.id), None),
                    last_stats=last_stats,
                )
            )

        new_stats.update(
            self._build_maximeter_stats(
                dt_from=last_record_dt.get(const.STAT_ID_KW(self.id), None)
            )
        )

        await self._add_statistics(new_stats)
        self._reset = False

    async def _add_statistics(self, new_stats):
        """Add new statistics."""

        for scope in new_stats:
            if scope in self.consumption_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=scope,
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                )
            elif scope in self.cost_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=scope,
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif scope in self.maximeter_stats:
                metadata = StatisticMetaData(
                    has_mean=True,
                    has_sum=False,
                    name=const.STAT_TITLE_KW(self.id, scope),
                    source=const.DOMAIN,
                    statistic_id=scope,
                    unit_of_measurement=UnitOfPower.KILO_WATT,
                )
            else:
                continue
            async_add_external_statistics(self.hass, metadata, new_stats[scope])

    def _build_consumption_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for consumptions."""
        dt_from = (
            dt_util.as_local(datetime(1970, 1, 1))
            if dt_from is None
            else dt_util.as_local(dt_from)
        )

        # retrieve sum for summable stats (consumptions)
        _significant_stats = self.consumption_stats

        _sum = {
            x: last_stats[x][x][0].get("sum", 0) if last_stats[x] else 0
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
                by_tariff_ids = [
                    const.STAT_ID_KWH(self.id),
                    const.STAT_ID_SURP_KWH(self.id),
                ]
                by_tariff_ids.extend([x for x in self.consumption_stats if _p in x])
                for stat_id in by_tariff_ids:
                    _label = "value_kWh" if "surp" not in stat_id else "surplus_kWh"
                    if _label in data and data[_label] is not None:
                        new_stats[stat_id].append(
                            StatisticData(
                                start=dt_found,
                                state=data[_label],
                            )
                        )

        for stat_id in new_stats:
            for stat_data in new_stats[stat_id]:
                _sum[stat_id] += stat_data["state"]
                stat_data["sum"] = _sum[stat_id]

        return new_stats

    def _build_cost_stats(
        self, dt_from: datetime | None, last_stats: list[dict[str, Any]]
    ):
        """Build long-term statistics for cost."""
        dt_from = (
            dt_util.as_local(datetime(1970, 1, 1))
            if dt_from is None
            else dt_util.as_local(dt_from)
        )

        # retrieve sum for summable stats (costs)
        _significant_stats = self.cost_stats

        _sum = {
            x: last_stats[x][x][0].get("sum", 0) if last_stats[x] else 0
            for x in _significant_stats
        }

        new_stats = {x: [] for x in _significant_stats}

        for data in self._edata.data.get("cost_hourly_sum", {}):
            dt_found = dt_util.as_local(data["datetime"])
            if dt_found >= dt_from:
                _p = utils.get_pvpc_tariff(data["datetime"])

                new_stats[const.STAT_ID_POWER_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["power_term"],
                    )
                )

                new_stats[const.STAT_ID_ENERGY_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

                new_stats[const.STAT_ID_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )

                if _p == "p1":
                    stat_id_energy_eur_px = const.STAT_ID_P1_ENERGY_EUR(self.id)
                    stat_id_eur_px = const.STAT_ID_P1_EUR(self.id)
                elif _p == "p2":
                    stat_id_energy_eur_px = const.STAT_ID_P2_ENERGY_EUR(self.id)
                    stat_id_eur_px = const.STAT_ID_P2_EUR(self.id)
                elif _p == "p3":
                    stat_id_energy_eur_px = const.STAT_ID_P3_ENERGY_EUR(self.id)
                    stat_id_eur_px = const.STAT_ID_P3_EUR(self.id)

                new_stats[stat_id_energy_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

                new_stats[stat_id_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )

        for stat_id in new_stats:
            for stat_data in new_stats[stat_id]:
                _sum[stat_id] += stat_data["state"]
                stat_data["sum"] = _sum[stat_id]

        return new_stats

    def _build_maximeter_stats(self, dt_from: datetime | None):
        """Build long-term statistics for maximeter."""

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
                _p = (
                    const.STAT_ID_P1_KW(self.id)
                    if utils.get_pvpc_tariff(data["datetime"]) == "p1"
                    else const.STAT_ID_P2_KW(self.id)
                )
                new_stats[const.STAT_ID_KW(self.id)].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )
                new_stats[_p].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

        return new_stats


async def get_consumptions_history(
    hass: HomeAssistant,
    scups: str,
    tariff: None | typing.Union("p1", "p2", "p3"),
    aggr: typing.Union("5minute", "day", "hour", "week", "month"),
    records: int = 30,
):
    "Fetch last N statistics records."
    if tariff is None:
        _stat_id = const.STAT_ID_KWH(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_KWH(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_KWH(scups)
    elif tariff == "p3":
        _stat_id = const.STAT_ID_P3_KWH(scups)

    if aggr == "5minute":
        _dt_unit = timedelta(minutes=5)
    elif aggr == "hour":
        _dt_unit = timedelta(hours=1)
    elif aggr == "day":
        _dt_unit = timedelta(days=1)
    elif aggr == "week":
        _dt_unit = relativedelta.relativedelta(weeks=1)
    elif aggr == "month":
        _dt_unit = relativedelta.relativedelta(months=1)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime.now().replace(hour=0, minute=0, second=0) - records * _dt_unit,
        None,
        {_stat_id},
        aggr,
        None,
        {"change"},
    )
    data = data[_stat_id]
    return [(dt_util.utc_from_timestamp(x["start"]), x["change"]) for x in data]


async def get_surplus_history(
    hass: HomeAssistant,
    scups: str,
    tariff: None | typing.Union("p1", "p2", "p3"),
    aggr: typing.Union("5minute", "day", "hour", "week", "month"),
    records: int = 30,
):
    "Fetch last N statistics records."
    if tariff is None:
        _stat_id = const.STAT_ID_SURP_KWH(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_SURP_KWH(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_SURP_KWH(scups)
    elif tariff == "p3":
        _stat_id = const.STAT_ID_P3_SURP_KWH(scups)

    if aggr == "5minute":
        _dt_unit = timedelta(minutes=5)
    elif aggr == "hour":
        _dt_unit = timedelta(hours=1)
    elif aggr == "day":
        _dt_unit = timedelta(days=1)
    elif aggr == "week":
        _dt_unit = relativedelta.relativedelta(weeks=1)
    elif aggr == "month":
        _dt_unit = relativedelta.relativedelta(months=1)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime.now().replace(hour=0, minute=0, second=0) - records * _dt_unit,
        None,
        {_stat_id},
        aggr,
        None,
        {"change"},
    )
    data = data[_stat_id]
    return [(dt_util.utc_from_timestamp(x["start"]), x["change"]) for x in data]


async def get_maximeter_history(
    hass: HomeAssistant, scups: str, tariff: None | typing.Union("p1", "p2")
):
    "Fetch last N statistics records."
    if tariff is None:
        _stat_id = const.STAT_ID_KW(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_KW(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_KW(scups)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(1970, 1, 1),
        None,
        {_stat_id},
        "day",
        None,
        {"max"},
    )
    data = data[_stat_id]
    return [(dt_util.utc_from_timestamp(x["start"]), x["max"]) for x in data]


async def get_costs_history(
    hass: HomeAssistant,
    scups: str,
    tariff: None | typing.Union("p1", "p2", "p3"),
    aggr: typing.Union("5minute", "day", "hour", "week", "month"),
    records: int = 30,
):
    "Fetch last N statistics records."
    if tariff is None:
        _stat_id = const.STAT_ID_EUR(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_EUR(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_EUR(scups)
    elif tariff == "p3":
        _stat_id = const.STAT_ID_P3_EUR(scups)

    if aggr == "5minute":
        _dt_unit = timedelta(minutes=5)
    elif aggr == "hour":
        _dt_unit = timedelta(hours=1)
    elif aggr == "day":
        _dt_unit = timedelta(days=1)
    elif aggr == "week":
        _dt_unit = relativedelta.relativedelta(weeks=1)
    elif aggr == "month":
        _dt_unit = relativedelta.relativedelta(months=1)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime.now().replace(hour=0, minute=0, second=0) - records * _dt_unit,
        None,
        {_stat_id},
        aggr,
        None,
        {"change"},
    )
    data = data[_stat_id]
    return [(dt_util.utc_from_timestamp(x["start"]), x["change"]) for x in data]
