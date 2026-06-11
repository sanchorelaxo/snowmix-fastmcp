from fastmcp import FastMCP
from snowmix_client import SnowmixClient

mcp = FastMCP("snowmix")

@mcp.tool()
async def snowmix_get_system_geometry() -> str:
    """Get the current system geometry of the Snowmix instance."""
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_system_geometry()
    finally:
        await client.close()

@mcp.tool()
async def snowmix_add_video_feed(feed_id: int, file_path: str, width: int = 1024, height: int = 576) -> str:
    """
    Add a new video feed to Snowmix.
    
    Args:
        feed_id: Unique integer ID for the feed.
        file_path: Path to the video file (MP4, etc.).
        width: Width of the feed geometry (default 1024).
        height: Height of the feed geometry (default 576).
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.add_video_feed(feed_id, file_path, width, height)
    finally:
        await client.close()

@mcp.tool()
async def snowmix_get_feed_info(feed_id: int) -> str:
    """
    Get information about a specific video feed.
    
    Args:
        feed_id: The integer ID of the feed to query.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_feed_info(feed_id)
    finally:
        await client.close()

if __name__ == "__main__":
    mcp.run()
