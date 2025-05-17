# WiiM Home Assistant Integration – Master Guide (v0.2 consolidated)

*Integrates and harmonizes “WiiM Custom Home Assistant Integration — End‑to‑End Guide + Scaffold for Cursor AI” and “WiiM – Home Assistant Custom Integration (Design v0.2)” to serve as the single source of truth for the project team and any AI coding agents involved.*

---

## 1 · Project Charter & Vision

| Item                  | Detail                                                                                                                                                            |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Objective**         | Ship a **dependency‑free HACS custom component** that exposes every WiiM / LinkPlay speaker on the local network as a `media_player` entity in Home Assistant.    |
| **Target HA Version** |  ≥ 2024.12.0 (Python 3.11 baseline)                                                                                                                               |
| **Success Metrics**   | • Entity auto‑discovers and appears in UI• Command latency < 500 ms• Unit‑test coverage > 85 %• ≤ 600 source LOC (excluding tests/docs)• MVP features R1–R6 green |
| **Distribution**      | HACS custom repo `hawiim`, semantic version tags & CHANGELOG                                                                                                      |

### 1.1 MVP Feature Set (v0.1)

| ID     | Requirement                                                         |
| ------ | ------------------------------------------------------------------- |
| **R1** | Core transport – play, pause, stop, next/prev, seek                 |
| **R2** | Volume – set absolute %, configurable step (default 5 %)            |
| **R3** | Preset keys – fire `MCUKeyShortClick:{n}` via `play_preset` service |
| **R4** | Grouping – join / un‑join any LinkPlay master (multi‑room)          |
| **R5** | Polling – user‑set interval (≥ 1 s; default 5 s)                    |
| **R6** | Discovery – Zeroconf `_linkplay._tcp` + manual entry                |

*Stretch Goals (v0.2+):* snapshot/restore, media browser, fixed‑volume detection, UPnP enrichment, EQ presets, Bluetooth source select, options‑flow extras, eventual core PR.

---

## 2 · High‑Level Architecture & Directory Layout

```text
custom_components/wiim/
├── __init__.py          # setup_entry / unload / reload
├── manifest.json        # no external "requirements"
├── const.py             # literals & defaults (see §3)
├── api.py               # ≤200 LOC async HTTP client (bundles cert)
├── coordinator.py       # DataUpdateCoordinator wrapper
├── media_player.py      # MediaPlayerEntity subclass & media browser
├── snapshot.py          # helper for snapshot/restore (stretch)
├── config_flow.py       # Zeroconf + manual + options UI
├── strings.json         # UI strings for ConfigFlow/OptionsFlow
├── services.yaml        # schemas: play_preset, toggle_power
└── tests/               # pytest‑asyncio unit tests & fixtures
```

### 2.1 Data Flow

1. **Discovery** – `config_flow` detects `_linkplay._tcp` mDNS records whose TXT field `model` starts with `WiiM`.
2. **Client** – `api.WiiMClient` issues HTTPS requests (self‑signed cert pinned in‐file) and falls back to Telnet where required.
3. **Coordinator** – polls `/httpapi.asp?command=getStatusEx` every `poll_interval` seconds.
4. **Entity** – reflects state, exposes HA media‑player services; async methods call client, then refresh coordinator.

---

## 3 · Constants & Supported Features (const.py excerpt)

```python
DOMAIN = "wiim"

# Config keys
CONF_HOST          = "host"
CONF_POLL_INTERVAL = "poll_interval"
CONF_VOLUME_STEP   = "volume_step"

# Defaults
DEFAULT_PORT          = 443   # HTTPS
DEFAULT_TIMEOUT       = 10    # seconds
DEFAULT_POLL_INTERVAL = 5     # seconds
DEFAULT_VOLUME_STEP   = 0.05  # 5 %

# Services / Attributes
SERVICE_PLAY_PRESET  = "play_preset"
SERVICE_TOGGLE_POWER = "toggle_power"
ATTR_PRESET          = "preset"
ATTR_GROUP_MEMBERS   = "group_members"
ATTR_FIRMWARE        = "firmware"
ATTR_FIXED_VOLUME    = "fixed_volume"
```

*Supported HA features: PLAY, PAUSE, VOLUME\_SET, JOIN, UNJOIN.*

---

## 4 · HTTP Client (`api.py`)

* **Certificate pinning** – embeds the WiiM CA cert to satisfy HTTPS on port 443.
* **Async‑only** – all I/O awaited; sync Telnet fallback wrapped in `run_in_executor`.
* **Concurrency** – single in‑flight request protected by `asyncio.Lock`.
* **Key methods**:

  * `get_status()` – returns parsed JSON dict (`play_status`, `play_mode`, `volume`, …).
  * `play() / pause() / stop()` – `setPlayerCmd:play/pause/stop`.
  * `set_volume(pct)` – `setPlayerCmd:vol:{pct}`.
  * `select_preset(n)` – `MCUKeyShortClick:{n}`.
  * `join(master_ip)` / `unjoin()` – `setMultiroom:Slave|Exit`.

---

## 5 · Coordinator (`coordinator.py`)

* Sub‑class of `DataUpdateCoordinator`.
* Owns `client` & updates `data` every `poll_interval` seconds.
* Marks entity unavailable after ≥ 3 consecutive failures or timeout.

---

## 6 · MediaPlayer Entity (`media_player.py`)

* Maps status JSON → `MediaPlayerState` & attributes.
* Exposes `async_media_play`, `async_media_pause`, `async_volume_set`, `async_join`, `async_unjoin`.
* Optional **Media Browser** panel (v0.2) listing presets & favourite web‑radio streams.
* Handles **snapshot/restore** for TTS (stretch).

---

## 7 · Config Flow & Options Flow

1. **Config Flow**

   * Zeroconf path – auto‑populates host/IP; validates by calling `client.get_status()`.
   * Manual path – user enters IP; same validation.
2. **Options Flow** (v0.2)

   * Adjust polling interval (1‑60 s).
   * Set default volume step (1‑10 %).

---

## 8 · Coding Rules & Quality Gates

| Topic         | Rule                                                             |
| ------------- | ---------------------------------------------------------------- |
| External Deps | **None.** Everything vendored / stdlib‑only.                     |
| File Size     | ≤ 150 LOC per file (excluding blanks/docstrings).                |
| Lint          | [ruff](https://github.com/astral‑sh/ruff) (full HA profile).     |
| Format        | black (line length 120).                                         |
| Tests         | pytest‑asyncio + `aresponses` for HTTP mocking; coverage > 85 %. |
| CI            | GitHub Actions: ruff → pytest → hassfest.                        |

---

## 9 · AI‑Driven Workflow (Cursor / Copilot)

> **Tip:** Keep this guide open in a pinned tab so the AI agent always has context.

### 9.1 Prompt Playbook

| Context File              | Example Prompt                                                                                                                        | Expected Output                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `api.py` (cursor at TODO) | “Implement `WiiMClient.get_status` following the HTTP API PDF. Use `aiohttp`, return parsed JSON.”                                    | Full async method with SSL ctx & error handling. |
| `media_player.py`         | “Write a `WiiMMediaPlayer` subclass of `MediaPlayerEntity` that maps play/pause/volume to `WiiMClient`. Use `DataUpdateCoordinator`.” | Complete entity with `supported_features`.       |
| …                         | …                                                                                                                                     | …                                                |

### 9.2 Task Sequence (import into ChatGPT Projects)

1. \*\*Bootstrap \*\*\`\` – literals & defaults (§3).
2. **Generate **\`\`** skeleton** – include cert & stubs.
3. **Implement client methods** – `_get`, `get_status`, transport cmds.
4. **Coordinator** – polling logic.
5. **MediaPlayer entity** – state mapping & services.
6. **Config Flow** – Zeroconf + manual.
7. **Unit tests** – `tests/` folder.
8. **CI workflow** – `.github/workflows/ci.yml`.
9. **Multi‑room helper** – join/unjoin services.
10. **Options Flow** – polling interval, volume step.
11. **Smoke Test** – manual HA container run.
12. **Release v0.1.0** – bump version & tag.

*(Full task definitions with acceptance criteria are copied verbatim from Section 9 of the original End‑to‑End Guide.)*

---

## 10 · Implementation Checklist

*

---

## 11 · Roadmap

| Version       | Features                                                           |
| ------------- | ------------------------------------------------------------------ |
| **0.1 (MVP)** | R1‑R6 + fixed‑volume detection + basic snapshot/restore            |
| **0.2**       | UPnP metadata enrichment, media position tracking, LED dimming cmd |
| **0.3**       | EQ presets, Bluetooth source select, TTS cutoff fix, core PR       |

---

## 12 · References & Resources

* **python‑linkplay** (Velleman fork): [https://github.com/velman/python-linkplay](https://github.com/velman/python-linkplay)
* **HA Core LinkPlay integration** (upstream patterns): [https://github.com/home-assistant/core/tree/dev/homeassistant/components/linkplay](https://github.com/home-assistant/core/tree/dev/homeassistant/components/linkplay)
* **WiiM HTTP API PDF** (command list): [https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf)
* **HA Developer Docs** – UpdateCoordinator, ConfigFlow patterns: [https://developers.home-assistant.io/](https://developers.home-assistant.io/)
* **LinkPlay Telnet command list** (legacy reference).

---

© 2025 WiiM Custom Integration Project – Consolidated Guide
