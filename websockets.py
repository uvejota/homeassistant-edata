import logging
import voluptuous as vol
from .const import DOMAIN
from homeassistant.core import callback
from homeassistant.components import websocket_api

_LOGGER = logging.getLogger(__name__)

@callback
def websocket_get_daily_data(hass, connection, msg):
    """Publish daily consumptions list data."""
    try:
        connection.send_result(msg["id"], hass.data[DOMAIN][msg["scups"].upper()].get('consumptions_daily_sum', []))
    except Exception as e:
        _LOGGER.exception (e)
        connection.send_result(msg["id"], [])

@callback
def websocket_get_monthly_data(hass, connection, msg):
    """Publish monthly consumptions list data."""
    try:
        connection.send_result(msg["id"], hass.data[DOMAIN][msg["scups"].upper()].get('consumptions_monthly_sum', []))
    except Exception as e:
        _LOGGER.exception (e)
        connection.send_result(msg["id"], [])

@callback
def websocket_get_maximeter(hass, connection, msg):
    """Publish maximeter list data."""
    try:
        connection.send_result(msg["id"], hass.data[DOMAIN][msg["scups"].upper()].get('maximeter', []))
    except Exception as e:
        _LOGGER.exception (e)
        connection.send_result(msg["id"], [])

def async_register_websockets (hass):
    
    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/consumptions/daily",
        websocket_get_daily_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
            vol.Required("type"): f"{DOMAIN}/consumptions/daily",
            vol.Required("scups"): str
        }),
    )

    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/consumptions/monthly",
        websocket_get_monthly_data,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
            vol.Required("type"): f"{DOMAIN}/consumptions/monthly",
            vol.Required("scups"): str
        }),
    )

    hass.components.websocket_api.async_register_command(
        f"{DOMAIN}/maximeter",
        websocket_get_maximeter,
        websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({
            vol.Required("type"): f"{DOMAIN}/maximeter",
            vol.Required("scups"): str
        }),
    )