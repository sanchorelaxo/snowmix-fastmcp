# GStreamer E2E Pipeline Patterns for Snowmix

Verified against Snowmix 0.5.2.2 and GStreamer 1.24.2.

## Architecture

```
  Video File → GStreamer (decode → BGRA → shmsink) → Snowmix feed socket
                                                              ↓
                                                    Snowmix mixing loop
                                                              ↓
  Output File ← GStreamer (shmsrc → encode → filesink) ← Snowmix mixer socket (/tmp/mixer1)
```

## INI Requirements

The INI must include:
- `system socket /tmp/mixer1` — output control socket for shmsrc
- `system geometry 1280 720 BGRA` — pixel format must be BGRA
- `maxplaces` BEFORE `system geometry` (see SKILL.md maxplaces section)
- `feed idle 0 1` + `feed alpha 0 1` + `stack 0` — background layer

## Input Pipeline (Video → Snowmix Feed)

```python
shm_size = width * height * 4 * 26  # 26 frames of BGRA buffer

pipeline = (
    f"filesrc location={video_path} "
    f"! decodebin name=decoder "
    f"! videoconvert "
    f"! videoscale "
    f"! video/x-raw,format=BGRA,width={width},height={height} "
    f"! shmsink socket-path={feed_socket} "
    f"shm-size={shm_size} wait-for-connection=0 sync=true"
)
```

Run with: `gst-launch-1.0 -q <pipeline>`

Key points:
- `wait-for-connection=0` — don't wait for Snowmix to connect before starting
- `sync=true` — pace frames at natural framerate
- `shm-size` must be large enough for multiple BGRA frames (W×H×4×N)
- Feed socket path must match what was set via `feed socket <id> <path>`

## Output Pipeline (Snowmix → File)

```python
pipeline = (
    f"shmsrc socket-path=/tmp/mixer1 do-timestamp=true is-live=true "
    f"! video/x-raw,format=BGRA,width={width},height={height},framerate=24/1 "
    f"! queue leaky=0 "
    f"! videoconvert "
    f"! x264enc bitrate=3000 tune=zerolatency speed-preset=5 "
    f"! h264parse "
    f"! mp4mux "
    f"! queue "
    f"! filesink location={output_path}"
)
```

Run with: `gst-launch-1.0 -e -v <pipeline>` (the `-e` sends EOS on termination for proper mp4 finalization)

Key points:
- Framerate in caps must match `system frame rate` in INI
- Stop output pipeline BEFORE input pipeline (EOS for proper mp4 closing)
- `is-live=true` on shmsrc for live source behavior

## Feed Setup Sequence (via MCP Client)

```python
await client.send_command("feed add 1 Feed1")
await client.feed_geometry(1, 1280, 720)
await client.feed_socket(1, "/tmp/feed1-control-pipe")
await client.feed_live(1)
# Start GStreamer input FIRST, then stack
# await start_gstreamer_input(...)
# await asyncio.sleep(2)
# await client.stack(0, 1)  # stack after data flows
```

## Overlay Commands During Pipeline

Once both input and output pipelines are running (mixing loop active):

```python
# Image overlay (requires m_overlay != NULL)
await client.image_load(1, image_path)     # no quotes around path!
await client.image_place(1, 1, 100, 50)    # place_id, image_id, x, y
await client.image_overlay([1])             # now works with pipeline running

# Text overlay
await client.send_command("text string 1 MyText")
await client.send_command("text font 1 FreeSans 24")
await client.text_place(1, 1, 1, 50, 50)   # place_id, text_id, font_id, x, y
await client.send_command("text overlay 1")
```

## Test Structure

```python
@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    # Kill stale, clean sockets, spawn with DEVNULL stdout
    ...
    
async def test_e2e(client):
    # 1. Setup feed
    # 2. Load image, place it (before pipeline)
    # 3. Start GStreamer input
    # 4. Start GStreamer output
    # 5. Overlay image + text (during pipeline)
    # 6. Wait 4-5 seconds for mixing
    # 7. Stop output (EOS), then input
    # 8. Assert output file exists and > 1KB
```

## Known Issues

- `stack 0 <feed_id>` before GStreamer input connects can crash Snowmix
- Snowmix subprocess must use `stdout=DEVNULL` (not tee/pipe) — Snowmix bails if fd 1 is closed
- Beziers01.mp4 (1280x720, H264, 29.97fps) works as test input
- title2.png (1920x1080) works as test image overlay
- Output mp4 at 3000kbps x264 produces reasonable quality for test verification
