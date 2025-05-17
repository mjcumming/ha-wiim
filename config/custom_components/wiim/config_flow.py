from __future__ import annotations

from typing import Any
from urllib.parse import urlparse
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import WiiMClient, WiiMError
from .const import (
    CONF_POLL_INTERVAL,
    CONF_VOLUME_STEP,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_VOLUME_STEP,
    DOMAIN,
)

# --- UPnP/SSDP discovery imports ---
try:
    from async_upnp_client.search import async_search
except ImportError:
    async_search = None

_LOGGER = logging.getLogger(__name__)

async def _async_validate_host(host: str) -> None:
    """Validate we can talk to the WiiM device and always close the session."""
    client = WiiMClient(host)
    try:
        await client.get_status()
    finally:
        # Ensure the underlying aiohttp session is closed even on failure
        await client.close()


class WiiMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a WiiM config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Set up instance."""
        self._host: str | None = None
        self._discovered_hosts: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "WiiMOptionsFlow":
        """Return the options flow."""
        return WiiMOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (manual or UPnP discovery)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await _async_validate_host(host)
            except WiiMError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"WiiM {host}", data={CONF_HOST: host}
                )

        # Offer UPnP discovery as a fallback
        if async_search is not None:
            return await self.async_step_upnp()

        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_upnp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Discover WiiM/LinkPlay devices via UPnP/SSDP."""
        errors: dict[str, str] = {}
        if not self._discovered_hosts:
            # Perform UPnP discovery
            self._discovered_hosts = await self._discover_upnp_hosts()
        if user_input is not None:
            host = user_input[CONF_HOST]
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await _async_validate_host(host)
            except WiiMError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"WiiM {host}", data={CONF_HOST: host}
                )
        if self._discovered_hosts:
            schema = vol.Schema({vol.Required(CONF_HOST): vol.In(self._discovered_hosts)})
            return self.async_show_form(step_id="upnp", data_schema=schema, errors=errors, description_placeholders={"count": str(len(self._discovered_hosts))})
        # If no devices found, fall back to manual
        schema = vol.Schema({vol.Required(CONF_HOST): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _discover_upnp_hosts(self) -> list[str]:
        """Use async_upnp_client to discover WiiM/LinkPlay devices on the network."""
        if async_search is None:
            return []

        found_hosts: set[str] = set()

        async def _callback(device):  # type: ignore[missing-param-doc]
            """Collect hosts from SSDP discovery callback."""
            # `SsdpDevice` objects provide a `host` attribute with the IP address.
            host = getattr(device, "host", None)

            # Fallback to parsing LOCATION header if attribute missing (older versions)
            if host is None:
                location = getattr(device, "location", None)
                if location:
                    host = urlparse(location).hostname

            if host:
                found_hosts.add(host)

        # Use a short timeout for discovery
        await async_search(async_callback=_callback, timeout=5)

        return list(found_hosts)

    async def async_step_zeroconf(self, discovery_info: dict[str, Any]) -> FlowResult:  # noqa: D401
        """Handle Zeroconf discovery."""
        host = discovery_info["host"]
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()

        try:
            await _async_validate_host(host)
        except WiiMError:
            return self.async_abort(reason="cannot_connect")

        self.context["configuration_in_progress"] = True
        self._host = host
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"WiiM {self._host}", data={CONF_HOST: self._host}
            )

        return self.async_show_form(step_id="confirm")

    # -----------------------------------------------------
    # SSDP discovery (native HA flow) ---------------------
    # -----------------------------------------------------

    async def async_step_ssdp(self, discovery_info: dict[str, Any]) -> FlowResult:  # noqa: D401
        """Handle SSDP discovery from Home Assistant core."""

        _LOGGER.debug("SSDP discovery: %s", discovery_info)

        # Get device host – depending on HA version field may be 'host' or 'ssdp_location'.
        host = discovery_info.get("host")
        if not host and (loc := discovery_info.get("ssdp_location")):
            from urllib.parse import urlparse

            host = urlparse(loc).hostname

        _LOGGER.debug("SSDP candidate host: %s", host)

        if not host:
            return self.async_abort(reason="no_host")

        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()

        try:
            await _async_validate_host(host)
        except WiiMError:
            return self.async_abort(reason="cannot_connect")

        self._host = host
        return await self.async_step_confirm()


class WiiMOptionsFlow(config_entries.OptionsFlow):
    """Handle WiiM options."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Init options flow."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:  # noqa: D401
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=self.entry.options.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_VOLUME_STEP,
                    default=self.entry.options.get(
                        CONF_VOLUME_STEP, DEFAULT_VOLUME_STEP
                    ),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=0.5)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
