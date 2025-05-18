"""WiiM coordinator for handling device updates and groups."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
import asyncio

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WiiMClient, WiiMError
from .const import (
    ATTR_GROUP_MEMBERS,
    ATTR_GROUP_LEADER,
    CONF_HOST,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class WiiMCoordinator(DataUpdateCoordinator):
    """WiiM coordinator for handling device updates and groups."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: WiiMClient,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Initialize WiiM coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client._host}",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self._group_members: set[str] = set()
        self._is_ha_group_leader = False
        self._ha_group_members: set[str] = set()
        self._base_poll_interval = poll_interval  # seconds
        self._consecutive_failures = 0
        self._imported_hosts: set[str] = set()
        # New: group registry
        self._groups: dict[str, dict] = {}  # master_ip -> group info
        self._last_title = None
        self._last_meta_info = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from WiiM device."""
        try:
            # Parallel fetch detailed status, basic status, and slave list (no meta info here)
            player_status, basic_status, multiroom = await asyncio.gather(
                self.client.get_player_status(),
                self.client.get_status(),
                self.client.get_multiroom_info(),
            )

            status = {**basic_status, **player_status}
            current_title = status.get("title")

            # Only fetch meta info if title changed
            if current_title != self._last_title or not self._last_meta_info:
                meta_info = await self.client.get_meta_info()
                self._last_title = current_title
                self._last_meta_info = meta_info
            else:
                meta_info = self._last_meta_info

            # Merge meta info
            if meta_info:
                status["album"] = meta_info.get("album")
                status["title"] = meta_info.get("title")
                status["artist"] = meta_info.get("artist")
                status["entity_picture"] = meta_info.get("albumArtURI")

            # Ensure source list exists so Lovelace shows picker
            if not status.get("sources"):
                try:
                    status["sources"] = await self.client.get_sources()
                except WiiMError as err:
                    _LOGGER.debug("Failed to fetch source list: %s", err)

            # Derive role
            if status.get("type") == "1" or status.get("master_uuid"):
                role = "guest"
            elif multiroom.get("slaves", 0) > 0:
                role = "master"
            else:
                role = "solo"

            # Update group registry
            self._update_group_registry(status, multiroom)

            # If we reach here the poll succeeded – reset failure counter and interval
            if self._consecutive_failures:
                self._consecutive_failures = 0
                if (
                    self.update_interval is not None
                    and self.update_interval.total_seconds() != self._base_poll_interval
                ):
                    self.update_interval = timedelta(seconds=self._base_poll_interval)

            # Update multiroom status & trigger discovery of new slave IPs
            self._group_members = {
                entry.get("ip") for entry in multiroom.get("slave_list", []) if entry.get("ip")
            }

            await self._async_trigger_slave_discovery()
            self._update_ha_group_status()

            return {
                "status": status,
                "multiroom": multiroom,
                "role": role,
                "ha_group": {
                    "is_leader": self._is_ha_group_leader,
                    "members": list(self._ha_group_members),
                },
            }
        except WiiMError as err:
            # Progressive back-off on consecutive failures to reduce log spam
            self._consecutive_failures += 1
            if self._consecutive_failures >= 3:
                new_interval = min(
                    self._base_poll_interval * (2 ** (self._consecutive_failures - 2)),
                    60,
                )
                if (
                    self.update_interval is None
                    or new_interval != self.update_interval.total_seconds()
                ):
                    self.update_interval = timedelta(seconds=new_interval)
            raise UpdateFailed(f"Error updating WiiM device: {err}")

    def _update_group_registry(self, status: dict, multiroom: dict) -> None:
        """Update the group registry with current group info."""
        master_ip = self.client.host if multiroom.get("slaves", 0) > 0 else multiroom.get("master_uuid")
        if not master_ip:
            return
        master_name = status.get("device_name") or "WiiM Group"
        group_info = self._groups.setdefault(master_ip, {"members": {}, "master": master_ip, "name": master_name})
        group_info["name"] = master_name  # Always update name in case it changes
        # Add master
        group_info["members"][self.client.host] = {
            "volume": status.get("volume", 0),
            "mute": status.get("mute", False),
            "state": status.get("play_status"),
            "name": master_name,
        }
        # Add slaves
        for entry in multiroom.get("slave_list", []):
            ip = entry.get("ip")
            if not ip:
                continue
            slave_name = entry.get("name") or f"WiiM {ip}"
            group_info["members"][ip] = {
                "volume": entry.get("volume", 0),
                "mute": bool(entry.get("mute", False)),
                "state": None,  # Will be filled in by polling that device
                "name": slave_name,
            }
        # Clean up any members no longer present
        current_ips = {self.client.host} | {entry.get("ip") for entry in multiroom.get("slave_list", []) if entry.get("ip")}
        group_info["members"] = {ip: v for ip, v in group_info["members"].items() if ip in current_ips}

    def _update_ha_group_status(self) -> None:
        """Update Home Assistant group status."""
        entity_id = f"media_player.wiim_{self.client._host.replace('.', '_')}"
        entity = self.hass.states.get(entity_id)

        if entity is None:
            _LOGGER.debug("[WiiM] Coordinator: Entity %s not found for group status update", entity_id)
            return

        group_members = entity.attributes.get(ATTR_GROUP_MEMBERS, [])
        group_leader = entity.attributes.get(ATTR_GROUP_LEADER)

        _LOGGER.debug("[WiiM] Coordinator: Entity %s group_members: %s, group_leader: %s", entity_id, group_members, group_leader)

        self._ha_group_members = set(group_members)
        self._is_ha_group_leader = group_leader == entity_id

    async def _async_trigger_slave_discovery(self) -> None:
        """Start config flows for new slave IPs that HA doesn't know yet."""
        for ip in self._group_members:
            if ip in self._imported_hosts:
                continue

            # Skip if already present
            if any(coord.client.host == ip for coord in self.hass.data.get(DOMAIN, {}).values()):
                self._imported_hosts.add(ip)
                continue

            self._imported_hosts.add(ip)

            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "import"},
                    data={CONF_HOST: ip},
                )
            )
            _LOGGER.debug("Started import flow for slave %s", ip)

    async def create_wiim_group(self) -> None:
        """Create a WiiM multiroom group."""
        try:
            _LOGGER.info("[WiiM] Coordinator: Creating new WiiM group for %s", self.client.host)
            await self.client.create_group()
            _LOGGER.info("[WiiM] Coordinator: Successfully created WiiM group for %s", self.client.host)
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("[WiiM] Coordinator: Failed to create WiiM group for %s: %s", self.client.host, err)
            raise

    async def delete_wiim_group(self) -> None:
        """Delete the WiiM multiroom group."""
        try:
            _LOGGER.info("[WiiM] Coordinator: Deleting WiiM group for %s", self.client.host)
            await self.client.delete_group()
            _LOGGER.info("[WiiM] Coordinator: Successfully deleted WiiM group for %s", self.client.host)
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("[WiiM] Coordinator: Failed to delete WiiM group for %s: %s", self.client.host, err)
            raise

    async def join_wiim_group(self, master_ip: str) -> None:
        """Join a WiiM multiroom group."""
        try:
            _LOGGER.info("[WiiM] Coordinator: %s joining WiiM group with master %s", self.client.host, master_ip)
            await self.client.join_group(master_ip)
            _LOGGER.info("[WiiM] Coordinator: %s successfully joined WiiM group with master %s", self.client.host, master_ip)
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("[WiiM] Coordinator: %s failed to join WiiM group with master %s: %s", self.client.host, master_ip, err)
            raise

    async def leave_wiim_group(self) -> None:
        """Leave the WiiM multiroom group."""
        try:
            _LOGGER.info("[WiiM] Coordinator: %s leaving WiiM group", self.client.host)
            await self.client.leave_group()
            _LOGGER.info("[WiiM] Coordinator: %s successfully left WiiM group", self.client.host)
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("[WiiM] Coordinator: %s failed to leave WiiM group: %s", self.client.host, err)
            raise

    @property
    def is_wiim_master(self) -> bool:
        """Return whether this device is a WiiM multiroom master."""
        return self.client.is_master

    @property
    def is_wiim_slave(self) -> bool:
        """Return whether this device is a WiiM multiroom slave."""
        return self.client.is_slave

    @property
    def wiim_group_members(self) -> set[str]:
        """Return set of WiiM group member IPs."""
        return self._group_members

    @property
    def is_ha_group_leader(self) -> bool:
        """Return whether this device is a HA media player group leader."""
        return self._is_ha_group_leader

    @property
    def ha_group_members(self) -> set[str]:
        """Return set of HA group member entity IDs."""
        return self._ha_group_members

    @property
    def groups(self) -> dict:
        """Return the current group registry."""
        return self._groups

    def get_group_by_master(self, master_ip: str) -> dict | None:
        """Get group info by master IP."""
        return self._groups.get(master_ip)

    def get_member_info(self, ip: str) -> dict | None:
        """Get member info by IP."""
        for group in self._groups.values():
            if ip in group["members"]:
                return group["members"][ip]
        return None
