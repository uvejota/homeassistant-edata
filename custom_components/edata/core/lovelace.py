from aiohttp import web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.core import HomeAssistant


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
