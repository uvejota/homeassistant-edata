"""Data structures definitions"""
from __future__ import annotations

from typing import TypedDict


class PricingRules(TypedDict):
    """Data structure to represent custom pricing rules"""

    p1_kw_year_eur: float
    p2_kw_year_eur: float
    p1_kwh_eur: float
    p2_kwh_eur: float
    p3_kwh_eur: float
    meter_month_eur: float
    market_kw_year_eur: float
    electricity_tax: float
    iva_tax: float


class WSCost(TypedDict):
    """Data structure for representing costs"""

    power_term: float
    energy_term: float
    value_eur: float


def calculate_cost(
    rules: PricingRules, power_limit: list[float], consumption: list[float]
):
    """Calculates 2.0TD electricity hourly cost by considering rules, contract power limits and consumed energy"""
    cost = WSCost(
        power_term=(
            power_limit[0] * (rules["p1_kw_year_eur"] + rules["market_kw_year_eur"])
            + power_limit[1] * (rules["p2_kw_year_eur"])
        )
        * rules["electricity_tax"]
        * rules["iva_tax"]
        / 365
        / 24,
        energy_term=(
            consumption[0] * rules["p1_kwh_eur"]
            + consumption[1] * rules["p2_kwh_eur"]
            + consumption[2] * rules["p3_kwh_eur"]
        )
        * rules["electricity_tax"]
        * rules["iva_tax"],
        value_eur=0,
    )
    cost["value_eur"] = (
        cost["power_term"] + cost["energy_term"] + rules["meter_month_eur"] / 30 / 24
    )
    return cost
