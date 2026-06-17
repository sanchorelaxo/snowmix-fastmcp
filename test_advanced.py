"""
Advanced tests for snowmix-fastmcp — MCP equivalents of expandedTest.ini lines 45-89.

Uses advancedTest.ini to start Snowmix, then exercises feed creation,
image loading/naming, text operations, and scene-like commands via the
Python client (MCP tool equivalents).

All operations here were originally TCL `eval` calls or include/library-based
commands in expandedTest.ini.  We re-implement them via the MCP client.
"""

import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio

from snowmix_client import SnowmixClient

# ------------------------------------------------------------------ #
#  Fixtures — advancedTest.ini
# ------------------------------------------------------------------ #

REPO_ROOT = Path(__file__).resolve().parent
INI_PATH = REPO_ROOT / "ini" / "advancedTest.ini"
SNOWMIX_BIN = os.environ.get("SNOWMIX_BIN", "/usr/local/bin/snowmix")
SNOWMIX_HOME = os.environ.get("SNOWMIX", "/home/rjodouin/Snowmix-0.5.2.2")

assert INI_PATH.exists(), f"Missing test ini: {INI_PATH}"
assert os.path.exists(SNOWMIX_BIN), f"Missing snowmix: {SNOWMIX_BIN}"

# Shared test image path
TEST_IMG = "/home/rjodouin/Downloads/hypno2_fx_DLs/hypno_Reductions by cinema.av/stills/title2.png"


@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    """Start Snowmix with advancedTest.ini for advanced tests."""
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

async def expect_ok(resp: str):
    """Assert response indicates success (silence or OK)."""
    assert resp == "OK" or not resp or resp.startswith("STAT:"), (
        f"Expected OK but got: {resp}"
    )


# ╔══════════════════════════════════════════════════════════════════╗
# ║  1. Image Loading & Naming                                        ║
# ╚══════════════════════════════════════════════════════════════════╝


class TestImageLoading:
    """Load images and assign names — MCP equivalent of:

        image load 1 ../images/CS/CS_TV_720p_3screen-up_background.png
        image name 1 CS Background Logo Right
    """

    async def test_image_load_basic(self, client: SnowmixClient):
        """Load a PNG image file."""
        resp = await client.image_load(1001, TEST_IMG)
        # image load is silent on success
        assert resp == "OK", f"image load failed: {resp}"

    async def test_image_name_assigns_label(self, client: SnowmixClient):
        """After loading, assign a human-readable name via image name."""
        await client.image_load(1002, TEST_IMG)
        resp = await client.image_name(1002, "Test_Background")
        assert resp == "OK", f"image name failed: {resp}"

    async def test_list_images_shows_count(self, client: SnowmixClient):
        """Listing images should show loaded image count > 0."""
        await client.image_load(1003, TEST_IMG)
        info = await client.list_images()
        assert info.get("used_load", 0) >= 1, f"No images loaded: {info}"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  2. Text Fonts & Placements                                       ║
# ╚══════════════════════════════════════════════════════════════════╝


class TestTextOverlays:
    """Create text overlays — MCP equivalent of:

        text font 4 Eurostile Bold 16
        text place 1 1 5 0 -10 1 1 1 1 se
        text align 1 left bottom
        text backgr 1 2000 2000 10 10 0 0 0 0.75
        text repeat move 1 -2 0 -3500 0
        text string 2 Snowmix Video Mixer
        text clipabs 2 0 500 334 200
    """

    async def test_text_font_sets_font(self, client: SnowmixClient):
        """Set font for a text overlay."""
        resp = await client.text_font(2001, "FreeSans 16")
        assert resp == "OK", f"text font failed: {resp}"

    async def test_text_place_advanced(self, client: SnowmixClient):
        """Create text string + place it with RGBA + anchor.

        Snowmix uses unsigned ints for x/y, so use positive values.
        font_id must match a previously set font.
        """
        await client.send_command("text string 2001 Advanced")
        await client.send_command("text font 2001 FreeSans 16")
        resp = await client.text_place(
            2001, 2001, 2001, 0, 710,
            1.0, 1.0, 1.0, 1.0, "se"
        )
        assert resp == "OK" or "STAT:" in resp

    async def test_text_place_align(self, client: SnowmixClient):
        """Set text alignment (text align, not text place align in 0.5.0+)."""
        await client.send_command("text string 2002 Aligned")
        await client.send_command("text font 2002 FreeSans 16")
        await client.text_place(2002, 2002, 2002, 0, 710)
        resp = await client.text_place_align(2002, "left", "bottom")
        assert resp == "OK", f"text align failed: {resp}"

    async def test_text_place_background(self, client: SnowmixClient):
        """Set text background (text backgr, not text place backgr in 0.5.0+)."""
        await client.send_command("text string 2003 BGTest")
        await client.send_command("text font 2003 FreeSans 16")
        await client.text_place(2003, 2003, 2003, 0, 710)
        resp = await client.text_place_background(
            2003, 2000, 2000, 10, 10, 0, 0, 0, 0.75
        )
        assert resp == "OK", f"text backgr failed: {resp}"

    async def test_text_place_clip(self, client: SnowmixClient):
        """Set text clip region (text clipabs, not text place clipabs in 0.5.0+)."""
        await client.send_command("text string 2004 ClipTest")
        await client.send_command("text font 2004 FreeSans 16")
        await client.text_place(2004, 2004, 2004, 0, 710)
        resp = await client.text_place_clip(2004, 0, 500, 334, 200)
        assert resp == "OK", f"text clipabs failed: {resp}"

    async def test_text_place_repeat_move(self, client: SnowmixClient):
        """Set text repeat move (text repeat move, not text place repeat move in 0.5.0+)."""
        await client.send_command("text string 2005 Scrolling")
        await client.send_command("text font 2005 FreeSans 16")
        await client.text_place(2005, 2005, 2005, 0, 710)
        resp = await client.text_place_repeat(2005, "move", -2, 0, -3500, 0)
        assert resp == "OK", f"text repeat move failed: {resp}"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  3. Feed Creation with Geometry                                   ║
# ╚══════════════════════════════════════════════════════════════════╝


class TestAdvancedFeeds:
    """Create feeds with specific geometry."""

    async def test_create_feed_with_geometry(self, client: SnowmixClient):
        """Create a feed, set geometry, verify."""
        await client.send_command("feed add 3001 Feed1")
        await client.send_command("feed geometry 3001 1280 720")
        info = await client.get_feed_info(3001)
        assert "STAT:" in info
        assert "3001" in info

    async def test_create_multiple_feeds(self, client: SnowmixClient):
        """Create multiple feeds (matching expandedTest's 3 feeds)."""
        for fid in (3011, 3012, 3013):
            await client.send_command(f"feed add {fid} Feed_{fid}")
            await client.send_command(f"feed geometry {fid} 1280 720")
        feeds = await client.list_feeds()
        ids = [f["id"] for f in feeds]
        for fid in (3011, 3012, 3013):
            assert fid in ids, f"Feed {fid} missing from list"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  4. Image Place & Overlay                                         ║
# ╚══════════════════════════════════════════════════════════════════╝


class TestImagePlacement:
    """Place images and configure overlays."""

    async def test_image_place_positioned(self, client: SnowmixClient):
        """Load an image and place it at a specific position."""
        await client.image_load(4001, TEST_IMG)
        resp = await client.image_place(4001, 4001, 100, 50)
        assert resp == "OK", f"image place failed: {resp}"

    async def test_image_overlay_without_pipeline(self, client: SnowmixClient):
        """Image overlay requires a running video pipeline (m_overlay != NULL).

        Without a pipeline, Snowmix returns 'Invalid parameters'.
        This is expected — we're testing the command path, not rendering.
        """
        await client.image_load(4011, TEST_IMG)
        await client.image_place(4011, 4011, 0, 0)
        resp = await client.image_overlay([4011])
        # Accept either OK (pipeline running) or error (no pipeline)
        assert resp == "OK" or "Invalid" in resp, f"Unexpected response: {resp}"


# ╔══════════════════════════════════════════════════════════════════╗
# ║  5. Command Chaining                                              ║
# ╚══════════════════════════════════════════════════════════════════╝


class TestCommandChaining:
    """Test creating and chaining custom commands."""

    async def test_command_list_shows_pre_defined(self, client: SnowmixClient):
        """PreShow and Show commands should exist from ini."""
        names = await client.command_list_all()
        names_lower = [n.lower() for n in names]
        assert any("preshow" in n for n in names_lower), (
            f"PreShow missing from: {names}"
        )
        assert any("show" in n for n in names_lower), (
            f"Show missing from: {names}"
        )
