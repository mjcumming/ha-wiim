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

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from WiiM device."""
        try:
            # Parallel fetch detailed status, basic status, and slave list
            player_status, basic_status, multiroom = await asyncio.gather(
                self.client.get_player_status(),
                self.client.get_status(),
                self.client.get_multiroom_info(),
            )

            # Merge – player_status has dynamic fields, basic_status adds static info
            status = {**basic_status, **player_status}

            # Ensure source list exists so Lovelace shows picker
            if not status.get("sources"):
                try:
                    status["sources"] = await self.client.get_sources()
                except WiiMError as err:
                    _LOGGER.debug("Failed to fetch source list: %s", err)

            # Derive role
            if status.get("type") == "1" or status.get("master_uuid"):
                role = "guest"
            elif multiroom.get("slave_count", 0) > 0:
                role = "master"
            else:
                role = "solo"

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
                entry.get("ip") for entry in multiroom.get("slaves", []) if entry.get("ip")
            }

            await self._async_trigger_slave_discovery()

            # Update HA group status
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
            # Start increasing after 3 failures, up to 60 seconds
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

    def _update_ha_group_status(self) -> None:
        """Update Home Assistant group status."""
        # Check if this device is part of a HA media player group
        entity_id = f"media_player.wiim_{self.client._host.replace('.', '_')}"
        entity = self.hass.states.get(entity_id)

        if entity is None:
            return

        # Get group information from entity attributes
        group_members = entity.attributes.get(ATTR_GROUP_MEMBERS, [])
        group_leader = entity.attributes.get(ATTR_GROUP_LEADER)

        # Update internal state
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
            await self.client.create_group()
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to create WiiM group: %s", err)
            raise

    async def delete_wiim_group(self) -> None:
        """Delete the WiiM multiroom group."""
        try:
            await self.client.delete_group()
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to delete WiiM group: %s", err)
            raise

    async def join_wiim_group(self, master_ip: str) -> None:
        """Join a WiiM multiroom group."""
        try:
            await self.client.join_group(master_ip)
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to join WiiM group: %s", err)
            raise

    async def leave_wiim_group(self) -> None:
        """Leave the WiiM multiroom group."""
        try:
            await self.client.leave_group()
            await self.async_refresh()
        except WiiMError as err:
            _LOGGER.error("Failed to leave WiiM group: %s", err)
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
