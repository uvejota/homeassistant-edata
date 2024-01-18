"""Edata entity definition."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import const


class EdataEntity(CoordinatorEntity):
    """Representation of an e-data Sensor."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator, name: str, state: str, attributes: list[str]
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        # names and identifiers
        self._attr_unique_id = f"{coordinator.id} {name}"
        self._attr_translation_key = name

        # state and attribute keys
        self._state = state
        self._attrs = attributes

        # data accessors
        self._data = coordinator.hass.data[const.DOMAIN][coordinator.id.upper()]

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._data.get("attributes", {}).get(self._state, None)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {x: self._data.get("attributes", {}).get(x, None) for x in self._attrs}

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (const.DOMAIN, self.coordinator.cups)
            },
            name=self.coordinator.id.upper(),
            sw_version=f"edata v{getattr(self.coordinator.hass.data['integrations'][const.DOMAIN], 'version', 0)}",
        )
