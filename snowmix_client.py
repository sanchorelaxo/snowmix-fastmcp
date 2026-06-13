import asyncio
import re
from typing import Any


class SnowmixClient:
    def __init__(self, host: str = '127.0.0.1', port: int = 9999):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._version: str | None = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        try:
            banner = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            decoded = banner.decode('utf-8', errors='ignore').strip()
            # Banner: "Snowmix version 0.5.2.2."
            self._version = decoded
        except asyncio.TimeoutError:
            pass

    async def send_command(self, command: str) -> str:
        """Send a command and return all response lines separated by newline.

        Snowmix responses are STAT: or MSG: lines.  Silent success returns no
        data (timeout → "OK").
        """
        if not self.writer or not self.reader:
            await self.connect()

        assert self.writer is not None
        assert self.reader is not None

        self.writer.write((command + '\n').encode('utf-8'))
        await self.writer.drain()

        lines: list[str] = []
        try:
            while True:
                line = await asyncio.wait_for(self.reader.readline(), timeout=1.0)
                if not line:
                    break
                decoded = line.decode('utf-8', errors='ignore').strip()
                if decoded:
                    lines.append(decoded)
                # STAT: / MSG: lines — wait a short moment for more data
                await asyncio.sleep(0.05)
        except asyncio.TimeoutError:
            if not lines:
                return "OK"

        return '\n'.join(lines).strip()

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None

    # ------------------------------------------------------------------ #
    #  System / Version
    # ------------------------------------------------------------------ #

    async def get_system_geometry(self) -> str:
        """Returns e.g. '1024x576 BGRA'."""
        raw = await self.send_command('system geometry')
        # "STAT:  system geometry = 1024x576 BGRA"
        m = re.search(r'=\s*(.+)', raw)
        return m.group(1).strip() if m else raw

    async def get_version(self) -> str:
        """Return version string captured from banner on connect."""
        if self._version:
            return self._version
        # Fallback — reconnect to get banner
        await self.connect()
        return self._version or "unknown"

    # ------------------------------------------------------------------ #
    #  Video Feeds
    # ------------------------------------------------------------------ #

    async def create_feed(self, name: str, feed_id: int | None = None) -> int:
        """Create a video feed. Returns the feed ID.

        Syntax: feed add <id> <name>  — name is bare text (no quotes).
        """
        if feed_id is not None:
            await self.send_command(f'feed add {feed_id} {name}')
            return feed_id
        existing = await self.list_feeds()
        ids = [f['id'] for f in existing]
        next_id = max(ids) + 1 if ids else 1
        await self.send_command(f'feed add {next_id} {name}')
        return next_id

    async def list_feeds(self) -> list[dict[str, Any]]:
        """Parse feed list response.

        Snowmix output::
          STAT: Feed ID 0  Name: Internal
          STAT: Feed ID 1  Name: test-name
          STAT:
        """
        raw = await self.send_command('feed list')
        feeds: list[dict[str, Any]] = []
        for line in raw.splitlines():
            # "Feed ID N  Name: <value>"
            m = re.match(r'STAT:\s*Feed ID (\d+)\s+Name:\s*(.*)', line)
            if m:
                name = m.group(2).strip()
                feeds.append({'id': int(m.group(1)), 'name': name})
        return feeds

    async def get_feed_info(self, feed_id: int) -> str:
        """Feed info response has multiple STAT: lines.

        Final line includes the name in angle brackets:
          STAT: feed 0 : STALLED ... <Internal>
        """
        return await self.send_command(f'feed info {feed_id}')

    async def update_feed_name(self, feed_id: int, name: str) -> str:
        "Return OK on success, or error message."
        return await self.send_command(f'feed name {feed_id} {name}')

    async def add_video_feed(self, feed_id: int, file_path: str,
                             width: int = 1024, height: int = 576) -> str:
        feed_name = file_path.split('/')[-1] or f'Feed_{feed_id}'
        r1 = await self.create_feed(feed_name, feed_id=feed_id)
        r2 = await self.send_command(f'feed geometry {feed_id} {width} {height}')
        return f'OK\n{r2}'

    # ------------------------------------------------------------------ #
    #  Virtual Feeds
    # ------------------------------------------------------------------ #

    async def create_vfeed(self, vfeed_id: int, name: str) -> str:
        """Create a virtual feed. IDs in 0..31 range.

        Syntax: vfeed add <id> <name>
        """
        return await self.send_command(f'vfeed add {vfeed_id} {name}')

    async def vfeed_source(self, vfeed_id: int, feed_id: int) -> str:
        """Route a real feed into a virtual feed.

        Syntax: vfeed source feed <vfeed_id> <feed_id>
        """
        return await self.send_command(f'vfeed source feed {vfeed_id} {feed_id}')

    async def vfeed_geometry(self, vfeed_id: int, width: int, height: int) -> str:
        return await self.send_command(f'vfeed geometry {vfeed_id} {width} {height}')

    async def list_vfeeds(self) -> list[dict[str, Any]]:
        """List virtual feeds.

        BARE 'vfeed' lists vfeeds:
          STAT: vfeed  1 : <vtest1>
          STAT: vfeed  2 : <vtest2>
          STAT:
        """
        raw = await self.send_command('vfeed add')
        vfeeds: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = re.match(r'STAT:\s*vfeed\s+(\d+)\s*:\s*<(.*)>', line)
            if m:
                vfeeds.append({'id': int(m.group(1)), 'name': m.group(2)})
        return vfeeds

    async def delete_vfeed(self, vfeed_id: int) -> str:
        """Delete a vfeed by issuing 'vfeed add <id>' with no name."""
        return await self.send_command(f'vfeed {vfeed_id}')

    # ------------------------------------------------------------------ #
    #  Audio Feeds
    # ------------------------------------------------------------------ #

    async def create_audio_feed(self, audio_feed_id: int, name: str) -> str:
        """Create an audio feed. IDs must be < MAX_AUDIO_FEEDS (20).

        Syntax: audio feed add <id> <name>
        """
        return await self.send_command(f'audio feed add {audio_feed_id} {name}')

    async def list_audio_feeds(self) -> list[dict[str, Any]]:
        """List audio feeds.

        BARE 'audio feed add' (no args) lists feeds:
          STAT: audio feed 1 <name>
        """
        raw = await self.send_command('audio feed add')
        feeds: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = re.match(r'STAT:\s*audio feed (\d+)\s+<(.*)>', line)
            if m:
                feeds.append({'id': int(m.group(1)), 'name': m.group(2)})
        return feeds

    async def audio_feed_channels(self, feed_id: int, channels: int) -> str:
        return await self.send_command(f'audio feed channels {feed_id} {channels}')

    async def audio_feed_rate(self, feed_id: int, rate: int) -> str:
        return await self.send_command(f'audio feed rate {feed_id} {rate}')

    async def audio_feed_format(self, feed_id: int, bits: int, signedness: str) -> str:
        return await self.send_command(f'audio feed format {feed_id} {bits} {signedness}')

    async def get_audio_feed_info(self, audio_feed_id: int) -> str:
        return await self.send_command(f'audio feed info {audio_feed_id}')

    async def delete_audio_feed(self, audio_feed_id: int) -> str:
        """Delete by 'audio feed add <id>' with no name."""
        return await self.send_command(f'audio feed add {audio_feed_id}')

    # ------------------------------------------------------------------ #
    #  Audio Mixers
    # ------------------------------------------------------------------ #

    async def create_audio_mixer(self, mixer_id: int, name: str) -> str:
        return await self.send_command(f'audio mixer add {mixer_id} {name}')

    async def list_audio_mixers(self) -> list[dict[str, Any]]:
        raw = await self.send_command('audio mixer add')
        mixers: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = re.match(r'STAT:\s*audio mixer (\d+)\s+<(.*)>', line)
            if m:
                mixers.append({'id': int(m.group(1)), 'name': m.group(2)})
        return mixers

    async def audio_mixer_add_feed(self, mixer_id: int, feed_id: int) -> str:
        """Syntax: audio mixer source feed <mixer_id> <source_feed_id>"""
        return await self.send_command(f'audio mixer source feed {mixer_id} {feed_id}')

    async def audio_mixer_start(self, mixer_id: int) -> str:
        return await self.send_command(f'audio mixer start {mixer_id}')

    async def get_audio_mixer_info(self, mixer_id: int) -> str:
        return await self.send_command(f'audio mixer info {mixer_id}')

    async def delete_audio_mixer(self, mixer_id: int) -> str:
        return await self.send_command(f'audio mixer add {mixer_id}')

    # ------------------------------------------------------------------ #
    #  Audio Sinks
    # ------------------------------------------------------------------ #

    async def create_audio_sink(self, sink_id: int, name: str) -> str:
        return await self.send_command(f'audio sink add {sink_id} {name}')

    async def list_audio_sinks(self) -> list[dict[str, Any]]:
        raw = await self.send_command('audio sink add')
        sinks: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = re.match(r'STAT:\s*audio sink (\d+)\s+<(.*)>', line)
            if m:
                sinks.append({'id': int(m.group(1)), 'name': m.group(2)})
        return sinks

    async def audio_sink_add_mixer(self, sink_id: int, mixer_id: int) -> str:
        """Syntax: audio sink source mixer <sink_id> <mixer_id>"""
        return await self.send_command(f'audio sink source mixer {sink_id} {mixer_id}')

    async def audio_sink_start(self, sink_id: int) -> str:
        return await self.send_command(f'audio sink start {sink_id}')

    async def get_audio_sink_info(self, sink_id: int) -> str:
        return await self.send_command(f'audio sink info {sink_id}')

    async def delete_audio_sink(self, sink_id: int) -> str:
        return await self.send_command(f'audio sink add {sink_id}')

    # ------------------------------------------------------------------ #
    #  Text Overlays
    # ------------------------------------------------------------------ #

    async def create_text(self, text_id: int, string: str, font_id: int = 0) -> str:
        """Create a text string."""
        cmds = [
            f'text string {text_id} {string}',
            f'text font {text_id} {font_id}',
        ]
        results = [await self.send_command(c) for c in cmds]
        return '\n'.join(results)

    async def text_place(self, place_id: int, text_id: int, font_id: int,
                         x: int, y: int, r: float = 1.0, g: float = 1.0,
                         b: float = 1.0, a: float = 1.0, anchor: str = 'nw') -> str:
        return await self.send_command(
            f'text place {place_id} {text_id} {font_id} {x} {y} {r} {g} {b} {a} {anchor}',
        )

    async def text_show(self, text_id: int) -> str:
        return await self.send_command(f'text show {text_id}')

    async def text_hide(self, text_id: int) -> str:
        return await self.send_command(f'text hide {text_id}')

    async def list_texts(self) -> list[dict[str, Any]]:
        raw = await self.send_command('text list')
        # TODO: parse actual format once verified against running Snowmix
        return [{'id': int(m.group(1))}
                for line in raw.splitlines()
                if (m := re.search(r'text\s+(\d+)', line))]

    # ------------------------------------------------------------------ #
    #  Images & Image Places
    # ------------------------------------------------------------------ #

    async def image_load(self, image_id: int, file_path: str) -> str:
        return await self.send_command(f'image load {image_id} {file_path}')

    async def image_place(self, place_id: int, image_id: int,
                          x: int = 0, y: int = 0) -> str:
        return await self.send_command(f'image place {place_id} {image_id} {x} {y}')

    async def image_overlay(self, place_ids: list[int]) -> str:
        return await self.send_command('image overlay ' + ' '.join(str(p) for p in place_ids))

    async def image_hide(self, image_id: int) -> str:
        return await self.send_command(f'image hide {image_id}')

    async def list_images(self) -> list[dict[str, Any]]:
        raw = await self.send_command('image list')
        images: list[dict[str, Any]] = []
        for line in raw.splitlines():
            m = re.search(r'image\s+(\d+)\s*=\s*"(.+)"', line)
            if m:
                images.append({'id': int(m.group(1)), 'filename': m.group(2)})
        return images

    async def get_image_info(self, image_id: int) -> str:
        return await self.send_command(f'image info {image_id}')

    async def delete_image(self, image_id: int) -> str:
        return await self.send_command(f'image delete {image_id}')

    # ------------------------------------------------------------------ #
    #  Custom Commands (scripts)
    # ------------------------------------------------------------------ #

    async def command_create(self, name: str) -> str:
        return await self.send_command(f'command create {name}')

    async def command_push(self, name: str, line: str) -> str:
        """Push a line onto a custom command.

        Syntax: command push <name> <line>
        """
        return await self.send_command(f'command push {name} {line}')

    async def command_end(self) -> str:
        return await self.send_command('command end')

    async def command_list_all(self) -> list[str]:
        raw = await self.send_command('command list')
        if raw in ('OK', ''):
            return []
        names: list[str] = []
        for line in raw.splitlines():
            # command list returns MSG: lines, not STAT:
            cleaned = re.sub(r'^(?:STAT|MSG):\s*', '', line).strip()
            if cleaned:
                names.append(cleaned)
        return names

    async def command_delete(self, name: str) -> str:
        return await self.send_command(f'command delete {name}')
