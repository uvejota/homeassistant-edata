"""History utilities for retrieving recent consumption and surplus data."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import typing

from dateutil.relativedelta import relativedelta

from edata.core.utils import get_tariff

from .data import DataManager


def _split_by_tariff(
    items: list,
    value_getter: Callable[[typing.Any], float],
    tariffs: list[int | None],
) -> list[list[tuple[float, float]]]:
    """Build one list of (timestamp_ms, value) tuples per requested tariff.

    ``None`` keeps every row. Each row's tariff is resolved once, however many
    tariffs are requested. Runs off the event loop: get_tariff resolves ES
    holidays synchronously.
    """
    split = any(tariff is not None for tariff in tariffs)
    rows = [
        (
            item.datetime.timestamp() * 1000,
            get_tariff(item.datetime) if split else None,
            value_getter(item),
        )
        for item in items
    ]
    return [
        [(ts, value) for ts, row_tariff, value in rows if tariff in (None, row_tariff)]
        for tariff in tariffs
    ]


def _get_reference_date(
    ref_date: datetime | None,
    now_as_ref: bool,
) -> datetime | None:
    """Calculate reference date for data queries."""
    if now_as_ref:
        return datetime.now()
    return ref_date


def _calculate_start_date(
    ref_date: datetime,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
) -> datetime:
    """Calculate start date based on aggregation type and number of records."""
    ref_date = ref_date.replace(minute=0, second=0, microsecond=0)
    if aggr == "hour":
        return ref_date - timedelta(hours=records)
    if aggr == "day":
        ref_date = ref_date.replace(hour=0)
        return ref_date - relativedelta(days=records)
    # month
    ref_date = ref_date.replace(day=1, hour=0)
    return ref_date - relativedelta(months=records)


def _sort_and_limit_results(
    result: list[tuple[float, float]],
    records: int,
) -> list[tuple[float, float]]:
    """Sort results by timestamp and limit to requested number of records."""
    result.sort(key=lambda x: x[0])
    return result[-records:] if len(result) > records else result


async def get_recent_energy_series(
    data_manager: DataManager,
    kind: typing.Literal["consumption", "surplus"],
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariffs: list[int | None],
    now_as_ref: bool = False,
) -> list[list[tuple[float, float]]]:
    """Get one (timestamp, kWh) series per tariff from a single read.

    A ``None`` tariff gives the total.
    """
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return [[] for _ in tariffs]

    # Calculate start date
    start_date = _calculate_start_date(ref_date, aggr, records)

    # For hourly data, use raw energy data
    if aggr == "hour":
        energy_data = await data_manager.get_energy(start=start_date, end=ref_date)
        series = await asyncio.to_thread(
            _split_by_tariff,
            energy_data,
            lambda e: getattr(e, f"{kind}_kwh"),
            tariffs,
        )
    else:
        # For day or month aggregation, use statistics
        stats = await data_manager.get_aggr_energy(
            aggregation=aggr,
            start=start_date,
            end=ref_date,
        )
        series = []
        for tariff in tariffs:
            field = f"{kind}_p{tariff}_kwh" if tariff else f"{kind}_kwh"
            series.append(
                [
                    (stat.datetime.timestamp() * 1000, getattr(stat, field))
                    for stat in stats
                ]
            )

    return [_sort_and_limit_results(result, records) for result in series]


async def get_recent_consumptions(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent consumption data as a list of tuples (timestamp, consumption_kwh)."""
    series = await get_recent_energy_series(
        data_manager, "consumption", aggr, records, [tariff], now_as_ref
    )
    return series[0]


async def get_recent_surplus(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent surplus data as a list of tuples (timestamp, surplus_kwh)."""
    series = await get_recent_energy_series(
        data_manager, "surplus", aggr, records, [tariff], now_as_ref
    )
    return series[0]


BILL_TERMS = {
    "energy": "energy_term",
    "power": "power_term",
    "others": "others_term",
}


async def get_recent_bill_series(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    terms: list[typing.Literal["energy", "power", "others"] | None],
    now_as_ref: bool = False,
) -> list[list[tuple[float, float]]]:
    """Get one (timestamp, EUR) series per bill term from a single read.

    A ``None`` term gives the total; the three terms add up to it.
    """
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return [[] for _ in terms]

    # Calculate start date
    start_date = _calculate_start_date(ref_date, aggr, records)

    # For hourly data, use raw bill data
    if aggr == "hour":
        bills = await data_manager.get_bills(start=start_date, end=ref_date)
    else:
        # For day or month aggregation, use aggregated bills
        bills = await data_manager.get_aggr_bills(
            aggregation=aggr,
            start=start_date,
            end=ref_date,
        )

    series = []
    for term in terms:
        field = BILL_TERMS[term] if term else "value_eur"
        result = [
            (bill.datetime.timestamp() * 1000, getattr(bill, field)) for bill in bills
        ]
        series.append(_sort_and_limit_results(result, records))
    return series


async def get_recent_bills(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    term: typing.Literal["energy", "power", "others"] | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent bill data as a list of tuples (timestamp, value_eur).

    With ``term``, return only that bill term (energy, power or others); the
    three add up to the total.
    """
    series = await get_recent_bill_series(
        data_manager, aggr, records, [term], now_as_ref
    )
    return series[0]


async def get_recent_maximeter(
    data_manager: DataManager,
    months: int = 12,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent maximeter data as a list of tuples (timestamp, max_power_kw)."""
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return []

    # Calculate start date (approximate: 30 days per month)
    start_date = ref_date - relativedelta(months=months)

    # Get power data
    power_data = await data_manager.get_power(start=start_date, end=ref_date)

    (result,) = await asyncio.to_thread(
        _split_by_tariff, power_data, lambda p: p.value_kw, [tariff]
    )

    result.sort(key=lambda x: x[0])
    return result
