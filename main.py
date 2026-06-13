from fastmcp import FastMCP
from snowmix_client import SnowmixClient

mcp = FastMCP("snowmix")


# ------------------------------------------------------------------ #
#  System & Info
# ------------------------------------------------------------------ #

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
async def snowmix_get_version() -> str:
    """Get the Snowmix version string (captured from connection banner)."""
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_version()
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Video Feeds
# ------------------------------------------------------------------ #

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


@mcp.tool()
async def snowmix_list_feeds() -> str:
    """List all video feeds with their names and IDs."""
    client = SnowmixClient()
    try:
        await client.connect()
        feeds = await client.list_feeds()
        return str(feeds)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_update_feed_name(feed_id: int, name: str) -> str:
    """
    Rename an existing video feed.

    Args:
        feed_id: The integer ID of the feed to rename.
        name: The new name for the feed.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.update_feed_name(feed_id, name)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_create_feed(name: str, feed_id: int = 0) -> str:
    """
    Create a new video feed (by name; feed_id 0 = auto-assign).

    Args:
        name: Name for the feed.
        feed_id: Optional integer ID (0 for auto-assign).
    """
    client = SnowmixClient()
    try:
        await client.connect()
        assigned = await client.create_feed(name, feed_id if feed_id else None)
        return str(assigned)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Virtual Feeds
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_create_vfeed(vfeed_id: int, name: str) -> str:
    """
    Create a new virtual feed.

    Args:
        vfeed_id: Integer ID for the virtual feed (0-31).
        name: Name for the virtual feed.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.create_vfeed(vfeed_id, name)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_vfeeds() -> str:
    """List all virtual feeds with their names and IDs."""
    client = SnowmixClient()
    try:
        await client.connect()
        vfeeds = await client.list_vfeeds()
        return str(vfeeds)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_vfeed_source(vfeed_id: int, feed_id: int) -> str:
    """
    Route a real video feed into a virtual feed.

    Args:
        vfeed_id: The virtual feed ID.
        feed_id: The source video feed ID.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.vfeed_source(vfeed_id, feed_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_delete_vfeed(vfeed_id: int) -> str:
    """
    Delete a virtual feed.

    Args:
        vfeed_id: The virtual feed ID to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.delete_vfeed(vfeed_id)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Audio Feeds
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_create_audio_feed(audio_feed_id: int, name: str) -> str:
    """
    Create a new audio feed.

    Args:
        audio_feed_id: Integer ID for the audio feed.
        name: Name for the audio feed.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.create_audio_feed(audio_feed_id, name)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_audio_feeds() -> str:
    """List all audio feeds with their properties."""
    client = SnowmixClient()
    try:
        await client.connect()
        feeds = await client.list_audio_feeds()
        return str(feeds)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_get_audio_feed_info(audio_feed_id: int) -> str:
    """
    Get detailed information about an audio feed.

    Args:
        audio_feed_id: The audio feed ID to query.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_audio_feed_info(audio_feed_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_delete_audio_feed(audio_feed_id: int) -> str:
    """
    Delete an audio feed.

    Args:
        audio_feed_id: The audio feed ID to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.delete_audio_feed(audio_feed_id)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Audio Mixers
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_create_audio_mixer(mixer_id: int, name: str) -> str:
    """
    Create a new audio mixer.

    Args:
        mixer_id: Integer ID for the mixer.
        name: Name for the mixer.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.create_audio_mixer(mixer_id, name)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_audio_mixers() -> str:
    """List all audio mixers with their properties."""
    client = SnowmixClient()
    try:
        await client.connect()
        mixers = await client.list_audio_mixers()
        return str(mixers)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_audio_mixer_add_feed(mixer_id: int, feed_id: int) -> str:
    """
    Route an audio feed into a mixer. Both must have matching sample rates.

    Args:
        mixer_id: The mixer ID.
        feed_id: The audio feed ID to route into the mixer.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.audio_mixer_add_feed(mixer_id, feed_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_get_audio_mixer_info(mixer_id: int) -> str:
    """
    Get detailed information about an audio mixer.

    Args:
        mixer_id: The mixer ID to query.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_audio_mixer_info(mixer_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_delete_audio_mixer(mixer_id: int) -> str:
    """
    Delete an audio mixer.

    Args:
        mixer_id: The mixer ID to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.delete_audio_mixer(mixer_id)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Audio Sinks
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_create_audio_sink(sink_id: int, name: str) -> str:
    """
    Create a new audio sink.

    Args:
        sink_id: Integer ID for the sink.
        name: Name for the sink.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.create_audio_sink(sink_id, name)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_audio_sinks() -> str:
    """List all audio sinks with their properties."""
    client = SnowmixClient()
    try:
        await client.connect()
        sinks = await client.list_audio_sinks()
        return str(sinks)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_audio_sink_add_mixer(sink_id: int, mixer_id: int) -> str:
    """
    Route an audio mixer into a sink. Both must have matching sample rates.

    Args:
        sink_id: The sink ID.
        mixer_id: The mixer ID to route into the sink.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.audio_sink_add_mixer(sink_id, mixer_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_get_audio_sink_info(sink_id: int) -> str:
    """
    Get detailed information about an audio sink.

    Args:
        sink_id: The sink ID to query.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_audio_sink_info(sink_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_delete_audio_sink(sink_id: int) -> str:
    """
    Delete an audio sink.

    Args:
        sink_id: The sink ID to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.delete_audio_sink(sink_id)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Text Overlays
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_create_text(text_id: int, string: str) -> str:
    """
    Create a new text overlay.

    Args:
        text_id: Integer ID for the text overlay.
        string: The text string to display.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.create_text(text_id, string)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_text_show(text_id: int) -> str:
    """
    Make a text overlay visible.

    Args:
        text_id: The text overlay ID to show.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.text_show(text_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_text_hide(text_id: int) -> str:
    """
    Hide a text overlay.

    Args:
        text_id: The text overlay ID to hide.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.text_hide(text_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_texts() -> str:
    """List all text overlays with their properties."""
    client = SnowmixClient()
    try:
        await client.connect()
        texts = await client.list_texts()
        return str(texts)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Image Overlays
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_image_load(image_id: int, file_path: str) -> str:
    """
    Load an image file into Snowmix.

    Args:
        image_id: Integer ID for the image.
        file_path: Path to the image file (PNG, JPG, etc.).
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.image_load(image_id, file_path)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_list_images() -> str:
    """List all loaded images with their properties."""
    client = SnowmixClient()
    try:
        await client.connect()
        images = await client.list_images()
        return str(images)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_get_image_info(image_id: int) -> str:
    """
    Get information about a loaded image.

    Args:
        image_id: The image ID to query.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.get_image_info(image_id)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_delete_image(image_id: int) -> str:
    """
    Remove a loaded image from Snowmix.

    Args:
        image_id: The image ID to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.delete_image(image_id)
    finally:
        await client.close()


# ------------------------------------------------------------------ #
#  Custom Commands (Macros)
# ------------------------------------------------------------------ #

@mcp.tool()
async def snowmix_command_list() -> str:
    """List all custom commands (macros)."""
    client = SnowmixClient()
    try:
        await client.connect()
        commands = await client.command_list_all()
        return str(commands)
    finally:
        await client.close()


@mcp.tool()
async def snowmix_command_delete(name: str) -> str:
    """
    Delete a custom command.

    Args:
        name: The command name to delete.
    """
    client = SnowmixClient()
    try:
        await client.connect()
        return await client.command_delete(name)
    finally:
        await client.close()


if __name__ == "__main__":
    mcp.run()
