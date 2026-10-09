"""Configuration flow definitions."""

import voluptuous as vol

from homeassistant.helpers import selector as sel

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_AUTHORIZED_NIF = "authorized_nif"
CONF_CUPS = "cups"
CONF_SCUPS = "scups"


def step_user() -> vol.Schema:
    """Build the user step schema."""

    return vol.Schema(
        {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_AUTHORIZED_NIF): str,
        }
    )


def step_choose_cups(cups_list: list[str]) -> vol.Schema:
    """Build the schema from a cups list."""

    return vol.Schema(
        {
            vol.Required(
                CONF_CUPS,
            ): sel.SelectSelector({"options": cups_list}),
        }
    )
