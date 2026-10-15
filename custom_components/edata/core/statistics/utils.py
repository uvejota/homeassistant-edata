"""Shared utilities for statistics management."""

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder import util as recorder_util
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    list_statistic_ids,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def make_stat_id(domain: str, integration_id: str, suffix: str) -> str:
    """Create a statistic ID."""
    return f"{domain}:{integration_id}_{suffix}"


async def get_last_stat(
    hass: HomeAssistant,
    stat_id: str,
) -> tuple[datetime, float]:
    """Return the (start datetime, cumulative sum) of the last recorded value.

    Reads the period ``start`` -- present for every statistic type -- instead of
    ``max``, which is ``None`` for sum/NONE-mean statistics and previously made
    this always report 1970, defeating incremental updates so the whole history
    was recompiled and re-imported on every sync.
    """
    recorder = recorder_util.get_instance(hass)
    last_stats = await recorder.async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        stat_id,
        True,
        {"sum"},
    )

    rows = last_stats.get(stat_id)
    if not rows:
        return dt_util.as_utc(datetime(1970, 1, 1)), 0.0

    row = rows[0]
    start = row.get("start")
    last_dt = (
        dt_util.utc_from_timestamp(start)
        if start is not None
        else dt_util.as_utc(datetime(1970, 1, 1))
    )
    return last_dt, row.get("sum") or 0.0


async def get_stat_before(
    hass: HomeAssistant,
    stat_id: str,
    before: datetime,
) -> tuple[datetime, float]:
    """Return the (start datetime, cumulative sum) of the last value before a time.

    Looks back a month first and then over the whole history, so a gap in the
    data does not restart the sum from 0.
    """
    recorder = recorder_util.get_instance(hass)
    epoch = dt_util.as_utc(datetime(1970, 1, 1))
    for start in (before - timedelta(days=31), epoch):
        stats = await recorder.async_add_executor_job(
            statistics_during_period,
            hass,
            start,
            before,
            {stat_id},
            "hour",
            None,
            {"sum"},
        )
        if rows := stats.get(stat_id):
            row = rows[-1]
            return dt_util.utc_from_timestamp(row["start"]), row.get("sum") or 0.0
    return epoch, 0.0


async def get_last_stat_datetime(
    hass: HomeAssistant,
    stat_id: str,
) -> datetime:
    """Get the last recorded datetime for a statistic."""
    last_dt, _ = await get_last_stat(hass, stat_id)
    return last_dt


def should_add_statistic(
    last_stat_dt: datetime,
    new_dt: datetime,
) -> bool:
    """Return True if new_dt is strictly newer than the last recorded value."""
    return new_dt > last_stat_dt


def resolve_load_window(
    earliest_stat_dt: datetime,
    data_start: datetime | None,
) -> tuple[datetime, datetime]:
    """Return naive-local ``(start, end)`` bounds for a windowed statistics load.

    Stored energy/bill datetimes are naive-local while statistic starts are UTC.
    The window begins one day before the earliest already-recorded statistic --
    a margin that absorbs that skew so no boundary row is ever missed;
    ``should_add_statistic`` still guards the seam against re-adding rows -- and
    is clamped to when data actually begins so a first run does not iterate
    decades of empty months.
    """
    start = dt_util.as_local(earliest_stat_dt).replace(tzinfo=None) - timedelta(days=1)
    if data_start is not None:
        start = max(start, data_start)
    end = dt_util.now().replace(tzinfo=None) + timedelta(days=1)
    return start, end


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


async def clear_statistics(
    hass: HomeAssistant, stat_ids: list[str], scups: str
) -> None:
    """Clear statistics from Home Assistant recorder and wait until it is done."""
    if not stat_ids:
        _LOGGER.info("%s: no statistics to clear", scups)
        return

    _LOGGER.warning(
        "%s: clearing %d Home Assistant statistics: %s",
        scups,
        len(stat_ids),
        stat_ids,
    )
    # the recorder clears them later on, in its own thread: a rebuild right
    # away would still see the old statistics, add nothing, and then they
    # would be cleared. Wait until it is actually done.
    done = hass.loop.create_future()

    def _on_done() -> None:
        hass.loop.call_soon_threadsafe(done.set_result, None)

    recorder_util.get_instance(hass).async_clear_statistics(stat_ids, on_done=_on_done)
    await done
