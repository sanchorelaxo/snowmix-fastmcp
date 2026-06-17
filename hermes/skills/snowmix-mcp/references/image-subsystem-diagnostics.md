# Image Subsystem Diagnostics

## C++ Source Analysis (Snowmix 0.5.2.2)

### Command Dispatch (`video_image.cpp:362-365`)

```cpp
// image load [ <image id> [<file name>]]  // empty file name deletes entry
else if (!strncasecmp (str, "load ", 5)) {
    str += 5;
    return set_image_load (ctr, pController, str, false, false);
}
```

### `set_image_load` parser (`video_image.cpp:925`)

```cpp
int n = sscanf(ci, "%u %[^\n]", &id, str);
trim_string(str);
if (n == 1) n = LoadImage(id, NULL);  // Deletes the entry
else if (n == 2 && (!async || m_mutex))
    n = (async ? AsyncLoadImage(id, str, indexed)
               : LoadImage(id, str, indexed));
else { free(str); return 1; }  // "Invalid number of parameters"
```

The `sscanf` expects exactly: `<unsigned int> <string until newline>`. Two fields.

### Status output format (line 606)

```c
str = strdup("image load <width> <height> <bits> <color> <<name>> <<file_name>>");
```

This is the STATUS/INFO output format (NOT the command syntax). It shows all fields a loaded image has.

### Subsystem activation

`system info` reports `Video image: loaded` or `Video image: no`.

Setting `maxplaces images 16` (or `maxplaces loaded_images 16`) allocates capacity. But the subsystem may not be active unless:
- A slib include activates it (`slib images.slib`), OR
- A `load images` directive appears in the ini, OR
- The binary was compiled with images enabled

If `image load <id> <path>` returns "MSG: Invalid number of parameters: ..." despite correct syntax, check `system info` for `Video image: loaded`. If it says `no`, the subsystem isn't active.

## Diagnostic runs against test.ini (port 9999)

```bash
# system info shows which subsystems are loaded
echo 'system info' | nc -w 1 127.0.0.1 9999
# Look for: Video feeds, Virtual video feeds, Video text, Video image, etc.

# image help lists all supported subcommands  
echo 'image help' | nc -w 1 127.0.0.1 9999
```

## Image help output (test.ini)

```
MSG:  image load [<image id> [<file name>]]  // empty string deletes entry
MSG:  image loadasync [<image id> [<file name>]]  // empty string deletes entry
MSG:  image name [<image id> [<name>]]  // empty string deletes name
MSG:  image place [<place id> [<image id> <x> <y> ...]]
MSG:  image overlay (<place id> | ...)
MSG:  image maxplaces (load | place) [<max value>]
...
```

## Maxplaces keywords (from video_mixer.cpp:545)

```cpp
// maxplaces - strings fonts placed_text loaded_images placed_images
// shapes placed_shapes shape_patterns audio_feeds audio_mixers
// audio_sink video_feeds virtual_feeds
```

These are the canonical underscored forms. Snowmix 0.5.2.2 also accepts space-separated aliases (`images` for `loaded_images`, `video feeds` for `video_feeds`, etc.).
