"""Migration functions."""


import json
import logging
import os

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from .const import STORAGE_KEY_PREAMBLE

_LOGGER = logging.getLogger(__name__)


def migrate_pre2024_storage_if_needed(
    hass: HomeAssistant, cups: str, sensor_id: str
) -> None:
    """Migrate old storage strategy to 2024.XX.XX ones."""

    _cups = cups.lower()
    _id = sensor_id.upper()

    old_path = hass.config.path(STORAGE_DIR, f"{STORAGE_KEY_PREAMBLE}_{_id}")
    new_path = hass.config.path(STORAGE_DIR, "edata", f"edata_{_cups}.json")

    os.makedirs(os.path.dirname(new_path), exist_ok=True)

    need_migration = not os.path.exists(new_path)

    try:
        with open(old_path, encoding="utf8") as old_file:
            storage_contents = json.load(old_file)
            old_data = storage_contents["data"]
    except Exception:
        storage_contents = None
        old_data = None

    if need_migration and (old_data is not None):
        _LOGGER.info("Migrating storage to 2024.xx.xx strategy")
        with open(new_path, "x", encoding="utf8") as new_file:
            json.dump(old_data, new_file)
        _LOGGER.info("Storage migrated successfuly, removing old storage")
        with open(old_path, mode="w", encoding="utf8") as old_file:
            storage_contents["data"] = []
            json.dump(storage_contents, old_file)
        _LOGGER.info("Old storage successfully removed")
