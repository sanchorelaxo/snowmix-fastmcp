# GStreamer E2E Pipeline Patterns for Snowmix

Verified against Snowmix 0.5.2.2 and GStreamer 1.24.2.
All patterns below were confirmed by a passing 3-test e2e suite producing
valid h264 1280x720 mp4 output (ffprobe-verified: 144 frames / ~6s).

## Architecture

```
  Video File -> GStreamer (decode -> BGRA -> shmsink) -> Snowmix feed socket
                                                              |
                                                    Snowmix mixing loop
                                                    (runs Show macro per frame)
                                                              |
  Output File <- GStreamer (shmsrc -> encode -> filesink) <- Snowmix mixer socket (/tmp/mixer1)
```

## INI Requirements

The INI must include:
- `system socket /tmp/mixer1` — output control socket for shmsrc
- `system geometry 1280 720 BGRA` — pixel format must be BGRA
- `maxplaces` BEFORE `system geometry` (see SKILL.md maxplaces section)
- `feed idle 0 1` + `feed alpha 0 1` + `stack 0` — background layer

## Input Pipeline (Video -> Snowmix Feed)

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

Run with: `create_subprocess_exec(GST_LAUNCH, "-q", *shlex.split(pipeline))`

CRITICAL: This build of gst-launch-1.0 rejects the pipeline as a single argv
string ("erroneous pipeline: syntax error"). You MUST split it with
shlex.split so `!` is its own argv element.

Key points:
- `wait-for-connection=0` — don't wait for Snowmix to connect before starting
- `sync=true` — pace frames at natural framerate
- `shm-size` must be large enough for multiple BGRA frames (W x H x 4 x N)
- Feed socket path must match what was set via `feed socket <id> <path>`

## Output Pipeline (Snowmix -> File)

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

Run with: `create_subprocess_exec(GST_LAUNCH, "-e", "-v", *shlex.split(pipeline))`
(the `-e` sends EOS on SIGINT for proper mp4 finalization)

Key points:
- Framerate in caps must match `system frame rate` in INI
- Stop output pipeline with SIGINT (not SIGTERM/kill) so gst-launch sends EOS
  and mp4mux finalises a valid, playable mp4. Then wait for the process to
  exit (timeout 10s), then kill input.
- `is-live=true` on shmsrc for live source behavior

## Snowmix Subprocess Setup (Critical)

Snowmix wires a default controller to stdin(fd0)/stdout(fd1) at startup.
If stdin EOFs (e.g. inherited /dev/null), that controller closes, taking
fd 1 with it. The next `feed socket` creates an AF_UNIX socket that the OS
assigns to fd 1, and Snowmix bails out with:
  "Creating a socket returned fd 1. This means that stdout was closed
   upon startup. Bailing out."

FIX: keep stdin open with `stdin=asyncio.subprocess.PIPE` (held open for
the process lifetime — never write to it, never close it):

```python
proc = await asyncio.create_subprocess_exec(
    SNOWMIX_BIN, str(INI_PATH),
    stdin=asyncio.subprocess.PIPE,   # CRITICAL: prevents fd-1 bail-out
    stdout=asyncio.subprocess.DEVNULL,
    stderr=asyncio.subprocess.PIPE,
)
```

## Feed Setup Sequence (via MCP Client)

```python
await client.send_command("feed add 1 Feed1")
await client.feed_geometry(1, 1280, 720)
await client.feed_socket(1, "/tmp/feed1-control-pipe")
await client.feed_live(1)
await client.stack(0, 1)   # SAFE even before GStreamer input starts
```

Note: `stack 0 <feed_id>` on an unconnected feed is SAFE — the feed enters
SETUP state and no crash occurs. The earlier claim that stacking before
the GStreamer input connects crashes Snowmix was a misdiagnosis of the
fd-1 bail-out (see above).

## Overlay Pattern: Show Macro (Critical)

`image overlay` and `text overlay` as one-shot commands ALWAYS return
"Invalid parameters" — even with a running pipeline. `m_overlay` (the
mixing buffer) is set at the start of each MixFrame call and reset to NULL
after each frame (video_mixer.cpp:1608). One-shot commands run between
frames, so they always see m_overlay==NULL.

The correct pattern: embed overlay commands in the `overlay finish` macro
(`Show`), which Snowmix executes once per output frame while m_overlay is
valid. Configure this BEFORE starting the output pipeline:

```python
# Load + place image and set up text BEFORE building the macro
await client.image_load(1, image_path)       # no quotes around path!
await client.image_place(1, 1, 100, 50)       # place_id, image_id, x, y
await client.send_command("text string 1 MyText")
await client.send_command("text font 1 FreeSans 24")
await client.text_place(1, 1, 1, 50, 50)      # place_id, text_id, font_id, x, y

# Rebuild Show to overlay image 1 + text 1 every frame
await client.command_delete("Show")
await client.command_create("Show")
await client.send_command("image overlay 1")  # recorded into Show
await client.send_command("text overlay 1")   # recorded into Show
await client.send_command("loop")             # recorded into Show
await client.command_end()
await client.send_command("overlay finish Show")
```

Then start the GStreamer output pipeline. The shmsrc connecting to the
mixer socket activates the mixing loop, which runs Show every frame,
applying the overlays automatically.

## Stopping the Pipeline Gracefully

```python
# Stop output first with SIGINT so gst-launch (-e) sends EOS
# and mp4mux finalises a valid, playable mp4.
if output_proc.returncode is None:
    output_proc.send_signal(signal.SIGINT)
    try:
        await asyncio.wait_for(output_proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        output_proc.kill()
        await output_proc.wait()
await stop_proc(input_proc)
```

## Test Structure

```python
@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    # Kill stale, clean sockets, spawn with stdin=PIPE (CRITICAL)
    ...

async def test_image_overlay_during_pipeline(client):
    # 1. Setup feed (add, geometry, socket, live, stack)
    # 2. Load image, place it, set up text (BEFORE building macro)
    # 3. Rebuild Show macro with image overlay + text overlay + loop
    # 4. Bind macro: overlay finish Show
    # 5. Start GStreamer input pipeline
    # 6. Start GStreamer output pipeline (activates mixing loop)
    # 7. Wait ~6 seconds for mixing
    # 8. Stop output with SIGINT (EOS for valid mp4), then input
    # 9. Assert output file exists and > 10KB
```

## Test Assets

- Beziers01.mp4 (1280x720, H264, ~30fps) at ~/Downloads/hypno2_fx_DLs/hypno2_Beziers/
- title2.png (1920x1080) at ~/Downloads/hypno2_fx_DLs/hypno_Reductions by cinema.av/stills/
- Output mp4 at 3000kbps x264 produces reasonable quality for test verification

## OBS Studio Integration (obs-gstreamer plugin)

The [obs-gstreamer](https://github.com/fzwoch/obs-gstreamer) plugin for OBS
Studio accepts GStreamer pipeline strings in its source properties. The plugin
provides two internal sinks named `video` and `audio` — your pipeline must
terminate with `video.` (and optionally `audio.`).

### Same-Machine: shmsrc (zero encoding, minimal latency)

When OBS and Snowmix run on the same machine AND OBS is NOT a Flatpak, use
`shmsrc` directly. No encoding needed — raw BGRA frames flow through shared
memory. This is the preferred pattern for non-Flatpak OBS.

**WARNING: Flatpak OBS cannot use shmsrc.** Flatpak's bwrap sandbox has a
private `/dev/shm` namespace, so `shmsrc` can't mmap Snowmix's shared memory
segment. See "Flatpak OBS Cannot mmap /dev/shm" below for the TCP bridge
workaround.

In the obs-gstreamer source Pipeline field (replace the default
`videotestsrc` pipeline):

```
shmsrc socket-path=/tmp/mixer1 do-timestamp=true is-live=true ! video/x-raw,format=BGRA,pixel-aspect-ratio=1/1,interlace-mode=progressive,framerate=24/1,width=1280,height=720 ! videoconvert ! video.
```

The `video.` at the end is the obs-gstreamer internal sink. `videoconvert`
bridges BGRA caps negotiation. Width/height/framerate must match the Snowmix
INI (`system geometry` and `system frame rate`).

OBS reads from the mixer socket whenever the source is active — Snowmix's mixing
loop activates on first read, same as when using a gst-launch output pipeline.
No output2rtp or separate GStreamer output process is needed.

### CRITICAL: Flatpak OBS Cannot See /tmp Sockets

If OBS Studio is installed as a **Flatpak** (check: `flatpak list | grep obs`),
it runs inside a `bwrap` sandbox with its own private `/tmp` namespace. A socket
at `/tmp/mixer1` is INVISIBLE to OBS — the obs-gstreamer plugin logs:
```
[obs-gstreamer] snowmix-input1: Could not open socket /tmp/mixer1: 2 No such file or directory
```
Even though `ls -la /tmp/mixer1` shows the socket exists on the host.

**Fix (socket path only):** Put Snowmix sockets in a home-directory directory
that the Flatpak sandbox can access:

1. Create `~/.snowmix-sockets/`
2. In the Snowmix INI: `system socket /home/<user>/.snowmix-sockets/mixer1`
3. Feed socket: `feed socket <id> /home/<user>/.snowmix-sockets/feed1-control-pipe`
4. In the obs-gstreamer pipeline, use the same home-dir path.

This fixes the socket-not-found error, BUT shmsrc will STILL fail (see next
section). The home-dir socket is necessary but not sufficient for Flatpak OBS.

### CRITICAL: Flatpak OBS Cannot mmap /dev/shm (shmsrc Broken)

Even after fixing the socket path, `shmsrc` will fail inside a Flatpak OBS.
The Unix socket connects (OBS finds it), but `shmsrc` needs to `mmap` the
POSIX shared memory segment Snowmix created at `/dev/shm/shmpipe.<pid>.    0`.
Flatpak's `bwrap` mounts its own private `tmpfs` at `/dev/shm`, so the shm
segment is invisible inside the sandbox.

Symptoms:
- Snowmix stderr: `Output pipe connection broken. Resetting socket` (repeated)
- OBS log: `[obs-gstreamer] snowmix-input1: Failed to read from shmsrc`
- OBS log: `[obs-gstreamer] snowmix-input1: Internal data stream error.`
- `flatpak override --user --filesystem=/dev/shm com.obsproject.Studio` does
  NOT fix this — bwrap still mounts a private tmpfs regardless.

**Fix: TCP Bridge (host-side GStreamer process)**

Run a GStreamer bridge process on the HOST that reads from Snowmix via shmsrc
(host has full /dev/shm access), encodes to H264, muxes to MPEG-TS, and serves
over TCP on localhost. Flatpak allows localhost network, so OBS connects via
`tcpclientsrc`.

Host-side bridge pipeline (run as a separate gst-launch process):
```
shmsrc socket-path=/home/<user>/.snowmix-sockets/mixer1 do-timestamp=true is-live=true
! video/x-raw,format=BGRA,width=1280,height=720,framerate=24/1
! queue leaky=0
! videoconvert
! x264enc bitrate=4000 tune=zerolatency speed-preset=5
! mpegtsmux
! tcpserversink host=127.0.0.1 port=5000 sync=false
```

OBS obs-gstreamer source pipeline:
```
tcpclientsrc host=127.0.0.1 port=5000 ! tsdemux ! decodebin ! videoconvert ! video.
```

This adds ~1 frame of encoding latency but is the only working approach for
Flatpak OBS. RTP over UDP is an alternative for remote OBS (see below), but
TCP over localhost is simpler for same-machine.

### Using obs_bridge.py (Permanent Bridge Component)

Instead of running the host-side bridge pipeline manually with gst-launch,
use the `obs_bridge.py` module which manages Snowmix + video input + TCP
bridge as a unit:

**Standalone CLI:**
```bash
source venv/bin/activate
python obs_bridge.py --video /path/to/video.mp4 --image /path/to/overlay.png --text "Live"
```

The CLI prints the OBS pipeline to copy, then runs until Ctrl-C. The video
input auto-restarts when the file reaches EOS, so the bridge runs indefinitely.

**As an MCP tool:**
```
snowmix_bridge_start(video_file="/path/to/video.mp4", image_file="/path/to/overlay.png")
snowmix_bridge_status()
snowmix_bridge_stop()
```

**As a Python module:**
```python
from obs_bridge import SnowmixBridge, BridgeConfig

config = BridgeConfig(video_file="/path/to/video.mp4", tcp_port=5000)
bridge = SnowmixBridge(config)
await bridge.start()
# ... OBS connects to tcpclientsrc host=127.0.0.1 port=5000 ...
await bridge.stop()
```

The `SnowmixBridge` class handles:
- Killing stale snowmix/gst-launch processes
- Creating `~/.snowmix-sockets/` and cleaning old socket files
- Starting Snowmix with `ini/obs.ini` and `stdin=PIPE` (prevents fd-1 bail-out)
- Configuring feed + image/text overlays + Show macro via `SnowmixClient`
- Starting video input (auto-restarts on EOS via monitor task)
- Starting the TCP bridge pipeline (shmsrc → x264enc → mpegtsmux → tcpserversink)
- Monitoring all processes and reporting errors via `BridgeStatus`

### CRITICAL: OBS Source Activation Timing

OBS only attempts to connect to the shmsrc socket when the source is
**activated** (added to a scene, made visible, or properties OK'd). If the
socket doesn't exist at that moment, the connection fails and OBS does NOT
retry automatically — the source stays blank even after Snowmix creates the
socket.

**Fix:** Start Snowmix FIRST (verify socket exists with `ls -la`), then in OBS:
right-click the source → Deactivate → wait 2s → Activate. Or open Properties
and click OK to re-initialize the pipeline.

### Pitfall: Never Use ximagesink/autovideosink in obs-gstreamer

The obs-gstreamer plugin provides its own internal sinks (`video.` and
`audio.`). Using `ximagesink` or `autovideosink` at the end of the pipeline
causes "Could not initialise X output" — the plugin cannot render to a
separate X window. Always terminate with `video.` (and `audio.` for audio).

### Remote Machine: RTP (requires encoding)

When OBS is on a different machine, run an encoding output pipeline on the
Snowmix machine:

```bash
gst-launch-1.0 -v \
    shmsrc socket-path=/tmp/mixer1 do-timestamp=true is-live=true \
    ! video/x-raw,format=BGRA,framerate=24/1,width=1280,height=720 \
    ! queue ! videoconvert \
    ! x264enc bitrate=3000 tune=zerolatency speed-preset=5 \
    ! h264parse ! rtph264pay \
    ! queue ! udpsink clients=<OBS_IP>:4012 sync=true
```

Then in OBS obs-gstreamer source:

```
udpsrc port=4012 caps="application/x-rtp,media=video,clock-rate=90000,encoding-name=H264" ! rtph264depay ! h264parse ! decodebin ! videoconvert ! video.
```

### Audio

Audio is NOT available via shmsrc — Snowmix delivers audio through the TCP
control connection (`audio sink ctr isaudio <id>`), not shared memory. For
same-machine audio, run the `av_output2tcp_server` script or handle audio via
a separate OBS audio source. See `/home/rjodouin/Snowmix-0.5.2.2/scripts/av_output2screen`
for the fdsrc-based audio pattern.

### Live Test Script Pattern

To run Snowmix live for N seconds (e.g. to verify OBS can see the output),
without starting an output pipeline (OBS reads the mixer socket directly):

```python
# 1. Start Snowmix with stdin=PIPE (prevents fd-1 bail-out)
# 2. Connect client, setup feed (add, geometry, socket, live, stack)
# 3. Load image + text, rebuild Show macro with overlays
# 4. Start GStreamer INPUT pipeline only (no output pipeline)
# 5. asyncio.sleep(N)  — OBS reads /tmp/mixer1 during this window
# 6. Cleanup: stop input, close stdin, terminate Snowmix
```

The key difference from the e2e test: no GStreamer output pipeline is started.
OBS (or any shmsrc reader) acts as the output consumer, activating the mixing
loop.

## Manual Debugging Technique

When diagnosing Snowmix issues, you can run it manually with stdin held open
via a named pipe and probe via raw socket:

```bash
mkfifo /tmp/sm_stdin_fifo
SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2 /usr/local/bin/snowmix ini/advancedTest.ini \
    >/tmp/sm_stdout.log 2>/tmp/sm_stderr.log </tmp/sm_stdin_fifo &
# In another terminal, hold the pipe open:
exec 3>/tmp/sm_stdin_fifo; sleep 3600
# Now probe via Python socket to 127.0.0.1:9999
```

This lets you test commands interactively without the test harness, while
keeping stdin open to avoid the fd-1 bail-out.
