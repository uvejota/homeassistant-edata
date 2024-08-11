"""Configuration Flow (GUI)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from edata.connectors.datadis import DatadisConnector
from edata.definitions import PricingRules
from edata.processors.billing import BillingProcessor
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from . import const, schemas as sch

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


def test_login(username, password, authorized_nif=None):
    """Test login synchronously."""

    api = DatadisConnector(username, password)

    api._recent_queries = {}  # noqa: SLF001
    api._recent_cache = {}  # noqa: SLF001

    if api.login() is False:
        return None

    return api.get_supplies(authorized_nif=authorized_nif)


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

    result = await hass.async_add_executor_job(
        test_login,
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(const.CONF_AUTHORIZEDNIF, None),
    )

    if result is None:
        raise InvalidCredentials

    if not result:
        raise NoSuppliesFound

    return [x["cups"] for x in result]


async def simulate_last_month_billing(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input from the 'step formulas'."""

    coordinator_id = config_entry.data["scups"].lower()
    pricing_rules = PricingRules(
        {
            x: data[x]
            for x in data
            if x
            in (
                const.CONF_CYCLE_START_DAY,
                const.PRICE_P1_KW_YEAR,
                const.PRICE_P2_KW_YEAR,
                const.PRICE_P1_KWH,
                const.PRICE_P2_KWH,
                const.PRICE_P3_KWH,
                const.PRICE_METER_MONTH,
                const.PRICE_MARKET_KW_YEAR,
                const.PRICE_ELECTRICITY_TAX,
                const.PRICE_IVA_TAX,
                const.BILLING_ENERGY_FORMULA,
                const.BILLING_POWER_FORMULA,
                const.BILLING_OTHERS_FORMULA,
                const.BILLING_SURPLUS_FORMULA,
            )
        }
    )
    proc = BillingProcessor(
        {
            "consumptions": hass.data[const.DOMAIN][coordinator_id]["edata"].data[
                "consumptions"
            ],
            "contracts": hass.data[const.DOMAIN][coordinator_id]["edata"].data[
                "contracts"
            ],
            "prices": hass.data[const.DOMAIN][coordinator_id]["edata"].data["pvpc"],
            "rules": pricing_rules,
        }
    )

    elements = len(proc.output["monthly"])
    if elements > 1:
        return proc.output["monthly"][-2]
    elif elements == 1:  # noqa: RET505
        return proc.output["monthly"][-1]
    else:
        _LOGGER.warning(
            "Skipping simulation. This is the normal if you just changed billing to PVPC"
        )
        return None


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
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
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
            return await self.async_step_costs()

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
            return await self.async_step_formulas()

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
            return await self.async_step_confirm()

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

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(sch.OPTIONS_STEP_CONFIRM(self.sim)),
        )
