"""Utility functions for ha_edata."""

import asyncio
from datetime import datetime

from edata.core.utils import get_tariff, iter_month_windows

from homeassistant.core import HomeAssistant

from .. import const

__all__ = [
    "async_get_tariffs",
    "get_shared_memory",
    "iter_month_windows",
]


def get_shared_memory(hass: HomeAssistant, scups: str) -> dict:
    """Get shared memory for a given CUPS."""
    return hass.data[const.DOMAIN][scups.lower()]


async def async_get_tariffs(dts: list[datetime]) -> list[int]:
    """Get the tariff of each datetime with a single executor hop.

    get_tariff resolves ES holidays synchronously (blocking imports on the first
    lookup of a year), so it stays off the event loop -- but once per batch, not
    once per row.
    """

    return await asyncio.to_thread(lambda: [get_tariff(dt) for dt in dts])
