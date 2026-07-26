"""Bill/cost statistics."""

from __future__ import annotations

import logging

from edata.core.utils import get_tariff

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
from ..utils import async_get_tariff
from .utils import (
    add_statistics,
    calculate_cumulative_sum,
    get_last_stat,
    make_stat_id,
    should_add_statistic,
)

_LOGGER = logging.getLogger(__name__)


async def update_bill_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
) -> None:
    """Update billing/cost statistics."""
    _LOGGER.debug("%s: updating bill statistics", scups)

    # Fetch data
    data = await service.get_bills()
    if not data:
        _LOGGER.debug("%s: no bill data available", scups)
        return

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
    last_stats = {}
    for key, stat_id in stat_ids.items():
        last_stats[key] = await get_last_stat(hass, stat_id)

    # Build statistics
    stats_data = {key: [] for key in stat_ids}

    for bill in data:
        dt_found = dt_util.as_local(bill.datetime)
        tariff = await async_get_tariff(bill.datetime)

        # Power term cost
        if should_add_statistic(last_stats["power_cost"][0], dt_found):
            stats_data["power_cost"].append(
                StatisticData(start=dt_found, state=bill.power_term)
            )

        # Energy term cost
        if should_add_statistic(last_stats["energy_cost"][0], dt_found):
            stats_data["energy_cost"].append(
                StatisticData(start=dt_found, state=bill.energy_term)
            )

        # Total cost
        if should_add_statistic(last_stats["cost"][0], dt_found):
            stats_data["cost"].append(
                StatisticData(start=dt_found, state=bill.value_eur)
            )

        # Tariff-specific costs
        if tariff in (1, 2, 3):
            tariff_cost_key = f"cost_p{tariff}"
            tariff_energy_key = f"energy_cost_p{tariff}"

            if should_add_statistic(last_stats[tariff_cost_key][0], dt_found):
                stats_data[tariff_cost_key].append(
                    StatisticData(start=dt_found, state=bill.value_eur)
                )

            if should_add_statistic(last_stats[tariff_energy_key][0], dt_found):
                stats_data[tariff_energy_key].append(
                    StatisticData(start=dt_found, state=bill.energy_term)
                )

    # Calculate cumulative sums (continuing from the last stored sum) and record
    for key, stat_id in stat_ids.items():
        if not stats_data[key]:
            continue

        calculate_cumulative_sum(stats_data[key], initial_sum=last_stats[key][1])
        metadata = _create_bill_metadata(stat_id)
        add_statistics(hass, metadata, stats_data[key], scups)

    _LOGGER.debug(
        "%s: added %d bill statistics",
        scups,
        sum(len(v) for v in stats_data.values()),
    )


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
