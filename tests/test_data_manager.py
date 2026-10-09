"""Tests for the DataManager facade against a real on-disk database."""

from collections.abc import AsyncGenerator, Generator
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edata.core.utils import get_db_path
from edata.database.controller import EdataDB
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR

from custom_components.edata.core.data import DataManager

from .fixtures import (
    CUPS,
    PASSWORD,
    SCUPS,
    USERNAME,
    build_contracts,
    build_energy,
    build_power,
    build_supply,
    default_billing_rules,
)


@pytest.fixture(autouse=True)
async def reset_edata_db(hass: HomeAssistant) -> AsyncGenerator[None]:
    """Reset the EdataDB singleton and remove its database between tests.

    Overrides the shared conftest fixture for this module (which has no recorder
    ordering constraint) so each test also starts from a fresh on-disk database.
    """

    db_path = Path(get_db_path(hass.config.path(STORAGE_DIR)))
    db_path.unlink(missing_ok=True)
    EdataDB.reset()
    yield
    EdataDB.reset()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_connectors() -> Generator[None]:
    """Serve fixture data from the Datadis connector and no PVPC prices."""
    with (
        patch("edata.services.data_service.DatadisConnector") as datadis,
        patch("edata.services.data_service.REDataConnector") as redata,
    ):
        datadis.return_value.async_login = AsyncMock(return_value=True)
        datadis.return_value.async_get_supplies = AsyncMock(
            return_value=[build_supply()]
        )
        datadis.return_value.async_get_contract_detail = AsyncMock(
            return_value=build_contracts()
        )
        datadis.return_value.async_get_consumption_data = AsyncMock(
            return_value=build_energy()
        )
        datadis.return_value.async_get_max_power = AsyncMock(
            return_value=build_power()
        )
        redata.return_value.async_get_realtime_prices = AsyncMock(return_value=[])
        yield


def _make_manager(hass: HomeAssistant, billing=None) -> DataManager:
    """Build a DataManager pointed at the test config storage."""
    return DataManager(
        hass=hass,
        username=USERNAME,
        password=PASSWORD,
        cups=CUPS,
        scups=SCUPS,
        billing=billing,
    )


async def test_sync_applies_custom_billing_rules(
    hass: HomeAssistant, mock_connectors: None
) -> None:
    """Custom billing rules are honored, so bills are built without PVPC prices."""
    manager = _make_manager(hass, billing=default_billing_rules())
    await manager.sync()

    energy = await manager.get_energy()
    assert len(energy) == len(build_energy())

    # With the previous bug the sync fell back to PVPC, which yields no bills
    # when there are no PVPC prices. Custom rules must produce bills instead.
    bills = await manager.get_bills()
    assert len(bills) > 0


async def test_sync_without_billing_creates_no_bills(
    hass: HomeAssistant, mock_connectors: None
) -> None:
    """When billing is disabled no bills are generated."""
    manager = _make_manager(hass, billing=None)
    await manager.sync()

    assert await manager.get_bills() == []


async def test_rebuild_and_simulate(
    hass: HomeAssistant, mock_connectors: None
) -> None:
    """rebuild_billing clears and recomputes; simulate_last_month previews a bill."""
    rules = default_billing_rules()
    manager = _make_manager(hass, billing=rules)
    await manager.sync()

    await manager.rebuild_billing()
    assert len(await manager.get_bills()) > 0

    preview = await manager.simulate_last_month(rules, is_pvpc=False)
    assert preview is not None
    assert preview.bill.value_eur > 0
    # the fixture only has the first 48 hours of January 2023: the preview must
    # say so instead of passing as a full month
    assert preview.start == datetime(2023, 1, 1, 0, 0)
    assert preview.end == datetime(2023, 1, 2, 23, 0)
    assert preview.hours == preview.bill.delta_h == 48
    assert preview.month_hours == 31 * 24


async def test_full_sync_requests_whole_history(
    hass: HomeAssistant, mock_connectors: None
) -> None:
    """full_sync asks Datadis from the supply start, not just what is missing."""
    rules = default_billing_rules()
    manager = _make_manager(hass, billing=rules)
    await manager.sync()
    datadis = manager._data_service.datadis
    datadis.async_get_consumption_data.reset_mock()
    datadis.async_get_max_power.reset_mock()

    assert await manager.full_sync()

    supply_start = build_supply().date_start
    starts = [call.args[2] for call in datadis.async_get_consumption_data.await_args_list]
    assert supply_start in starts
    assert datadis.async_get_max_power.await_args.args[2] == supply_start
    assert len(await manager.get_bills()) > 0
