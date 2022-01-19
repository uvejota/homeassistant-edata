from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict


class WSConsumption(TypedDict):
    """Data structure for representing consumptions in websockets"""

    datetime: str | datetime  # for backward compatibility purposes
    value_kWh: float
    value_p1_kWh: float
    value_p2_kWh: float
    value_p3_kWh: float


class WSMaxPower(TypedDict):
    """Data structure for representing max power demand (maximeter) in websockets"""

    datetime: str | datetime  # for backward compatibility purposes
    value_kW: float
    value_p1_kW: float
    value_p2_kW: float
    value_p3_kW: float


def init_consumption(datetime: str | datetime) -> WSConsumption:
    """Initializer for a WSConsumption TypedDict"""
    return WSConsumption(
        datetime=datetime, value_kWh=0, value_p1_kWh=0, value_p2_kWh=0, value_p3_kWh=0
    )


def init_maxpower(datetime: str | datetime) -> WSMaxPower:
    """Initializer for a WSMaxPower TypedDict"""
    return WSMaxPower(
        datetime=datetime, value_kW=0, value_p1_kW=0, value_p2_kW=0, value_p3_kW=0
    )
