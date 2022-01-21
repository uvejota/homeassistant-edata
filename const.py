"""Constants definition"""

DOMAIN = "edata"
STORAGE_KEY_PREAMBLE = f"{DOMAIN}.storage"
STORAGE_VERSION = 1
STORAGE_ELEMENTS = ["supplies", "contracts"]

STATE_LOADING = "loading"
STATE_ERROR = "error"
STATE_READY = "ready"

# Custom configuration entries
CONF_CUPS = "cups"
CONF_PROVIDER = "provider"
CONF_EXPERIMENTAL = "experimental"
CONF_DEBUG = "debug"
CONF_BILLING = "billing"

# pricing settings
PRICE_P1_KW_YEAR = "p1_kw_year_€"
PRICE_P2_KW_YEAR = "p2_kw_year_€"
PRICE_P1_KWH = "p1_kwh_€"
PRICE_P2_KWH = "p2_kwh_€"
PRICE_P3_KWH = "p3_kwh_€"
PRICE_METER_MONTH = "meter_month_€"
PRICE_MARKET_KW_YEAR = "market_kw_year_€"
PRICE_ELECTRICITY_TAX = "electricity_tax"
PRICE_IVA = "iva"

DATA_STATE = "state"
DATA_ATTRIBUTES = "attributes"
DATA_SUPPLIES = "supplies"
DATA_CONTRACTS = "contracts"

WS_CONSUMPTIONS_HOUR = "ws_consumptions_hour"
WS_CONSUMPTIONS_DAY = "ws_consumptions_day"
WS_CONSUMPTIONS_MONTH = "ws_consumptions_month"
WS_MAXIMETER = "ws_maximeter"

# sensor attributes
ATTRIBUTES = {
    "cups": None,
    "contract_p1_kW": "kW",
    "contract_p2_kW": "kW",
    "yesterday_kWh": "kWh",
    "yesterday_hours": "h",
    "yesterday_p1_kWh": "kWh",
    "yesterday_p2_kWh": "kWh",
    "yesterday_p3_kWh": "kWh",
    "month_kWh": "kWh",
    "month_daily_kWh": "kWh",
    "month_days": "d",
    "month_p1_kWh": "kWh",
    "month_p2_kWh": "kWh",
    "month_p3_kWh": "kWh",
    # "month_pvpc_€": '€',
    "last_month_kWh": "kWh",
    "last_month_daily_kWh": "kWh",
    "last_month_days": "d",
    "last_month_p1_kWh": "kWh",
    "last_month_p2_kWh": "kWh",
    "last_month_p3_kWh": "kWh",
    # "last_month_pvpc_€": '€',
    # "last_month_idle_W": 'W',
    "max_power_kW": "kW",
    "max_power_date": None,
    "max_power_mean_kW": "kW",
    "max_power_90perc_kW": "kW",
}

EXPERIMENTAL_ATTRS = []

COORDINATOR_ID = lambda scups: f"{DOMAIN}_{scups}"

STAT_TITLE_KWH = lambda id, scope: f"{DOMAIN}_{id} {scope} energy consumption"
STAT_TITLE_KW = lambda id, scope: f"{DOMAIN}_{id} {scope} maximeter"

STAT_ID_KWH = lambda scups: f"{DOMAIN}:{scups}_consumption"
STAT_ID_P1_KWH = lambda scups: f"{DOMAIN}:{scups}_p1_consumption"
STAT_ID_P2_KWH = lambda scups: f"{DOMAIN}:{scups}_p2_consumption"
STAT_ID_P3_KWH = lambda scups: f"{DOMAIN}:{scups}_p3_consumption"

STAT_ID_KW = lambda scups: f"{DOMAIN}:{scups}_maximeter"
STAT_ID_P1_KW = lambda scups: f"{DOMAIN}:{scups}_p1_maximeter"
STAT_ID_P2_KW = lambda scups: f"{DOMAIN}:{scups}_p2_maximeter"

WARN_INCONSISTENT_STORAGE = "Inconsistent stored data for %s, attempting to autofix it by wiping and rebuilding stats"
WARN_STATISTICS_CLEAR = "Clearing statistics for %s"
WARN_MISSING_STATS = "Some stats are missing for %s"
