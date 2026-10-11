"""Configuration Flow (GUI)."""

from functools import partial
import logging
from typing import Any

from edata.models import Supply
from edata.models.bill import BillingRules, PVPCBillingRules
from edata.providers.datadis import DatadisConnector

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import STORAGE_DIR

from . import const
from .core.config import (
    CONF_AUTHORIZED_NIF,
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
    normalize_nif,
    step_choose_cups,
    step_user,
)
from .core.data import BillSimulation
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


def get_scups(cups: str, taken: set[str]) -> str:
    """Return the shortest CUPS suffix (4+ chars, lower case) not in ``taken``."""

    for i in range(4, len(cups)):
        scups = cups[-i:].lower()
        if scups not in taken:
            return scups
    return cups.lower()


async def simulate_last_month_billing(
    hass: HomeAssistant, config_entry: config_entries.ConfigEntry, data: dict[str, Any]
) -> BillSimulation | None:
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
        self._supplies: list[Supply] = []

    def _configured_cups(self) -> set[str]:
        """Return the CUPS of every entry, loaded or not.

        Entries created before CUPS were used as unique IDs only get one when
        they are next set up, so look at their data too.
        """
        return {
            entry.data[CONF_CUPS].upper()
            for entry in self._async_current_entries(include_ignore=False)
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the credentials check step."""
        errors = {}

        if user_input is not None:
            user_input[CONF_USERNAME] = normalize_nif(user_input[CONF_USERNAME]) or ""
            nif = normalize_nif(user_input.get(CONF_AUTHORIZED_NIF))
            if nif is not None and nif.upper() == user_input[CONF_USERNAME].upper():
                _LOGGER.warning(
                    "Ignoring authorized NIF since it is equal to the provided username"
                )
                nif = None
            user_input[CONF_AUTHORIZED_NIF] = nif

            # the connector opens its query cache on disk, so build it off the loop
            api = await self.hass.async_add_executor_job(
                partial(
                    DatadisConnector,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    storage_path=self.hass.config.path(STORAGE_DIR),
                    session=async_get_clientsession(self.hass),
                )
            )
            # log in first: a rejected login would otherwise surface as an empty
            # supply list, pointing at the CUPS or authorized NIF instead
            if not await api.async_login():
                errors["base"] = "cannot_login"
            elif not (supplies := await api.async_get_supplies(authorized_nif=nif)):
                errors["base"] = "no_supplies_found"
            else:
                configured = self._configured_cups()
                self._supplies = [
                    x for x in supplies if x.cups.upper() not in configured
                ]
                if not self._supplies:
                    return self.async_abort(reason="all_configured")
                self.user_input.update(user_input)
                return await self.async_step_choosecups()

        return self.async_show_form(
            step_id="user", data_schema=step_user(user_input), errors=errors
        )

    async def async_step_choosecups(self, user_input=None):
        """Handle the 'choose cups' step."""

        if user_input is None:
            return self.async_show_form(
                step_id="choosecups",
                data_schema=step_choose_cups(self._supplies),
            )

        cups = user_input[CONF_CUPS]
        await self.async_set_unique_id(cups.upper())
        self._abort_if_unique_id_configured()
        if cups.upper() in self._configured_cups():
            return self.async_abort(reason="already_configured")

        taken = {
            entry.data[CONF_SCUPS]
            for entry in self._async_current_entries(include_ignore=False)
        } | set(self.hass.data.get(const.DOMAIN, {}))
        scups = get_scups(cups, taken)
        return self.async_create_entry(
            title=scups,
            data={**self.user_input, CONF_CUPS: cups, CONF_SCUPS: scups},
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
        self.sim: BillSimulation | None = None

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
