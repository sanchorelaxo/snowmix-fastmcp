import os
import subprocess
import time
import pytest
import pytest_asyncio
from snowmix_client import SnowmixClient

@pytest.fixture(scope="module")
def snowmix_process():
    env = os.environ.copy()
    env["SNOWMIX"] = "/usr/local/lib/Snowmix-0.5.2.2"
    proc = subprocess.Popen(
        ["snowmix", "ini/minimal.ini"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1.5)  # wait for startup
    yield proc
    proc.terminate()
    proc.wait()

@pytest_asyncio.fixture
async def client():
    c = SnowmixClient()
    await c.connect()
    yield c
    await c.close()

@pytest.mark.asyncio
async def test_system_geometry(client: SnowmixClient):
    result = await client.get_system_geometry()
    assert "geometry" in result.lower()

@pytest.mark.asyncio
async def test_add_video_feed(client: SnowmixClient):
    import random
    feed_id = random.randint(2000, 9000)
    video_path = "/home/rjodouin/Downloads/hypno2_fx_DLs/Goopy Gradients/0001.mp4"
    
    # Add feed (this command is often silent on success in Snowmix)
    res = await client.add_video_feed(feed_id, video_path)
    
    # Get info to verify it was actually created
    info = await client.get_feed_info(feed_id)
    assert str(feed_id) in info

@pytest.mark.asyncio
async def test_handle_multiple_video_feeds(client: SnowmixClient):
    import random
    feed_id1 = random.randint(2000, 9000)
    feed_id2 = random.randint(2000, 9000)
    while feed_id2 == feed_id1:
        feed_id2 = random.randint(2000, 9000)
        
    video_path1 = "/home/rjodouin/Downloads/hypno2_fx_DLs/Goopy Gradients/0001.mp4"
    video_path2 = "/home/rjodouin/Downloads/hypno2_fx_DLs/Goopy Gradients/0002.mp4"
    
    # Add feeds (often silent on success)
    await client.add_video_feed(feed_id1, video_path1)
    await client.add_video_feed(feed_id2, video_path2)
    
    # Verify both were created
    info1 = await client.get_feed_info(feed_id1)
    info2 = await client.get_feed_info(feed_id2)
    
    assert str(feed_id1) in info1
    assert str(feed_id2) in info2
