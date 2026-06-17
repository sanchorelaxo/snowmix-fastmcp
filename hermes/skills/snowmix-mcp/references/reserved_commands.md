# Snowmix Reserved Commands Reference

This file contains practical examples of Snowmix reserved commands for use with the `snowmix_execute` MCP tool.

## System Commands
```
system geometry          # Returns: "geometry 1280 720 25"
system info              # Returns version and build info
system quit              # Gracefully shut down Snowmix
```

## Video Feed Commands
```
feed add 1               # Create video feed with ID 1
feed name 1 "Camera 1"   # Name the feed
feed switch 1            # Switch main output to feed 1
feed status 1            # Get status of feed 1
```

## Virtual Feed Commands (Picture-in-Picture, Overlays)
```
vfeed add 1              # Create virtual feed 1
vfeed name 1 "PiP Feed"
vfeed place 1 100 100 320 180  # Place vfeed 1 at x=100, y=100, width=320, height=180
vfeed switch 1           # Make vfeed 1 the main output
vfeed source 1 1         # Set vfeed 1's source to feed 1
```

## Text Overlay Commands
```
text add 1               # Create text overlay 1
text string 1 "LIVE"     # Set text content
text font 1 "sans 24"    # Set font and size
text location 1 ne       # Position: ne (northeast/top-right), nw, se, sw, or x y coordinates
text color 1 255 0 0 255 # RGBA color (red, fully opaque)
text show 1              # Display the text
text hide 1              # Hide the0 text
```

## Image Overlay Commands
```
image add 1 "/path/to/logo.png"  # Load image
image show 1                     # Display image
image place 1 50 50              # Position at x=50, y=50
image hide 1                     # Hide image
```

## Audio Commands
```
audio feed add 1         # Create audio feed 1
audio feed rate 1 48000  # Set sample rate
audio mixer add 1        # Create audio mixer 1
audio mixer source feed 1 1  # Route audio feed 1 to mixer 1
audio mixer switch 1     # Switch main audio to mixer 1
```

## Command Macros
You can group commands into macros for batch execution:
```
command create my_macro
feed switch 1
text show 1
command end
```
Then execute with: `my_macro`

## Node-Snowmix Library Patterns

The `node-snowmix` library provides object-oriented wrappers for common operations:

```javascript
// Connect to Snowmix
const snowmix = Snowmix.new({ host: '127.0.0.1', port: 9999 });
await snowmix.connect();

// Get system info
const geometry = await snowmix.sendCommand('system geometry');

// Work with feeds (auto-populated on connect)
const vfeed = snowmix.vfeeds.byId(1);
await vfeed.switch();

// Create text overlay
const text = snowmix.texts.create({ string: 'LIVE', location: 'ne' });
await text.show();

// Close connection
await snowmix.close();
```

## Important Notes

1. **Line-oriented protocol**: Each command must be sent as a separate string terminated by a newline. Do not batch multiple commands into a single `sendCommand` call unless using a command macro.
2. **State persistence**: Snowmix maintains state across connections. A feed created in one session persists until explicitly deleted or Snowmix restarts.
3. **Default port**: The default TCP control port is `9999`. Ensure no other process is using this port.
4. **INI files**: Snowmix requires an INI file to start. Use `ini/minimal.ini` for basic testing or create a custom INI file for production pipelines.
