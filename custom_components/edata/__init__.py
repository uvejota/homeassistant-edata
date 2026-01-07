"""Home Assistant e-data integration."""

from __future__ import annotations

import logging
from pathlib import Path

from edata.models.bill import BillingRules, PVPCBillingRules

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.typing import ConfigType

from . import const
from .coordinator import EdataCoordinator
from .core.config import (
    CONF_AUTHORIZED_NIF,
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from .core.lovelace import init_resource, register_static_path
from .core.options import CONF_BILLING, CONF_DEBUG, CONF_PVPC
from .core.utils import get_shared_memory
from .websockets import async_register_websockets

PLATFORMS: list[str] = ["button", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up edata-card resources."""

    path = Path(__file__).parent / "www"
    name = "edata-card.js"
    register_static_path(hass.http.app, "/edata/" + name, path / name)
    version = getattr(hass.data["integrations"][const.DOMAIN], "version", 0)
    await init_resource(hass, "/edata/edata-card.js", str(version))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up edata from a config entry."""
    _LOGGER.debug("Setting up platform 'edata'")

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    entry.async_on_unload(unsub_options_update_listener)

    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    is_pvpc = entry.options.get(CONF_PVPC, False)
    is_billing = entry.options.get(CONF_BILLING, False)

    if entry.options.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)
        # _LOGGER.setLevel(logging.DEBUG)
    else:
        logging.getLogger("edata").setLevel(logging.WARNING)

    billing_rules = None
    if is_billing and is_pvpc:
        billing_rules = PVPCBillingRules(**entry.options.copy())
    elif is_billing:
        billing_rules = BillingRules(**entry.options.copy())

    coordinator = EdataCoordinator(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_CUPS],
        entry.data[CONF_SCUPS],
        entry.data.get(CONF_AUTHORIZED_NIF),
        billing_rules,
    )
    shared = get_shared_memory(hass, entry.data[CONF_SCUPS])
    shared["coordinator"] = coordinator

    # postpone first refresh to speed up startup
    async def async_first_refresh(*args):
        """Force the component to assess the first refresh."""
        hass.async_create_task(coordinator.async_refresh())

    if hass.state == CoreState.running:
        await async_first_refresh()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, async_first_refresh)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # register websockets
    async_register_websockets(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(const.DOMAIN, {}).pop(entry.data.get("scups"), None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry) -> None:
    """Handle removal of an entry."""

    hass.data.get(const.DOMAIN, {}).pop(entry.data.get("scups"), None)


async def options_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""

    scups = entry.data[CONF_SCUPS]
    _LOGGER.debug("%s: options changed", scups)
    # TODO reload entry
    """
    data = hass.data[const.DOMAIN][scups.lower()]
    coor: EdataCoordinator = data["coordinator"]

    # Convertir MappingProxyType a dict regular
    options_dict = dict(entry.options)

    # Parsear fecha si existe
    since = None
    if "update_billing_since" in options_dict:
        parsed_dt = dt_util.parse_datetime(options_dict["update_billing_since"])
        if parsed_dt:
            since = dt_util.as_local(parsed_dt)

    await coor.update_billing(options_dict, since)
    """
