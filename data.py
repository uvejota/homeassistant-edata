"""Data structures definitions"""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict


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


# Initializer for a WSConsumption TypedDict
init_consumption = lambda dt: WSConsumption(
    datetime=dt, value_kWh=0, value_p1_kWh=0, value_p2_kWh=0, value_p3_kWh=0
)

# Initializer for a WSMaxPower TypedDict
init_maxpower = lambda dt: WSMaxPower(
    datetime=dt, value_kW=0, value_p1_kW=0, value_p2_kW=0, value_p3_kW=0
)
