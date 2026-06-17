Status update on snowmix-mcp dev:

     What I've done
     - Read /home/rjodouin/Documents/git/snowmix-fastmcp/hermes/plans/handoff.md and resynced on the goal: get
     the advanced image/text test path green, starting with test_image_load_basic.
     - Re-read snowmix_client.py, test_advanced.py, the INI files, and the relevant Snowmix 0.5.2.2 C++ source:
       - src/video_image.cpp (image load / maxplaces handling)
       - src/controller.cpp (command dispatch, "wrong_param_no" error path)
       - src/video_image.h (MAX_IMAGES = 32, default effective slots = 16)
     - Started Snowmix manually with ini/advancedTest.ini and probed port 9999.
     - Confirmed the project venv works; pytest-asyncio is installed.

     Root cause found
     - test_image_load_basic uses image id 1001.
     - Snowmix's default loaded image slots are 16, and max places are 16.
     - When image load receives an id >= the current max, LoadImage returns -1, which the controller maps to:
       MSG: Invalid number of parameters: "image load ..."
     - The test then fails because it expects resp == "OK".

     I also saw the same parameter-count error for image load 1 /tmp/nonexistent.png, so missing PNG /
     out-of-range id both surface as that message. The client method image_load returning raw Snowmix output will
     not be "OK" unless we make Snowmix succeed.

     Changes made
     - Updated /home/rjodouin/Documents/git/snowmix-fastmcp/ini/advancedTest.ini to raise the relevant maxplaces
     limits before image/text/feed commands are used (image maxplaces load / place, text maxplaces string / font
     / place, feed maxplaces).
     - Left a Snowmix instance running on port 9999 with that INI for live probing.

     Remaining issue
     - After restart, image maxplaces load still reported 16 slots. The INI maxplaces statements may need to be
     ordered differently (before any subsystem is implicitly created), or the syntax may need adjustment.
     - Until the limits actually increase, test_image_load_basic stays red.

     Recommended next steps
     1. Confirm the INI changes took effect by reading /tmp/snowmix_adv_test.log and re-checking image maxplaces
     load / text maxplaces string / feed maxplaces output. If it still says 16, move the maxplaces lines
     immediately after the system lines and before any include/slib lines.
     2. If INI adjustment alone does not work, add a test setup step that sends maxplaces commands
     programmatically before loading images/text/feeds, e.g.:
        image maxplaces load 500
        image maxplaces place 500
        text maxplaces string 500 font 500 place 500
        feed maxplaces 500
     3. Verify the SnowmixClient.image_load method converts an empty/silent success response to "OK", since
     Snowmix itself says nothing on successful image load.
     4. Re-run:
        SNOWMIX=/home/rjodouin/Snowmix-0.5.2.2 ./venv/bin/pytest test_advanced.py -v -k test_image_load_basic -x
     5. Once that single test passes, run the full advanced suite.