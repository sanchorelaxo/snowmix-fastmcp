# Plan: Port node-snowmix Tests to Python (TDD)

**Source**: https://github.com/matthew1000/node-snowmix/tree/master/test
**Target**: `/home/rjodouin/Documents/git/snowmix-fastmcp/`
**Method**: Strict TDD — RED (failing test) → GREEN (client method) → MCP tool + docs

## Pre-work: snowmix_client.py has duplicate methods

The client has `audio_mixers()`, `audio_sinks()`, `trim_agents()` duplicated ~12 times each (copy-paste noise). The `_get_agent_ids` helper is also missing.

**Fix**: Remove all duplicates, add `_get_agent_ids(command_prefix: str) -> list[int]` helper, then proceed.

---

## Phase 1: `system-geometry.js` + `version.js` (already partial)

**Tests**:
- `test_system_geometry` — exists, passes
- `test_version` — not yet written

**Node** asserts `geometry.width == 1024` and `geometry.height == 576`. Our version *might* differ from node's 0.5.1 expectation (we're 0.5.2.2).

**Steps**:
1. RED: Write `test_version(client)` — send `version` command, assert it includes "0.5"
2. GREEN: Add `get_version()` to `snowmix_client.py` — sends `version`, returns stripped response
3. Update `test_system_geometry` to parse width/height and assert exact values (1024x576)

---

## Phase 2: `feeds.js` — Video Feeds CRUD

**Node pattern**:
- `snowmix.feeds._createOrUpdate({name: 'name1'})` — auto-assigns ID
- `snowmix.feeds._createOrUpdate({name: 'name3-id4', id: 4})` — explicit ID
- `snowmix.feeds.all()` — list all
- `snowmix.feeds.allIds()` — just IDs
- `snowmix.feeds.byId(id).name` — fetch by ID

**Our approach** (simpler, no full ORM):
- `create_feed(name, id=None) -> int` — sends `feed add <id> "<name>"`, returns the ID
- `list_feeds() -> list[dict]` — parses `feed list`
- `get_feed(feed_id) -> dict` — parses `feed info <id>`
- `update_feed(feed_id, name) -> str` — sends `feed add <id> "<name>"` to update name

**Tests to write**:
- `test_create_feed_auto_id` — create feed without explicit ID, verify it gets one
- `test_create_feed_explicit_id` — create with ID=4, verify feed info shows it
- `test_list_feeds` — verify at least the Internal feed (ID 0) exists
- `test_get_feed_by_id` — fetch feed 0, verify name is "Internal"
- `test_update_feed_name` — change name, verify it stuck
- `test_create_multiple_feeds_sequential_ids` — create 2 feeds, verify IDs are sequential

**Snowmix command details**:
- `feed add <id> "<name>"` — creates/updates, silent on success
- `feed list` — returns `STAT:` lines with feed IDs/names
- `feed info <id>` — returns `STAT:` with feed details

---

## Phase 3: `vfeeds.js` — Virtual Feeds CRUD

**Node pattern**:
- `snowmix.vfeeds.deleteAll()`
- `snowmix.vfeeds.create({name: 'name1', sourceId: 1, source: 'feed'})`
- `snowmix.vfeeds.all()`, `vfeeds.byId(id)`, `vfeeds.allIds()`
- `snowmix.vfeeds.create({name: 'new-name-for-2', id: 2})` — update by specifying ID
- `snowmix.populate()` → re-read all state from Snowmix
- vfeed creation requires a real feed to exist first

**Our approach**:
- `delete_all_vfeeds() -> str`
- `create_vfeed(name, source_id, source='feed', id=None) -> int`
- `list_vfeeds() -> list[dict]`
- `get_vfeed(vfeed_id) -> dict`
- `populate_vfeeds() -> list[dict]` — re-read from Snowmix

**Tests**:
- `test_delete_all_vfeeds` — deleteAll, verify none
- `test_create_vfeed` — create a real feed, then a vfeed sourcing it
- `test_list_vfeeds` — verify count
- `test_get_vfeed_by_id` — verify name/source
- `test_update_vfeed_name` — update name by re-creating with same ID
- `test_populate_vfeeds` — verify details survive re-read

**Snowmix commands**:
- `vfeed add <id> <name>` — creates vfeed (note: node uses `vfeed create`, but Snowmix 0.5.2.2 uses `vfeed add`)
- `vfeed source <id> feed <feed_id>` — attaches real feed
- `vfeed geometry <id> <w> <h>` — sets dimensions
- `vfeed info <id>` — queries details (⚠️ may crash Snowmix — test carefully, use as last resort)
- `vfeed delete <id>` — removes one vfeed

---

## Phase 4: Audio Feeds, Mixers, Sinks (3 separate test files)

**Node pattern** is nearly identical for all three:
- `deleteAll()` → `create({name})` → `all()` → `byId(id)` → `create({name, id})` for update → `populate()` → verify

### 4a: `audioFeeds.js`
- `audio feed add <id> "<name>"`
- `audio feed list` → STAT: lines
- `audio feed info <id>`
- `audio feed delete <id>`

### 4b: `audioMixers.js`
- `audio mixer add <id> "<name>"`
- `audio mixer list`
- `audio mixer info <id>`
- `audio mixer delete <id>`

### 4c: `audioSinks.js`
- `audio sink add <id> "<name>"`
- `audio sink list`
- `audio sink info <id>`
- `audio sink delete <id>`

**Tests** — each file requires:
- `test_create_<entity>` — create with name, verify
- `test_list_<entity>` — verify list includes it
- `test_get_<entity>_by_id` — verify name matches
- `test_update_<entity>_name` — update via create with same ID
- `test_delete_all_<entity>` — remove all, verify empty
- `test_populate_<entity>` — verify re-read preserves state

---

## Phase 5: `audio.js` — Full Audio Pipeline

**Node pattern** — creates feeds → mixers → routes → sinks:
1. Connect
2. `audioFeeds.deleteAll()`, `audioMixers.deleteAll()`, `audioSinks.deleteAll()`
3. `audioFeeds.create()` × 2
4. `audioMixers.create()`
5. `audioSinks.create()`
6. `audioMixers.byId(1).addAudioFeed(1)` — feeds → mixer
7. `audioMixers.byId(1).unmuteAudioFeed(1)` — unmute
8. `audioMixers.byId(1).start()` — start mixer
9. `audioSinks.byId(1).addAudioMixer(1)` — mixer → sink
10. Cleanup

**Our approach**:
- `audio_mixer_add_feed(mixer_id, feed_id)` → `audio mixer source feed <mixer_id> <feed_id>`
- `audio_mixer_unmute_feed(mixer_id, feed_id)` → `audio mixer feed unmute <mixer_id> <feed_id>`
- `audio_mixer_start(mixer_id)` → `audio mixer run <mixer_id>`
- `audio_sink_add_mixer(sink_id, mixer_id)` → `audio sink source mixer <sink_id> <mixer_id>`

**Test**: `test_audio_pipeline_end_to_end` — full set-up → route → verify → teardown

---

## Phase 6: `texts.js` — Text Overlays

**Node pattern**:
- `snowmix.texts.create({string: 'north-west', location: 'nw', offset: [200, 100]})`
- `snowmix.texts.byId(id).show()`
- `snowmix.texts.all()`, `snowmix.texts.allIds()`

**Our approach**:
- `create_text(text_id=None, string='', location='nw', offset_x=0, offset_y=0, size=32, color='white') -> int`
- `show_text(text_id) -> str`
- `hide_text(text_id) -> str`
- `list_texts() -> list[dict]`
- `get_text(text_id) -> dict`

**Snowmix commands**:
- `text add <id>` — create text object
- `text string <id> "<text>"` — set content
- `text location <id> <n|ne|e|se|s|sw|w|nw|c>` — set anchor
- `text offset <id> <x> <y>` — pixel offset from anchor
- `text size <id> <size>` — font size
- `text color <id> <color>` — text color
- `text show <id>` — display
- `text hide <id>` — hide

**Tests**:
- `test_create_text` — create with string/location/offset, verify
- `test_create_multiple_texts` — verify IDs
- `test_show_text` — show, verify visible
- `test_show_and_list` — create 2+ texts, show some, verify show state

---

## Phase 7: `images.js` — Images + ImagePlaces

**Node pattern** more complex — two-tier: Image objects + ImagePlace objects (positioned instances):
- `snowmix.images.create({id: 1, filename: './cat.png'})`
- `snowmix.images.byId(1).addPlace({id: 1, x: 100, y: 200, location: 'n'})`
- `snowmix.imagePlaces.byId(1).show()`
- `snowmix.commands.list('Show')` → verifies `image overlay 1 3` etc.

**Our approach**:
- `image_add(id, file_path) -> str` — `image add <id> "<path>"`
- `image_place_add(image_id, place_id, x=0, y=0, location='n') -> str`
- `image_show(place_id) -> str`
- `image_hide(place_id) -> str`
- `list_images() -> list[dict]`
- `list_image_places() -> list[dict]`
- `get_image_place(place_id) -> dict`

**Snowmix commands**:
- `image add <id> "<path>"` — load image file
- `image place <id> <place_id> <x> <y> <location>` — position an instance
- `image show <id> [place_ids...]` — show with optional specific places
- `image hide <id>` — hide all places of image
- `image overlay <place_id>` — show a single place
- `image info <id>`
- `image place info <place_id>`
- `image delete <id>`

**Tests**:
- `test_create_image` — load image, verify dimensions
- `test_create_image_place` — position image, verify coordinates
- `test_show_image_place` — show, verify showing state
- `test_multi_image_multi_place` — 2 images, 3 places, cross-references
- `test_delete_images` — cleanup, verify empty

---

## Phase 8: `commands.js` — Custom Commands

**Node pattern**:
- `snowmix.commands.create('testCommand1', ['foo', 'bar'])`
- `snowmix.commands.list('testCommand1')` → `[undefined, 'foo', 'bar']`
- `snowmix.commands.list('rubbish')` → `undefined`
- `snowmix.commands.listAll()` → includes 'testCommand1'
- `snowmix.commands.delete('testCommand1')`
- `snowmix.commands.setCommandsOverlayedAtFrameEnd(['c1', 'c2'])`
- `snowmix.commands.commandsOverlayedAtFrameEnd()` → `['c1', 'c2']`

**Our approach**:
- `command_create(name, lines: list[str]) -> str`
- `command_list(name) -> list[str]`
- `command_list_all() -> list[str]`
- `command_delete(name) -> str`
- `set_overlay_commands(commands: list[str]) -> str`
- `get_overlay_commands() -> list[str]`

**Snowmix commands**:
- `command <name> add <line1> <line2> ...` — define custom command
- `command <name> list` — list lines
- `command list` — list all command names
- `command <name> delete` — remove
- `overlay finish set <cmd1> <cmd2> ...` — set commands run at frame end
- `overlay finish list` — show frame-end commands

**Tests**:
- `test_create_command` — define multi-line command
- `test_list_command` — verify lines stored
- `test_list_nonexistent_command` — returns empty list
- `test_list_all_commands` — verify our command appears
- `test_delete_command` — remove, verify gone
- `test_overlay_commands` — set/get frame-end overlay commands

---

## Phase 9: Wire Everything as MCP Tools in `main.py`

Add tool for each client method. Naming convention: `snowmix_<group>_<verb>`.

| Client Method | MCP Tool |
|---|---|
| `get_version()` | `snowmix_get_version` |
| `create_feed(name, id)` | `snowmix_create_feed` |
| `list_feeds()` | `snowmix_list_feeds` |
| `get_feed(feed_id)` | `snowmix_get_feed_info` (exists) |
| `update_feed(feed_id, name)` | `snowmix_update_feed` |
| `delete_all_vfeeds()` | `snowmix_delete_all_vfeeds` |
| `create_vfeed(name, source_id)` | `snowmix_create_vfeed` |
| `list_vfeeds()` | `snowmix_list_vfeeds` |
| `get_vfeed(vfeed_id)` | `snowmix_get_vfeed` |
| `create_audio_feed(name, id)` | `snowmix_create_audio_feed` |
| `list_audio_feeds()` | `snowmix_list_audio_feeds` |
| `delete_all_audio_feeds()` | `snowmix_delete_all_audio_feeds` |
| `create_audio_mixer(name, id)` | `snowmix_create_audio_mixer` |
| ... etc for mixers, sinks | ... |
| `audio_mixer_add_feed(mixer_id, feed_id)` | `snowmix_audio_mixer_add_feed` |
| `audio_mixer_start(mixer_id)` | `snowmix_audio_mixer_start` |
| `audio_sink_add_mixer(sink_id, mixer_id)` | `snowmix_audio_sink_add_mixer` |
| `create_text(string, location, ...)` | `snowmix_create_text` |
| `show_text(text_id)` | `snowmix_show_text` |
| `hide_text(text_id)` | `snowmix_hide_text` |
| `list_texts()` | `snowmix_list_texts` |
| `image_add(id, file_path)` | `snowmix_add_image` |
| `image_place_add(...)` | `snowmix_add_image_place` |
| `image_show(place_id)` | `snowmix_show_image_place` |
| `image_hide(image_id)` | `snowmix_hide_image_place` |
| `command_create(name, lines)` | `snowmix_create_command` |
| `command_list(name)` | `snowmix_get_command` |
| `command_list_all()` | `snowmix_list_commands` |
| `command_delete(name)` | `snowmix_delete_command` |
| `set_overlay_commands(cmds)` | `snowmix_set_overlay_commands` |
| `get_overlay_commands()` | `snowmix_get_overlay_commands` |

---

## Phase 10: Update Documentation

- `snowmix_commands_reference.md` — already has all 17 command categories, ensure it's accurate
- `README.md` — update tools table, add new usage examples
- `~/.hermes/skills/snowmix-mcp/SKILL.md` — update Available MCP Tools table
- `~/.hermes/skills/snowmix-mcp/references/reserved_commands.md` — update

---

## Execution Order (Incremental)

| Step | Description | Est. Test Count |
|------|-------------|-----------------|
| 0 | Clean up `snowmix_client.py` duplicates, add `_get_agent_ids` | 0 |
| 1 | `version.js` + improve `system-geometry.js` | 2 |
| 2 | `feeds.js` | 6 |
| 3 | `vfeeds.js` | 6 |
| 4a | `audioFeeds.js` | 6 |
| 4b | `audioMixers.js` | 6 |
| 4c | `audioSinks.js` | 6 |
| 5 | `audio.js` (pipeline) | 1 |
| 6 | `texts.js` | 4 |
| 7 | `images.js` | 5 |
| 8 | `commands.js` | 6 |
| 9 | Wire MCP tools in `main.py` | — |
| 10 | Update docs | — |

**Total**: ~48 new tests

---

## Test Assets

Test media files live under `/home/rjodouin/Downloads/hypno2_fx_DLs/`:
- **Video**: `Goopy Gradients/` — has `0001.mp4`, `0002.mp4` etc.
- **Images**: `.png` files exist in the tree (find them before the image tests)
- These paths are used for `feed add` with file paths, `image add` with file paths, etc.

## Notes

- **Snowmix command syntax differs from node-snowmix**: node uses `vfeed create` but our 0.5.2.2 uses `vfeed add`. Always verify with actual snowmix before implementing.
- **`vfeed info` may crash Snowmix**: discovered in earlier sessions. Use `vfeed list` or verify via side effects instead.
- **Use randomized IDs** (2000–9000 range for feeds, 100–199 range for vfeeds, higher ranges for text/images/audio) to avoid collisions.
- **Silent success**: Many commands return nothing on success. Verify via `info`/`list` queries.
- **Connection banner**: Client must consume the version bannerline before sending commands.
