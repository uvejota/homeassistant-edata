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
from ..utils import async_get_tariff, iter_month_windows
from .utils import (
    add_statistics,
    calculate_cumulative_sum,
    get_last_stat,
    make_stat_id,
    resolve_load_window,
    should_add_statistic,
)

_LOGGER = logging.getLogger(__name__)


async def update_energy_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
) -> None:
    """Update energy consumption and surplus statistics one month at a time."""
    _LOGGER.debug("%s: updating energy statistics", scups)

    # Define stat IDs
    stat_ids = {
        "consumption": make_stat_id(DOMAIN, integration_id, "consumption"),
        "consumption_p1": make_stat_id(DOMAIN, integration_id, "p1_consumption"),
        "consumption_p2": make_stat_id(DOMAIN, integration_id, "p2_consumption"),
        "consumption_p3": make_stat_id(DOMAIN, integration_id, "p3_consumption"),
        "surplus": make_stat_id(DOMAIN, integration_id, "surplus"),
    }

    # Get last recorded (datetime, cumulative sum) per statistic
    last_stats = {
        key: await get_last_stat(hass, stat_id) for key, stat_id in stat_ids.items()
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
        data = await service.get_energy(start=win_start, end=win_end)
        if not data:
            continue

        batch: dict[str, list[StatisticData]] = {key: [] for key in stat_ids}

        for energy_point in data:
            dt_found = dt_util.as_local(energy_point.datetime)
            tariff = await async_get_tariff(energy_point.datetime)

            if energy_point.consumption_kwh is not None:
                if should_add_statistic(last_stats["consumption"][0], dt_found):
                    batch["consumption"].append(
                        StatisticData(start=dt_found, state=energy_point.consumption_kwh)
                    )

                tariff_key = f"consumption_p{tariff}"
                if tariff_key in batch and should_add_statistic(
                    last_stats[tariff_key][0], dt_found
                ):
                    batch[tariff_key].append(
                        StatisticData(start=dt_found, state=energy_point.consumption_kwh)
                    )

            if energy_point.surplus_kwh is not None:
                if should_add_statistic(last_stats["surplus"][0], dt_found):
                    batch["surplus"].append(
                        StatisticData(start=dt_found, state=energy_point.surplus_kwh)
                    )

        for key, stat_id in stat_ids.items():
            if not batch[key]:
                continue

            calculate_cumulative_sum(batch[key], initial_sum=running_sum[key])
            running_sum[key] = batch[key][-1]["sum"]
            add_statistics(hass, _create_energy_metadata(stat_id), batch[key], scups)
            added += len(batch[key])

    _LOGGER.debug("%s: added %d energy statistics", scups, added)


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
