"""e-data integration"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PLATFORMS: list[str] = ["sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up edata from a config entry."""

    # hass_data = dict(entry.data)
    # Registers update listener to update config entry when options are updated.
    entry.add_update_listener(options_update_listener)
    # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
    # hass_data["unsub_options_update_listener"] = unsub_options_update_listener
    # hass.data[DOMAIN][entry.entry_id] = hass_data

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.data.get("scups"))

    return unload_ok


async def async_remove_entry(hass, entry) -> None:
    """Handle removal of an entry."""


async def options_update_listener(hass: HomeAssistant, config_entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
