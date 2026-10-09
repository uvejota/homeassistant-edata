"""Tests for the edata websocket API."""

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


@pytest.mark.parametrize("aggr", ["hour", "day", "month"])
async def test_surplus_by_tariff_adds_up_to_total(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    hass_ws_client: WebSocketGenerator,
    aggr: str,
) -> None:
    """Surplus split by tariff (P1, P2, P3) adds up to the total at every point."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    async def fetch(**extra: Any) -> list:
        await client.send_json_auto_id(
            {"type": f"{DOMAIN}/ws/surplus", "scups": SCUPS, "aggr": aggr, **extra}
        )
        response = await client.receive_json()
        assert response["success"]
        return response["result"]

    total = {ts: value for ts, value in await fetch()}
    by_tariff: dict[float, float] = {}
    for tariff in (1, 2, 3):
        for ts, value in await fetch(tariff=tariff):
            by_tariff[ts] = by_tariff.get(ts, 0.0) + value

    assert any(total.values())
    # per-tariff series may carry one extra, older hourly point that the total
    # trims to ``records``; compare over the total's points
    assert by_tariff.keys() >= total.keys()
    for ts, value in total.items():
        assert by_tariff[ts] == pytest.approx(value)


@pytest.mark.parametrize("aggr", ["hour", "day", "month"])
async def test_cost_terms_add_up_to_total(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    hass_ws_client: WebSocketGenerator,
    aggr: str,
) -> None:
    """Cost split by bill term (energy, power, others) adds up to the total."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    async def fetch(**extra: Any) -> list:
        await client.send_json_auto_id(
            {"type": f"{DOMAIN}/ws/costs", "scups": SCUPS, "aggr": aggr, **extra}
        )
        response = await client.receive_json()
        assert response["success"]
        return response["result"]

    total = {ts: value for ts, value in await fetch()}
    by_term: dict[float, float] = {}
    for term in ("energy", "power", "others"):
        for ts, value in await fetch(term=term):
            by_term[ts] = by_term.get(ts, 0.0) + value

    assert any(total.values())
    assert by_term.keys() == total.keys()
    for ts, value in total.items():
        assert by_term[ts] == pytest.approx(value)


async def test_costs_reject_tariff(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Bills carry no per-tariff split, so a tariff filter is rejected."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/ws/costs", "scups": SCUPS, "aggr": "month", "tariff": 1}
    )
    response = await client.receive_json()
    assert not response["success"]
    assert response["error"]["code"] == "invalid_format"
