# Snowmix Reserved Commands Reference

This document catalogs the 17 categories of reserved commands in Snowmix 0.5.2.2, along with critical implementation notes discovered during MCP development.

> **⚠️ Critical Implementation Notes (Learned Today)**
> 1. **Silent Success**: Many Snowmix commands (e.g., `feed add`, `feed geometry`) return **nothing** on success. Clients must handle read timeouts gracefully (e.g., return `"OK"` if no `MSG:` or `STAT:` error is received within the timeout window).
> 2. **Multi-Step Feed Creation**: Do not use `feed file <id> "<path>"` for files with spaces. It returns `MSG: Invalid parameters`. Instead, use the multi-step pattern:
>    - `feed add <id> "<name>"`
>    - `feed geometry <id> <width> <height>`
> 3. **Quoting**: Always quote names and paths containing spaces: `feed add 100 "My Video.mp4"`.
> 4. **Connection Banner**: Snowmix sends a version banner (e.g., `Snowmix version 0.5.2.2.\n`) immediately upon TCP connection. Clients **must** consume this line before sending the first command, otherwise it will be misinterpreted as a command response.
> 5. **Line-Oriented Protocol**: Each command must be sent as a separate TCP frame terminated by `\n`. Do not batch multiple commands into a single write unless separated by newlines and you are prepared to parse multi-line `STAT:` responses.

---

## 1. Audio Feed commands
Manage audio input feeds.
- `audio feed add <id>` - Create a new audio feed.
- `audio feed drop <id>` - Remove an audio feed.
- `audio feed channels <id> <channels>` - Set number of channels (e.g., 2 for stereo).
- `audio feed format <id> <format>` - Set sample format (e.g., `S16LE`, `S32LE`, `F32LE`).
- `audio feed rate <id> <rate>` - Set sample rate (e.g., `48000`).
- `audio feed delay <id> <delay>` - Set audio delay in seconds.
- `audio feed queue <id> <min> <max>` - Set queue min/max delay.
- `audio feed mute <id> <0|1>` - Mute or unmute the feed.
- `audio feed volume <id> <volume>` - Set volume (1.0 = 100%).
- `audio feed move volume <id> <start_vol> <end_vol> <duration>` - Animate volume.
- `audio feed source <id> <source_id>` - Map an audio source to this feed.
- `audio feed info <id>` - Get feed information.

## 2. Audio Mixer commands
Mix multiple audio feeds together.
- `audio mixer add <id>` - Create a new audio mixer.
- `audio mixer drop <id>` - Remove an audio mixer.
- `audio mixer channels <id> <channels>` - Set output channels.
- `audio mixer format <id> <format>` - Set output format.
- `audio mixer rate <id> <rate>` - Set output sample rate.
- `audio mixer source feed <mixer_id> <feed_id> <channel_map>` - Route an audio feed to the mixer.
- `audio mixer source mixer <mixer_id> <source_mixer_id>` - Route a mixer into another mixer.
- `audio mixer mute <id> <0|1>` - Mute the mixer output.
- `audio mixer volume <id> <volume>` - Set mixer output volume.
- `audio mixer info <id>` - Get mixer information.

## 3. Audio Sink commands
Output audio from Snowmix to external destinations.
- `audio sink add <id>` - Create a new audio sink.
- `audio sink drop <id>` - Remove an audio sink.
- `audio sink source <id> <mixer_id>` - Set the mixer feeding this sink.
- `audio sink start <id>` - Start the sink.
- `audio sink stop <id>` - Stop the sink.
- `audio sink info <id>` - Get sink information.

## 4. Bg (Background) commands
Manage background worker threads and main mixer frame filling.
- `bg add <id>` - Add a background worker thread.
- `bg delete <id>` - Remove a background worker thread.
- `bg info` - List background threads.
- `bg fill <r> <g> <b> <a>` - Set the default background fill color for the main mixer.

## 5. Feed (Video) commands
Manage video input feeds.
- `feed add <id> "<name>"` - Create a new video feed. **(Must be followed by `feed geometry`)**
- `feed drop <id>` - Remove a video feed.
- `feed geometry <id> <width> <height>` - Set the feed resolution.
- `feed name <id> "<name>"` - Rename a feed.
- `feed file <id> "<path>"` - Assign a file to a feed (⚠️ **Fails with spaces in path**; use multi-step creation instead).
- `feed filename <id> "<path>"` - Alternative file assignment (same space limitation).
- `feed keeplast <id> <0|1>` - Retain the last frame when the source disconnects.
- `feed idle <id> <image_id>` - Show an image when the feed is idle/disconnected.
- `feed chroma key <id> <r> <g> <b> <level>` - Enable chroma keying (green screen).
- `feed flip <id> <horizontal> <vertical>` - Flip the video (0 or 1).
- `feed scale <id> <width> <height>` - Scale the incoming video.
- `feed coor <id> <x> <y>` - Set the feed coordinates on the canvas.
- `feed switch <id>` - Switch the main output exclusively to this feed.
- `feed info <id>` - Get detailed feed status (returns `STAT:` block).

## 6. General commands
System-wide controls and utilities.
- `help` - List all reserved commands.
- `help <command>` - Get syntax for a specific command.
- `include <file.ini>` - Include another configuration file.
- `message "<text>"` - Print a message to the console/log.
- `messagef "<format>" <arg1> <arg2>` - Formatted message.
- `quit` - Gracefully shut down Snowmix.
- `require version <major> <minor>` - Ensure a minimum Snowmix version.
- `stat` - Print global statistics.
- `verbose <level>` - Set logging verbosity (0-3).
- `host allow <ip>` - Allow specific IP to connect to the control socket.
- `socket <port>` - Set the TCP control port (default 9999).

## 7. Image commands
Load and manipulate static images.
- `image add <id> "<path>"` - Load an image file (PNG, JPG, etc.).
- `image drop <id>` - Remove an image from memory.
- `image place <id> <x> <y>` - Set the base placement coordinates.
- `image geometry <id> <width> <height>` - Set the display geometry.
- `image overlay <id> <0|1>` - Enable/disable overlay mode (transparency).
- `image index <id> <index>` - For indexed images, select a specific frame/index.
- `image matrix <id> <m11> <m12> <m21> <m22> <dx> <dy>` - Apply Cairo 2D transformation matrix.
- `image write <id> "<path>"` - Save the current image state to a file.
- `image info <id>` - Get image properties.

## 8. Macros and conditionals
Control flow logic. **Only effective inside a `command create` macro.**
- `label <name>` - Define a jump target.
- `goto <name>` - Unconditional jump to a label.
- `loop [<count>]` - Repeat the following block.
- `next [<count>]` - Skip to the end of the current loop.
- `if <condition>` - Begin conditional block.
- `else` - Alternative branch.
- `endif` - End conditional block.
- **Conditions**: `feedstate(<id>, 'RUNNING')`, `prevstate(<id>, 'STALLED')`, `exist(command, "<name>")`.

## 9. Monitor commands
Configure the local preview display.
- `monitor display <0|1>` - Enable or disable the local monitor window.
- `monitor source <id>` - Set the feed/vfeed to display.
- `monitor geometry <width> <height>` - Set the monitor window size.
- `monitor coor <x> <y>` - Set the monitor window position.
- `monitor scaling <factor>` - Set display scaling factor.
- `monitor aspect <ratio>` - Force a specific aspect ratio (e.g., `16:9`).

## 10. OpenGL Shape commands (GLShape)
Direct OpenGL rendering commands.
- `glshape add <id>` - Create a new OpenGL shape.
- `glshape drop <id>` - Remove an OpenGL shape.
- `glshape begin <mode>` - Begin drawing (e.g., `GL_TRIANGLES`, `GL_QUADS`).
- `glshape end` - End drawing.
- `glshape vertex <x> <y> <z>` - Define a vertex.
- `glshape color <r> <g> <b> <a>` - Set vertex color.
- `glshape texcoord <u> <v>` - Set texture coordinates.
- `glshape info <id>` - Get GLShape information.

## 11. Shape Commands
Cairo 2D vector path drawing.
- `shape add <id>` - Create a new shape.
- `shape drop <id>` - Remove a shape.
- `shape moveto <x> <y>` - Move the drawing cursor.
- `shape lineto <x> <y>` - Draw a line to the specified point.
- `shape curveto <x1> <y1> <x2> <y2> <x3> <y3>` - Draw a cubic Bezier curve.
- `shape arc <x> <y> <radius> <angle1> <angle2>` - Draw an arc.
- `shape fill` - Fill the current path.
- `shape stroke` - Stroke the current path.
- `shape clip` - Set the current path as the clipping region.
- `shape info <id>` - Get shape information.

## 12. Placed Shape commands
Manage the placement and animation of 2D shapes on the canvas.
- `placedshape add <id> <shape_id>` - Place a shape on the canvas.
- `placedshape drop <id>` - Remove a placed shape.
- `placedshape coor <id> <x> <y>` - Set placement coordinates.
- `placedshape scale <id> <sx> <sy>` - Set scaling factors.
- `placedshape rotation <id> <angle>` - Set rotation angle in degrees.
- `placedshape alpha <id> <alpha>` - Set opacity (0.0 to 1.0).
- `placedshape move coor <id> <x1> <y1> <x2> <y2> <duration>` - Animate position.
- `placedshape info <id>` - Get placed shape information.

## 13. OpenGL Placed Shape commands
Manage the placement and animation of 3D/OpenGL shapes on the canvas.
- `glplacedshape add <id> <glshape_id>` - Place a GLShape on the canvas.
- `glplacedshape drop <id>` - Remove a placed GLShape.
- `glplacedshape coor <id> <x> <y> <z>` - Set 3D placement coordinates.
- `glplacedshape rotation <id> <x_angle> <y_angle> <z_angle>` - Set 3D rotation.
- `glplacedshape scale <id> <sx> <sy> <sz>` - Set 3D scaling.
- `glplacedshape move rotation <id> <x1> <y1> <z1> <x2> <y2> <z2> <duration>` - Animate 3D rotation.
- `glplacedshape info <id>` - Get placed GLShape information.

## 14. Python Interpreter commands
Execute Python code and interact with Snowmix internals.
- `python exec "<code>"` - Execute a single line of Python.
- `python file "<path>"` - Execute a Python script file.
- **Built-in `snowmix` module methods**:
  - `snowmix.info(category, subcategory, format)` - Query Snowmix state (e.g., `"feed"`, `"info"`, `"100"`).
  - `snowmix.parse("<command>")` - Send a reserved command to Snowmix from Python.
  - `snowmix.message("<text>")` - Print a message to the Snowmix console.

## 15. Tcl Interpreter commands
Execute Tcl code and interact with Snowmix internals.
- `tcl exec "<code>"` - Execute a single line of Tcl.
- `tcl file "<path>"` - Execute a Tcl script file.
- **Built-in `snowmix` commands**:
  - `snowmix info <category> <subcategory> <format>` - Query Snowmix state.
  - `snowmix parse "<command>"` - Send a reserved command to Snowmix from Tcl.

## 16. Text commands
Render and animate text overlays.
- `text add <id>` - Create a new text overlay.
- `text drop <id>` - Remove a text overlay.
- `text font <id> "<font_name>" <size>` - Set the font and size (e.g., `"Sans"`, `24`).
- `text string <id> "<text>"` - Set the text content.
- `text place <id> <x> <y>` - Set the base placement coordinates.
- `text align <id> <alignment>` - Set alignment (`left`, `center`, `right`, `top`, `bottom`).
- `text anchor <id> <anchor>` - Set the anchor point (e.g., `nw`, `ne`, `sw`, `se`, `center`).
- `text backgr <id> <r> <g> <b> <a>` - Set background color and alpha.
- `text show <id>` - Make the text visible.
- `text hide <id>` - Hide the text.
- `text repeat move <id> <x1> <y1> <x2> <y2> <duration>` - Create rolling/crawling text animation.
- `text info <id>` - Get text overlay information.

## 17. Virtual Feed (vfeed) commands
Create placeholder feeds for complex overlay routing and compositing.
- `vfeed add <id>` - Create a new virtual feed.
- `vfeed drop <id>` - Remove a virtual feed.
- `vfeed geometry <id> <width> <height>` - Set the virtual feed resolution.
- `vfeed source <id> <feed_id>` - Route a real feed into this virtual feed.
- `vfeed clip <id> <x> <y> <width> <height>` - Define a clipping region.
- `vfeed align <id> <alignment>` - Set alignment of the source within the vfeed.
- `vfeed switch <id>` - Switch the main output to this virtual feed.
- `vfeed move coor <id> <x1> <y1> <x2> <y2> <duration>` - Animate the vfeed position.
- `vfeed info <id>` - Get virtual feed information.

---

## MCP Integration Guidelines

When building tools for the `snowmix-mcp` FastMCP server:
1. **Map 1:1**: Each MCP tool should ideally wrap a single logical operation (e.g., `snowmix_add_video_feed` handles both `feed add` and `feed geometry`).
2. **Validation**: Use Pydantic/Zod to validate `feed_id` (int > 0), `width`/`height` (int > 0), and ensure `file_path` is a valid string.
3. **Error Handling**: Always check the response for `MSG:` prefixes. If a command times out with no output, assume success (return `"OK"`), but if `MSG: Invalid...` is returned, raise an exception or return the error string to the LLM.
4. **State Verification**: After a mutating command (like `feed add`), it is best practice to immediately call the corresponding `info` command (e.g., `feed info <id>`) to verify the state change before reporting success to the user.
