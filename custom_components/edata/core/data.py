"""Definition of data manager for ha-edata integration."""

import calendar
from dataclasses import dataclass
from datetime import datetime
import typing

from edata.core.utils import get_month
from edata.models import Bill, Contract, Energy, Power, Statistics, Supply
from edata.models.bill import BillingRules, PVPCBillingRules
from edata.services.bill_service import BillService
from edata.services.data_service import DataService

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR


@dataclass
class BillSimulation:
    """A month's simulated bill and how much of the month it covers.

    Only hours with every input (consumption and, for PVPC, a price) are billed,
    so ``hours`` may fall short of ``month_hours`` and the bill short of the
    real one.
    """

    bill: Bill
    start: datetime
    end: datetime
    hours: float
    month_hours: int


class DataManager:
    """Defines the data manager for ha-edata integration."""

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
        """Initialize the data manager."""

        self.hass = hass
        self.cups = cups
        self.scups = scups
        self.billing = billing

        storage_path = self.hass.config.path(STORAGE_DIR)
        self._data_service = DataService(
            cups=self.cups,
            datadis_user=username,
            datadis_pwd=password,
            storage_path=storage_path,
            datadis_authorized_nif=authorized_nif,
            session=async_get_clientsession(hass),
        )
        self._bill_service = BillService(cups=self.cups, storage_path=storage_path)

    async def sync(self) -> bool:
        """Sync data from external service; return whether Datadis was reached."""
        synced = await self._data_service.update()
        if self.billing:
            await self._bill_service.update(
                billing_rules=self.billing,
                is_pvpc=isinstance(self.billing, PVPCBillingRules),
            )
        return synced

    async def full_sync(self) -> bool:
        """Re-fetch every record Datadis still serves, not just what is missing.

        The regular sync only asks for days that are missing or newer than the
        last record, and Datadis answers a repeated query from the connector's
        24 h cache. Requesting the whole history uses a different query, so it
        brings the latest data Datadis has (and fills older gaps it now has).
        The connector keeps the start within Datadis's two-year window.
        """
        if not await self._data_service.update():
            return False

        supply = await self._data_service.get_supply()
        if supply is None:
            return False
        start, end = supply.date_start, datetime.now()

        await self._data_service.update_energy(start, end)
        await self._data_service.update_power(start, end)
        await self._data_service.update_statistics(start, end)
        if self.billing:
            await self._bill_service.update(
                start=start,
                billing_rules=self.billing,
                is_pvpc=isinstance(self.billing, PVPCBillingRules),
            )
        return True

    async def run_migrations(self) -> list:
        """Import legacy 1.x on-disk storage into the 2.0 database, if present."""
        return await self._data_service.run_migrations()

    async def get_supply(
        self,
    ) -> Supply | None:
        """Get supply data."""
        return await self._data_service.get_supply()

    async def get_contracts(
        self,
    ) -> list[Contract]:
        """Get contracts data."""
        return await self._data_service.get_contracts()

    async def get_energy(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Energy]:
        """Get energy data."""
        return await self._data_service.get_energy(
            start=start,
            end=end,
        )

    async def get_most_recent_energy_dt(
        self,
    ) -> datetime | None:
        """Get the most recent energy data."""
        return await self._data_service.get_last_energy_dt()

    async def get_power(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Power]:
        """Get power data."""
        return await self._data_service.get_power(
            start=start,
            end=end,
        )

    async def get_bills(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bill]:
        """Get bills data."""
        return await self._bill_service.get_bills(
            start=start,
            end=end,
        )

    async def get_aggr_energy(
        self,
        aggregation: typing.Literal["day", "month"],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Statistics]:
        """Get aggregated energy data."""
        return await self._data_service.get_statistics(
            type_=aggregation,
            start=start,
            end=end,
        )

    async def get_aggr_bills(
        self,
        aggregation: typing.Literal["day", "month"],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bill]:
        """Get aggregated bill data."""
        return await self._bill_service.get_bills(
            start=start,
            end=end,
            type_=aggregation,
        )

    async def rebuild_billing(self, since: datetime | None = None) -> None:
        """Clear and recompute bills, optionally only from a datetime onwards."""
        await self._bill_service.clear_bills(since)
        if self.billing:
            await self._bill_service.update(
                start=since,
                billing_rules=self.billing,
                is_pvpc=isinstance(self.billing, PVPCBillingRules),
            )

    async def simulate_last_month(
        self, billing_rules: BillingRules, is_pvpc: bool
    ) -> BillSimulation | None:
        """Preview the last complete month's bill under candidate rules."""
        bills = await self._bill_service.simulate(
            billing_rules=billing_rules, is_pvpc=is_pvpc
        )
        if not bills:
            return None

        by_month: dict[datetime, list[Bill]] = {}
        for item in bills:
            by_month.setdefault(get_month(item.datetime), []).append(item)

        months = sorted(by_month)
        month = months[-2] if len(months) > 1 else months[-1]
        hourly = by_month[month]

        agg = Bill(datetime=month, delta_h=0)
        for item in hourly:
            agg.delta_h += item.delta_h
            agg.value_eur += item.value_eur
            agg.energy_term += item.energy_term
            agg.power_term += item.power_term
            agg.others_term += item.others_term
            agg.surplus_term += item.surplus_term

        return BillSimulation(
            bill=agg,
            start=min(x.datetime for x in hourly),
            end=max(x.datetime for x in hourly),
            hours=agg.delta_h,
            month_hours=calendar.monthrange(month.year, month.month)[1] * 24,
        )
