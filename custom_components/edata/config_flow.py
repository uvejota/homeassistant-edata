"""Configuration Flow (GUI)."""

import logging
import tempfile
from typing import Any

from edata.models import Bill
from edata.models.bill import BillingRules, PVPCBillingRules
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
from .core.options import (
    CONF_APPLYFROM,
    CONF_BILLING,
    CONF_CONFIRM,
    CONF_PVPC,
    CONF_UPDATE_SINCE,
    step_confirm,
    step_costs,
    step_formulas,
    step_init,
)
from .core.utils import get_shared_memory

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
) -> Bill | None:
    """Preview the last month's bill for the candidate billing options."""

    data_manager = get_shared_memory(hass, config_entry.data[CONF_SCUPS]).get(
        const.SHARED_DATAMANAGER
    )
    if data_manager is None:
        return None

    is_pvpc = data.get(CONF_PVPC, False)
    rules_model = PVPCBillingRules if is_pvpc else BillingRules
    return await data_manager.simulate_last_month(rules_model(**data), is_pvpc)


class ConfigFlow(config_entries.ConfigFlow, domain=const.DOMAIN):
    """Handle a config flow for edata."""

    VERSION = 2

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
        if not supplies:
            errors["base"] = (
                "invalid_credentials" if supplies is None else "no_supplies_found"
            )
            return self.async_show_form(
                step_id="user", data_schema=step_user(), errors=errors
            )

        self.user_input["cups_list"] = [x.cups for x in supplies]
        self.user_input.update(user_input)
        return await self.async_step_choosecups()

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
        self.sim: Bill | None = None

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

        self.sim = await simulate_last_month_billing(
            self.hass, self.config_entry, self.user_input
        )
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Confirm the billing changes and the date to apply them from."""

        if user_input is None or not user_input[CONF_CONFIRM]:
            return self.async_show_form(
                step_id="confirm",
                data_schema=step_confirm(self.sim),
            )

        self.user_input[CONF_UPDATE_SINCE] = user_input[CONF_APPLYFROM]
        return self.async_create_entry(data=self.user_input)
