"""Websockets related definitions."""

import datetime
import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import callback

from . import const
from .stats import (
    get_consumptions_history,
    get_costs_history,
    get_db_instance,
    get_maximeter_history,
)

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


@callback
def websocket_get_daily_data(hass, connection, msg):
    """Publish daily consumptions list data.."""
    try:
        data = hass.data[const.DOMAIN][msg["scups"].upper()].get(
            "ws_consumptions_day", []
        )
        # served data is filtered so only last 'records' records are represented
        connection.send_result(msg["id"], data[-msg.get("records", 30) :])
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].upper()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@callback
def websocket_get_monthly_data(hass, connection, msg):
    """Publish monthly consumptions list data.."""
    try:
        connection.send_result(
            msg["id"],
            hass.data[const.DOMAIN][msg["scups"].upper()].get(
                "ws_consumptions_month", []
            ),
        )
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].upper()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@callback
def websocket_get_maximeter(hass, connection, msg):
    """Publish maximeter list data.."""
    try:
        data = hass.data[const.DOMAIN][msg["scups"].upper()].get("ws_maximeter", [])
        if "tariff" in msg:
            data = [x for x in data if x[f"value_p{msg['tariff']}_kW"] > 0]
        connection.send_result(msg["id"], data)
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].upper()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/consumptions",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "5minute", "day", "hour", "week", "month"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union("p1", "p2", "p3"),
    }
)
@websocket_api.async_response
async def ws_get_consumption(hass, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]

    data = await get_consumptions_history(hass, _scups, _tariff, _aggr, _records)
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/costs",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "5minute", "day", "hour", "week", "month"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union("p1", "p2", "p3"),
    }
)
@websocket_api.async_response
async def ws_get_cost(hass, connection, msg):
    """Fetch costs history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]

    data = await get_costs_history(hass, _scups, _tariff, _aggr, _records)
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/maximeter",
        vol.Required("scups"): str,
        vol.Optional("tariff"): vol.Union("p1", "p2"),
    }
)
@websocket_api.async_response
async def ws_get_maximeter(hass, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()
    _tariff = None if "tariff" not in msg else msg["tariff"]

    data = await get_maximeter_history(hass, _scups, _tariff)
    connection.send_result(msg["id"], data)


def async_register_websockets(hass):
    """Register websockets into HA API."""

    ## v1
    # for daily consumptions
    hass.components.websocket_api.async_register_command(
        f"{const.DOMAIN}/consumptions/daily",
        websocket_get_daily_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/consumptions/daily",
                vol.Required("scups"): str,
                vol.Optional("records"): int,
            }
        ),
    )

    # for monthly consumptions
    hass.components.websocket_api.async_register_command(
        f"{const.DOMAIN}/consumptions/monthly",
        websocket_get_monthly_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/consumptions/monthly",
                vol.Required("scups"): str,
            }
        ),
    )

    # for maximeter
    hass.components.websocket_api.async_register_command(
        f"{const.DOMAIN}/maximeter",
        websocket_get_maximeter,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/maximeter",
                vol.Required("scups"): str,
                vol.Optional("tariff"): int,
            }
        ),
    )

    ## v2:
    hass.components.websocket_api.async_register_command(ws_get_consumption)
    hass.components.websocket_api.async_register_command(ws_get_cost)
    hass.components.websocket_api.async_register_command(ws_get_maximeter)
