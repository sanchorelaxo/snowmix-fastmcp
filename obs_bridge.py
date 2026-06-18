"""OBS TCP Bridge for Snowmix.

Provides a TCP bridge between Snowmix's shared-memory output socket and
Flatpak-sandboxed OBS Studio.  Flatpak's bwrap gives OBS a private /dev/shm
namespace, so GStreamer's shmsrc inside OBS cannot mmap the shared-memory
segments Snowmix creates on the host.  This bridge reads from Snowmix via
shmsrc on the host and re-serves the stream over TCP localhost, which the
Flatpak network namespace allows.

Architecture:
    Video file → GStreamer (decode → BGRA → shmsink) → Snowmix feed socket
                                                        |
                                              Snowmix mixing loop
                                              (runs Show macro per frame)
                                                        |
    OBS ← tcpclientsrc ← tsdemux ← decodebin ← tcpserversink ← x264enc ← shmsrc ← Snowmix mixer socket

Usage (standalone):
    python obs_bridge.py                          # defaults
    python obs_bridge.py --video /path/to.mp4     # custom video
    python obs_bridge.py --port 5001              # custom TCP port

OBS obs-gstreamer pipeline:
    tcpclientsrc host=127.0.0.1 port=5000 ! tsdemux ! decodebin ! videoconvert ! video.

The bridge auto-restarts the video input when the file reaches EOS, so it
runs indefinitely until killed.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import sys
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
INI_PATH = str(Path(__file__).resolve().parent / "ini" / "obs.ini")
GST_LAUNCH = shutil.which("gst-launch-1.0") or "gst-launch-1.0"

# Sockets must be in the home directory for Flatpak OBS to access them.
# /tmp is NOT shared between the host and the Flatpak sandbox.
SOCKET_DIR = Path.home() / ".snowmix-sockets"
MIXER_SOCKET = str(SOCKET_DIR / "mixer1")
FEED_SOCKET = str(SOCKET_DIR / "feed1-control-pipe")

DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FRAMERATE = "24/1"
DEFAULT_TCP_PORT = 5000
DEFAULT_BITRATE = 4000


@dataclass
class BridgeConfig:
    """Configuration for the OBS TCP bridge."""

    video_file: str = ""
    image_file: str = ""
    text_string: str = "Snowmix"
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    framerate: str = DEFAULT_FRAMERATE
    tcp_port: int = DEFAULT_TCP_PORT
    bitrate: int = DEFAULT_BITRATE
    ini_path: str = INI_PATH
    mixer_socket: str = MIXER_SOCKET
    feed_socket: str = FEED_SOCKET


@dataclass
class BridgeStatus:
    """Snapshot of bridge process state."""

    running: bool = False
    snowmix_pid: int | None = None
    input_pid: int | None = None
    bridge_pid: int | None = None
    tcp_port: int | None = None
    mixer_socket: str = ""
    obs_pipeline: str = ""
    errors: list[str] = field(default_factory=list)


class SnowmixBridge:
    """Manages Snowmix + video input + TCP bridge as a unit.

    Use as an async context manager or call start()/stop() directly.
    """

    def __init__(self, config: BridgeConfig | None = None):
        self.config = config or BridgeConfig()
        self._snowmix_proc: asyncio.subprocess.Process | None = None
        self._input_proc: asyncio.subprocess.Process | None = None
        self._bridge_proc: asyncio.subprocess.Process | None = None
        self._monitor_task: asyncio.Task | None = None
        self._client: SnowmixClient | None = None
        self._status = BridgeStatus(
            mixer_socket=self.config.mixer_socket,
            tcp_port=self.config.tcp_port,
            obs_pipeline=self._obs_pipeline_str(),
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
        s.input_pid = self._input_proc.pid if self._input_proc else None
        s.bridge_pid = self._bridge_proc.pid if self._bridge_proc else None
        return s

    async def start(self) -> BridgeStatus:
        """Start Snowmix, video input, and TCP bridge. Returns status."""
        await self._cleanup_existing()
        self._prepare_sockets()

        # 1. Start Snowmix
        env = {**os.environ, "SNOWMIX": SNOWMIX_HOME}
        self._snowmix_proc = await asyncio.create_subprocess_exec(
            SNOWMIX_BIN, self.config.ini_path,
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

        # 2. Configure feed + overlays via TCP client
        self._client = SnowmixClient(port=9999)
        await self._client.connect()
        c = self.config
        await self._client.send_command(f"feed add 1 Feed1")
        await self._client.feed_geometry(1, c.width, c.height)
        await self._client.feed_socket(1, c.feed_socket)
        await self._client.feed_live(1)
        await self._client.stack(0, 1)

        if c.image_file:
            await self._client.image_load(1, c.image_file)
            await self._client.image_place(1, 1, 100, 50)
        if c.text_string:
            await self._client.send_command(f"text string 1 {c.text_string}")
            await self._client.send_command("text font 1 FreeSans 24")
            await self._client.text_place(1, 1, 1, 50, 50)

        # 3. Build Show macro (overlay finish) for per-frame overlays
        await self._client.command_delete("Show")
        await self._client.command_create("Show")
        if c.image_file:
            await self._client.send_command("image overlay 1")
        if c.text_string:
            await self._client.send_command("text overlay 1")
        await self._client.send_command("loop")
        await self._client.command_end()
        await self._client.send_command("overlay finish Show")
        await self._client.close()

        # 4. Start video input (auto-restarts on EOS)
        if c.video_file:
            self._input_proc = await self._start_input()
            await asyncio.sleep(1)

        # 5. Start TCP bridge: shmsrc → x264enc → mpegtsmux → tcpserversink
        self._bridge_proc = await self._start_bridge()
        await asyncio.sleep(2)
        if self._bridge_proc.returncode is not None:
            stderr_data = b""
            if self._bridge_proc.stderr:
                stderr_data = await self._bridge_proc.stderr.read()
            self._status.errors.append(f"Bridge failed: {stderr_data.decode()[:300]}")
            await self.stop()
            return self.status

        # 6. Start monitor task (restarts input on EOS, checks liveness)
        self._monitor_task = asyncio.create_task(self._monitor())

        return self.status

    async def stop(self) -> None:
        """Stop all processes."""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        for proc in (self._bridge_proc, self._input_proc, self._snowmix_proc):
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()

        self._bridge_proc = None
        self._input_proc = None
        if self._snowmix_proc and self._snowmix_proc.stdin:
            self._snowmix_proc.stdin.close()
        self._snowmix_proc = None

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
        for s in (self.config.mixer_socket, self.config.feed_socket):
            if os.path.exists(s):
                os.remove(s)

    async def _start_input(self) -> asyncio.subprocess.Process:
        c = self.config
        shm_size = c.width * c.height * 4 * 26
        pipeline = (
            f"filesrc location={c.video_file} "
            f"! decodebin name=decoder "
            f"! videoconvert "
            f"! videoscale "
            f"! video/x-raw,format=BGRA,width={c.width},height={c.height} "
            f"! shmsink socket-path={c.feed_socket} "
            f"shm-size={shm_size} wait-for-connection=0 sync=true"
        )
        return await asyncio.create_subprocess_exec(
            GST_LAUNCH, "-q", *shlex.split(pipeline),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

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
        """Restart video input on EOS; detect Snowmix/bridge death."""
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
                # Restart input if it died (video file reached EOS)
                if (
                    self._input_proc
                    and self._input_proc.returncode is not None
                    and self.config.video_file
                ):
                    self._input_proc = await self._start_input()
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass


# ── CLI entry point ─────────────────────────────────────────────────── #

def _parse_args():
    import argparse

    p = argparse.ArgumentParser(
        description="OBS TCP Bridge for Snowmix (bypasses Flatpak /dev/shm sandbox)"
    )
    p.add_argument("--video", default="", help="Video file to loop as feed input")
    p.add_argument("--image", default="", help="PNG image overlay")
    p.add_argument("--text", default="Snowmix", help="Text overlay string")
    p.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    p.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    p.add_argument("--framerate", default=DEFAULT_FRAMERATE)
    p.add_argument("--port", type=int, default=DEFAULT_TCP_PORT, help="TCP port for OBS")
    p.add_argument("--bitrate", type=int, default=DEFAULT_BITRATE)
    p.add_argument("--ini", default=INI_PATH, help="Snowmix INI file")
    return p.parse_args()


async def _cli():
    args = _parse_args()
    config = BridgeConfig(
        video_file=args.video,
        image_file=args.image,
        text_string=args.text,
        width=args.width,
        height=args.height,
        framerate=args.framerate,
        tcp_port=args.port,
        bitrate=args.bitrate,
        ini_path=args.ini,
    )
    bridge = SnowmixBridge(config)
    status = await bridge.start()
    if status.errors:
        print("Bridge failed to start:")
        for e in status.errors:
            print(f"  {e}")
        return 1

    print(f"Snowmix PID: {status.snowmix_pid}")
    print(f"Input PID:   {status.input_pid}")
    print(f"Bridge PID:  {status.bridge_pid}")
    print(f"TCP port:    {status.tcp_port}")
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
