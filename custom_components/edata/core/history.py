"""History utilities for retrieving recent consumption and surplus data."""

from datetime import datetime, timedelta
import typing

from dateutil.relativedelta import relativedelta
from edata.core.utils import get_tariff

from .data import DataManager


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
    """Get recent consumption data as a list of tuples (timestamp, value_kWh)."""
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
        result = [
            (energy.datetime.timestamp(), energy.value_kWh)
            for energy in energy_data
            if tariff is None or get_tariff(energy.datetime) == tariff
        ]
        return _sort_and_limit_results(result, records)

    # For day or month aggregation, use statistics
    stats = await data_manager.get_aggr_energy(
        aggregation=aggr,
        start=start_date,
        end=ref_date,
    )

    result = []
    for stat in stats:
        timestamp = stat.datetime.timestamp()
        # Extract value based on tariff period
        if tariff == 1:
            value = stat.value_p1_kWh
        elif tariff == 2:
            value = stat.value_p2_kWh
        elif tariff == 3:
            value = stat.value_p3_kWh
        else:
            # No tariff specified, use total value
            value = stat.value_kWh
        result.append((timestamp, value))

    return _sort_and_limit_results(result, records)


async def get_recent_surplus(
    data_manager: DataManager,
    aggr: typing.Literal["hour", "day", "month"],
    records: int,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent surplus data as a list of tuples (timestamp, surplus_kWh)."""
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
        result = [
            (energy.datetime.timestamp(), energy.surplus_kWh)
            for energy in energy_data
            if tariff is None or get_tariff(energy.datetime) == tariff
        ]
        return _sort_and_limit_results(result, records)

    # For day or month aggregation, use statistics
    stats = await data_manager.get_aggr_energy(
        aggregation=aggr,
        start=start_date,
        end=ref_date,
    )

    result = []
    for stat in stats:
        timestamp = stat.datetime.timestamp()
        # Extract surplus value based on tariff period
        if tariff == 1:
            value = stat.surplus_p1_kWh
        elif tariff == 2:
            value = stat.surplus_p2_kWh
        elif tariff == 3:
            value = stat.surplus_p3_kWh
        else:
            # No tariff specified, use total surplus
            value = stat.surplus_kWh
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

    result = [(bill.datetime.timestamp(), bill.value_eur) for bill in bills]

    return _sort_and_limit_results(result, records)


async def get_recent_maximeter(
    data_manager: DataManager,
    months: int = 12,
    tariff: int | None = None,
    now_as_ref: bool = False,
) -> list[tuple[float, float]]:
    """Get recent maximeter data as a list of tuples (timestamp, max_power_kW)."""
    # Get reference date
    most_recent = await data_manager.get_most_recent_energy_dt()
    ref_date = _get_reference_date(most_recent, now_as_ref)
    if ref_date is None:
        return []

    # Calculate start date (approximate: 30 days per month)
    start_date = ref_date - relativedelta(months=months)

    # Get power data
    power_data = await data_manager.get_power(start=start_date, end=ref_date)

    result = [
        (power.datetime.timestamp(), power.value_kW)
        for power in power_data
        if tariff is None or get_tariff(power.datetime) == tariff
    ]

    # Sort by timestamp
    result.sort(key=lambda x: x[0])
    return result
