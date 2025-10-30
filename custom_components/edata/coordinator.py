"""Data update coordinator definitions."""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
import logging
import math
import os

from dateutil.relativedelta import relativedelta

from edata.const import PROG_NAME as EDATA_PROG_NAME
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CURRENCY_EURO,
    MAJOR_VERSION,
    MINOR_VERSION,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .migrate import migrate_pre2024_storage_if_needed
from .utils import get_db_instance

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
    ) -> None:
        """Initialize the data handler.."""

        # Number of cached months (starting from 1st day of the month will be automatic)
        self.cache_months = const.CACHE_MONTHS_SHORT

        # Store properties
        self.hass = hass
        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.scups = scups.upper()
        self.id = scups.lower()
        self.billing_rules = billing

        # Check if v2023 storage has already been migrated
        migrate_pre2024_storage_if_needed(hass, self.cups, self.id)

        # Init shared data
        hass.data[const.DOMAIN][self.id] = {const.CONF_CUPS: self.cups}

        # Instantiate the api helper
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
        self._data[EDATA_PROG_NAME] = self._edata
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

        self.consumptions_stat_ids = {
            const.STAT_ID_KWH(self.id),
            const.STAT_ID_P1_KWH(self.id),
            const.STAT_ID_P2_KWH(self.id),
            const.STAT_ID_P3_KWH(self.id),
        }

        self.surplus_stat_ids = {
            const.STAT_ID_SURP_KWH(self.id),
        }

        self.energy_stat_ids = self.consumptions_stat_ids.union(self.surplus_stat_ids)

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
        self._corrupt_stats = []

        hass.data[const.DOMAIN][self.id]["dt_last"] = self._last_stats_dt

        # Just the preamble of the statistics
        self._stat_id_preamble = f"{const.DOMAIN}:{self.id}"

        super().__init__(
            hass,
            _LOGGER,
            name=const.COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    @classmethod
    async def async_setup(
        cls,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str,
        billing: PricingRules | None = None,
    ):
        """Async constructor."""

        return await hass.async_add_executor_job(
            cls, hass, username, password, cups, scups, authorized_nif, billing
        )

    async def _async_update_data(self, update_statistics=True):
        """Update data via API."""

        # fetch last 365 days
        await self.hass.async_add_executor_job(
            self._edata.update,
            datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            - relativedelta(months=self.cache_months),  # since N cache_months
            datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(minutes=1),  # to: yesterday midnight
        )

        if update_statistics:
            await self.update_statistics()

        self._load_data()

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

        _LOGGER.debug("%s: checking latest statistics", self.scups)

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
        for x in statistic_ids:
            try:
                if MAJOR_VERSION <= 2022:
                    last_record_dt[x] = dt_util.parse_datetime(
                        last_stats[x][x][0]["end"]
                    )
                elif MAJOR_VERSION == 2023 and MINOR_VERSION < 3:
                    last_record_dt[x] = dt_util.as_local(last_stats[x][x][0]["end"])
                else:
                    last_record_dt[x] = dt_util.utc_from_timestamp(
                        last_stats[x][x][0]["end"]
                    )
            except Exception:
                last_record_dt[x] = dt_util.as_utc(datetime(1970, 1, 1))

        # store most recent stat for each statistic_id
        self._last_stats_dt = last_record_dt
        self._last_stats_sum = {
            x: last_stats[x][x][0]["sum"]
            for x in last_stats
            if x in last_stats[x] and "sum" in last_stats[x][x][0]
        }

    async def check_statistics_integrity(self) -> bool:
        """Check if statistics differ from stored data since a given datetime."""

        _LOGGER.warning("Running statistics integrity check")
        self._corrupt_stats = []

        # recalculate all data
        await self.hass.async_add_executor_job(self._edata.process_data, False)

        # give from_dt a proper default value
        from_dt = dt_util.as_utc(
            self._edata.data["consumptions_daily_sum"][0]["datetime"]
        )

        _LOGGER.debug(
            "%s: performing integrity check since %s",
            self.scups,
            dt_util.as_local(from_dt),
        )
        # get all statistic_ids starting with edata:<id/scups>
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_check = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
        ]

        if len(to_check) == 0:
            _LOGGER.warning(
                "%s: no statistics found",
                self.scups,
            )
            return False

        data = await get_db_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            from_dt,
            dt_util.as_utc(datetime.now()),
            set(to_check),
            "hour",
            None,
            {"change", "state"},
        )

        # Checksums
        _consumptions_checksum = 0
        _consumptions_tariff_checksum = [0, 0, 0]
        _surplus_checksum = 0

        for c in self._edata.data["consumptions_daily_sum"]:
            _consumptions_checksum += c["value_kWh"]
            _consumptions_tariff_checksum[0] += c["value_p1_kWh"]
            _consumptions_tariff_checksum[1] += c["value_p2_kWh"]
            _consumptions_tariff_checksum[2] += c["value_p3_kWh"]
            _surplus_checksum += c["surplus_kWh"]

        for test_tuple in (
            (_consumptions_checksum, const.STAT_ID_KWH(self.id)),
            (_consumptions_tariff_checksum[0], const.STAT_ID_P1_KWH(self.id)),
            (_consumptions_tariff_checksum[1], const.STAT_ID_P2_KWH(self.id)),
            (_consumptions_tariff_checksum[2], const.STAT_ID_P3_KWH(self.id)),
            (_surplus_checksum, const.STAT_ID_SURP_KWH(self.id)),
        ):
            _stats_sum = 0
            if (stats := data.get(test_tuple[1], None)) is not None:
                _LOGGER.debug(
                    "First evaluated sample of %s is %s",
                    test_tuple[1],
                    dt_util.as_local(dt_util.utc_from_timestamp(stats[0]["start"])),
                )
                for c in stats:
                    _stats_sum += c["change"]
                    if c["change"] < 0:
                        _LOGGER.warning(
                            "%s: negative change found at '%s'",
                            self.scups,
                            test_tuple[1],
                        )
            else:
                _LOGGER.warning(
                    "%s: '%s' statistic not found", self.scups, test_tuple[1]
                )

            if not math.isclose(test_tuple[0], _stats_sum, abs_tol=1):  # +-1kWh
                _LOGGER.warning(
                    "%s: '%s' statistic is corrupt, its checksum is %s, got %s",
                    self.scups,
                    test_tuple[1],
                    test_tuple[0],
                    _stats_sum,
                )
                self._corrupt_stats.append(test_tuple[1])

        _LOGGER.warning(
            "%s: %s corrupt statistics", self.scups, len(self._corrupt_stats)
        )
        return len(self._corrupt_stats) == 0

    async def rebuild_statistics(
        self, from_dt: datetime | None = None, include_only: list[str] | None = None
    ):
        """Rebuild edata statistics since a given datetime. Defaults to last year."""

        _LOGGER.debug("%s: rebuilding statistics", self.scups)

        # recalculate all data
        await self.hass.async_add_executor_job(self._edata.process_data, False)

        # get all statistic_ids starting with edata:<id/scups>
        all_ids = await get_db_instance(self.hass).async_add_executor_job(
            list_statistic_ids, self.hass
        )
        to_clear = [
            x["statistic_id"]
            for x in all_ids
            if x["statistic_id"].startswith(self._stat_id_preamble)
        ]

        # give from_dt a proper default value
        if from_dt is None:
            from_dt = dt_util.as_utc(
                self._edata.data["consumptions_monthly_sum"][0]["datetime"]
            )
            # if from_dt is none, only corrupt stats get a reset
            to_clear = [x for x in to_clear if x in self._corrupt_stats]

        if len(to_clear) == 0:
            _LOGGER.warning("%s: there are no corrupt statistics", to_clear)
            return

        if include_only is not None:
            to_clear = [x for x in include_only if x in to_clear]

        # retrieve stored statistics along with its metadata
        old_metadata = await get_db_instance(self.hass).async_add_executor_job(
            get_metadata, self.hass
        )

        old_data = await get_db_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.as_utc(datetime(1970, 1, 1)),
            from_dt,
            set(to_clear),
            "hour",
            None,
            {"state", "sum", "mean", "max"},
        )

        # wipe all-time statistics (since it is the only method provided by home assistant)
        _LOGGER.warning(
            "Clearing statistics for %s",
            to_clear,
        )
        get_db_instance(self.hass).async_clear_statistics(to_clear)

        # now restore old statistics
        for stat_id in old_data:
            if stat_id not in to_clear:
                continue

            self._last_stats_dt[stat_id] = dt_util.utc_from_timestamp(
                old_data[stat_id][-1]["start"]
            )
            self._last_stats_sum[stat_id] = old_data[stat_id][-1]["sum"]

            _LOGGER.warning("Restoring statistic id '%s'", stat_id)
            get_db_instance(self.hass).async_import_statistics(
                old_metadata[stat_id][1],
                [
                    StatisticData(
                        start=dt_util.utc_from_timestamp(x["start"]),
                        state=x["state"],
                        sum=x.get("sum", None),
                        mean=x.get("mean", None),
                        max=x.get("max", None),
                    )
                    for x in old_data[stat_id]
                ],
                Statistics,
            )

        self._corrupt_stats = []

        await self._update_consumption_stats()
        if self.billing_rules:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def update_statistics(self):
        """Update Long Term Statistics with newly found data."""

        _LOGGER.debug("%s: synchronizing statistics", self.scups)

        # first fetch from db last statistics for current id
        await self._update_last_stats_summary()

        for stat_id in self._last_stats_dt:
            _LOGGER.debug(
                "%s: '%s' most recent data is at %s",
                self.scups,
                stat_id,
                self._last_stats_dt[stat_id],
            )

        await self._update_consumption_stats()
        await self._update_maximeter_stats()

        if self.billing_rules:
            # costs are only processed if billing functionality is enabled
            await self._update_cost_stats()

    async def _add_statistics(self, new_stats):
        """Add new statistics as a bundle."""

        for stat_id in new_stats:
            if len(new_stats[stat_id]) > 0:
                _LOGGER.debug(
                    "%s: inserting %s new values for statistic '%s'",
                    self.scups,
                    len(new_stats[stat_id]),
                    stat_id,
                )
            else:
                continue

            if stat_id in self.energy_stat_ids:
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

        new_stats = {x: [] for x in self.energy_stat_ids}

        # init as 0 if need
        for stat_id in self.energy_stat_ids:
            if stat_id not in self._last_stats_sum:
                self._last_stats_sum[stat_id] = 0

        _label = "value_kWh"
        for data in self._edata.data.get("consumptions", []):
            dt_found = dt_util.as_local(data["datetime"])
            _p = utils.get_pvpc_tariff(data["datetime"])
            by_tariff_ids = [
                const.STAT_ID_KWH(self.id),
                const.STAT_ID_SURP_KWH(self.id),
            ]
            by_tariff_ids.extend([x for x in self.energy_stat_ids if _p in x])
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

        _costs_data = self._edata.data.get("cost_hourly_sum", [])
        if len(_costs_data) == 0:
            # return empty stats since billing is apparently not enabled
            return

        for data in _costs_data:
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

    def soft_wipe(self):
        """Apply a soft wipe."""

        edata_dir = os.path.join(self.hass.config.path(STORAGE_DIR), EDATA_PROG_NAME)
        edata_file = os.path.join(edata_dir, f"edata_{self.cups.lower()}.json")
        edata_backup_file = edata_file + ".bck"

        _LOGGER.warning("%s, soft wipe requested, preparing a backup", self.scups)
        if os.path.exists(edata_file):
            _LOGGER.warning(
                "%s: backup file is '%s', rename it back to '%s' to restore it",
                self.scups,
                edata_backup_file,
                edata_file,
            )
            os.rename(edata_file, edata_backup_file)

        _LOGGER.debug("%s: deleting mem cache", self.scups)
        self._edata.reset()

    async def async_soft_reset(self):
        """Apply an async full reset."""

        await self.hass.async_add_executor_job(self.soft_wipe)
        await self._async_update_data(update_statistics=False)
        if not await self.check_statistics_integrity():
            await self.rebuild_statistics()
        else:
            _LOGGER.warning("%s: statistics recreation is not needed", self.scups)

    async def async_full_import(self):
        """Apply an async full fetch."""

        _LOGGER.warning("Importing last two years of data from Datadis")
        self.set_long_cache()
        await self._async_update_data(update_statistics=False)
        self._edata.process_data()
        # check if consumptions statistics are wrong
        if not await self.check_statistics_integrity():
            await self.rebuild_statistics()
        else:
            _LOGGER.warning("%s: statistics recreation is not needed", self.scups)

        self.set_short_cache()
        _LOGGER.debug(
            "%s: reducing cache items to last %s months", self.scups, self.cache_months
        )
        await self._async_update_data(update_statistics=False)

    def set_long_cache(self):
        """Set the number of cached monts to a long value (two years)."""

        self.cache_months = const.CACHE_MONTHS_LONG

    def set_short_cache(self):
        """Set the number of cached monts to a short value (a year)."""

        self.cache_months = const.CACHE_MONTHS_SHORT

    async def update_billing(self, options: dict, since: datetime | None = None):
        """Update billing rules and recalculate."""

        _LOGGER.info("%s: updating costs since %s", self.scups, since.isoformat())
        billing_enabled = options.get(const.CONF_BILLING, False)

        if billing_enabled:
            pricing_rules = {
                const.PRICE_ELECTRICITY_TAX: const.DEFAULT_PRICE_ELECTRICITY_TAX,
                const.PRICE_IVA_TAX: const.DEFAULT_PRICE_IVA,
            }
            pricing_rules.update(
                {
                    x: options[x]
                    for x in options
                    if x
                    in (
                        const.CONF_CYCLE_START_DAY,
                        const.PRICE_P1_KW_YEAR,
                        const.PRICE_P2_KW_YEAR,
                        const.PRICE_P1_KWH,
                        const.PRICE_P2_KWH,
                        const.PRICE_P3_KWH,
                        const.PRICE_METER_MONTH,
                        const.PRICE_MARKET_KW_YEAR,
                        const.PRICE_ELECTRICITY_TAX,
                        const.PRICE_IVA_TAX,
                        const.BILLING_ENERGY_FORMULA,
                        const.BILLING_POWER_FORMULA,
                        const.BILLING_OTHERS_FORMULA,
                        const.BILLING_SURPLUS_FORMULA,
                    )
                }
            )
        else:
            pricing_rules = None

        self._edata.pricing_rules = pricing_rules
        self._edata.is_pvpc = options[const.CONF_PVPC]
        self._edata.enable_billing = options[const.CONF_BILLING]

        for key in self._edata.data:
            if not key.startswith("cost"):
                continue
            if since is not None:
                self._edata.data[key] = [
                    x
                    for x in self._edata.data[key]
                    if dt_util.as_local(x["datetime"]) < since
                ]
            else:
                self._edata.data[key] = []

        self._edata.process_cost()

        await self.rebuild_statistics(since, self.cost_stat_ids)
