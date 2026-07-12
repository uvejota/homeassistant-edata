"""Tests for the edata config and options flows."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.edata.const import DOMAIN
from custom_components.edata.core.config import (
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from custom_components.edata.core.options import (
    CONF_APPLYFROM,
    CONF_BILLING,
    CONF_CONFIRM,
    CONF_DEBUG,
    CONF_PVPC,
    CONF_UPDATE_SINCE,
)

from .fixtures import CUPS, PASSWORD, USERNAME


def _schema_defaults(schema: vol.Schema) -> dict:
    """Extract the default values from a voluptuous schema."""
    defaults = {}
    for key in schema.schema:
        if key.default is vol.UNDEFINED:
            continue
        defaults[str(key.schema)] = key.default()
    return defaults


@pytest.fixture
def mock_supplies() -> AsyncMock:
    """Patch the config flow Datadis connector to return one supply."""
    with patch(
        "custom_components.edata.config_flow.DatadisConnector"
    ) as connector:
        instance = connector.return_value
        instance.async_get_supplies = AsyncMock(
            return_value=[SimpleNamespace(cups=CUPS)]
        )
        yield instance.async_get_supplies


async def test_user_flow_success(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
) -> None:
    """A valid user completes credentials and CUPS selection to create an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
    )
    assert result["step_id"] == "choosecups"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CUPS: CUPS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CUPS] == CUPS


@pytest.mark.parametrize(
    ("supplies_return", "expected_error"),
    [
        (None, "invalid_credentials"),
        ([], "no_supplies_found"),
    ],
    ids=["invalid_credentials", "no_supplies_found"],
)
async def test_user_flow_errors(
    setup_integration: None,
    hass: HomeAssistant,
    supplies_return: list | None,
    expected_error: str,
) -> None:
    """Credential and empty-supply errors are surfaced on the user step."""
    with patch(
        "custom_components.edata.config_flow.DatadisConnector"
    ) as connector:
        connector.return_value.async_get_supplies = AsyncMock(
            return_value=supplies_return
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_options_flow_apply_since(
    setup_integration: None,
    hass: HomeAssistant,
    billing_config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """The billing options flow walks costs, formulas and confirm to store a date."""
    billing_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(billing_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        billing_config_entry.entry_id
    )
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DEBUG: False, CONF_BILLING: True, CONF_PVPC: False},
    )
    assert result["step_id"] == "costs"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _schema_defaults(result["data_schema"])
    )
    assert result["step_id"] == "formulas"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _schema_defaults(result["data_schema"])
    )
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**_schema_defaults(result["data_schema"]), CONF_APPLYFROM: "2023-02-01", CONF_CONFIRM: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPDATE_SINCE] == "2023-02-01"


async def test_options_flow_billing_disabled(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Disabling billing on the init step creates the entry without further steps."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DEBUG: False, CONF_BILLING: False, CONF_PVPC: False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
