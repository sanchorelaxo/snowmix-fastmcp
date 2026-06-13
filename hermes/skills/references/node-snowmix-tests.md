# node-snowmix test suite map

Source: https://github.com/matthew1000/node-snowmix/tree/master/test

Port status:
- `feeds.js` → ported (`test_snowmix.py`: cover create, rename, query-by-id, all-ids)
- `vfeeds.js` → needs port (covered by task grafts, not yet stabilized in main suite)
- `system-geometry.js` → ported (tests pass)
- `commands.js` → not yet ported (custom command CRUD)
- `images.js` → blocked on PNG fixture assets under `tests/images/`
- `audioFeeds.js` / `audioMixers.js` / `audioSinks.js` / `audio.js` → not yet ported

Implemented Python equivalents cover:
- async client fixture with banner consumption
- multi-step feed creation via feed add + geometry
- assert_command_failed for MSG: errors

Missing to complete the port:
1. `tests/images/` fixture set (cat.png, leopard.png) or download substitutes
2. client methods exposing:
   - `vfeed add/drop/info`, `vfeed source`, `vfeed populate`
   - `audioFeed/Mixer/Sink` CRUD helpers
   - `commands create/list/listAll/delete`, `setCommandsOverlayedAtFrameEnd`
   - `images` and `imagePlaces` helpers
3. strict no-warnings/no-errors assertions mirroring node logger checks
