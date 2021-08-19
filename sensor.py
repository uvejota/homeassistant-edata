import logging
import voluptuous as vol
from homeassistant.helpers.entity import Entity
from homeassistant.helpers import config_validation as cv
from homeassistant.core import callback
from homeassistant.components import websocket_api
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from edata.helpers import ReportHelper, PLATFORMS, ATTRIBUTES

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)
FRIENDLY_NAME = 'edata'
DOMAIN = 'edata'

# Custom configuration entries
CONF_CUPS = 'cups'
CONF_PROVIDER = 'provider'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PROVIDER): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional('experimental'): cv.boolean,
    }
)

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    entities = []
    experimental = False
    if 'experimental' in config:
        experimental = config['experimental']
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][config[CONF_CUPS][-4:].upper()] = {}
    edata = ReportHelper (config[CONF_PROVIDER], config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_CUPS], experimental=experimental)

    try:
        await edata.async_update ()
    except Exception as e:
        _LOGGER.error (e)

    entities.append(EdataSensor(hass, edata, name=f'edata_{config[CONF_CUPS][-4:]}'))
    add_entities(entities)

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

class EdataSensor(Entity):
    """Representation of a Sensor."""

    def __init__(self, hass, edata, state='cups', name='edata'):
        """Initialize the sensor."""
        self._state = None
        self._attributes = {}
        self.hass = hass
        self.edata = edata
        self.state_label = state
        self._name = name

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon to be used for this entity."""
        return "mdi:flash" 

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return ''

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            await self.edata.async_update ()
        except Exception as e:
            _LOGGER.error (e)
        # update attrs
        for attr in self.edata.attributes:
            self._attributes[attr] = f"{self._get_attr_value(attr)} {ATTRIBUTES[attr] if ATTRIBUTES[attr] is not None else ''}" if self._get_attr_value(attr) is not None else '-'

        if self._get_attr_value('cups') is not None:
            scups = self._get_attr_value('cups')[-4:]
            for i in self.edata.data:
                self.hass.data[DOMAIN][scups.upper()][i] = self.edata.data[i]
        
        # update state
        self._state = self._get_attr_value('cups')

    def _get_attr_value (self, attr):
        try:
            return self.edata.attributes[attr]
        except Exception:
            return None

    