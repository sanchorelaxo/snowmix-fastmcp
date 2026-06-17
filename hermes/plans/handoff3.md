# Handoff 3 — Snowmix FastMCP

## Status: IN PROGRESS (Task 7 from dev-plan.md)

### What was done

Created `test_e2e.py` with 3 tests:

- `test_feed_setup_and_stack` — create feed, set socket, stack
- `test_image_overlay_during_pipeline` — the core e2e: GStreamer feeds video in, MCP overlays image+text, GStreamer reads mixed output to MP4
- `test_feed_status_after_streaming` — verify feed shows activity

### Blocker

The e2e test fails because Snowmix crashes when `stack 0 1` is sent. The first test (`test_feed_setup_and_stack`) gets a `ConnectionResetError` on the stack command, meaning Snowmix dies. Subsequent tests can't connect (port 9999 refused).

**Root cause (likely):** `stack 0 1` tries to stack feed 1, but feed 1 has no data source connected yet (no GStreamer shmsink writing to the feed socket). Snowmix may crash when stacking a feed that has no shared memory area.

**Possible fixes:**

1. Stack only feed 0 (background) before the pipeline starts: `stack 0` instead of `stack 0 1`
2. Start the GStreamer input pipeline FIRST, then stack feed 1 after data is flowing
3. Reorder: create feed → start input → then stack

### Remaining (Task 8 from dev-plan.md)

Once the stack crash is fixed, run the full suite:

```bash
SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2 ./venv/bin/pytest test_snowmix.py test_advanced.py test_e2e.py -v -s
```

Note: `test_advanced.py` and `test_e2e.py` both use module-scoped Snowmix fixtures on port 9999, so they should be run sequentially (pytest does this by default with module scope, but both kill stale Snowmix in their fixtures).
