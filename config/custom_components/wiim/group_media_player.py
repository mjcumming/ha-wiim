from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerState
from .const import DOMAIN

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

    @property
    def group_info(self):
        return self.coordinator.get_group_by_master(self.master_ip) or {}

    @property
    def group_members(self):
        return list(self.group_info.get("members", {}).keys())

    @property
    def group_leader(self):
        return self.master_ip

    @property
    def state(self):
        # Aggregated: playing if any member is playing, paused if all paused, idle if all idle
        states = [m.get("state") for m in self.group_info.get("members", {}).values() if m.get("state")]
        if not states:
            return MediaPlayerState.IDLE
        if any(s == MediaPlayerState.PLAYING or s == "play" for s in states):
            return MediaPlayerState.PLAYING
        if all(s == MediaPlayerState.PAUSED or s == "pause" for s in states):
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self):
        # Max of all member volumes (0-1), default to 0 if missing
        vols = [m.get("volume", 0) or 0 for m in self.group_info.get("members", {}).values()]
        if not vols:
            return 0
        return max(vols) / 100

    @property
    def is_volume_muted(self):
        # True if all members are muted
        mutes = [m.get("mute") for m in self.group_info.get("members", {}).values()]
        return all(mutes) if mutes else None

    @property
    def extra_state_attributes(self):
        # Expose per-slave volume/mute
        attrs = {}
        for ip, m in self.group_info.get("members", {}).items():
            attrs[f"member_{ip}_volume"] = m.get("volume")
            attrs[f"member_{ip}_mute"] = m.get("mute")
            attrs[f"member_{ip}_name"] = m.get("name")
        return attrs

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

    def _find_coordinator_by_ip(self, ip):
        # Helper to find coordinator by IP
        for coord in self.hass.data[DOMAIN].values():
            if coord.client.host == ip:
                return coord
        return None