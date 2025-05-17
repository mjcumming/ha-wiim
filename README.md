# WiiM Home Assistant Integration

A lightweight, dependency-free custom component that exposes every WiiM (and other LinkPlay-based) speaker on your local network as a `media_player` entity in Home Assistant.

---

## Features

| Category    | Details                                                                                                   |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| Transport   | Play / Pause / Stop / Next / Previous, seek, preset keys                                                  |
| Volume      | Absolute 0-100 %, configurable step, mute toggle                                                          |
| Metadata    | Title, artist, album, progress bar, play / shuffle / repeat modes                                         |
| Discovery   | • SSDP/UPnP MediaRenderer<br>• Zeroconf `_linkplay._tcp`<br>• Follower auto-import from multi-room groups |
| Multi-room  | Create group, join / leave any LinkPlay master, expose `group_members` & `group_role`                     |
| Diagnostics | Reboot speaker, sync clock, Wi-Fi RSSI & channel sensors                                                  |
| No deps     | Uses HA-bundled `aiohttp` only – no extra Python packages                                                 |

---

## Installation

1. Copy the `custom_components/wiim` folder to your Home Assistant `config/custom_components` directory.
   _(Or add <https://github.com/your-repo/hawiim> as a HACS custom repository and install from the HACS UI.)_

2. Restart Home Assistant.

3. Open _Settings → Devices & Services_.
   • The integration will auto-discover speakers via UPnP/SSDP and multi-room follow-ups.
   • If nothing appears, click **"Add Integration"** and search for **WiiM**; enter the speaker's IP.

---

## Configuration options

| Option        | Default | Notes                                                         |
| ------------- | ------- | ------------------------------------------------------------- |
| Poll interval | 5 s     | 1–60 s; shorter → quicker UI refresh, longer → fewer requests |
| Volume step   | 0.05    | 0.01–0.5 (1–10 %)                                             |

Change these in _Settings → Devices & Services → WiiM → ︙ → Configure_.

---

## Entity services

| Service                     | Description                            |
| --------------------------- | -------------------------------------- |
| `media_player.play_preset`  | Presses preset key 1-6 (`preset: 1-6`) |
| `media_player.toggle_power` | Standby ↔ On                           |
| `wiim.reboot_device`        | Reboots the speaker                    |
| `wiim.sync_time`            | Sync speaker clock to HA time          |

---

## Known limitations / Roadmap

- Album-art URL is returned only if the firmware supplies `cover_url`; some sources (AirPlay, Bluetooth) don't. UPnP artwork lookup is planned for **v0.2**.
- TTS snapshot/restore and LED brightness control are stretch goals.
- Final aim is to upstream this into Home Assistant core.

---

## Contributing

PRs are welcome! See `wiim_guide.md` for the full architecture and task list. Please run `black`, `ruff`, and unit tests (`pytest -q`) before opening a pull request.

---

© 2025 WiiM Custom Integration Project – MIT License
