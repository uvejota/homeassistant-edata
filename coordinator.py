import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from edata.processors import DataUtils as du
from homeassistant.core import HomeAssistant
from homeassistant.components.recorder.const import DATA_INSTANCE
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    clear_statistics,
    get_last_statistics,
    statistics_during_period,
    month_start_end,
    day_start_end,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR,
    POWER_KILO_WATT,
)

from homeassistant.util import dt as dt_util

from .const import *
from .websockets import *
from edata.connectors import DatadisConnector
from .store import DateTimeEncoder

import numpy as np

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

        self._data = {
            "state": STATE_LOADING,
            "attributes": {x: None for x in ATTRIBUTES},
        }
        if prev_data is not None:
            self._data.update(prev_data)

        self.consumption_stats = ["p1_kWh", "p2_kWh", "p3_kWh", "kWh"]
        self.maximeter_stats = ["p1_kW", "p2_kW", "p3_kW", "kW"]

        hass.data[DOMAIN][self.id.upper()] = {}

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
            else datetime(1970, 1, 1),
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
        if something_changed or self._data.get("state", STATE_LOADING) != STATE_READY:
            ## Load contractual data
            await self.load_data()

        return self._data

    async def load_data(self):

        attrs = {x: None for x in ATTRIBUTES}

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

        last_stats = {
            x: await self.hass.async_add_executor_job(
                get_last_statistics, self.hass, 1, self.stat_ids[x], True
            )
            for x in self.stat_ids
        }

        last_records = {
            x: dt_util.as_local(
                dt_util.parse_datetime(last_stats[x][self.stat_ids[x]][0]["end"])
            )
            for x in self.stat_ids
        }

        # Load consumptions
        compiled_stats = {}
        for _aggr_method in ("month", "day"):
            _stats = await self.hass.async_add_executor_job(
                statistics_during_period,
                self.hass,
                dt_util.as_local(datetime(1970, 1, 1)),
                None,
                [self.stat_ids[x] for x in self.consumption_stats],
                _aggr_method,
            )
            compiled_stats[_aggr_method] = {}
            for key in _stats:
                _sum = 0
                for stat in _stats[key]:
                    _dt = dt_util.as_local(dt_util.parse_datetime(stat["start"]))
                    isodate = _dt.isoformat()
                    if isodate not in compiled_stats[_aggr_method]:
                        compiled_stats[_aggr_method][isodate] = {
                            "datetime": isodate,
                            "value_kWh": 0,
                            "value_p1_kWh": 0,
                            "value_p2_kWh": 0,
                            "value_p3_kWh": 0,
                        }
                    for _scope in self.consumption_stats:
                        if self.stat_ids[_scope] == stat["statistic_id"]:
                            _key = f"value_{_scope}"
                            _inc = round(stat["sum"] - _sum, 1)
                            compiled_stats[_aggr_method][isodate][_key] = _inc
                            _sum = stat["sum"]
                            if _inc < 0:
                                return False
                            break

            # load into websockets
            self.hass.data[DOMAIN][self.id.upper()][
                f"ws_consumptions_{_aggr_method}"
            ] = sorted(
                [compiled_stats[_aggr_method][x] for x in compiled_stats[_aggr_method]],
                key=lambda d: dt_util.parse_datetime(d["datetime"]),
            )

        # yesterday attributes
        ydates = day_start_end(datetime.now() - timedelta(days=1))
        _date_str = dt_util.as_local(ydates[0]).isoformat()
        if _date_str in compiled_stats["day"]:
            attrs["yesterday_kWh"] = compiled_stats["day"][_date_str]["value_kWh"]
            attrs["yesterday_p1_kWh"] = compiled_stats["day"][_date_str]["value_p1_kWh"]
            attrs["yesterday_p2_kWh"] = compiled_stats["day"][_date_str]["value_p2_kWh"]
            attrs["yesterday_p3_kWh"] = compiled_stats["day"][_date_str]["value_p3_kWh"]
            attrs["yesterday_hours"] = round(
                (
                    last_records["kWh"]
                    - last_records["kWh"].replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                ).seconds
                / 3600,
                2,
            )
        # current month attributes
        cmdates = month_start_end(datetime.now().replace(day=1))
        _date_str = dt_util.as_local(cmdates[0]).isoformat()
        if _date_str in compiled_stats["month"]:
            attrs["month_kWh"] = compiled_stats["month"][_date_str]["value_kWh"]
            attrs["month_p1_kWh"] = compiled_stats["month"][_date_str]["value_p1_kWh"]
            attrs["month_p2_kWh"] = compiled_stats["month"][_date_str]["value_p2_kWh"]
            attrs["month_p3_kWh"] = compiled_stats["month"][_date_str]["value_p3_kWh"]
            attrs["month_days"] = round(
                (
                    last_records["kWh"]
                    - last_records["kWh"].replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    )
                ).days
            )
            attrs["month_daily_kWh"] = round(
                attrs["month_kWh"] / attrs["month_days"], 1
            )
        # last month attributes
        lmdates = month_start_end(cmdates[0] - relativedelta(months=1))
        _date_str = dt_util.as_local(lmdates[0]).isoformat()
        if _date_str in compiled_stats["month"]:
            attrs["last_month_kWh"] = compiled_stats["month"][_date_str]["value_kWh"]
            attrs["last_month_p1_kWh"] = compiled_stats["month"][_date_str][
                "value_p1_kWh"
            ]
            attrs["last_month_p2_kWh"] = compiled_stats["month"][_date_str][
                "value_p2_kWh"
            ]
            attrs["last_month_p3_kWh"] = compiled_stats["month"][_date_str][
                "value_p3_kWh"
            ]
            attrs["last_month_days"] = round(
                (
                    last_records["kWh"].replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    )
                    - (
                        last_records["kWh"].replace(
                            day=1, hour=0, minute=0, second=0, microsecond=0
                        )
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

        compiled_stats = {}
        for key in _stats:
            for stat in _stats[key]:
                _dt = dt_util.as_local(dt_util.parse_datetime(stat["start"]))
                isodate = _dt.isoformat()
                if isodate not in compiled_stats:
                    compiled_stats[isodate] = {
                        "datetime": isodate,
                        "value_kW": 0,
                        "value_p1_kW": 0,
                        "value_p2_kW": 0,
                        "value_p3_kW": 0,
                    }
                for _scope in self.maximeter_stats:
                    if self.stat_ids[_scope] == stat["statistic_id"]:
                        _key = f"value_{_scope}"
                        compiled_stats[isodate][_key] = round(stat["mean"], 1)
                        break

        # load into websockets
        self.hass.data[DOMAIN][self.id.upper()]["ws_maximeter"] = sorted(
            [compiled_stats[x] for x in compiled_stats],
            key=lambda d: dt_util.parse_datetime(d["datetime"]),
        )

        max_date = None
        max_value = 0
        for record in self.hass.data[DOMAIN][self.id.upper()]["ws_maximeter"]:
            if record["value_kW"] > max_value:
                max_value = record["value_kW"]
                max_date = record["datetime"]

        values = np.array(
            [
                x["value_kW"]
                for x in self.hass.data[DOMAIN][self.id.upper()]["ws_maximeter"]
            ]
        )

        attrs["max_power_kW"] = max_value
        attrs["max_power_date"] = max_date
        attrs["max_power_mean_kW"] = round(np.mean(values), 1)
        attrs["max_power_90perc_kW"] = round(np.percentile(values, 90), 1)

        # update attributes
        self._data["state"] = STATE_READY
        self._data["attributes"].update(attrs)

        await Store(
            self.hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREAMBLE}_{self.id.upper()}",
            encoder=DateTimeEncoder,
        ).async_save({x: self._datadis.data[x] for x in ["supplies", "contracts"]})

        return True
