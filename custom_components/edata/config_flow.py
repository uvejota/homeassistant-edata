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
from homeassistant.helpers import selector as sel

from . import const

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(const.CONF_AUTHORIZEDNIF): str,
    }
)

J2_EXPR_TOKENS = ("{{ ", " }}")


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured."""


class InvalidCredentials(HomeAssistantError):
    """Error to indicate credentials are invalid."""


class InvalidCups(HomeAssistantError):
    """Error to indicate cups is invalid."""


def test_login(username, password, authorized_nif=None):
    """Test login synchronously."""

    api = DatadisConnector(username, password)
    if (res := api.login()) is False:
        return res

    return api.get_supplies(authorized_nif=authorized_nif)


def get_scups(hass: HomeAssistant, cups: str) -> str:
    """Calculate a non-colliding scups."""

    for i in range(4, len(cups)):
        scups = cups[-i:].upper()
        if hass.data.get(const.DOMAIN, {}).get(scups) is None:
            break
    return scups


async def validate_step_user(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input from the 'step user'."""

    result = await hass.async_add_executor_job(
        test_login,
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data[const.CONF_AUTHORIZEDNIF],
    )

    if not result:
        raise InvalidCredentials

    # Return info that you want to store in the config entry.
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

    try:
        return proc.output["monthly"][-2]
    except Exception:
        return proc.output["monthly"][-1]


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self.inputs = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            self.inputs["cups_list"] = await validate_step_user(self.hass, user_input)
        except InvalidCredentials:
            errors["base"] = "invalid_credentials"
        else:
            self.inputs.update(user_input)
            return await self.async_step_choosecups()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_choosecups(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            self.inputs.update(user_input)
            self.inputs[const.CONF_SCUPS] = get_scups(
                self.hass, self.inputs[const.CONF_CUPS]
            )
            return self.async_create_entry(
                title=self.inputs[const.CONF_SCUPS],
                data={**self.inputs},
            )

        return self.async_show_form(
            step_id="choosecups",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        const.CONF_CUPS,
                    ): sel.SelectSelector({"options": self.inputs["cups_list"]}),
                }
            ),
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
            data_schema=vol.Schema(
                {
                    vol.Required(
                        const.CONF_DEBUG,
                        default=self.config_entry.options.get(const.CONF_DEBUG, False),
                    ): bool,
                    vol.Required(
                        const.CONF_BILLING,
                        default=self.config_entry.options.get(
                            const.CONF_BILLING, False
                        ),
                    ): bool,
                    vol.Required(
                        const.CONF_PVPC,
                        default=self.config_entry.options.get(const.CONF_PVPC, False),
                    ): bool,
                }
            ),
        )

    async def async_step_costs(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None:
            if const.PRICE_MARKET_KW_YEAR not in user_input:
                user_input[const.PRICE_MARKET_KW_YEAR] = 0
            for key in user_input:
                self.inputs[key] = user_input[key]
            return await self.async_step_formulas()

        base_schema = {
            vol.Required(
                const.PRICE_P1_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_P1_KW_YEAR, const.DEFAULT_PRICE_P1_KW_YEAR
                ),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_P2_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_P2_KW_YEAR, const.DEFAULT_PRICE_P2_KW_YEAR
                ),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_METER_MONTH,
                default=self.config_entry.options.get(
                    const.PRICE_METER_MONTH, const.DEFAULT_PRICE_METER_MONTH
                ),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_ELECTRICITY_TAX,
                default=self.config_entry.options.get(
                    const.PRICE_ELECTRICITY_TAX,
                    const.DEFAULT_PRICE_ELECTRICITY_TAX,
                ),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_IVA_TAX,
                default=self.config_entry.options.get(
                    const.PRICE_IVA_TAX,
                    const.DEFAULT_PRICE_IVA,
                ),
            ): vol.Coerce(float),
        }

        pvpc_schema = {
            vol.Required(
                const.PRICE_MARKET_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_MARKET_KW_YEAR,
                    const.DEFAULT_PRICE_MARKET_KW_YEAR,
                ),
            ): vol.Coerce(float),
        }

        nonpvpc_schema = {
            vol.Required(
                const.PRICE_P1_KWH,
                default=self.config_entry.options.get(const.PRICE_P1_KWH, 0),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_P2_KWH,
                default=self.config_entry.options.get(const.PRICE_P2_KWH, 0),
            ): vol.Coerce(float),
            vol.Required(
                const.PRICE_P3_KWH,
                default=self.config_entry.options.get(const.PRICE_P3_KWH, 0),
            ): vol.Coerce(float),
        }

        if self.inputs[const.CONF_PVPC]:
            schema = vol.Schema(base_schema).extend(pvpc_schema)
        else:
            schema = vol.Schema(base_schema).extend(nonpvpc_schema)

        return self.async_show_form(
            step_id="costs",
            data_schema=schema,
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

        formulas_schema = vol.Schema(
            {
                vol.Required(
                    const.BILLING_ENERGY_FORMULA,
                    default=J2_EXPR_TOKENS[0]
                    + self.config_entry.options.get(
                        const.BILLING_ENERGY_FORMULA,
                        const.DEFAULT_CUSTOM_BILLING_FORMULAS[
                            const.BILLING_ENERGY_FORMULA
                        ],
                    )
                    + J2_EXPR_TOKENS[1],
                ): sel.TemplateSelector(),
                vol.Required(
                    const.BILLING_POWER_FORMULA,
                    default=J2_EXPR_TOKENS[0]
                    + self.config_entry.options.get(
                        const.BILLING_POWER_FORMULA,
                        const.DEFAULT_CUSTOM_BILLING_FORMULAS[
                            const.BILLING_POWER_FORMULA
                        ],
                    )
                    + J2_EXPR_TOKENS[1],
                ): sel.TemplateSelector(),
                vol.Required(
                    const.BILLING_OTHERS_FORMULA,
                    default=J2_EXPR_TOKENS[0]
                    + self.config_entry.options.get(
                        const.BILLING_OTHERS_FORMULA,
                        const.DEFAULT_CUSTOM_BILLING_FORMULAS[
                            const.BILLING_OTHERS_FORMULA
                        ],
                    )
                    + J2_EXPR_TOKENS[1],
                ): sel.TemplateSelector(),
            }
        )

        return self.async_show_form(
            step_id="formulas",
            data_schema=formulas_schema,
        )

    async def async_step_confirm(self, user_input=None) -> FlowResult:
        """Manage the options."""

        if user_input is not None and user_input["confirm"]:
            self.inputs["update_billing_since"] = user_input["apply_from"]
            return self.async_create_entry(title="", data=self.inputs)

        confirm_schema = vol.Schema(
            {
                vol.Required(
                    "month",
                    default=self.sim["datetime"].strftime("%m/%Y"),
                ): str,
                vol.Required(
                    "value_eur",
                    default=self.sim["value_eur"],
                ): vol.Coerce(float),
                vol.Required(
                    "energy_term",
                    default=self.sim["energy_term"],
                ): vol.Coerce(float),
                vol.Required(
                    "power_term",
                    default=self.sim["power_term"],
                ): vol.Coerce(float),
                vol.Required(
                    "others_term",
                    default=self.sim["others_term"],
                ): vol.Coerce(float),
                vol.Required(
                    "apply_from",
                ): sel.DateTimeSelector(),
                vol.Required(
                    "confirm",
                    default=False,
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="confirm",
            data_schema=confirm_schema,
        )
