"""
Tests for snowmix-fastmcp client, ported from node-snowmix test suite.

Adapted for Snowmix 0.5.2.2 syntax differences:
  - feed names: ``feed add <id> <name>`` (NO quotes around name)
  - version: captured from connect banner (no ``version`` command)
  - vfeed add: ``vfeed add <id> <name>``, IDs in 0..31
  - vfeed source: ``vfeed source feed <vfeed_id> <feed_id>``
  - audio, text, image commands use their subcommand syntax
"""

import asyncio
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import pytest
import pytest_asyncio

from snowmix_client import SnowmixClient

# ------------------------------------------------------------------ #
#  Fixtures
# ------------------------------------------------------------------ #

REPO_ROOT = Path(__file__).resolve().parent
INI_PATH = REPO_ROOT / "ini" / "test.ini"
# Try to find the Snowmix binary
SNOWMIX_BIN = os.environ.get(
    "SNOWMIX_BIN",
    "/usr/local/bin/snowmix",
)
assert INI_PATH.exists(), f"Missing test ini: {INI_PATH}"
assert os.path.exists(SNOWMIX_BIN), f"Missing snowmix: {SNOWMIX_BIN}"


@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    """Start a single snowmix instance for the module, clean up after."""
    proc = await asyncio.create_subprocess_exec(
        SNOWMIX_BIN,
        str(INI_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await asyncio.sleep(2)  # Allow time to bind

    yield proc

    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


@pytest_asyncio.fixture
async def client(snowmix_process):  # noqa: ARG001 (depends on module fixture)
    """Return a fresh connected client per test."""
    c = SnowmixClient(host="127.0.0.1", port=9999)
    await c.connect()
    yield c
    await c.close()


# ------------------------------------------------------------------ #
#  Helper: wait for OK or silence after mutating commands
# ------------------------------------------------------------------ #

async def expect_ok(resp: str):
    """Assert the response indicates success (silence or OK)."""
    assert resp == "OK" or not resp or resp.startswith("STAT:"), (
        f"Expected OK but got: {resp}"
    )


# ================================================================== #
#  1. System Geometry
# ================================================================== #


class TestSystemGeometry:
    async def test_system_geometry(self, client: SnowmixClient):
        geom = await client.get_system_geometry()
        assert geom == "1024x576 BGRA", f"Unexpected geometry: {geom}"


# ================================================================== #
#  2. Version (from banner)
# ================================================================== #


class TestVersion:
    async def test_version_from_banner(self, client: SnowmixClient):
        ver = await client.get_version()
        assert "Snowmix version" in ver, f"Unexpected version: {ver}"
        assert "0.5.2.2" in ver, f"Wrong version: {ver}"


# ================================================================== #
#  3. Video Feeds
# ================================================================== #


class TestVideoFeeds:
    async def test_initially_has_internal_feed(self, client: SnowmixClient):
        """Default snowmix has feed 0 'Internal'."""
        feeds = await client.list_feeds()
        ids = [f["id"] for f in feeds]
        assert 0 in ids, "Default feed missing"
        feed0 = next(f for f in feeds if f["id"] == 0)
        assert feed0["name"] == "Internal"

    async def test_add_new_feed(self, client: SnowmixClient):
        """Create a feed with a bare name."""
        fid = await client.create_feed("test-feed", feed_id=2)
        assert fid == 2

    async def test_list_shows_added_feed(self, client: SnowmixClient):
        feeds = await client.list_feeds()
        ids = [f["id"] for f in feeds]
        assert 2 in ids
        f2 = next(f for f in feeds if f["id"] == 2)
        # feed 2 may have been renamed by a prior test; just check it's present
        assert isinstance(f2["name"], str) and len(f2["name"]) > 0

    async def test_update_feed_name(self, client: SnowmixClient):
        """Re-adding same ID changes the name."""
        await client.update_feed_name(2, "renamed-feed")
        feeds = await client.list_feeds()
        f2 = next(f for f in feeds if f["id"] == 2)
        assert f2["name"] == "renamed-feed"

    async def test_get_feed_info(self, client: SnowmixClient):
        """feed info returns STAT lines."""
        info = await client.get_feed_info(0)
        assert "STAT:" in info, f"Expected STAT: lines, got: {info}"
        assert "feed 0" in info or "Feed" in info

    async def test_feed_auto_id(self, client: SnowmixClient):
        """Auto-assign ID (max existing + 1)."""
        fid = await client.create_feed("auto-feed")
        assert isinstance(fid, int)
        assert fid >= 3


# ================================================================== #
#  4. Virtual Feeds
# ================================================================== #


class TestVirtualFeeds:
    async def test_create_vfeed(self, client: SnowmixClient):
        """Create a virtual feed (IDs 0..31)."""
        await expect_ok(await client.create_vfeed(1, "vtest1"))

    async def test_vfeed_list_includes_new(self, client: SnowmixClient):
        """vfeed (bare) lists vfeeds."""
        vfeeds = await client.list_vfeeds()
        ids = [v["id"] for v in vfeeds]
        assert 1 in ids, f"vfeed 1 not in list: {vfeeds}"
        vf = next(v for v in vfeeds if v["id"] == 1)
        assert vf["name"] == "vtest1"

    async def test_vfeed_source(self, client: SnowmixClient):
        """Route real feed 0 into vfeed 1."""
        await expect_ok(await client.vfeed_source(1, 0))

    async def test_vfeed_geometry(self, client: SnowmixClient):
        """Set vfeed geometry."""
        resp = await client.vfeed_geometry(1, 640, 480)


# ================================================================== #
#  5. Audio Feeds
# ================================================================== #


class TestAudioFeeds:
    async def test_create_audio_feed(self, client: SnowmixClient):
        await expect_ok(await client.create_audio_feed(2, "audio-feed-2"))

    async def test_audio_feed_channels(self, client: SnowmixClient):
        await expect_ok(await client.audio_feed_channels(2, 2))

    async def test_audio_feed_rate(self, client: SnowmixClient):
        await expect_ok(await client.audio_feed_rate(2, 48000))

    async def test_audio_feed_format(self, client: SnowmixClient):
        await expect_ok(await client.audio_feed_format(2, 16, "signed"))

    async def test_list_audio_feeds(self, client: SnowmixClient):
        feeds = await client.list_audio_feeds()
        assert isinstance(feeds, list)
        assert len(feeds) >= 1
        ids = [f["id"] for f in feeds]
        assert 2 in ids, f"Audio feed 2 missing: {feeds}"


# ================================================================== #
#  6. Audio Mixers
# ================================================================== #


class TestAudioMixers:
    async def test_create_audio_mixer(self, client: SnowmixClient):
        await expect_ok(await client.create_audio_mixer(1, "mixer1"))

    async def test_audio_mixer_add_feed(self, client: SnowmixClient):
        # Mixer default rate is 0 — must match feed rate (48000)
        await client.send_command("audio mixer rate 1 48000")
        await client.send_command("audio mixer channels 1 2")
        await expect_ok(await client.audio_mixer_add_feed(1, 2))

    async def test_list_audio_mixers(self, client: SnowmixClient):
        mixers = await client.list_audio_mixers()
        assert isinstance(mixers, list)
        assert len(mixers) >= 1
        ids = [m["id"] for m in mixers]
        assert 1 in ids

    async def test_get_audio_mixer_info(self, client: SnowmixClient):
        info = await client.get_audio_mixer_info(1)
        assert info


# ================================================================== #
#  7. Audio Sinks
# ================================================================== #


class TestAudioSinks:
    async def test_create_audio_sink(self, client: SnowmixClient):
        await expect_ok(await client.create_audio_sink(1, "sink1"))

    async def test_audio_sink_add_mixer(self, client: SnowmixClient):
        # Sink default rate is 0 — must match mixer rate (48000)
        await client.send_command("audio sink rate 1 48000")
        await client.send_command("audio sink channels 1 2")
        await expect_ok(await client.audio_sink_add_mixer(1, 1))

    async def test_list_audio_sinks(self, client: SnowmixClient):
        sinks = await client.list_audio_sinks()
        assert isinstance(sinks, list)
        assert len(sinks) >= 1
        ids = [s["id"] for s in sinks]
        assert 1 in ids


# ================================================================== #
#  8. Custom Commands (Scripts)
# ================================================================== #


class TestCommands:
    async def test_command_create_and_list(self, client: SnowmixClient):
        """Create a command with a line, end it, then list."""
        await expect_ok(await client.command_create("testcmd"))
        await expect_ok(await client.command_push("testcmd", "next 10"))
        await expect_ok(await client.command_end())
        names = await client.command_list_all()
        names_lower = [n.lower() for n in names]
        assert any("testcmd" in n for n in names_lower), (
            f"testcmd not found in: {names}"
        )
