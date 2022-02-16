import logging

import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_BILLING,
    CONF_CUPS,
    CONF_DEBUG,
    CONF_EXPERIMENTAL,
    CONF_PROVIDER,
    DOMAIN,
    PRICE_ELECTRICITY_TAX,
    PRICE_IVA,
    PRICE_MARKET_KW_YEAR,
    PRICE_METER_MONTH,
    PRICE_P1_KW_YEAR,
    PRICE_P1_KWH,
    PRICE_P2_KW_YEAR,
    PRICE_P2_KWH,
    PRICE_P3_KWH,
    STATE_ERROR,
    STORAGE_ELEMENTS,
    STORAGE_KEY_PREAMBLE,
    STORAGE_VERSION,
)
from .coordinator import EdataCoordinator
from .store import DateTimeEncoder, async_load_storage
from .websockets import async_register_websockets

# HA variables
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.All(
    cv.deprecated(CONF_USERNAME),
    cv.deprecated(CONF_PASSWORD),
    cv.deprecated(CONF_CUPS),
    cv.deprecated(CONF_EXPERIMENTAL),
    cv.deprecated(CONF_PROVIDER),
    PLATFORM_SCHEMA.extend(
        (
            {
                vol.Optional(CONF_DEBUG): cv.boolean,
                vol.Optional(CONF_PROVIDER): cv.string,
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(CONF_CUPS): cv.string,
                vol.Optional(CONF_EXPERIMENTAL): cv.boolean,
            }
        ),
    ),
)


VALID_ENTITY_CONFIG = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_CUPS): cv.string,
        vol.Optional(CONF_EXPERIMENTAL, default=False): cv.boolean,
        # vol.Optional(CONF_PROVIDER): cv.string
    },
    extra=vol.REMOVE_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import edata configuration from YAML."""
    hass.data.setdefault(DOMAIN, {})

    if config.get(CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)

    logging.getLogger("edata").setLevel(logging.INFO)

    if any(
        key in config
        for key in [
            CONF_USERNAME,
            CONF_PASSWORD,
            CONF_CUPS,
            CONF_EXPERIMENTAL,
            CONF_PROVIDER,
        ]
    ):
        try:
            validated_config = VALID_ENTITY_CONFIG(config)
            _LOGGER.warning(
                "Loading edata sensor via platform setup is deprecated. It will be imported into Home Assistant integration. Please remove it from your configuration"
            )
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data=validated_config,
                )
            )
        except vol.Error as ex:
            _LOGGER.warning("Invalid config '%s': %s", config, ex)

    return True


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(DOMAIN, {})

    usr = config_entry.data[CONF_USERNAME]
    pwd = config_entry.data[CONF_PASSWORD]
    cups = config_entry.data[CONF_CUPS]
    scups = cups[-4:]

    billing = (
        {
            PRICE_P1_KW_YEAR: config_entry.options.get(PRICE_P1_KW_YEAR),
            PRICE_P2_KW_YEAR: config_entry.options.get(PRICE_P2_KW_YEAR),
            PRICE_P1_KWH: config_entry.options.get(PRICE_P1_KWH),
            PRICE_P2_KWH: config_entry.options.get(PRICE_P2_KWH),
            PRICE_P3_KWH: config_entry.options.get(PRICE_P3_KWH),
            PRICE_METER_MONTH: config_entry.options.get(PRICE_METER_MONTH),
            PRICE_MARKET_KW_YEAR: config_entry.options.get(PRICE_MARKET_KW_YEAR),
            PRICE_ELECTRICITY_TAX: config_entry.options.get(PRICE_ELECTRICITY_TAX),
            PRICE_IVA: config_entry.options.get(PRICE_IVA),
        }
        if config_entry.options.get(CONF_BILLING, False)
        else None
    )

    # load old data if any
    storage = await async_load_storage(
        Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREAMBLE}_{scups}",
            encoder=DateTimeEncoder,
        )
    )
    prev_data = {x: storage.get(x, []) for x in STORAGE_ELEMENTS} if storage else None
    coordinator = EdataCoordinator(hass, usr, pwd, cups, billing, prev_data=prev_data)

    # postpone first refresh to speed up startup
    @callback
    async def async_first_refresh(*args):
        """Force the component to assess the first refresh."""
        await coordinator.async_refresh()

    if hass.state == CoreState.running:
        await async_first_refresh()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, async_first_refresh)

    # add sensor entities
    async_add_entities([EdataSensor(coordinator)])

    # register websockets
    async_register_websockets(hass)

    return True


class EdataSensor(CoordinatorEntity, SensorEntity):
    """Representation of an e-data Sensor."""

    _attr_icon = "hass:flash"
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = coordinator.name
        self._data = coordinator.hass.data[DOMAIN][coordinator.id.upper()]

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._data.get("state", STATE_ERROR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._data.get("attributes", {})
