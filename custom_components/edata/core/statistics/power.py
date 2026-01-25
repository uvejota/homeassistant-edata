"""Power statistics (maximeter)."""

from __future__ import annotations

import logging

from edata.core.utils import get_tariff

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ...const import DOMAIN
from ..data import DataManager
from ..utils import async_get_tariff
from .utils import (
    add_statistics,
    get_last_stat_datetime,
    make_stat_id,
    should_add_statistic,
)

_LOGGER = logging.getLogger(__name__)


async def update_power_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
) -> None:
    """Update power (maximeter) statistics."""
    _LOGGER.debug("%s: updating power statistics", scups)

    # Fetch data
    data = await service.get_power()
    if not data:
        _LOGGER.debug("%s: no power data available", scups)
        return

    # Define stat IDs
    stat_ids = {
        "maximeter": make_stat_id(DOMAIN, integration_id, "maximeter"),
        "maximeter_p1": make_stat_id(DOMAIN, integration_id, "p1_maximeter"),
        "maximeter_p2": make_stat_id(DOMAIN, integration_id, "p2_maximeter"),
    }

    # Get last recorded datetimes
    last_stat_dts = {}
    for key, stat_id in stat_ids.items():
        last_stat_dts[key] = await get_last_stat_datetime(hass, stat_id)

    # Build statistics
    stats_data = {key: [] for key in stat_ids}

    for power_point in data:
        dt_found = dt_util.as_local(power_point.datetime)
        tariff = await async_get_tariff(power_point.datetime)

        # General maximeter
        if should_add_statistic(last_stat_dts["maximeter"], dt_found):
            stats_data["maximeter"].append(
                StatisticData(
                    start=dt_found.replace(minute=0),
                    state=power_point.value_kw,
                    max=power_point.value_kw,
                )
            )

        # Tariff-specific maximeter
        tariff_key = f"maximeter_p{tariff}" if tariff in (1, 2) else None
        if tariff_key and tariff_key in stats_data:
            if should_add_statistic(last_stat_dts[tariff_key], dt_found):
                stats_data[tariff_key].append(
                    StatisticData(
                        start=dt_found.replace(minute=0),
                        state=power_point.value_kw,
                        max=power_point.value_kw,
                    )
                )

    # Add to recorder (no cumulative sum for power)
    for key, stat_id in stat_ids.items():
        if not stats_data[key]:
            continue

        metadata = _create_power_metadata(stat_id)
        add_statistics(hass, metadata, stats_data[key], scups)

    _LOGGER.debug(
        "%s: added %d power statistics",
        scups,
        sum(len(v) for v in stats_data.values()),
    )


def _create_power_metadata(stat_id: str) -> StatisticMetaData:
    """Create metadata for power statistic."""
    return StatisticMetaData(
        mean_type=StatisticMeanType.ARITHMETIC,
        has_sum=False,
        name=stat_id,
        source=DOMAIN,
        statistic_id=stat_id,
        unit_class=None,
        unit_of_measurement=UnitOfPower.KILO_WATT,
    )
