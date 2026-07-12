"""Tests for the edata integration setup and options handling."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.edata.const import DOMAIN, SHARED_DATAMANAGER
from custom_components.edata.core.options import CONF_UPDATE_SINCE

from .fixtures import SCUPS


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
