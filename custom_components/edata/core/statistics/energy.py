"""Energy statistics (consumption and surplus)."""

from __future__ import annotations

import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfEnergy
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


async def update_energy_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
) -> None:
    """Update energy consumption and surplus statistics."""
    _LOGGER.debug("%s: updating energy statistics", scups)

    # Fetch data
    data = await service.get_energy()
    if not data:
        _LOGGER.debug("%s: no energy data available", scups)
        return

    # Define stat IDs
    stat_ids = {
        "consumption": make_stat_id(DOMAIN, integration_id, "consumption"),
        "consumption_p1": make_stat_id(DOMAIN, integration_id, "p1_consumption"),
        "consumption_p2": make_stat_id(DOMAIN, integration_id, "p2_consumption"),
        "consumption_p3": make_stat_id(DOMAIN, integration_id, "p3_consumption"),
        "surplus": make_stat_id(DOMAIN, integration_id, "surplus"),
    }

    # Get last recorded (datetime, cumulative sum) per statistic
    last_stats = {}
    for key, stat_id in stat_ids.items():
        last_stats[key] = await get_last_stat(hass, stat_id)

    # Build statistics
    stats_data = {key: [] for key in stat_ids}

    for energy_point in data:
        dt_found = dt_util.as_local(energy_point.datetime)
        tariff = await async_get_tariff(energy_point.datetime)

        # Add consumption
        if energy_point.consumption_kwh is not None:
            # Total consumption
            if should_add_statistic(last_stats["consumption"][0], dt_found):
                stats_data["consumption"].append(
                    StatisticData(start=dt_found, state=energy_point.consumption_kwh)
                )

            # Tariff-specific consumption
            tariff_key = f"consumption_p{tariff}"
            if tariff_key in stats_data and should_add_statistic(
                last_stats[tariff_key][0], dt_found
            ):
                stats_data[tariff_key].append(
                    StatisticData(start=dt_found, state=energy_point.consumption_kwh)
                )

        # Add surplus
        if energy_point.surplus_kwh is not None:
            if should_add_statistic(last_stats["surplus"][0], dt_found):
                stats_data["surplus"].append(
                    StatisticData(start=dt_found, state=energy_point.surplus_kwh)
                )

    # Calculate cumulative sums (continuing from the last stored sum) and record
    for key, stat_id in stat_ids.items():
        if not stats_data[key]:
            continue

        calculate_cumulative_sum(stats_data[key], initial_sum=last_stats[key][1])
        metadata = _create_energy_metadata(stat_id)
        add_statistics(hass, metadata, stats_data[key], scups)

    _LOGGER.debug(
        "%s: added %d energy statistics",
        scups,
        sum(len(v) for v in stats_data.values()),
    )


def _create_energy_metadata(stat_id: str) -> StatisticMetaData:
    """Create metadata for energy statistic."""
    return StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=stat_id,
        source=DOMAIN,
        statistic_id=stat_id,
        unit_class=SensorDeviceClass.ENERGY,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
