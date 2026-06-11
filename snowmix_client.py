import asyncio

class SnowmixClient:
    def __init__(self, host: str = '127.0.0.1', port: int = 9999):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        # Read the initial Snowmix version banner (just one line)
        try:
            banner = await asyncio.wait_for(self.reader.readline(), timeout=1.0)
            # Consume any remaining immediate output just in case
            # But don't use read(4096) as it might consume command responses!
        except asyncio.TimeoutError:
            pass

    async def send_command(self, command: str) -> str:
        if not self.writer or not self.reader:
            await self.connect()
        
        assert self.writer is not None
        assert self.reader is not None
        
        self.writer.write((command + '\n').encode('utf-8'))
        await self.writer.drain()
        
        lines = []
        try:
            while True:
                line = await asyncio.wait_for(self.reader.readline(), timeout=1.0)
                if not line:
                    break
                decoded = line.decode('utf-8', errors='ignore').strip()
                lines.append(decoded)
                # If we hit a standalone STAT: or MSG: or the response seems complete, break
                if decoded == 'STAT:' or decoded.startswith('MSG:') or (len(lines) > 1 and not decoded.startswith('STAT:')):
                    break
        except asyncio.TimeoutError:
            # Snowmix commands are often silent on success. 
            # If we timed out with no lines, it likely succeeded.
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

    async def add_video_feed(self, feed_id: int, file_path: str, width: int = 1024, height: int = 576) -> str:
        feed_name = file_path.split('/')[-1] or f"Feed_{feed_id}"
        res1 = await self.send_command(f'feed add {feed_id} "{feed_name}"')
        res2 = await self.send_command(f'feed geometry {feed_id} {width} {height}')
        return f"{res1}\n{res2}"

    async def get_feed_info(self, feed_id: int) -> str:
        return await self.send_command(f'feed info {feed_id}')

    async def get_system_geometry(self) -> str:
        return await self.send_command('system geometry')
