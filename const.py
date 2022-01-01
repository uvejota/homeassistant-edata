DOMAIN = 'edata'
STORAGE_KEY_PREAMBLE = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

STATE_LOADING = "loading"
STATE_ERROR = "error"
STATE_READY = "ready"

ATTRIBUTES = {
    "cups": None,
    "contract_p1_kW": 'kW',
    "contract_p2_kW": 'kW',
    "yesterday_kWh": 'kWh',
    "yesterday_hours": 'h',
    "yesterday_p1_kWh": 'kWh',
    "yesterday_p2_kWh": 'kWh',
    "yesterday_p3_kWh": 'kWh',
    "month_kWh": 'kWh',
    # "month_daily_kWh": 'kWh',
    "month_days": 'd',
    "month_p1_kWh": 'kWh',
    "month_p2_kWh": 'kWh',
    "month_p3_kWh": 'kWh',
    # "month_pvpc_€": '€',
    "last_month_kWh": 'kWh',
    # "last_month_daily_kWh": 'kWh',
    "last_month_days": 'd',
    "last_month_p1_kWh": 'kWh',
    "last_month_p2_kWh": 'kWh',
    "last_month_p3_kWh": 'kWh',
    # "last_month_pvpc_€": '€',
    # "last_month_idle_W": 'W',
    "max_power_kW": 'kW',
    "max_power_date": None,
    "max_power_mean_kW": 'kW',
    "max_power_90perc_kW": 'kW',
    "last_registered_kWh_date": None
}

EXPERIMENTAL_ATTRS = []
