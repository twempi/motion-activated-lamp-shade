# GestureLight — hand tracking and lamp control

GestureLight uses a webcam and MediaPipe hand landmarks to send lamp-button
presses to an ESP32 over local Wi-Fi. Lamp control is opt-in: it activates only
when the ESP32's URL is explicitly supplied.

```text
Webcam -> OpenCV frames -> MediaPipe hand landmarks -> gestures -> local Wi-Fi HTTP -> ESP32 -> lamp buttons
```

Close a fist and open it to press the power button. Touch thumb and index
finger together, then move the hand up or down to adjust brightness.

## What it does

- Opens an OpenCV webcam capture device.
- Detects up to two hands with MediaPipe Hands by default.
- Extracts handedness, handedness confidence, normalized landmarks, and pixel
  landmarks for every detected hand.
- Draws a landmark skeleton over the webcam preview.
- Shows FPS, hand count/detection state, and handedness in the preview.
- With `--esp32-url`, sends ESP32 power and brightness button commands for
  the configured hand gestures.
- Exits cleanly when `q` or `Escape` is pressed.
- Logs camera, model-initialization, frame-capture, and detection-state events
  without logging every frame.

## Project layout

```text
.
├── src/gesturelight/
│   ├── __init__.py
│   ├── camera.py        # Webcam configuration, capture, and cleanup
│   ├── gesture_classifier.py # Rendering-free hand gesture classifier
│   ├── hand_tracker.py  # MediaPipe model, landmark data, and drawing
│   ├── lamp_controller.py # Local-Wi-Fi HTTP connection to the ESP32
│   ├── main.py          # CLI, preview loop, FPS/debug UI, keyboard controls
│   ├── gesturelight.ino # ESP32 button-pulse firmware
│   └── wifi_secrets.example.h # Template for local Wi-Fi credentials
├── tests/               # No physical webcam required
├── pyproject.toml       # Python package and dependency metadata
├── uv.lock              # Locked Python dependencies
├── flake.nix            # Nix development shell, app package, and NixOS module
└── flake.lock           # Locked Nixpkgs revision
```

The gesture classifier consumes the data returned by `HandTracker.process()`;
it does not depend on OpenCV drawing functions or MediaPipe protobuf objects.

## Landmark data API

`HandTracker.process(frame_bgr)` returns a `HandTrackingResult`:

```python
result.hands  # tuple[DetectedHand, ...]
result.hand_count  # number of hands in this frame
result.has_hands  # True when at least one hand was found

hand.handedness  # "Left", "Right", or None
hand.handedness_confidence  # float from 0.0 to 1.0, or None
hand.normalized_landmarks  # tuple[NormalizedLandmark, ...]
hand.pixel_landmarks  # tuple[PixelLandmark, ...]
```

Normalized `x` and `y` coordinates are image-relative values (normally from
0.0 to 1.0), which makes them independent of camera resolution. Pixel
coordinates are derived for the current frame and clamped to its bounds for
safe OpenCV drawing. `z` is MediaPipe's relative depth estimate; it is not a
pixel distance.

## Install as a desktop application

The flake packages the locked Python environment, its required Linux runtime
libraries, a `gesturelight-hand-tracker` command, and a `GestureLight` desktop
entry. It is currently available for **x86_64 Linux** only: the pinned
MediaPipe 0.10.21 release supplies the required classic Hands API wheel for
that platform but not Linux ARM.

From this repository, install it into your user profile:

```bash
nix profile install path:.#gesturelight
```

Nix flakes use Git-tracked files when the project is a Git checkout. If you
have created new source files locally, add or commit them before this command
so they are included in the package.

After the profile is active, search your desktop's application launcher for
`GestureLight`. You can also launch it from a terminal with either command:

```bash
gesturelight-hand-tracker
nix run path:.#gesturelight
```

For a profile-only install, supply the ESP32 address with `--esp32-url` when
launching from a terminal. To configure the launcher too, use the NixOS module
below.

## Configure through a NixOS flake

Add this project as an input to your system flake:

```nix
inputs.gesturelight.url = "path:/home/edward/Documents/projects/lamp-shade";
```

Then import its module in the `modules` list for your NixOS configuration and
configure it directly:

```nix
modules = [
  inputs.gesturelight.nixosModules.default
  {
    gesturelight = {
      enable = true;
      url = "192.168.1.50";
    };
  }
];
```

The module installs GestureLight and creates a launcher-specific wrapper with
the URL set from `gesturelight.url`; it does not set a global session variable.
Use an `http://` prefix yourself only when you want to include one explicitly.
Rebuild your system after changing the option.

## Dependencies and NixOS setup

The development shell supplies CPython 3.11, `uv`, and native GUI/runtime
libraries. `uv` creates a local `.venv` and installs the Python wheels pinned
in `uv.lock`. ESP32 communication uses Python's standard-library HTTP client.

This mixed approach is deliberate: at the Nixpkgs revision pinned by this
project, the required classic MediaPipe Hands Python API is not available as a
Nix package. A pure Nix environment would therefore need a custom MediaPipe
derivation. The small `uv` environment is easier to understand and reproduce:
Nix pins the interpreter/native libraries, and `uv.lock` pins Python packages.

From the repository root:

```bash
nix develop path:.
uv sync --extra dev
```

`path:.` also works while developing uncommitted changes. Once the flake is
committed, plain `nix develop` is equivalent.

The flake includes common libraries used by the OpenCV and MediaPipe wheels.
OpenCV's Linux wheel supplies Qt's `xcb` plugin rather than a native Wayland
plugin, so the development shell uses the XWayland-compatible `xcb` backend.
If NixOS reports a missing dynamic library, ensure your system has
[`programs.nix-ld.enable = true`](https://wiki.nixos.org/wiki/Nix-ld) and then
open a new shell. That is a machine-level NixOS setting, so it is intentionally
not changed by this repository.

## Run

Start the full hand tracker:

```bash
uv run gesturelight-hand-tracker
```

To control the ESP32-connected lamp, first configure and upload the Wi-Fi
firmware described below. Then power the board from any suitable USB power
supply; it does not need a data connection to the computer. The computer and
ESP32 must be on the same trusted local network.
Classic ESP32 boards require a 2.4 GHz Wi-Fi SSID.

```bash
uv run gesturelight-hand-tracker --esp32-url http://192.168.1.50
```

The preview describes both hand controls. The application sends button pulses,
so it cannot know the lamp's current on/off state independently.

Start the webcam-only diagnostic first if you want to isolate capture and GUI
from MediaPipe:

```bash
uv run gesturelight-hand-tracker --camera-only
```

Useful options:

```bash
# Choose another webcam (the default index is 0)
uv run gesturelight-hand-tracker --camera-index 1

# Request a smaller frame for easier CPU debugging
uv run gesturelight-hand-tracker --width 640 --height 480

# Disable the selfie-style mirrored preview
uv run gesturelight-hand-tracker --no-mirror

# Inspect model/camera details in the terminal
uv run gesturelight-hand-tracker --log-level DEBUG

# Loosen the intentionally tight touch threshold only if needed
uv run gesturelight-hand-tracker --esp32-url http://192.168.1.50 --pinch-distance-ratio 0.20

# Require more or less vertical movement for each brightness button press
uv run gesturelight-hand-tracker --esp32-url http://192.168.1.50 --brightness-step-ratio 0.50
```

Default settings are camera index `0`, requested resolution `1280x720`, up to
`2` hands, `0.50` detection/tracking confidence, a `0.15` pinch-to-palm-size
ratio, a `0.15` palm-size brightness movement per press, and a one-second HTTP
timeout for an ESP32 connection. The webcam driver may choose a nearby supported
resolution or frame rate; the actual values are logged on startup. `--camera-only`
cannot be combined with `--esp32-url`.

## ESP32 firmware and wiring

[`src/gesturelight/gesturelight.ino`](src/gesturelight/gesturelight.ino)
maps local Wi-Fi commands and button outputs as follows:

| HTTP `command` value | Action | ESP32 GPIO |
| --- | --- | --- |
| `p` | Power-button pulse | 16 |
| `d` | Brightness-down pulse | 17 |
| `u` | Brightness-up pulse | 18 |

Before uploading, copy the template beside the sketch and replace the Wi-Fi
placeholders. The local `wifi_secrets.h` file is deliberately ignored by Git.

```bash
cp src/gesturelight/wifi_secrets.example.h src/gesturelight/wifi_secrets.h
```

Upload the sketch over USB once, open its 115200-baud serial monitor, and note
the printed `http://...` address. Reserve that address in the router if
possible, then use it with `--esp32-url`; after that, the board only needs USB
power. GestureLight verifies `/health` at startup and uses `POST /command`
requests for button pulses.

The ESP32 accepts commands from any device on its LAN. Use this only on your
trusted home network—not a guest or shared network.

## Controls

| Key | Action |
| --- | --- |
| `q` | Quit cleanly |
| `Escape` | Quit cleanly |

## Gesture control

In Wi-Fi-control mode:

- Power: hold a fully closed fist briefly, then open all four fingers. This
  sends one `p` button press and requires another fist before it can fire
  again. A recent brightness pinch temporarily blocks this gesture so tracking
  noise cannot toggle the lamp.
- Brightness: touch thumb and index finger together, then move the hand up for
  `u` or down for `d`. One button press is sent for each movement of roughly
  one-sixth of your palm size; release the pinch to stop brightness control.

The pinch uses normalized 3D landmark distance relative to palm size, so it
rejects fingers that are merely close or overlap in the camera view.

## Diagnostics and troubleshooting

The terminal log helps localize a problem:

| Observation | Likely layer | First check |
| --- | --- | --- |
| `Could not open camera index ...` | Webcam capture | Try `--camera-index 1`; run `ls -l /dev/video*`; close other camera apps. |
| Webcam-only mode fails | Webcam or GUI | Confirm a graphical desktop session and camera permissions. |
| Webcam-only mode works, full mode fails at startup | MediaPipe/dependencies | In the Nix shell, run `uv sync --extra dev` again and inspect `--log-level DEBUG`. |
| Preview works but no landmarks appear | Detection | Use even lighting, show one open hand clearly, and try moving closer/farther from the camera. |
| Landmarks appear but lag | Processing rate | Try `--width 640 --height 480` or `--model-complexity 0`. |
| `Could not reach ESP32 ...` | Wi-Fi | Check that the board has power, both devices use the same LAN, and the URL is still correct. |
| Touches do not trigger | Gesture calibration | Keep the hand fully in view; try `--pinch-distance-ratio 0.20`. |
| Brightness changes too quickly or slowly | Gesture calibration | Increase or decrease `--brightness-step-ratio` respectively. |

On many Linux systems webcam permissions come from membership in the `video`
group. Check `groups` and re-login after an administrator changes group
membership. Do not run the application as root.

The on-screen overlay deliberately reports the displayed loop rate, including
capture, inference, rendering, and event handling. It is more useful for
end-to-end tuning than a detector-only timing number.

## Tests

Run the hardware-free test suite and linter from the Nix shell:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

The tests use fake camera and HTTP objects plus a synthetic blank BGR image.
They do not open a real webcam or contact an ESP32. The MediaPipe smoke test
verifies that the pinned model API can initialize and process that synthetic frame.

## Manual validation procedure

Automated tests cannot validate your physical webcam, lighting, or desktop
window. Run this once on the target development machine:

1. Enter the shell and synchronize dependencies:

   ```bash
   nix develop path:.
   uv sync --extra dev
   ```

2. Optionally launch `uv run gesturelight-hand-tracker --camera-only`. Confirm
   that the webcam window opens, FPS changes, and `q` closes it.
3. Launch `uv run gesturelight-hand-tracker`.
4. With no hand visible, confirm the app stays running and reports `Hands: 0
   (none detected)`.
5. Put one hand in view. Confirm landmark dots and connecting lines appear.
6. Move and rotate the hand. Confirm the landmarks follow it and the overlay
   shows handedness when available.
7. Remove the hand. Confirm the app continues and returns to zero detected
   hands without errors.
8. Press `q` (or `Escape`). Confirm the window closes and the terminal reports
   that the camera and tracker were released.
9. Start a different camera application to confirm the webcam is no longer
   held by GestureLight.
10. With the lamp in a safe state, configure `wifi_secrets.h`, upload the
    firmware over USB once, and confirm the serial monitor prints its local
    HTTP URL. Disconnect its USB data cable and power the ESP32 from a USB
    power supply.
11. Run `uv run gesturelight-hand-tracker --esp32-url http://192.168.1.50`,
    using the address printed by the board.
12. Hold a fully closed fist briefly, then open all four fingers. Confirm the
    lamp toggles once; keep the hand open to confirm it does not repeat. Close
    the fist and open it again to confirm one further pulse.
13. Touch thumb and index finger together, then move the hand up. Confirm one
    or more `BRIGHTNESS UP` pulses as the hand moves. Repeat moving down and
    confirm `BRIGHTNESS DOWN` pulses. Release the pinch and confirm movement
    alone does not change brightness.

## Current scope and next step

This stage supports local-Wi-Fi power and brightness gestures using an open
HTTP endpoint on the ESP32. It does not add MQTT, cloud access,
automatic device discovery, or lamp-state sensing. Manual validation remains
necessary across the intended lighting and camera placement.
