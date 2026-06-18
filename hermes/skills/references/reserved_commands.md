# Snowmix Reserved Commands Reference

Verified command syntax for Snowmix 0.5.2.2, confirmed through C++ source
analysis and the snowmix-fastmcp test suite (42/42 passing). Each command below
was exercised via `SnowmixClient` methods in `test_snowmix.py`,
`test_advanced.py`, or `test_e2e.py`.

## Protocol Behavior

- **Banner on connect**: Snowmix sends `Snowmix version 0.5.2.2.` immediately
  on TCP connect. The client must consume it before issuing commands.
- **Silent success**: Many commands return nothing on success. The client
  treats a 1.0s read timeout with no `MSG:`/`STAT:` lines as `"OK"`.
- **Line-oriented**: Each command is a single line terminated by `\n`. Never
  batch multiple commands into one TCP frame.
- **STAT: vs MSG:**: Most list commands return `STAT:` lines. `command list`
  returns `MSG:` lines. The client strips both prefixes.

## System Commands
```
system geometry            # Returns: "STAT:  system geometry = 1280x720 BGRA"
system info                # Returns version, build, subsystem status
system quit                # Gracefully shut down Snowmix
```

## Video Feed Commands
```
feed add 1 Camera1         # Create feed with ID 1, name is bare text (NO quotes)
feed name 1 Camera1        # Rename an existing feed (NOT "feed add" for renames)
feed geometry 1 1280 720   # Set feed resolution (must be <= system geometry)
feed socket 1 /tmp/feed1-control-pipe  # Set shmem socket path for GStreamer shmsink
feed live 1                # Mark feed as live
feed info 1                # Get feed status (returns STAT: block)
feed list                  # List all feeds (returns "STAT: Feed ID N Name: ...")
feed drop 1                # Remove a feed
```

**Pitfall:** `feed add <id> <name>` on an existing feed returns
`MSG: Feed ID <id> already used`. Use `feed name <id> <newname>` to rename.

## Feed Stacking (Output Routing)

```
stack 0                    # Background only (feed 0 / internal)
stack 0 1                  # Stack feed 1 onto mixer output at layer 0
```

**Note:** `stack 0 <feed_id>` on an unconnected feed (no GStreamer shmsink
yet) is SAFE — the feed enters SETUP state, no crash. The `feed switch <id>`
command does NOT work reliably; use `stack 0 <feed_id>` instead.

## Virtual Feed Commands
```
vfeed add 1 MyVfeed        # Create virtual feed with ID 1 and name (0-31 range)
vfeed add                  # LIST mode (no args) — returns "STAT: vfeed  N : <name>"
vfeed source feed 1 1      # Route real feed 1 into vfeed 1
vfeed geometry 1 640 360   # Set vfeed resolution
vfeed drop 1               # Remove a vfeed
```

**Pitfall:** Bare `vfeed` is NOT a recognized command. `vfeed add` with no
arguments is the list mode.

## Image Commands
```
image load 1 /path/to/logo.png   # Load PNG (NO quotes on path — sscanf %u %[^\n])
image name 1 Logo               # Set a human-readable name
image place 1 1 100 50          # Place image: place_id=1, image_id=1, x=100, y=50
image overlay 1                  # Overlay placed image 1 (ONLY inside Show macro)
image hide 1                     # Hide placed image 1
image maxplaces load             # Query: "load 5000 used 1"
image maxplaces place            # Query: "place 5000 used 1"
```

**Pitfalls:**
- `image load` is the load command, NOT `image add`.
- Do NOT quote the file path. The C parser uses `sscanf("%u %[^\n]")` which
  does not strip quotes — quoting causes the path to include literal `"` chars
  and the file won't be found.
- `image place` takes BOTH a place_id and an image_id, not just one ID.
- There is NO `image list` or `image info` command. Use `image maxplaces
  load` / `image maxplaces place` for counts, and `image name <id>` to query
  a name.
- `image overlay` only works inside the per-frame mixing loop (the `Show`
  macro bound via `overlay finish`). Calling it as a one-shot command always
  returns `MSG: Invalid parameters` because `m_overlay` is NULL between frames.

## Text Overlay Commands
```
text string 1 Hello World        # Create/set text string for text_id 1
text font 1 FreeSans 24          # Set font name and size (separate args, NO quotes)
text place 1 1 0 50 50 1 1 1 1 nw  # Place text: place_id=1 text_id=1 font_id=0 x=50 y=50 r g b a anchor
text show 1                      # Show placed text 1
text hide 1                      # Hide placed text 1
text overlay 1                    # Overlay text 1 (ONLY inside Show macro)
text align 1 center top          # Set alignment (NOT "text place align" — obsolete in 0.5.0+)
text backgr 1 0 0 100 20 0 0 0 0.5  # Background rectangle (NOT "text place backgr")
text clipabs 1 0 0 1280 720      # Clip rectangle (NOT "text place clipabs")
text repeat move 1 2 0 1280 0    # Marquee scroll (NOT "text place repeat move")
text place                        # List placed text items (bare, no args)
```

**Pitfalls:**
- `text string <id> <text>` creates text content. There is no `text add`.
- `text font <id> <font_name> <size>` — font name and size are separate
  arguments, NOT a quoted string like `"sans 24"`.
- `text place <subcommand>` is OBSOLETE in 0.5.0+. Use `text align`,
  `text backgr`, `text clipabs`, `text repeat move` directly. The bare
  `text place <place_id> <text_id> ...` (numeric placement) is still valid.
- `text overlay` only works inside the Show macro (same as `image overlay`).

## Audio Feed Commands
```
audio feed add 1 Music           # Create audio feed 1 with name
audio feed add                   # LIST mode (no args)
audio feed rate 1 48000          # Set sample rate
audio feed channels 1 2          # Set channel count (2 = stereo)
audio feed format 1 16 signed    # Set bit depth and signedness
audio feed info 1                # Get feed info
audio feed add 1                 # Delete (re-issue add with no name)
```

## Audio Mixer Commands
```
audio mixer add 1 MainMixer      # Create mixer 1 with name
audio mixer add                  # LIST mode (no args)
audio mixer rate 1 48000         # Set sample rate (MUST match source feed rate)
audio mixer channels 1 2         # Set channel count (MUST match source feed)
audio mixer source feed 1 1      # Route audio feed 1 into mixer 1
audio mixer start 1              # Start mixer
audio mixer info 1               # Get mixer info
audio mixer add 1                # Delete (re-issue add with no name)
```

**Pitfall:** `audio mixer source feed` with mismatched rates returns
`MSG: Invalid number of parameters` — misleading. Match the mixer's rate and
channels to the source feed BEFORE calling `source feed`.

## Audio Sink Commands
```
audio sink add 1 Output          # Create sink 1 with name
audio sink add                   # LIST mode (no args)
audio sink rate 1 48000          # Set sample rate (MUST match source mixer rate)
audio sink channels 1 2          # Set channel count
audio sink source mixer 1 1      # Route mixer 1 into sink 1 (NOTE: "source mixer" subcommand)
audio sink start 1               # Start sink
audio sink info 1                # Get sink info
audio sink add 1                 # Delete (re-issue add with no name)
```

**Pitfall:** The syntax is `audio sink source mixer <sink_id> <mixer_id>`,
NOT `audio sink source <sink_id> <mixer_id>`. The `mixer` subcommand keyword
is required.

## Command Macros

Macros group commands for per-frame execution. The `overlay finish` macro
(`Show`) runs once per output frame during the mixing loop — this is where
`image overlay` and `text overlay` must be placed.

```
command create Show              # Enter macro creation mode
image overlay 1                  # Recorded into Show
text overlay 1                   # Recorded into Show
loop                             # Recorded into Show (loops the macro)
command end                      # Finalize the macro

overlay finish Show              # Bind Show to run every output frame
overlay pre Show                 # Bind Show to run before each frame (alternative)

command list                     # List all macros (returns MSG: lines, not STAT:)
command delete Show              # Delete a macro
command push Show image overlay 2  # Push a line onto an existing macro
```

## INI Configuration

Use `ini/test.ini` (full subsystem allocations) or `ini/advancedTest.ini`
(advanced overlay/stack config). NEVER use `ini/minimal.ini` — it omits
`maxplaces` for audio/text/image subsystems, causing creation commands to fail
silently.

**Critical INI ordering:** `maxplaces` directives MUST appear BEFORE
`system geometry`. Geometry triggers CVideoFeeds creation which locks in the
max; if maxplaces comes after, defaults (16) are baked in and your directives
silently fail.

```ini
system control port 9999

# maxplaces FIRST
maxplaces images 5000
maxplaces imageplaces 5000
maxplaces texts 5000
maxplaces video feeds 5000

# NOW geometry (locks in maxplaces)
system geometry 1280 720 BGRA
system frame rate 24
system socket /tmp/mixer1
```
