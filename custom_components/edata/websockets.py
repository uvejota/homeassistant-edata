"""Websockets related definitions."""

import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from . import const
from .stats import (
    get_consumptions_history,
    get_costs_history,
    get_maximeter_history,
    get_surplus_history,
)

_LOGGER = logging.getLogger(__name__)


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
async def ws_get_consumptions(hass: HomeAssistant, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]

    try:
        data = await get_consumptions_history(hass, _scups, _tariff, _aggr, _records)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/surplus",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union(
            "5minute", "day", "hour", "week", "month"
        ),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union("p1", "p2", "p3"),
    }
)
@websocket_api.async_response
async def ws_get_surplus(hass: HomeAssistant, connection, msg):
    """Fetch surplus history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]

    try:
        data = await get_surplus_history(hass, _scups, _tariff, _aggr, _records)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
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
async def ws_get_cost(hass: HomeAssistant, connection, msg):
    """Fetch costs history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _tariff = None if "tariff" not in msg else msg["tariff"]

    try:
        data = await get_costs_history(hass, _scups, _tariff, _aggr, _records)
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/maximeter",
        vol.Required("scups"): str,
        vol.Optional("tariff"): vol.Union("p1", "p2"),
    }
)
@websocket_api.async_response
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


def async_register_websockets(hass: HomeAssistant):
    """Register websockets into HA API."""

    ## v2:
    hass.components.websocket_api.async_register_command(ws_get_consumptions)
    hass.components.websocket_api.async_register_command(ws_get_surplus)
    hass.components.websocket_api.async_register_command(ws_get_cost)
    hass.components.websocket_api.async_register_command(ws_get_maximeter)
