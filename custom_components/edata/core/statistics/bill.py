"""Bill/cost statistics."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.const import CURRENCY_EURO
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ..data import DataManager
from ..utils import async_get_tariffs, iter_month_windows
from .utils import (
    add_statistics,
    calculate_cumulative_sum,
    get_last_stat,
    get_stat_before,
    make_stat_id,
    resolve_load_window,
    should_add_statistic,
)

_LOGGER = logging.getLogger(__name__)


async def update_bill_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
    since: datetime | None = None,
) -> None:
    """Update billing/cost statistics one month at a time.

    With ``since`` (naive local time), the statistics from then on are rewritten
    instead of only extended: rows already recorded are overwritten, older ones
    are kept, and the sum carries on from the last value before ``since``.
    """
    _LOGGER.debug("%s: updating bill statistics", scups)

    # Define stat IDs
    stat_ids = {
        "cost": make_stat_id(DOMAIN, integration_id, "cost"),
        "cost_p1": make_stat_id(DOMAIN, integration_id, "p1_cost"),
        "cost_p2": make_stat_id(DOMAIN, integration_id, "p2_cost"),
        "cost_p3": make_stat_id(DOMAIN, integration_id, "p3_cost"),
        "power_cost": make_stat_id(DOMAIN, integration_id, "power_cost"),
        "energy_cost": make_stat_id(DOMAIN, integration_id, "energy_cost"),
        "energy_cost_p1": make_stat_id(DOMAIN, integration_id, "p1_energy_cost"),
        "energy_cost_p2": make_stat_id(DOMAIN, integration_id, "p2_energy_cost"),
        "energy_cost_p3": make_stat_id(DOMAIN, integration_id, "p3_energy_cost"),
    }

    # Get last recorded (datetime, cumulative sum) per statistic
    if since is None:
        last_stats = {
            key: await get_last_stat(hass, stat_id) for key, stat_id in stat_ids.items()
        }
    else:
        since_utc = dt_util.as_utc(
            since.replace(tzinfo=dt_util.get_default_time_zone())
        )
        last_stats = {
            key: await get_stat_before(hass, stat_id, since_utc)
            for key, stat_id in stat_ids.items()
        }

    # Load only from the earliest already-recorded stat onwards, month by month,
    # carrying the cumulative sum across windows so totals stay continuous
    supply = await service.get_supply()
    earliest = min(last_stats[key][0] for key in stat_ids)
    load_start, load_end = resolve_load_window(
        earliest, supply.date_start if supply else None
    )
    running_sum = {key: last_stats[key][1] for key in stat_ids}
    added = 0

    for win_start, win_end in iter_month_windows(load_start, load_end):
        data = await service.get_bills(start=win_start, end=win_end)
        if not data:
            continue

        batch: dict[str, list[StatisticData]] = {key: [] for key in stat_ids}

        tariffs = await async_get_tariffs([x.datetime for x in data])
        for bill, tariff in zip(data, tariffs, strict=True):
            dt_found = dt_util.as_local(bill.datetime)

            if should_add_statistic(last_stats["power_cost"][0], dt_found):
                batch["power_cost"].append(
                    StatisticData(start=dt_found, state=bill.power_term)
                )

            if should_add_statistic(last_stats["energy_cost"][0], dt_found):
                batch["energy_cost"].append(
                    StatisticData(start=dt_found, state=bill.energy_term)
                )

            if should_add_statistic(last_stats["cost"][0], dt_found):
                batch["cost"].append(
                    StatisticData(start=dt_found, state=bill.value_eur)
                )

            if tariff in (1, 2, 3):
                tariff_cost_key = f"cost_p{tariff}"
                tariff_energy_key = f"energy_cost_p{tariff}"

                if should_add_statistic(last_stats[tariff_cost_key][0], dt_found):
                    batch[tariff_cost_key].append(
                        StatisticData(start=dt_found, state=bill.value_eur)
                    )

                if should_add_statistic(last_stats[tariff_energy_key][0], dt_found):
                    batch[tariff_energy_key].append(
                        StatisticData(start=dt_found, state=bill.energy_term)
                    )

        for key, stat_id in stat_ids.items():
            if not batch[key]:
                continue

            calculate_cumulative_sum(batch[key], initial_sum=running_sum[key])
            running_sum[key] = batch[key][-1]["sum"]
            add_statistics(hass, _create_bill_metadata(stat_id), batch[key], scups)
            added += len(batch[key])

    _LOGGER.debug("%s: added %d bill statistics", scups, added)


def _create_bill_metadata(stat_id: str) -> StatisticMetaData:
    """Create metadata for bill/cost statistic."""
    return StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=stat_id,
        source=DOMAIN,
        statistic_id=stat_id,
        unit_class=None,
        unit_of_measurement=CURRENCY_EURO,
    )
