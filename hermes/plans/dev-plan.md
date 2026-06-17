# Snowmix-FastMCP Dev Plan

## Status
- Baseline: 25/25 tests pass in test_snowmix.py with test.ini
- test_advanced.py: 14 tests, all failing due to INI + client issues
- End-to-end test: not yet created

## Root Causes Identified

1. **Wrong maxplaces keywords in advancedTest.ini**
   - Current: `maxplaces images 16`, `maxplaces imageplaces 16`
   - Correct (per expandedTestMin.ini): `maxplaces loaded_images N`, `maxplaces placed_images N`
   - Same issue for texts: `maxplaces strings`, `maxplaces texts` are correct, but `maxplaces fonts` is missing

2. **Test IDs exceed maxplaces limits**
   - Tests use image IDs 1001-4011, text IDs 2001-2005, feed IDs 3001-3013
   - Default maxplaces = 16, so any ID >= 16 is rejected
   - Fix: set maxplaces to 5000+ for all subsystems

3. **image_load wraps path in quotes**
   - Client sends: `image load 1001 "/path/to/file.png"`
   - Snowmix C++ parser (`set_image_load` in video_image.cpp:925) uses `sscanf(str, "%u %[^\n]", ...)` which captures quotes as part of the filename
   - Fix: remove quotes, send bare path

4. **Missing slib includes**
   - Image and text subsystems need to be loaded via `include ../slib/images.slib` and `include ../slib/texts.slib`
   - Without these, `image load` and `text` commands may not be fully initialized

5. **image_load success response handling**
   - Snowmix is silent on successful image load (no MSG:, no STAT:)
   - send_command() returns "OK" on timeout with no data, which is correct
   - But the quotes issue prevents success

## Steps (in order)

### 1. Fix advancedTest.ini
- Use correct maxplaces keywords: `loaded_images`, `placed_images`
- Set all limits to 5000 to accommodate test IDs
- Include slib files for images, texts, system, scenes, feeds
- Add `maxplaces fonts 5000`

### 2. Fix snowmix_client.py
- Remove quotes from image_load path: `f'image load {image_id} {file_path}'`

### 3. Fix test_advanced.py
- Verify all test IDs are within maxplaces limits (they will be once maxplaces = 5000)
- Verify assertions match Snowmix's actual response behavior

### 4. Run test_advanced.py
- `SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2 ./venv/bin/pytest test_advanced.py -v`
- Fix any remaining failures

### 5. Scan video/image assets
- Search /home/rjodouin/Downloads/hypno2_fx_DLs/ for PNG images and video files
- Catalog available assets for e2e test

### 6. Create test_e2e.py
- End-to-end test that exercises the full Snowmix pipeline:
  - Start Snowmix with advancedTest.ini
  - Create video feeds from actual video files
  - Load PNG images
  - Create text overlays
  - Create virtual feeds
  - Build an overlay scene with image + text
  - Verify the full pipeline via Snowmix STAT: queries
- Use mixed-in assets: at least 1 video file + 1 PNG image + text overlays

### 7. Run full suite
- `SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2 ./venv/bin/pytest test_snowmix.py test_advanced.py test_e2e.py -v`
- All tests green

## Files to Modify
- `ini/advancedTest.ini` — fix maxplaces keywords, add slib includes
- `snowmix_client.py` — fix image_load path quoting
- `test_advanced.py` — may need assertion adjustments
- `test_e2e.py` — new file

## Key Technical Details
- Snowmix binary: `/usr/local/bin/snowmix`
- Snowmix home: `/home/rjodouin/Snowmix-0.5.2.2`
- Project venv: `./venv`
- Control port: 9999
- maxplaces keywords (from expandedTestMin.ini): `loaded_images`, `placed_images`, `video_feeds`, `audio_feeds`, `audio_mixers`, `audio_sink`, `strings`, `texts`, `shapes`, `shapeplaces`
- slib path: `../slib/` relative to ini directory (resolves to `/home/rjodouin/Snowmix-0.5.2.2/slib/`)
