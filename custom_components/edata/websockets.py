"""Websockets related definitions."""

import logging

import voluptuous as vol

from homeassistant.components.websocket_api import (
    async_register_command,
    async_response,
    websocket_command,
)
from homeassistant.core import HomeAssistant

from . import const
from .core import history as edata_history
from .core.data import DataManager

_LOGGER = logging.getLogger(__name__)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/consumptions",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union("day", "hour", "month"),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union(1, 2, 3),
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

    data_manager: DataManager | None = hass.data[const.DOMAIN][_scups].get(
        const.SHARED_DATAMANAGER
    )
    if data_manager is None:
        _LOGGER.info("No data manager found for CUPS %s", _scups)
        connection.send_result(msg["id"], [])
        return

    data = await edata_history.get_recent_consumptions(
        data_manager,
        aggr=_aggr,
        records=_records,
        tariff=_tariff,
        now_as_ref=_now_as_ref,
    )
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/surplus",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union("day", "hour", "month"),
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
    data_manager: DataManager | None = hass.data[const.DOMAIN][_scups].get(
        const.SHARED_DATAMANAGER
    )
    if data_manager is None:
        _LOGGER.info("No data manager found for CUPS %s", _scups)
        connection.send_result(msg["id"], [])
        return
    try:
        data = await edata_history.get_recent_surplus(
            data_manager,
            aggr=_aggr,
            records=_records,
            now_as_ref=_now_as_ref,
        )
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/costs",
        vol.Required("scups"): str,
        vol.Optional("aggr", default="day"): vol.Union("day", "hour", "month"),
        vol.Optional("records", default=30): int,
        vol.Optional("tariff"): vol.Union(1, 2, 3),
        vol.Optional("from_now"): bool,
    }
)
@async_response
async def ws_get_cost(hass: HomeAssistant, connection, msg):
    """Fetch costs history."""
    _scups = msg["scups"].lower()
    _aggr = msg["aggr"]
    _records = msg["records"]
    _now_as_ref = msg.get("from_now", False)
    data_manager: DataManager | None = hass.data[const.DOMAIN][_scups].get(
        const.SHARED_DATAMANAGER
    )
    if data_manager is None:
        _LOGGER.info("No data manager found for CUPS %s", _scups)
        connection.send_result(msg["id"], [])
        return
    try:
        data = await edata_history.get_recent_bills(
            data_manager,
            aggr=_aggr,
            records=_records,
            now_as_ref=_now_as_ref,
        )
    except KeyError:
        data = []
        _LOGGER.info("Stats not found for CUPS %s", _scups)
    connection.send_result(msg["id"], data)


@websocket_command(
    {
        vol.Required("type"): f"{const.DOMAIN}/ws/maximeter",
        vol.Required("scups"): str,
        vol.Optional("tariff"): vol.Union(1, 2),
    }
)
@async_response
async def ws_get_maximeter(hass: HomeAssistant, connection, msg):
    """Fetch consumptions history."""
    _scups = msg["scups"].lower()
    _tariff = msg.get("tariff")
    data_manager: DataManager | None = hass.data[const.DOMAIN][_scups].get(
        const.SHARED_DATAMANAGER
    )
    if data_manager is None:
        _LOGGER.info("No data manager found for CUPS %s", _scups)
        connection.send_result(msg["id"], [])
        return
    try:
        data = await edata_history.get_recent_maximeter(
            data_manager,
            tariff=_tariff,
        )
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
    _shared = hass.data[const.DOMAIN][_scups]
    if _shared is None:
        _LOGGER.info("No shared data found for CUPS %s", _scups)
        connection.send_result(msg["id"], [])
        return
    connection.send_result(msg["id"], _shared[const.SHARED_ATTRIBUTES])


def async_register_websockets(hass: HomeAssistant):
    """Register websockets into HA API."""

    async_register_command(hass, ws_get_consumptions)
    async_register_command(hass, ws_get_surplus)
    async_register_command(hass, ws_get_cost)
    async_register_command(hass, ws_get_maximeter)
    async_register_command(hass, ws_get_summary)
