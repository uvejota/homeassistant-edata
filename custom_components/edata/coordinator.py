"""Data update coordinator definitions."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
import os

from dateutil.relativedelta import relativedelta

from edata.connectors.datadis import RECENT_QUERIES_FILE
from edata.definitions import ATTRIBUTES, PricingRules
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
from homeassistant.helpers.storage import STORAGE_DIR, Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .utils import get_db_instance
import contextlib

_LOGGER = logging.getLogger(__name__)


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics.."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str,
        billing: PricingRules | None = None,
        prev_data=None,
    ) -> None:
        """Initialize the data handler.."""

        # Number of cached months (starting from 1st day of the month will be automatic)
        self._default_cache_months = 12

        # Store properties
        self.hass = hass
        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.id = scups.lower()
        self.billing_rules = billing

        # Check if v2023 storage has already been migrated
        self.is_storage_migration_complete = os.path.exists(
            self.hass.config.path(
                STORAGE_DIR, "edata", f"edata_{self.cups.lower()}.json"
            )
        )

        # Init shared data
        hass.data[const.DOMAIN][self.id] = {}

        # Instantiate the api helper
        if not self.is_storage_migration_complete:
            # ... providing old data manually, if migration hasn't been done yet
            self._edata = EdataHelper(
                username,
                password,
                self.cups,
                self.authorized_nif,
                pricing_rules=self.billing_rules,
                data=prev_data,
                storage_dir_path=self.hass.config.path(STORAGE_DIR),
            )
        else:
            # ... or just providing the storage dir path otherwise
            self._edata = EdataHelper(
                username,
                password,
                self.cups,
                self.authorized_nif,
                pricing_rules=self.billing_rules,
                storage_dir_path=self.hass.config.path(STORAGE_DIR),
            )

        # Making self._data to reference hass.data[const.DOMAIN][self.id] so we can use it like an alias
        self._data = hass.data[const.DOMAIN][self.id]
        self._data.update(
            {
                const.DATA_STATE: const.STATE_LOADING,
                const.DATA_ATTRIBUTES: {x: None for x in ATTRIBUTES},
            }
        )

        self._load_data(preprocess=True)

        # Used statistic IDs (edata:<id>_metric_to_track)
        self.statistic_ids = {
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

        if self.billing_rules:
            # If billing rules are provided, we also track costs
            self.statistic_ids.update(
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

        # Stats id grouped by scope
        self.consumption_stat_ids = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
            const.STAT_ID_SURP_KWH(self.id),
            const.STAT_ID_P1_SURP_KWH(self.id),
            const.STAT_ID_P2_SURP_KWH(self.id),
            const.STAT_ID_P3_SURP_KWH(self.id),
        }

        self.maximeter_stat_ids = {
            const.STAT_ID_KW(self.id),
            const.STAT_ID_P1_KW(self.id),
            const.STAT_ID_P2_KW(self.id),
        }

        self.cost_stat_ids = {
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

        # We also track last stats sum and datetime
        self._last_stats_sum = None
        self._last_stats_dt = None

        # Just the preamble of the statistics
        self._stat_id_preamble = f"{const.DOMAIN}:{self.id}"

        super().__init__(
            hass,
            _LOGGER,
            name=const.COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API.."""

        # fetch last 365 days
        await self.hass.async_add_executor_job(
            self._edata.update,
            datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            - relativedelta(months=self._default_cache_months),  # since: 1 year ago
            datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(minutes=1),  # to: yesterday midnight
        )

        await self.update_statistics()

        self._load_data()

        if not self.is_storage_migration_complete:
            await Store(
                self.hass,
                const.STORAGE_VERSION,
                f"{const.STORAGE_KEY_PREAMBLE}_{self.id}",
            ).async_save(utils.serialize_dict(self._edata.data))

            if os.path.isfile(RECENT_QUERIES_FILE):
                with open(
                    RECENT_QUERIES_FILE, encoding="utf8"
                ) as recent_queries_content:
                    recent_queries = json.load(recent_queries_content)
                    await Store(
                        self.hass,
                        const.STORAGE_VERSION,
                        f"{const.STORAGE_KEY_PREAMBLE}_recent_queries",
                    ).async_save(recent_queries)

        return self._data

    def _load_data(self, preprocess=False):
        """Load data found in built-in statistics into state, attributes and websockets."""

        try:
            if preprocess:
                self._edata.process_data()

            # reference to attributes shared storage
            attrs = self._data[const.DATA_ATTRIBUTES]
            attrs.update(self._edata.attributes)

            # load into websockets
            self._data[const.WS_CONSUMPTIONS_DAY] = self._edata.data[
                "consumptions_daily_sum"
            ]
            self._data[const.WS_CONSUMPTIONS_MONTH] = self._edata.data[
                "consumptions_monthly_sum"
            ]
            self._data["ws_maximeter"] = self._edata.data["maximeter"]

            # update state
            with contextlib.suppress(AttributeError):
                self._data["state"] = self._edata.attributes[
                    "last_registered_date"
                ].strftime("%d/%m/%Y")

        except Exception:
            _LOGGER.warning("Some data is missing, will try to fetch later")
            return False

        return True

    async def _update_last_stats_summary(self):
        """Update self._last_stats_sum and self._last_stats_dt."""

        statistic_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        statistic_ids = [
            x["statistic_id"]
            for x in statistic_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
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
                try:
                    last_record_dt[x] = dt_util.parse_datetime(
                        last_stats[x][x][0]["end"]
                    )
                except Exception:
                    last_record_dt[x] = datetime(1970, 1, 1)
        elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
            for x in statistic_ids:
                try:
                    last_record_dt[x] = dt_util.as_local(last_stats[x][x][0]["end"])
                except Exception:
                    last_record_dt[x] = datetime(1970, 1, 1)
        else:
            for x in statistic_ids:
                try:
                    last_record_dt[x] = dt_util.utc_from_timestamp(
                        last_stats[x][x][0]["end"]
                    )
                except Exception:
                    last_record_dt[x] = datetime(1970, 1, 1)

        # store most recent stat for each statistic_id
        self._last_stats_dt = last_record_dt
        self._last_stats_sum = {
            x: last_stats[x][x][0]["sum"]
            for x in last_stats
            if "sum" in last_stats[x][x][0] and x in last_stats[x]
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
            if x["statistic_id"].startswith(self._stat_id_preamble)
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

        if self.billing_rules:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def _add_statistics(self, new_stats):
        """Add new statistics as a bundle."""

        for stat_id in new_stats:
            if stat_id in self.consumption_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_KWH(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                )
            elif stat_id in self.cost_stat_ids:
                metadata = StatisticMetaData(
                    has_mean=False,
                    has_sum=True,
                    name=const.STAT_TITLE_EUR(self.id, stat_id),
                    source=const.DOMAIN,
                    statistic_id=stat_id,
                    unit_of_measurement=CURRENCY_EURO,
                )
            elif stat_id in self.maximeter_stat_ids:
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

        new_stats = {x: [] for x in self.consumption_stat_ids}

        # init as 0 if need
        for stat_id in self.consumption_stat_ids:
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
            by_tariff_ids.extend([x for x in self.consumption_stat_ids if _p in x])
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
        new_stats = {x: [] for x in self.cost_stat_ids}

        # init as 0 if need
        for stat_id in self.cost_stat_ids:
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
        new_stats = {x: [] for x in self.maximeter_stat_ids}

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
