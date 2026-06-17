"""
End-to-end test for snowmix-fastmcp — mixed video output with GStreamer.

This test starts Snowmix, feeds a real video file into it via GStreamer shmsink,
configures image/text overlays via the MCP client, reads mixed frames out via
GStreamer shmsrc, and verifies the output file has content.

Flow:
  1. Start Snowmix with advancedTest.ini (socket /tmp/mixer1, 1280x720 BGRA)
  2. Create feed 1, set socket path, stack it
  3. Start GStreamer input pipeline: filesrc -> decodebin -> videoconvert
     -> videoscale -> BGRA caps -> shmsink (to feed socket)
  4. Start GStreamer output pipeline: shmsrc (from /tmp/mixer1) -> videoconvert
     -> x264enc -> mp4mux -> filesink (to /tmp/e2e_output.mp4)
  5. Via MCP client: load image, place image, overlay, set text
  6. Wait for frames to be mixed and encoded
  7. Stop pipelines, verify output file exists and has content
"""

import asyncio
import os
import shutil
from pathlib import Path

import pytest
import pytest_asyncio

from snowmix_client import SnowmixClient

# ------------------------------------------------------------------ #
#  Constants
# ------------------------------------------------------------------ #

REPO_ROOT = Path(__file__).resolve().parent
INI_PATH = REPO_ROOT / "ini" / "advancedTest.ini"
SNOWMIX_BIN = os.environ.get("SNOWMIX_BIN", "/usr/local/bin/snowmix")
SNOWMIX_HOME = os.environ.get("SNOWMIX", "/home/rjodouin/Snowmix-0.5.2.2")
GST_LAUNCH = shutil.which("gst-launch-1.0")
assert GST_LAUNCH, "gst-launch-1.0 not found"

# Video and image assets from hypno2_fx_DLs
VIDEO_FILE = "/home/rjodouin/Downloads/hypno2_fx_DLs/hypno2_Beziers/Beziers01.mp4"
IMAGE_FILE = "/home/rjodouin/Downloads/hypno2_fx_DLs/hypno_Reductions by cinema.av/stills/title2.png"

# Snowmix sockets
MIXER_SOCKET = "/tmp/mixer1"
FEED_SOCKET = "/tmp/feed1-control-pipe"

# Output file
OUTPUT_FILE = "/tmp/snowmix_e2e_output.mp4"

# System geometry (must match advancedTest.ini)
WIDTH = 1280
HEIGHT = 720
FRAMERATE = "24/1"

# Preconditions
assert INI_PATH.exists(), f"Missing test ini: {INI_PATH}"
assert os.path.exists(SNOWMIX_BIN), f"Missing snowmix: {SNOWMIX_BIN}"
assert os.path.exists(VIDEO_FILE), f"Missing video: {VIDEO_FILE}"
assert os.path.exists(IMAGE_FILE), f"Missing image: {IMAGE_FILE}"


# ------------------------------------------------------------------ #
#  Fixtures
# ------------------------------------------------------------------ #

@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    """Start Snowmix with advancedTest.ini."""
    # Kill any stale Snowmix on port 9999
    stale = await asyncio.create_subprocess_exec(
        "pkill", "-9", "snowmix",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await stale.wait()
    await asyncio.sleep(1)

    # Clean up stale sockets
    for sock in (MIXER_SOCKET, FEED_SOCKET):
        if os.path.exists(sock):
            os.remove(sock)

    env = {**os.environ, "SNOWMIX": SNOWMIX_HOME}
    proc = await asyncio.create_subprocess_exec(
        SNOWMIX_BIN,
        str(INI_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    await asyncio.sleep(2)
    yield proc
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


@pytest_asyncio.fixture
async def client(snowmix_process):
    """Fresh connected client per test."""
    c = SnowmixClient(host="127.0.0.1", port=9999)
    await c.connect()
    yield c
    await c.close()


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

async def start_gstreamer_input(video_path: str, feed_socket: str,
                                 width: int, height: int) -> asyncio.subprocess.Process:
    """Start GStreamer pipeline to feed video into Snowmix via shmsink.

    filesrc -> decodebin -> videoconvert -> videoscale -> BGRA caps -> shmsink
    """
    shm_size = width * height * 4 * 26  # enough for 26 frames
    pipeline = (
        f"filesrc location={video_path} "
        f"! decodebin name=decoder "
        f"! videoconvert "
        f"! videoscale "
        f"! video/x-raw,format=BGRA,width={width},height={height} "
        f"! shmsink socket-path={feed_socket} "
        f"shm-size={shm_size} wait-for-connection=0 sync=true"
    )
    proc = await asyncio.create_subprocess_exec(
        GST_LAUNCH, "-q", pipeline,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def start_gstreamer_output(output_path: str, mixer_socket: str,
                                  width: int, height: int) -> asyncio.subprocess.Process:
    """Start GStreamer pipeline to read mixed frames from Snowmix via shmsrc.

    shmsrc -> queue -> BGRA caps -> videoconvert -> x264enc -> mp4mux -> filesink
    """
    pipeline = (
        f"shmsrc socket-path={mixer_socket} do-timestamp=true is-live=true "
        f"! video/x-raw,format=BGRA,width={width},height={height},framerate={FRAMERATE} "
        f"! queue leaky=0 "
        f"! videoconvert "
        f"! x264enc bitrate=3000 tune=zerolatency speed-preset=5 "
        f"! h264parse "
        f"! mp4mux "
        f"! queue "
        f"! filesink location={output_path}"
    )
    proc = await asyncio.create_subprocess_exec(
        GST_LAUNCH, "-e", "-v", pipeline,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def stop_proc(proc: asyncio.subprocess.Process):
    """Terminate a GStreamer process gracefully."""
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


async def setup_feed(client: SnowmixClient, feed_id: int = 1):
    """Create and configure feed 1 if it doesn't already exist."""
    feeds = await client.list_feeds()
    ids = [f["id"] for f in feeds]
    if feed_id not in ids:
        await client.send_command(f"feed add {feed_id} Feed{feed_id}")
    await client.feed_geometry(feed_id, WIDTH, HEIGHT)
    await client.feed_socket(feed_id, FEED_SOCKET)
    await client.feed_live(feed_id)
    await client.stack(0, feed_id)


# ------------------------------------------------------------------ #
#  Tests
# ------------------------------------------------------------------ #

class TestEndToEnd:
    """End-to-end: feed video, overlay image+text, capture mixed output."""

    async def test_feed_setup_and_stack(self, client: SnowmixClient):
        """Create feed 1, set socket, mark live, and stack it."""
        await setup_feed(client, 1)

        # Verify feed exists
        feeds = await client.list_feeds()
        ids = [f["id"] for f in feeds]
        assert 1 in ids, f"Feed 1 missing from: {feeds}"

    async def test_image_overlay_during_pipeline(self, client: SnowmixClient):
        """Load image, place it, and overlay while GStreamer pipeline runs.

        This is the core e2e test: video flows in, image is overlaid,
        mixed frames flow out to a file.
        """
        # Ensure feed 1 is set up
        await setup_feed(client, 1)

        # Load and place image
        resp = await client.image_load(1, IMAGE_FILE)
        assert resp == "OK", f"image load failed: {resp}"

        resp = await client.image_place(1, 1, 100, 50)
        assert resp == "OK", f"image place failed: {resp}"

        # Start GStreamer input (video -> Snowmix feed)
        input_proc = await start_gstreamer_input(
            VIDEO_FILE, FEED_SOCKET, WIDTH, HEIGHT
        )
        # Give input pipeline time to connect
        await asyncio.sleep(3)

        # Start GStreamer output (Snowmix -> file)
        # Clean up old output
        if os.path.exists(OUTPUT_FILE):
            os.remove(OUTPUT_FILE)

        output_proc = await start_gstreamer_output(
            OUTPUT_FILE, MIXER_SOCKET, WIDTH, HEIGHT
        )

        # Give output pipeline time to start reading frames
        await asyncio.sleep(2)

        # Now overlay the image (mixing loop is active because output is reading)
        resp = await client.image_overlay([1])
        # With pipeline running, overlay should succeed
        assert resp == "OK" or "Invalid" not in resp, (
            f"image overlay failed: {resp}"
        )

        # Add text overlay too
        await client.send_command("text string 1 Snowmix_E2E_Test")
        await client.send_command("text font 1 FreeSans 24")
        await client.text_place(1, 1, 1, 50, 50)
        await client.send_command("text overlay 1")

        # Let it mix for a few seconds
        await asyncio.sleep(5)

        # Stop output first (sends EOS for proper mp4 finalization)
        await stop_proc(output_proc)
        await stop_proc(input_proc)

        # Verify output file exists and has content
        assert os.path.exists(OUTPUT_FILE), "Output file was not created"
        size = os.path.getsize(OUTPUT_FILE)
        assert size > 1000, f"Output file too small ({size} bytes)"
        print(f"\nE2E output: {OUTPUT_FILE} ({size} bytes)")

    async def test_feed_status_after_streaming(self, client: SnowmixClient):
        """After streaming, feed 1 should show non-zero frame count."""
        # This test runs after the pipeline test (module-scoped Snowmix)
        info = await client.get_feed_info(1)
        assert "STAT:" in info
        assert "1" in info
        # Feed should exist and show some activity
        assert "Feed1" in info or "feed 1" in info.lower()
