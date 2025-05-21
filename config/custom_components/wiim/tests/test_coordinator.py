"""Tests for the WiiM coordinator."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant

from custom_components.wiim.api import WiiMError

MOCK_HOST = "192.168.1.100"

@pytest.mark.asyncio
async def test_coordinator_update_success(hass: HomeAssistant, mock_coordinator, mock_client):
    """Test successful coordinator update."""
    # Patch async methods to return dicts, not coroutines
    mock_client.get_player_status = AsyncMock(return_value={"title": "Test", "device_name": "Test Device", "device_id": "testid", "power": True, "play_status": "play", "volume": 50, "mute": False})
    mock_client.get_status = AsyncMock(return_value={"title": "Test", "device_name": "Test Device", "device_id": "testid", "power": True, "play_status": "play", "volume": 50, "mute": False})
    mock_client.get_multiroom_info = AsyncMock(return_value={"slave_list": [], "type": "0"})
    mock_client.get_meta_info = AsyncMock(return_value={})
    await mock_coordinator.async_refresh()
    assert mock_coordinator.data is not None
    assert "status" in mock_coordinator.data
    assert "multiroom" in mock_coordinator.data
    assert "role" in mock_coordinator.data
    assert mock_coordinator.data["role"] == "solo"

@pytest.mark.asyncio
async def test_coordinator_update_failure(hass: HomeAssistant, mock_coordinator, mock_client):
    """Test coordinator update failure."""
    mock_client.get_player_status = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_status = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_multiroom_info = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_meta_info = AsyncMock(return_value={})
    await mock_coordinator.async_refresh()
    assert mock_coordinator.last_update_success is False

@pytest.mark.asyncio
async def test_coordinator_group_management(hass: HomeAssistant, mock_coordinator, mock_client):
    """Test group management functions."""
    mock_client.create_group = AsyncMock()
    mock_client.join_group = AsyncMock()
    mock_client.leave_group = AsyncMock()
    mock_client.delete_group = AsyncMock()
    mock_client.get_player_status = AsyncMock(return_value={"title": "Test", "device_name": "Test Device", "device_id": "testid", "power": True, "play_status": "play", "volume": 50, "mute": False})
    mock_client.get_status = AsyncMock(return_value={"title": "Test", "device_name": "Test Device", "device_id": "testid", "power": True, "play_status": "play", "volume": 50, "mute": False})
    mock_client.get_multiroom_info = AsyncMock(return_value={"slave_list": [], "type": "0"})
    mock_client.get_meta_info = AsyncMock(return_value={})
    await mock_coordinator.create_wiim_group()
    await mock_coordinator.join_wiim_group("192.168.1.101")
    await mock_coordinator.leave_wiim_group()
    await mock_coordinator.delete_wiim_group()

@pytest.mark.asyncio
async def test_coordinator_group_registry(hass: HomeAssistant, mock_coordinator):
    """Test group registry functionality."""
    # Should return None for unknown master
    assert mock_coordinator.get_group_by_master("unknown") is None

@pytest.mark.asyncio
async def test_coordinator_poll_interval_management(hass: HomeAssistant, mock_coordinator):
    """Test poll interval management."""
    # Patch async_cancel and async_refresh
    mock_coordinator.async_cancel = AsyncMock()
    mock_coordinator.async_refresh = AsyncMock()
    await mock_coordinator.async_stop()
    await mock_coordinator.async_start()
    await mock_coordinator.async_stop()

@pytest.mark.asyncio
async def test_coordinator_error_handling(hass: HomeAssistant, mock_coordinator, mock_client):
    """Test error handling in coordinator."""
    mock_client.get_player_status = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_status = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_multiroom_info = AsyncMock(side_effect=WiiMError("fail"))
    mock_client.get_meta_info = AsyncMock(return_value={})
    await mock_coordinator.async_refresh()
    assert mock_coordinator.last_update_success is False

@pytest.mark.asyncio
async def test_coordinator_multiroom_state(hass: HomeAssistant, mock_coordinator, mock_client):
    """Test multiroom state properties."""
    mock_client.is_master = False
    assert not mock_coordinator.is_wiim_master
    mock_client.is_master = True
    assert mock_coordinator.is_wiim_master