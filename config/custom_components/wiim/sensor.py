"""Diagnostic sensors for WiiM speakers."""

from __future__ import annotations

import logging
from typing import Any, Final

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_WIFI_RSSI,
    ATTR_WIFI_CHANNEL,
    ATTR_GROUP_ROLE,
    DOMAIN,
)
from .coordinator import WiiMCoordinator

_LOGGER = logging.getLogger(__name__)

SENSORS: Final = {
    ATTR_WIFI_RSSI: {
        "name": "WiFi RSSI",
        "unit": "dBm",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
    },
    ATTR_WIFI_CHANNEL: {
        "name": "WiFi Channel",
        "unit": None,
        "device_class": None,
    },
    ATTR_GROUP_ROLE: {
        "name": "Group Role",
        "unit": None,
        "device_class": None,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up diagnostic sensors for a config entry."""
    coordinator: WiiMCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []

    for key in SENSORS:
        entities.append(_WiiMDiagnosticSensor(coordinator, key))

    async_add_entities(entities)


class _WiiMDiagnosticSensor(CoordinatorEntity[WiiMCoordinator], SensorEntity):
    """A single read‐only diagnostic attribute exposed as a sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WiiMCoordinator, attribute: str) -> None:
        super().__init__(coordinator)
        self._attribute = attribute
        meta = SENSORS[attribute]
        self._attr_unique_id = f"{coordinator.client.host}-{attribute}"
        self._attr_name = meta["name"]
        self._attr_native_unit_of_measurement = meta["unit"]
        self._attr_device_class = meta["device_class"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.client.host)},
            name=f"WiiM {coordinator.client.host}",
            manufacturer="WiiM",
        )

    @property
    def native_value(self) -> Any | None:  # type: ignore[override]
        status = self.coordinator.data.get("status", {})
        if self._attribute == ATTR_WIFI_RSSI:
            return status.get("wifi_rssi") or status.get("RSSI")
        if self._attribute == ATTR_WIFI_CHANNEL:
            return status.get("wifi_channel") or status.get("WifiChannel")
        if self._attribute == ATTR_GROUP_ROLE:
            return self.coordinator.data.get("role")
        return None