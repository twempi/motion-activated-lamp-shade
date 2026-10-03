"""Hardware-free checks for GestureLight's hand-control gestures."""

from __future__ import annotations

import pytest

from gesturelight.gesture_classifier import (
    HandGestureConfig,
    HandGestureController,
    LampGestureAction,
)
from gesturelight.hand_tracker import (
    DetectedHand,
    HandTrackingResult,
    NormalizedLandmark,
    PixelLandmark,
)


def _result(
    shape: str,
    *,
    pinching: bool = False,
    wrist_y: float = 0.8,
    depth_gap: float = 0.0,
) -> HandTrackingResult:
    if shape not in {"fist", "open"}:
        raise ValueError(f"Unknown hand shape: {shape}")

    landmarks = [NormalizedLandmark(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    landmarks[0] = NormalizedLandmark(x=0.5, y=wrist_y, z=0.0)
    landmarks[9] = NormalizedLandmark(x=0.5, y=wrist_y - 0.2, z=0.0)
    tip_y = wrist_y - (0.1 if shape == "fist" else 0.6)
    for x, pip_index, tip_index in zip(
        (0.43, 0.5, 0.57, 0.64),
        (6, 10, 14, 18),
        (8, 12, 16, 20),
        strict=True,
    ):
        landmarks[pip_index] = NormalizedLandmark(x=x, y=wrist_y - 0.3, z=0.0)
        landmarks[tip_index] = NormalizedLandmark(x=x, y=tip_y, z=0.0)

    landmarks[4] = NormalizedLandmark(x=0.25, y=wrist_y - 0.45, z=0.0)
    if pinching:
        landmarks[4] = NormalizedLandmark(x=0.42, y=wrist_y - 0.55, z=0.0)
        landmarks[8] = NormalizedLandmark(x=0.43, y=wrist_y - 0.55, z=depth_gap)

    hand = DetectedHand(
        handedness="Right",
        handedness_confidence=0.99,
        normalized_landmarks=tuple(landmarks),
        pixel_landmarks=tuple(PixelLandmark(x=0, y=0) for _ in landmarks),
    )
    return HandTrackingResult(hands=(hand,))


def test_open_hand_only_presses_power_after_a_fist() -> None:
    controller = HandGestureController(HandGestureConfig())

    assert controller.update(_result("open")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("open")) is LampGestureAction.POWER
    assert controller.update(_result("open")) is None


def test_pinch_and_vertical_motion_changes_brightness() -> None:
    controller = HandGestureController(HandGestureConfig())

    assert controller.update(_result("open", pinching=True, wrist_y=0.8)) is None
    assert (
        controller.update(_result("open", pinching=True, wrist_y=0.76))
        is LampGestureAction.BRIGHTNESS_UP
    )
    assert controller.update(_result("open", pinching=True, wrist_y=0.76)) is None
    assert (
        controller.update(_result("open", pinching=True, wrist_y=0.8))
        is LampGestureAction.BRIGHTNESS_DOWN
    )


def test_brightness_pinch_clears_a_pending_power_gesture() -> None:
    controller = HandGestureController(HandGestureConfig())

    assert controller.update(_result("fist")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("open", pinching=True)) is None
    assert controller.update(_result("open")) is None


def test_brightness_pinch_blocks_brief_fist_detection_glitches() -> None:
    controller = HandGestureController(HandGestureConfig())

    assert controller.update(_result("open", pinching=True)) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("fist")) is None
    assert controller.update(_result("open")) is None


def test_brightness_requires_tips_to_be_close_in_depth_too() -> None:
    controller = HandGestureController(HandGestureConfig())

    assert controller.update(_result("open", pinching=True, depth_gap=0.1)) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pinch_distance_ratio": 0.0},
        {"brightness_step_ratio": 0.0},
        {"power_fist_stable_frames": 0},
        {"power_rearm_frames": -1},
    ],
)
def test_gesture_configuration_rejects_invalid_values(kwargs: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        HandGestureConfig(**kwargs)
