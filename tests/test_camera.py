"""Hardware-free tests for camera resource management."""

from __future__ import annotations

import pytest

from gesturelight.camera import Camera, CameraConfig, CameraError


class FakeCapture:
    """Small stand-in for cv2.VideoCapture; it never opens real hardware."""

    def __init__(self, *, is_open: bool = True, frame: object | None = None) -> None:
        self.is_open = is_open
        self.frame = frame
        self.released = False
        self.settings: list[tuple[int, float]] = []

    def isOpened(self) -> bool:
        return self.is_open

    def set(self, property_id: int, value: float) -> bool:
        self.settings.append((property_id, value))
        return True

    def get(self, property_id: int) -> float:
        values = {
            FakeCv2.CAP_PROP_FRAME_WIDTH: 640.0,
            FakeCv2.CAP_PROP_FRAME_HEIGHT: 480.0,
            FakeCv2.CAP_PROP_FPS: 30.0,
        }
        return values[property_id]

    def read(self) -> tuple[bool, object | None]:
        return self.frame is not None, self.frame

    def release(self) -> None:
        self.released = True


class FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5

    def __init__(self, capture: FakeCapture) -> None:
        self.capture = capture
        self.calls: list[tuple[int, ...]] = []

    def VideoCapture(self, *arguments: int) -> FakeCapture:
        self.calls.append(arguments)
        return self.capture


def test_open_configures_requested_camera_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    """Camera setup should configure OpenCV without touching real hardware."""
    from gesturelight import camera as camera_module

    capture = FakeCapture(frame=object())
    fake_cv2 = FakeCv2(capture)
    monkeypatch.setattr(camera_module, "cv2", fake_cv2)

    camera = Camera(CameraConfig(index=2, width=640, height=480, fps=30))
    camera.open()

    assert fake_cv2.calls == [(2,)]
    assert capture.settings == [(3, 640), (4, 480), (5, 30)]
    assert camera.read() is capture.frame

    camera.release()
    assert capture.released
    assert not camera.is_open


def test_open_releases_capture_when_device_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed open must return a useful error and not leak the capture object."""
    from gesturelight import camera as camera_module

    capture = FakeCapture(is_open=False)
    monkeypatch.setattr(camera_module, "cv2", FakeCv2(capture))

    with pytest.raises(CameraError, match="Could not open camera index 0"):
        Camera(CameraConfig()).open()

    assert capture.released


def test_read_returns_none_for_a_failed_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frame failures remain distinguishable from an unopened camera."""
    from gesturelight import camera as camera_module

    capture = FakeCapture(frame=None)
    monkeypatch.setattr(camera_module, "cv2", FakeCv2(capture))
    camera = Camera(CameraConfig())
    camera.open()

    assert camera.read() is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"index": -1},
        {"width": 0},
        {"height": -1},
        {"fps": 0},
    ],
)
def test_camera_config_rejects_invalid_values(kwargs: dict[str, int]) -> None:
    """Configuration errors should be detected before attempting to open hardware."""
    with pytest.raises(ValueError):
        CameraConfig(**kwargs)
