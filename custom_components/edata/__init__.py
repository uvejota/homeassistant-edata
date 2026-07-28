"""Home Assistant e-data integration."""

from __future__ import annotations

from datetime import datetime, time
import logging
from pathlib import Path

from edata.models.bill import BillingRules, PVPCBillingRules
from pydantic import ValidationError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from . import const
from .coordinator import EdataCoordinator
from .core.config import (
    CONF_AUTHORIZED_NIF,
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from .core.data import DataManager
from .core.lovelace import init_resource, register_static_path
from .core.options import CONF_BILLING, CONF_DEBUG, CONF_PVPC, CONF_UPDATE_SINCE
from .core.utils import get_shared_memory
from .websockets import async_register_websockets

PLATFORMS: list[str] = ["button", "sensor"]
_LOGGER = logging.getLogger(__name__)


def _build_billing_rules(options: dict) -> BillingRules | None:
    """Build billing rules from the config entry options."""

    if not options.get(CONF_BILLING, False):
        return None
    rules_model = PVPCBillingRules if options.get(CONF_PVPC, False) else BillingRules
    try:
        return rules_model(**dict(options))
    except ValidationError:
        _LOGGER.warning(
            "Ignoring invalid billing options; please reconfigure billing"
        )
        return None


def _apply_debug_level(options: dict) -> None:
    """Set the edata logger level according to the debug option."""

    if options.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)
    else:
        logging.getLogger("edata").setLevel(logging.WARNING)


def _remove_legacy_file(path: Path) -> None:
    """Delete the imported 1.x JSON cache file (best effort)."""
    path.unlink(missing_ok=True)


async def _migrate_legacy_storage(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Import the 1.x JSON cache into the 2.0 database, then remove it.

    Best effort: a failure is logged and the entry is still migrated, since 2.0
    can rebuild the database from Datadis.
    """

    cups = entry.data[CONF_CUPS]
    scups = entry.data[CONF_SCUPS]
    manager = DataManager(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        cups,
        scups,
        entry.data.get(CONF_AUTHORIZED_NIF),
    )
    try:
        results = await manager.run_migrations()
    except Exception:
        _LOGGER.exception(
            "%s: legacy storage migration failed; 2.0 will rebuild from Datadis",
            scups,
        )
        return

    if not results:
        return

    _LOGGER.info("%s: imported legacy 1.x storage (%s)", scups, results)
    # 1.x wrote .storage/edata/edata_{cups}.json (full CUPS, lower-cased).
    legacy_file = (
        Path(hass.config.path(STORAGE_DIR)) / "edata" / f"edata_{cups.lower()}.json"
    )
    await hass.async_add_executor_job(_remove_legacy_file, legacy_file)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry to the current version."""

    if entry.version < 2:
        # 2.0 stores data in .storage/edata.db; import the orphaned 1.x JSON cache
        # from .storage/edata/ so history (incl. data older than Datadis's window)
        # is preserved, then bump the entry version.
        await _migrate_legacy_storage(hass, entry)
        hass.config_entries.async_update_entry(entry, version=2)

    return True


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

    _apply_debug_level(entry.options)
    billing_rules = _build_billing_rules(entry.options)

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
    """Handle options update by re-applying billing rules."""

    scups = entry.data[CONF_SCUPS]
    _LOGGER.debug("%s: options changed", scups)

    _apply_debug_level(entry.options)

    coordinator: EdataCoordinator | None = get_shared_memory(hass, scups).get(
        "coordinator"
    )
    if coordinator is None:
        return

    since: datetime | None = None
    if raw_since := entry.options.get(CONF_UPDATE_SINCE):
        if parsed := dt_util.parse_date(raw_since):
            since = datetime.combine(parsed, time.min)

    await coordinator.update_billing(_build_billing_rules(entry.options), since)
