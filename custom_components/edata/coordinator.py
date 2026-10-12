"""Data update coordinator definitions."""

import asyncio
from datetime import datetime, time, timedelta
import logging

from dateutil.relativedelta import relativedelta
from edata.models.bill import BillingRules

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .core.config import CONF_CUPS
from .core.data import DataManager
from .core.options import SYNC_MODE_AUTO, SYNC_MODE_FIXED
from .core.statistics import (
    clear_statistics,
    get_integration_stat_ids,
    update_all_statistics,
)

_LOGGER = logging.getLogger(__name__)

# Datadis serves each query at most once every 24 h (repeats come from the
# connector's cache, which expires 24 h after each answer), so two syncs are
# always at least this far apart, counted from the end of the previous one.
SYNC_INTERVAL = timedelta(hours=24)
# automatic mode: how much later the sync time moves while syncs do not bring
# yesterday's data yet
SYNC_STEP = timedelta(minutes=30)
# how late after its time a sync may run to keep 24 h after the previous one;
# from this delay on, it rather waits for its time the next day
SYNC_MAX_DELAY = timedelta(hours=1)
# automatic mode: syncs without yesterday's data tolerated once it was reached
# (an occasional Datadis delay) before the sync time is moved later
SYNC_MISSES_TOLERATED = 1
# automatic mode: syncs in a row without yesterday's data (a whole turn of the
# clock) after which the supply is taken to lag two days behind, so the day
# before yesterday is awaited instead
SYNC_LAG_ATTEMPTS = int(timedelta(days=1) / SYNC_STEP)
SYNC_STORAGE_VERSION = 1


def sync_store(hass: HomeAssistant, scups: str) -> Store[dict[str, str]]:
    """Return the store that persists the last successful Datadis sync."""

    return Store(hass, SYNC_STORAGE_VERSION, f"{const.DOMAIN}.{scups.lower()}.sync")


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics.."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str | None = None,
        billing: BillingRules | None = None,
        sync_mode: str = SYNC_MODE_AUTO,
        sync_time: time | None = None,
    ) -> None:
        """Initialize the data handler."""

        # Store properties
        self.hass = hass
        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.scups = scups.upper()
        self.id = scups.lower()
        self.billing_rules = billing
        self._sync_task: asyncio.Task | None = None
        # last successful Datadis sync, persisted so a restart doesn't force one
        self._sync_store = sync_store(hass, self.scups)
        self._last_sync: datetime | None = None
        self._last_sync_loaded = False
        # automatic mode: the time of day it syncs at, whether a sync ever
        # brought yesterday's data, and how many in a row have not since
        self._sync_at: time | None = None
        self._sync_stable = False
        self._sync_misses = 0
        # automatic mode: days behind today of the last day awaited complete
        self._sync_lag = 1
        self._sync_mode = sync_mode
        self._sync_time = sync_time
        self._unsub_sync_timer: CALLBACK_TYPE | None = None

        # Init shared data
        hass.data[const.DOMAIN][self.id] = {CONF_CUPS: self.cups}
        self._shared = hass.data[const.DOMAIN][self.id]

        # Instantiate the managers
        self._data_manager = DataManager(
            hass=hass,
            username=username,
            password=password,
            cups=self.cups,
            scups=self.scups,
            authorized_nif=authorized_nif,
            billing=billing,
        )

        # Making self._shared to reference hass.data[const.DOMAIN][self.id] so we can use it like an alias
        self._shared = hass.data[const.DOMAIN][self.id]
        self._shared.update(
            {
                const.SHARED_STATE: "loading",
                const.SHARED_DATAMANAGER: self._data_manager,
            }
        )

        # init the coordinator
        super().__init__(
            hass,
            _LOGGER,
            name=f"{const.DOMAIN}_{self.id}",
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API."""

        await self._async_load_sync_state()
        await self._load_data()

        if not await self._async_sync_due():
            self._schedule_sync()
            return self._shared

        # Never let a slow full sync stack: skip if the previous one is still running.
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = self.hass.async_create_background_task(
                self._sync_data(),
                f"{const.DOMAIN}_{self.id}_update_data_task",
            )
        else:
            _LOGGER.debug("%s: previous sync still running, skipping", self.scups)

        return self._shared

    async def _async_load_sync_state(self) -> None:
        """Load the persisted sync state once."""

        if self._last_sync_loaded:
            return
        stored = await self._sync_store.async_load() or {}
        if last := stored.get("last_sync"):
            self._last_sync = dt_util.parse_datetime(last)
        if sync_at := stored.get("sync_at"):
            self._sync_at = dt_util.parse_time(sync_at)
        self._sync_stable = stored.get("stable", False)
        self._sync_misses = stored.get("misses", 0)
        self._sync_lag = stored.get("lag", 1)
        self._last_sync_loaded = True

    async def _async_sync_due(self) -> bool:
        """Return whether it is time for the next Datadis sync."""

        await self._async_load_sync_state()
        next_sync = self.next_sync
        if next_sync is None:
            return True
        if dt_util.utcnow() < next_sync:
            _LOGGER.debug(
                "%s: last Datadis sync at %s, skipping until %s",
                self.scups,
                self._last_sync,
                next_sync,
            )
            return False
        return True

    @property
    def next_sync(self) -> datetime | None:
        """Return when the next Datadis sync is due (``None``: right away)."""

        if self._last_sync is None:
            return None
        if self._sync_mode == SYNC_MODE_FIXED and self._sync_time is not None:
            sync_at = self._sync_time
        elif self._sync_at is not None:
            sync_at = self._sync_at
        else:
            # stored by an older version: keep the time it synced at
            sync_at = dt_util.as_local(self._last_sync).time()
        return self._next_sync_at(sync_at)

    def _next_sync_at(self, sync_at: time) -> datetime:
        """Return the first sync at ``sync_at``, at least 24 h after the last.

        A sync ends some seconds after its time, so the next one has to wait
        those seconds too. Once that delay adds up to an hour (or the last sync
        ran late, e.g. after a restart), a day is skipped to get back to the
        sync time.
        """

        earliest = self._last_sync + SYNC_INTERVAL
        day = dt_util.as_local(self._last_sync).date()
        while True:
            candidate = datetime.combine(
                day, sync_at, tzinfo=dt_util.get_default_time_zone()
            )
            if earliest - candidate < SYNC_MAX_DELAY:
                return max(candidate, earliest)
            day += timedelta(days=1)

    @callback
    def _schedule_sync(self) -> None:
        """Wake up exactly when the next Datadis sync is due."""

        if self._unsub_sync_timer is not None:
            self._unsub_sync_timer()
            self._unsub_sync_timer = None
        next_sync = self.next_sync
        if next_sync is None or next_sync <= dt_util.utcnow():
            # due now: the next hourly refresh takes care of it
            return

        @callback
        def _sync_time_reached(_now: datetime) -> None:
            self._unsub_sync_timer = None
            self.hass.async_create_background_task(
                self.async_refresh(), f"{const.DOMAIN}_{self.id}_scheduled_sync"
            )

        self._unsub_sync_timer = async_track_point_in_utc_time(
            self.hass, _sync_time_reached, next_sync
        )

    @callback
    def set_sync_schedule(self, mode: str, sync_time: time | None) -> None:
        """Apply a new sync mode and fixed time."""

        if (mode, sync_time) == (self._sync_mode, self._sync_time):
            return
        self._sync_mode, self._sync_time = mode, sync_time
        if self._last_sync_loaded:
            self._schedule_sync()

    async def async_shutdown(self) -> None:
        """Cancel the scheduled sync."""

        await super().async_shutdown()
        if self._unsub_sync_timer is not None:
            self._unsub_sync_timer()
            self._unsub_sync_timer = None

    async def _async_update_sync_time(self) -> None:
        """Move the automatic sync time later while the awaited day is missing.

        The awaited day is yesterday, or the day before for supplies that a
        whole turn of the clock showed to lag two days behind.
        """

        if self._sync_at is None:
            self._sync_at = (
                dt_util.as_local(self._last_sync).time().replace(microsecond=0)
            )
        if await self._async_has_day(1):
            if self._sync_lag != 1:
                _LOGGER.info("%s: yesterday's data arrived, awaiting it", self.scups)
            self._sync_lag = 1
            self._sync_stable = True
            self._sync_misses = 0
            return
        if self._sync_lag == 2 and await self._async_has_day(2):
            self._sync_stable = True
            self._sync_misses = 0
            return

        self._sync_misses += 1
        if (
            self._sync_lag == 1
            and self._sync_misses >= SYNC_LAG_ATTEMPTS
            and await self._async_has_day(2)
        ):
            _LOGGER.info(
                "%s: no data for yesterday at any time of the day, "
                "awaiting the day before yesterday",
                self.scups,
            )
            self._sync_lag = 2
            self._sync_stable = True
            self._sync_misses = 0
            return
        if self._sync_stable and self._sync_misses <= SYNC_MISSES_TOLERATED:
            _LOGGER.info(
                "%s: awaited day not there yet, keeping the sync time", self.scups
            )
            return
        self._sync_at = (
            datetime.combine(dt_util.now().date(), self._sync_at) + SYNC_STEP
        ).time()
        _LOGGER.info(
            "%s: awaited day not there yet, syncing at %s from now on",
            self.scups,
            self._sync_at,
        )

    async def _async_has_day(self, days_ago: int) -> bool:
        """Return whether the stored data covers the whole day ``days_ago`` ago."""

        last = await self._data_manager.get_most_recent_energy_dt()
        if last is None:
            return False
        # energy records are local (Spanish) time and start at the hour
        day_end = datetime.combine(
            dt_util.now().date() - timedelta(days=days_ago - 1), time.min
        )
        return last.replace(tzinfo=None) >= day_end - timedelta(hours=1)

    async def _async_sync_datadis(self, full: bool = False) -> bool:
        """Sync from Datadis and record the time when it succeeds.

        ``full`` re-fetches the whole history Datadis serves instead of only
        what is missing (see ``DataManager.full_sync``).
        """

        if full:
            synced = await self._data_manager.full_sync()
        else:
            synced = await self._data_manager.sync()
        if synced:
            await self._async_load_sync_state()
            self._last_sync = dt_util.utcnow()
            # a manual sync only delays the next one: its time says nothing
            # about when Datadis has the data
            if not full and self._sync_mode != SYNC_MODE_FIXED:
                await self._async_update_sync_time()
            await self._sync_store.async_save(
                {
                    "last_sync": self._last_sync.isoformat(),
                    "sync_at": self._sync_at.isoformat() if self._sync_at else None,
                    "stable": self._sync_stable,
                    "misses": self._sync_misses,
                    "lag": self._sync_lag,
                }
            )
            _LOGGER.info(
                "%s: Datadis synced, next sync at %s", self.scups, self.next_sync
            )
            self._schedule_sync()
        elif self._data_manager.login_rejected and self.config_entry is not None:
            # retrying cannot help: ask the user for the new password (HA keeps
            # a single re-authentication flow per entry)
            _LOGGER.warning(
                "%s: Datadis rejected the credentials, asking to re-authenticate",
                self.scups,
            )
            self.config_entry.async_start_reauth(self.hass)
        return synced

    async def _sync_data(self):
        """Sync data via API."""

        _LOGGER.info("%s: updating data", self.scups)
        await self._async_sync_datadis()
        await self._load_data()

        _LOGGER.info("%s: updating all statistics", self.scups)
        await update_all_statistics(
            self.hass,
            self._data_manager,
            self.id,
            self.scups,
        )

    async def _load_data(self) -> bool:
        """Load state and attributes."""

        attrs = self._shared.get(const.SHARED_ATTRIBUTES, {})
        a_year_ago = dt_util.now() - relativedelta(years=1)

        # Get supply and contract info
        supply = await self._data_manager.get_supply()
        if supply:
            attrs.update(
                {
                    "cups": supply.cups,
                    "supply_address": supply.address,
                    "supply_point_type": supply.point_type,
                }
            )
        contracts = await self._data_manager.get_contracts()
        attrs.update(
            {
                "contract_p1_kw": contracts[-1].power_p1 if contracts else None,
                "contract_p2_kw": contracts[-1].power_p2 if contracts else None,
            }
        )

        attrs.update(
            {
                "last_datetime": await self._data_manager.get_most_recent_energy_dt(),
                "next_sync": self.next_sync,
            }
        )

        energy_daily = await self._data_manager.get_aggr_energy(
            aggregation="day", start=a_year_ago
        )
        if energy_daily:
            last_day = energy_daily[-1]
            attrs.update({f"last_day_{x}": y for x, y in last_day.model_dump().items()})

        energy_monthly = await self._data_manager.get_aggr_energy(
            aggregation="month", start=a_year_ago
        )
        if energy_monthly:
            last_month = energy_monthly[-1]
            attrs.update({f"month_{x}": y for x, y in last_month.model_dump().items()})
        if len(energy_monthly) > 1:
            last_month = energy_monthly[-2]
            attrs.update(
                {f"last_month_{x}": y for x, y in last_month.model_dump().items()}
            )

        power = await self._data_manager.get_power(start=a_year_ago)
        attrs.update(
            {
                "max_power_kw": max(power, key=lambda x: x.value_kw).value_kw
                if power
                else None,
                "max_power_datetime": max(power, key=lambda x: x.value_kw).datetime
                if power
                else None,
                "max_power_mean_kw": sum(p.value_kw for p in power) / len(power)
                if power
                else None,
            }
        )

        if self.billing_rules:
            bills = await self._data_manager.get_aggr_bills(
                aggregation="month",
                start=dt_util.now() - relativedelta(years=1),
            )
            if bills:
                last_bill = bills[-1]
                attrs.update(
                    {f"month_bill_{x}": y for x, y in last_bill.model_dump().items()}
                )
                if len(bills) > 1:
                    prev_bill = bills[-2]
                    attrs.update(
                        {
                            f"last_month_bill_{x}": y
                            for x, y in prev_bill.model_dump().items()
                        }
                    )

        # update state
        self._shared["state"] = attrs["last_datetime"]
        self._shared[const.SHARED_ATTRIBUTES] = attrs

        _LOGGER.debug("%s: updated state and attributes: %s", self.scups, attrs)

        self.async_update_listeners()

        return True

    async def async_soft_reset(self):
        """Apply an async soft reset - clears and rebuilds HA statistics."""

        stat_ids = await get_integration_stat_ids(
            self.hass,
            const.DOMAIN,
            self.id,
        )
        clear_statistics(self.hass, stat_ids, self.scups)
        await update_all_statistics(
            self.hass,
            self._data_manager,
            self.id,
            self.scups,
        )

    async def async_full_import(self):
        """Fetch all available data from Datadis and rebuild statistics."""

        _LOGGER.warning("%s: importing all available data from Datadis", self.scups)
        await self._async_sync_datadis(full=True)
        await self._load_data()
        await self.async_soft_reset()

    async def update_billing(
        self, billing_rules: BillingRules | None, since: datetime | None
    ) -> None:
        """Apply new billing rules and recompute cost statistics from a date."""

        _LOGGER.info("%s: updating billing since %s", self.scups, since)
        self.billing_rules = billing_rules
        self._data_manager.billing = billing_rules

        await self._data_manager.rebuild_billing(since)

        stat_ids = await get_integration_stat_ids(self.hass, const.DOMAIN, self.id)
        cost_stat_ids = [stat_id for stat_id in stat_ids if "cost" in stat_id]
        clear_statistics(self.hass, cost_stat_ids, self.scups)

        await update_all_statistics(
            self.hass,
            self._data_manager,
            self.id,
            self.scups,
        )
        await self._load_data()
