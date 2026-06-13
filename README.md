# Snowmix FastMCP Server

A Python-based Model Context Protocol (MCP) server for controlling the Snowmix real-time video/audio mixer, built with `fastmcp`.

## Overview

This project provides a clean, async Python interface to Snowmix 0.5.2.2 via its TCP control socket (default `127.0.0.1:9999`). It exposes high-level MCP tools for managing video feeds, querying system state, and verifying feed creation, abstracting away the quirks of Snowmix's line-oriented, silent-on-success protocol.

## Features

- **Async TCP Client**: Robust handling of Snowmix's initial version banner and silent command responses.
- **Pydantic Validation**: Strict type checking for feed IDs, geometries, and file paths.
- **TDD Enforced**: All core functionality is backed by `pytest` tests that spawn a real Snowmix instance.
- **Space-Safe Paths**: Implements the verified multi-step feed creation pattern (`feed add` + `feed geometry`) to reliably handle file paths containing spaces.

## Prerequisites

1. **Snowmix 0.5.2.2** installed and running:
   ```bash
   # Ensure the SNOWMIX environment variable is set
   export SNOWMIX=/usr/local/lib/Snowmix-0.5.2.2
   snowmix ini/minimal.ini &
   ```
2. **Python 3.10+**

## Installation

```bash
# Clone or navigate to the project directory
cd ~/Documents/git/snowmix-fastmcp

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install fastmcp pytest pytest-asyncio
```

## Usage

### Running the MCP Server

To start the server in stdio mode (for integration with Hermes Agent or other MCP hosts):

```bash
source venv/bin/activate
python main.py
```

### Available MCP Tools

| Tool Name | Description |
|-----------|-------------|
| `snowmix_get_system_geometry` | Returns the current system resolution and format (e.g., `1024x576 BGRA`). |
| `snowmix_add_video_feed` | Adds a new video feed. Handles the multi-step `feed add` + `feed geometry` sequence automatically. |
| `snowmix_get_feed_info` | Queries the status of a specific feed by its integer ID. |

### Example: Adding a Video Feed via MCP

When an LLM calls `snowmix_add_video_feed` with:
- `feed_id`: `100`
- `file_path`: `"/home/rjodouin/Downloads/hypno2_fx_DLs/Goopy Gradients/0001.mp4"`
- `width`: `1024`
- `height`: `576`

The server executes:
1. `feed add 100 "0001.mp4"`
2. `feed geometry 100 1024 576`

And returns `"OK"` on success, or the `MSG:` error string on failure.

## Development & Testing

This project strictly follows Test-Driven Development (RED-GREEN-REFACTOR).

### Running Tests

The test suite automatically spawns a Snowmix instance, runs the tests, and tears it down.

```bash
source venv/bin/activate
pytest test_snowmix.py -v
```

### Adding New Tools

1. **RED**: Write a failing test in `test_snowmix.py` for the new Snowmix command behavior.
2. **GREEN**: Add the corresponding method to `snowmix_client.py` and expose it via `@mcp.tool()` in `main.py`.
3. **REFACTOR**: Clean up the code while ensuring `pytest` remains green.
4. **Document**: Update `snowmix_commands_reference.md` and this `README.md` with the new tool.

## Architecture Notes & Snowmix Quirks

- **Silent Success**: Many Snowmix commands return nothing on success. The `SnowmixClient` handles this by returning `"OK"` if a 1.0s read timeout occurs with no `MSG:` or `STAT:` error lines.
- **Connection Banner**: Snowmix sends `Snowmix version X.Y.Z.\n` immediately upon TCP connect. The client consumes this automatically.
- **Multi-Step Feed Creation**: The legacy `feed file <id> "<path>"` command fails with `MSG: Invalid parameters` when paths contain spaces. This client uses the robust `feed add <id> <name>` followed by `feed geometry <id> <w> <h>` pattern.
- **Audio Rate Matching**: When routing audio feeds to mixers or mixers to sinks, Snowmix enforces matching sample rates. If the rates don't match, Snowmix returns the deceptive error `MSG: Invalid number of parameters` instead of a rate mismatch message. Always set `audio mixer rate <id> <rate>` and `audio sink rate <id> <rate>` to match the source's rate before calling `audio mixer source feed` or `audio sink source mixer`.
- **`vfeed add` Lists vfeeds**: `vfeed add` with no arguments lists all virtual feeds. Bare `vfeed` is not a recognized command.
- **`feed name` for Renames**: Use `feed name <id> <newname>` to rename a feed. Re-issuing `feed add <id> <name>` on an existing feed fails with `MSG: Feed ID <id> already used`.
- **`command list` Returns `MSG:` Lines**: Unlike most list commands (`STAT:`), `command list` returns `MSG:` lines. Parsers must handle both prefixes.

## References

- [Snowmix Reserved Commands Documentation](https://snowmix.sourceforge.io/Documentation/reserved.html)
- [Snowmix Commands Reference (Local)](./snowmix_commands_reference.md)
- [FastMCP Documentation](https://gofastmcp.com)

## License

MIT
