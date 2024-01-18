"""Data update coordinator definitions."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging
import os

from dateutil.relativedelta import relativedelta

from edata.connectors.datadis import RECENT_QUERIES_FILE
from edata.definitions import ATTRIBUTES, PricingRules
from edata.helpers import EdataHelper
from edata.processors import utils
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR, Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import const
from .stats import EdataStatistics

_LOGGER = logging.getLogger(__name__)


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics.."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        scups: str,
        authorized_nif: str,
        billing: dict[str, float] = None,
        prev_data=None,
    ) -> None:
        """Initialize the data handler.."""
        self.hass = hass

        self._experimental = False
        self._billing = None
        if billing is not None:
            self._billing = PricingRules(
                p1_kw_year_eur=billing[const.PRICE_P1_KW_YEAR],
                p2_kw_year_eur=billing[const.PRICE_P2_KW_YEAR],
                p1_kwh_eur=billing.get(const.PRICE_P1_KWH, None),
                p2_kwh_eur=billing.get(const.PRICE_P2_KWH, None),
                p3_kwh_eur=billing.get(const.PRICE_P3_KWH, None),
                meter_month_eur=billing[const.PRICE_METER_MONTH],
                market_kw_year_eur=billing[const.PRICE_MARKET_KW_YEAR],
                electricity_tax=billing[const.PRICE_ELECTRICITY_TAX],
                iva_tax=billing[const.PRICE_IVA],
                energy_formula=billing[const.BILLING_ENERGY_FORMULA],
                power_formula=billing[const.BILLING_POWER_FORMULA],
                others_formula=billing[const.BILLING_OTHERS_FORMULA],
                surplus_formula=billing.get(const.BILLING_SURPLUS_FORMULA, "0"),
            )

        self.cups = cups.upper()
        self.authorized_nif = authorized_nif
        self.id = scups.lower()

        self.is_storage_migration_complete = os.path.exists(
            self.hass.config.path(
                STORAGE_DIR, "edata", f"edata_{self.cups.lower()}.json"
            )
        )

        # init data shared store
        hass.data[const.DOMAIN][self.id] = {}

        # the api object

        if not self.is_storage_migration_complete:
            self._edata = EdataHelper(
                username,
                password,
                self.cups,
                self.authorized_nif,
                pricing_rules=self._billing,
                data=prev_data,
                storage_dir_path=self.hass.config.path(STORAGE_DIR),
            )
        else:
            self._edata = EdataHelper(
                username,
                password,
                self.cups,
                self.authorized_nif,
                pricing_rules=self._billing,
                storage_dir_path=self.hass.config.path(STORAGE_DIR),
            )

        # shared storage
        # making self._data to reference hass.data[const.DOMAIN][self.id] so we can use it like an alias
        self._data = hass.data[const.DOMAIN][self.id]
        self._data.update(
            {
                const.DATA_STATE: const.STATE_LOADING,
                const.DATA_ATTRIBUTES: {x: None for x in ATTRIBUTES},
            }
        )

        if prev_data is not None:
            self._load_data(preprocess=True)

        self.statistics = EdataStatistics(
            self.hass, self.id, self._billing is not None, self._edata
        )
        super().__init__(
            hass,
            _LOGGER,
            name=const.COORDINATOR_ID(self.id),
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API.."""

        # fetch last 365 days
        await self.hass.async_add_executor_job(
            self._edata.update,
            datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            - relativedelta(months=12),  # since: 1 year ago
            datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(minutes=1),  # to: yesterday midnight
        )

        await self.statistics.update_statistics()

        self._load_data()

        if not self.is_storage_migration_complete:
            await Store(
                self.hass,
                const.STORAGE_VERSION,
                f"{const.STORAGE_KEY_PREAMBLE}_{self.id}",
            ).async_save(utils.serialize_dict(self._edata.data))

            if os.path.isfile(RECENT_QUERIES_FILE):
                with open(
                    RECENT_QUERIES_FILE, encoding="utf8"
                ) as recent_queries_content:
                    recent_queries = json.load(recent_queries_content)
                    await Store(
                        self.hass,
                        const.STORAGE_VERSION,
                        f"{const.STORAGE_KEY_PREAMBLE}_recent_queries",
                    ).async_save(recent_queries)

        return self._data

    def _load_data(self, preprocess=False):
        """Load data found in built-in statistics into state, attributes and websockets."""

        try:
            if preprocess:
                self._edata.process_data()

            # reference to attributes shared storage
            attrs = self._data[const.DATA_ATTRIBUTES]
            attrs.update(self._edata.attributes)

            # load into websockets
            self._data[const.WS_CONSUMPTIONS_DAY] = self._edata.data[
                "consumptions_daily_sum"
            ]
            self._data[const.WS_CONSUMPTIONS_MONTH] = self._edata.data[
                "consumptions_monthly_sum"
            ]
            self._data["ws_maximeter"] = self._edata.data["maximeter"]

            # update state
            self._data["state"] = self._edata.attributes[
                "last_registered_date"
            ].strftime("%d/%m/%Y")

        except Exception:
            _LOGGER.warning("Some data is missing, will try to fetch later")
            return False

        return True
