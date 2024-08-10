"""Websockets related definitions."""

import logging

import voluptuous as vol

from homeassistant.components.websocket_api import (
    BASE_COMMAND_MESSAGE_SCHEMA,
    async_register_command,
    async_response,
    websocket_command,
)
from homeassistant.core import HomeAssistant, callback

from . import const
from .utils import (
    get_consumptions_history,
    get_costs_history,
    get_maximeter_history,
    get_surplus_history,
    get_attributes,
)

_LOGGER = logging.getLogger(__name__)


@callback
def websocket_get_daily_data(hass: HomeAssistant, connection, msg):
    """Publish daily consumptions list data.."""
    try:
        data = hass.data[const.DOMAIN][msg["scups"].lower()].get(
            "ws_consumptions_day", []
        )
        # served data is filtered so only last 'records' records are represented
        connection.send_result(msg["id"], data[-msg.get("records", 30) :])
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].lower()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@callback
def websocket_get_monthly_data(hass: HomeAssistant, connection, msg):
    """Publish monthly consumptions list data.."""
    try:
        connection.send_result(
            msg["id"],
            hass.data[const.DOMAIN][msg["scups"].lower()].get(
                "ws_consumptions_month", []
            ),
        )
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].lower()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@callback
def websocket_get_maximeter(hass: HomeAssistant, connection, msg):
    """Publish maximeter list data.."""
    try:
        data = hass.data[const.DOMAIN][msg["scups"].lower()].get("ws_maximeter", [])
        if "tariff" in msg:
            data = [x for x in data if x[f"value_p{msg['tariff']}_kW"] > 0]
        connection.send_result(msg["id"], data)
    except KeyError as _:
        _LOGGER.error(
            "The provided scups parameter is not correct: %s", msg["scups"].lower()
        )
    except Exception as _:
        _LOGGER.exception("Unhandled exception when processing websockets: %s", _)
        connection.send_result(msg["id"], [])


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/consumptions",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "day", "hour", "week", "month", "year"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union("p1", "p2", "p3"),
        vol.Optional("from_now"): bool,
    }
)
@async_response
async def ws_get_consumptions(hass: HomeAssistant, connection, msg):
    """Fetch consumptions history."""

    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = msg.get("tariff", None)
    _now_as_ref = msg.get("from_now", False)

    try:
        data = await get_consumptions_history(
            hass, _scups, _tariff, _aggr, _records, now_as_ref=_now_as_ref
        )
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/surplus",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "day", "hour", "week", "month", "year"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("from_now"): bool,
    }
)
@async_response
async def ws_get_surplus(hass: HomeAssistant, connection, msg):
    """Fetch surplus history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _now_as_ref = msg.get("from_now", False)

    try:
        data = await get_surplus_history(hass, _scups, _aggr, _records, _now_as_ref)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/costs",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "day", "hour", "week", "month", "year"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union("p1", "p2", "p3"),
        vol.Optional("from_now"): bool,
    }
)
@async_response
async def ws_get_cost(hass: HomeAssistant, connection, msg):
    """Fetch costs history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]
    _now_as_ref = msg.get("from_now", False)

    try:
        data = await get_costs_history(hass, _scups, _tariff, _aggr, _records)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/maximeter",
        vol.Required("scups"): str,
        vol.Optional("tariff"): vol.Union("p1", "p2"),
    }
)
@async_response
async def ws_get_maximeter(hass: HomeAssistant, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()
    _tariff = None if "tariff" not in msg else msg["tariff"]

    try:
        data = await get_maximeter_history(hass, _scups, _tariff)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/summary",
        vol.Required("scups"): str,
    }
)
@async_response
async def ws_get_summary(hass: HomeAssistant, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()

    try:
        data = await get_attributes(hass, _scups)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


def async_register_websockets(hass: HomeAssistant):
    """Register websockets into HA API."""

    ## v1
    # for daily consumptions
    async_register_command(
        hass,
        f"{const.DOMAIN}/consumptions/daily",
        websocket_get_daily_data,
        BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/consumptions/daily",
                vol.Required("scups"): str,
                vol.Optional("records"): int,
            }
        ),
    )

    # for monthly consumptions
    async_register_command(
        hass,
        f"{const.DOMAIN}/consumptions/monthly",
        websocket_get_monthly_data,
        BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/consumptions/monthly",
                vol.Required("scups"): str,
            }
        ),
    )

    # for maximeter
    async_register_command(
        hass,
        f"{const.DOMAIN}/maximeter",
        websocket_get_maximeter,
        BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{const.DOMAIN}/maximeter",
                vol.Required("scups"): str,
                vol.Optional("tariff"): int,
            }
        ),
    )

    ## v2:
    async_register_command(hass, ws_get_consumptions)
    async_register_command(hass, ws_get_surplus)
    async_register_command(hass, ws_get_cost)
    async_register_command(hass, ws_get_maximeter)
    async_register_command(hass, ws_get_summary)
