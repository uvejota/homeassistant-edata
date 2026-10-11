"""Configuration flow definitions."""

from edata.models import Supply
import voluptuous as vol

from homeassistant.helpers import selector as sel

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_AUTHORIZED_NIF = "authorized_nif"
CONF_CUPS = "cups"
CONF_SCUPS = "scups"


def normalize_nif(value: str | None) -> str | None:
    """Return a NIF without blanks, or None when empty.

    The case is kept as typed: Datadis may tell it apart in a login.
    """

    if value is None:
        return None
    return "".join(value.split()) or None


def step_user(prev: dict | None = None) -> vol.Schema:
    """Build the user step schema, keeping what was typed (but the password)."""

    prev = prev or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME, default=prev.get(CONF_USERNAME, vol.UNDEFINED)
            ): str,
            vol.Required(CONF_PASSWORD): sel.TextSelector(
                sel.TextSelectorConfig(type=sel.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_AUTHORIZED_NIF,
                description={"suggested_value": prev.get(CONF_AUTHORIZED_NIF)},
            ): str,
        }
    )


def supply_label(supply: Supply) -> str:
    """Describe a supply as its CUPS followed by where it is, when known."""

    place = ", ".join(x for x in (supply.address, supply.municipality) if x)
    return f"{supply.cups} · {place}" if place else supply.cups


def step_choose_cups(supplies: list[Supply]) -> vol.Schema:
    """Build the schema to choose one of the given supplies."""

    return vol.Schema(
        {
            vol.Required(CONF_CUPS): sel.SelectSelector(
                sel.SelectSelectorConfig(
                    options=[
                        sel.SelectOptionDict(value=x.cups, label=supply_label(x))
                        for x in supplies
                    ]
                )
            ),
        }
    )
