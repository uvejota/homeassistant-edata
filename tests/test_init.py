"""Tests for the edata integration setup and options handling."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.edata import _build_billing_rules
from custom_components.edata.const import DOMAIN, SHARED_DATAMANAGER
from custom_components.edata.core.config import (
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from custom_components.edata.core.options import (
    CONF_BILLING,
    CONF_PVPC,
    CONF_UPDATE_SINCE,
)

from .fixtures import CUPS, PASSWORD, SCUPS, USERNAME


async def test_setup_and_unload(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """The integration sets up, populates shared memory, and unloads cleanly."""
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert SHARED_DATAMANAGER in hass.data[DOMAIN][SCUPS]

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_options_update_triggers_billing_recompute(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Updating billing options recomputes costs from the requested date."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][SCUPS]["coordinator"]
    with patch.object(
        coordinator, "update_billing", AsyncMock()
    ) as mock_update_billing:
        hass.config_entries.async_update_entry(
            billing_config_entry,
            options={**billing_config_entry.options, CONF_UPDATE_SINCE: "2023-02-01"},
        )
        await hass.async_block_till_done()

    mock_update_billing.assert_awaited_once()
    _, since = mock_update_billing.await_args.args
    assert since == datetime(2023, 2, 1, 0, 0)


async def test_migrate_v1_entry_bumps_version_and_keeps_legacy_storage(
    setup_integration: None,
    hass: HomeAssistant,
    mock_data_manager: None,
) -> None:
    """A v1 entry is migrated to v2 while the 1.x storage is left in place for now."""
    legacy_dir = Path(hass.config.path(STORAGE_DIR)) / "edata"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_dir / f"edata_{SCUPS}.json"
    legacy_file.write_text("{}", encoding="utf-8")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title=SCUPS,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: CUPS,
            CONF_SCUPS: SCUPS,
        },
        options={},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert legacy_file.exists()


def test_build_billing_rules_guards_invalid_options() -> None:
    """Invalid or disabled billing options degrade to no billing without raising."""
    assert _build_billing_rules({}) is None
    # billing enabled but required price fields absent (e.g. legacy/partial config)
    assert _build_billing_rules({CONF_BILLING: True, CONF_PVPC: False}) is None
