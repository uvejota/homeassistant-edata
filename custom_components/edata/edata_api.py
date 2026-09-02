"""Adapter between the e-data 2.x library and this integration.

The 2.x library replaced ``EdataHelper`` with two async services
(``DataService`` and ``BillService``) returning pydantic models, and dropped both
the ``data`` dict of lists and the ``attributes`` summary the integration was
built around.

This module restores those two shapes so the coordinator, the sensors, the
websockets and the bundled Lovelace card keep working unchanged:

    DataService/BillService -> EdataApi -> .data{} + .attributes{} -> consumers
              (2.x models)     (here)      (legacy field names)

Everything the library exposes is imported lazily inside functions: importing
``edata.services`` pulls SQLAlchemy, sqlmodel, pydantic, holidays and jinja2, and
that must not happen in the Home Assistant event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import os
from typing import Any

from . import const
from .summary import build_attributes

_LOGGER = logging.getLogger(__name__)

# Subdirectory and file name of the 1.x JSON storage, as written by migrate.py
# and as expected by the library's legacy_json_1_3_3 migration.
LEGACY_SUBDIR = "edata"
DB_FILENAME = "edata.db"

DATA_KEYS = (
    "supplies",
    "contracts",
    "consumptions",
    "maximeter",
    "pvpc",
    "consumptions_daily_sum",
    "consumptions_monthly_sum",
    "cost_hourly_sum",
    "cost_daily_sum",
    "cost_monthly_sum",
)

_get_tariff = None


def tariff_label(a_datetime: datetime) -> str:
    """Return the tariff of a datetime as 'p1', 'p2' or 'p3'.

    Replaces the 1.x ``edata.processors.utils.get_pvpc_tariff``, which returned
    the label directly; 2.x returns an int instead.
    """

    global _get_tariff  # noqa: PLW0603

    if _get_tariff is None:
        from edata.core.utils import get_tariff  # noqa: PLC0415

        _get_tariff = get_tariff

    tariff = _get_tariff(a_datetime)

    if tariff not in (1, 2, 3):
        # the library returns 0 when it cannot decide, which would leave the
        # per-tariff cost statistics without a bucket to write into
        _LOGGER.warning("Unexpected tariff %s at %s, assuming p3", tariff, a_datetime)
        tariff = 3

    return f"p{tariff}"


# Energy prices are per-tariff in custom billing, but PVPC takes them from
# REData: PVPCBillingRules types these fields as None and rejects floats.
KWH_PRICE_KEYS = (
    const.PRICE_P1_KWH,
    const.PRICE_P2_KWH,
    const.PRICE_P3_KWH,
    const.PRICE_SURP_P1_KWH,
    const.PRICE_SURP_P2_KWH,
    const.PRICE_SURP_P3_KWH,
)


def build_billing_rules(options: dict[str, Any], is_pvpc: bool):
    """Build the library billing rules out of the config entry options.

    Replaces the 1.x ``PricingRules`` dict. The option keys already match the
    model field names, so this only has to drop what does not belong.
    """

    from edata.models.bill import BillingRules, PVPCBillingRules  # noqa: PLC0415

    model = PVPCBillingRules if is_pvpc else BillingRules
    excluded = KWH_PRICE_KEYS if is_pvpc else ()

    return model(
        **{
            key: value
            for key, value in options.items()
            if key in model.model_fields and key not in excluded and value is not None
        }
    )


def _energy_to_dict(item) -> dict[str, Any]:
    """Map an Energy model into the legacy 'consumptions' shape."""

    return {
        "datetime": item.datetime,
        "delta_h": item.delta_h,
        "value_kWh": item.consumption_kwh,
        "surplus_kWh": item.surplus_kwh,
        "real": item.real,
    }


def _statistics_to_dict(item) -> dict[str, Any]:
    """Map a Statistics model into the legacy 'consumptions_*_sum' shape."""

    return {
        "datetime": item.datetime,
        "delta_h": item.delta_h,
        "value_kWh": item.consumption_kwh,
        "value_p1_kWh": item.consumption_p1_kwh,
        "value_p2_kWh": item.consumption_p2_kwh,
        "value_p3_kWh": item.consumption_p3_kwh,
        "surplus_kWh": item.surplus_kwh,
        "surplus_p1_kWh": item.surplus_p1_kwh,
        "surplus_p2_kWh": item.surplus_p2_kwh,
        "surplus_p3_kWh": item.surplus_p3_kwh,
    }


def _power_to_dict(item) -> dict[str, Any]:
    """Map a Power model into the legacy 'maximeter' shape.

    'value_p1_kW'/'value_p2_kW' were never provided by the 1.x library even
    though websockets.py filters on them; they are derived here with the same
    peak/off-peak split the coordinator applies to maximeter statistics.
    """

    is_p1 = tariff_label(item.datetime) == "p1"

    return {
        "datetime": item.datetime,
        "value_kW": item.value_kw,
        "value_p1_kW": item.value_kw if is_p1 else 0,
        "value_p2_kW": 0 if is_p1 else item.value_kw,
    }


def _bill_to_dict(item) -> dict[str, Any]:
    """Map a Bill model into the legacy 'cost_*_sum' shape."""

    return {
        "datetime": item.datetime,
        "delta_h": item.delta_h,
        "value_eur": item.value_eur,
        "energy_term": item.energy_term,
        "power_term": item.power_term,
        "others_term": item.others_term,
        "surplus_term": item.surplus_term,
    }


def _contract_to_dict(item) -> dict[str, Any]:
    """Map a Contract model into the legacy 'contracts' shape."""

    return {
        "date_start": item.date_start,
        "date_end": item.date_end,
        "marketer": item.marketer,
        "distributorCode": item.distributor_code,
        "power_p1": item.power_p1,
        "power_p2": item.power_p2,
    }


def _supply_to_dict(item) -> dict[str, Any]:
    """Map a Supply model into the legacy 'supplies' shape."""

    return {
        "cups": item.cups,
        "date_start": item.date_start,
        "date_end": item.date_end,
        "address": item.address,
        "postal_code": item.postal_code,
        "province": item.province,
        "municipality": item.municipality,
        "distributor": item.distributor,
        "pointType": item.point_type,
        "distributorCode": item.distributor_code,
    }


def _price_to_dict(item) -> dict[str, Any]:
    """Map an EnergyPrice model into the legacy 'pvpc' shape."""

    return {
        "datetime": item.datetime,
        "delta_h": item.delta_h,
        "value_eur_kWh": item.value_eur_kwh,
    }


class EdataApi:
    """Hold the 2.x services and expose 1.x-shaped data and attributes."""

    def __init__(
        self,
        cups: str,
        username: str,
        password: str,
        authorized_nif: str | None,
        storage_path: str,
    ) -> None:
        """Initialize the adapter.

        Blocking: building the services creates the storage directory, the async
        SQLAlchemy engine and the Datadis diskcache. Instantiate from an
        executor thread.
        """

        self.cups = cups.upper()
        self.data: dict[str, list[dict[str, Any]]] = {x: [] for x in DATA_KEYS}
        self.attributes: dict[str, Any] = dict.fromkeys(const.ATTRIBUTES)

        self._username = username
        self._password = password
        self._authorized_nif = authorized_nif
        self._storage_path = storage_path

        self._build_services()

    def _build_services(self) -> None:
        """Instantiate both library services. Blocking."""

        from edata.services.bill_service import BillService  # noqa: PLC0415
        from edata.services.data_service import DataService  # noqa: PLC0415

        self._data_service = DataService(
            self.cups,
            self._username,
            self._password,
            self._storage_path,
            datadis_authorized_nif=self._authorized_nif,
        )
        self._bill_service = BillService(self.cups, self._storage_path)

    @property
    def legacy_storage_path(self) -> str:
        """Return the path of the 1.x JSON storage for this supply."""

        return os.path.join(
            self._storage_path, LEGACY_SUBDIR, f"edata_{self.cups.lower()}.json"
        )

    @property
    def db_path(self) -> str:
        """Return the path of the 2.x SQLite database."""

        return os.path.join(self._storage_path, DB_FILENAME)

    async def async_import_legacy_storage(self) -> bool:
        """Import the 1.x JSON storage into the database, once.

        Guarded on the database being empty for this supply: the library
        migration is idempotent but reads the whole JSON file with a blocking
        call inside a coroutine, so it must not run on every startup.
        """

        if await self._data_service.get_last_energy_dt() is not None:
            return False

        if not await asyncio.to_thread(os.path.exists, self.legacy_storage_path):
            _LOGGER.debug(
                "%s: no legacy storage found at %s",
                self.cups,
                self.legacy_storage_path,
            )
            return False

        _LOGGER.warning(
            "%s: importing legacy storage '%s' into '%s', this may take a while",
            self.cups,
            self.legacy_storage_path,
            self.db_path,
        )

        results = await self._data_service.run_migrations(compile_statistics=True)
        for result in results:
            _LOGGER.warning(
                "%s: migration '%s' imported %s supplies, %s contracts, %s energy, "
                "%s power and %s pvpc records",
                self.cups,
                result.name,
                result.supplies,
                result.contracts,
                result.energy,
                result.power,
                result.pvpc,
            )

        return True

    async def async_update(self, date_from: datetime, date_to: datetime) -> bool:
        """Fetch new data from Datadis and REData."""

        return await self._data_service.update(date_from, date_to)

    async def async_refresh_cache(self, date_from: datetime, date_to: datetime) -> None:
        """Reload the in-memory data and attributes from the database."""

        supplies = await self._data_service.get_supplies()
        contracts = await self._data_service.get_contracts()
        energy = await self._data_service.get_energy(date_from, date_to)
        power = await self._data_service.get_power(date_from, date_to)
        pvpc = await self._data_service.get_pvpc(date_from, date_to)
        daily = await self._data_service.get_statistics("day", date_from, date_to)
        monthly = await self._data_service.get_statistics("month", date_from, date_to)
        hourly_cost = await self._bill_service.get_bills(
            date_from, date_to, type_="hour"
        )
        daily_cost = await self._bill_service.get_bills(date_from, date_to, type_="day")
        monthly_cost = await self._bill_service.get_bills(
            date_from, date_to, type_="month"
        )

        self.data.update(
            {
                "supplies": [_supply_to_dict(x) for x in supplies],
                "contracts": [_contract_to_dict(x) for x in contracts],
                "consumptions": [_energy_to_dict(x) for x in energy],
                "maximeter": [_power_to_dict(x) for x in power],
                "pvpc": [_price_to_dict(x) for x in pvpc],
                "consumptions_daily_sum": [_statistics_to_dict(x) for x in daily],
                "consumptions_monthly_sum": [_statistics_to_dict(x) for x in monthly],
                "cost_hourly_sum": [_bill_to_dict(x) for x in hourly_cost],
                "cost_daily_sum": [_bill_to_dict(x) for x in daily_cost],
                "cost_monthly_sum": [_bill_to_dict(x) for x in monthly_cost],
            }
        )

        self.attributes = build_attributes(self.cups, self.data)

    async def async_recompile_statistics(
        self, date_from: datetime, date_to: datetime
    ) -> None:
        """Recompile the daily and monthly aggregates from scratch.

        Replaces the 1.x ``EdataHelper.process_data(False)``.
        """

        await self._data_service.update_statistics(date_from, date_to)

    async def async_update_costs(
        self,
        billing_rules,
        is_pvpc: bool,
        since: datetime | None = None,
        until: datetime | None = None,
        clear_first: bool = False,
    ) -> None:
        """Calculate the costs that are still missing.

        With ``clear_first``, stored bills are dropped from ``since`` onwards
        beforehand: the library keeps a hash of the rules on every bill but never
        compares it, so a pricing change would otherwise leave the old costs in
        place. Without it, the library resumes from the last stored bill, which
        is what the periodic refresh wants.
        """

        if clear_first:
            await self._bill_service.clear_bills(since)

        await self._bill_service.update(
            since, until, billing_rules=billing_rules, is_pvpc=is_pvpc
        )

    async def async_clear_costs(self, since: datetime | None = None) -> None:
        """Drop stored costs, e.g. when billing gets disabled."""

        await self._bill_service.clear_bills(since)

    async def async_wipe(self) -> None:
        """Drop every stored record of this supply, so it gets fetched again.

        The library exposes no delete API beyond ``clear_bills``, and the
        database is shared by every configured supply, so the rows of this cups
        are deleted directly through the library's own models and engine rather
        than by removing the file (which would wipe the other supplies too).

        PVPC prices are left alone: they are not supply-specific and REData only
        serves the last 28 days, so they could not be fetched again.
        """

        from sqlalchemy import delete  # noqa: PLC0415
        from sqlmodel.ext.asyncio.session import AsyncSession  # noqa: PLC0415

        from edata.database.models import (  # noqa: PLC0415
            BillModel,
            ContractModel,
            EnergyModel,
            PowerModel,
            StatisticsModel,
            SupplyModel,
        )

        _LOGGER.warning(
            "%s: wipe requested, all local data will be fetched again", self.cups
        )

        db = self._data_service.db
        # referenced tables last, so children never outlive their supply row
        models = (
            BillModel,
            StatisticsModel,
            EnergyModel,
            PowerModel,
            ContractModel,
            SupplyModel,
        )

        async with AsyncSession(db.engine) as session:
            for model in models:
                await session.exec(delete(model).where(model.cups == self.cups))
            await session.commit()

        self.data = {x: [] for x in DATA_KEYS}
        self.attributes = dict.fromkeys(const.ATTRIBUTES)
