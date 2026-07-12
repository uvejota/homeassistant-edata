"""Button platform for edata component."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .core.config import CONF_SCUPS
from .core.utils import get_shared_memory
from .entity import EdataButtonEntity


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up entry."""
    hass.data.setdefault(DOMAIN, {})

    # get configured parameters
    scups = config_entry.data[CONF_SCUPS]
    shared = get_shared_memory(hass, scups)
    coordinator = shared["coordinator"]
    # add sensor entities
    _entities = []
    _entities.append(
        EdataResetButton(coordinator, "soft_reset", coordinator.async_soft_reset)
    )
    _entities.append(
        EdataImportButton(coordinator, "import_all_data", coordinator.async_full_import)
    )
    async_add_entities(_entities)

    return True


class EdataResetButton(EdataButtonEntity, ButtonEntity):
    """Representation of an e-data restoration button."""

    _attr_icon = "mdi:sync-alert"


class EdataImportButton(EdataButtonEntity, ButtonEntity):
    """Representation of an e-data import button."""

    _attr_icon = "mdi:content-save-all"
