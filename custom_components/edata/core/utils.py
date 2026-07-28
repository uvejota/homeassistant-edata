"""Utility functions for ha_edata."""

import asyncio
from datetime import datetime

from edata.core.utils import get_tariff, iter_month_windows

from homeassistant.core import HomeAssistant

from .. import const

__all__ = [
    "async_get_tariff",
    "get_shared_memory",
    "iter_month_windows",
]


def get_shared_memory(hass: HomeAssistant, scups: str) -> dict:
    """Get shared memory for a given CUPS."""
    return hass.data[const.DOMAIN][scups.lower()]


async def async_get_tariff(dt: datetime) -> int:
    """Get tariff for a given datetime asynchronously."""

    return await asyncio.to_thread(get_tariff, dt)
