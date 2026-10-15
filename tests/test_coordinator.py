"""Tests for the coordinator's Datadis sync throttling."""

from datetime import datetime, time, timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.edata.const import DOMAIN
from custom_components.edata.coordinator import (
    SYNC_INTERVAL,
    SYNC_LAG_ATTEMPTS,
    SYNC_STEP,
    EdataCoordinator,
)
from custom_components.edata.core.options import (
    CONF_SYNC_MODE,
    CONF_SYNC_TIME,
    SYNC_MODE_FIXED,
)

from .fixtures import SCUPS

# the fake energy data ends at 2023-01-02 23:00, so at this time (early morning
# of 2023-01-03 in the test time zone) yesterday's data is complete
FRESH_DATA_NOW = "2023-01-03 12:00:00+00:00"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> EdataCoordinator:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][SCUPS]["coordinator"]


def _yesterday_end() -> datetime:
    """Return the last hour of yesterday, as the energy records store it."""
    return datetime.combine(dt_util.now().date(), time.min) - timedelta(hours=1)


async def _refresh(hass: HomeAssistant, coordinator: EdataCoordinator) -> None:
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_sync_skipped_within_interval(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After a successful sync, refreshes skip Datadis until the interval passes."""
    freezer.move_to(FRESH_DATA_NOW)
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1

    freezer.tick(SYNC_INTERVAL - timedelta(minutes=1))
    await _refresh(hass, coordinator)
    assert manager.synced == 1

    freezer.tick(timedelta(minutes=2))
    await _refresh(hass, coordinator)
    assert manager.synced == 2


async def test_failed_sync_is_retried(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """A sync that did not reach Datadis is retried on the next refresh."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1

    manager.sync_result = False
    coordinator._last_sync = None
    await _refresh(hass, coordinator)
    assert manager.synced == 2
    await _refresh(hass, coordinator)
    assert manager.synced == 3


async def test_last_sync_survives_restart(
    setup_integration: None,
    hass: HomeAssistant,
    hass_storage: dict,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """A recent sync stored before a restart prevents a new one at startup."""
    hass_storage[f"{DOMAIN}.{SCUPS.lower()}.sync"] = {
        "version": 1,
        "key": f"{DOMAIN}.{SCUPS.lower()}.sync",
        "data": {"last_sync": (dt_util.utcnow() - timedelta(hours=1)).isoformat()},
    }

    coordinator = await _setup(hass, config_entry)
    assert coordinator._data_manager.synced == 0


async def test_full_import_always_syncs(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """The manual full import bypasses the interval and re-fetches everything."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert (manager.synced, manager.full_synced) == (1, 0)
    first_sync = coordinator._last_sync

    await coordinator.async_full_import()
    assert (manager.synced, manager.full_synced) == (1, 1)
    assert coordinator._last_sync > first_sync


async def test_sync_store_removed_with_entry(
    setup_integration: None,
    hass: HomeAssistant,
    hass_storage: dict,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Removing the entry deletes its persisted last-sync timestamp."""
    key = f"{DOMAIN}.{SCUPS.lower()}.sync"
    await _setup(hass, config_entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert key in hass_storage

    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def test_rejected_credentials_ask_to_reauthenticate(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """When Datadis rejects the credentials, the user is asked for new ones."""
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager

    # Datadis not answering is only retried
    manager.sync_result = False
    coordinator._last_sync = None
    await _refresh(hass, coordinator)
    assert not list(config_entry.async_get_active_flows(hass, {SOURCE_REAUTH}))

    manager.login_rejected = True
    await _refresh(hass, coordinator)
    await _refresh(hass, coordinator)
    flows = list(config_entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"


async def test_auto_sync_moves_later_until_yesterday_arrives(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Without yesterday's data, each sync is tried half an hour later."""
    freezer.move_to("2023-01-05 12:00:00+00:00")
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert manager.synced == 1
    assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL + SYNC_STEP

    freezer.tick(SYNC_INTERVAL + timedelta(minutes=1))
    await _refresh(hass, coordinator)
    assert manager.synced == 1

    freezer.move_to(coordinator.next_sync)
    manager.last_energy_dt = _yesterday_end()
    await _refresh(hass, coordinator)
    assert manager.synced == 2
    # yesterday arrived: that time is kept
    assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL


async def test_auto_sync_tolerates_one_miss(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Once yesterday's data arrived, a single late day does not move the time."""
    freezer.move_to(FRESH_DATA_NOW)
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL

    # the fake data stays at 2023-01-02 from now on
    for misses, step in ((1, timedelta(0)), (2, SYNC_STEP), (3, SYNC_STEP)):
        freezer.move_to(coordinator.next_sync)
        await _refresh(hass, coordinator)
        assert coordinator._sync_misses == misses
        assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL + step

    freezer.move_to(coordinator.next_sync)
    manager.last_energy_dt = _yesterday_end()
    await _refresh(hass, coordinator)
    assert manager.synced == 5
    assert coordinator._sync_misses == 0
    assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL


async def test_auto_sync_learns_two_day_lag(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A supply that never has yesterday's data awaits the day before instead."""
    # the fake data ends with the day before yesterday
    freezer.move_to("2023-01-04 12:00:00+00:00")
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager

    # a whole turn of the clock without yesterday's data
    for _ in range(SYNC_LAG_ATTEMPTS - 1):
        assert coordinator._sync_lag == 1
        assert coordinator.next_sync == (
            coordinator._last_sync + SYNC_INTERVAL + SYNC_STEP
        )
        freezer.move_to(coordinator.next_sync)
        manager.last_energy_dt = _yesterday_end() - timedelta(days=1)
        await _refresh(hass, coordinator)
    assert manager.synced == SYNC_LAG_ATTEMPTS
    assert coordinator._sync_lag == 2
    # the day before yesterday is there: the time is kept from now on
    assert coordinator.next_sync == coordinator._last_sync + SYNC_INTERVAL

    freezer.move_to(coordinator.next_sync)
    manager.last_energy_dt = _yesterday_end() - timedelta(days=1)
    await _refresh(hass, coordinator)
    assert (coordinator._sync_lag, coordinator._sync_misses) == (2, 0)

    # yesterday's data shows up again: back to awaiting it
    freezer.move_to(coordinator.next_sync)
    manager.last_energy_dt = _yesterday_end()
    await _refresh(hass, coordinator)
    assert (coordinator._sync_lag, coordinator._sync_misses) == (1, 0)


async def test_failed_sync_keeps_schedule(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A sync that did not reach Datadis neither counts as late nor moves the time."""
    freezer.move_to(FRESH_DATA_NOW)
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    next_sync = coordinator.next_sync

    manager.sync_result = False
    freezer.move_to(next_sync)
    await _refresh(hass, coordinator)
    assert manager.synced == 2
    assert coordinator._sync_misses == 0
    assert coordinator.next_sync == next_sync


async def test_scheduled_sync_runs_on_time(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The next sync is scheduled for its exact time, not the next hourly refresh."""
    freezer.move_to(FRESH_DATA_NOW)
    coordinator = await _setup(hass, config_entry)
    manager = coordinator._data_manager
    next_sync = coordinator.next_sync
    assert coordinator._unsub_sync_timer is not None

    freezer.move_to(next_sync)
    async_fire_time_changed(hass, next_sync)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert manager.synced == 2
    # and the following one is scheduled again
    assert coordinator.next_sync == next_sync + SYNC_INTERVAL
    assert coordinator._unsub_sync_timer is not None


@pytest.mark.parametrize(
    ("sync_at", "delay"),
    [(timedelta(minutes=30), SYNC_INTERVAL + SYNC_STEP), (None, SYNC_INTERVAL)],
    ids=["moved_later", "before_upgrade"],
)
async def test_sync_time_survives_restart(
    setup_integration: None,
    hass: HomeAssistant,
    hass_storage: dict,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    sync_at: timedelta | None,
    delay: timedelta,
) -> None:
    """The automatic sync time is restored; older stores keep the last sync's."""
    last_sync = dt_util.utcnow().replace(microsecond=0) - timedelta(hours=1)
    stored = {"last_sync": last_sync.isoformat()}
    if sync_at is not None:
        stored["sync_at"] = dt_util.as_local(last_sync + sync_at).time().isoformat()
        stored["lag"] = 2
    key = f"{DOMAIN}.{SCUPS.lower()}.sync"
    hass_storage[key] = {"version": 1, "key": key, "data": stored}

    coordinator = await _setup(hass, config_entry)
    assert coordinator._data_manager.synced == 0
    assert coordinator.next_sync == last_sync + delay
    assert coordinator._sync_lag == (1 if sync_at is None else 2)


async def test_manual_sync_keeps_sync_time(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A forced sync delays the next one, but not to its own time of day."""
    freezer.move_to(FRESH_DATA_NOW)
    coordinator = await _setup(hass, config_entry)
    first_sync = coordinator._last_sync

    freezer.tick(timedelta(hours=5))
    await coordinator.async_full_import()
    # tomorrow at the usual time is not 24 h after the forced sync yet
    assert coordinator.next_sync == first_sync + 2 * SYNC_INTERVAL
    assert coordinator._sync_misses == 0


async def test_fixed_sync_time(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """A fixed time is kept at least 24 h after the end of the previous sync."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=SCUPS,
        data=config_entry.data,
        options={CONF_SYNC_MODE: SYNC_MODE_FIXED, CONF_SYNC_TIME: "19:00:00"},
    )
    coordinator = await _setup(hass, entry)
    tz = dt_util.get_default_time_zone()

    def local(*args: int) -> datetime:
        return datetime(*args, tzinfo=tz)

    for last, expected in (
        # a manual sync in the morning: the fixed time the next day
        (local(2023, 1, 5, 10, 0), local(2023, 1, 6, 19, 0)),
        # the sync itself took 40 s: the next one waits for them
        (local(2023, 1, 5, 19, 0, 40), local(2023, 1, 6, 19, 0, 40)),
        # 59 min late is still waited for
        (local(2023, 1, 5, 19, 59), local(2023, 1, 6, 19, 59)),
        # an hour late: skip a day to get back to the fixed time
        (local(2023, 1, 5, 20, 0), local(2023, 1, 7, 19, 0)),
        # the day clocks go forward is only 23 h long: an hour late too
        (local(2023, 3, 11, 19, 0), local(2023, 3, 13, 19, 0)),
    ):
        coordinator._last_sync = dt_util.as_utc(last)
        assert coordinator.next_sync == expected, last


@pytest.mark.parametrize(
    ("since", "expected"),
    [
        (datetime(2023, 1, 2), datetime(2023, 1, 2)),
        # recalculated from the start: from the first bill, so the costs
        # recorded before edata.db begins (e.g. by 1.x) are kept
        (None, datetime(2023, 1, 1)),
    ],
    ids=["since_date", "from_the_start"],
)
async def test_billing_change_rewrites_costs_from_its_date(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    mock_bill_statistics: AsyncMock,
    since: datetime | None,
    expected: datetime,
) -> None:
    """New billing rules rewrite the cost statistics instead of clearing them."""
    coordinator = await _setup(hass, billing_config_entry)

    with patch(
        "custom_components.edata.coordinator.clear_statistics", AsyncMock()
    ) as clear:
        await coordinator.update_billing(coordinator.billing_rules, since)

    clear.assert_not_awaited()
    mock_bill_statistics.assert_awaited_once()
    assert mock_bill_statistics.await_args.kwargs["since"] == expected


async def test_billing_disabled_clears_costs(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
    mock_bill_statistics: AsyncMock,
) -> None:
    """Turning billing off clears the cost statistics."""
    coordinator = await _setup(hass, billing_config_entry)

    with (
        patch(
            "custom_components.edata.coordinator.get_integration_stat_ids",
            AsyncMock(
                return_value=[f"{DOMAIN}:{SCUPS}_cost", f"{DOMAIN}:{SCUPS}_consumption"]
            ),
        ),
        patch(
            "custom_components.edata.coordinator.clear_statistics", AsyncMock()
        ) as clear,
    ):
        await coordinator.update_billing(None, None)

    clear.assert_awaited_once()
    assert clear.await_args.args[1] == [f"{DOMAIN}:{SCUPS}_cost"]
    mock_bill_statistics.assert_not_awaited()
