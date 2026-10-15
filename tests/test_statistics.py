"""Tests for the edata recorder statistics generation."""

from datetime import datetime
from itertools import accumulate
import time
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.recorder import statistics as recorder_statistics
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.components.recorder.util import get_instance
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.edata.const import DOMAIN
from custom_components.edata.core.statistics import bill as bill_stats
from custom_components.edata.core.statistics import energy as energy_stats
from custom_components.edata.core.statistics import power as power_stats
from custom_components.edata.core.statistics.utils import (
    clear_statistics,
    get_last_stat,
    make_stat_id,
)

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


async def test_energy_statistics_carry_sum_across_month_windows(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """A multi-month build chunks by month yet keeps one continuous cumulative sum.

    Guards the monthly windowing: batches from consecutive windows must not reset
    the sum at the seam, so the concatenated sums equal a single running total.
    """
    hours = 24 * 70  # ~2.3 months -> at least three monthly windows carry data
    data_manager = FakeDataManager()
    data_manager._energy = build_energy(hours)
    stat_id = make_stat_id(DOMAIN, SCUPS, "consumption")

    # Accumulate the per-window batches in call order for the consumption stat.
    rows: list[StatisticData] = []

    def _capture(
        _hass: HomeAssistant,
        metadata: dict[str, Any],
        statistics: list[StatisticData],
        _scups: str,
    ) -> None:
        if metadata["statistic_id"] == stat_id:
            rows.extend(statistics)

    with patch.object(energy_stats, "add_statistics", side_effect=_capture):
        await energy_stats.update_energy_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )

    # Every hour is imported exactly once, in chronological order.
    assert len(rows) == hours
    assert [r["start"] for r in rows] == sorted(r["start"] for r in rows)

    # Sums form a single continuous running total with no per-window reset.
    expected = list(accumulate(r["state"] for r in rows))
    assert [r["sum"] for r in rows] == pytest.approx(expected, abs=1e-6)


async def _cost_rows(hass: HomeAssistant) -> list[tuple[float, float]]:
    """Return the (state, sum) of every recorded total cost row."""
    stat_id = make_stat_id(DOMAIN, SCUPS, "cost")
    recorder = get_instance(hass)
    await async_wait_recording_done(hass)
    stats = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(1970, 1, 1, tzinfo=dt_util.UTC),
        None,
        {stat_id},
        "hour",
        None,
        {"state", "sum"},
    )
    return [(row["state"], row["sum"]) for row in stats.get(stat_id, [])]


async def test_bill_statistics_rewrite_from_since(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """A billing change rewrites the costs from its date on and keeps the rest."""
    data_manager = FakeDataManager()
    await bill_stats.update_bill_statistics(hass, data_manager, SCUPS, SCUPS.upper())
    before = await _cost_rows(hass)
    assert len(before) == 48

    # new prices from the second day on
    since = datetime(2023, 1, 2)
    data_manager._bills = [
        x.model_copy(update={"value_eur": x.value_eur * 2})
        if x.datetime >= since
        else x
        for x in data_manager._bills
    ]
    await bill_stats.update_bill_statistics(
        hass, data_manager, SCUPS, SCUPS.upper(), since=since
    )
    after = await _cost_rows(hass)

    # no row added or removed; the first day is untouched
    assert len(after) == 48
    assert after[:24] == before[:24]
    # the second day is rewritten, and the sum carries on from the first
    values = [x.value_eur for x in data_manager._bills]
    assert [state for state, _ in after[24:]] == pytest.approx(values[24:])
    assert after[-1][1] == pytest.approx(sum(values))


async def test_cleared_statistics_can_be_rebuilt_right_away(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """Rebuilding right after clearing does not race the recorder (#355)."""
    data_manager = FakeDataManager()
    await bill_stats.update_bill_statistics(hass, data_manager, SCUPS, SCUPS.upper())
    assert len(await _cost_rows(hass)) == 48

    # a large history takes the recorder a while to clear
    clear = recorder_statistics.clear_statistics

    def slow_clear(*args: Any) -> None:
        time.sleep(0.5)
        clear(*args)

    stat_ids = [make_stat_id(DOMAIN, SCUPS, "cost")]
    with patch.object(recorder_statistics, "clear_statistics", slow_clear):
        await clear_statistics(hass, stat_ids, SCUPS.upper())
        await bill_stats.update_bill_statistics(
            hass, data_manager, SCUPS, SCUPS.upper()
        )
        assert len(await _cost_rows(hass)) == 48


async def _rows(hass: HomeAssistant, key: str, types: set) -> list[dict]:
    """Return every recorded row of an edata statistic."""
    stat_id = make_stat_id(DOMAIN, SCUPS, key)
    await async_wait_recording_done(hass)
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(1970, 1, 1, tzinfo=dt_util.UTC),
        None,
        {stat_id},
        "hour",
        None,
        types,
    )
    return stats.get(stat_id, [])


async def test_energy_statistics_rewrite_from_since(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """A full import rewrites the consumption from its date on and keeps the rest."""
    data_manager = FakeDataManager()
    await energy_stats.update_energy_statistics(
        hass, data_manager, SCUPS, SCUPS.upper()
    )
    before = await _rows(hass, "consumption", {"state", "sum"})
    assert len(before) == 48

    since = datetime(2023, 1, 2)
    data_manager._energy = [
        x.model_copy(update={"consumption_kwh": x.consumption_kwh * 2})
        if x.datetime >= since
        else x
        for x in data_manager._energy
    ]
    await energy_stats.update_energy_statistics(
        hass, data_manager, SCUPS, SCUPS.upper(), since=since
    )
    after = await _rows(hass, "consumption", {"state", "sum"})

    assert len(after) == 48
    assert after[:24] == before[:24]
    values = [x.consumption_kwh for x in data_manager._energy]
    assert [x["state"] for x in after[24:]] == pytest.approx(values[24:])
    assert after[-1]["sum"] == pytest.approx(sum(values))


async def test_power_statistics_rewrite_from_since(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """A full import rewrites the maximeter from its date on and keeps the rest."""
    data_manager = FakeDataManager()
    await power_stats.update_power_statistics(hass, data_manager, SCUPS, SCUPS.upper())
    before = await _rows(hass, "maximeter", {"max"})
    assert len(before) == 6

    since = datetime(2023, 1, 25)
    data_manager._power = [
        x.model_copy(update={"value_kw": x.value_kw + 1})
        if x.datetime >= since
        else x
        for x in data_manager._power
    ]
    await power_stats.update_power_statistics(
        hass, data_manager, SCUPS, SCUPS.upper(), since=since
    )
    after = await _rows(hass, "maximeter", {"max"})

    assert len(after) == 6
    assert after[:3] == before[:3]
    assert [x["max"] for x in after[3:]] == pytest.approx(
        [x.value_kw for x in data_manager._power[3:]]
    )
