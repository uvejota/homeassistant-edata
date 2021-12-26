import logging
import voluptuous as vol
import json
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, EVENT_HOMEASSISTANT_START
from datetime import datetime, timedelta
from homeassistant.helpers.storage import Store
from edata.helpers import EdataHelper
from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY_PREAMBLE
from .websockets import *
from .store import DateTimeEncoder, DataTools

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(minutes=30)

# Custom configuration entries
CONF_CUPS = 'cups'
CONF_PROVIDER = 'provider'
CONF_EXPERIMENTAL = 'experimental'
CONF_DEBUG = 'debug'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_PROVIDER): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional(CONF_EXPERIMENTAL): cv.boolean,
        vol.Optional(CONF_DEBUG): cv.boolean
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    await async_setup_reload_service(hass, DOMAIN, ['sensor'])

    entities = []
    experimental = config.get(CONF_EXPERIMENTAL, False)
    debug = config.get(CONF_DEBUG, False)
    hass.data.setdefault(DOMAIN, {})
    entities.append(EdataSensor(hass, config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_CUPS], experimental=experimental))
    async_add_entities(entities)
    async_register_websockets (hass)

    if debug:
        logging.getLogger("edata").setLevel(logging.INFO)

    return True


class EdataSensor(SensorEntity):
    """Representation of a Sensor."""
    _attr_unit_of_measurement = None
    _attr_icon = "hass:flash"
    STORAGE_INTERVAL = timedelta (hours=12)

    def __init__(self, hass, usr, pwd, cups, experimental=False, name='edata'):
        """Initialize the sensor."""
        self._usr = usr 
        self._pwd = pwd  
        self._cups = cups  
        self._experimental = experimental
        self._state = 'loading'
        self._attributes = {}
        self._hass = hass
        self._cups = cups.upper()
        self._scups = cups[-4:].upper()
        self._attr_name = f'{DOMAIN}_{self._scups}'
        #self._attr_unique_id = f'{DOMAIN}.{self._scups}'
        self._hass.data[DOMAIN][self._scups] = {}
        self._store = Store (hass, STORAGE_VERSION, f"{STORAGE_KEY_PREAMBLE}_{self._scups}", encoder=DateTimeEncoder)
        self._last_stored = datetime (1970, 1, 1)
        self._last_update = datetime (1970, 1, 1)
        self._helper = EdataHelper ('datadis', self._usr, self._pwd, self._cups, experimental=self._experimental)

    async def async_added_to_hass(self):

        @callback
        def force_refresh(*args):
            """Force the component to refresh."""
            self.async_schedule_update_ha_state(True)

        try:
            serialized_data = await self._store.async_load()
            old_data = json.loads(json.dumps(serialized_data), object_hook=DataTools.datetime_parser)
            if old_data is not None and old_data != {}:
                if DataTools.check_integrity(old_data):
                    self._helper = EdataHelper ('datadis', self._usr, self._pwd, self._cups, data=old_data, experimental=self._experimental)
                    self._helper.process_data ()
                    self._attributes = self._helper.attributes
                    self._hass.data[DOMAIN][self._scups] = self._helper.data
                else:
                    _LOGGER.warning ('wrong database structure, wiping data')
        except Exception as e:
            _LOGGER.exception (e)
        finally:
            if self._hass.state == CoreState.running:
                force_refresh()
            else:
                self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, force_refresh)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        # update data asynchronously
        try:
            res = await self._hass.async_add_executor_job(self._update)
            if res and (datetime.now() - self._last_stored) > self.STORAGE_INTERVAL:
                # do store
                self._last_stored = datetime.now()
                await self._store.async_save(self._data)
        except Exception as e:
            _LOGGER.error ('uncaught exception when updating data')
            _LOGGER.exception (e)

    def _update (self):
        self._helper.update ()
        if self._last_update != self._helper.last_update:
            self._state = self._helper.attributes['last_registered_kWh_date'].strftime("%Y-%m-%d %H:%M")
            self._attributes = self._helper.attributes
            self._data = self._helper.data
            self._last_update = self._helper.last_update
            self._hass.data[DOMAIN][self._scups] = self._data
            return True
        else:
            return False