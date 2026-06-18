"""OBS TCP Bridge for Snowmix.

Provides a TCP bridge between Snowmix's shared-memory output socket and
Flatpak-sandboxed OBS Studio.  Flatpak's bwrap gives OBS a private /dev/shm
namespace, so GStreamer's shmsrc inside OBS cannot mmap the shared-memory
segments Snowmix creates on the host.  This bridge reads from Snowmix via
shmsrc on the host and re-serves the stream over TCP localhost, which the
Flatpak network namespace allows.

Architecture:
    Video file(s) -> GStreamer (decode -> BGRA -> shmsink) -> Snowmix feed socket(s)
                                                                  |
                                                        Snowmix mixing loop
                                                        (runs Show macro per frame)
                                                                  |
    OBS <- tcpclientsrc <- tsdemux <- decodebin <- tcpserversink <- x264enc <- shmsrc <- Snowmix mixer socket

Supports N video sources with automatic layout computation:
  - side_by_side: sources arranged left-to-right, each gets canvas_width/N
  - grid: sources arranged in a grid (ceil(sqrt(N)) columns)
  - manual: each source specifies its own width/height/shift

Usage (standalone):
    # Single video (backward compat)
    python obs_bridge.py --video /path/to.mp4

    # Two videos side by side with text overlay
    python obs_bridge.py --video left.mp4 --video right.mp4 --text "SUCK IT"

    # Three videos in a grid
    python obs_bridge.py --video a.mp4 --video b.mp4 --video c.mp4 --layout grid

OBS obs-gstreamer pipeline:
    tcpclientsrc host=127.0.0.1 port=5000 ! tsdemux ! decodebin ! videoconvert ! video.

The bridge auto-restarts each video input when the file reaches EOS, so it
runs indefinitely until killed.
"""

from __future__ import annotations

import asyncio
import math
import os
import shlex
import shutil
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Allow running both as a module and as a standalone script
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from snowmix_client import SnowmixClient
else:
    from .snowmix_client import SnowmixClient


# ── Defaults ────────────────────────────────────────────────────────── #

SNOWMIX_BIN = os.environ.get("SNOWMIX_BIN", "/usr/local/bin/snowmix")
SNOWMIX_HOME = os.environ.get("SNOWMIX", "/home/rjodouin/Snowmix-0.5.2.2")
GST_LAUNCH = shutil.which("gst-launch-1.0") or "gst-launch-1.0"

# Sockets must be in the home directory for Flatpak OBS to access them.
# /tmp is NOT shared between the host and the Flatpak sandbox.
SOCKET_DIR = Path.home() / ".snowmix-sockets"
MIXER_SOCKET = str(SOCKET_DIR / "mixer1")

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FRAMERATE = "24/1"
DEFAULT_TCP_PORT = 5000
DEFAULT_BITRATE = 4000


# ── Dataclasses ─────────────────────────────────────────────────────── #

@dataclass
class VideoSource:
    """A single video file source for the mixer.

    width/height of 0 means auto-compute from the chosen layout.
    shift_x/shift_y are used in 'manual' layout or to override auto layout.
    """
    path: str
    shift_x: int = 0
    shift_y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class TextOverlay:
    """Text overlay with optional shadow.

    x/y in Snowmix text place are OFFSETS from the anchor point, not
    absolute coordinates.  The anchor (e.g. 's' = bottom-center) sets the
    base position; alignment (center/bottom) controls how text is drawn
    relative to that anchor.  See snowmix_util.cpp SetAnchor for anchor
    values: nw, ne, se, sw, n, w, s, e, c.
    """
    string: str = ""
    font: str = "FreeSans Bold 64"
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0
    shadow: bool = False
    shadow_r: float = 1.0
    shadow_g: float = 1.0
    shadow_b: float = 1.0
    shadow_a: float = 1.0
    shadow_dx: int = 2
    shadow_dy: int = 2
    anchor: str = "s"
    align_h: str = "center"   # left, center, right
    align_v: str = "bottom"   # top, middle, bottom


@dataclass
class BridgeConfig:
    """Configuration for the OBS TCP bridge.

    Sources is a list of VideoSource.  If empty but video_file is set
    (backward compat), a single full-canvas source is created.
    If text is None but text_string is set (backward compat), a basic
    TextOverlay is created.
    """
    sources: list[VideoSource] = field(default_factory=list)
    text: TextOverlay | None = None
    image_file: str = ""
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    framerate: str = DEFAULT_FRAMERATE
    tcp_port: int = DEFAULT_TCP_PORT
    bitrate: int = DEFAULT_BITRATE
    layout: str = "side_by_side"   # side_by_side, grid, manual
    mixer_socket: str = MIXER_SOCKET

    # Backward-compat fields
    video_file: str = ""
    text_string: str = ""

    def __post_init__(self):
        if not self.sources and self.video_file:
            self.sources = [VideoSource(path=self.video_file)]
        if self.text is None and self.text_string:
            self.text = TextOverlay(string=self.text_string, font="FreeSans 24")

    @property
    def feed_sockets(self) -> list[str]:
        """Socket paths for each feed (1-indexed)."""
        return [
            str(SOCKET_DIR / f"feed{i+1}-control-pipe")
            for i in range(len(self.sources))
        ]


@dataclass
class BridgeStatus:
    """Snapshot of bridge process state."""
    running: bool = False
    snowmix_pid: int | None = None
    input_pids: list[int] = field(default_factory=list)
    bridge_pid: int | None = None
    tcp_port: int | None = None
    mixer_socket: str = ""
    obs_pipeline: str = ""
    num_sources: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def input_pid(self) -> int | None:
        """Backward compat: first input PID."""
        return self.input_pids[0] if self.input_pids else None


# ── Layout computation ──────────────────────────────────────────────── #

def compute_layout(sources: list[VideoSource], canvas_w: int, canvas_h: int,
                   layout: str) -> None:
    """Fill in width/height/shift_x/shift_y for each source in-place.

    For 'side_by_side' and 'grid', any source with width=0 or height=0
    gets auto-computed.  For 'manual', all dimensions must be set already.
    """
    n = len(sources)
    if n == 0:
        return

    if layout == "manual":
        for s in sources:
            if s.width <= 0 or s.height <= 0:
                raise ValueError(
                    f"manual layout requires explicit width/height for "
                    f"source {s.path}"
                )
        return

    if layout == "side_by_side":
        sw = canvas_w // n
        sh = canvas_h
        for i, s in enumerate(sources):
            if s.width <= 0:
                s.width = sw
            if s.height <= 0:
                s.height = sh
            s.shift_x = i * sw
            s.shift_y = 0
        return

    if layout == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        sw = canvas_w // cols
        sh = canvas_h // rows
        for i, s in enumerate(sources):
            if s.width <= 0:
                s.width = sw
            if s.height <= 0:
                s.height = sh
            col = i % cols
            row = i // cols
            s.shift_x = col * sw
            s.shift_y = row * sh
        return

    raise ValueError(f"Unknown layout: {layout}")


# ── INI generation ──────────────────────────────────────────────────── #

def generate_ini(width: int, height: int, mixer_socket: str,
                 framerate: str = "24") -> str:
    """Generate a Snowmix INI file content for the given canvas dimensions."""
    return f"""\
# Auto-generated INI for OBS TCP bridge.
# maxplaces must come BEFORE system geometry (locks in feed limits).
system control port 9999

maxplaces strings 5000
maxplaces fonts 5000
maxplaces texts 5000
maxplaces images 5000
maxplaces imageplaces 5000
maxplaces video feeds 5000
maxplaces virtual feeds 5000
maxplaces audio feeds 20
maxplaces audio mixers 20
maxplaces audio sinks 20
maxplaces shapes 64
maxplaces shapeplaces 64

system geometry {width} {height} BGRA
system frame rate {framerate}
system socket {mixer_socket}

feed idle 0 1
feed alpha 0 1
stack 0

command create PreShow
  loop
command end
overlay pre PreShow
command create Show
  loop
command end
overlay finish Show
"""


# ── Bridge class ────────────────────────────────────────────────────── #

class SnowmixBridge:
    """Manages Snowmix + N video inputs + TCP bridge as a unit.

    Use as an async context manager or call start()/stop() directly.
    """

    def __init__(self, config: BridgeConfig | None = None):
        self.config = config or BridgeConfig()
        self._snowmix_proc: asyncio.subprocess.Process | None = None
        self._input_procs: list[asyncio.subprocess.Process] = []
        self._bridge_proc: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task | None = None
        self._client: SnowmixClient | None = None
        self._ini_temp: str | None = None
        self._status = BridgeStatus(
            mixer_socket=self.config.mixer_socket,
            tcp_port=self.config.tcp_port,
            obs_pipeline=self._obs_pipeline_str(),
            num_sources=len(self.config.sources),
        )

    def _obs_pipeline_str(self) -> str:
        return (
            f"tcpclientsrc host=127.0.0.1 port={self.config.tcp_port} "
            f"! tsdemux ! decodebin ! videoconvert ! video."
        )

    @property
    def status(self) -> BridgeStatus:
        s = self._status
        s.running = (
            self._snowmix_proc is not None
            and self._snowmix_proc.returncode is None
            and self._bridge_proc is not None
            and self._bridge_proc.returncode is None
        )
        s.snowmix_pid = self._snowmix_proc.pid if self._snowmix_proc else None
        s.input_pids = [p.pid for p in self._input_procs if p.returncode is None]
        s.bridge_pid = self._bridge_proc.pid if self._bridge_proc else None
        return s

    async def start(self) -> BridgeStatus:
        """Start Snowmix, video inputs, and TCP bridge. Returns status."""
        c = self.config

        # Compute layout for all sources
        compute_layout(c.sources, c.width, c.height, c.layout)

        await self._cleanup_existing()
        self._prepare_sockets()

        # 1. Generate INI and start Snowmix
        ini_content = generate_ini(c.width, c.height, c.mixer_socket,
                                   framerate=c.framerate.split("/")[0])
        ini_fd, ini_path = tempfile.mkstemp(suffix=".ini", prefix="snowmix-obs-")
        os.write(ini_fd, ini_content.encode())
        os.close(ini_fd)
        self._ini_temp = ini_path

        env = {**os.environ, "SNOWMIX": SNOWMIX_HOME}
        self._snowmix_proc = await asyncio.create_subprocess_exec(
            SNOWMIX_BIN, ini_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await asyncio.sleep(2)
        if self._snowmix_proc.returncode is not None:
            stderr_data = b""
            if self._snowmix_proc.stderr:
                stderr_data = await self._snowmix_proc.stderr.read()
            self._status.errors.append(f"Snowmix failed: {stderr_data.decode()[:300]}")
            return self.status

        # 2. Configure feeds + overlays via TCP client
        self._client = SnowmixClient(port=9999)
        await self._client.connect()

        feed_sockets = c.feed_sockets
        for i, src in enumerate(c.sources):
            feed_id = i + 1
            await self._client.send_command(f"feed add {feed_id} Feed{feed_id}")
            await self._client.feed_geometry(feed_id, src.width, src.height)
            await self._client.feed_socket(feed_id, feed_sockets[i])
            await self._client.feed_live(feed_id)
            await self._client.send_command(f"feed shift {feed_id} {src.shift_x} {src.shift_y}")

        # Build stack: background (0) + all feeds
        stack_args = "0 " + " ".join(str(i + 1) for i in range(len(c.sources)))
        await self._client.send_command(f"stack {stack_args}")

        # Image overlay (optional)
        if c.image_file:
            await self._client.image_load(1, c.image_file)
            await self._client.image_place(1, 1, 100, 50)

        # Text overlay (optional)
        if c.text and c.text.string:
            await self._configure_text(c.text)

        # 3. Build Show macro (overlay finish) for per-frame overlays
        await self._client.command_delete("Show")
        await self._client.command_create("Show")
        if c.image_file:
            await self._client.send_command("image overlay 1")
        if c.text and c.text.string:
            if c.text.shadow:
                await self._client.send_command("text overlay 1")   # shadow first
                await self._client.send_command("text overlay 2")   # main on top
            else:
                await self._client.send_command("text overlay 1")
        await self._client.send_command("loop")
        await self._client.command_end()
        await self._client.send_command("overlay finish Show")
        await self._client.close()

        # 4. Start video inputs (auto-restart on EOS)
        if c.sources:
            self._input_procs = await self._start_inputs()
            await asyncio.sleep(1)

        # 5. Start TCP bridge: shmsrc -> x264enc -> mpegtsmux -> tcpserversink
        self._bridge_proc = await self._start_bridge()
        await asyncio.sleep(2)
        if self._bridge_proc.returncode is not None:
            stderr_data = b""
            if self._bridge_proc.stderr:
                stderr_data = await self._bridge_proc.stderr.read()
            self._status.errors.append(f"Bridge failed: {stderr_data.decode()[:300]}")
            await self.stop()
            return self.status

        # 6. Start monitor task (restarts inputs on EOS, checks liveness)
        self._monitor_task = asyncio.create_task(self._monitor())

        return self.status

    async def _configure_text(self, t: TextOverlay) -> None:
        """Configure text string, font, and place(s) in Snowmix."""
        assert self._client is not None, "client must be connected"
        # CRITICAL: set string BEFORE text place, or place creation fails
        # with "Invalid number of parameters" (string must exist first).
        await self._client.send_command(f"text string 1 {t.string}")
        await self._client.send_command(f"text font 1 {t.font}")

        if t.shadow:
            # Place 1 = shadow (drawn first), Place 2 = main text (on top)
            # x/y are OFFSETS from the anchor point, not absolute coords.
            await self._client.text_place(
                place_id=1, text_id=1, font_id=1,
                x=t.shadow_dx, y=t.shadow_dy,
                r=t.shadow_r, g=t.shadow_g, b=t.shadow_b, a=t.shadow_a,
                anchor=t.anchor,
            )
            await self._client.text_place_align(1, t.align_h, t.align_v)

            await self._client.text_place(
                place_id=2, text_id=1, font_id=1,
                x=0, y=0,
                r=t.r, g=t.g, b=t.b, a=t.a,
                anchor=t.anchor,
            )
            await self._client.text_place_align(2, t.align_h, t.align_v)
        else:
            await self._client.text_place(
                place_id=1, text_id=1, font_id=1,
                x=0, y=0,
                r=t.r, g=t.g, b=t.b, a=t.a,
                anchor=t.anchor,
            )
            await self._client.text_place_align(1, t.align_h, t.align_v)

    async def stop(self) -> None:
        """Stop all processes."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        for proc in (self._bridge_proc, *self._input_procs, self._snowmix_proc):
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

        self._bridge_proc = None
        self._input_procs = []
        if self._snowmix_proc and self._snowmix_proc.stdin:
            self._snowmix_proc.stdin.close()
        self._snowmix_proc = None

        # Clean up temp INI
        if self._ini_temp and os.path.exists(self._ini_temp):
            os.remove(self._ini_temp)
            self._ini_temp = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()

    # ── Internal helpers ────────────────────────────────────────────── #

    async def _cleanup_existing(self):
        for cmd in ("snowmix", "gst-launch-1.0"):
            try:
                await asyncio.create_subprocess_exec(
                    "pkill", "-9", cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except Exception:
                pass
        await asyncio.sleep(1)

    def _prepare_sockets(self):
        SOCKET_DIR.mkdir(parents=True, exist_ok=True)
        sockets_to_clean = [self.config.mixer_socket] + self.config.feed_sockets
        for s in sockets_to_clean:
            if os.path.exists(s):
                os.remove(s)

    def _input_pipeline(self, video_path: str, feed_socket: str,
                        w: int, h: int) -> str:
        shm_size = w * h * 4 * 26
        return (
            f"filesrc location={video_path} "
            f"! decodebin name=decoder "
            f"! videoconvert "
            f"! videoscale "
            f"! video/x-raw,format=BGRA,width={w},height={h} "
            f"! shmsink socket-path={feed_socket} "
            f"shm-size={shm_size} wait-for-connection=0 sync=true"
        )

    async def _start_inputs(self) -> list[asyncio.subprocess.Process]:
        procs = []
        c = self.config
        for i, src in enumerate(c.sources):
            pipeline = self._input_pipeline(
                src.path, c.feed_sockets[i], src.width, src.height
            )
            proc = await asyncio.create_subprocess_exec(
                GST_LAUNCH, "-q", *shlex.split(pipeline),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            procs.append(proc)
        return procs

    async def _restart_input(self, index: int) -> None:
        """Restart a single input that reached EOS."""
        c = self.config
        src = c.sources[index]
        pipeline = self._input_pipeline(
            src.path, c.feed_sockets[index], src.width, src.height
        )
        proc = await asyncio.create_subprocess_exec(
            GST_LAUNCH, "-q", *shlex.split(pipeline),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._input_procs[index] = proc

    async def _start_bridge(self) -> asyncio.subprocess.Process:
        c = self.config
        pipeline = (
            f"shmsrc socket-path={c.mixer_socket} do-timestamp=true is-live=true "
            f"! video/x-raw,format=BGRA,width={c.width},height={c.height},framerate={c.framerate} "
            f"! queue leaky=0 "
            f"! videoconvert "
            f"! x264enc bitrate={c.bitrate} tune=zerolatency speed-preset=5 "
            f"! mpegtsmux "
            f"! tcpserversink host=127.0.0.1 port={c.tcp_port} sync=false"
        )
        return await asyncio.create_subprocess_exec(
            GST_LAUNCH, "-v", *shlex.split(pipeline),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def _monitor(self):
        """Restart video inputs on EOS; detect Snowmix/bridge death."""
        try:
            while True:
                await asyncio.sleep(5)
                # Check Snowmix
                if self._snowmix_proc and self._snowmix_proc.returncode is not None:
                    self._status.errors.append(
                        f"Snowmix exited (rc={self._snowmix_proc.returncode})"
                    )
                    break
                # Check bridge
                if self._bridge_proc and self._bridge_proc.returncode is not None:
                    self._status.errors.append(
                        f"Bridge exited (rc={self._bridge_proc.returncode})"
                    )
                    break
                # Restart inputs that died (video file reached EOS)
                for i, proc in enumerate(self._input_procs):
                    if proc and proc.returncode is not None:
                        print(f"Input {i+1} ended (EOS), restarting...")
                        await self._restart_input(i)
        except asyncio.CancelledError:
            pass


# ── CLI entry point ─────────────────────────────────────────────────── #

def _parse_args():
    import argparse

    p = argparse.ArgumentParser(
        description="OBS TCP Bridge for Snowmix (bypasses Flatpak /dev/shm sandbox)"
    )
    p.add_argument("--video", action="append", default=[],
                   help="Video file path (repeatable for multiple sources)")
    p.add_argument("--image", default="", help="PNG image overlay")
    p.add_argument("--text", default="", help="Text overlay string")
    p.add_argument("--text-font", default="FreeSans Bold 64",
                   help="Text font specification")
    p.add_argument("--text-color", default="1.0,1.0,1.0,1.0",
                   help="Text color R,G,B,A (0.0-1.0)")
    p.add_argument("--text-shadow", action="store_true",
                   help="Enable text shadow")
    p.add_argument("--text-shadow-color", default="1.0,1.0,1.0,1.0",
                   help="Shadow color R,G,B,A")
    p.add_argument("--text-anchor", default="s",
                   help="Text anchor: nw,n,ne,w,c,e,sw,s,se")
    p.add_argument("--text-align", default="center bottom",
                   help="Text alignment: 'center bottom', 'left top', etc")
    p.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    p.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    p.add_argument("--framerate", default=DEFAULT_FRAMERATE)
    p.add_argument("--port", type=int, default=DEFAULT_TCP_PORT,
                   help="TCP port for OBS")
    p.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    p.add_argument("--layout", default="side_by_side",
                   choices=["side_by_side", "grid", "manual"],
                   help="Layout mode for multiple sources")
    return p.parse_args()


def _parse_color(s: str) -> tuple[float, float, float, float]:
    parts = [float(x) for x in s.split(",")]
    if len(parts) == 3:
        parts.append(1.0)
    return tuple(parts)  # type: ignore


async def _cli():
    args = _parse_args()

    if not args.video:
        print("Error: at least one --video is required")
        return 1

    sources = [VideoSource(path=v) for v in args.video]

    text = None
    if args.text:
        tc = _parse_color(args.text_color)
        sc = _parse_color(args.text_shadow_color)
        align_parts = args.text_align.split()
        align_h = align_parts[0] if align_parts else "center"
        align_v = align_parts[1] if len(align_parts) > 1 else "bottom"
        text = TextOverlay(
            string=args.text,
            font=args.text_font,
            r=tc[0], g=tc[1], b=tc[2], a=tc[3],
            shadow=args.text_shadow,
            shadow_r=sc[0], shadow_g=sc[1], shadow_b=sc[2], shadow_a=sc[3],
            anchor=args.text_anchor,
            align_h=align_h,
            align_v=align_v,
        )

    config = BridgeConfig(
        sources=sources,
        text=text,
        image_file=args.image,
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        tcp_port=args.port,
        bitrate=args.bitrate,
        layout=args.layout,
    )
    bridge = SnowmixBridge(config)
    status = await bridge.start()
    if status.errors:
        print("Bridge failed to start:")
        for e in status.errors:
            print(f"  {e}")
        return 1

    print(f"Snowmix PID:  {status.snowmix_pid}")
    print(f"Bridge PID:   {status.bridge_pid}")
    print(f"TCP port:     {status.tcp_port}")
    print(f"Sources:      {status.num_sources} ({config.layout})")
    for i, src in enumerate(config.sources):
        print(f"  [{i+1}] {src.width}x{src.height} @ ({src.shift_x},{src.shift_y}) {src.path}")
    print(f"Mixer socket: {status.mixer_socket}")
    print()
    print("=" * 70)
    print("OBS obs-gstreamer pipeline (copy this):")
    print(f"  {status.obs_pipeline}")
    print("=" * 70)
    print()
    print("Toggle OBS source: deactivate, wait 2s, activate.")
    print("Bridge running until Ctrl-C...")

    # Wait until killed or a process dies
    try:
        while bridge.status.running:
            await asyncio.sleep(5)
        print("A process died, stopping...")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await bridge.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli()))
