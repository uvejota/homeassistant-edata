import logging
import voluptuous as vol
import json
from homeassistant.helpers import config_validation as cv
from homeassistant.components.sensor import SensorEntity, PLATFORM_SCHEMA
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from homeassistant.helpers.storage import Store
from edata.helpers import ReportHelper, ATTRIBUTES
from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY_PREAMBLE
from .websockets import *
from .store import DateTimeEncoder, DataTools

# HA variables
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=30)

# Custom configuration entries
CONF_CUPS = 'cups'
CONF_PROVIDER = 'provider'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_PROVIDER): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional('experimental'): cv.boolean,
    }
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    entities = []
    experimental = config.get('experimental', False)
    hass.data.setdefault(DOMAIN, {})
    entities.append(EdataSensor(hass, config[CONF_USERNAME], config[CONF_PASSWORD], config[CONF_CUPS], experimental=experimental))
    for e in entities:
        await e.try_load_storage()
    async_add_entities(entities, True)
    async_register_websockets (hass)


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
        self._hass = hass
        self._cups = cups.upper()
        self._scups = cups[-4:].upper()
        self._attr_name = f'{DOMAIN}_{self._scups}'
        #self._attr_unique_id = f'{DOMAIN}.{self._scups}'
        self._hass.data[DOMAIN][self._scups] = {}
        self._store = Store (hass, STORAGE_VERSION, f"{STORAGE_KEY_PREAMBLE}_{self._scups}", encoder=DateTimeEncoder)
        self._last_stored = datetime (1970, 1, 1)
        self._helper = ReportHelper ('datadis', usr, pwd, cups, experimental=experimental)

    async def try_load_storage (self):
        try:
            serialized_data = await self._store.async_load()
            old_data = json.loads(json.dumps(serialized_data), object_hook=DataTools.datetime_parser)
            if old_data is not None and old_data != {}:
                if DataTools.check_integrity(old_data):
                    self._helper = ReportHelper ('datadis', self._usr, self._pwd, self._cups, data=old_data, experimental=self._experimental) # storage_dir='.storage'
                    self._helper.process_data ()
                else:
                    _LOGGER.warning ('wrong database structure, wiping data')
        except Exception as e:
            _LOGGER.exception (e)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        '''
        attrs = {}
        for attr in self._helper.attributes:
            attrs[attr] = f"{self._get_attr_value(attr)} {ATTRIBUTES[attr] if ATTRIBUTES[attr] is not None else ''}" if self._get_attr_value(attr) is not None else '-'
        '''
        return self._helper.attributes

    async def async_update(self):
        """Fetch new state data for the sensor."""
        # update data asynchronously
        self._hass.data[DOMAIN][self._scups] = await self.async_data_update ()

    async def async_data_update (self):
        try:
            await self._helper.async_update ()
            if self._helper.last_update > datetime(1970, 1, 1):
                if (datetime.now() - self._last_stored) > self.STORAGE_INTERVAL:
                    # do store
                    self._last_stored = datetime.now()
                    await self._store.async_save(self._helper.data)
                self._state = self._helper.last_update.strftime("%Y-%m-%d %H:%M")
            return self._helper.data
        except Exception as e:
            _LOGGER.error ('uncaught exception when updating data')
            _LOGGER.exception (e)

    def _get_attr_value (self, attr):
        try:
            return self._helper.attributes[attr]
        except Exception:
            return None

    