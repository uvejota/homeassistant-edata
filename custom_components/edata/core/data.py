"""Definition of data manager for ha-edata integration."""

from datetime import datetime
import typing

from edata.models import Bill, Contract, Energy, Power, Statistics, Supply
from edata.models.bill import BillingRules
from edata.services.bill_service import BillService
from edata.services.data_service import DataService

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR


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
        )
        self._bill_service = BillService(cups=self.cups, storage_path=storage_path)

    async def sync(self) -> None:
        """Sync data from external service."""
        await self._data_service.update()
        if self.billing:
            await self._bill_service.update()

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
        return await self._data_service._get_last_energy_dt()  # noqa: SLF001

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
