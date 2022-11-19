"""Config flow for edata integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from edata.connectors.datadis import DatadisConnector
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from . import const

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(const.CONF_CUPS): str,
        vol.Optional(const.CONF_AUTHORIZEDNIF): str,
    }
)


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured"""


class InvalidCredentials(HomeAssistantError):
    """Error to indicate credentials are invalid"""


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    scups = data[const.CONF_CUPS][-4:]
    if hass.data.get(const.DOMAIN, {}).get(scups) is not None:
        raise AlreadyConfigured

    api = DatadisConnector(data[CONF_USERNAME], data[CONF_PASSWORD])
    result = await hass.async_add_executor_job(api.login)
    if not result:
        raise InvalidCredentials

    # Return info that you want to store in the config entry.
    return {"title": scups}


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 1

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
            info = await validate_input(self.hass, user_input)
        except AlreadyConfigured:
            errors["base"] = "already_configured"
        except InvalidCredentials:
            errors["base"] = "invalid_credentials"
        else:
            await self.async_set_unique_id(user_input[const.CONF_CUPS])
            self._abort_if_unique_id_configured()
            extra_data = {"scups": user_input[const.CONF_CUPS][-4:]}
            return self.async_create_entry(
                title=info["title"], data={**user_input, **extra_data}
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Import data from yaml config"""
        await self.async_set_unique_id(import_data[const.CONF_CUPS])
        self._abort_if_unique_id_configured()
        scups = import_data[const.CONF_CUPS][-4:]
        extra_data = {"scups": scups}
        return self.async_create_entry(title=scups, data={**import_data, **extra_data})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.inputs = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
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

    async def async_step_costs(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            for key in user_input.keys():
                self.inputs[key] = user_input[key]
            return self.async_create_entry(title="", data=self.inputs)

        base_schema = {
            vol.Required(
                const.PRICE_P1_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_P1_KW_YEAR, const.DEFAULT_PRICE_P1_KW_YEAR
                ),
            ): float,
            vol.Required(
                const.PRICE_P2_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_P2_KW_YEAR, const.DEFAULT_PRICE_P2_KW_YEAR
                ),
            ): float,
            vol.Required(
                const.PRICE_METER_MONTH,
                default=self.config_entry.options.get(
                    const.PRICE_METER_MONTH, const.DEFAULT_PRICE_METER_MONTH
                ),
            ): float,
            vol.Required(
                const.PRICE_MARKET_KW_YEAR,
                default=self.config_entry.options.get(
                    const.PRICE_MARKET_KW_YEAR,
                    const.DEFAULT_PRICE_MARKET_KW_YEAR,
                ),
            ): float,
            vol.Required(
                const.PRICE_ELECTRICITY_TAX,
                default=self.config_entry.options.get(
                    const.PRICE_ELECTRICITY_TAX,
                    const.DEFAULT_PRICE_ELECTRICITY_TAX,
                ),
            ): float,
            vol.Required(
                const.PRICE_IVA,
                default=self.config_entry.options.get(
                    const.PRICE_IVA, const.DEFAULT_PRICE_IVA
                ),
            ): float,
        }

        custom_schema = {
            vol.Required(
                const.PRICE_P1_KWH,
                default=self.config_entry.options.get(const.PRICE_P1_KWH),
            ): float,
            vol.Required(
                const.PRICE_P2_KWH,
                default=self.config_entry.options.get(const.PRICE_P2_KWH),
            ): float,
            vol.Required(
                const.PRICE_P3_KWH,
                default=self.config_entry.options.get(const.PRICE_P3_KWH),
            ): float,
        }

        return self.async_show_form(
            step_id="costs",
            data_schema=vol.Schema(base_schema)
            if self.inputs[const.CONF_PVPC]
            else vol.Schema(base_schema).extend(custom_schema),
        )
