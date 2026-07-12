"""Tests for the edata sensors."""

from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant


async def test_sensor_states(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    snapshot: SnapshotAssertion,
) -> None:
    """All edata sensors expose the expected state and attributes after a refresh."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    states = {
        state.entity_id: {
            "state": state.state,
            "attributes": dict(state.attributes),
        }
        for state in hass.states.async_all("sensor")
    }
    assert states == snapshot
