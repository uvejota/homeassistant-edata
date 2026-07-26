"""Tests for the edata recorder statistics generation."""

from typing import Any
from unittest.mock import patch

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.util import get_instance
from homeassistant.core import HomeAssistant

from custom_components.edata.const import DOMAIN
from custom_components.edata.core.statistics import bill as bill_stats
from custom_components.edata.core.statistics import energy as energy_stats
from custom_components.edata.core.statistics import power as power_stats
from custom_components.edata.core.statistics.utils import get_last_stat, make_stat_id

from .fixtures import SCUPS, FakeDataManager, build_energy


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


async def test_energy_statistics_are_incremental(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """A later sync imports only new rows and continues the cumulative sum.

    Guards the get_last_stat fix: it previously read ``max`` (None for these
    stats), always reported 1970 and re-imported the whole history every sync.
    """
    data_manager = FakeDataManager()
    data_manager._energy = build_energy(48)
    stat_id = make_stat_id(DOMAIN, SCUPS, "consumption")

    # First sync writes to the real recorder.
    await energy_stats.update_energy_statistics(hass, data_manager, SCUPS, SCUPS.upper())
    await get_instance(hass).async_block_till_done()
    await hass.async_block_till_done()

    _, sum_after_first = await get_last_stat(hass, stat_id)
    assert sum_after_first == pytest.approx(
        sum(e.consumption_kwh for e in build_energy(48)), abs=1e-6
    )

    # Grow the history; capture exactly what the second sync would import.
    data_manager._energy = build_energy(72)
    captured: dict[str, list[StatisticData]] = {}

    def _capture(
        _hass: HomeAssistant,
        metadata: dict[str, Any],
        statistics: list[StatisticData],
        _scups: str,
    ) -> None:
        captured[metadata["statistic_id"]] = statistics

    with patch.object(energy_stats, "add_statistics", side_effect=_capture):
        await energy_stats.update_energy_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )

    new_rows = captured[stat_id]
    # Only the 24 new hours are imported, not the whole 72-hour history.
    assert len(new_rows) == 24
    # The cumulative sum continues from the stored value (no reset).
    first_new_state = build_energy(72)[48].consumption_kwh
    assert new_rows[0]["sum"] == pytest.approx(sum_after_first + first_new_state, abs=1e-6)
    assert new_rows[-1]["sum"] == pytest.approx(
        sum(e.consumption_kwh for e in build_energy(72)), abs=1e-6
    )
