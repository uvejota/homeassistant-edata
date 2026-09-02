"""Home Assistant e-data integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import const, utils
from .coordinator import EdataCoordinator
from .websockets import async_register_websockets

PLATFORMS: list[str] = ["button", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up edata-card resources."""

    path = Path(__file__).parent / "www"
    name = "edata-card.js"
    utils.register_static_path(hass.http.app, "/edata/" + name, path / name)
    version = getattr(hass.data["integrations"][const.DOMAIN], "version", 0)
    await utils.init_resource(hass, "/edata/edata-card.js", str(version))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up edata from a config entry."""
    _LOGGER.debug("Setting up platform 'edata'")

    # Registers update listener to update config entry when options are updated.
    unsub_options_update_listener = entry.add_update_listener(options_update_listener)
    entry.async_on_unload(unsub_options_update_listener)

    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    usr = entry.data[CONF_USERNAME]
    pwd = entry.data[CONF_PASSWORD]
    cups = entry.data[const.CONF_CUPS]
    authorized_nif = entry.data.get(const.CONF_AUTHORIZEDNIF, None)
    scups = entry.data[const.CONF_SCUPS]
    billing_enabled = entry.options.get(const.CONF_BILLING, False)

    if entry.options.get(const.CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)
        # _LOGGER.setLevel(logging.DEBUG)
    else:
        logging.getLogger("edata").setLevel(logging.WARNING)

    if billing_enabled:
        pricing_rules = {
            const.PRICE_ELECTRICITY_TAX: const.DEFAULT_PRICE_ELECTRICITY_TAX,
            const.PRICE_IVA_TAX: const.DEFAULT_PRICE_IVA,
        }
        pricing_rules.update(
            {
                x: entry.options[x]
                for x in entry.options
                if x
                in (
                    const.CONF_CYCLE_START_DAY,
                    const.PRICE_P1_KW_YEAR,
                    const.PRICE_P2_KW_YEAR,
                    const.PRICE_P1_KWH,
                    const.PRICE_P2_KWH,
                    const.PRICE_P3_KWH,
                    const.PRICE_METER_MONTH,
                    const.PRICE_MARKET_KW_YEAR,
                    const.PRICE_ELECTRICITY_TAX,
                    const.PRICE_IVA_TAX,
                    const.BILLING_ENERGY_FORMULA,
                    const.BILLING_POWER_FORMULA,
                    const.BILLING_OTHERS_FORMULA,
                    const.BILLING_SURPLUS_FORMULA,
                )
            }
        )
    else:
        pricing_rules = None

    coordinator = await EdataCoordinator.async_setup(
        hass,
        usr,
        pwd,
        cups,
        scups,
        authorized_nif,
        pricing_rules,
        entry.options.get(const.CONF_PVPC, True),
    )
    hass.data[const.DOMAIN][scups.lower()]["coordinator"] = coordinator

    # postpone first refresh to speed up startup
    @callback
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

    scups = entry.data[const.CONF_SCUPS]
    _LOGGER.debug("%s: options changed", scups)
    data = hass.data[const.DOMAIN][scups.lower()]
    coor: EdataCoordinator = data["coordinator"]

    await coor.update_billing(
        entry.options,
        dt_util.as_local(dt_util.parse_datetime(entry.options["update_billing_since"])),
    )
