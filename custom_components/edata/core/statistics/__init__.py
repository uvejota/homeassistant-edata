"""Statistics management for edata integration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ..data import DataManager
from .bill import update_bill_statistics
from .energy import update_energy_statistics
from .power import update_power_statistics
from .utils import clear_statistics, get_integration_stat_ids

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "clear_statistics",
    "get_integration_stat_ids",
    "update_all_statistics",
]


async def update_all_statistics(
    hass: HomeAssistant,
    service: DataManager,
    integration_id: str,
    scups: str,
) -> None:
    """Update all statistics for the integration."""

    try:
        await update_energy_statistics(hass, service, integration_id, scups)
    except Exception:
        _LOGGER.exception("%s: failed to update energy statistics", scups)

    try:
        await update_power_statistics(hass, service, integration_id, scups)
    except Exception:
        _LOGGER.exception("%s: failed to update power statistics", scups)

    try:
        await update_bill_statistics(hass, service, integration_id, scups)
    except Exception:
        _LOGGER.exception("%s: failed to update bill statistics", scups)

    _LOGGER.info("%s: finished updating all statistics", scups)
