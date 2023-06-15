"""Websockets related definitions"""

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@callback
def websocket_get_daily_data(hass, connection, msg):
    """Publish daily consumptions list data."""
    try:
        data = hass.data[DOMAIN][msg["scups"].upper()].get("ws_consumptions_day", [])
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
    """Publish monthly consumptions list data."""
    try:
        connection.send_result(
            msg["id"],
            hass.data[DOMAIN][msg["scups"].upper()].get("ws_consumptions_month", []),
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
    """Publish maximeter list data."""
    try:
        data = hass.data[DOMAIN][msg["scups"].upper()].get("ws_maximeter", [])
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


def async_register_websockets(hass):
    """Register websockets into HA API"""

    # for daily consumptions
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/consumptions/daily",
        websocket_get_daily_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{DOMAIN}/consumptions/daily",
                vol.Required("scups"): str,
                vol.Optional("records"): int,
            }
        ),
    )

    # for monthly consumptions
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/consumptions/monthly",
        websocket_get_monthly_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{DOMAIN}/consumptions/monthly",
                vol.Required("scups"): str,
            }
        ),
    )

    # for maximeter
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/maximeter",
        websocket_get_maximeter,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
            {
                vol.Required("type"): f"{DOMAIN}/maximeter",
                vol.Required("scups"): str,
                vol.Optional("tariff"): int,
            }
        ),
    )
