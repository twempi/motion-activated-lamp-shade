"""Hardware-free tests for landmark data conversion and validation."""

from __future__ import annotations

import pytest

from gesturelight.hand_tracker import (
    DetectedHand,
    HandTrackerConfig,
    HandTrackingResult,
    NormalizedLandmark,
    PixelLandmark,
    normalized_to_pixel_coordinates,
)


@pytest.mark.parametrize(
    ("normalized", "frame_size", "expected"),
    [
        ((0.0, 0.0), (640, 480), (0, 0)),
        ((0.5, 0.5), (640, 480), (320, 240)),
        ((1.0, 1.0), (640, 480), (639, 479)),
        ((-0.1, 1.2), (640, 480), (0, 479)),
    ],
)
def test_normalized_coordinates_convert_to_in_frame_pixels(
    normalized: tuple[float, float], frame_size: tuple[int, int], expected: tuple[int, int]
) -> None:
    """Drawing coordinates must always remain inside the image."""
    assert normalized_to_pixel_coordinates(*normalized, *frame_size) == expected


def test_tracking_result_exposes_hands_without_opencv_objects() -> None:
    """A future classifier can consume model data without knowing about drawing."""
    landmark = NormalizedLandmark(x=0.5, y=0.25, z=-0.1)
    hand = DetectedHand(
        handedness="Right",
        handedness_confidence=0.98,
        normalized_landmarks=(landmark,),
        pixel_landmarks=(PixelLandmark(x=320, y=120),),
    )
    result = HandTrackingResult(hands=(hand,))

    assert result.hand_count == 1
    assert result.has_hands
    assert result.hands[0].normalized_landmarks[0] == landmark


def test_detected_hand_rejects_mismatched_landmark_lists() -> None:
    """Normalized and pixel data must remain index-aligned for classifiers."""
    with pytest.raises(ValueError, match="same number"):
        DetectedHand(
            handedness=None,
            handedness_confidence=None,
            normalized_landmarks=(NormalizedLandmark(x=0.0, y=0.0, z=0.0),),
            pixel_landmarks=(),
        )


@pytest.mark.parametrize("frame_size", [(0, 480), (640, 0)])
def test_pixel_conversion_rejects_empty_frames(frame_size: tuple[int, int]) -> None:
    """A zero-sized image cannot have valid pixel landmark coordinates."""
    with pytest.raises(ValueError, match="positive"):
        normalized_to_pixel_coordinates(0.5, 0.5, *frame_size)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_num_hands": 0},
        {"model_complexity": 2},
        {"min_detection_confidence": -0.1},
        {"min_detection_confidence": 1.1},
        {"min_tracking_confidence": -0.1},
        {"min_tracking_confidence": 1.1},
    ],
)
def test_hand_tracker_config_rejects_invalid_values(kwargs: dict[str, float | int]) -> None:
    """Bad detector settings should fail before a model is initialized."""
    with pytest.raises(ValueError):
        HandTrackerConfig(**kwargs)
