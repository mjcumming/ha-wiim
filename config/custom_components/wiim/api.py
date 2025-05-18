"""WiiM HTTP API client.

This file is **self-contained** – it does **not** import anything from the
external *python-linkplay* project.  A handful of small helper ideas (such as
certificate pinning and request/response structure) were originally inspired
by that library (© Velleman, MIT license).  We rewrote the relevant parts from
scratch so the custom component has **zero run-time dependencies** beyond the
standard library and *aiohttp* which Home Assistant already provides.

The attribution above satisfies the MIT licence; upstream code was trimmed
and re-implemented following Home Assistant's async best-practices and is now
maintained exclusively in this repository.
"""

from __future__ import annotations

import asyncio
import json
import logging
from http import HTTPStatus
from typing import Any

import aiohttp
import async_timeout
from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError
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
    PLAY_MODE_NORMAL,
    PLAY_MODE_REPEAT_ALL,
    PLAY_MODE_REPEAT_ONE,
    PLAY_MODE_SHUFFLE,
    PLAY_MODE_SHUFFLE_REPEAT_ALL,
    API_ENDPOINT_MULTIROOM_SLAVES,
    API_ENDPOINT_GROUP_SLAVES,
    API_ENDPOINT_GROUP_KICK,
    API_ENDPOINT_GROUP_SLAVE_MUTE,
)

_LOGGER = logging.getLogger(__name__)

WIIM_CA_CERT = """-----BEGIN CERTIFICATE-----
MIIDmDCCAoACAQEwDQYJKoZIhvcNAQELBQAwgZExCzAJBgNVBAYTAkNOMREwDwYD
VQQIDAhTaGFuZ2hhaTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtw
bGF5MQwwCgYDVQQLDANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAe
BgkqhkiG9w0BCQEWEW1haWxAbGlua3BsYXkuY29tMB4XDTE4MTExNTAzMzI1OVoX
DTQ2MDQwMTAzMzI1OVowgZExCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhTaGFuZ2hh
aTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtwbGF5MQwwCgYDVQQL
DANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAeBgkqhkiG9w0BCQEW
EW1haWxAbGlua3BsYXkuY29tMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEApP7trR9C8Ajr/CZqi70HYzQHZMX0gj8K3RzO0k5aucWiRkHtvcnfJIz+4dMB
EZHjv/STutsFBwbtD1iLEv48Cxvht6AFPuwTX45gYQ18hyEUC8wFhG7cW7Ek5HtZ
aLH75UFxrpl6zKn/Vy3SGL2wOd5qfBiJkGyZGgg78JxHVBZLidFuU6H6+fIyanwr
ejj8B5pz+KAui6T7SWA8u69UPbC4AmBLQxMPzIX/pirgtKZ7LedntanHlY7wrlAa
HroZOpKZxG6UnRCmw23RPHD6FUZq49f/zyxTFbTQe5NmjzG9wnKCf3R8Wgl8JPW9
4yAbOgslosTfdgrmjkPfFIP2JQIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQARmy6f
esrifhW5NM9i3xsEVp945iSXhqHgrtIROgrC7F1EIAyoIiBdaOvitZVtsYc7Ivys
QtyVmEGscyjuYTdfigvwTVVj2oCeFv1Xjf+t/kSuk6X3XYzaxPPnFG4nAe2VwghE
rbZG0K5l8iXM7Lm+ZdqQaAYVWsQDBG8lbczgkB9q5ed4zbDPf6Fsrsynxji/+xa4
9ARfyHlkCDBThGNnnl+QITtfOWxm/+eReILUQjhwX+UwbY07q/nUxLlK6yrzyjnn
wi2B2GovofQ/4icVZ3ecTqYK3q9gEtJi72V+dVHM9kSA4Upy28Y0U1v56uoqeWQ6
uc2m8y8O/hXPSfKd
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


class WiiMRequestError(WiiMError):
    """HTTP/TCP communication error while talking to the speaker."""


class WiiMInvalidDataError(WiiMError):
    """The device responded with malformed or non-JSON data."""


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
        # Some firmwares ship a *device-unique* self-signed certificate.  We
        # start optimistic (verify on) and permanently fall back to
        # *insecure* mode after the first verification failure to avoid the
        # noisy SSL errors on every poll.
        self._verify_ssl_default: bool = True

    @property
    def host(self) -> str:
        """Return the host address."""
        return self._host

    def _get_ssl_context(self) -> ssl.SSLContext:
        """Return (and lazily create) the SSL context.

        Home Assistant considers `ssl.create_default_context()` a blocking
        operation because it tries to load the system trust store from disk.
        To stay fully async-safe we instead create a bare `SSLContext` and
        explicitly load **only** the pinned WiiM root certificate. If loading
        the certificate fails for any reason (e.g. corrupted PEM), we fall
        back to an *unverified* context so the request code can still proceed
        and rely on the existing retry-with-insecure logic.
        """

        if self._ssl_context is not None:
            return self._ssl_context

        # Start with a minimal TLS client context (no file-system access)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False  # Device uses self-signed cert with host-mismatch

        try:
            ctx.load_verify_locations(cadata=WIIM_CA_CERT)
        except ssl.SSLError as err:
            # Invalid PEM bundled in the code – warn once and disable verification.
            _LOGGER.warning(
                "Failed to load pinned WiiM CA certificate (%s); falling back to "
                "insecure SSL – this is less secure but keeps the integration "
                "functional.",
                err,
            )
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        self._ssl_context = ctx
        return self._ssl_context

    async def _request(
        self, endpoint: str, method: str = "GET", **kwargs: Any
    ) -> dict[str, Any]:
        """Make a request to the WiiM device with retry on SSL errors."""
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)

        kwargs.setdefault("headers", HEADERS)

        async def _try_request(url: str, verify_ssl: bool) -> dict[str, Any] | None:
            """Inner helper to attempt a single request and return parsed JSON or raw text."""
            kwargs["ssl"] = self._get_ssl_context() if verify_ssl else False  # type: ignore

            _LOGGER.debug("WiiM HTTP %s %s (verify_ssl=%s)", method, url, verify_ssl)

            async with async_timeout.timeout(self._timeout.total):
                async with self._session.request(method, url, **kwargs) as response:
                    response.raise_for_status()
                    text = await response.text()

                    if not text:
                        _LOGGER.debug("%s -> empty response", url)
                        return {}
                    if not text.lstrip().startswith(("{", "[")):
                        _LOGGER.debug("%s -> non-JSON: %s", url, text.strip())
                        return {"raw": text.strip()}

                    _LOGGER.debug("%s -> %d bytes JSON", url, len(text))
                    return json.loads(text)

        # Build port/verify matrix based on previous results.
        if self._verify_ssl_default:
            ports_to_try = [
                (443, True),
                (443, False),
                (4443, True),
                (4443, False),
            ]
        else:
            ports_to_try = [
                (443, False),
                (4443, False),
            ]
        last_err: Exception | None = None
        tried: list[str] = []
        for port, verify_ssl in ports_to_try:
            url = f"https://{self._host}:{port}{endpoint}"
            tried.append(f"{url} (verify={verify_ssl})")
            try:
                result = await _try_request(url, verify_ssl)
                if result is not None:
                    _LOGGER.debug("Successful request on %s", url)
                    return result
            except (asyncio.TimeoutError, ClientError, json.JSONDecodeError) as err:
                # If verification failed once – remember and skip verified
                # attempts in the future.
                if verify_ssl and isinstance(err, ssl.SSLCertVerificationError):
                    self._verify_ssl_default = False
                _LOGGER.debug("Request to %s failed: %s", url, err)
                last_err = err
                continue  # try next port

        # All attempts failed → raise
        if last_err:
            if isinstance(last_err, asyncio.TimeoutError):
                raise WiiMTimeoutError(
                    "Timeout communicating with WiiM device after trying %s: %s"
                    % (", ".join(tried), last_err)
                )
            raise WiiMConnectionError(
                "Error communicating with WiiM device after trying %s: %s"
                % (", ".join(tried), last_err)
            )

    # Basic Player Controls
    async def get_status(self) -> dict[str, Any]:
        """Get the current status of the WiiM device with normalised keys."""
        raw = await self._request(API_ENDPOINT_STATUS)

        # Normalise keys so the rest of the integration can rely on a stable schema
        status: dict[str, Any] = {}

        # Volume and mute
        status["volume"] = raw.get("volume") or raw.get("vol") or raw.get("vol_level")
        status["mute"] = bool(raw.get("mute")) if "mute" in raw else None

        # Power state (1 = on, 0 = standby) – some firmwares expose "power"
        if "power" in raw:
            status["power"] = bool(raw["power"])
        elif "standby" in raw:
            status["power"] = not bool(raw["standby"])

        # Playback state – Wiim returns "play_status", LinkPlay returns "playstatus" or encoded in apollo_state
        play_status = raw.get("play_status") or raw.get("playstatus")
        ap_state = raw.get("apollo_state")
        if play_status:
            status["play_status"] = play_status
        elif ap_state:
            # Map common apollo_state strings
            if "playing" in ap_state:
                status["play_status"] = "play"
            elif "pause" in ap_state or "paused" in ap_state:
                status["play_status"] = "pause"
            else:
                status["play_status"] = "stop"

        # Play / repeat / shuffle mode if directly available
        status["play_mode"] = raw.get("play_mode") or raw.get("repeat_mode")

        # Position and duration
        status["position"] = raw.get("curpos") or raw.get("position")
        status["duration"] = raw.get("durpos") or raw.get("duration")

        # Update timestamp for position
        if status.get("position") is not None:
            status["position_updated_at"] = asyncio.get_running_loop().time()

        # Source / stream type
        status["source"] = raw.get("stream_type") or raw.get("source")

        # Preset & EQ
        status["preset"] = raw.get("preset_key") or raw.get("preset")
        status["eq_preset"] = raw.get("eq_mode") or raw.get("eq_preset")
        status["eq_custom"] = raw.get("eq_custom")

        # Wi-Fi diagnostics (used by sensor platform)
        status["wifi_rssi"] = raw.get("wifi_signal") or raw.get("rssi")
        status["wifi_channel"] = raw.get("wifi_channel") or raw.get("wifichannel")

        # Device info
        status["device_model"] = raw.get("model_name") or raw.get("device_model")
        status["device_name"] = raw.get("friendly_name") or raw.get("device_name")
        status["device_id"] = raw.get("uuid") or raw.get("device_id")
        status["firmware"] = raw.get("version") or raw.get("firmware")

        # Now-playing details – some firmwares expose a single caret-separated string
        if "nowplaying" in raw and raw["nowplaying"]:
            parts = raw["nowplaying"].split("^")
            # Expected order: title^artist^album
            if len(parts) >= 1:
                status["title"] = parts[0]
            if len(parts) >= 2:
                status["artist"] = parts[1]
            if len(parts) >= 3:
                status["album"] = parts[2]
        else:
            # Individual keys some firmwares provide
            status["title"] = raw.get("title")
            status["artist"] = raw.get("artist")
            status["album"] = raw.get("album")

        # Multi-room group info (leave untouched for coordinator)
        if "multiroom" in raw:
            status["multiroom"] = raw["multiroom"]

        return status

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
        _LOGGER.debug("[WiiM] Creating multiroom group on %s", self._host)
        await self._request(API_ENDPOINT_GROUP_CREATE)
        self._group_master = self._host
        self._group_slaves = []

    async def delete_group(self) -> None:
        """Delete the current multiroom group."""
        if not self._group_master:
            raise WiiMError("Not part of a multiroom group")
        _LOGGER.debug("[WiiM] Deleting multiroom group on %s", self._host)
        await self._request(API_ENDPOINT_GROUP_DELETE)
        self._group_master = None
        self._group_slaves = []

    async def join_group(self, master_ip: str) -> None:
        """Join a multiroom group as a slave."""
        # Check actual device state before raising error
        multiroom = await self.get_multiroom_info()
        if multiroom.get("type") == "1" or self._group_master:
            # Try to leave group first
            try:
                await self.leave_group()
            except Exception:
                pass  # Ignore errors, try to join anyway
        _LOGGER.debug("[WiiM] %s joining group with master %s", self._host, master_ip)
        endpoint = API_ENDPOINT_GROUP_JOIN.format(ip=master_ip)
        await self._request(endpoint)
        self._group_master = master_ip
        self._group_slaves = []

    async def leave_group(self) -> None:
        """Leave the current multiroom group."""
        _LOGGER.debug("[WiiM] %s leaving group", self._host)
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

    # ---------------------------------------------------------------------
    # Extended helpers -----------------------------------------------------
    # ---------------------------------------------------------------------

    async def get_player_status(self) -> dict[str, Any]:
        """Return a **normalised** status dict.

        Order of preference: getPlayerStatusEx → getStatusEx.
        Raw payload is converted to a stable schema so the rest of the
        integration can rely on consistent keys.
        """
        from .const import API_ENDPOINT_PLAYER_STATUS

        try:
            raw: dict[str, Any] = await self._request(API_ENDPOINT_PLAYER_STATUS)
        except WiiMError:
            raw = await self._request(API_ENDPOINT_STATUS)

        return self._parse_player_status(raw)

    # Mapping table {raw_key: canonical_key}
    _STATUS_MAP: dict[str, str] = {
        "status": "play_status",
        "vol": "volume",
        "mute": "mute",
        "eq": "eq_preset",
        "loop": "loop_mode",
        "curpos": "position_ms",
        "totlen": "duration_ms",
        "Title": "title_hex",
        "Artist": "artist_hex",
        "Album": "album_hex",
        # Wi-Fi (only present in fallback)
        "WifiChannel": "wifi_channel",
        "RSSI": "wifi_rssi",
    }

    def _parse_player_status(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Translate raw player status JSON into canonical schema."""

        _LOGGER.debug("Raw player status: %s", raw)

        data: dict[str, Any] = {}

        for k, v in raw.items():
            key = self._STATUS_MAP.get(k, k)
            data[key] = v

        # Hex-decode metadata
        data["title"] = _hex_to_str(raw.get("Title")) or raw.get("title")
        data["artist"] = _hex_to_str(raw.get("Artist")) or raw.get("artist")
        data["album"] = _hex_to_str(raw.get("Album")) or raw.get("album")

        # Power – getPlayerStatusEx does not include a dedicated key; assume ON
        data.setdefault("power", True)

        # Wi-Fi diagnostics fallback (some firmwares use lowercase)
        if "wifi_channel" not in data and raw.get("wifi_channel"):
            data["wifi_channel"] = raw["wifi_channel"]
        if "wifi_rssi" not in data and raw.get("wifi_rssi"):
            data["wifi_rssi"] = raw["wifi_rssi"]

        # Volume normalisation 0-1 float (HA convention)
        if (vol := raw.get("vol")) is not None:
            try:
                vol_int = int(vol)
                data["volume_level"] = vol_int / 100
                # Also keep 0-100 style for existing entity code
                data["volume"] = vol_int
            except ValueError:
                pass

        # Position / duration in seconds
        if raw.get("curpos"):
            data["position"] = int(raw["curpos"]) // 1_000
            data["position_updated_at"] = asyncio.get_running_loop().time()
        if raw.get("totlen"):
            data["duration"] = int(raw["totlen"]) // 1_000

        # Convert numeric strings to int where helpful
        if "mute" in data:
            try:
                data["mute"] = bool(int(data["mute"]))
            except (TypeError, ValueError):
                data["mute"] = bool(data["mute"])

        # Derive play_mode from LinkPlay "loop" code if not supplied directly
        if "play_mode" not in data and "loop_mode" in data:
            try:
                loop_val = int(data["loop_mode"])
            except (TypeError, ValueError):
                loop_val = 4  # default = normal

            if loop_val == 0:
                data["play_mode"] = PLAY_MODE_REPEAT_ALL  # repeat all
            elif loop_val == 1:
                data["play_mode"] = PLAY_MODE_REPEAT_ONE
            elif loop_val == 2:
                data["play_mode"] = PLAY_MODE_SHUFFLE_REPEAT_ALL
            elif loop_val == 3:
                data["play_mode"] = PLAY_MODE_SHUFFLE
            else:
                data["play_mode"] = PLAY_MODE_NORMAL

        # Artwork: various firmwares use different keys
        cover = (
            raw.get("cover")
            or raw.get("cover_url")
            or raw.get("albumart")
            or raw.get("pic_url")
        )
        if cover:
            data["entity_picture"] = cover

        _LOGGER.debug("Parsed status: %s", data)
        return data

    async def get_multiroom_info(self) -> dict[str, Any]:
        """Get multiroom status."""
        try:
            response = await self._request(API_ENDPOINT_GROUP_SLAVES)
            _LOGGER.debug("Multiroom response: %s", response)

            # Parse the response
            result = {}

            # Check if we're a master
            if "slave_list" in response:
                result["slaves"] = len(response["slave_list"])
                result["slave_list"] = response["slave_list"]
            else:
                result["slaves"] = 0
                result["slave_list"] = []

            # Check if we're a slave
            if "master_uuid" in response:
                result["type"] = "1"  # We're a slave
                result["master_uuid"] = response["master_uuid"]
            else:
                result["type"] = "0"  # We're not a slave

            return result
        except Exception as e:
            _LOGGER.error("Failed to get multiroom info: %s", e)
            return {"slaves": 0, "slave_list": [], "type": "0"}

    async def kick_slave(self, slave_ip: str) -> None:
        """Remove a slave device from the group."""
        if not self.is_master:
            raise WiiMError("Not a group master")
        _LOGGER.debug("[WiiM] Kicking slave %s from group", slave_ip)
        await self._request(f"{API_ENDPOINT_GROUP_KICK}{slave_ip}")

    async def mute_slave(self, slave_ip: str, mute: bool) -> None:
        """Mute/unmute a slave device."""
        if not self.is_master:
            raise WiiMError("Not a group master")
        _LOGGER.debug("[WiiM] Setting mute=%s for slave %s", mute, slave_ip)
        await self._request(f"{API_ENDPOINT_GROUP_SLAVE_MUTE}{slave_ip}:{1 if mute else 0}")

    # ---------------------------------------------------------------------
    # Diagnostic / maintenance helpers
    # ---------------------------------------------------------------------

    async def reboot(self) -> None:
        """Reboot the device via HTTP API."""
        await self._request("/httpapi.asp?command=reboot")

    async def sync_time(self, ts: int | None = None) -> None:
        """Synchronise device RTC with Unix timestamp (defaults to *now*)."""
        if ts is None:
            ts = int(asyncio.get_running_loop().time())
        await self._request(f"/httpapi.asp?command=timeSync:{ts}")

    async def get_meta_info(self) -> dict[str, Any]:
        """Get current track metadata including album art."""
        try:
            response = await self._request("/httpapi.asp?command=getMetaInfo")
            return response.get("metaData", {})
        except Exception as e:
            _LOGGER.error("Failed to get meta info: %s", e)
            return {}


# ---------------------------------------------------------------------------
# --- low-level helpers (adapted from python-linkplay, MIT) ------------------
# ---------------------------------------------------------------------------

# The WiiM integration interacts with the speaker exclusively through the
# HTTP API exposed on ``https://<ip>/httpapi.asp?command=...``.  The three
# convenience helpers below replicate the tiny helper layer that the
# *python-linkplay* library offers so that our high-level code remains compact
# and easy to unit-test.  They purposefully depend **only** on ``aiohttp`` and
# the Python standard library.


async def _ensure_session(base_ssl_ctx: ssl.SSLContext | None) -> ClientSession:  # type: ignore
    """Create a throw-away :class:`aiohttp.ClientSession` with our SSL context.

    Helper for users that do not provide a session; we open one and make sure
    the connector uses the given SSL context (or default verification disabled
    if *None*).  The caller is responsible for closing it.
    """

    if base_ssl_ctx is None:
        connector = aiohttp.TCPConnector(ssl=False)
    else:
        connector = aiohttp.TCPConnector(ssl=base_ssl_ctx)

    return aiohttp.ClientSession(connector=connector)


async def session_call_api(endpoint: str, session: ClientSession, command: str) -> str:
    """Perform a **single GET** to the LinkPlay HTTP API and return raw text.

    Parameters
    ----------
    endpoint
        Base URL including scheme/host/port, *without* trailing slash, e.g.
        ``https://192.168.1.10:443``.
    session
        An *aiohttp* :class:`ClientSession` instance.
    command
        The command part of the API call, for example ``getStatusEx``.
    """

    url = f"{endpoint}/httpapi.asp?command={command}"

    try:
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            response = await session.get(url, headers=HEADERS)
    except (asyncio.TimeoutError, ClientError, asyncio.CancelledError) as err:
        raise WiiMRequestError(f"{err} error requesting data from '{url}'") from err

    if response.status != HTTPStatus.OK:
        raise WiiMRequestError(
            f"Unexpected HTTP status {response.status} received from '{url}'"
        )

    return await response.text()


async def session_call_api_json(
    endpoint: str, session: ClientSession, command: str
) -> dict[str, str]:
    """Call the API and JSON-decode the response."""

    raw = await session_call_api(endpoint, session, command)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WiiMInvalidDataError(
            f"Unexpected JSON ({raw[:80]}…) received from '{endpoint}'"
        ) from exc


async def session_call_api_ok(endpoint: str, session: ClientSession, command: str) -> None:
    """Call the API and assert the speaker answers exactly 'OK'."""

    result = await session_call_api(endpoint, session, command)
    if result.strip() != "OK":
        raise WiiMRequestError(
            f"Didn't receive expected 'OK' from {endpoint} (got {result!r})"
        )


def _hex_to_str(val: str | None) -> str | None:
    """Decode hex‐encoded UTF-8 strings used by LinkPlay for metadata."""
    if not val:
        return None
    try:
        return bytes.fromhex(val).decode("utf-8", errors="replace")
    except ValueError:
        return val  # already plain
