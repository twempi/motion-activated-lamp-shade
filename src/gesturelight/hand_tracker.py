"""MediaPipe hand detection, landmark extraction, and visualization helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Self

import numpy as np
from numpy.typing import NDArray

try:
    import cv2
except ImportError:  # Defer the friendly error until someone starts tracking.
    cv2: Any | None = None

try:
    import mediapipe as mp
except ImportError:
    mp: Any | None = None

logger = logging.getLogger(__name__)

Frame = NDArray[np.uint8]

DEFAULT_MAX_NUM_HANDS = 2
DEFAULT_MODEL_COMPLEXITY = 1
DEFAULT_MIN_DETECTION_CONFIDENCE = 0.5
DEFAULT_MIN_TRACKING_CONFIDENCE = 0.5
LIVE_VIDEO_MODE = False

# The 21 MediaPipe hand-landmark indices connected as a hand skeleton. Keeping
# this model topology here lets drawing consume our data classes rather than
# exposing MediaPipe protobuf objects to future gesture-classifier code.
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (0, 17),
)

CONNECTION_COLOR_BGR = (255, 255, 255)
LANDMARK_COLOR_BGR = (0, 255, 0)
CONNECTION_THICKNESS = 2
LANDMARK_RADIUS = 3
# OpenCV uses -1 as the thickness value for a filled circle.
LANDMARK_FILLED_THICKNESS = -1


class HandTrackerError(RuntimeError):
    """Base error for hand-tracking setup and processing failures."""


class HandTrackerInitializationError(HandTrackerError):
    """Raised when the MediaPipe hand-landmark model cannot start."""


class FrameProcessingError(HandTrackerError):
    """Raised when an input frame cannot be prepared for hand tracking."""


@dataclass(frozen=True, slots=True)
class HandTrackerConfig:
    """Settings for MediaPipe's detector and temporal tracker.

    ``min_detection_confidence`` applies when MediaPipe needs to find a hand.
    ``min_tracking_confidence`` applies while it follows landmarks in later
    frames, which is usually less expensive than detecting again.
    """

    max_num_hands: int = DEFAULT_MAX_NUM_HANDS
    model_complexity: int = DEFAULT_MODEL_COMPLEXITY
    min_detection_confidence: float = DEFAULT_MIN_DETECTION_CONFIDENCE
    min_tracking_confidence: float = DEFAULT_MIN_TRACKING_CONFIDENCE

    def __post_init__(self) -> None:
        if self.max_num_hands < 1:
            raise ValueError("Maximum number of hands must be at least one.")
        if self.model_complexity not in (0, 1):
            raise ValueError("Hand model complexity must be 0 or 1.")
        _validate_confidence("Detection confidence", self.min_detection_confidence)
        _validate_confidence("Tracking confidence", self.min_tracking_confidence)


@dataclass(frozen=True, slots=True)
class NormalizedLandmark:
    """A MediaPipe landmark in image-relative coordinates.

    ``x`` and ``y`` are normally in the range 0 to 1. ``z`` is a relative
    depth value, not a pixel distance. Values are retained unchanged so a
    future classifier receives the model's original measurement.
    """

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class PixelLandmark:
    """The same landmark converted to a drawable image pixel coordinate."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class DetectedHand:
    """Structured data for one detected hand, independent of rendering."""

    handedness: str | None
    handedness_confidence: float | None
    normalized_landmarks: tuple[NormalizedLandmark, ...]
    pixel_landmarks: tuple[PixelLandmark, ...]

    def __post_init__(self) -> None:
        if len(self.normalized_landmarks) != len(self.pixel_landmarks):
            raise ValueError(
                "Normalized and pixel landmark lists must contain the same number of points."
            )
        if self.handedness_confidence is not None:
            _validate_confidence("Handedness confidence", self.handedness_confidence)


@dataclass(frozen=True, slots=True)
class HandTrackingResult:
    """All hands found in a single video frame."""

    hands: tuple[DetectedHand, ...]

    @property
    def hand_count(self) -> int:
        """Number of hands detected in this frame."""
        return len(self.hands)

    @property
    def has_hands(self) -> bool:
        """Whether at least one hand was detected in this frame."""
        return bool(self.hands)


def normalized_to_pixel_coordinates(
    normalized_x: float,
    normalized_y: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int]:
    """Convert normalized image coordinates to safe, in-frame pixel coordinates.

    Multiplying by image width/height maps model-relative coordinates to the
    current frame. Clamping is intentional: landmarks can be just outside the
    image near an edge, while OpenCV drawing needs valid pixel indices.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image width and height must be positive.")

    pixel_x = min(max(int(normalized_x * image_width), 0), image_width - 1)
    pixel_y = min(max(int(normalized_y * image_height), 0), image_height - 1)
    return pixel_x, pixel_y


class HandTracker:
    """Run MediaPipe Hands and return landmark data separate from the UI."""

    def __init__(self, config: HandTrackerConfig) -> None:
        self._config = config
        self._model = self._create_model()

    @property
    def config(self) -> HandTrackerConfig:
        """Return the MediaPipe configuration in use."""
        return self._config

    def process(self, frame_bgr: Frame) -> HandTrackingResult:
        """Detect hands in one OpenCV BGR frame and extract structured landmarks."""
        if self._model is None:
            raise HandTrackerError("Cannot process a frame after the hand tracker has been closed.")
        self._validate_bgr_frame(frame_bgr)

        # OpenCV captures BGR, while MediaPipe expects RGB. This conversion is
        # the boundary between camera/UI image format and model image format.
        try:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        except Exception as error:
            raise FrameProcessingError("Could not convert the BGR frame to RGB.") from error

        frame_rgb.flags.writeable = False
        try:
            raw_result = self._model.process(frame_rgb)
        except Exception as error:
            raise HandTrackerError("MediaPipe failed while processing a video frame.") from error
        finally:
            frame_rgb.flags.writeable = True

        return self._to_tracking_result(raw_result, frame_bgr.shape[1], frame_bgr.shape[0])

    def draw_landmarks(self, frame_bgr: Frame, result: HandTrackingResult) -> Frame:
        """Draw landmark dots and hand-skeleton connections onto a BGR frame.

        The input frame is changed in place and returned for convenient use in
        the display loop. ``HandTrackingResult`` itself remains rendering-free.
        """
        if cv2 is None:
            raise HandTrackerError("OpenCV is required to draw hand landmarks.")

        for hand in result.hands:
            pixels = hand.pixel_landmarks
            for start_index, end_index in HAND_CONNECTIONS:
                if end_index >= len(pixels):
                    continue
                start = pixels[start_index]
                end = pixels[end_index]
                cv2.line(
                    frame_bgr,
                    (start.x, start.y),
                    (end.x, end.y),
                    CONNECTION_COLOR_BGR,
                    CONNECTION_THICKNESS,
                )

            for point in pixels:
                cv2.circle(
                    frame_bgr,
                    (point.x, point.y),
                    LANDMARK_RADIUS,
                    LANDMARK_COLOR_BGR,
                    thickness=LANDMARK_FILLED_THICKNESS,
                )

        return frame_bgr

    def close(self) -> None:
        """Release MediaPipe resources. Safe to call more than once."""
        if self._model is None:
            return

        model, self._model = self._model, None
        try:
            model.close()
            logger.info("Closed MediaPipe hand tracker.")
        except Exception:
            logger.warning("An error occurred while closing the hand tracker.", exc_info=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _create_model(self) -> Any:
        if cv2 is None:
            raise HandTrackerInitializationError(
                "OpenCV is not installed. Enter the Nix shell and run 'uv sync'."
            )
        if mp is None:
            raise HandTrackerInitializationError(
                "MediaPipe is not installed. Enter the Nix shell and run 'uv sync'."
            )

        try:
            model = mp.solutions.hands.Hands(
                static_image_mode=LIVE_VIDEO_MODE,
                max_num_hands=self._config.max_num_hands,
                model_complexity=self._config.model_complexity,
                min_detection_confidence=self._config.min_detection_confidence,
                min_tracking_confidence=self._config.min_tracking_confidence,
            )
        except Exception as error:
            raise HandTrackerInitializationError(
                "Could not initialize the MediaPipe hand-landmark model."
            ) from error

        logger.info(
            "Initialized MediaPipe hand tracker (maximum hands: %s, detection confidence: %.2f, "
            "tracking confidence: %.2f).",
            self._config.max_num_hands,
            self._config.min_detection_confidence,
            self._config.min_tracking_confidence,
        )
        return model

    @staticmethod
    def _validate_bgr_frame(frame_bgr: Frame) -> None:
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise FrameProcessingError(
                "Expected a non-empty BGR frame with exactly three channels."
            )
        if frame_bgr.shape[0] == 0 or frame_bgr.shape[1] == 0:
            raise FrameProcessingError("Expected a non-empty BGR frame.")

    @staticmethod
    def _to_tracking_result(raw_result: Any, width: int, height: int) -> HandTrackingResult:
        raw_hands = raw_result.multi_hand_landmarks or ()
        raw_handedness = raw_result.multi_handedness or ()
        hands: list[DetectedHand] = []

        for index, raw_hand in enumerate(raw_hands):
            normalized_landmarks = tuple(
                NormalizedLandmark(x=landmark.x, y=landmark.y, z=landmark.z)
                for landmark in raw_hand.landmark
            )
            pixel_landmarks = tuple(
                PixelLandmark(*normalized_to_pixel_coordinates(point.x, point.y, width, height))
                for point in normalized_landmarks
            )
            handedness, confidence = HandTracker._extract_handedness(raw_handedness, index)
            hands.append(
                DetectedHand(
                    handedness=handedness,
                    handedness_confidence=confidence,
                    normalized_landmarks=normalized_landmarks,
                    pixel_landmarks=pixel_landmarks,
                )
            )

        return HandTrackingResult(hands=tuple(hands))

    @staticmethod
    def _extract_handedness(raw_handedness: Any, index: int) -> tuple[str | None, float | None]:
        try:
            classification = raw_handedness[index].classification[0]
        except (AttributeError, IndexError, TypeError):
            return None, None
        return classification.label, float(classification.score)


def _validate_confidence(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0.")
