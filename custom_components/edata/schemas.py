"""Configuration Schemas."""

import typing

import voluptuous as vol

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector as sel

from . import const

STEP_USER = {
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Optional(const.CONF_AUTHORIZEDNIF): str,
}


def STEP_CHOOSECUPS(cups_list: list[str]) -> dict[str, typing.Any]:
    """Build the dict schema from a cups list."""

    return {
        vol.Required(
            const.CONF_CUPS,
        ): sel.SelectSelector({"options": cups_list}),
    }


def OPTIONS_STEP_INIT(prev_options: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """Build the options init step dict schema."""

    return {
        vol.Required(
            const.CONF_DEBUG,
            default=prev_options.get(const.CONF_DEBUG, False),
        ): bool,
        vol.Required(
            const.CONF_BILLING,
            default=prev_options.get(const.CONF_BILLING, False),
        ): bool,
        vol.Required(
            const.CONF_PVPC,
            default=prev_options.get(const.CONF_PVPC, False),
        ): bool,
    }


def OPTIONS_STEP_COSTS(
    is_pvpc: bool, prev_options: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    """Build the options costs step dict schema."""

    base_schema = {
        vol.Required(
            const.PRICE_P1_KW_YEAR,
            default=prev_options.get(
                const.PRICE_P1_KW_YEAR, const.DEFAULT_PRICE_P1_KW_YEAR
            ),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_P2_KW_YEAR,
            default=prev_options.get(
                const.PRICE_P2_KW_YEAR, const.DEFAULT_PRICE_P2_KW_YEAR
            ),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_METER_MONTH,
            default=prev_options.get(
                const.PRICE_METER_MONTH, const.DEFAULT_PRICE_METER_MONTH
            ),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_ELECTRICITY_TAX,
            default=prev_options.get(
                const.PRICE_ELECTRICITY_TAX,
                const.DEFAULT_PRICE_ELECTRICITY_TAX,
            ),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_IVA_TAX,
            default=prev_options.get(
                const.PRICE_IVA_TAX,
                const.DEFAULT_PRICE_IVA,
            ),
        ): vol.Coerce(float),
    }

    pvpc_schema = {
        vol.Required(
            const.PRICE_MARKET_KW_YEAR,
            default=prev_options.get(
                const.PRICE_MARKET_KW_YEAR,
                const.DEFAULT_PRICE_MARKET_KW_YEAR,
            ),
        ): vol.Coerce(float),
    }

    nonpvpc_schema = {
        vol.Required(
            const.PRICE_P1_KWH,
            default=prev_options.get(const.PRICE_P1_KWH, vol.UNDEFINED),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_P2_KWH,
            default=prev_options.get(const.PRICE_P2_KWH, vol.UNDEFINED),
        ): vol.Coerce(float),
        vol.Required(
            const.PRICE_P3_KWH,
            default=prev_options.get(const.PRICE_P3_KWH, vol.UNDEFINED),
        ): vol.Coerce(float),
    }

    schema = base_schema
    if is_pvpc:
        schema.update(pvpc_schema)
    else:
        schema.update(nonpvpc_schema)

    return schema


def OPTIONS_STEP_FORMULAS(
    is_pvpc: bool, prev_options: dict[str, typing.Any]
) -> dict[str, typing.Any]:
    """Build the options formulas step dict schema."""

    def tokenize(expr):
        return "{{ " + expr + " }}"

    if is_pvpc:
        def_formulas = const.DEFAULT_PVPC_BILLING_FORMULAS
    else:
        def_formulas = const.DEFAULT_CUSTOM_BILLING_FORMULAS

    if prev_options.get(const.CONF_PVPC, False) != is_pvpc:
        return {
            vol.Required(
                const.BILLING_ENERGY_FORMULA,
                default=tokenize(def_formulas[const.BILLING_ENERGY_FORMULA]),
            ): sel.TemplateSelector(),
            vol.Required(
                const.BILLING_POWER_FORMULA,
                default=tokenize(def_formulas[const.BILLING_POWER_FORMULA]),
            ): sel.TemplateSelector(),
            vol.Required(
                const.BILLING_OTHERS_FORMULA,
                default=tokenize(def_formulas[const.BILLING_OTHERS_FORMULA]),
            ): sel.TemplateSelector(),
        }

    return {
        vol.Required(
            const.BILLING_ENERGY_FORMULA,
            default=tokenize(
                prev_options.get(
                    const.BILLING_ENERGY_FORMULA,
                    def_formulas[const.BILLING_ENERGY_FORMULA],
                )
            ),
        ): sel.TemplateSelector(),
        vol.Required(
            const.BILLING_POWER_FORMULA,
            default=tokenize(
                prev_options.get(
                    const.BILLING_POWER_FORMULA,
                    def_formulas[const.BILLING_POWER_FORMULA],
                )
            ),
        ): sel.TemplateSelector(),
        vol.Required(
            const.BILLING_OTHERS_FORMULA,
            default=tokenize(
                prev_options.get(
                    const.BILLING_OTHERS_FORMULA,
                    def_formulas[const.BILLING_OTHERS_FORMULA],
                )
            ),
        ): sel.TemplateSelector(),
    }


def OPTIONS_STEP_CONFIRM(sim: dict[str, float] | None) -> dict[str, typing.Any]:
    """Build the options confirm step dict schema."""

    confirm_schema = {
        vol.Required(
            const.CONF_APPLYFROM,
        ): sel.DateTimeSelector(),
        vol.Required(
            const.CONF_CONFIRM,
            default=False,
        ): bool,
    }

    if sim is not None:
        sim_schema = {
            vol.Required(
                const.CONF_MONTH,
                default=sim["datetime"].strftime("%m/%Y"),
            ): str,
            vol.Required(
                const.CONF_VALUE_EUR,
                default=sim[const.CONF_VALUE_EUR],
            ): vol.Coerce(float),
            vol.Required(
                const.CONF_ENERGY_TERM,
                default=sim[const.CONF_ENERGY_TERM],
            ): vol.Coerce(float),
            vol.Required(
                const.CONF_POWER_TERM,
                default=sim[const.CONF_POWER_TERM],
            ): vol.Coerce(float),
            vol.Required(
                const.CONF_OTHERS_TERM,
                default=sim[const.CONF_OTHERS_TERM],
            ): vol.Coerce(float),
        }
        schema = sim_schema
        schema.update(confirm_schema)
        return schema

    return confirm_schema
