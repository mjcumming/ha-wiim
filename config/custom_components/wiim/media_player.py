"""WiiM media player entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_platform
import voluptuous as vol
from homeassistant.components.media_player.const import (
    ATTR_GROUP_MEMBERS as HA_ATTR_GROUP_MEMBERS,
)

from .api import WiiMError
from .const import (
    ATTR_DEVICE_ID,
    ATTR_DEVICE_MODEL,
    ATTR_DEVICE_NAME,
    ATTR_EQ_CUSTOM,
    ATTR_EQ_PRESET,
    ATTR_FIRMWARE,
    ATTR_MUTE,
    ATTR_PLAY_MODE,
    ATTR_PRESET,
    ATTR_REPEAT_MODE,
    ATTR_SHUFFLE_MODE,
    ATTR_SOURCE,
    DOMAIN,
    PLAY_MODE_NORMAL,
    PLAY_MODE_REPEAT_ALL,
    PLAY_MODE_REPEAT_ONE,
    PLAY_MODE_SHUFFLE,
    PLAY_MODE_SHUFFLE_REPEAT_ALL,
    CONF_VOLUME_STEP,
    DEFAULT_VOLUME_STEP,
)
from .coordinator import WiiMCoordinator

_LOGGER = logging.getLogger(__name__)

# Home Assistant doesn't define a constant for the leader attribute.
HA_ATTR_GROUP_LEADER = "group_leader"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WiiM media player from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entity = WiiMMediaPlayer(coordinator)

    async_add_entities([entity])

    # Register custom entity services
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        "play_preset",
        {vol.Required("preset"): vol.All(int, vol.Range(min=1, max=6))},
        "async_play_preset",
    )
    platform.async_register_entity_service(
        "toggle_power",
        {},
        "async_toggle_power",
    )

    # Diagnostic helpers
    platform.async_register_entity_service(
        "reboot_device",
        {},
        "async_reboot_device",
    )
    platform.async_register_entity_service(
        "sync_time",
        {},
        "async_sync_time",
    )


class WiiMMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a WiiM media player."""

    def __init__(self, coordinator: WiiMCoordinator) -> None:
        """Initialize the WiiM media player."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.client.host
        self._attr_name = f"WiiM {coordinator.client.host}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.client.host)},
            name=self._attr_name,
            manufacturer="WiiM",
            model=coordinator.data.get("status", {}).get("device_model", "WiiM"),
            sw_version=coordinator.data.get("status", {}).get("firmware", ""),
        )
        # Compose the bitmask of capabilities supported by the WiiM device.
        self._attr_supported_features = MediaPlayerEntityFeature(
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.CLEAR_PLAYLIST
            | MediaPlayerEntityFeature.SHUFFLE_SET
            | MediaPlayerEntityFeature.REPEAT_SET
            | MediaPlayerEntityFeature.GROUPING
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        status = self.coordinator.data.get("status", {})
        if not status.get("power"):
            return MediaPlayerState.OFF
        if status.get("play_status") == "play":
            return MediaPlayerState.PLAYING
        if status.get("play_status") == "pause":
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        """Return the volume level of the media player (0..1)."""
        if volume := self.coordinator.data.get("status", {}).get("volume"):
            return float(volume) / 100
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Return boolean if volume is currently muted."""
        return self.coordinator.data.get("status", {}).get("mute")

    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        return self.coordinator.data.get("status", {}).get("title")

    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media."""
        return self.coordinator.data.get("status", {}).get("artist")

    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current playing media."""
        return self.coordinator.data.get("status", {}).get("album")

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        return self.coordinator.data.get("status", {}).get("position")

    @property
    def media_position_updated_at(self) -> float | None:
        """When was the position of the current playing media valid."""
        return self.coordinator.data.get("status", {}).get("position_updated_at")

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return self.coordinator.data.get("status", {}).get("duration")

    @property
    def shuffle(self) -> bool | None:
        """Return true if shuffle is enabled."""
        mode = self.coordinator.data.get("status", {}).get("play_mode")
        return mode in (PLAY_MODE_SHUFFLE, PLAY_MODE_SHUFFLE_REPEAT_ALL)

    @property
    def repeat(self) -> str | None:
        """Return current repeat mode."""
        mode = self.coordinator.data.get("status", {}).get("play_mode")
        if mode == PLAY_MODE_REPEAT_ONE:
            return "one"
        if mode in (PLAY_MODE_REPEAT_ALL, PLAY_MODE_SHUFFLE_REPEAT_ALL):
            return "all"
        return "off"

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        return self.coordinator.data.get("status", {}).get("source")

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return self.coordinator.data.get("status", {}).get("sources", [])

    @property
    def group_members(self) -> list[str]:
        """Return list of group member entity IDs."""
        return list(self.coordinator.ha_group_members)

    @property
    def group_leader(self) -> str | None:
        """Return the entity ID of the group leader."""
        if self.coordinator.is_ha_group_leader:
            return self.entity_id
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        status = self.coordinator.data.get("status", {})
        return {
            # Artwork path consumed by frontend via entity_picture
            "entity_picture": status.get("entity_picture"),
            ATTR_DEVICE_MODEL: status.get("device_model"),
            ATTR_DEVICE_NAME: status.get("device_name"),
            ATTR_DEVICE_ID: status.get("device_id"),
            ATTR_FIRMWARE: status.get("firmware"),
            ATTR_PRESET: status.get("preset"),
            ATTR_PLAY_MODE: status.get("play_mode"),
            ATTR_REPEAT_MODE: status.get("repeat_mode"),
            ATTR_SHUFFLE_MODE: status.get("shuffle_mode"),
            ATTR_SOURCE: status.get("source"),
            ATTR_MUTE: status.get("mute"),
            ATTR_EQ_PRESET: status.get("eq_preset"),
            ATTR_EQ_CUSTOM: status.get("eq_custom"),
            # Use HA-core constant names so the frontend recognises the
            # grouping capability and displays the chain-link button.
            HA_ATTR_GROUP_MEMBERS: list(self.coordinator.ha_group_members),
            HA_ATTR_GROUP_LEADER: self.group_leader,
        }

    @property
    def entity_picture(self) -> str | None:
        """Return URL to current artwork."""
        return self.coordinator.data.get("status", {}).get("entity_picture")

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        try:
            await self.coordinator.client.set_power(True)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to turn on WiiM device: %s", err)
            raise

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        try:
            await self.coordinator.client.set_power(False)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to turn off WiiM device: %s", err)
            raise

    async def async_media_play(self) -> None:
        """Send play command."""
        try:
            await self.coordinator.client.play()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to play on WiiM device: %s", err)
            raise

    async def async_media_pause(self) -> None:
        """Send pause command."""
        try:
            await self.coordinator.client.pause()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to pause WiiM device: %s", err)
            raise

    async def async_media_stop(self) -> None:
        """Send stop command."""
        try:
            await self.coordinator.client.stop()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to stop WiiM device: %s", err)
            raise

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        try:
            await self.coordinator.client.next_track()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to play next track on WiiM device: %s", err)
            raise

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        try:
            await self.coordinator.client.previous_track()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to play previous track on WiiM device: %s", err)
            raise

    def _volume_step(self) -> float:
        entry_id = getattr(self.coordinator, 'entry_id', None)
        if entry_id:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry is not None:
                return entry.options.get(CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP)
        return 0.05

    async def async_volume_up(self) -> None:
        """Volume up the media player."""
        if volume := self.volume_level:
            step = self._volume_step()
            try:
                await self.coordinator.client.set_volume(min(1.0, volume + step))
                await self.coordinator.async_refresh()
            except WiiMError as err:
                _LOGGER.error("Failed to increase volume on WiiM device: %s", err)
                raise

    async def async_volume_down(self) -> None:
        """Volume down the media player."""
        if volume := self.volume_level:
            step = self._volume_step()
            try:
                await self.coordinator.client.set_volume(max(0.0, volume - step))
                await self.coordinator.async_refresh()
            except WiiMError as err:
                _LOGGER.error("Failed to decrease volume on WiiM device: %s", err)
                raise

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        try:
            await self.coordinator.client.set_volume(volume)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to set volume on WiiM device: %s", err)
            raise

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        try:
            await self.coordinator.client.set_mute(mute)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to mute WiiM device: %s", err)
            raise

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        try:
            await self.coordinator.client.set_source(source)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to select source on WiiM device: %s", err)
            raise

    async def async_clear_playlist(self) -> None:
        """Clear players playlist."""
        try:
            await self.coordinator.client.clear_playlist()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to clear playlist on WiiM device: %s", err)
            raise

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle mode."""
        try:
            if shuffle:
                if self.repeat == "all":
                    await self.coordinator.client.set_shuffle_mode(
                        PLAY_MODE_SHUFFLE_REPEAT_ALL
                    )
                else:
                    await self.coordinator.client.set_shuffle_mode(PLAY_MODE_SHUFFLE)
            else:
                if self.repeat == "all":
                    await self.coordinator.client.set_shuffle_mode(PLAY_MODE_REPEAT_ALL)
                else:
                    await self.coordinator.client.set_shuffle_mode(PLAY_MODE_NORMAL)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to set shuffle mode on WiiM device: %s", err)
            raise

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode."""
        try:
            if repeat == "all":
                if self.shuffle:
                    await self.coordinator.client.set_repeat_mode(
                        PLAY_MODE_SHUFFLE_REPEAT_ALL
                    )
                else:
                    await self.coordinator.client.set_repeat_mode(PLAY_MODE_REPEAT_ALL)
            elif repeat == "one":
                await self.coordinator.client.set_repeat_mode(PLAY_MODE_REPEAT_ONE)
            elif self.shuffle:
                await self.coordinator.client.set_repeat_mode(PLAY_MODE_SHUFFLE)
            else:
                await self.coordinator.client.set_repeat_mode(PLAY_MODE_NORMAL)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to set repeat mode on WiiM device: %s", err)
            raise

    async def async_play_preset(self, preset: int) -> None:
        """Handle the play_preset service call."""
        try:
            await self.coordinator.client.play_preset(preset)
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to play preset on WiiM device: %s", err)
            raise

    async def async_toggle_power(self) -> None:
        """Handle the toggle_power service call."""
        try:
            await self.coordinator.client.toggle_power()
            await self.coordinator.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to toggle power on WiiM device: %s", err)
            raise

    async def async_join(self, group_members: list[str]) -> None:
        """Join `group_members` as a group."""
        # Create group if leader, else join leader's group
        if not self.coordinator.client.group_master:
            # Become master
            await self.coordinator.create_wiim_group()
            master_ip = self.coordinator.client.host
        else:
            master_ip = self.coordinator.client.group_master

        # Command each member to join via service call
        for entity_id in group_members:
            if entity_id == self.entity_id:
                continue
            coord = _find_coordinator(self.hass, entity_id)
            if coord is not None:
                await coord.join_wiim_group(master_ip)

    async def async_unjoin(self) -> None:
        """Remove this player from any group."""
        if self.coordinator.client.is_master:
            await self.coordinator.delete_wiim_group()
        else:
            await self.coordinator.leave_wiim_group()

    # ------------------------------------------------------------------
    # Diagnostic helpers exposed as entity services
    # ------------------------------------------------------------------

    async def async_reboot_device(self) -> None:
        """Reboot the speaker via entity service."""
        try:
            await self.coordinator.client.reboot()
        except WiiMError as err:
            _LOGGER.error("Failed to reboot WiiM device: %s", err)
            raise

    async def async_sync_time(self) -> None:
        """Synchronise the speaker clock to Home Assistant time."""
        try:
            await self.coordinator.client.sync_time()
        except WiiMError as err:
            _LOGGER.error("Failed to sync time on WiiM device: %s", err)
            raise


def _find_coordinator(hass: HomeAssistant, entity_id: str) -> WiiMCoordinator | None:
    """Return coordinator for the given entity ID."""
    for coord in hass.data[DOMAIN].values():
        # Coordinator stores entities via host; build expected entity_id
        expected = f"media_player.wiim_{coord.client.host.replace('.', '_')}"
        if expected == entity_id:
            return coord
    return None
