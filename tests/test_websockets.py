"""Tests for the edata websocket API."""

from collections.abc import Callable
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant

from custom_components.edata.const import DOMAIN

from .fixtures import SCUPS


@pytest.mark.parametrize(
    "message",
    [
        {"type": f"{DOMAIN}/ws/consumptions", "scups": SCUPS, "aggr": "day"},
        {"type": f"{DOMAIN}/ws/consumptions", "scups": SCUPS, "aggr": "hour"},
        {"type": f"{DOMAIN}/ws/surplus", "scups": SCUPS, "aggr": "month"},
        {"type": f"{DOMAIN}/ws/costs", "scups": SCUPS, "aggr": "month"},
        {"type": f"{DOMAIN}/ws/maximeter", "scups": SCUPS},
        {"type": f"{DOMAIN}/ws/summary", "scups": SCUPS},
    ],
    ids=["consumptions_day", "consumptions_hour", "surplus_month", "costs", "maximeter", "summary"],
)
async def test_websocket_commands(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    hass_ws_client: WebSocketGenerator,
    snapshot: SnapshotAssertion,
    message: dict[str, Any],
) -> None:
    """Each websocket command returns the expected shaped payload."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(message)
    response = await client.receive_json()

    assert response["success"]
    assert response["result"] == snapshot
