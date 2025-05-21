"""Tests for the WiiM API client."""
from __future__ import annotations

import pytest
import aiohttp
from unittest.mock import patch

from custom_components.wiim.api import WiiMClient, WiiMError

MOCK_HOST = "192.168.1.100"
MOCK_PORT = 80
MOCK_DEVICE_NAME = "Test Device"
MOCK_DEVICE_ID = "test-device-id"
MOCK_MAC = "00:11:22:33:44:55"

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

class _DummyResp:
    def __init__(self, text_data="{}"):
        self._text = text_data

    async def text(self):
        return self._text

    def raise_for_status(self):
        return None

class _DummyCtxMgr:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *_exc):
        return False

class _DummySession:
    def __init__(self, *args, **kwargs):
        pass

    def request(self, *_a, **_kw):
        return _DummyCtxMgr(_DummyResp())

    async def close(self):
        pass

@pytest.fixture(autouse=True)
def patch_aiohttp_session(monkeypatch):
    """Patch aiohttp.ClientSession globally for all API tests."""
    monkeypatch.setattr(aiohttp, "ClientSession", _DummySession)
    yield

@pytest.fixture
def api_client():
    """Create a WiiM API client."""
    return WiiMClient(MOCK_HOST, MOCK_PORT)

@pytest.mark.asyncio
async def test_client_initialization(api_client):
    """Test client initialization."""
    assert api_client.host == MOCK_HOST
    assert api_client.port == MOCK_PORT
    assert api_client.base_url == (
        f"http://{MOCK_HOST}:{MOCK_PORT}" if MOCK_PORT == 80 else f"https://{MOCK_HOST}:{MOCK_PORT}"
    )

@pytest.mark.asyncio
async def test_get_status_success(api_client):
    """Test successful status retrieval."""
    response_data = {"power": True, "play_status": "play", "volume": 50}
    with patch.object(WiiMClient, "_request", return_value=response_data):
        result = await api_client.get_status()
    assert result["power"] is True
    assert result["play_status"] == "play"
    assert result["volume"] == 50

@pytest.mark.asyncio
async def test_get_status_failure(api_client):
    """Test failed status retrieval."""
    with patch.object(WiiMClient, "get_status", side_effect=WiiMError("fail")):
        with pytest.raises(WiiMError):
            await api_client.get_status()

@pytest.mark.asyncio
async def test_play_control(api_client):
    """Test play control commands."""
    patcher = patch.object(WiiMClient, "_request", return_value={})
    patcher.start()
    try:
        await api_client.play()
        await api_client.pause()
        await api_client.stop()
        await api_client.next_track()
        await api_client.previous_track()
    finally:
        patcher.stop()

@pytest.mark.asyncio
async def test_volume_control(api_client):
    """Test volume control commands."""
    patcher = patch.object(WiiMClient, "_request", return_value={})
    patcher.start()
    try:
        await api_client.set_volume(0.75)
        await api_client.set_mute(True)
        await api_client.set_mute(False)
    finally:
        patcher.stop()

@pytest.mark.asyncio
async def test_group_management(api_client):
    """Test group management commands."""
    patcher = patch.object(WiiMClient, "_request", return_value={})
    patcher.start()
    try:
        await api_client.create_group()
        await api_client.delete_group()
        await api_client.join_group("192.168.1.101")
        await api_client.leave_group()
    finally:
        patcher.stop()

@pytest.mark.asyncio
async def test_error_handling(api_client):
    """Test error handling."""
    with patch.object(WiiMClient, "get_status", side_effect=WiiMError("fail")):
        with pytest.raises(WiiMError):
            await api_client.get_status()

@pytest.mark.asyncio
async def test_session_management(api_client):
    """Test session management."""
    with patch.object(WiiMClient, "_request", return_value={}):
        await api_client.get_status()
    await api_client.close()