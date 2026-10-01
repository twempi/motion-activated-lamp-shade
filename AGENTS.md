# GestureLight agent guide

## Current scope

This repository is at the webcam and hand-landmark stage of GestureLight:

```text
Webcam -> OpenCV -> MediaPipe hand landmarks -> debug preview
```

Do not add gesture classification, MQTT, ESP32 communication, networking,
relay control, or lamp control unless the user explicitly expands the scope.
Do not modify unrelated firmware or user-created files unless the request names
them.

## Code layout

- `src/gesturelight/camera.py`: OpenCV camera configuration, frame capture,
  camera errors, and release.
- `src/gesturelight/hand_tracker.py`: MediaPipe initialization, BGR-to-RGB
  conversion, structured landmark data, and landmark drawing.
- `src/gesturelight/main.py`: CLI, preview loop, FPS/debug overlay, keyboard
  handling, and application cleanup.
- `tests/`: hardware-free tests. Never require a physical webcam in normal
  test runs.

Keep a future classifier independent of OpenCV drawing: consume
`HandTrackingResult` / `DetectedHand`, not MediaPipe protobuf objects or UI
functions.

## Development environment

Use the project flake and its locked `uv` environment:

```bash
nix develop path:.
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For a one-command run from the repository root:

```bash
nix develop path:. -c uv run gesturelight-hand-tracker --camera-only
```

The flake is currently a development shell, not an installable Nix package.
Keep `flake.lock` and `uv.lock` synchronized when their respective inputs
change.

## NixOS and GUI constraints

- Use Python 3.11 from the flake. MediaPipe is pinned to `0.10.21` because the
  project uses the classic `mp.solutions.hands` API.
- Do not casually replace it with a newer MediaPipe release or switch to the
  Tasks API; that is an intentional compatibility decision and needs a tested
  migration.
- The non-headless OpenCV wheel uses Qt's `xcb` platform plugin, not a native
  Wayland plugin. Preserve the flake's X11 runtime libraries and
  `QT_QPA_PLATFORM = "xcb"`; this uses XWayland on the development desktop.
- If a Qt/OpenCV window fails, first test `--camera-only`. A camera-open log
  means capture works; Qt plugin errors are a GUI runtime issue.

## Implementation rules

- Prefer small, typed dataclasses and direct functions over new abstractions or
  dependencies.
- Keep configuration values named and configurable; camera index must remain
  easy to change.
- Use `logging`, not frame-by-frame `print()` calls.
- Preserve clear errors for missing dependencies, camera-open failure,
  frame-capture failure, and MediaPipe initialization/processing failure.
- Always release the camera, close MediaPipe, and destroy OpenCV windows on
  every exit path.
- Keep BGR/RGB, normalized-coordinate, pixel-coordinate, detection/tracking,
  and FPS comments accurate when touching those areas.

## Verification and documentation

- Run the full hardware-free test suite and Ruff after Python changes.
- `tests/test_hand_tracker_model.py` is a dependency/model smoke test using a
  synthetic frame; it must not access a webcam.
- Manual webcam validation is required for camera, window, and lighting
  behavior. Do not claim it passed unless it was actually observed.
- Update `README.md` when changing CLI flags, dependencies, Nix runtime
  requirements, architecture, or manual validation steps.
