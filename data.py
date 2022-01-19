from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict


class Consumption(TypedDict):
    """Data structure for consumptions in websockets"""

    datetime: str | datetime  # for backward compatibility purposes
    value_kWh: float
    value_p1_kWh: float
    value_p2_kWh: float
    value_p3_kWh: float


class MaxPower(TypedDict):
    """Data structure for max power demand (maximeter) in websockets"""

    datetime: str | datetime  # for backward compatibility purposes
    value_kW: float
    value_p1_kW: float
    value_p2_kW: float
    value_p3_kW: float


def zero_consumption(datetime: str | datetime) -> Consumption:
    return Consumption(
        datetime=datetime, value_kWh=0, value_p1_kWh=0, value_p2_kWh=0, value_p3_kWh=0
    )


def zero_maxpower(datetime: str | datetime) -> MaxPower:
    return MaxPower(
        datetime=datetime, value_kW=0, value_p1_kW=0, value_p2_kW=0, value_p3_kW=0
    )
