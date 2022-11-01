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
CONF_PVPC = "pvpc"
CONF_WIPE = "wipe_data"
CONF_AUTHORIZEDNIF = "authorized_nif"

# pricing settings
PRICE_P1_KW_YEAR = "p1_kw_year_eur"
PRICE_P2_KW_YEAR = "p2_kw_year_eur"
PRICE_P1_KWH = "p1_kwh_eur"
PRICE_P2_KWH = "p2_kwh_eur"
PRICE_P3_KWH = "p3_kwh_eur"
PRICE_METER_MONTH = "meter_month_eur"
PRICE_MARKET_KW_YEAR = "market_kw_year_eur"
PRICE_ELECTRICITY_TAX = "electricity_tax"
PRICE_IVA = "iva"

DEFAULT_PRICE_P1_KW_YEAR = 30.67266
DEFAULT_PRICE_P2_KW_YEAR = 1.4243591
DEFAULT_PRICE_P1_KWH = None
DEFAULT_PRICE_P2_KWH = None
DEFAULT_PRICE_P3_KWH = None
DEFAULT_PRICE_METER_MONTH = 0.81
DEFAULT_PRICE_MARKET_KW_YEAR = 3.113
DEFAULT_PRICE_ELECTRICITY_TAX = 1.05
DEFAULT_PRICE_IVA = 1.05

DATA_STATE = "state"
DATA_ATTRIBUTES = "attributes"
DATA_SUPPLIES = "supplies"
DATA_CONTRACTS = "contracts"

WS_CONSUMPTIONS_HOUR = "ws_consumptions_hour"
WS_CONSUMPTIONS_DAY = "ws_consumptions_day"
WS_CONSUMPTIONS_MONTH = "ws_consumptions_month"
WS_MAXIMETER = "ws_maximeter"

COORDINATOR_ID = lambda scups: f"{DOMAIN}_{scups}"

STAT_TITLE_KWH = lambda id, scope: f"{id.upper()} {scope} consumption"
STAT_TITLE_KW = lambda id, scope: f"{id.upper()} {scope} maximeter"
STAT_TITLE_EUR = lambda id, scope: f"{id.upper()} {scope} cost"

STAT_ID_KWH = lambda scups: f"{DOMAIN}:{scups}_consumption"
STAT_ID_P1_KWH = lambda scups: f"{DOMAIN}:{scups}_p1_consumption"
STAT_ID_P2_KWH = lambda scups: f"{DOMAIN}:{scups}_p2_consumption"
STAT_ID_P3_KWH = lambda scups: f"{DOMAIN}:{scups}_p3_consumption"

STAT_ID_KW = lambda scups: f"{DOMAIN}:{scups}_maximeter"
STAT_ID_P1_KW = lambda scups: f"{DOMAIN}:{scups}_p1_maximeter"
STAT_ID_P2_KW = lambda scups: f"{DOMAIN}:{scups}_p2_maximeter"

STAT_ID_EUR = lambda scups: f"{DOMAIN}:{scups}_cost"
STAT_ID_ENERGY_EUR = lambda scups: f"{DOMAIN}:{scups}_energy_cost"
STAT_ID_POWER_EUR = lambda scups: f"{DOMAIN}:{scups}_power_cost"


WARN_INCONSISTENT_STORAGE = "Inconsistent stored data for %s, attempting to autofix it by wiping and rebuilding stats"
WARN_STATISTICS_CLEAR = "Clearing statistics for %s"
WARN_MISSING_STATS = "Some stats are missing for %s"
