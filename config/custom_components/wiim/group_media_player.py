from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState, MediaPlayerEntityFeature
from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

class WiiMGroupMediaPlayer(MediaPlayerEntity):
    """Representation of a WiiM group media player entity."""

    def __init__(self, hass, coordinator, master_ip):
        self.hass = hass
        self.coordinator = coordinator
        self.master_ip = master_ip
        group_info = coordinator.get_group_by_master(master_ip) or {}
        group_name = group_info.get('name')
        if not group_name or group_name.strip().lower() in ("wiim group", "none", "null", ""):
            group_name = f"WiiM Group {master_ip}"
        safe_name = (
            group_name.replace(' ', '_')
            .replace('(', '')
            .replace(')', '')
            .replace(',', '')
            .replace('.', '_')
            .replace('none', '')
            .replace('null', '')
            .lower()
        )
        self._attr_unique_id = f"wiim_group_{safe_name}"
        self._attr_name = f"{group_name} (Group)"
        self._attr_supported_features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.GROUPING
        )

    @property
    def group_info(self):
        info = self.coordinator.get_group_by_master(self.master_ip) or {}
        _LOGGER.debug("[WiiMGroup] Group info for master %s: %s", self.master_ip, info)
        return info

    @property
    def group_members(self):
        return list(self.group_info.get("members", {}).keys())

    @property
    def group_leader(self):
        return self.master_ip

    @property
    def state(self):
        # Get master's state directly from its coordinator
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            _LOGGER.warning("[WiiMGroup] No coordinator found for master %s in group %s", self.master_ip, self._attr_name)
            return MediaPlayerState.IDLE

        status = master_coord.data.get("status", {})
        role = master_coord.data.get("role")
        _LOGGER.debug(
            "[WiiMGroup] Master %s state check - role=%s, status=%s",
            self.master_ip, role, status
        )

        if not status.get("power"):
            return MediaPlayerState.OFF
        if status.get("play_status") == "play":
            return MediaPlayerState.PLAYING
        if status.get("play_status") == "pause":
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self):
        # Get master's volume directly from its coordinator
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            return 0
        if volume := master_coord.data.get("status", {}).get("volume"):
            return float(volume) / 100
        return 0

    @property
    def is_volume_muted(self):
        # Get master's mute state directly from its coordinator
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            return None
        return master_coord.data.get("status", {}).get("mute")

    @property
    def extra_state_attributes(self):
        # Expose per-slave volume/mute
        attrs = {}
        for ip, m in self.group_info.get("members", {}).items():
            attrs[f"member_{ip}_volume"] = m.get("volume")
            attrs[f"member_{ip}_mute"] = m.get("mute")
            attrs[f"member_{ip}_name"] = m.get("name")
        return attrs

    @property
    def supported_features(self):
        return self._attr_supported_features

    @property
    def entity_picture(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            _LOGGER.debug("[WiiMGroup] No coordinator found for master %s in group %s", self.master_ip, self._attr_name)
            return None
        pic = master_coord.data.get("status", {}).get("entity_picture")
        if not pic:
            _LOGGER.debug("[WiiMGroup] No entity_picture for master %s in group %s: %s", self.master_ip, self._attr_name, master_coord.data.get("status", {}))
        return pic

    @property
    def media_title(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            _LOGGER.debug("[WiiMGroup] No coordinator found for master %s in group %s", self.master_ip, self._attr_name)
            return None
        title = master_coord.data.get("status", {}).get("title")
        if not title:
            _LOGGER.debug("[WiiMGroup] No media_title for master %s in group %s: %s", self.master_ip, self._attr_name, master_coord.data.get("status", {}))
        return title

    @property
    def media_artist(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            _LOGGER.debug("[WiiMGroup] No coordinator found for master %s in group %s", self.master_ip, self._attr_name)
            return None
        artist = master_coord.data.get("status", {}).get("artist")
        if not artist:
            _LOGGER.debug("[WiiMGroup] No media_artist for master %s in group %s: %s", self.master_ip, self._attr_name, master_coord.data.get("status", {}))
        return artist

    @property
    def media_album_name(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if not master_coord:
            _LOGGER.debug("[WiiMGroup] No coordinator found for master %s in group %s", self.master_ip, self._attr_name)
            return None
        album = master_coord.data.get("status", {}).get("album")
        if not album:
            _LOGGER.debug("[WiiMGroup] No media_album_name for master %s in group %s: %s", self.master_ip, self._attr_name, master_coord.data.get("status", {}))
        return album

    @property
    def media_position(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if master_coord:
            return master_coord.data.get("status", {}).get("position")
        return None

    @property
    def media_duration(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if master_coord:
            return master_coord.data.get("status", {}).get("duration")
        return None

    @property
    def media_position_updated_at(self):
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if master_coord:
            return master_coord.data.get("status", {}).get("position_updated_at")
        return None

    async def async_set_volume_level(self, volume):
        # Relative group volume logic: all members change by the same delta
        group = self.group_info
        if not group or not group["members"]:
            return
        current_max = max(m.get("volume", 0) for m in group["members"].values())
        new_max = int(volume * 100)
        delta = new_max - current_max
        for ip, m in group["members"].items():
            cur = m.get("volume", 0)
            new_vol = max(0, min(100, cur + delta))
            # Set volume via API (master or slave)
            coord = self._find_coordinator_by_ip(ip)
            if coord:
                await coord.client.set_volume(new_vol / 100)

    async def async_mute_volume(self, mute: bool):
        # Mute/unmute all members
        group = self.group_info
        for ip in group.get("members", {}):
            coord = self._find_coordinator_by_ip(ip)
            if coord:
                await coord.client.set_mute(mute)

    async def async_media_play(self):
        # Play on all members
        for ip in self.group_members:
            coord = self._find_coordinator_by_ip(ip)
            if coord:
                await coord.client.play()

    async def async_media_pause(self):
        # Pause on all members
        for ip in self.group_members:
            coord = self._find_coordinator_by_ip(ip)
            if coord:
                await coord.client.pause()

    async def async_media_next_track(self):
        """Send next track command to the group master only."""
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if master_coord:
            await master_coord.client.next_track()
        else:
            _LOGGER.warning("[WiiMGroup] No coordinator found for master %s when trying to send next_track", self.master_ip)

    async def async_media_previous_track(self):
        """Send previous track command to the group master only."""
        master_coord = self._find_coordinator_by_ip(self.master_ip)
        if master_coord:
            await master_coord.client.previous_track()
        else:
            _LOGGER.warning("[WiiMGroup] No coordinator found for master %s when trying to send previous_track", self.master_ip)

    def _find_coordinator_by_ip(self, ip):
        # Helper to find coordinator by IP
        for coord in self.hass.data[DOMAIN].values():
            if coord.client.host == ip:
                role = coord.data.get("role")
                multiroom = coord.data.get("multiroom", {})
                _LOGGER.debug(
                    "[WiiMGroup] Found coordinator for %s: role=%s, multiroom=%s, data=%s",
                    ip, role, multiroom, coord.data
                )
                return coord
        _LOGGER.warning("[WiiMGroup] No coordinator found for IP %s", ip)
        return None