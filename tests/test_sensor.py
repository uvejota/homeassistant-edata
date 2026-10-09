"""Tests for the edata sensors."""

from datetime import datetime

from pytest_homeassistant_custom_component.common import MockConfigEntry
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.edata.const import DOMAIN

from .fixtures import SCUPS


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


async def test_sensor_attributes_rounded(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Float attributes (and floats inside lists) are shown with two decimals."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    shared = hass.data[DOMAIN][SCUPS.lower()]
    shared["attributes"].update(
        {
            "last_day_consumption_kwh": 1.0,
            "last_day_delta_h": 24.0,
            "last_day_consumption_by_tariff": [0.1 + 0.2, 1.23456, 0.0],
            "last_datetime": datetime(2023, 1, 2, 23, 0),
        }
    )
    shared["coordinator"].async_update_listeners()
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{SCUPS.lower()} last_day_kwh"
    )
    attributes = hass.states.get(entity_id).attributes
    assert attributes["last_day_consumption_by_tariff"] == [0.3, 1.23, 0.0]
    assert attributes["last_day_delta_h"] == 24.0
    assert attributes["last_datetime"] == datetime(2023, 1, 2, 23, 0)
