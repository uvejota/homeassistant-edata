"""Config flow for edata integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from edata.connectors import DatadisConnector

from .const import (
    CONF_CUPS,
    CONF_EXPERIMENTAL,
    DOMAIN,
    CONF_BILLING,
    PRICE_ELECTRICITY_TAX,
    PRICE_IVA,
    PRICE_MARKET_KW_YEAR,
    PRICE_METER_MONTH,
    PRICE_P1_KW_YEAR,
    PRICE_P1_KWH,
    PRICE_P2_KW_YEAR,
    PRICE_P2_KWH,
    PRICE_P3_KWH,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_CUPS): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    # TODO validate the data can be used to set up a connection.
    scups = data[CONF_CUPS][-4:]
    if hass.data.get(DOMAIN, {}).get(scups) is not None:
        raise AlreadyConfigured

    # Return info that you want to store in the config entry.
    return {"title": scups}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
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
        else:
            await self.async_set_unique_id(user_input[CONF_CUPS])
            self._abort_if_unique_id_configured()
            extra_data = {"scups": user_input[CONF_CUPS][-4:]}
            return self.async_create_entry(
                title=info["title"], data={**user_input, **extra_data}
            )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """Import data from yaml config"""
        await self.async_set_unique_id(import_data[CONF_CUPS])
        self._abort_if_unique_id_configured()
        scups = import_data[CONF_CUPS][-4:]
        extra_data = {"scups": scups}
        return self.async_create_entry(title=scups, data={**import_data, **extra_data})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured"""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BILLING,
                        default=self.config_entry.options.get(CONF_BILLING, False),
                    ): bool,
                    vol.Required(
                        PRICE_P1_KW_YEAR,
                        default=self.config_entry.options.get(
                            PRICE_P1_KW_YEAR, 30.67266
                        ),
                    ): float,
                    vol.Required(
                        PRICE_P2_KW_YEAR,
                        default=self.config_entry.options.get(
                            PRICE_P2_KW_YEAR, 1.4243591
                        ),
                    ): float,
                    vol.Required(
                        PRICE_P1_KWH,
                        default=self.config_entry.options.get(PRICE_P1_KWH, 0.20),
                    ): float,
                    vol.Required(
                        PRICE_P2_KWH,
                        default=self.config_entry.options.get(PRICE_P2_KWH, 0.15),
                    ): float,
                    vol.Required(
                        PRICE_P3_KWH,
                        default=self.config_entry.options.get(PRICE_P3_KWH, 0.1),
                    ): float,
                    vol.Required(
                        PRICE_METER_MONTH,
                        default=self.config_entry.options.get(PRICE_METER_MONTH, 0.81),
                    ): float,
                    vol.Required(
                        PRICE_MARKET_KW_YEAR,
                        default=self.config_entry.options.get(
                            PRICE_MARKET_KW_YEAR, 0.81
                        ),
                    ): float,
                    vol.Required(
                        PRICE_ELECTRICITY_TAX,
                        default=self.config_entry.options.get(
                            PRICE_ELECTRICITY_TAX, 1.05
                        ),
                    ): float,
                    vol.Required(
                        PRICE_IVA,
                        default=self.config_entry.options.get(PRICE_IVA, 1.1),
                    ): float,
                }
            ),
        )
