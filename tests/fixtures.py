"""Shared fixture data and fakes for the edata integration tests."""

from datetime import datetime, timedelta
import typing

from edata.models import Bill, Contract, Energy, Power, Statistics, Supply
from edata.models.bill import BillingRules

CUPS = "ES0021000000000000AA0A"
SCUPS = "aa0a"
USERNAME = "12345678Z"
PASSWORD = "secret"

# A fixed reference so snapshots stay deterministic.
BASE_DT = datetime(2023, 1, 1, 0, 0)


def build_supply() -> Supply:
    """Build a single fake supply."""
    return Supply(
        cups=CUPS,
        date_start=BASE_DT,
        date_end=BASE_DT + timedelta(days=60),
        address="FAKE STREET 1",
        postal_code="00000",
        province="FAKE",
        municipality="FAKETOWN",
        distributor="FAKE ENERGY",
        point_type=5,
        distributor_code="2",
    )


def build_contracts() -> list[Contract]:
    """Build a single fake contract with two power periods."""
    return [
        Contract(
            date_start=BASE_DT,
            date_end=BASE_DT + timedelta(days=60),
            marketer="FAKE MARKETER",
            distributor_code="2",
            power=[4.4, 4.4],
        )
    ]


def build_energy(hours: int = 48) -> list[Energy]:
    """Build a deterministic list of hourly energy records."""
    return [
        Energy(
            datetime=BASE_DT + timedelta(hours=i),
            delta_h=1.0,
            consumption_kwh=round(0.1 * (i % 24) + 0.05, 3),
            surplus_kwh=round(0.01 * (i % 12), 3),
            generation_kwh=0.0,
            selfconsumption_kwh=0.0,
            real=True,
        )
        for i in range(hours)
    ]


def build_power(count: int = 6) -> list[Power]:
    """Build a deterministic list of maximeter records."""
    return [
        Power(
            datetime=BASE_DT + timedelta(days=i * 10),
            value_kw=round(3.0 + 0.1 * i, 2),
        )
        for i in range(count)
    ]


def build_daily_stats(days: int = 3) -> list[Statistics]:
    """Build deterministic daily statistics."""
    return [
        Statistics(
            datetime=BASE_DT + timedelta(days=i),
            delta_h=24.0,
            consumption_kwh=round(5.0 + i, 3),
            consumption_by_tariff=[round(2.0 + i, 3), 2.0, 1.0],
            surplus_kwh=round(0.5 + 0.1 * i, 3),
            surplus_by_tariff=[0.2, 0.2, round(0.1 + 0.1 * i, 3)],
        )
        for i in range(days)
    ]


def build_monthly_stats(months: int = 2) -> list[Statistics]:
    """Build deterministic monthly statistics."""
    return [
        Statistics(
            datetime=datetime(2023, 1 + i, 1),
            delta_h=720.0,
            consumption_kwh=round(150.0 + 10 * i, 3),
            consumption_by_tariff=[round(60.0 + 5 * i, 3), 50.0, 40.0],
            surplus_kwh=round(5.0 + i, 3),
            surplus_by_tariff=[2.0, 2.0, round(1.0 + i, 3)],
        )
        for i in range(months)
    ]


def build_monthly_bills(months: int = 2) -> list[Bill]:
    """Build deterministic monthly bills."""
    return [
        Bill(
            datetime=datetime(2023, 1 + i, 1),
            delta_h=720.0,
            value_eur=round(50.0 + 5 * i, 3),
            energy_term=round(35.0 + 3 * i, 3),
            power_term=round(14.0 + i, 3),
            others_term=1.0,
            surplus_term=0.0,
        )
        for i in range(months)
    ]


def default_billing_rules() -> BillingRules:
    """Return custom (non-PVPC) billing rules for tests."""
    return BillingRules(
        p1_kwh_eur=0.20,
        p2_kwh_eur=0.20,
        p3_kwh_eur=0.20,
        p1_kw_year_eur=20,
        p2_kw_year_eur=10,
    )


class FakeDataManager:
    """In-memory stand-in for the DataManager used across HA-level tests."""

    def __init__(self, *_args: typing.Any, billing: BillingRules | None = None, **_kw):
        """Store the billing rules and preload deterministic data."""
        self.billing = billing
        self.synced = 0
        self.rebuilt: list[datetime | None] = []
        self._supply = build_supply()
        self._contracts = build_contracts()
        self._energy = build_energy()
        self._power = build_power()
        self._daily = build_daily_stats()
        self._monthly = build_monthly_stats()
        self._bills = build_monthly_bills()

    async def sync(self) -> None:
        """Record that a sync happened."""
        self.synced += 1

    async def rebuild_billing(self, since: datetime | None = None) -> None:
        """Record a billing rebuild request."""
        self.rebuilt.append(since)

    async def simulate_last_month(self, billing_rules, is_pvpc) -> Bill:
        """Return a deterministic preview bill."""
        return self._bills[-1]

    async def get_supply(self) -> Supply:
        """Return the fake supply."""
        return self._supply

    async def get_contracts(self) -> list[Contract]:
        """Return the fake contracts."""
        return self._contracts

    async def get_energy(self, start=None, end=None) -> list[Energy]:
        """Return the fake energy records within the range."""
        return [x for x in self._energy if _in_range(x.datetime, start, end)]

    async def get_most_recent_energy_dt(self) -> datetime:
        """Return the last energy timestamp."""
        return self._energy[-1].datetime

    async def get_power(self, start=None, end=None) -> list[Power]:
        """Return the fake power records within the range."""
        return [x for x in self._power if _in_range(x.datetime, start, end)]

    async def get_bills(self, start=None, end=None) -> list[Bill]:
        """Return the fake bills within the range."""
        return [x for x in self._bills if _in_range(x.datetime, start, end)]

    async def get_aggr_energy(self, aggregation, start=None, end=None):
        """Return the fake aggregated energy statistics."""
        source = self._daily if aggregation == "day" else self._monthly
        return [x for x in source if _in_range(x.datetime, start, end)]

    async def get_aggr_bills(self, aggregation, start=None, end=None) -> list[Bill]:
        """Return the fake aggregated bills."""
        return [x for x in self._bills if _in_range(x.datetime, start, end)]


def _in_range(dt: datetime, start: datetime | None, end: datetime | None) -> bool:
    """Return whether dt lies within the optional [start, end] range."""
    if start is not None and dt < _naive(start):
        return False
    if end is not None and dt > _naive(end):
        return False
    return True


def _naive(dt: datetime) -> datetime:
    """Drop tzinfo so comparisons with naive fixture datetimes work."""
    return dt.replace(tzinfo=None)
