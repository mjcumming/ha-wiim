"""WiiM HTTP API client."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import async_timeout
from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError, ClientConnectorCertificateError
import ssl

from .const import (
    API_ENDPOINT_CLEAR_PLAYLIST,
    API_ENDPOINT_DEVICE_INFO,
    API_ENDPOINT_EQ_CUSTOM,
    API_ENDPOINT_EQ_GET,
    API_ENDPOINT_EQ_PRESET,
    API_ENDPOINT_FIRMWARE,
    API_ENDPOINT_GROUP_CREATE,
    API_ENDPOINT_GROUP_DELETE,
    API_ENDPOINT_GROUP_EXIT,
    API_ENDPOINT_GROUP_JOIN,
    API_ENDPOINT_LED,
    API_ENDPOINT_LED_BRIGHTNESS,
    API_ENDPOINT_MAC,
    API_ENDPOINT_MUTE,
    API_ENDPOINT_NEXT,
    API_ENDPOINT_PAUSE,
    API_ENDPOINT_PLAYLIST,
    API_ENDPOINT_PLAY,
    API_ENDPOINT_POWER,
    API_ENDPOINT_PREV,
    API_ENDPOINT_PRESET,
    API_ENDPOINT_REPEAT,
    API_ENDPOINT_SEEK,
    API_ENDPOINT_SHUFFLE,
    API_ENDPOINT_SOURCE,
    API_ENDPOINT_SOURCES,
    API_ENDPOINT_STATUS,
    API_ENDPOINT_STOP,
    API_ENDPOINT_VOLUME,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    EQ_PRESET_CUSTOM,
    PLAY_MODE_NORMAL,
    PLAY_MODE_REPEAT_ALL,
    PLAY_MODE_REPEAT_ONE,
    PLAY_MODE_SHUFFLE,
    PLAY_MODE_SHUFFLE_REPEAT_ALL,
)

_LOGGER = logging.getLogger(__name__)

WIIM_CA_CERT = """-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKu1yRsYJzszMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
BAYTAk5MMRMwEQYDVQQIDApTb21lLVN0YXRlMQ8wDQYDVQQHDAZBbXN0ZXJkYW0x
EjAQBgNVBAoMCVdpZU0gSW5jLjAeFw0yNTAxMDEwMDAwMDBaFw0zNTAxMDEwMDAw
MDBaMEUxCzAJBgNVBAYTAk5MMRMwEQYDVQQIDApTb21lLVN0YXRlMQ8wDQYDVQQH
DAZBbXN0ZXJkYW0xEjAQBgNVBAoMCVdpZU0gSW5jLjCCASIwDQYJKoZIhvcNAQEB
BQADggEPADCCAQoCggEBAMm3gZCPtGHBX9nuSUXwxLBzME2YkdE+5EYXPLkZXl2b
usZT6F4LmSpaV0t1Ik5+pUvNbK/CtYQgQki71R+xVQ1BM8DT6vKrrO5gkP7FpC18
pDutLCRa14Q6gttxyPjdvVSdGInxjeRGna43EIBgzHuLlHotE5T7V6czS4QhIwJI
YOvTo95OfzmiEJeZVrDCTnhgypKekJy5o+1OtSWT8gJtIhXCTITVEWilR92pT9bk
M54q9WlH0I1GtIsfRSAxEPPGjBJOCa/MEGLjm+rXhN3kLBXjg5eQof8I4eAbOeXK
YIZHuZOKhHvJ3C0cFLbFhF38sZ4N2VNivXzXcXcCAwEAAaNTMFEwHQYDVR0OBBYE
FA/7t6kTpsuRWpu9X6lzNN2O0oSbMB8GA1UdIwQYMBaAFA/7t6kTpsuRWpu9X6lz
NN2O0oSbMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAGX2HFqT
2bQVWwtIg9Y9ycYzaO+F6DRKCVh0b07XHtcwPa5RWPLXxF75PwQxzb62LF8A3+yQ
psOSJyYwcmBHQYaWV7k/akdUSHh3D1ynjUTduVdJN9WewtG/XAIN5e8w1sM+dBos
BgU984wgKqeFTig84yYI6FqdtYYG6iwSeNBY0d5hDOGOZa2mYIZHuZOKhHvJ3C0c
FLbFhF38sZ4N2VNivXzXcXc=
-----END CERTIFICATE-----"""

HEADERS = {"Connection": "close"}


class WiiMError(Exception):
    """Base exception for WiiM errors."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        """Initialize WiiM error."""
        super().__init__(message)
        self.error_code = error_code


class WiiMConnectionError(WiiMError):
    """Exception raised for connection errors."""


class WiiMTimeoutError(WiiMError):
    """Exception raised for timeout errors."""


class WiiMResponseError(WiiMError):
    """Exception raised for invalid responses."""


class WiiMClient:
    """WiiM HTTP API client."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: int = DEFAULT_TIMEOUT,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize WiiM client."""
        self._host = host
        self._port = port
        self._timeout = ClientTimeout(total=timeout)
        self._session = session
        self._lock = asyncio.Lock()
        self._base_url = f"https://{host}:{port}"
        self._group_master: str | None = None
        self._group_slaves: list[str] = []
        self._ssl_context: ssl.SSLContext | None = None

    @property
    def host(self) -> str:
        """Return the host address."""
        return self._host

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Return (and lazily create) the SSL context with the pinned CA."""
        if self._ssl_context is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False  # Self-signed cert, hostname mismatch
            ctx.load_verify_locations(cadata=WIIM_CA_CERT)
            self._ssl_context = ctx
        return self._ssl_context

    async def _request(
        self, endpoint: str, method: str = "GET", **kwargs: Any
    ) -> dict[str, Any]:
        """Make a request to the WiiM device with retry on SSL errors."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

        url = f"{self._base_url}{endpoint}"
        kwargs.setdefault("headers", HEADERS)
        ssl_ctx = self._get_ssl_context()
        kwargs["ssl"] = ssl_ctx

        def raise_error(error: Exception) -> None:
            """Raise the appropriate error."""
            if isinstance(error, asyncio.TimeoutError):
                raise WiiMTimeoutError(
                    f"Timeout communicating with WiiM device: {error}"
                )
            if isinstance(error, ClientError):
                raise WiiMConnectionError(
                    f"Error communicating with WiiM device: {error}"
                )
            raise error

        async with self._lock:
            try:
                async with async_timeout.timeout(self._timeout.total):
                    async with self._session.request(method, url, **kwargs) as response:
                        response.raise_for_status()
                        text = await response.text()
                        if not text:
                            return {}

                        # Some firmware versions return a garbled frame on the
                        # first request after boot (e.g. "HTTP/1.1 200 OK").
                        # If the payload clearly isn't JSON, ignore it once.
                        if not text.lstrip().startswith(("{", "[")):
                            _LOGGER.warning(
                                "Discarding non-JSON payload from WiiM device: %s",
                                text[:50],
                            )
                            return {}

                        data = json.loads(text)
                        if "error" in data:
                            raise WiiMResponseError(
                                f"WiiM API error: {data['error']}",
                                error_code=data.get("error_code"),
                            )
                        return data
            except ClientConnectorCertificateError:
                # Retry with insecure SSL exactly like python-linkplay to maximise compatibility
                kwargs["ssl"] = False  # type: ignore
                async with self._session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    text = await response.text()
                    return json.loads(text) if text else {}
            except (asyncio.TimeoutError, ClientError, json.JSONDecodeError) as err:
                raise_error(err)
            except Exception as err:
                raise WiiMError(f"Unexpected error: {err}")

    # Basic Player Controls
    async def get_status(self) -> dict[str, Any]:
        """Get the current status of the WiiM device."""
        return await self._request(API_ENDPOINT_STATUS)

    async def play(self) -> None:
        """Play the current track."""
        await self._request(API_ENDPOINT_PLAY)

    async def pause(self) -> None:
        """Pause the current track."""
        await self._request(API_ENDPOINT_PAUSE)

    async def stop(self) -> None:
        """Stop playback."""
        await self._request(API_ENDPOINT_STOP)

    async def next_track(self) -> None:
        """Play the next track."""
        await self._request(API_ENDPOINT_NEXT)

    async def previous_track(self) -> None:
        """Play the previous track."""
        await self._request(API_ENDPOINT_PREV)

    async def set_volume(self, volume: float) -> None:
        """Set the volume level (0-1)."""
        volume_pct = int(volume * 100)
        await self._request(f"{API_ENDPOINT_VOLUME}{volume_pct}")

    async def set_mute(self, mute: bool) -> None:
        """Set mute state."""
        await self._request(f"{API_ENDPOINT_MUTE}{1 if mute else 0}")

    async def set_power(self, power: bool) -> None:
        """Set power state."""
        await self._request(f"{API_ENDPOINT_POWER}{1 if power else 0}")

    # Playback Control
    async def set_repeat_mode(self, mode: str) -> None:
        """Set repeat mode."""
        if mode not in (PLAY_MODE_NORMAL, PLAY_MODE_REPEAT_ALL, PLAY_MODE_REPEAT_ONE):
            raise ValueError(f"Invalid repeat mode: {mode}")
        await self._request(f"{API_ENDPOINT_REPEAT}{mode}")

    async def set_shuffle_mode(self, mode: str) -> None:
        """Set shuffle mode."""
        if mode not in (
            PLAY_MODE_NORMAL,
            PLAY_MODE_SHUFFLE,
            PLAY_MODE_SHUFFLE_REPEAT_ALL,
        ):
            raise ValueError(f"Invalid shuffle mode: {mode}")
        await self._request(f"{API_ENDPOINT_SHUFFLE}{mode}")

    async def seek(self, position: int) -> None:
        """Seek to position in seconds."""
        await self._request(f"{API_ENDPOINT_SEEK}{position}")

    async def clear_playlist(self) -> None:
        """Clear the current playlist."""
        await self._request(API_ENDPOINT_CLEAR_PLAYLIST)

    # Multiroom
    async def get_multiroom_status(self) -> dict[str, Any]:
        """Get multiroom status including master/slave relationships."""
        status = await self.get_status()
        multiroom = status.get("multiroom", {})

        # Update internal state
        self._group_master = multiroom.get("master")
        self._group_slaves = multiroom.get("slaves", [])

        return multiroom

    async def create_group(self) -> None:
        """Create a multiroom group and become the master."""
        await self._request(API_ENDPOINT_GROUP_CREATE)
        self._group_master = self._host
        self._group_slaves = []

    async def delete_group(self) -> None:
        """Delete the current multiroom group."""
        if not self._group_master:
            raise WiiMError("Not part of a multiroom group")
        await self._request(API_ENDPOINT_GROUP_DELETE)
        self._group_master = None
        self._group_slaves = []

    async def join_group(self, master_ip: str) -> None:
        """Join a multiroom group as a slave."""
        if self._group_master:
            raise WiiMError("Already part of a multiroom group")
        await self._request(f"{API_ENDPOINT_GROUP_JOIN}{master_ip}")
        self._group_master = master_ip
        self._group_slaves = []

    async def leave_group(self) -> None:
        """Leave the current multiroom group."""
        if not self._group_master:
            raise WiiMError("Not part of a multiroom group")
        await self._request(API_ENDPOINT_GROUP_EXIT)
        self._group_master = None
        self._group_slaves = []

    @property
    def is_master(self) -> bool:
        """Return whether this device is a multiroom master."""
        return self._group_master == self._host

    @property
    def is_slave(self) -> bool:
        """Return whether this device is a multiroom slave."""
        return self._group_master is not None and not self.is_master

    @property
    def group_master(self) -> str | None:
        """Return the IP of the group master if part of a group."""
        return self._group_master

    @property
    def group_slaves(self) -> list[str]:
        """Return list of slave IPs if this device is a master."""
        return self._group_slaves if self.is_master else []

    # EQ Controls
    async def set_eq_preset(self, preset: str) -> None:
        """Set EQ preset."""
        await self._request(f"{API_ENDPOINT_EQ_PRESET}{preset}")

    async def set_eq_custom(self, eq_values: list[int]) -> None:
        """Set custom EQ values (10 bands)."""
        if len(eq_values) != 10:
            raise ValueError("EQ must have exactly 10 bands")
        eq_str = ",".join(str(v) for v in eq_values)
        await self._request(f"{API_ENDPOINT_EQ_CUSTOM}{eq_str}")

    async def get_eq(self) -> dict[str, Any]:
        """Get current EQ settings."""
        return await self._request(API_ENDPOINT_EQ_GET)

    # Source Selection
    async def set_source(self, source: str) -> None:
        """Set input source."""
        await self._request(f"{API_ENDPOINT_SOURCE}{source}")

    async def get_sources(self) -> list[str]:
        """Get available input sources."""
        response = await self._request(API_ENDPOINT_SOURCES)
        return response.get("sources", [])

    # Device Info
    async def get_device_info(self) -> dict[str, Any]:
        """Get device information."""
        return await self._request(API_ENDPOINT_DEVICE_INFO)

    async def get_firmware_version(self) -> str:
        """Get firmware version."""
        response = await self._request(API_ENDPOINT_FIRMWARE)
        return response.get("firmware", "")

    async def get_mac_address(self) -> str:
        """Get MAC address."""
        response = await self._request(API_ENDPOINT_MAC)
        return response.get("mac", "")

    # LED Control
    async def set_led(self, enabled: bool) -> None:
        """Set LED state."""
        await self._request(f"{API_ENDPOINT_LED}{1 if enabled else 0}")

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness (0-100)."""
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        await self._request(f"{API_ENDPOINT_LED_BRIGHTNESS}{brightness}")

    async def close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def play_preset(self, preset: int) -> None:
        """Play a preset (1-6)."""
        if not 1 <= preset <= 6:
            raise ValueError("Preset must be between 1 and 6")
        await self._request(f"{API_ENDPOINT_PRESET}{preset}")

    async def toggle_power(self) -> None:
        """Toggle power state."""
        status = await self.get_status()
        power = status.get("power", False)
        await self.set_power(not power)
