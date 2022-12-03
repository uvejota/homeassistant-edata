"""Sensor platform for edata component"""

import json
import logging

import voluptuous as vol
from edata.connectors.datadis import RECENT_QUERIES_FILE
from edata.processors import utils as edata_utils
from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const
from . import utils
from .coordinator import EdataCoordinator
from .websockets import async_register_websockets

# HA variables
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.All(
    cv.deprecated(CONF_USERNAME),
    cv.deprecated(CONF_PASSWORD),
    cv.deprecated(const.CONF_CUPS),
    cv.deprecated(const.CONF_EXPERIMENTAL),
    cv.deprecated(const.CONF_PROVIDER),
    PLATFORM_SCHEMA.extend(
        (
            {
                vol.Optional(const.CONF_DEBUG): cv.boolean,
                vol.Optional(const.CONF_PROVIDER): cv.string,
                vol.Optional(CONF_USERNAME): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Optional(const.CONF_CUPS): cv.string,
                vol.Optional(const.CONF_EXPERIMENTAL): cv.boolean,
            }
        ),
    ),
)


VALID_ENTITY_CONFIG = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(const.CONF_CUPS): cv.string,
        vol.Optional(const.CONF_EXPERIMENTAL, default=False): cv.boolean,
        # vol.Optional(const.CONF_PROVIDER): cv.string
    },
    extra=vol.REMOVE_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import edata configuration from YAML."""
    hass.data.setdefault(const.DOMAIN, {})

    if config.get(const.CONF_DEBUG, False):
        logging.getLogger("edata").setLevel(logging.INFO)
    else:
        logging.getLogger("edata").setLevel(logging.WARNING)

    if any(
        key in config
        for key in [
            CONF_USERNAME,
            CONF_PASSWORD,
            const.CONF_CUPS,
            const.CONF_EXPERIMENTAL,
            const.CONF_PROVIDER,
        ]
    ):
        try:
            validated_config = VALID_ENTITY_CONFIG(config)
            _LOGGER.warning(
                "Loading edata sensor via platform setup is deprecated. It will be imported into Home Assistant integration. Please remove it from your configuration"
            )
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    const.DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data=validated_config,
                )
            )
        except vol.Error as ex:
            _LOGGER.warning("Invalid config '%s': %s", config, ex)

    return True


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(const.DOMAIN, {})

    usr = config_entry.data[CONF_USERNAME]
    pwd = config_entry.data[CONF_PASSWORD]
    cups = config_entry.data[const.CONF_CUPS]

    if not utils.check_cups_integrity(cups):
        _LOGGER.error(
            "Specified CUPS (%s) is invalid, please copy it from Datadis website", cups
        )

    authorized_nif = config_entry.data.get(const.CONF_AUTHORIZEDNIF, None)
    scups = config_entry.data.get(const.CONF_SCUPS, cups[-4:].upper())

    is_pvpc = config_entry.options.get(const.CONF_PVPC, False)

    billing = (
        {
            const.PRICE_P1_KW_YEAR: config_entry.options.get(const.PRICE_P1_KW_YEAR),
            const.PRICE_P2_KW_YEAR: config_entry.options.get(const.PRICE_P2_KW_YEAR),
            const.PRICE_P1_KWH: config_entry.options.get(const.PRICE_P1_KWH)
            if not is_pvpc
            else None,
            const.PRICE_P2_KWH: config_entry.options.get(const.PRICE_P2_KWH)
            if not is_pvpc
            else None,
            const.PRICE_P3_KWH: config_entry.options.get(const.PRICE_P3_KWH)
            if not is_pvpc
            else None,
            const.PRICE_METER_MONTH: config_entry.options.get(const.PRICE_METER_MONTH),
            const.PRICE_MARKET_KW_YEAR: config_entry.options.get(
                const.PRICE_MARKET_KW_YEAR
            ),
            const.PRICE_ELECTRICITY_TAX: config_entry.options.get(
                const.PRICE_ELECTRICITY_TAX
            ),
            const.PRICE_IVA: config_entry.options.get(const.PRICE_IVA),
        }
        if config_entry.options.get(const.CONF_BILLING, False)
        else None
    )

    # load old data if any
    serialized_data = await Store(
        hass,
        const.STORAGE_VERSION,
        f"{const.STORAGE_KEY_PREAMBLE}_{scups}",
    ).async_load()
    storage = edata_utils.deserialize_dict(serialized_data)

    datadis_recent_queries = await Store(
        hass,
        const.STORAGE_VERSION,
        f"{const.STORAGE_KEY_PREAMBLE}_recent_queries",
    ).async_load()

    if datadis_recent_queries:
        with open(RECENT_QUERIES_FILE, "w", encoding="utf8") as queries_file:
            json.dump(datadis_recent_queries, queries_file)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "recreate_statistics",
        {},
        "service_recreate_statistics",
    )

    coordinator = EdataCoordinator(
        hass,
        usr,
        pwd,
        cups,
        scups,
        authorized_nif,
        billing,
        prev_data=None if not storage else storage,
    )

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
        self._data = coordinator.hass.data[const.DOMAIN][coordinator.id.upper()]
        self._coordinator = coordinator

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._data.get("state", const.STATE_ERROR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._data.get("attributes", {})

    async def service_recreate_statistics(self):
        """Recreates statistics"""
        await self._coordinator.statistics.clear_all_statistics()
        await self._coordinator.statistics.update_statistics()
