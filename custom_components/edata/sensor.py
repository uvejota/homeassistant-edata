"""Sensor platform for edata component."""

import json
import logging

from edata.connectors.datadis import RECENT_QUERIES_FILE
from edata.processors import utils as edata_utils
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CURRENCY_EURO,
    EVENT_HOMEASSISTANT_START,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.storage import Store

from . import const, utils
from .coordinator import EdataCoordinator
from .websockets import async_register_websockets
from .entity import EdataEntity

# HA variables
_LOGGER = logging.getLogger(__name__)

INFO_SENSORS_DESC = [
    # (name, state_key, [attributes_key])
    (
        "info",
        "cups",
        ["contract_p1_kW", "contract_p2_kW"],
    ),
]

ENERGY_SENSORS_DESC = [
    (
        "yesterday_kwh",
        "yesterday_kWh",
        ["yesterday_hours", "yesterday_p1_kWh", "yesterday_p2_kWh", "yesterday_p3_kWh"],
    ),
    (
        "last_registered_day_kwh",
        "last_registered_day_kWh",
        [
            "last_registered_date",
            "last_registered_day_hours",
            "last_registered_day_p1_kWh",
            "last_registered_day_p2_kWh",
            "last_registered_day_p3_kWh",
        ],
    ),
    (
        "month_kwh",
        "month_kWh",
        [
            "month_days",
            "month_daily_kWh",
            "month_p1_kWh",
            "month_p2_kWh",
            "month_p3_kWh",
        ],
    ),
    (
        "last_month_kwh",
        "last_month_kWh",
        [
            "last_month_days",
            "last_month_daily_kWh",
            "last_month_p1_kWh",
            "last_month_p2_kWh",
            "last_month_p3_kWh",
        ],
    ),
]

POWER_SENSORS_DESC = [
    (
        "max_power_kw",
        "max_power_kW",
        [
            "max_power_date",
            "max_power_mean_kW",
            "max_power_90perc_kW",
        ],
    ),
]

COST_SENSORS_DESC = [
    (
        "month_eur",
        "month_€",
        [],
    ),
    (
        "last_month_eur",
        "last_month_€",
        [],
    ),
]


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
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

    pricing_rules = (
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
            const.BILLING_ENERGY_FORMULA: config_entry.options.get(
                const.BILLING_ENERGY_FORMULA, const.DEFAULT_BILLING_ENERGY_FORMULA
            ),
            const.BILLING_POWER_FORMULA: config_entry.options.get(
                const.BILLING_POWER_FORMULA, const.DEFAULT_BILLING_POWER_FORMULA
            ),
            const.BILLING_OTHERS_FORMULA: config_entry.options.get(
                const.BILLING_OTHERS_FORMULA, const.DEFAULT_BILLING_OTHERS_FORMULA
            ),
            const.BILLING_SURPLUS_FORMULA: "0",  # TODO implement also surplus billing
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
        pricing_rules,
        prev_data=storage if storage else None,
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
    _entities = []
    _entities.extend([EdataInfoSensor(coordinator, *x) for x in INFO_SENSORS_DESC])
    _entities.extend([EdataEnergySensor(coordinator, *x) for x in ENERGY_SENSORS_DESC])
    _entities.extend([EdataPowerSensor(coordinator, *x) for x in POWER_SENSORS_DESC])
    _entities.extend([EdataCostSensor(coordinator, *x) for x in COST_SENSORS_DESC])
    async_add_entities(_entities)

    # register websockets
    async_register_websockets(hass)

    return True


class EdataInfoSensor(EdataEntity, SensorEntity):
    """Representation of the info related to an e-data sensor."""

    _attr_icon = "mdi:home-lightning-bolt-outline"
    _attr_native_unit_of_measurement = None
    _attr_has_entity_name = False

    def __init__(
        self, coordinator, name: str, state: str, attributes: list[str]
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, name, state, attributes)

        # override to allow backwards compatibility
        self._attr_translation_key = None
        self._attr_name = f"edata_{coordinator.id}"

    async def service_recreate_statistics(self):
        """Recreates statistics."""
        await self.coordinator.statistics.rebuild_recent_statistics()
        _LOGGER.warning(
            "You must reload the entity manually to finish statistics recreation"
        )


class EdataEnergySensor(EdataEntity, SensorEntity):
    """Representation of an energy-related e-data sensor."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR


class EdataPowerSensor(EdataEntity, SensorEntity):
    """Representation of a power-related e-data sensor."""

    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT


class EdataCostSensor(EdataEntity, SensorEntity):
    """Representation of an cost-related e-data sensor."""

    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = CURRENCY_EURO
