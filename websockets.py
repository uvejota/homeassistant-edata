import logging
import voluptuous as vol
from .const import DOMAIN
from homeassistant.core import callback
from homeassistant.components import websocket_api
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

@callback
def websocket_get_daily_data(hass, connection, msg):
    """Publish daily consumptions list data."""
    try:
        data = hass.data[DOMAIN][msg["scups"].upper()].get('consumptions_daily_sum', [])
        filtered_data = [x for x in data if ((datetime.today().date() - datetime.strptime(x['datetime'], '%Y-%m-%d').date()) < timedelta (days=30))]
        connection.send_result(msg["id"], filtered_data)
    except KeyError as e:
        _LOGGER.error ("the provided scups parameter is not correct: %s", msg["scups"].upper())
    except Exception as e:
        _LOGGER.exception ("unhandled exception when processing websockets", e)
        connection.send_result(msg["id"], [])

@callback
def websocket_get_monthly_data(hass, connection, msg):
    """Publish monthly consumptions list data."""
    try:
        connection.send_result(msg["id"], hass.data[DOMAIN][msg["scups"].upper()].get('consumptions_monthly_sum', []))
    except KeyError as e:
        _LOGGER.error ("the provided scups parameter is not correct: %s", msg["scups"].upper())
    except Exception as e:
        _LOGGER.exception ("unhandled exception when processing websockets", e)
        connection.send_result(msg["id"], [])

@callback
def websocket_get_maximeter(hass, connection, msg):
    """Publish maximeter list data."""
    try:
        connection.send_result(msg["id"], hass.data[DOMAIN][msg["scups"].upper()].get('maximeter', []))
    except KeyError as e:
        _LOGGER.error ("the provided scups parameter is not correct: %s", msg["scups"].upper())
    except Exception as e:
        _LOGGER.exception ("unhandled exception when processing websockets", e)
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