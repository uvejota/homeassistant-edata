"""Configuration Flow (GUI)."""

import logging
import tempfile
from typing import Any

from edata.providers.datadis import DatadisConnector

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback

from . import const
from .core.config import (
    CONF_AUTHORIZED_NIF,
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
    step_choose_cups,
    step_user,
)
from .core.options import CONF_BILLING, CONF_PVPC, step_costs, step_formulas, step_init

_LOGGER = logging.getLogger(__name__)

J2_EXPR_TOKENS = ("{{ ", " }}")


def get_scups(hass: HomeAssistant, cups: str) -> None | str:
    """Calculate a non-colliding scups."""

    for i in range(4, len(cups)):
        scups = cups[-i:].lower()
        found = hass.data.get(const.DOMAIN, {}).get(scups)
        if found is None:
            break
        elif found[CONF_CUPS] == cups.upper():  # noqa: RET508
            return None

    return scups


async def simulate_last_month_billing(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry, data: dict[str, Any]
) -> dict[str, Any] | None:
    """Validate the user input from the 'step formulas'."""

    # TODO: Implement simulation once edata package supports it
    # For now, skip simulation and continue with configuration
    _LOGGER.warning(
        "Billing simulation not yet implemented with new API, skipping simulation"
    )
    return None


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        super().__init__()
        self.user_input = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the credentials check step."""
        errors = {}

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=step_user())

        if user_input.get(CONF_AUTHORIZED_NIF, None) == user_input[CONF_USERNAME]:
            _LOGGER.warning(
                "Ignoring authorized NIF since it is equal to the provided username"
            )
            user_input[CONF_AUTHORIZED_NIF] = None

        api = DatadisConnector(
            user_input[CONF_USERNAME],
            user_input[CONF_PASSWORD],
            storage_path=tempfile.gettempdir(),
        )
        supplies = await api.async_get_supplies(
            authorized_nif=user_input.get(CONF_AUTHORIZED_NIF)
        )
        if supplies is None:
            errors["base"] = "invalid_credentials"
        if not supplies:
            errors["base"] = "no_supplies_found"
        self.user_input["cups_list"] = [x.cups for x in supplies]

        if not errors:
            self.user_input.update(user_input)
            return await self.async_step_choosecups()

        return self.async_show_form(
            step_id="user", data_schema=step_user(), errors=errors
        )

    async def async_step_choosecups(self, user_input=None):
        """Handle the 'choose cups' step."""
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="choosecups",
                data_schema=step_choose_cups(self.user_input["cups_list"]),
            )

        self.user_input.update(user_input)
        scups = get_scups(self.hass, self.user_input[CONF_CUPS])

        if scups is None:
            errors.update({"base": "already_configured"})

        if not errors:
            self.user_input[CONF_SCUPS] = scups
            return self.async_create_entry(
                title=self.user_input[CONF_SCUPS],
                data={**self.user_input},
            )

        return self.async_show_form(
            step_id="choosecups",
            data_schema=step_choose_cups(self.user_input["cups_list"]),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Provide options for edata."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self.user_input = {}

    async def async_step_init(self, user_input=None):
        """Manage the options."""

        if user_input is None:
            return self.async_show_form(
                step_id="init",
                data_schema=step_init(prev_options=self.config_entry.options.copy()),
            )

        if not user_input[CONF_BILLING]:
            return self.async_create_entry(
                data=user_input,
            )

        self.user_input = user_input
        return await self.async_step_costs()

    async def async_step_costs(self, user_input=None):
        """Manage the options."""

        if user_input is None:
            return self.async_show_form(
                step_id="costs",
                data_schema=step_costs(
                    self.user_input[CONF_PVPC], self.config_entry.options.copy()
                ),
            )

        for key in user_input:
            self.user_input[key] = user_input[key]

        return await self.async_step_formulas()

    async def async_step_formulas(self, user_input=None):
        """Manage the options."""

        if user_input is None:
            return self.async_show_form(
                step_id="formulas",
                data_schema=step_formulas(
                    self.user_input[CONF_PVPC], self.config_entry.options.copy()
                ),
            )

        for key in user_input:
            self.user_input[key] = (
                user_input[key]
                .replace(J2_EXPR_TOKENS[0].strip(), "")
                .replace(J2_EXPR_TOKENS[1].strip(), "")
                .strip()
            )

        return self.async_create_entry(data=self.user_input)
