"""History utilities for retrieving recent consumption and surplus data."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import typing

from dateutil.relativedelta import relativedelta

from edata.core.utils import get_tariff

from .data import DataManager


def _filter_by_tariff(
    items: list,
    value_getter: Callable[[typing.Any], float],
    tariff: int | None,
) -> list[tuple[float, float]]:
    """Build (timestamp_ms, value) tuples, keeping only rows matching tariff.

    Runs off the event loop: get_tariff resolves ES holidays synchronously.
    """
    return [
        (item.datetime.timestamp() * 1000, value_getter(item))
        for item in items
        if tariff is None or get_tariff(item.datetime) == tariff
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


async def get_recent_consumptions(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent consumption data as a list of tuples (timestamp, consumption_kwh)."""
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return []

    # Calculate start date
    start_date = _calculate_start_date(ref_date, aggr, records)

    # For hourly data, use raw energy data
    if aggr == "hour":
        energy_data = await data_manager.get_energy(start=start_date, end=ref_date)
        result = await asyncio.to_thread(
            _filter_by_tariff, energy_data, lambda e: e.consumption_kwh, tariff
        )
        return _sort_and_limit_results(result, records)

    # For day or month aggregation, use statistics
    stats = await data_manager.get_aggr_energy(
        aggregation=aggr,
        start=start_date,
        end=ref_date,
    )

    result = []
    for stat in stats:
        timestamp = stat.datetime.timestamp() * 1000
        # Extract value based on tariff period
        if tariff == 1:
            value = stat.consumption_p1_kwh
        elif tariff == 2:
            value = stat.consumption_p2_kwh
        elif tariff == 3:
            value = stat.consumption_p3_kwh
        else:
            # No tariff specified, use total value
            value = stat.consumption_kwh
        result.append((timestamp, value))

    return _sort_and_limit_results(result, records)


async def get_recent_surplus(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent surplus data as a list of tuples (timestamp, surplus_kwh)."""
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return []

    # Calculate start date
    start_date = _calculate_start_date(ref_date, aggr, records)

    # For hourly data, use raw energy data
    if aggr == "hour":
        energy_data = await data_manager.get_energy(start=start_date, end=ref_date)
        result = await asyncio.to_thread(
            _filter_by_tariff, energy_data, lambda e: e.surplus_kwh, tariff
        )
        return _sort_and_limit_results(result, records)

    # For day or month aggregation, use statistics
    stats = await data_manager.get_aggr_energy(
        aggregation=aggr,
        start=start_date,
        end=ref_date,
    )

    result = []
    for stat in stats:
        timestamp = stat.datetime.timestamp() * 1000
        # Extract surplus value based on tariff period
        if tariff == 1:
            value = stat.surplus_p1_kwh
        elif tariff == 2:
            value = stat.surplus_p2_kwh
        elif tariff == 3:
            value = stat.surplus_p3_kwh
        else:
            # No tariff specified, use total surplus
            value = stat.surplus_kwh
        result.append((timestamp, value))

    return _sort_and_limit_results(result, records)


async def get_recent_bills(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent bill data as a list of tuples (timestamp, value_eur)."""
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return []

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

    result = [(bill.datetime.timestamp() * 1000, bill.value_eur) for bill in bills]

    return _sort_and_limit_results(result, records)


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

    result = await asyncio.to_thread(
        _filter_by_tariff, power_data, lambda p: p.value_kw, tariff
    )

    result.sort(key=lambda x: x[0])
    return result
