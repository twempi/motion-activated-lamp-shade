# GestureLight — hand-tracking foundation

GestureLight will eventually let hand gestures operate a physical desk lamp. This
repository currently implements only the webcam and computer-vision foundation:

```text
Webcam -> OpenCV frames -> MediaPipe hand landmarks -> debug preview
```

It does **not** send MQTT messages, communicate with an ESP32, control relays,
or classify gestures yet.

## What it does

- Opens an OpenCV webcam capture device.
- Detects up to two hands with MediaPipe Hands by default.
- Extracts handedness, handedness confidence, normalized landmarks, and pixel
  landmarks for every detected hand.
- Draws a landmark skeleton over the webcam preview.
- Shows FPS, hand count/detection state, and handedness in the preview.
- Exits cleanly when `q` or `Escape` is pressed.
- Logs camera, model-initialization, frame-capture, and detection-state events
  without logging every frame.

## Project layout

```text
.
├── src/gesturelight/
│   ├── __init__.py
│   ├── camera.py        # Webcam configuration, capture, and cleanup
│   ├── hand_tracker.py  # MediaPipe model, landmark data, and drawing
│   └── main.py          # CLI, preview loop, FPS/debug UI, keyboard controls
├── tests/               # No physical webcam required
├── pyproject.toml       # Python package and dependency metadata
├── uv.lock              # Locked Python dependencies
├── flake.nix            # NixOS development shell
└── flake.lock           # Locked Nixpkgs revision
```

The split is intentional: a future `gesture_classifier.py` can consume the
data returned by `HandTracker.process()` without owning a webcam or depending
on OpenCV drawing calls.

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

## Dependencies and NixOS setup

The development shell supplies CPython 3.11, `uv`, and native GUI/runtime
libraries. `uv` creates a local `.venv` and installs the Python wheels pinned
in `uv.lock`.

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
```

Default settings are camera index `0`, requested resolution `1280x720`, up to
`2` hands, and `0.50` detection/tracking confidence. The webcam driver may
choose a nearby supported resolution or frame rate; the actual values are
logged on startup.

## Controls

| Key | Action |
| --- | --- |
| `q` | Quit cleanly |
| `Escape` | Quit cleanly |

## Diagnostics and troubleshooting

The terminal log helps localize a problem:

| Observation | Likely layer | First check |
| --- | --- | --- |
| `Could not open camera index ...` | Webcam capture | Try `--camera-index 1`; run `ls -l /dev/video*`; close other camera apps. |
| Webcam-only mode fails | Webcam or GUI | Confirm a graphical desktop session and camera permissions. |
| Webcam-only mode works, full mode fails at startup | MediaPipe/dependencies | In the Nix shell, run `uv sync --extra dev` again and inspect `--log-level DEBUG`. |
| Preview works but no landmarks appear | Detection | Use even lighting, show one open hand clearly, and try moving closer/farther from the camera. |
| Landmarks appear but lag | Processing rate | Try `--width 640 --height 480` or `--model-complexity 0`. |

On many Linux systems webcam permissions come from membership in the `video`
group. Check `groups` and re-login after an administrator changes group
membership. Do not run the application as root.

The on-screen overlay deliberately reports the displayed loop rate, including
capture, inference, rendering, and event handling. It is more useful for
end-to-end tuning than a detector-only timing number.

## Tests

Run the hardware-free test suite and linter from the Nix shell:

```bash
uv run pytest
uv run ruff check .
```

The tests use fake camera objects and a synthetic blank BGR image. They do not
open a real webcam. The MediaPipe smoke test verifies that the pinned model API
can initialize and process that synthetic frame.

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

## Current scope and next step

This stage is **hand tracking only**. It deliberately contains no gesture
classification, MQTT, ESP32 communication, relay logic, networking, or lamp
control.

After tracking is reliable across your intended lighting and camera placement,
the logical next step is a separate `gesture_classifier.py`. It should consume
`HandTrackingResult`, define a small set of gestures, and add temporal
stability/debouncing before any hardware integration is considered.
