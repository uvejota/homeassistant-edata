"""Config flow for edata integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .const import DOMAIN, CONF_CUPS, CONF_EXPERIMENTAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_CUPS): str,
        vol.Required(CONF_EXPERIMENTAL): bool,
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
            extra_data = {"scups": user_input[CONF_CUPS][-4:]}
            return self.async_create_entry(title=info["title"], data={**user_input, **extra_data})

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class AlreadyConfigured(HomeAssistantError):
    """Error to indicate CUPS is already configured"""
