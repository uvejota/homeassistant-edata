"""Options flow definitions."""

import typing

from edata.models import Bill
from edata.models.bill import BillingRules, PVPCBillingRules
from pydantic_core import PydanticUndefined
import voluptuous as vol

from homeassistant.helpers import selector as sel

CONF_DEBUG = "debug"
CONF_BILLING = "billing"
CONF_PVPC = "pvpc"
CONF_APPLYFROM = "apply_from"
CONF_CONFIRM = "confirm"
CONF_UPDATE_SINCE = "update_billing_since"


def step_init(prev_options: dict[str, typing.Any]) -> vol.Schema:
    """Build the options init step dict schema."""

    return vol.Schema(
        {
            vol.Required(
                CONF_DEBUG,
                default=prev_options.get(CONF_DEBUG, False),
            ): bool,
            vol.Required(
                CONF_BILLING,
                default=prev_options.get(CONF_BILLING, False),
            ): bool,
            vol.Required(
                CONF_PVPC,
                default=prev_options.get(CONF_PVPC, False),
            ): bool,
        }
    )


def _is_numeric(annotation: typing.Any) -> bool:
    """Return whether a model field annotation accepts a float value."""

    return annotation is float or float in typing.get_args(annotation)


def _numeric_default(info: typing.Any, prev: typing.Any) -> float:
    """Return a safe numeric default for a billing rule field."""

    if prev is not None:
        return prev
    if info.default is None or info.default is PydanticUndefined:
        return 0
    return info.default


def step_costs(is_pvpc: bool, prev_options: dict[str, typing.Any]) -> vol.Schema:
    """Build the options costs step dict schema with the numeric billing fields."""

    schema = {}

    rules_model = PVPCBillingRules if is_pvpc else BillingRules
    for key, info in rules_model.model_fields.items():
        if key.endswith("_formula") or not _is_numeric(info.annotation):
            continue
        schema[
            vol.Required(key, default=_numeric_default(info, prev_options.get(key)))
        ] = sel.NumberSelector(
            config=sel.NumberSelectorConfig(
                min=0, step=1e-3, mode=sel.NumberSelectorMode.BOX
            )
        )

    return vol.Schema(schema)


def step_formulas(is_pvpc: bool, prev_options: dict[str, typing.Any]) -> vol.Schema:
    """Build the options formulas step dict schema with the formula fields."""

    def tokenize(expr: str) -> str:
        return "{{ " + expr + " }}"

    schema = {}
    rules_model = PVPCBillingRules if is_pvpc else BillingRules
    for key, info in rules_model.model_fields.items():
        if not key.endswith("_formula"):
            continue
        default = prev_options.get(key, info.default) or "0"
        schema[vol.Required(key, default=tokenize(default))] = sel.TemplateSelector()

    return vol.Schema(schema)


def step_confirm(sim: Bill | None) -> vol.Schema:
    """Build the options confirm step dict schema, previewing the last month."""

    schema: dict[typing.Any, typing.Any] = {}
    if sim is not None:
        schema = {
            vol.Optional("month", default=sim.datetime.strftime("%m/%Y")): str,
            vol.Optional("value_eur", default=round(sim.value_eur, 2)): vol.Coerce(
                float
            ),
            vol.Optional("energy_term", default=round(sim.energy_term, 2)): vol.Coerce(
                float
            ),
            vol.Optional("power_term", default=round(sim.power_term, 2)): vol.Coerce(
                float
            ),
            vol.Optional("others_term", default=round(sim.others_term, 2)): vol.Coerce(
                float
            ),
        }

    schema[vol.Required(CONF_APPLYFROM)] = sel.DateSelector()
    schema[vol.Required(CONF_CONFIRM, default=False)] = bool

    return vol.Schema(schema)
