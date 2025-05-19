# WiiM Audio (LinkPlay) – Home Assistant Integration

A modern, dependency-free Home Assistant custom component for controlling WiiM and most LinkPlay-based speakers as `media_player` entities.

**WiiM-first, LinkPlay-friendly:** This integration is designed for full support of WiiM's own hardware and firmware, while remaining compatible with most LinkPlay-based speakers and streamers.

---

## Features

| Category    | Details                                                                             |
| ----------- | ----------------------------------------------------------------------------------- |
| Transport   | Play / Pause / Stop / Next / Previous, seek, preset keys                            |
| Volume      | Absolute 0-100 %, configurable step, mute toggle                                    |
| Metadata    | Title, artist, album, progress bar, play / shuffle / repeat modes                   |
| Discovery   | SSDP/UPnP MediaRenderer, Zeroconf `_linkplay._tcp`, group auto-import               |
| Multi-room  | Create group, join/leave any LinkPlay master, expose `group_members` & `group_role` |
| Diagnostics | Reboot, sync clock, Wi-Fi RSSI & channel sensors                                    |
| No deps     | Uses only HA-bundled `aiohttp` — zero external Python packages                      |
| Config      | Poll interval, volume step, options flow                                            |
| Services    | Play preset, toggle power, reboot, sync time                                        |

---

## Installation

### HACS (Recommended)

1. Add this repository as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) in HACS.
2. Search for **WiiM Audio (LinkPlay)** and install.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/wiim` folder to your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant.

---

## Configuration

- Open _Settings → Devices & Services_.
- The integration will auto-discover speakers via UPnP/SSDP and multi-room follow-ups.
- If nothing appears, click **"Add Integration"** and search for **WiiM Audio (LinkPlay)**; enter the speaker's IP if needed.
- Options (poll interval, volume step) are available via the integration's configuration menu.

---

## Entity Services

| Service                     | Description                            |
| --------------------------- | -------------------------------------- |
| `media_player.play_preset`  | Presses preset key 1-6 (`preset: 1-6`) |
| `media_player.toggle_power` | Standby ↔ On                           |
| `wiim.reboot_device`        | Reboots the speaker                    |
| `wiim.sync_time`            | Sync speaker clock to HA time          |

---

## Known Limitations

- Album-art URL is returned only if the firmware supplies `cover_url`; some sources (AirPlay, Bluetooth) may not provide artwork.
- Some advanced features (e.g., TTS snapshot/restore, LED brightness) are not yet implemented.

---

## Contributing

Pull requests are welcome! Please ensure your code is formatted with `black`, linted with `ruff`, and passes all tests (`pytest -q`) before submitting.

---

## References & Acknowledgements

- **WiiM HTTP API**: [Official PDF](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf)
- **python-linkplay**: [Velleman fork](https://github.com/Velleman/python-linkplay) — this project was a key reference and inspiration for the HTTP API client.
- **Home Assistant LinkPlay integration**: [HA Core](https://github.com/home-assistant/core/tree/dev/homeassistant/components/linkplay)
- **Home Assistant Developer Docs**: [developers.home-assistant.io](https://developers.home-assistant.io/)

---

© 2025 WiiM Custom Integration Project – MIT License
