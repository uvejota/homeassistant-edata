"""Constants definition."""

DOMAIN = "edata"
STORAGE_KEY_PREAMBLE = f"{DOMAIN}.storage"

STATE_LOADING = "loading"
STATE_ERROR = "error"
STATE_READY = "ready"

# Custom configuration entries
CONF_CUPS = "cups"
CONF_SCUPS = "scups"
CONF_DEBUG = "debug"
CONF_BILLING = "billing"
CONF_PVPC = "pvpc"
CONF_SURPLUS = "surplus"
CONF_CYCLE_START_DAY = "cycle_start_day"
CONF_WIPE = "wipe_data"
CONF_AUTHORIZEDNIF = "authorized_nif"
CONF_APPLYFROM = "apply_from"
CONF_CONFIRM = "confirm"
CONF_MONTH = "month"
CONF_VALUE_EUR = "value_eur"
CONF_ENERGY_TERM = "energy_term"
CONF_POWER_TERM = "power_term"
CONF_OTHERS_TERM = "others_term"

# pricing settings
PRICE_P1_KW_YEAR = "p1_kw_year_eur"
PRICE_P2_KW_YEAR = "p2_kw_year_eur"
PRICE_P1_KWH = "p1_kwh_eur"
PRICE_P2_KWH = "p2_kwh_eur"
PRICE_P3_KWH = "p3_kwh_eur"
PRICE_SURP_P1_KWH = "surplus_p1_kwh_eur"
PRICE_SURP_P2_KWH = "surplus_p2_kwh_eur"
PRICE_SURP_P3_KWH = "surplus_p3_kwh_eur"
PRICE_METER_MONTH = "meter_month_eur"
PRICE_MARKET_KW_YEAR = "market_kw_year_eur"
PRICE_ELECTRICITY_TAX = "electricity_tax"
PRICE_IVA_TAX = "iva_tax"

DEFAULT_PRICE_P1_KW_YEAR = 30.67266
DEFAULT_PRICE_P2_KW_YEAR = 1.4243591
DEFAULT_PRICE_P1_KWH = None
DEFAULT_PRICE_P2_KWH = None
DEFAULT_PRICE_P3_KWH = None
DEFAULT_PRICE_METER_MONTH = 0.81
DEFAULT_PRICE_MARKET_KW_YEAR = 3.113
DEFAULT_PRICE_ELECTRICITY_TAX = 1.05
DEFAULT_PRICE_IVA = 1.21

BILLING_ENERGY_FORMULA = "energy_formula"
BILLING_POWER_FORMULA = "power_formula"
BILLING_OTHERS_FORMULA = "others_formula"
BILLING_SURPLUS_FORMULA = "surplus_formula"

DEFAULT_CUSTOM_BILLING_FORMULAS = {
    BILLING_ENERGY_FORMULA: "electricity_tax * iva_tax * kwh_eur * kwh",
    BILLING_POWER_FORMULA: "electricity_tax * iva_tax * (p1_kw * p1_kw_year_eur + p2_kw * p2_kw_year_eur) / 365 / 24",
    BILLING_OTHERS_FORMULA: "iva_tax * meter_month_eur / 30 / 24",
    BILLING_SURPLUS_FORMULA: "electricity_tax * iva_tax * surplus_kwh * surplus_kwh_eur",
}

DEFAULT_PVPC_BILLING_FORMULAS = {
    BILLING_ENERGY_FORMULA: "electricity_tax * iva_tax * kwh_eur * kwh",
    BILLING_POWER_FORMULA: "electricity_tax * iva_tax * (p1_kw * (p1_kw_year_eur + market_kw_year_eur) + p2_kw * p2_kw_year_eur) / 365 / 24",
    BILLING_OTHERS_FORMULA: "iva_tax * meter_month_eur / 30 / 24",
    BILLING_SURPLUS_FORMULA: "electricity_tax * iva_tax * surplus_kwh * surplus_kwh_eur",
}

DATA_STATE = "state"
DATA_ATTRIBUTES = "attributes"
DATA_SUPPLIES = "supplies"
DATA_CONTRACTS = "contracts"

WS_CONSUMPTIONS_HOUR = "ws_consumptions_hour"
WS_CONSUMPTIONS_DAY = "ws_consumptions_day"
WS_CONSUMPTIONS_MONTH = "ws_consumptions_month"
WS_MAXIMETER = "ws_maximeter"

COORDINATOR_ID = lambda scups: f"{DOMAIN}_{scups}"

STAT_TITLE_KWH = lambda id, scope: scope
STAT_TITLE_SURP_KWH = lambda id, scope: scope
STAT_TITLE_KW = lambda id, scope: scope
STAT_TITLE_EUR = lambda id, scope: scope

STAT_ID_KWH = lambda scups: f"{DOMAIN}:{scups}_consumption"
STAT_ID_P1_KWH = lambda scups: f"{DOMAIN}:{scups}_p1_consumption"
STAT_ID_P2_KWH = lambda scups: f"{DOMAIN}:{scups}_p2_consumption"
STAT_ID_P3_KWH = lambda scups: f"{DOMAIN}:{scups}_p3_consumption"

STAT_ID_SURP_KWH = lambda scups: f"{DOMAIN}:{scups}_surplus"
STAT_ID_P1_SURP_KWH = lambda scups: f"{DOMAIN}:{scups}_p1_surplus"
STAT_ID_P2_SURP_KWH = lambda scups: f"{DOMAIN}:{scups}_p2_surplus"
STAT_ID_P3_SURP_KWH = lambda scups: f"{DOMAIN}:{scups}_p3_surplus"

STAT_ID_KW = lambda scups: f"{DOMAIN}:{scups}_maximeter"
STAT_ID_P1_KW = lambda scups: f"{DOMAIN}:{scups}_p1_maximeter"
STAT_ID_P2_KW = lambda scups: f"{DOMAIN}:{scups}_p2_maximeter"

STAT_ID_EUR = lambda scups: f"{DOMAIN}:{scups}_cost"
STAT_ID_P1_EUR = lambda scups: f"{DOMAIN}:{scups}_p1_cost"
STAT_ID_P2_EUR = lambda scups: f"{DOMAIN}:{scups}_p2_cost"
STAT_ID_P3_EUR = lambda scups: f"{DOMAIN}:{scups}_p3_cost"
STAT_ID_ENERGY_EUR = lambda scups: f"{DOMAIN}:{scups}_energy_cost"
STAT_ID_P1_ENERGY_EUR = lambda scups: f"{DOMAIN}:{scups}_p1_energy_cost"
STAT_ID_P2_ENERGY_EUR = lambda scups: f"{DOMAIN}:{scups}_p2_energy_cost"
STAT_ID_P3_ENERGY_EUR = lambda scups: f"{DOMAIN}:{scups}_p3_energy_cost"
STAT_ID_POWER_EUR = lambda scups: f"{DOMAIN}:{scups}_power_cost"


WARN_INCONSISTENT_STORAGE = "Inconsistent stored data for %s, attempting to autofix it by wiping and rebuilding stats"
WARN_STATISTICS_CLEAR = "Clearing statistics for %s"
WARN_MISSING_STATS = "Statistic '%s' is missing"

# cups integrity
CUPS_CONTROL_DIGITS = "TRWAGMYFPDXBNJZSQVHLCKE"
