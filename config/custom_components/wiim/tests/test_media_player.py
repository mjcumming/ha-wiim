"""Tests for the WiiM media player entity."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_MEDIA_NEXT_TRACK,
    SERVICE_MEDIA_PAUSE,
    SERVICE_MEDIA_PLAY,
    SERVICE_MEDIA_PREVIOUS_TRACK,
    SERVICE_MEDIA_STOP,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    SERVICE_VOLUME_DOWN,
    SERVICE_VOLUME_MUTE,
    SERVICE_VOLUME_SET,
    SERVICE_VOLUME_UP,
)
from homeassistant.core import HomeAssistant

from custom_components.wiim.const import DOMAIN
from custom_components.wiim.media_player import WiiMMediaPlayer
from .conftest import MOCK_HOST  # reuse same constant

# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _make_entity(hass: HomeAssistant, mock_client):
    """Return a WiiMMediaPlayer instance with pre-populated coordinator data."""
    from custom_components.wiim.coordinator import WiiMCoordinator

    coordinator = WiiMCoordinator(hass, mock_client)
    # Provide minimal parsed status so MediaPlayer init succeeds
    status = {
        "play_status": "play",
        "volume": 50,
        "mute": False,
        "title": "Test Title",
        "artist": "Test Artist",
        "album": "Test Album",
        "sources": ["wifi", "line_in", "bluetooth", "optical"],
    }
    coordinator.data = {
        "status": status,
        "multiroom": {},
        "role": "solo",
        "ha_group": {"is_leader": False, "members": []},
    }
    entity = WiiMMediaPlayer(coordinator)
    return entity

@pytest.mark.asyncio
async def test_media_player_setup(setup_integration, mock_client, hass: HomeAssistant):
    """Test media player setup."""
    entity = _make_entity(hass, mock_client)
    assert entity.volume_level == 0.5
    assert not entity.is_volume_muted
    assert entity.media_title == "Test Title"
    assert entity.media_artist == "Test Artist"
    assert entity.media_album_name == "Test Album"

@pytest.mark.asyncio
async def test_media_player_turn_on(setup_integration, mock_client, hass: HomeAssistant):
    """Test turning on the media player."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_power = AsyncMock()
    entity.coordinator.async_refresh = AsyncMock()
    await entity.async_turn_on()
    mock_client.set_power.assert_called_with(True)

@pytest.mark.asyncio
async def test_media_player_turn_off(setup_integration, mock_client, hass: HomeAssistant):
    """Test turning off the media player."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_power = AsyncMock()
    entity.coordinator.async_refresh = AsyncMock()
    await entity.async_turn_off()
    mock_client.set_power.assert_called_with(False)

@pytest.mark.asyncio
async def test_media_player_play(setup_integration, mock_client, hass: HomeAssistant):
    """Test playing media."""
    entity = _make_entity(hass, mock_client)
    mock_client.play = AsyncMock()
    await entity.async_media_play()
    mock_client.play.assert_called_once()

@pytest.mark.asyncio
async def test_media_player_pause(setup_integration, mock_client, hass: HomeAssistant):
    """Test pausing media."""
    entity = _make_entity(hass, mock_client)
    mock_client.pause = AsyncMock()
    await entity.async_media_pause()
    mock_client.pause.assert_called_once()

@pytest.mark.asyncio
async def test_media_player_stop(setup_integration, mock_client, hass: HomeAssistant):
    """Test stopping media."""
    entity = _make_entity(hass, mock_client)
    mock_client.stop = AsyncMock()
    entity.coordinator.async_refresh = AsyncMock()
    await entity.async_media_stop()
    mock_client.stop.assert_called_once()

@pytest.mark.asyncio
async def test_media_player_next_track(setup_integration, mock_client, hass: HomeAssistant):
    """Test next track."""
    entity = _make_entity(hass, mock_client)
    mock_client.next_track = AsyncMock()
    await entity.async_media_next_track()
    mock_client.next_track.assert_called_once()

@pytest.mark.asyncio
async def test_media_player_previous_track(setup_integration, mock_client, hass: HomeAssistant):
    """Test previous track."""
    entity = _make_entity(hass, mock_client)
    mock_client.previous_track = AsyncMock()
    await entity.async_media_previous_track()
    mock_client.previous_track.assert_called_once()

@pytest.mark.asyncio
async def test_media_player_volume_up(setup_integration, mock_client, hass: HomeAssistant):
    """Test volume up."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_volume = AsyncMock()
    await entity.async_volume_up()
    mock_client.set_volume.assert_called()

@pytest.mark.asyncio
async def test_media_player_volume_down(setup_integration, mock_client, hass: HomeAssistant):
    """Test volume down."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_volume = AsyncMock()
    await entity.async_volume_down()
    mock_client.set_volume.assert_called()

@pytest.mark.asyncio
async def test_media_player_set_volume(setup_integration, mock_client, hass: HomeAssistant):
    """Test setting volume."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_volume = AsyncMock()
    await entity.async_set_volume_level(0.7)
    mock_client.set_volume.assert_called_with(0.7)

@pytest.mark.asyncio
async def test_media_player_mute(setup_integration, mock_client, hass: HomeAssistant):
    """Test muting."""
    entity = _make_entity(hass, mock_client)
    mock_client.set_mute = AsyncMock()
    await entity.async_mute_volume(True)
    mock_client.set_mute.assert_called_with(True)

@pytest.mark.asyncio
async def test_media_player_supported_features(setup_integration, mock_client, hass: HomeAssistant):
    """Test supported features."""
    entity = _make_entity(hass, mock_client)
    assert entity.supported_features is not None
    features = entity.supported_features
    assert features & MediaPlayerEntityFeature.PLAY
    assert features & MediaPlayerEntityFeature.PAUSE
    assert features & MediaPlayerEntityFeature.STOP
    assert features & MediaPlayerEntityFeature.NEXT_TRACK
    assert features & MediaPlayerEntityFeature.PREVIOUS_TRACK
    assert features & MediaPlayerEntityFeature.VOLUME_SET
    assert features & MediaPlayerEntityFeature.VOLUME_MUTE
    assert features & MediaPlayerEntityFeature.GROUPING

@pytest.mark.asyncio
async def test_media_player_source_list(setup_integration, mock_client, hass: HomeAssistant):
    """Test source list."""
    entity = _make_entity(hass, mock_client)
    sources = entity.source_list
    assert isinstance(sources, list)
    assert "WiFi" in sources
    assert "Line In" in sources
    assert "Bluetooth" in sources
    assert "Optical" in sources