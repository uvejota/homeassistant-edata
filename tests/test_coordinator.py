"""Tests for the coordinator's Datadis sync throttling."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.edata.const import DOMAIN
from custom_components.edata.coordinator import SYNC_INTERVAL, EdataCoordinator

from .fixtures import SCUPS


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> EdataCoordinator:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][SCUPS]["coordinator"]


async def _refresh(hass: HomeAssistant, coordinator: EdataCoordinator) -> None:
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_sync_skipped_within_interval(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a successful sync, refreshes skip Datadis until the interval passes."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1

    freezer.tick(SYNC_INTERVAL - timedelta(minutes=1))
    await _refresh(hass, coordinator)
    assert manager.synced == 1

    freezer.tick(timedelta(minutes=2))
    await _refresh(hass, coordinator)
    assert manager.synced == 2


async def test_failed_sync_is_retried(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """A sync that did not reach Datadis is retried on the next refresh."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1

    manager.sync_result = False
    coordinator._last_sync = None
    await _refresh(hass, coordinator)
    assert manager.synced == 2
    await _refresh(hass, coordinator)
    assert manager.synced == 3


async def test_last_sync_survives_restart(
    setup_integration: None,
    hass: HomeAssistant,
    hass_storage: dict,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """A recent sync stored before a restart prevents a new one at startup."""
    hass_storage[f"{DOMAIN}.{SCUPS.lower()}.sync"] = {
        "version": 1,
        "key": f"{DOMAIN}.{SCUPS.lower()}.sync",
        "data": {"last_sync": (dt_util.utcnow() - timedelta(hours=1)).isoformat()},
    }

    coordinator = await _setup(hass, config_entry)
    assert coordinator._data_manager.synced == 0


async def test_full_import_always_syncs(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """The manual full import bypasses the interval."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1

    await coordinator.async_full_import()
    assert manager.synced == 2
