"""Configuration Flow (GUI)."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from dateutil.relativedelta import relativedelta
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import STORAGE_DIR

from . import const, schemas as sch
from .edata_api import build_billing_rules

_LOGGER = logging.getLogger(__name__)

J2_EXPR_TOKENS = ("{{ ", " }}")


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured."""


class InvalidCredentials(HomeAssistantError):
    """Error to indicate credentials are invalid."""


class NoSuppliesFound(HomeAssistantError):
    """Error to indicate no supplies were found."""


class InvalidCups(HomeAssistantError):
    """Error to indicate cups is invalid."""


def build_connector(username: str, password: str):
    """Build a bare Datadis connector. Blocking, run it in an executor."""

    from edata.providers.datadis import DatadisConnector  # noqa: PLC0415

    # no storage path: supply lookups bypass the cache anyway, so this flow has
    # no reason to touch the integration database
    return DatadisConnector(username, password)


async def test_login(hass: HomeAssistant, username, password, authorized_nif=None):
    """Test login asynchronously."""

    api = await hass.async_add_executor_job(build_connector, username, password)

    if not await api.async_login():
        return None

    return await api.async_get_supplies(authorized_nif=authorized_nif)


def get_scups(hass: HomeAssistant, cups: str) -> str:
    """Calculate a non-colliding scups."""

    for i in range(4, len(cups)):
        scups = cups[-i:].lower()
        found = hass.data.get(const.DOMAIN, {}).get(scups)
        if found is None:
            break
        elif found[const.CONF_CUPS] == cups.upper():  # noqa: RET508
            raise AlreadyConfigured

    return scups


async def validate_step_user(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input from the 'step user'."""

    if data.get(const.CONF_AUTHORIZEDNIF, None) == data[CONF_USERNAME]:
        _LOGGER.warning(
            "Ignoring authorized NIF since it is equal to the provided username"
        )
        data[const.CONF_AUTHORIZEDNIF] = None

    result = await test_login(
        hass,
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(const.CONF_AUTHORIZEDNIF, None),
    )

    if result is None:
        raise InvalidCredentials

    if not result:
        raise NoSuppliesFound

    return [x.cups for x in result]


def build_bill_service(cups: str, storage_path: str):
    """Build a bill service. Blocking, run it in an executor."""

    from edata.services.bill_service import BillService  # noqa: PLC0415

    return BillService(cups, storage_path)


async def simulate_last_month_billing(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry, data: dict[str, Any]
) -> dict[str, Any]:
    """Simulate last month bill with the user input from the 'step formulas'."""

    is_pvpc = data.get(const.CONF_PVPC, True)
    billing_rules = build_billing_rules(data, is_pvpc)

    service = await hass.async_add_executor_job(
        build_bill_service,
        config_entry.data[const.CONF_CUPS].upper(),
        hass.config.path(STORAGE_DIR),
    )

    month_starts = datetime.today().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    last_month_starts = month_starts - relativedelta(months=1)

    # simulate() does not persist anything, and returns hourly bills
    bills = await service.simulate(
        billing_rules,
        is_pvpc,
        last_month_starts,
        month_starts - timedelta(minutes=1),
    )

    if not bills:
        _LOGGER.warning(
            "Skipping simulation. This is the normal if you just changed billing to PVPC"
        )
        return None

    return {
        "datetime": last_month_starts,
        const.CONF_VALUE_EUR: round(sum(x.value_eur for x in bills), 2),
        const.CONF_ENERGY_TERM: round(sum(x.energy_term for x in bills), 2),
        const.CONF_POWER_TERM: round(sum(x.power_term for x in bills), 2),
        const.CONF_OTHERS_TERM: round(sum(x.others_term for x in bills), 2),
    }


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self.inputs = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema(sch.STEP_USER)
            )

        errors = {}

        try:
            self.inputs["cups_list"] = await validate_step_user(self.hass, user_input)
        except InvalidCredentials:
            errors["base"] = "invalid_credentials"
        except NoSuppliesFound:
            errors["base"] = "no_supplies_found"
        except Exception as e:
            _LOGGER.exception(e)
        else:
            self.inputs.update(user_input)
            return await self.async_step_choosecups()

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema(sch.STEP_USER), errors=errors
        )

    async def async_step_choosecups(self, user_input=None) -> FlowResult:
        """Handle the 'choose cups' step."""

        if user_input is not None:
            self.inputs.update(user_input)
            try:
                self.inputs[const.CONF_SCUPS] = get_scups(
                    self.hass, self.inputs[const.CONF_CUPS]
                )
            except AlreadyConfigured:
                return self.async_show_form(
                    step_id="choosecups",
                    data_schema=vol.Schema(
                        sch.STEP_CHOOSECUPS(self.inputs["cups_list"])
                    ),
                    errors={"base": "already_configured"},
                )
            except Exception as e:
                _LOGGER.exception(e)

            return self.async_create_entry(
                title=self.inputs[const.CONF_SCUPS],
                data={**self.inputs},
            )

        return self.async_show_form(
            step_id="choosecups",
            data_schema=vol.Schema(sch.STEP_CHOOSECUPS(self.inputs["cups_list"])),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlowHandler:
        """Return the options flow handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self.inputs = {}
        self.sim = {}

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            user_input[const.CONF_SURPLUS] = False
            if not user_input[const.CONF_BILLING]:
                return self.async_create_entry(
                    title="",
                    data=user_input,
                )
            self.inputs = user_input
            try:
                return await self.async_step_costs()
            except Exception as e:
                _LOGGER.exception(e)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(sch.OPTIONS_STEP_INIT(self.config_entry.options)),
        )

    async def async_step_costs(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if const.PRICE_MARKET_KW_YEAR not in user_input:
                user_input[const.PRICE_MARKET_KW_YEAR] = (
                    const.DEFAULT_PRICE_MARKET_KW_YEAR
                )
            for key in user_input:
                self.inputs[key] = user_input[key]

            try:
                return await self.async_step_formulas()
            except Exception as e:
                _LOGGER.exception(e)

        return self.async_show_form(
            step_id="costs",
            data_schema=vol.Schema(
                sch.OPTIONS_STEP_COSTS(
                    self.inputs[const.CONF_PVPC], self.config_entry.options
                )
            ),
        )

    async def async_step_formulas(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if const.BILLING_SURPLUS_FORMULA not in user_input:
                user_input[const.BILLING_SURPLUS_FORMULA] = "0"

            for key in user_input:
                self.inputs[key] = (
                    user_input[key]
                    .replace(J2_EXPR_TOKENS[0].strip(), "")
                    .replace(J2_EXPR_TOKENS[1].strip(), "")
                    .strip()
                )
            self.sim = await simulate_last_month_billing(
                self.hass, self.config_entry, self.inputs
            )
            try:
                return await self.async_step_confirm()
            except Exception as e:
                _LOGGER.exception(e)

        return self.async_show_form(
            step_id="formulas",
            data_schema=vol.Schema(
                sch.OPTIONS_STEP_FORMULAS(
                    self.inputs[const.CONF_PVPC], self.config_entry.options
                )
            ),
        )

    async def async_step_confirm(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None and user_input["confirm"]:
            self.inputs["update_billing_since"] = user_input["apply_from"]
            return self.async_create_entry(title="", data=self.inputs)
        try:
            return self.async_show_form(
                step_id="confirm",
                data_schema=vol.Schema(sch.OPTIONS_STEP_CONFIRM(self.sim)),
            )
        except Exception as e:
            _LOGGER.exception(e)
