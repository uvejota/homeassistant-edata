"""Tests for the edata config and options flows."""

from datetime import time
from unittest.mock import AsyncMock, patch

import aiohttp
from edata.providers.datadis import URL_TOKEN, LoginStatus
from freezegun.api import FrozenDateTimeFactory

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
import voluptuous as vol

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.edata.config_flow import get_scups
from custom_components.edata.const import DOMAIN
from custom_components.edata.core.config import (
    CONF_AUTHORIZED_NIF,
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from custom_components.edata.core.options import (
    CONF_APPLYFROM,
    CONF_BILLING,
    CONF_CONFIRM,
    CONF_DEBUG,
    CONF_IMPORT_SINCE,
    CONF_PVPC,
    CONF_SYNC_MODE,
    CONF_SYNC_TIME,
    CONF_UPDATE_SINCE,
    SYNC_MODE_AUTO,
    SYNC_MODE_FIXED,
    step_costs,
    step_formulas,
)

from .fixtures import CUPS, PASSWORD, SCUPS, USERNAME, build_supply


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
        instance.async_login = AsyncMock(return_value=True)
        instance.async_get_supplies = AsyncMock(
            return_value=[build_supply()]
        )
        yield instance.async_get_supplies


async def test_user_flow_success(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
    mock_data_manager: None,
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
    assert result["data"][CONF_SCUPS] == SCUPS
    assert result["result"].unique_id == CUPS
    assert "cups_list" not in result["data"]


@pytest.mark.parametrize(
    ("login", "status", "supplies", "expected_error"),
    [
        (False, LoginStatus.REJECTED, None, "invalid_auth"),
        (False, LoginStatus.UNAVAILABLE, None, "cannot_connect"),
        (True, LoginStatus.OK, [], "no_supplies_found"),
    ],
    ids=["invalid_auth", "cannot_connect", "no_supplies_found"],
)
async def test_user_flow_errors(
    setup_integration: None,
    hass: HomeAssistant,
    login: bool,
    status: LoginStatus,
    supplies: list | None,
    expected_error: str,
) -> None:
    """Rejected credentials, Datadis not answering and no supplies differ."""
    with patch(
        "custom_components.edata.config_flow.DatadisConnector"
    ) as connector:
        connector.return_value.async_login = AsyncMock(return_value=login)
        connector.return_value.login_status = status
        connector.return_value.async_get_supplies = AsyncMock(return_value=supplies)
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    # supplies are only asked for once the login worked
    assert connector.return_value.async_get_supplies.await_count == int(login)


async def test_user_flow_retries_after_an_error(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """After a rejected login the user can fix the password and go on."""
    with patch(
        "custom_components.edata.config_flow.DatadisConnector"
    ) as connector:
        connector.return_value.async_login = AsyncMock(side_effect=[False, True])
        connector.return_value.login_status = LoginStatus.REJECTED
        connector.return_value.async_get_supplies = AsyncMock(
            return_value=[build_supply()]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: "wrong"}
        )
        assert result["errors"] == {"base": "invalid_auth"}

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD}
        )
    assert result["step_id"] == "choosecups"


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
    # the preview states the simulated span and its coverage, not just the month
    assert _schema_defaults(result["data_schema"])["period"] == (
        "01/02/2023 – 25/02/2023 (600/672 h)"
    )

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


async def test_options_flow_fixed_sync_time(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Choosing a fixed sync time asks for it and applies it to the coordinator."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][SCUPS]["coordinator"]

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    # automatic by default
    assert _schema_defaults(result["data_schema"])[CONF_SYNC_MODE] == SYNC_MODE_AUTO
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SYNC_MODE: SYNC_MODE_FIXED,
            CONF_DEBUG: False,
            CONF_BILLING: False,
            CONF_PVPC: False,
        },
    )
    assert result["step_id"] == "sync_time"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SYNC_TIME: "07:30:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_SYNC_MODE] == SYNC_MODE_FIXED
    assert result["data"][CONF_SYNC_TIME] == "07:30:00"
    await hass.async_block_till_done()
    assert (coordinator._sync_mode, coordinator._sync_time) == (
        SYNC_MODE_FIXED,
        time(7, 30),
    )


@pytest.mark.parametrize(
    ("import_since", "error"),
    [
        ("2024-11-01", None),
        (None, None),
        # Datadis serves two years, counted in whole months
        ("2024-10-31", "import_since_out_of_range"),
        ("2026-10-16", "import_since_out_of_range"),
    ],
)
async def test_options_flow_import_since(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
    freezer: FrozenDateTimeFactory,
    import_since: str | None,
    error: str | None,
) -> None:
    """The date to import history from must be within what Datadis serves."""
    freezer.move_to("2026-10-15 12:00:00+00:00")
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    user_input = {CONF_DEBUG: False, CONF_BILLING: False, CONF_PVPC: False}
    if import_since is not None:
        user_input[CONF_IMPORT_SINCE] = import_since
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    if error is None:
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"].get(CONF_IMPORT_SINCE) == import_since
    else:
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_IMPORT_SINCE: error}
        assert result["description_placeholders"] == {"earliest": "01/11/2024"}


@pytest.mark.parametrize("is_pvpc", [False, True], ids=["custom", "pvpc"])
@pytest.mark.parametrize(
    "builder", [step_costs, step_formulas], ids=["costs", "formulas"]
)
def test_billing_schema_excludes_surplus(builder, is_pvpc: bool) -> None:
    """Surplus discounts are no longer configurable (assumed zero)."""
    keys = [str(key.schema) for key in builder(is_pvpc, {}).schema]
    assert not any("surplus" in key for key in keys)


@pytest.mark.parametrize(
    ("reply", "expected_error"),
    [
        # what Datadis answers to wrong credentials
        ({"status": 500, "text": '{"message": "Bad credentials"}'}, "invalid_auth"),
        ({"status": 503, "text": "Service Unavailable"}, "cannot_connect"),
        ({"exc": aiohttp.ClientConnectionError()}, "cannot_connect"),
    ],
    ids=["rejected", "unavailable", "no_connection"],
)
async def test_user_flow_with_real_connector(
    setup_integration: None,
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    reply: dict,
    expected_error: str,
) -> None:
    """The real connector, on HA's session, tells the login failures apart."""
    aioclient_mock.post(URL_TOKEN, **reply)

    result = await _submit_credentials(hass)

    assert result["errors"] == {"base": expected_error}


def _supply(cups: str, **changes):
    """Build a fake supply with another CUPS (and other fields)."""
    return build_supply().model_copy(update={"cups": cups, **changes})


def _entry(cups: str, scups: str, unique_id: str | None = None) -> MockConfigEntry:
    """Build an edata entry for ``cups`` (not set up)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=scups,
        unique_id=unique_id,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: cups,
            CONF_SCUPS: scups,
        },
    )


async def _submit_credentials(hass: HomeAssistant, **user_input):
    """Start a user flow and submit the credentials step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: USERNAME, CONF_PASSWORD: PASSWORD, **user_input},
    )


async def test_password_is_hidden_and_input_kept_after_an_error(
    setup_integration: None,
    hass: HomeAssistant,
) -> None:
    """The password field is masked; on error the NIFs are kept but not it."""
    with patch("custom_components.edata.config_flow.DatadisConnector") as connector:
        connector.return_value.async_login = AsyncMock(return_value=False)
        connector.return_value.login_status = LoginStatus.REJECTED
        result = await _submit_credentials(hass, **{CONF_AUTHORIZED_NIF: "87654321X"})

    assert result["errors"] == {"base": "invalid_auth"}
    fields = {str(key): (key, value) for key, value in result["data_schema"].schema.items()}
    password = fields[CONF_PASSWORD][1]
    assert password.config["type"] == "password"
    assert fields[CONF_USERNAME][0].default() == USERNAME
    assert fields[CONF_AUTHORIZED_NIF][0].description == {
        "suggested_value": "87654321X"
    }
    assert fields[CONF_PASSWORD][0].default is vol.UNDEFINED


@pytest.mark.parametrize(
    ("username", "authorized_nif", "stored_username", "stored_nif"),
    [
        (" 1234 5678Z ", "  ", "12345678Z", None),
        ("12345678Z", "87654321 x", "12345678Z", "87654321x"),
        # the same NIF as the username (any case) is not an authorization
        ("12345678Z", "12345678z", "12345678Z", None),
    ],
)
async def test_nifs_are_cleaned_up(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
    mock_data_manager: None,
    username: str,
    authorized_nif: str,
    stored_username: str,
    stored_nif: str | None,
) -> None:
    """Blanks are dropped from the NIFs, and a self-authorization is ignored."""
    result = await _submit_credentials(
        hass, **{CONF_USERNAME: username, CONF_AUTHORIZED_NIF: authorized_nif}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CUPS: CUPS}
    )

    assert result["data"][CONF_USERNAME] == stored_username
    assert result["data"][CONF_AUTHORIZED_NIF] == stored_nif
    assert mock_supplies.await_args.kwargs["authorized_nif"] == stored_nif


async def test_supplies_are_labelled_and_configured_ones_hidden(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
) -> None:
    """Each CUPS shows where it is; already configured CUPS are left out."""
    _entry("ES0021000000000000BB0B", "bb0b").add_to_hass(hass)  # not set up
    mock_supplies.return_value = [
        build_supply(),
        _supply("ES0021000000000000BB0B"),
        _supply("ES0021000000000000CC0C", address=None, municipality=None),
    ]

    result = await _submit_credentials(hass)

    assert result["step_id"] == "choosecups"
    selector = result["data_schema"].schema[CONF_CUPS]
    assert selector.config["options"] == [
        {"value": CUPS, "label": f"{CUPS} · FAKE STREET 1, FAKETOWN"},
        {"value": "ES0021000000000000CC0C", "label": "ES0021000000000000CC0C"},
    ]


async def test_abort_when_every_supply_is_configured(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
) -> None:
    """With nothing left to add, the flow ends instead of offering a duplicate."""
    _entry(CUPS, SCUPS, unique_id=CUPS).add_to_hass(hass)

    result = await _submit_credentials(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "all_configured"


async def test_duplicate_cups_aborts(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
) -> None:
    """A CUPS configured while the flow was open is caught by its unique ID."""
    result = await _submit_credentials(hass)
    assert result["step_id"] == "choosecups"

    _entry(CUPS, SCUPS, unique_id=CUPS).add_to_hass(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CUPS: CUPS}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_short_cups_avoids_every_entry(
    setup_integration: None,
    hass: HomeAssistant,
    mock_supplies: AsyncMock,
    mock_data_manager: None,
) -> None:
    """The short CUPS skips those of entries that are not loaded too."""
    # another supply ending the same way, configured but not set up
    _entry("ES0021000000000001AA0A", SCUPS).add_to_hass(hass)

    result = await _submit_credentials(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CUPS: CUPS}
    )

    assert result["data"][CONF_SCUPS] == "0aa0a"


def test_get_scups() -> None:
    """The shortest free suffix of 4+ characters is used."""
    assert get_scups(CUPS, set()) == "aa0a"
    assert get_scups(CUPS, {"aa0a", "0aa0a"}) == "00aa0a"


async def test_existing_entry_gets_its_unique_id(
    setup_integration: None,
    hass: HomeAssistant,
    mock_data_manager: None,
) -> None:
    """Entries created before CUPS were unique IDs get one when set up."""
    entry = _entry(CUPS.lower(), SCUPS)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.unique_id == CUPS


async def test_reauth_updates_the_password(
    setup_integration: None,
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_data_manager: None,
) -> None:
    """Re-authentication checks the new password, saves it and reloads."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["username"] == USERNAME

    with patch("custom_components.edata.config_flow.DatadisConnector") as connector:
        connector.return_value.async_login = AsyncMock(side_effect=[False, True])
        connector.return_value.login_status = LoginStatus.REJECTED
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PASSWORD: "still-wrong"}
        )
        assert result["errors"] == {"base": "invalid_auth"}

        with patch.object(hass.config_entries, "async_reload") as reload:
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_PASSWORD: "new-secret"}
            )
            await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_PASSWORD] == "new-secret"
    assert config_entry.data[CONF_CUPS] == CUPS
    reload.assert_called_once_with(config_entry.entry_id)
