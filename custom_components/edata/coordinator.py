"""Data update coordinator definitions."""

import asyncio
from datetime import datetime, timedelta
import logging

from dateutil.relativedelta import relativedelta
from edata.models.bill import BillingRules

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .core.config import CONF_CUPS
from .core.data import DataManager
from .core.statistics import (
    clear_statistics,
    get_integration_stat_ids,
    update_all_statistics,
)

_LOGGER = logging.getLogger(__name__)


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

        await self._load_data()

        # Never let a slow full sync stack: skip if the previous one is still running.
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = self.hass.async_create_background_task(
                self._sync_data(),
                f"{const.DOMAIN}_{self.id}_update_data_task",
            )
        else:
            _LOGGER.debug("%s: previous sync still running, skipping", self.scups)

        return self._shared

    async def _sync_data(self):
        """Sync data via API."""

        _LOGGER.info("%s: updating data", self.scups)
        await self._data_manager.sync()
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
            {"last_datetime": await self._data_manager.get_most_recent_energy_dt()}
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
            bills = await self._data_manager.get_bills(
                start=dt_util.now() - relativedelta(years=1)
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
        await self._data_manager.sync()
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
