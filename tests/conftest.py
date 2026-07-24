"""Common fixtures for the edata integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

from custom_components.edata.const import DOMAIN
from custom_components.edata.core.config import (
    CONF_CUPS,
    CONF_PASSWORD,
    CONF_SCUPS,
    CONF_USERNAME,
)
from custom_components.edata.core.options import CONF_BILLING, CONF_PVPC

from .fixtures import CUPS, PASSWORD, SCUPS, USERNAME, FakeDataManager

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Force the Home Assistant snapshot extension (snapshots/ directory).

    Pinning it here keeps precedence over syrupy's default ``snapshot`` fixture,
    whose registration order relative to pytest-homeassistant-custom-component is
    not guaranteed (in CI syrupy loads last and would otherwise look in
    ``__snapshots__`` instead of ``snapshots``).
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True)
def mock_coordinator_statistics() -> Generator[AsyncMock]:
    """Skip the recorder-backed statistics rebuild in coordinator refreshes.

    The statistics builders are exercised directly in ``test_statistics``; here
    they are stubbed so setup/refresh tests do not race recorder writes.
    """
    with patch(
        "custom_components.edata.coordinator.update_all_statistics", AsyncMock()
    ) as mock:
        yield mock


@pytest.fixture
def setup_integration(
    recorder_mock: None,
    enable_custom_integrations: None,
) -> None:
    """Set up the recorder and enable the edata custom integration.

    ``recorder_mock`` must resolve before ``hass`` (it asserts hass is not yet
    set up), so request this fixture before ``hass`` in every test signature.
    """
    return None


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a mock config entry without billing enabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=SCUPS,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: CUPS,
            CONF_SCUPS: SCUPS,
        },
        options={},
    )


@pytest.fixture
def billing_config_entry() -> MockConfigEntry:
    """Return a mock config entry with custom billing enabled."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=SCUPS,
        data={
            CONF_USERNAME: USERNAME,
            CONF_PASSWORD: PASSWORD,
            CONF_CUPS: CUPS,
            CONF_SCUPS: SCUPS,
        },
        options={
            CONF_BILLING: True,
            CONF_PVPC: False,
            "p1_kwh_eur": 0.2,
            "p2_kwh_eur": 0.2,
            "p3_kwh_eur": 0.2,
            "p1_kw_year_eur": 20,
            "p2_kw_year_eur": 10,
        },
    )


@pytest.fixture
def mock_data_manager() -> Generator[type[FakeDataManager]]:
    """Patch the coordinator DataManager with the in-memory fake."""
    with patch(
        "custom_components.edata.coordinator.DataManager", FakeDataManager
    ) as mock:
        yield mock
