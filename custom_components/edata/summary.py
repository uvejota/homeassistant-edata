"""Summary attributes for the edata sensors, websockets and Lovelace card.

The 1.x library published these through ``EdataHelper.attributes``. The 2.x
library dropped the concept entirely, so they are computed here from the
legacy-shaped lists built by :mod:`.edata_api`.

The arithmetic is a transcription of the 1.2.22 implementation
(``edata/helpers.py`` ``process_*`` methods plus ``MaximeterProcessor``) so that
every attribute keeps the exact name, meaning and rounding it had before.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math

from dateutil.relativedelta import relativedelta

from . import const

_LOGGER = logging.getLogger(__name__)

TARIFFS = (1, 2, 3)


def _get_by_key(items: list[dict], key: str, value) -> dict | None:
    """Return the first element of a list of dicts where element[key] == value."""

    for item in items:
        if item.get(key) == value:
            return item

    return None


def _percentile(values: list[float], percent: float) -> float | None:
    """Return the linear-interpolated percentile of a list of values.

    Unlike the 1.x helper this sorts first: the old one indexed the list in
    chronological order, so 'max_power_90perc_kW' was not actually a percentile.
    """

    if not values:
        return None

    ordered = sorted(values)
    k = (len(ordered) - 1) * percent
    floor = math.floor(k)
    ceil = math.ceil(k)
    if floor == ceil:
        return ordered[int(k)]

    return ordered[floor] * (ceil - k) + ordered[ceil] * (k - floor)


def _daily_attributes(prefix: str, row: dict | None, attributes: dict) -> None:
    """Fill the '<prefix>_*' attributes from a daily-sum row."""

    attributes[f"{prefix}_kWh"] = row.get("value_kWh") if row is not None else None
    attributes[f"{prefix}_surplus_kWh"] = (
        row.get("surplus_kWh") if row is not None else None
    )
    attributes[f"{prefix}_hours"] = row.get("delta_h") if row is not None else None

    for tariff in TARIFFS:
        attributes[f"{prefix}_p{tariff}_kWh"] = (
            row.get(f"value_p{tariff}_kWh") if row is not None else None
        )
        attributes[f"{prefix}_surplus_p{tariff}_kWh"] = (
            row.get(f"surplus_p{tariff}_kWh") if row is not None else None
        )


def _monthly_attributes(prefix: str, row: dict | None, attributes: dict) -> None:
    """Fill the '<prefix>_*' attributes from a monthly-sum row."""

    attributes[f"{prefix}_kWh"] = row.get("value_kWh") if row is not None else None
    attributes[f"{prefix}_surplus_kWh"] = (
        row.get("surplus_kWh") if row is not None else None
    )
    attributes[f"{prefix}_days"] = (
        row.get("delta_h", 0) / 24 if row is not None else None
    )

    days = attributes[f"{prefix}_days"]
    total = attributes[f"{prefix}_kWh"]
    if row is None or total is None:
        attributes[f"{prefix}_daily_kWh"] = None
    else:
        attributes[f"{prefix}_daily_kWh"] = (total / days) if days > 0 else 0

    for tariff in TARIFFS:
        attributes[f"{prefix}_p{tariff}_kWh"] = (
            row.get(f"value_p{tariff}_kWh") if row is not None else None
        )
        attributes[f"{prefix}_surplus_p{tariff}_kWh"] = (
            row.get(f"surplus_p{tariff}_kWh") if row is not None else None
        )


def build_attributes(cups: str, data: dict[str, list[dict]]) -> dict:
    """Build the whole summary attributes dict out of legacy-shaped data."""

    attributes = dict.fromkeys(const.ATTRIBUTES)

    consumptions = data.get("consumptions") or []
    daily = data.get("consumptions_daily_sum") or []
    monthly = data.get("consumptions_monthly_sum") or []
    maximeter = data.get("maximeter") or []
    contracts = data.get("contracts") or []
    cost_monthly = data.get("cost_monthly_sum") or []

    attributes["cups"] = cups

    if contracts:
        attributes["contract_p1_kW"] = contracts[-1].get("power_p1")
        attributes["contract_p2_kW"] = contracts[-1].get("power_p2")

    today = datetime.today()
    today_starts = datetime(today.year, today.month, today.day, 0, 0, 0)
    month_starts = datetime(today.year, today.month, 1, 0, 0, 0)

    if consumptions:
        _daily_attributes(
            "yesterday",
            _get_by_key(daily, "datetime", today_starts - timedelta(days=1)),
            attributes,
        )

        _monthly_attributes(
            "month", _get_by_key(monthly, "datetime", month_starts), attributes
        )
        _monthly_attributes(
            "last_month",
            _get_by_key(monthly, "datetime", month_starts - relativedelta(months=1)),
            attributes,
        )

        attributes["last_registered_date"] = consumptions[-1]["datetime"]
        if daily:
            _daily_attributes("last_registered_day", daily[-1], attributes)

    if maximeter:
        values = [x["value_kW"] for x in maximeter]
        max_kw = max(values)
        attributes["max_power_kW"] = max_kw
        attributes["max_power_date"] = maximeter[values.index(max_kw)]["datetime"]
        attributes["max_power_mean_kW"] = sum(values) / len(values)
        attributes["max_power_90perc_kW"] = _percentile(values, 0.9)

    this_month_cost = _get_by_key(cost_monthly, "datetime", month_starts)
    if this_month_cost is not None:
        attributes["month_€"] = this_month_cost.get("value_eur")

    last_month_cost = _get_by_key(
        cost_monthly, "datetime", month_starts - relativedelta(months=1)
    )
    if last_month_cost is not None:
        attributes["last_month_€"] = last_month_cost.get("value_eur")

    # the 1.x library rounded every numeric attribute to two decimals
    for key, value in attributes.items():
        if isinstance(value, float):
            attributes[key] = round(value, 2)

    return attributes
