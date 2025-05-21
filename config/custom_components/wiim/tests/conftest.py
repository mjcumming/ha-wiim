"""Common test fixtures for WiiM integration tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.wiim.api import WiiMClient
from custom_components.wiim.const import DOMAIN
from custom_components.wiim.coordinator import WiiMCoordinator

MOCK_HOST = "192.168.1.100"
MOCK_DEVICE_NAME = "WiiM Test Device"
MOCK_DEVICE_ID = "test_device_id"
MOCK_MAC = "00:11:22:33:44:55"

@pytest.fixture
def mock_client():
    """Create a mock WiiM client."""
    client = AsyncMock(spec=WiiMClient)
    client.host = MOCK_HOST
    client._host = MOCK_HOST
    client.get_status.return_value = {
        "device_name": MOCK_DEVICE_NAME,
        "device_id": MOCK_DEVICE_ID,
        "mac": MOCK_MAC,
        "power": True,
        "play_status": "play",
        "volume": 50,
        "mute": False,
        "title": "Test Title",
        "artist": "Test Artist",
        "album": "Test Album",
        "plm_support": "0xb",
        "sources": ["wifi", "line_in", "bluetooth", "optical"],
        "role": "solo",
        "multiroom": {},
    }
    client.get_player_status.return_value = client.get_status.return_value
    client.get_multiroom_info.return_value = {"slave_list": [], "type": "0"}
    client.get_meta_info.return_value = {}
    return client

@pytest.fixture
def mock_coordinator(hass: HomeAssistant, mock_client):
    """Create a mock WiiM coordinator."""
    coordinator = WiiMCoordinator(hass, mock_client)
    coordinator.data = {
        "status": mock_client.get_status.return_value,
        "multiroom": {},
        "role": "solo",
        "ha_group": {"is_leader": False, "members": []},
    }
    return coordinator

@pytest_asyncio.fixture
async def setup_integration(hass: HomeAssistant, mock_client, enable_custom_integrations):
    """Set up the WiiM integration with a mock client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=MOCK_DEVICE_NAME,
        unique_id=MOCK_DEVICE_ID,
        data={"host": MOCK_HOST},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.wiim.api.WiiMClient", return_value=mock_client),
        patch("custom_components.wiim.__init__.WiiMClient", return_value=mock_client),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    yield entry

    # Teardown
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

# ---------------------------------------------------------------------------
# Global patch – disable real network access for *any* WiiMClient instance
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_wiimclient_network(monkeypatch):
    """Patch WiiMClient methods that would hit the network (autouse)."""

    # Raw payload returned by the device (before normalisation)
    default_raw_status = {
        "status": "play",
        "vol": "50",
        "mute": "0",
        "DeviceName": MOCK_DEVICE_NAME,
        "device_id": MOCK_DEVICE_ID,
        "firmware": "test",
    }

    monkeypatch.setattr(
        "custom_components.wiim.api.WiiMClient.get_multiroom_info",
        AsyncMock(return_value={"slave_list": [], "type": "0"}),
    )

    monkeypatch.setattr(
        "custom_components.wiim.api.WiiMClient._request", AsyncMock(return_value=default_raw_status),
    )

    # Patch high-level helpers that would otherwise call the network
    monkeypatch.setattr(
        "custom_components.wiim.api.WiiMClient.get_meta_info",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "custom_components.wiim.api.WiiMClient.get_player_status",
        AsyncMock(return_value=default_raw_status),
    )
    monkeypatch.setattr(
        "custom_components.wiim.api.WiiMClient.close", AsyncMock(),
    )