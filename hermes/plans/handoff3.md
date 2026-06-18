# Handoff 3 — Snowmix FastMCP

## Status: IN PROGRESS (Task 7 from dev-plan.md)

### What was done

Created `test_e2e.py` with 3 tests:

- `test_feed_setup_and_stack` — create feed, set socket, stack
- `test_image_overlay_during_pipeline` — the core e2e: GStreamer feeds video in, MCP overlays image+text, GStreamer reads mixed output to MP4
- `test_feed_status_after_streaming` — verify feed shows activity

### Blocker — RESOLVED

The handoff3 blocker was misdiagnosed. `stack 0 1` does NOT crash Snowmix —
stacking an unconnected feed is fine (feed shows SETUP state, no crash).

**Actual root causes (two independent bugs):**

1. **Snowmix stdin/stdout controller closes fd 1.** Snowmix wires a default
   controller to stdin(fd 0)/stdout(fd 1). If stdin EOFs (e.g. inherited
   /dev/null in the test harness), that controller closes, taking fd 1 with
   it. Later, `feed socket` creates an AF_UNIX socket that the OS assigns to
   the now-free fd 1, and Snowmix bails out: "Creating a socket returned fd 1.
   This means that stdout was closed upon startup."
   **Fix:** start Snowmix with `stdin=asyncio.subprocess.PIPE` (held open for
   the process lifetime) so the default controller never EOFs. See
   `test_e2e.py` snowmix fixture.

2. **gst-launch-1.0 rejects the pipeline as a single argv string.** Passing
   the whole pipeline as one `create_subprocess_exec` argument produces
   "erroneous pipeline: syntax error". gst-launch wants space-split tokens
   with `!` as a separate argv element.
   **Fix:** `*shlex.split(pipeline)` in both `start_gstreamer_input` and
   `start_gstreamer_output`.

**Overlay architecture correction:**

The original test called `image overlay 1` / `text overlay 1` as one-shot
standalone commands. This always fails with "Invalid parameters" because
`m_overlay` (the mixing buffer) is only non-NULL *during* the per-frame
mixing loop — it is reset to NULL after each frame (video_mixer.cpp:1608).
The correct Snowmix pattern: embed `image overlay` / `text overlay` inside
the `overlay finish` macro (`Show`), which Snowmix executes once per output
frame. The test now rebuilds `Show` with `image overlay 1`, `text overlay 1`,
`loop`, then re-binds it with `overlay finish Show`.

### Result — DONE

Full suite 42/42 pass. The core e2e test produces a valid h264 1280x720 mp4
(verified via ffprobe: 144 frames / ~6s in the test run).
