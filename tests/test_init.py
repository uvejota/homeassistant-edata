"""Tests for the edata integration setup and options handling."""

from datetime import datetime
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.edata import _build_billing_rules, async_migrate_entry
from custom_components.edata.const import DOMAIN, SHARED_DATAMANAGER
from custom_components.edata.core.config import (
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from custom_components.edata.core.options import (
    CONF_BILLING,
    CONF_PVPC,
    CONF_UPDATE_SINCE,
)

from .fixtures import CUPS, PASSWORD, SCUPS, USERNAME


async def test_setup_and_unload(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """The integration sets up, populates shared memory, and unloads cleanly."""
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert SHARED_DATAMANAGER in hass.data[DOMAIN][SCUPS]

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_options_update_triggers_billing_recompute(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Updating billing options recomputes costs from the requested date."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][SCUPS]["coordinator"]
    with patch.object(
        coordinator, "update_billing", AsyncMock()
    ) as mock_update_billing:
        hass.config_entries.async_update_entry(
            billing_config_entry,
            options={**billing_config_entry.options, CONF_UPDATE_SINCE: "2023-02-01"},
        )
        await hass.async_block_till_done()

    mock_update_billing.assert_awaited_once()
    _, since = mock_update_billing.await_args.args
    assert since == datetime(2023, 2, 1, 0, 0)


_LEGACY_PAYLOAD = {
    "supplies": [
        {
            "cups": CUPS,
            "date_start": "2023-01-01T00:00:00",
            "date_end": "2024-12-31T00:00:00",
            "address": "-",
            "postal_code": "-",
            "province": "-",
            "municipality": "-",
            "distributor": "-",
            "pointType": 5,
            "distributorCode": "2",
        }
    ],
    "contracts": [
        {
            "date_start": "2024-01-01T00:00:00",
            "date_end": "2024-12-31T00:00:00",
            "marketer": "MARKETER",
            "distributorCode": "2",
            "power_p1": 4.6,
            "power_p2": 4.6,
        }
    ],
    "consumptions": [
        {
            "datetime": "2024-01-01T00:00:00",
            "delta_h": 1,
            "value_kWh": 0.5,
            "surplus_kWh": 0,
            "real": True,
        },
        {
            "datetime": "2024-01-01T01:00:00",
            "delta_h": 1,
            "value_kWh": 0.4,
            "surplus_kWh": 0,
            "real": True,
        },
    ],
    "maximeter": [{"datetime": "2024-01-10T14:15:00", "value_kW": 3.2}],
    "pvpc": [],
}


async def test_migrate_v1_entry_imports_and_removes_legacy_storage(
    hass: HomeAssistant,
) -> None:
    """A v1 entry imports the 1.x JSON into the 2.0 DB and removes the old file."""
    storage = Path(hass.config.path(STORAGE_DIR))
    legacy_dir = storage / "edata"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    # 1.x named the cache by the full CUPS, lower-cased.
    legacy_file = legacy_dir / f"edata_{CUPS.lower()}.json"
    legacy_file.write_text(json.dumps(_LEGACY_PAYLOAD), encoding="utf-8")

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title=SCUPS,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: CUPS,
            CONF_SCUPS: SCUPS,
        },
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 2
    # A successful, non-empty import removes the old file and populates the DB.
    assert not legacy_file.exists()
    assert (storage / "edata.db").exists()


async def test_migrate_v1_entry_without_legacy_file_just_bumps_version(
    hass: HomeAssistant,
) -> None:
    """With no 1.x cache present, migration is a no-op that still bumps the version."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        title=SCUPS,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: CUPS,
            CONF_SCUPS: SCUPS,
        },
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2


def test_build_billing_rules_guards_invalid_options() -> None:
    """Invalid or disabled billing options degrade to no billing without raising."""
    assert _build_billing_rules({}) is None
    # billing enabled but required price fields absent (e.g. legacy/partial config)
    assert _build_billing_rules({CONF_BILLING: True, CONF_PVPC: False}) is None
