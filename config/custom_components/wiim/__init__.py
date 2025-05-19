"""The WiiM integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WiiMClient
from .const import DOMAIN, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
from .coordinator import WiiMCoordinator

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR, Platform.BUTTON, Platform.NUMBER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WiiM from a config entry."""
    # Re-use Home Assistant's global aiohttp session to avoid unclosed-session warnings.
    client = WiiMClient(entry.data["host"], session=async_get_clientsession(hass))
    # Validate device is reachable; initial data will be fetched by coordinator
    await client.get_status()
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    coordinator = WiiMCoordinator(hass, client, poll_interval=poll_interval)
    coordinator.entry_id = entry.entry_id  # type: ignore[attr-defined]

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    # ------------------------------------------------------------------
    # Update entry title to user-friendly device name on first setup
    # ------------------------------------------------------------------

    status = coordinator.data.get("status", {}) if isinstance(coordinator.data, dict) else {}
    friendly_name = status.get("device_name") or status.get("DeviceName")
    if friendly_name and friendly_name != entry.title:
        hass.config_entries.async_update_entry(entry, title=friendly_name)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # No need for explicit shutdown handler – HA will close the shared session.

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
