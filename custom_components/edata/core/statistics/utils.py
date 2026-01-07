"""Shared utilities for statistics management."""

from datetime import datetime
import logging

from homeassistant.components.recorder import util as recorder_util
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    list_statistic_ids,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def make_stat_id(domain: str, integration_id: str, suffix: str) -> str:
    """Create a statistic ID."""
    return f"{domain}:{integration_id}_{suffix}"


async def get_last_stat_datetime(
    hass: HomeAssistant,
    stat_id: str,
) -> datetime:
    """Get the last recorded datetime for a statistic."""
    recorder = recorder_util.get_instance(hass)
    last_stats = await recorder.async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        stat_id,
        True,
        {"max"},
    )

    if not last_stats.get(stat_id):
        return dt_util.as_utc(datetime(1970, 1, 1))

    if _max := last_stats[stat_id][0].get("max"):
        return dt_util.utc_from_timestamp(_max)

    return dt_util.as_utc(datetime(1970, 1, 1))


def should_add_statistic(
    last_stat_dt: datetime,
    new_dt: datetime,
) -> bool:
    """Check if a new statistic should be added."""
    return new_dt >= last_stat_dt


def add_statistics(
    hass: HomeAssistant,
    metadata: StatisticMetaData,
    statistics: list[StatisticData],
    scups: str,
) -> None:
    """Add statistics to Home Assistant recorder."""
    if not statistics:
        return

    _LOGGER.debug(
        "%s: adding %d values for statistic '%s'",
        scups,
        len(statistics),
        metadata["statistic_id"],
    )

    try:
        async_add_external_statistics(hass, metadata, statistics)
    except (ValueError, KeyError) as err:
        _LOGGER.error(
            "%s: failed to add statistics for '%s': %s",
            scups,
            metadata["statistic_id"],
            err,
        )


def calculate_cumulative_sum(
    statistics: list[StatisticData],
    initial_sum: float = 0.0,
) -> list[StatisticData]:
    """Calculate cumulative sum for statistics."""
    cumulative = initial_sum
    for stat in statistics:
        cumulative += stat.get("state", 0.0)
        stat["sum"] = cumulative
    return statistics


async def get_integration_stat_ids(
    hass: HomeAssistant,
    domain: str,
    integration_id: str,
) -> list[str]:
    """Get all statistic IDs for this integration from recorder."""
    preamble = f"{domain}:{integration_id}"
    recorder = recorder_util.get_instance(hass)
    all_ids = await recorder.async_add_executor_job(list_statistic_ids, hass)
    return [
        x["statistic_id"] for x in all_ids if x["statistic_id"].startswith(preamble)
    ]


def clear_statistics(hass: HomeAssistant, stat_ids: list[str], scups: str) -> None:
    """Clear statistics from Home Assistant recorder."""
    if not stat_ids:
        _LOGGER.info("%s: no statistics to clear", scups)
        return

    _LOGGER.warning(
        "%s: clearing %d Home Assistant statistics: %s",
        scups,
        len(stat_ids),
        stat_ids,
    )
    recorder = recorder_util.get_instance(hass)
    recorder.async_clear_statistics(stat_ids)
