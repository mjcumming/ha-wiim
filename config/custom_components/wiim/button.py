"""Button entities for WiiM speakers: Reboot and Sync Time."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WiiMCoordinator
from .api import WiiMError

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: WiiMCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        WiiMRebootButton(coordinator),
        WiiMSyncTimeButton(coordinator),
    ]
    async_add_entities(entities)

class WiiMRebootButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator: WiiMCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}-reboot"
        self._attr_name = "Reboot"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.client.host)},
            name=f"WiiM {coordinator.client.host}",
            manufacturer="WiiM",
        )
    async def async_press(self) -> None:
        try:
            await self.coordinator.client.reboot()
        except WiiMError as err:
            raise Exception(f"Failed to reboot WiiM device: {err}")

class WiiMSyncTimeButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator: WiiMCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.client.host}-sync_time"
        self._attr_name = "Sync Time"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.client.host)},
            name=f"WiiM {coordinator.client.host}",
            manufacturer="WiiM",
        )
    async def async_press(self) -> None:
        try:
            await self.coordinator.client.sync_time()
        except WiiMError as err:
            raise Exception(f"Failed to sync time on WiiM device: {err}")