---
name: snowmix-mcp
description: Control Snowmix video mixer via FastMCP (Python). Use for video mixing, feed switching, text/image overlays, and audio routing.
version: 2.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [video, snowmix, mcp, mixing, broadcast, python]
    related_skills: [test-driven-development]
---

# Snowmix MCP Skill (Python/FastMCP)

## Overview

This skill governs the Python `fastmcp` server at `/home/rjodouin/Documents/git/snowmix-fastmcp` that wraps Snowmix 0.5.2.2's TCP control socket for video/audio mixing. It is the canonical reference for the project's TDD conventions, Snowmix-specific protocol quirks discovered through C++ source-code analysis, and the node-snowmix test port.

## When to Use

- User wants to switch video feeds, add text/image overlays, or route audio.
- User mentions "snowmix", "video mixer", "switch feed", "overlay", or "broadcast".
- Building a video pipeline that requires programmatic mixing.
- Editing `main.py`, `snowmix_client.py`, or `test_snowmix.py` in the project.
- Debugging silent-success or banner-consumption behavior.
- Porting tests from `https://github.com/matthew1000/node-snowmix/tree/master/test`.

## Project Layout

- `snowmix_client.py` — async TCP client; owns connection banner handling, `send_command`, and helper methods.
- `main.py` — `FastMCP("snowmix")` instance exposing `@mcp.tool()` wrappers.
- `test_snowmix.py` — pytest + pytest-asyncio suite (25 tests, all green); owns the module-scoped Snowmix subprocess fixture.
- `snowmix_commands_reference.md` — local command cheat sheet (18 categories with verified syntax).
- `ini/test.ini` — test ini with full subsystem allocations (audio maxplaces, image maxplaces, etc.).
- `pyproject.toml` — pytest asyncio config + ruff settings.
- `conftest.py` — pytest-asyncio auto mode.

## Prerequisites

1. Snowmix 0.5.2.2 installed:
   - Binary: `/usr/local/bin/snowmix`
   - Source tree: `/home/rjodouin/Snowmix-0.5.2.2/src/`
   - Default control port: `127.0.0.1:9999`
2. The MCP server lives at `~/Documents/git/snowmix-fastmcp/`.
3. Activate the virtual environment: `source ~/Documents/git/snowmix-fastmcp/venv/bin/activate`

## Available MCP Tools

| Tool Name | Description |
|-----------|-------------|
| `snowmix_get_system_geometry` | Get the current system geometry configuration (resolution, frame rate, etc.) |
| `snowmix_get_version` | Get the Snowmix version string from the connection banner. |
| **Video Feeds** | |
| `snowmix_add_video_feed` | Add a new video feed with ID, file path, width, and height. |
| `snowmix_get_feed_info` | Get information about a specific video feed by its ID. |
| `snowmix_list_feeds` | List all video feeds with their names and IDs. |
| `snowmix_update_feed_name` | Rename an existing video feed. |
| `snowmix_create_feed` | Create a video feed by name (0 = auto-assign ID). |
| **Virtual Feeds** | |
| `snowmix_create_vfeed` | Create a new virtual feed (ID range 0–31). |
| `snowmix_list_vfeeds` | List all virtual feeds. |
| `snowmix_vfeed_source` | Route a real video feed into a virtual feed. |
| `snowmix_delete_vfeed` | Remove a virtual feed. |
| **Audio Feeds** | |
| `snowmix_create_audio_feed` | Create a new audio feed. |
| `snowmix_list_audio_feeds` | List all audio feeds. |
| `snowmix_get_audio_feed_info` | Get detailed info for an audio feed (rate, channels, format). |
| `snowmix_delete_audio_feed` | Delete an audio feed. |
| **Audio Mixers** | |
| `snowmix_create_audio_mixer` | Create a new audio mixer. |
| `snowmix_list_audio_mixers` | List all audio mixers. |
| `snowmix_audio_mixer_add_feed` | Route an audio feed into a mixer (rates must match). |
| `snowmix_get_audio_mixer_info` | Get detailed info for an audio mixer. |
| `snowmix_delete_audio_mixer` | Delete an audio mixer. |
| **Audio Sinks** | |
| `snowmix_create_audio_sink` | Create a new audio sink. |
| `snowmix_list_audio_sinks` | List all audio sinks. |
| `snowmix_audio_sink_add_mixer` | Route an audio mixer into a sink (rates must match). |
| `snowmix_get_audio_sink_info` | Get detailed info for an audio sink. |
| `snowmix_delete_audio_sink` | Delete an audio sink. |
| **Text Overlays** | |
| `snowmix_create_text` | Create a new text overlay. |
| `snowmix_text_show` | Make a text overlay visible. |
| `snowmix_text_hide` | Hide a text overlay. |
| `snowmix_list_texts` | List all text overlays. |
| **Image Overlays** | |
| `snowmix_image_load` | Load an image file into Snowmix. |
| `snowmix_list_images` | List all loaded images. |
| `snowmix_get_image_info` | Get info for a loaded image. |
| `snowmix_delete_image` | Remove a loaded image. |
| **Commands (Macros)** | |
| `snowmix_command_list` | List all custom commands (macros). |
| `snowmix_command_delete` | Delete a custom command by name. |

## Critical Snowmix Protocol Quirks

These discoveries came from C++ source analysis (Snowmix 0.5.2.2) and are NOT in the official documentation:

- **Banner on connect**: Snowmix sends `Snowmix version X.Y.Z.` immediately on TCP connect. The client must consume that line before issuing commands or it will be parsed as the first command response.
- **Silent success**: Many commands return nothing on success. `send_command` treats a 1.0s read timeout with no `MSG:`/`STAT:` lines as `"OK"`.
- **`feed name` for renames, not `feed add`**: Re-issuing `feed add <id> <name>` on an existing feed returns `MSG: Feed ID <id> already used`. Use `feed name <id> <newname>` instead. The client's `update_feed_name()` must send `feed name`, not `feed add`.
- **`vfeed add` for listing**: `vfeed add` with no arguments lists all virtual feeds (output: `STAT: vfeed  <id> : <name>`). Bare `vfeed` is NOT a recognized command. The client's `list_vfeeds()` must send `vfeed add`, not `vfeed`.
- **`command list` returns `MSG:` lines**: Unlike most list commands which return `STAT:` lines, `command list` returns `MSG:` lines. The client's `command_list_all()` must strip both `STAT:` and `MSG:` prefixes — filtering on `raw.startswith('MSG:')` drops all legitimate results.
- **`audio sink source` uses `mixer` subcommand**: The correct syntax is `audio sink source mixer <sink_id> <mixer_id>`, NOT `audio sink source <sink_id> <mixer_id>`.
- **Multi-step feed creation**: `feed file <id> "<path>"` fails with spaces in the path. Use:
  1. `feed add <id> <name>`
  2. `feed geometry <id> <width> <height>`
- **Quoting**: Quote any name/path containing spaces. Never batch multiple commands into one TCP frame.

### Audio Rate Matching (Critical)

Snowmix enforces sample rate matching between audio sources and their destinations. The `MixerSource()` / `SinkSource()` internals check that the mixer's/sink's sample rate matches the source feed's/mixer's rate. **When the rates don't match, Snowmix returns `MSG: Invalid number of parameters` — this is deceptive.** The actual error is a rate mismatch, not a syntax error.

**Fix:** Before calling `audio mixer source feed <mixer> <feed>` or `audio sink source mixer <sink> <mixer>`, ensure all components share the same rate and channel count:
```python
# Match mixer to feed rate (audio feed 2 defaults to 48000/2)
await client.send_command("audio mixer rate 1 48000")
await client.send_command("audio mixer channels 1 2")
await client.audio_mixer_add_feed(1, 2)

# Match sink to mixer rate
await client.send_command("audio sink rate 1 48000")
await client.send_command("audio sink channels 1 2")
await client.audio_sink_add_mixer(1, 1)
```

**How to diagnose:** If `audio mixer source feed X Y` returns "Invalid number of parameters" but you've confirmed the syntax is correct and both entities exist, check their rates with `audio feed info Y` and `audio mixer info X`. A mismatch in the `rate` or `channels` fields is the root cause.

## Common Snowmix Reserved Commands

### Video Feeds
- `feed add <id> <name>` - Create a video feed
- `feed name <id> <name>` - Rename an existing feed
- `feed geometry <id> <width> <height>` - Set feed resolution
- `feed info <id>` - Get feed info (returns `STAT:` block)
- `feed drop <id>` - Remove a feed

### Virtual Feeds
- `vfeed add <id> <name>` - Create a virtual feed
- `vfeed add` - List all virtual feeds (no args = list mode)
- `vfeed source feed <vfeed_id> <feed_id>` - Route a real feed into a vfeed
- `vfeed drop <id>` - Remove a vfeed
- `vfeed geometry <id> <width> <height>` - Set vfeed resolution

### Audio
- `audio feed add <id>` - Create an audio feed
- `audio feed channels <id> <n>` - Set channel count
- `audio feed rate <id> <rate>` - Set sample rate (e.g. 48000)
- `audio mixer add <id>` - Create an audio mixer
- `audio mixer rate <id> <rate>` - Set mixer sample rate (match to feed first!)
- `audio mixer source feed <mixer_id> <feed_id>` - Route audio feed to mixer
- `audio mixer info <id>` - Get mixer info
- `audio sink add <id>` - Create an audio sink
- `audio sink source mixer <sink_id> <mixer_id>` - Route mixer to sink
- `audio sink rate <id> <rate>` - Set sink sample rate (match to mixer first!)

### Commands (Macros)
- `command create <name>` - Enter command creation mode
- `command end` - Exit creation mode (finalizes the command)
- `command list` - List all commands (returns `MSG:` lines)
- `command delete <name>` - Delete a command
- `command push <name> <line>` - Push a line onto a command

## Usage Examples

### Check System Geometry
**User:** "What is the current Snowmix resolution?"
**Action:** Call `snowmix_get_system_geometry` tool.

### Add a Video Feed
**User:** "Add a video feed from <path> with ID 100 at 1024x576"
**Action:** Call `snowmix_add_video_feed` with `feed_id=100`, `file_path="<path>"`, `width=1024`, `height=576`.

### Verify Feed Creation
**User:** "Check if feed 100 was created successfully."
**Action:** Call `snowmix_get_feed_info` with `feed_id=100`.

## Test Fixture Pattern

```python
import asyncio, os
from pathlib import Path
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parent
INI_PATH = REPO_ROOT / "ini" / "test.ini"
SNOWMIX_BIN = os.environ.get("SNOWMIX_BIN", "/usr/local/bin/snowmix")

@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    proc = await asyncio.create_subprocess_exec(
        SNOWMIX_BIN, str(INI_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.sleep(2)  # Allow time to bind
    yield proc
    proc.terminate()
    await proc.wait()

@pytest_asyncio.fixture
async def client(snowmix_process) -> SnowmixClient:
    c = SnowmixClient()
    await c.connect()
    yield c
    await c.close()
```

## ini Configuration

The test fixture uses `ini/test.ini` (not `minimal.ini`). `minimal.ini` omits `maxplaces` for audio/text/image subsystems, causing creation commands to fail silently.

The fixture resolves `SNOWMIX_BIN` from the environment (default: `/usr/local/bin/snowmix`). The ini path is absolute via `Path(__file__).resolve().parent / "ini" / "test.ini"`.

## Development & Extension (TDD)

When adding new tools, follow the **test-driven-development** skill strictly:

1. **RED**: Write a failing test in `test_snowmix.py` for the new behavior.
2. **GREEN**: Implement the minimal code in `snowmix_client.py` or `main.py`.
3. **REFACTOR**: Clean up while keeping tests green.

**Never write production code without a failing test first.**

Run the test suite:
```bash
source venv/bin/activate
pytest test_snowmix.py -v
```

## Porting node-snowmix Tests

Map node-snowmix suites to Python equivalents:
- `feeds.js` → create/rename/delete feeds, check `all()`, `byId()`, `allIds()` — **ported (5 tests pass)**
- `vfeeds.js` → add/rename/delete vfeeds, source mapping — **ported (4 tests pass)**
- `system-geometry.js` → assert `system geometry` response — **ported (1 test passes)**
- `commands.js` → create/list/delete custom commands — **ported (1 test passes)**
- `audioFeeds.js` → create/set rate/channels/format — **ported (5 tests pass)**
- `audioMixers.js` → create/add feed/list/info — **ported (4 tests pass)**
- `audioSinks.js` → create/add mixer/list — **ported (3 tests pass)**
- `images.js` → requires PNG fixtures under `tests/images/` — **not yet ported**

See `references/node-snowmix-tests.md` for detailed port status.

## Troubleshooting

- **Connection Refused**: Snowmix is not running. Start it with `export SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2/src && /usr/local/bin/snowmix /home/rjodouin/Documents/git/snowmix-fastmcp/ini/test.ini`.
- **All Tests Error**: Likely Snowmix not running. Run `pgrep snowmix` — if nothing, start it. The test fixture spawns its own process; check `test.ini` exists.
- **Command Silent/Timeout**: Snowmix commands are silent on success. The Python client handles this by returning "OK" on timeout.
- **MCP Tool Not Found**: Ensure the MCP server is registered in Hermes config and the virtual environment is activated.

## Testing Pitfalls

1. **Silent Success**: Snowmix returns nothing on success. Do not assert on stdout. Verify side effects via `info` queries.
2. **State Collision**: Snowmix retains state across test runs. Use high-range IDs (e.g., 2000+) in new tests to prevent "ID already used" errors.
3. **Use test.ini, Not minimal.ini**: `minimal.ini` omits `maxplaces` for audio/text/image subsystems. Always use `ini/test.ini`.
4. **pytest-asyncio Config**: The project requires `asyncio_mode = "auto"` set via `pyproject.toml` (`[tool.pytest.ini_options]`). A `conftest.py` also sets this.
5. **Rate Matching Required**: Adding an audio feed to a mixer, or a mixer to a sink, requires matching sample rates. See Audio Rate Matching section above.
6. **Feed Switching Uses `stack`**: The `feed switch <id>` reserved command may not work. Use `stack 0 <feed_id>` instead (from video-switcher.ini examples).

## References

- `references/node-snowmix-tests.md` — Extracted test specs and mapping notes from the node-snowmix test suite.
- `/home/rjodouin/Documents/git/snowmix-fastmcp/snowmix_commands_reference.md` — Local command reference covering all 18 Snowmix command categories with verified syntax.
- [Snowmix Reserved Commands](https://snowmix.sourceforge.io/Documentation/reserved.html) — Official documentation (note: syntax for some commands differs from source-code reality).
