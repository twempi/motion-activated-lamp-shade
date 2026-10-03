"""Rendering-independent hand gestures for GestureLight controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot

from gesturelight.hand_tracker import DetectedHand, HandTrackingResult, NormalizedLandmark

THUMB_TIP_INDEX = 4
INDEX_FINGER_TIP_INDEX = 8
WRIST_INDEX = 0
MIDDLE_FINGER_MCP_INDEX = 9
FINGER_TIP_INDICES = (8, 12, 16, 20)
FINGER_PIP_INDICES = (6, 10, 14, 18)

DEFAULT_PINCH_DISTANCE_RATIO = 0.15
DEFAULT_BRIGHTNESS_STEP_RATIO = 0.15
DEFAULT_POWER_FIST_STABLE_FRAMES = 3
DEFAULT_POWER_REARM_FRAMES = 3
FINGER_EXTENSION_RATIO = 1.25
FIST_MAX_EXTENDED_FINGERS = 0
OPEN_MIN_EXTENDED_FINGERS = 4


class LampGestureAction(Enum):
    """A physical button action requested by a recognized hand gesture."""

    POWER = "power"
    BRIGHTNESS_UP = "brightness_up"
    BRIGHTNESS_DOWN = "brightness_down"


@dataclass(frozen=True, slots=True)
class HandGestureConfig:
    """Calibration values for the power and brightness gestures."""

    pinch_distance_ratio: float = DEFAULT_PINCH_DISTANCE_RATIO
    brightness_step_ratio: float = DEFAULT_BRIGHTNESS_STEP_RATIO
    power_fist_stable_frames: int = DEFAULT_POWER_FIST_STABLE_FRAMES
    power_rearm_frames: int = DEFAULT_POWER_REARM_FRAMES

    def __post_init__(self) -> None:
        if self.pinch_distance_ratio <= 0:
            raise ValueError("Pinch distance ratio must be greater than zero.")
        if self.brightness_step_ratio <= 0:
            raise ValueError("Brightness step ratio must be greater than zero.")
        if self.power_fist_stable_frames < 1:
            raise ValueError("Power fist stable frames must be at least one.")
        if self.power_rearm_frames < 0:
            raise ValueError("Power rearm frames cannot be negative.")


class HandGestureController:
    """Recognize fist-to-open power and pinch-to-move brightness gestures."""

    def __init__(self, config: HandGestureConfig) -> None:
        self._config = config
        self._fist_frames = 0
        self._power_armed = False
        self._power_rearm_frames = config.power_rearm_frames
        self._pinch_origin_y: float | None = None

    def update(self, result: HandTrackingResult) -> LampGestureAction | None:
        """Return at most one control action for the current landmark frame."""
        if not result.hands:
            self._reset()
            return None

        hand = result.hands[0]
        if self._is_pinching(hand):
            self._reset_power_after_pinch()
            return self._brightness_action(hand)

        self._pinch_origin_y = None
        if self._power_rearm_frames < self._config.power_rearm_frames:
            self._power_rearm_frames += 1
            return None

        if self._is_fist(hand):
            self._fist_frames += 1
            if self._fist_frames >= self._config.power_fist_stable_frames:
                self._power_armed = True
            return None

        self._fist_frames = 0
        if self._power_armed and self._is_open_hand(hand):
            self._power_armed = False
            return LampGestureAction.POWER
        return None

    def _brightness_action(self, hand: DetectedHand) -> LampGestureAction | None:
        palm_scale = self._palm_scale(hand)
        if palm_scale <= 0:
            self._pinch_origin_y = None
            return None

        wrist_y = hand.normalized_landmarks[WRIST_INDEX].y
        if self._pinch_origin_y is None:
            self._pinch_origin_y = wrist_y
            return None

        movement = wrist_y - self._pinch_origin_y
        if abs(movement) < palm_scale * self._config.brightness_step_ratio:
            return None

        self._pinch_origin_y = wrist_y
        return (
            LampGestureAction.BRIGHTNESS_DOWN if movement > 0 else LampGestureAction.BRIGHTNESS_UP
        )

    def _is_pinching(self, hand: DetectedHand) -> bool:
        if not self._has_required_landmarks(hand):
            return False

        landmarks = hand.normalized_landmarks
        pinch_distance = self._distance(
            landmarks[THUMB_TIP_INDEX], landmarks[INDEX_FINGER_TIP_INDEX]
        )
        return pinch_distance <= self._palm_scale(hand) * self._config.pinch_distance_ratio

    def _is_fist(self, hand: DetectedHand) -> bool:
        return (
            self._has_required_landmarks(hand)
            and self._extended_finger_count(hand) <= FIST_MAX_EXTENDED_FINGERS
        )

    def _is_open_hand(self, hand: DetectedHand) -> bool:
        return (
            self._has_required_landmarks(hand)
            and self._extended_finger_count(hand) >= OPEN_MIN_EXTENDED_FINGERS
        )

    def _extended_finger_count(self, hand: DetectedHand) -> int:
        if not self._has_required_landmarks(hand):
            return 0

        landmarks = hand.normalized_landmarks
        wrist = landmarks[WRIST_INDEX]
        return sum(
            self._distance(landmarks[tip_index], wrist)
            > self._distance(landmarks[pip_index], wrist) * FINGER_EXTENSION_RATIO
            for tip_index, pip_index in zip(FINGER_TIP_INDICES, FINGER_PIP_INDICES, strict=True)
        )

    def _palm_scale(self, hand: DetectedHand) -> float:
        if not self._has_required_landmarks(hand):
            return 0.0
        landmarks = hand.normalized_landmarks
        return self._distance(landmarks[WRIST_INDEX], landmarks[MIDDLE_FINGER_MCP_INDEX])

    @staticmethod
    def _distance(first: NormalizedLandmark, second: NormalizedLandmark) -> float:
        return hypot(first.x - second.x, first.y - second.y, first.z - second.z)

    @staticmethod
    def _has_required_landmarks(hand: DetectedHand) -> bool:
        return len(hand.normalized_landmarks) > max(FINGER_TIP_INDICES)

    def _reset(self) -> None:
        self._fist_frames = 0
        self._power_armed = False
        self._power_rearm_frames = self._config.power_rearm_frames
        self._pinch_origin_y = None

    def _reset_power_after_pinch(self) -> None:
        self._fist_frames = 0
        self._power_armed = False
        self._power_rearm_frames = 0
