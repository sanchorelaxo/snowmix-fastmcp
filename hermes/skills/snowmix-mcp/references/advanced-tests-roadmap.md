# snowmix-mcp testing roadmap and known blockers

This file tracks the state of the snowmix-fastmcp test suite and the quirks that made past tests red. Use it before adding new tests or resurrecting skipped ones.

## Files under test

- `test_snowmix.py` — base port from node-snowmix; all historical green tests live here.
- `test_advanced.py` — the next layer: feed creation with geometry, image load/name/list, text font/place/align/background/clip/repeat, command chaining. These are MCP equivalents of the TCL/slib-driven `expandedTest.ini` lines 45-89.

## Most recent debugging session (2026-06-13)

### Goal
Make `test_advanced.py::test_image_load_basic` pass.

### Failure
`image load 1001 <path>` returns:

```
MSG: Invalid number of parameters: "image load 1001 /home/rjodouin/Downloads/.../title2.png "
```

### Root cause
Snowmix 0.5.2.2 defaults to **16 loaded-image slots** (`m_max_images = 16`) and 16 placed-image slots. `LoadImage` rejects `image_id >= m_max_images` and returns `-1`; the controller maps `-1` to "Invalid number of parameters". The client interprets this nonzero response as failure, so the test fails.

### Why the message is misleading
The C++ parser checks `sscanf(ci, "%u %[^\n]", &id, str)`. Even with valid syntax, the underlying `LoadImage` call can fail with -1, which the dispatcher (`controller.cpp`) converts to the same "Invalid number of parameters" message regardless of the real reason.

### Fix path (incomplete)
Add these commands **before** any image/text/feed creation in the test fixture or INI:

```ini
image maxplaces load 500
image maxplaces place 500
text maxplaces string 500
text maxplaces font 500
text maxplaces place 500
feed maxplaces 500
```

Then use `test.ini` (which already has the relevant subsystems allocated) rather than `expandedTestMin.ini` for tests that rely on image/text. Alternatively, derive an `advancedTest.ini` that contains the maxplaces directives at the top.

### Verification recipe

```bash
python3 - <<'PY'
import socket
s = socket.create_connection(('127.0.0.1', 9999), timeout=5)
s.recv(4096)  # banner
s.sendall(b'image maxplaces load\n')
print(s.recv(4096).decode(errors='replace'))
PY
```

Expected after raising limits: `MSG: image maxplaces load 500 used 0`.

### Why the first INI edit did not appear to take effect
`advancedTest.ini` was edited to set maxplaces, but after restart `image maxplaces load` still reported 16. Possible causes:
- The image subsystem was implicitly created by a preceding command (feed/text/scene) before maxplaces ran, locking the old allocation. Snowmix allocates subsystem tables on first reference; raising maxplaces is only allowed when no entries have been created.
- The `maxplaces` keywords in the ini used an alias Snowmix didn't parse (e.g. `loaded_images` vs `images`). Check canonical forms in `video_mixer.cpp` around line 545.
- The directive appeared inside a `command create ... command end` block or after a subsystem access.

### Recommended fixture design for advanced tests

```python
@pytest_asyncio.fixture(scope="module")
async def snowmix_process():
    env = {**os.environ, "SNOWMIX": SNOWMIX_HOME}
    proc = await asyncio.create_subprocess_exec(
        SNOWMIX_BIN, str(INI_PATH),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    await asyncio.sleep(2)
    # optional: connect once and bump maxplaces globally
    c = SnowmixClient(port=9999)
    await c.connect()
    for cmd in [
        "image maxplaces load 500",
        "image maxplaces place 500",
        "text maxplaces string 500",
        "text maxplaces font 500",
        "text maxplaces place 500",
        "feed maxplaces 500",
    ]:
        await c.send_command(cmd)
    await c.close()
    yield proc
    # ...terminate...
```

## Other traps seen during implementation

- **Image IDs cannot exceed maxplaces.** Even `image load 1 /tmp/x.png` fails when `m_max_images` is 0 or subsystem inactive. Verify `system info` reports `Video image: loaded` first.
- **Texts have the same limit.** `text string`, `text font`, and `text place` respectively consume string/font/place slots.
- **PNG only.** Snowmix `LoadImage` checks PNG magic bytes and rejects non-PNG files.
- **File search path.** Snowmix resolves relative file names through its search path (cwd, `$HOME/.snowmix`, `$SNOWMIX/`). Absolute paths are safest in tests.
- **SnowmixClient.image_load returns the stripped Snowmix response.** On true success Snowmix returns nothing, so the helper should emit `"OK"`. On failure it returns the `MSG:` line; the helper should pass that through so tests can assert on it.
