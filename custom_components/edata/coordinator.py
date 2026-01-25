"""Data update coordinator definitions."""

from datetime import timedelta
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

        self.hass.async_create_background_task(
            self._sync_data(),
            f"{const.DOMAIN}_{self.id}_update_data_task",
        )

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
        # supply = await self._data_manager.get_supply()
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
