"""Tests for the edata recorder statistics generation."""

from typing import Any
from unittest.mock import patch

from syrupy.assertion import SnapshotAssertion

from homeassistant.components.recorder.models import StatisticData
from homeassistant.core import HomeAssistant

from custom_components.edata.core.statistics import bill as bill_stats
from custom_components.edata.core.statistics import energy as energy_stats
from custom_components.edata.core.statistics import power as power_stats

from .fixtures import SCUPS, FakeDataManager


async def test_statistics_payloads(
    setup_integration: None,
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
) -> None:
    """Energy, power and bill statistics produce the expected external stats."""
    data_manager = FakeDataManager()
    captured: dict[str, list[float]] = {}

    def _capture(
        _hass: HomeAssistant,
        metadata: dict[str, Any],
        statistics: list[StatisticData],
        _scups: str,
    ) -> None:
        captured[metadata["statistic_id"]] = [s["state"] for s in statistics]

    with (
        patch.object(energy_stats, "add_statistics", side_effect=_capture),
        patch.object(power_stats, "add_statistics", side_effect=_capture),
        patch.object(bill_stats, "add_statistics", side_effect=_capture),
    ):
        await energy_stats.update_energy_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )
        await power_stats.update_power_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )
        await bill_stats.update_bill_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )

    assert captured == snapshot
