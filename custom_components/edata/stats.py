"""HA Long Term Statistics for e-data."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from dateutil import relativedelta

from edata.helpers import EdataHelper
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
from .utils import get_db_instance

_LOGGER = logging.getLogger(__name__)


class EdataStatistics:
    """A helper for long term statistics in edata."""

    def __init__(
        self,
        hass: HomeAssistant,
        sensor_id: str,
        enable_billing: bool,
        edata_helper: EdataHelper,
    ) -> None:
        """EdataStatistics constructor."""

        self.id = sensor_id
        self.hass = hass
        self.is_billing_enabled = enable_billing
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
        if self.is_billing_enabled:
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

        self._last_stats_sum = None
        self._last_stats_dt = None

        self._stat_id_pre = f"{const.DOMAIN}:{self.id}"

    async def _update_last_stats_summary(self):
        """Update self._last_stats_sum and self._last_stats_dt."""

        statistic_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        statistic_ids = [
            x["statistic_id"]
            for x in statistic_ids
            if x["statistic_id"].startswith(self._stat_id_pre)
        ]

        # fetch last stats
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            last_stats = {
                _stat: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics, self.hass, 1, _stat, True
                )
                for _stat in statistic_ids
            }
        else:
            last_stats = {
                _stat: await get_db_instance(self.hass).async_add_executor_job(
                    get_last_statistics,
                    self.hass,
                    1,
                    _stat,
                    True,
                    {"max", "sum"},
                )
                for _stat in statistic_ids
            }

        # get last record local datetime and eval if any stat is missing
        last_record_dt = {}
        if MAJOR_VERSION < 2022 or (MAJOR_VERSION == 2022 and MINOR_VERSION < 12):
            for x in statistic_ids:
                last_record_dt[x] = dt_util.parse_datetime(last_stats[x][x][0]["end"])
        elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
            for x in statistic_ids:
                last_record_dt[x] = dt_util.as_local(last_stats[x][x][0]["end"])
        else:
            for x in statistic_ids:
                last_record_dt[x] = dt_util.utc_from_timestamp(
                    last_stats[x][x][0]["end"]
                )

        # store most recent stat for each statistic_id
        self._last_stats_dt = last_record_dt
        self._last_stats_sum = {
            x: last_stats[x][x][0]["sum"]
            for x in last_stats
            if "sum" in last_stats[x][x][0]
        }

    async def rebuild_recent_statistics(self, from_dt: datetime | None = None):
        """Rebuild edata statistics since a given datetime. Defaults to last year."""

        # give from_dt a proper default value
        if from_dt is None:
            from_dt = (
                datetime.now().replace(day=1, hour=0, minute=0, second=0)
                - timedelta(hours=1)
                - relativedelta.relativedelta(years=1)
            )

        # get all statistic_ids starting with edata:<id/scups>
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_clear = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(self._stat_id_pre)
        ]

        if len(to_clear) == 0:
            return

        # retrieve stored statistics along with its metadata
        old_metadata = await get_db_instance(self.hass).async_add_executor_job(
            get_metadata, self.hass
        )

        old_data = await get_db_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            datetime(1970, 1, 1),
            from_dt,
            set(to_clear),
            "hour",
            None,
            {"state", "sum"},
        )

        # wipe all-time statistics (since it is the only method provided by home assistant)
        _LOGGER.warning(
            const.WARN_STATISTICS_CLEAR,
            to_clear,
        )
        get_db_instance(self.hass).async_clear_statistics(to_clear)

        # now restore old statistics
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

        # ... at this point, you DON'T know when will the recorder instance finish the statistics import.
        # this is dirty, but it seems to work most of the times
        await asyncio.sleep(5)
        await self.update_statistics()

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data."""

        # first fetch from db last statistics for current id
        await self._update_last_stats_summary()

        await self._update_consumption_stats()
        await self._update_maximeter_stats()

        if self.is_billing_enabled:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def _add_statistics(self, new_stats):
        """Add new statistics as a bundle."""

        for stat_id in new_stats:
            if stat_id in self.consumption_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                )
            elif stat_id in self.cost_stats:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif stat_id in self.maximeter_stats:
                metadata = StatisticMetaData(
                    has_mean=True,
                    has_sum=False,
                    name=const.STAT_TITLE_KW(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfPower.KILO_WATT,
                )
            else:
                continue
            async_add_external_statistics(self.hass, metadata, new_stats[stat_id])

    async def _update_consumption_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for consumptions."""

        new_stats = {x: [] for x in self.consumption_stats}

        # init as 0 if need
        for stat_id in self.consumption_stats:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        _label = "value_kWh"
        for data in self._edata.data.get("consumptions", {}):
            dt_found = dt_util.as_local(data["datetime"])
            _p = utils.get_pvpc_tariff(data["datetime"])
            by_tariff_ids = [
                const.STAT_ID_KWH(self.id),
                const.STAT_ID_SURP_KWH(self.id),
            ]
            by_tariff_ids.extend([x for x in self.consumption_stats if _p in x])
            for stat_id in by_tariff_ids:
                if (stat_id not in self._last_stats_dt) or (
                    dt_found >= self._last_stats_dt[stat_id]
                ):
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
                self._last_stats_sum[stat_id] += stat_data["state"]
                stat_data["sum"] = self._last_stats_sum[stat_id]

        await self._add_statistics(new_stats)

    async def _update_cost_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for cost."""
        new_stats = {x: [] for x in self.cost_stats}

        # init as 0 if need
        for stat_id in self.cost_stats:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        for data in self._edata.data.get("cost_hourly_sum", {}):
            dt_found = dt_util.as_local(data["datetime"])
            tariff = utils.get_pvpc_tariff(data["datetime"])

            if (const.STAT_ID_POWER_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_POWER_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_POWER_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["power_term"],
                    )
                )

            if (const.STAT_ID_ENERGY_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_ENERGY_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_ENERGY_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

            if (const.STAT_ID_EUR(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_EUR(self.id)]
            ):
                new_stats[const.STAT_ID_EUR(self.id)].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )

            if tariff == "p1":
                stat_id_energy_eur_px = const.STAT_ID_P1_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P1_EUR(self.id)
            elif tariff == "p2":
                stat_id_energy_eur_px = const.STAT_ID_P2_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P2_EUR(self.id)
            elif tariff == "p3":
                stat_id_energy_eur_px = const.STAT_ID_P3_ENERGY_EUR(self.id)
                stat_id_eur_px = const.STAT_ID_P3_EUR(self.id)

            if (stat_id_energy_eur_px not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_energy_eur_px]
            ):
                new_stats[stat_id_energy_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["energy_term"],
                    )
                )

            if (stat_id_eur_px not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_eur_px]
            ):
                new_stats[stat_id_eur_px].append(
                    StatisticData(
                        start=dt_found,
                        state=data["value_eur"],
                    )
                )

        for stat_id in new_stats:
            for stat_data in new_stats[stat_id]:
                self._last_stats_sum[stat_id] += stat_data["state"]
                stat_data["sum"] = self._last_stats_sum[stat_id]

        await self._add_statistics(new_stats)

    async def _update_maximeter_stats(self) -> dict[str, list[StatisticData]]:
        """Build long-term statistics for maximeter."""

        _label = "value_kW"
        new_stats = {x: [] for x in self.maximeter_stats}

        for data in self._edata.data.get("maximeter", {}):
            dt_found = dt_util.as_local(data["datetime"])
            stat_id_by_tariff = (
                const.STAT_ID_P1_KW(self.id)
                if utils.get_pvpc_tariff(data["datetime"]) == "p1"
                else const.STAT_ID_P2_KW(self.id)
            )

            if (const.STAT_ID_KW(self.id) not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[const.STAT_ID_KW(self.id)]
            ):
                new_stats[const.STAT_ID_KW(self.id)].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

            if (stat_id_by_tariff not in self._last_stats_dt) or (
                dt_found >= self._last_stats_dt[stat_id_by_tariff]
            ):
                new_stats[stat_id_by_tariff].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=data[_label],
                        max=data[_label],
                    )
                )

        await self._add_statistics(new_stats)
