import logging
from datetime import datetime, timedelta

import numpy as np
from dateutil.relativedelta import relativedelta
from edata.connectors import DatadisConnector
from edata.processors import DataUtils as du
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    day_start_end,
    get_last_statistics,
    month_start_end,
    statistics_during_period,
)
from homeassistant.const import ENERGY_KILO_WATT_HOUR, POWER_KILO_WATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTES,
    DOMAIN,
    STATE_LOADING,
    STATE_READY,
    STORAGE_ELEMENTS,
    STORAGE_KEY_PREAMBLE,
    STORAGE_VERSION,
)
from .data import init_consumption, init_maxpower
from .store import DateTimeEncoder

_LOGGER = logging.getLogger(__name__)


class EdataCoordinator(DataUpdateCoordinator):
    """Handle Datadis data and statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        cups: str,
        prev_data=None,
    ) -> None:
        """Initialize the data handler."""
        self.hass = hass
        self.reset = prev_data is None

        self._experimental = False
        self._cups = cups.upper()
        self.id = self._cups[-4:].lower()

        hass.data[DOMAIN][self.id.upper()] = {}
        # making self._data to reference hass.data[DOMAIN][self.id.upper()] so we can use it like an alias
        self._data = hass.data[DOMAIN][self.id.upper()]
        self._data.update(
            {
                "state": STATE_LOADING,
                "attributes": {x: None for x in ATTRIBUTES},
                "supplies": [],
                "contracts": [],
            }
        )
        if prev_data is not None:
            self._data.update(prev_data)

        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "p3_kW", "kW"]

        self.stat_ids = {
            "kWh": f"{DOMAIN}:{self.id}_consumption",
            "p1_kWh": f"{DOMAIN}:{self.id}_p1_consumption",
            "p2_kWh": f"{DOMAIN}:{self.id}_p2_consumption",
            "p3_kWh": f"{DOMAIN}:{self.id}_p3_consumption",
            "kW": f"{DOMAIN}:{self.id}_maximeter",
            "p1_kW": f"{DOMAIN}:{self.id}_p1_maximeter",
            "p2_kW": f"{DOMAIN}:{self.id}_p2_maximeter",
            "p3_kW": f"{DOMAIN}:{self.id}_p3_maximeter",
        }

        self._datadis = DatadisConnector(username, password, data=prev_data)

        super().__init__(
            hass,
            _LOGGER,
            name=f"edata_{self.id}",
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self):
        """Update data via API."""

        # preload attributes if first boot
        if self._data.get("state", STATE_LOADING) == STATE_LOADING:
            if False is await self.load_data():
                self.reset = True
                _LOGGER.warning(
                    "Inconsistent stored data for %s, attempting to autofix it by wiping and rebuilding stats",
                    self.id.upper(),
                )

        # reset stats if no storage file was found
        if self.reset:
            _LOGGER.warning(
                "Clearing statistics for %s",
                [self.stat_ids[x] for x in self.stat_ids],
            )
            await self.hass.async_add_executor_job(
                clear_statistics,
                self.hass.data[DATA_INSTANCE],
                [self.stat_ids[x] for x in self.stat_ids],
            )

        # fetch last statistics found
        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.stat_ids[x], True
            )
            for x in self.stat_ids
        }

        # retrieve sum for summable stats (consumptions)
        _sum = {
            x: last_stats[x][self.stat_ids[x]][0].get("sum", 0) if last_stats[x] else 0
            for x in self.consumption_stats
        }

        try:
            last_kWh_record = last_stats["kWh"][self.stat_ids["kWh"]][0]["end"]
            _LOGGER.info("Last consumptions record was at %s", last_kWh_record)
        except KeyError as _:
            last_kWh_record = None
            _LOGGER.warning("No consumption stats found")

        try:
            last_kW_record = last_stats["kW"][self.stat_ids["kW"]][0]["end"]
            _LOGGER.info("Last maximeter record was at %s", last_kW_record)
        except KeyError as _:
            last_kW_record = None
            _LOGGER.warning("No maximeter stats found")

        await self.hass.async_add_executor_job(
            self._datadis.update,
            self._cups,
            min(
                dt_util.parse_datetime(last_kWh_record).replace(tzinfo=None),
                dt_util.parse_datetime(last_kW_record).replace(tzinfo=None),
                datetime.today() - timedelta(days=30),
            )
            if last_kWh_record is not None and last_kW_record is not None
            else datetime.today() - timedelta(days=365),
            datetime.today(),
        )

        self._data.update(self._datadis.data)

        new_stats = {x: [] for x in self.stat_ids}
        something_changed = False

        _LABEL_kWh = "value_kWh"
        for data in self._datadis.data.get("consumptions", {}):
            if last_kWh_record is None or dt_util.as_local(
                data["datetime"]
            ) >= dt_util.parse_datetime(last_kWh_record):
                something_changed = True
                _p = du.get_pvpc_tariff(data["datetime"])
                _sum["kWh"] += data[_LABEL_kWh]
                new_stats["kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_LABEL_kWh],
                        sum=_sum["kWh"],
                    )
                )
                _sum[_p + "_kWh"] += data[_LABEL_kWh]
                new_stats[_p + "_kWh"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]),
                        state=data[_LABEL_kWh],
                        sum=_sum[_p + "_kWh"],
                    )
                )

        _LABEL_kW = "value_kW"
        for data in self._datadis.data.get("maximeter", {}):
            if last_kW_record is None or dt_util.as_local(
                data["datetime"]
            ) >= dt_util.parse_datetime(last_kW_record):
                something_changed = True
                _p = du.get_pvpc_tariff(data["datetime"])
                new_stats["kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_LABEL_kW],
                        mean=data[_LABEL_kW],
                    )
                )
                new_stats[_p + "_kW"].append(
                    StatisticData(
                        start=dt_util.as_local(data["datetime"]).replace(minute=0),
                        state=data[_LABEL_kW],
                        mean=data[_LABEL_kW],
                    )
                )

        for _scope in self.consumption_stats:
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"{DOMAIN}_{self.id} {_scope} energy consumption",
                source=DOMAIN,
                statistic_id=self.stat_ids[_scope],
                unit_of_measurement=ENERGY_KILO_WATT_HOUR,
            )
            _LOGGER.info("Adding new stats to %s", self.stat_ids[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        for _scope in self.maximeter_stats:
            metadata = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=f"{DOMAIN}_{self.id} {_scope} maximeter",
                source=DOMAIN,
                statistic_id=self.stat_ids[_scope],
                unit_of_measurement=POWER_KILO_WATT,
            )
            _LOGGER.info("Adding new stats to %s", self.stat_ids[_scope])
            async_add_external_statistics(self.hass, metadata, new_stats[_scope])

        # compile state and attributes
        if something_changed:
            ## Load contractual data
            if False is await self.load_data() and not self.reset:
                _LOGGER.warning(
                    "Inconsistent stored data for %s, attempting to autofix it by wiping and rebuilding stats",
                    self.id.upper(),
                )
                await self._async_update_data()

        # put reset flag down
        if self.reset:
            self.reset = False

        return self._data

    async def load_data(self):
        """Load data found in built-in statistics into state, attributes and websockets"""

        attrs = self._data["attributes"]  # reference to attributes shared storage

        # anonymous function to sort dicts based of datetime key, and return a list of dicts for using in websockets
        build_ws_data = lambda dict_shaped_data: sorted(
            [dict_shaped_data[element] for element in dict_shaped_data],
            key=lambda item: dt_util.parse_datetime(item["datetime"]),
        )

        # add supplies-related attributes
        attrs.update(
            {
                "cups": self._cups
                if self._cups in [x["cups"] for x in self._data["supplies"]]
                else None
            }
        )

        # add contract-related attributes
        attrs.update(
            {
                "contract_p1_kW": self._data["contracts"][-1].get("power_p1", None)
                if len(self._data["contracts"]) > 0
                else None,
                "contract_p2_kW": self._data["contracts"][-1].get("power_p2", None)
                if len(self._data["contracts"]) > 0
                else None,
            }
        )

        # read last statistics
        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.stat_ids[x], True
            )
            for x in self.stat_ids
        }

        # store last record datetime
        try:
            last_record_dt = {
                x: dt_util.as_local(
                    dt_util.parse_datetime(last_stats[x][self.stat_ids[x]][0]["end"])
                )
                for x in self.stat_ids
            }
        except KeyError as _:
            return False

        # Load consumptions
        consumptions = {}
        for aggr in ("month", "day"):
            # for each aggregation method (month/day)
            _stats = await self.hass.async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_local(datetime(1970, 1, 1)),
                None,
                [self.stat_ids[x] for x in self.consumption_stats],
                aggr,
            )
            consumptions[aggr] = {}
            for key in _stats:
                # for each stat key (p1, p2, p3...)
                _sum = 0
                for stat in _stats[key]:
                    # for each stat record
                    dt_iso = dt_util.as_local(
                        dt_util.parse_datetime(stat["start"])
                    ).isoformat()
                    if dt_iso not in consumptions[aggr]:
                        # if first element, initialize a Consumption structure
                        consumptions[aggr][dt_iso] = init_consumption(dt_iso)
                    for scope in self.consumption_stats:
                        # for each stat id
                        if self.stat_ids[scope] == stat["statistic_id"]:
                            _key = f"value_{scope}"
                            _inc = round(stat["sum"] - _sum, 1)
                            consumptions[aggr][dt_iso][_key] = _inc
                            _sum = stat["sum"]
                            if _inc < 0:
                                # if negative increment, data has to be wiped
                                return False
                            break

            # load into websockets
            self._data[f"ws_consumptions_{aggr}"] = build_ws_data(consumptions[aggr])

        # yesterday attributes
        _date_str = dt_util.as_local(
            day_start_end(datetime.now() - timedelta(days=1))[0]
        ).isoformat()
        if _date_str in consumptions["day"]:
            attrs["yesterday_kWh"] = consumptions["day"][_date_str]["value_kWh"]
            attrs["yesterday_p1_kWh"] = consumptions["day"][_date_str]["value_p1_kWh"]
            attrs["yesterday_p2_kWh"] = consumptions["day"][_date_str]["value_p2_kWh"]
            attrs["yesterday_p3_kWh"] = consumptions["day"][_date_str]["value_p3_kWh"]
            attrs["yesterday_hours"] = round(
                (
                    last_record_dt["kWh"] - day_start_end(last_record_dt["kWh"])[0]
                ).seconds
                / 3600,
                2,
            )
        # current month attributes
        cmdates = month_start_end(datetime.now().replace(day=1))
        _date_str = dt_util.as_local(cmdates[0]).isoformat()
        if _date_str in consumptions["month"]:
            attrs["month_kWh"] = consumptions["month"][_date_str]["value_kWh"]
            attrs["month_p1_kWh"] = consumptions["month"][_date_str]["value_p1_kWh"]
            attrs["month_p2_kWh"] = consumptions["month"][_date_str]["value_p2_kWh"]
            attrs["month_p3_kWh"] = consumptions["month"][_date_str]["value_p3_kWh"]
            attrs["month_days"] = round(
                (last_record_dt["kWh"] - month_start_end(last_record_dt["kWh"])[0]).days
            )
            attrs["month_daily_kWh"] = round(
                attrs["month_kWh"] / attrs["month_days"], 1
            )

        # last month attributes
        lmdates = month_start_end(cmdates[0] - relativedelta(months=1))
        _date_str = dt_util.as_local(lmdates[0]).isoformat()
        if _date_str in consumptions["month"]:
            attrs["last_month_kWh"] = consumptions["month"][_date_str]["value_kWh"]
            attrs["last_month_p1_kWh"] = consumptions["month"][_date_str][
                "value_p1_kWh"
            ]
            attrs["last_month_p2_kWh"] = consumptions["month"][_date_str][
                "value_p2_kWh"
            ]
            attrs["last_month_p3_kWh"] = consumptions["month"][_date_str][
                "value_p3_kWh"
            ]
            attrs["last_month_days"] = round(
                (
                    month_start_end(last_record_dt["kWh"])[0]
                    - (
                        month_start_end(last_record_dt["kWh"])[0]
                        - relativedelta(months=1)
                    )
                ).days,
                2,
            )
            attrs["last_month_daily_kWh"] = round(
                attrs["last_month_kWh"] / attrs["last_month_days"], 1
            )

        # Load maximeter
        _stats = await self.hass.async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.as_local(datetime(1970, 1, 1)),
            None,
            [self.stat_ids[x] for x in self.maximeter_stats],
            "hour",
        )

        maximeter = {}
        for key in _stats:
            for stat in _stats[key]:
                dt_iso = dt_util.as_local(
                    dt_util.parse_datetime(stat["start"])
                ).isoformat()
                if dt_iso not in maximeter:
                    maximeter[dt_iso] = init_maxpower(dt_iso)
                for _scope in self.maximeter_stats:
                    if self.stat_ids[_scope] == stat["statistic_id"]:
                        _key = f"value_{_scope}"
                        maximeter[dt_iso][_key] = round(stat["mean"], 1)
                        break

        # load into websockets
        self._data["ws_maximeter"] = build_ws_data(maximeter)

        # load maximeter attributes
        values = np.array([x["value_kW"] for x in self._data["ws_maximeter"]])
        max_idx = np.argmax(values)

        attrs["max_power_kW"] = self._data["ws_maximeter"][max_idx]["value_kW"]
        attrs["max_power_date"] = self._data["ws_maximeter"][max_idx]["datetime"]
        attrs["max_power_mean_kW"] = round(np.mean(values), 1)
        attrs["max_power_90perc_kW"] = round(np.percentile(values, 90), 1)

        # update state
        self._data["state"] = STATE_READY

        await Store(
            self.hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREAMBLE}_{self.id.upper()}",
            encoder=DateTimeEncoder,
        ).async_save({x: self._datadis.data[x] for x in STORAGE_ELEMENTS})

        return True
