"""Sensor platform for edata component."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant

from . import const
from .entity import EdataSensorEntity

INFO_SENSORS_DESC = [
    # (name, state_key, [attributes_key])
    (
        "info",
        "last_datetime",
        ["contract_p1_kW", "contract_p2_kW"],
    ),
]

ENERGY_SENSORS_DESC = [
    (
        "last_day_kwh",
        "last_day_value_kWh",
        [
            "last_datetime",
            "last_day_delta_h",
            "last_day_value_p1_kWh",
            "last_day_value_p2_kWh",
            "last_day_value_p3_kWh",
        ],
    ),
    (
        "last_day_surplus_kwh",
        "last_day_surplus_kWh",
        [
            "last_datetime",
            "last_day_delta_h",
            "last_day_surplus_p1_kWh",
            "last_day_surplus_p2_kWh",
            "last_day_surplus_p3_kWh",
        ],
    ),
    (
        "month_kwh",
        "month_value_kWh",
        [
            "month_delta_h",
            "month_daily_kWh",
            "month_value_p1_kWh",
            "month_value_p2_kWh",
            "month_value_p3_kWh",
        ],
    ),
    (
        "month_surplus_kwh",
        "month_surplus_kWh",
        [
            "month_delta_h",
            "month_surplus_p1_kWh",
            "month_surplus_p2_kWh",
            "month_surplus_p3_kWh",
        ],
    ),
    (
        "last_month_kwh",
        "last_month_value_kWh",
        [
            "last_month_delta_h",
            "last_month_value_p1_kWh",
            "last_month_value_p2_kWh",
            "last_month_value_p3_kWh",
        ],
    ),
    (
        "last_month_surplus_kwh",
        "last_month_surplus_kWh",
        [
            "last_month_delta_h",
            "last_month_surplus_p1_kWh",
            "last_month_surplus_p2_kWh",
            "last_month_surplus_p3_kWh",
        ],
    ),
]

POWER_SENSORS_DESC = [
    (
        "max_power_kw",
        "max_power_kW",
        [
            "max_power_datetime",
            "max_power_mean_kW",
        ],
    ),
]

COST_SENSORS_DESC = [
    (
        "month_eur",
        "month_bill_value_eur",
        [],
    ),
    (
        "last_month_eur",
        "last_month_bill_value_eur",
        [],
    ),
]


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(const.DOMAIN, {})

    # get configured parameters
    scups = config_entry.data["scups"]
    coordinator = hass.data[const.DOMAIN][scups.lower()]["coordinator"]
    # add sensor entities
    _entities = []
    _entities.extend([EdataInfoSensor(coordinator, *x) for x in INFO_SENSORS_DESC])
    _entities.extend([EdataEnergySensor(coordinator, *x) for x in ENERGY_SENSORS_DESC])
    _entities.extend([EdataPowerSensor(coordinator, *x) for x in POWER_SENSORS_DESC])
    _entities.extend([EdataCostSensor(coordinator, *x) for x in COST_SENSORS_DESC])
    async_add_entities(_entities)

    return True


class EdataInfoSensor(EdataSensorEntity, SensorEntity):
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


class EdataEnergySensor(EdataSensorEntity, SensorEntity):
    """Representation of an energy-related e-data sensor."""

    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR


class EdataPowerSensor(EdataSensorEntity, SensorEntity):
    """Representation of a power-related e-data sensor."""

    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT


class EdataCostSensor(EdataSensorEntity, SensorEntity):
    """Representation of an cost-related e-data sensor."""

    _attr_icon = "mdi:currency-eur"
    _attr_native_unit_of_measurement = CURRENCY_EURO
