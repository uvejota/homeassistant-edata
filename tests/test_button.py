"""Tests for the edata buttons."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.edata.const import DOMAIN
from custom_components.edata.coordinator import EdataCoordinator

from .fixtures import SCUPS


@pytest.mark.parametrize(
    ("unique_suffix", "coordinator_method"),
    [
        ("soft_reset", "async_soft_reset"),
        ("import_all_data", "async_full_import"),
    ],
    ids=["soft_reset", "import_all_data"],
)
async def test_button_press(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    unique_suffix: str,
    coordinator_method: str,
) -> None:
    """Pressing each button invokes the matching coordinator action."""
    # Patch on the class before setup so the button captures the mock at creation.
    with patch.object(
        EdataCoordinator, coordinator_method, AsyncMock()
    ) as mock_action:
        config_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        entity_registry = er.async_get(hass)
        entity_id = entity_registry.async_get_entity_id(
            BUTTON_DOMAIN, DOMAIN, f"{SCUPS} {unique_suffix}"
        )
        assert entity_id is not None

        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )

    mock_action.assert_awaited_once()
