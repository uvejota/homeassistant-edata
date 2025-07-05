"""Declarations of some package utilities."""

from datetime import datetime, timedelta
import logging

from aiohttp import web
from dateutil import relativedelta

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.components.recorder.statistics import statistics_during_period
import homeassistant.components.recorder.util as recorder_util
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import const

_LOGGER = logging.getLogger(__name__)


def get_db_instance(hass: HomeAssistant):
    """Workaround for older HA versions."""
    try:
        return recorder_util.get_instance(hass)
    except AttributeError:
        return hass


def check_cups_integrity(cups: str):
    """Return false if cups is not valid, true otherwise."""

    _cups = cups.upper()

    if len(_cups) not in [20, 22]:
        return False

    if not all("0" <= x <= "9" for x in _cups[2:18]):
        return False

    cups_16_digits = int(_cups[2:18])
    base = cups_16_digits % 529
    cups_c = int(base / 23)
    cups_r = base % 23

    if (
        const.CUPS_CONTROL_DIGITS[cups_c] + const.CUPS_CONTROL_DIGITS[cups_r]
        != _cups[18:20]
    ):
        return False

    return True


def register_static_path(app: web.Application, url_path: str, path):
    """Register static path."""

    async def serve_file(request):
        return web.FileResponse(path)

    app.router.add_route("GET", url_path, serve_file)


async def init_resource(hass: HomeAssistant, url: str, ver: str) -> bool:
    """Initialize JS resource.

    Original author: AlexxIT/go2rtc HA integration.
    """
    resources: ResourceStorageCollection = hass.data["lovelace"].resources
    # force load storage
    await resources.async_get_info()

    url2 = f"{url}?v={ver}"

    for item in resources.async_items():
        if not item.get("url", "").startswith(url):
            continue

        # no need to update
        if item["url"].endswith(ver):
            return False

        if isinstance(resources, ResourceStorageCollection):
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": url2}
            )
        else:
            # not the best solution, but what else can we do
            item["url"] = url2

        return True

    if isinstance(resources, ResourceStorageCollection):
        await resources.async_create_item({"res_type": "module", "url": url2})
    else:
        add_extra_js_url(hass, url2)

    return True


def group_by_year(data: list[tuple[datetime, float]]) -> list[tuple[datetime, float]]:
    """Aggregate data by year."""

    yearly_data = {}
    for date, value in data:
        year = date.year
        if year in yearly_data:
            yearly_data[year] += value
        else:
            yearly_data[year] = value
    result = [
        (datetime(year, 1, 1, 0, 0), total) for year, total in yearly_data.items()
    ]
    result.sort(key=lambda x: x[0])
    return result


def fetch_changes_from_mem(
    hass: HomeAssistant,
    stat_id: str,
    scups: str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
):
    "Fetch last N records from memory."

    data = hass.data[const.DOMAIN][scups.lower()]["edata"].data
    group = None
    key = None

    if aggr == "hour":
        dt_unit = timedelta(hours=1)
    elif aggr == "day":
        dt_unit = timedelta(days=1)
    elif aggr == "month":
        dt_unit = relativedelta.relativedelta(months=1)
    else:
        return None

    ref = datetime.now().replace(hour=0, minute=0, second=0)
    try:
        if not now_as_ref:
            ref = dt_util.as_local(
                data["consumptions"][-1]["datetime"].replace(hour=0, minute=0, second=0)
            )
        if dt_util.as_local(data["consumptions"][0]["datetime"]) > (
            ref - records * dt_unit
        ):
            return None
    except Exception:
        return None

    if stat_id == const.STAT_ID_KWH(scups):
        key = "value_kWh"
        group = "consumptions"
    elif stat_id == const.STAT_ID_P1_KWH(scups):
        key = "value_p1_kWh"
        group = "consumptions"
    elif stat_id == const.STAT_ID_P2_KWH(scups):
        key = "value_p2_kWh"
        group = "consumptions"
    elif stat_id == const.STAT_ID_P3_KWH(scups):
        key = "value_p3_kWh"
        group = "consumptions"
    elif stat_id == const.STAT_ID_SURP_KWH(scups):
        key = "surplus_kWh"
        group = "consumptions"
    else:
        return None

    if aggr == "day":
        group += "_daily_sum"
    elif aggr == "month":
        group += "_monthly_sum"
    elif aggr == "hour" and group == "cost":
        group += "_hourly_sum"

    return [
        (dt_util.as_local(x["datetime"]), x[key])
        for x in data[group][-records:]
        if dt_util.as_local(x["datetime"]) >= ref - records * dt_unit
    ]


async def fetch_changes_from_stats(
    hass: HomeAssistant,
    stat_id: str,
    scups: str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
):
    "Fetch last N statistics records."

    ref = datetime.now().replace(hour=0, minute=0, second=0)
    try:
        if not now_as_ref:
            ref = dt_util.as_local(
                hass.data[const.DOMAIN][scups.lower()]["edata"]
                .data["consumptions"][-1]["datetime"]
                .replace(hour=0, minute=0, second=0)
            )
    except Exception:
        pass

    _aggr = aggr
    if aggr == "hour":
        _dt_unit = timedelta(hours=1)
    elif aggr == "day":
        _dt_unit = timedelta(days=1)
    elif aggr == "week":
        _dt_unit = relativedelta.relativedelta(weeks=1)
    elif aggr == "month":
        _dt_unit = relativedelta.relativedelta(months=1)
    elif aggr == "year":
        _dt_unit = relativedelta.relativedelta(years=1)
        _aggr = "month"
    else:
        _LOGGER.warning("Not a valid aggr method '%s'", aggr)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        ref - records * _dt_unit,
        None,
        {stat_id},
        _aggr,
        None,
        {"change"},
    )
    data = data[stat_id]
    if aggr == "year":
        return group_by_year(
            [(dt_util.utc_from_timestamp(x["start"]), x["change"]) for x in data]
        )
    return [(dt_util.utc_from_timestamp(x["start"]), x["change"]) for x in data]


async def fetch_changes(
    hass: HomeAssistant,
    stat_id: str,
    scups: str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
):
    "Fetch last N statistics from the best source."

    if (
        data := fetch_changes_from_mem(hass, stat_id, scups, aggr, records, now_as_ref)
    ) is None:
        data = await fetch_changes_from_stats(
            hass, stat_id, scups, aggr, records, now_as_ref
        )

    return data


async def get_consumptions_history(
    hass: HomeAssistant,
    scups: str,
    tariff: None | str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
) -> list[tuple[datetime, float]]:
    "Fetch last N consumptions records."

    if tariff is None:
        _stat_id = const.STAT_ID_KWH(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_KWH(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_KWH(scups)
    elif tariff == "p3":
        _stat_id = const.STAT_ID_P3_KWH(scups)

    return await fetch_changes(hass, _stat_id, scups, aggr, records, now_as_ref)


async def get_surplus_history(
    hass: HomeAssistant,
    scups: str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
) -> list[tuple[datetime, float]]:
    "Fetch last N surplus records."

    _stat_id = const.STAT_ID_SURP_KWH(scups)
    return await fetch_changes(hass, _stat_id, scups, aggr, records, now_as_ref)


async def get_maximeter_history(
    hass: HomeAssistant, scups: str, tariff: None | str
) -> list[tuple[datetime, float]]:
    "Fetch last N max power records."
    if tariff is None:
        _stat_id = const.STAT_ID_KW(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_KW(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_KW(scups)

    data = await get_db_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        datetime(1970, 1, 1),
        None,
        {_stat_id},
        "day",
        None,
        {"max"},
    )
    data = data[_stat_id]
    return [(dt_util.utc_from_timestamp(x["start"]), x["max"]) for x in data]


async def get_costs_history(
    hass: HomeAssistant,
    scups: str,
    tariff: None | str,
    aggr: str,
    records: int = 30,
    now_as_ref: bool = True,
) -> list[tuple[datetime, float]]:
    "Fetch last N costs records."

    if tariff is None:
        _stat_id = const.STAT_ID_EUR(scups)
    elif tariff == "p1":
        _stat_id = const.STAT_ID_P1_EUR(scups)
    elif tariff == "p2":
        _stat_id = const.STAT_ID_P2_EUR(scups)
    elif tariff == "p3":
        _stat_id = const.STAT_ID_P3_EUR(scups)

    return await fetch_changes(hass, _stat_id, scups, aggr, records, now_as_ref)


async def get_attributes(
    hass: HomeAssistant,
    scups: str,
) -> list[tuple[datetime, float]]:
    "Fetch all attributes from edata helper."

    try:
        return hass.data[const.DOMAIN][scups.lower()]["edata"].attributes
    except Exception:
        return {}
