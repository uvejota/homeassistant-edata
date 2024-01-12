"""Declarations of some package utilities."""

import logging
from aiohttp import web

from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant
from homeassistant.components.frontend import add_extra_js_url

from . import const

_LOGGER = logging.getLogger(__name__)


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
    """Initialize JS resource."""
    resources: ResourceStorageCollection = hass.data["lovelace"]["resources"]
    # force load storage
    await resources.async_get_info()

    url2 = f"{url}?v={ver}"

    for item in resources.async_items():
        if not item.get("url", "").startswith(url):
            continue

        # no need to update
        if item["url"].endswith(ver):
            return False

        _LOGGER.debug(f"Update lovelace resource to: {url2}")

        if isinstance(resources, ResourceStorageCollection):
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": url2}
            )
        else:
            # not the best solution, but what else can we do
            item["url"] = url2

        return True

    if isinstance(resources, ResourceStorageCollection):
        _LOGGER.debug(f"Add new lovelace resource: {url2}")
        await resources.async_create_item({"res_type": "module", "url": url2})
    else:
        _LOGGER.debug(f"Add extra JS module: {url2}")
        add_extra_js_url(hass, url2)

    return True
