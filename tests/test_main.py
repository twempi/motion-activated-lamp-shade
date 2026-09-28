"""Tests for command-line configuration and non-hardware UI helpers."""

from __future__ import annotations

import numpy as np
import pytest

from gesturelight.hand_tracker import (
    DetectedHand,
    HandTrackingResult,
    NormalizedLandmark,
    PixelLandmark,
)
from gesturelight.main import ApplicationConfig, FrameRateMeter, build_debug_lines, parse_args, run


def test_command_line_settings_build_application_config() -> None:
    """The most useful capture and tracker parameters are configurable."""
    config = parse_args(
        [
            "--camera-index",
            "2",
            "--width",
            "640",
            "--height",
            "480",
            "--max-hands",
            "1",
            "--min-detection-confidence",
            "0.7",
            "--min-tracking-confidence",
            "0.8",
            "--no-mirror",
            "--camera-only",
            "--log-level",
            "DEBUG",
        ]
    )

    assert config.camera.index == 2
    assert config.camera.width == 640
    assert config.camera.height == 480
    assert config.tracker.max_num_hands == 1
    assert config.tracker.min_detection_confidence == 0.7
    assert config.tracker.min_tracking_confidence == 0.8
    assert not config.mirror
    assert config.camera_only
    assert config.log_level == "DEBUG"


def test_invalid_command_line_configuration_has_an_argparse_error() -> None:
    """Users should receive argument help instead of a ValueError traceback."""
    with pytest.raises(SystemExit) as error:
        parse_args(["--camera-index", "-1"])

    assert error.value.code == 2


def test_frame_rate_meter_uses_elapsed_time_between_completed_frames() -> None:
    """A stable frame duration should yield a stable FPS value."""
    meter = FrameRateMeter()

    assert meter.update(10.0) == 0.0
    assert meter.update(10.5) == 2.0
    assert meter.update(11.0) == 2.0


def test_debug_lines_include_detection_and_handedness_information() -> None:
    """The on-screen diagnostics expose the state needed for development."""
    hand = DetectedHand(
        handedness="Left",
        handedness_confidence=0.95,
        normalized_landmarks=(NormalizedLandmark(x=0.0, y=0.0, z=0.0),),
        pixel_landmarks=(PixelLandmark(x=0, y=0),),
    )
    lines = build_debug_lines(30.0, HandTrackingResult(hands=(hand,)))

    assert lines == (
        "FPS: 30.0",
        "Hands: 1 (detected)",
        "Handedness: Left (0.95)",
    )


def test_debug_lines_make_camera_only_mode_obvious() -> None:
    """The camera diagnostic mode must not appear to be hand tracking."""
    assert build_debug_lines(0.0, None) == (
        "FPS: 0.0",
        "Hand tracking: disabled (--camera-only)",
    )


def test_run_releases_resources_after_q_without_real_hardware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The normal exit path must clean up the camera, tracker, and OpenCV windows."""
    from gesturelight import main as main_module

    class FakeOpenCV:
        WINDOW_NORMAL = 0
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 0
        error = RuntimeError

        def __init__(self) -> None:
            self.destroyed_windows = False
            self.wait_key_calls = 0

        def namedWindow(self, *_: object) -> None:
            return None

        def flip(self, frame: np.ndarray, _: int) -> np.ndarray:
            return frame

        def putText(self, *_: object) -> None:
            return None

        def imshow(self, *_: object) -> None:
            return None

        def waitKey(self, _: int) -> int:
            self.wait_key_calls += 1
            return ord("q")

        def destroyAllWindows(self) -> None:
            self.destroyed_windows = True

    class FakeCamera:
        instance: FakeCamera | None = None

        def __init__(self, _: object) -> None:
            self.closed = False
            FakeCamera.instance = self

        def __enter__(self) -> FakeCamera:
            return self

        def __exit__(self, *_: object) -> None:
            self.closed = True

        def read(self) -> np.ndarray:
            return np.zeros((8, 8, 3), dtype=np.uint8)

    class FakeTracker:
        instance: FakeTracker | None = None

        def __init__(self, _: object) -> None:
            self.closed = False
            FakeTracker.instance = self

        def __enter__(self) -> FakeTracker:
            return self

        def __exit__(self, *_: object) -> None:
            self.closed = True

        def process(self, _: np.ndarray) -> HandTrackingResult:
            return HandTrackingResult(hands=())

        def draw_landmarks(self, frame: np.ndarray, _: HandTrackingResult) -> np.ndarray:
            return frame

    fake_opencv = FakeOpenCV()
    monkeypatch.setattr(main_module.camera_module, "cv2", fake_opencv)
    monkeypatch.setattr(main_module, "Camera", FakeCamera)
    monkeypatch.setattr(main_module, "HandTracker", FakeTracker)

    configuration = ApplicationConfig(
        camera=main_module.CameraConfig(),
        tracker=main_module.HandTrackerConfig(),
    )

    assert run(configuration) == 0
    assert fake_opencv.wait_key_calls == 1
    assert fake_opencv.destroyed_windows
    assert FakeCamera.instance is not None and FakeCamera.instance.closed
    assert FakeTracker.instance is not None and FakeTracker.instance.closed
