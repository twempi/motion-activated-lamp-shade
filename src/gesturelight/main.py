"""Command-line application loop for GestureLight's webcam hand tracker."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from gesturelight import camera as camera_module
from gesturelight.camera import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    Camera,
    CameraConfig,
    CameraError,
    Frame,
)
from gesturelight.hand_tracker import (
    DEFAULT_MAX_NUM_HANDS,
    DEFAULT_MIN_DETECTION_CONFIDENCE,
    DEFAULT_MIN_TRACKING_CONFIDENCE,
    DEFAULT_MODEL_COMPLEXITY,
    HandTracker,
    HandTrackerConfig,
    HandTrackerError,
    HandTrackingResult,
)

logger = logging.getLogger(__name__)

WINDOW_TITLE = "GestureLight Hand Tracking"
DEFAULT_LOG_LEVEL = "INFO"

FPS_SMOOTHING_WEIGHT = 0.9
KEY_POLL_DELAY_MS = 1
QUIT_KEY = ord("q")
ESCAPE_KEY = 27
HORIZONTAL_FLIP_CODE = 1

OVERLAY_LEFT_MARGIN_PX = 10
OVERLAY_TOP_MARGIN_PX = 25
OVERLAY_LINE_HEIGHT_PX = 25
OVERLAY_FONT_SCALE = 0.6
OVERLAY_TEXT_COLOR_BGR = (255, 255, 255)
OVERLAY_OUTLINE_COLOR_BGR = (0, 0, 0)
OVERLAY_OUTLINE_THICKNESS = 3
OVERLAY_TEXT_THICKNESS = 1


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configuration assembled from command-line arguments."""

    camera: CameraConfig
    tracker: HandTrackerConfig
    mirror: bool = True
    camera_only: bool = False
    log_level: str = DEFAULT_LOG_LEVEL


class FrameRateMeter:
    """Measure loop FPS using a monotonic, high-resolution timer."""

    def __init__(self) -> None:
        self._last_timestamp: float | None = None
        self._fps = 0.0

    def update(self, timestamp: float) -> float:
        """Record a completed frame and return a lightly smoothed FPS value."""
        previous_timestamp, self._last_timestamp = self._last_timestamp, timestamp
        if previous_timestamp is None:
            return self._fps

        elapsed_seconds = timestamp - previous_timestamp
        if elapsed_seconds <= 0:
            return self._fps

        instantaneous_fps = 1.0 / elapsed_seconds
        if self._fps == 0.0:
            self._fps = instantaneous_fps
        else:
            self._fps = (
                FPS_SMOOTHING_WEIGHT * self._fps + (1.0 - FPS_SMOOTHING_WEIGHT) * instantaneous_fps
            )
        return self._fps


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the small command-line interface used during development."""
    parser = argparse.ArgumentParser(
        description="Display a webcam feed with MediaPipe hand landmarks for GestureLight."
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=DEFAULT_CAMERA_INDEX,
        help="OpenCV camera index to use (default: %(default)s).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_FRAME_WIDTH,
        help="Requested camera frame width in pixels (default: %(default)s).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_FRAME_HEIGHT,
        help="Requested camera frame height in pixels (default: %(default)s).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Requested camera FPS. Omit to let the driver choose.",
    )
    parser.add_argument(
        "--max-hands",
        type=int,
        default=DEFAULT_MAX_NUM_HANDS,
        help="Maximum hands for MediaPipe to track (default: %(default)s).",
    )
    parser.add_argument(
        "--model-complexity",
        type=int,
        choices=(0, 1),
        default=DEFAULT_MODEL_COMPLEXITY,
        help="MediaPipe hand-model complexity: 0 (lighter) or 1 (default).",
    )
    parser.add_argument(
        "--min-detection-confidence",
        type=float,
        default=DEFAULT_MIN_DETECTION_CONFIDENCE,
        help="Minimum confidence to detect a new hand (default: %(default)s).",
    )
    parser.add_argument(
        "--min-tracking-confidence",
        type=float,
        default=DEFAULT_MIN_TRACKING_CONFIDENCE,
        help="Minimum confidence to continue tracking a hand (default: %(default)s).",
    )
    parser.add_argument(
        "--no-mirror",
        action="store_false",
        dest="mirror",
        help="Do not mirror the preview horizontally.",
    )
    parser.set_defaults(mirror=True)
    parser.add_argument(
        "--camera-only",
        action="store_true",
        help="Show only the webcam/FPS diagnostic; do not start MediaPipe.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=DEFAULT_LOG_LEVEL,
        help="Terminal log verbosity (default: %(default)s).",
    )
    return parser


def parse_args(arguments: Sequence[str] | None = None) -> ApplicationConfig:
    """Parse and validate command-line arguments into typed application settings."""
    parser = build_argument_parser()
    args = parser.parse_args(arguments)
    try:
        return ApplicationConfig(
            camera=CameraConfig(
                index=args.camera_index,
                width=args.width,
                height=args.height,
                fps=args.fps,
            ),
            tracker=HandTrackerConfig(
                max_num_hands=args.max_hands,
                model_complexity=args.model_complexity,
                min_detection_confidence=args.min_detection_confidence,
                min_tracking_confidence=args.min_tracking_confidence,
            ),
            mirror=args.mirror,
            camera_only=args.camera_only,
            log_level=args.log_level,
        )
    except ValueError as error:
        parser.error(str(error))
        raise AssertionError("argparse.error always raises SystemExit") from error


def configure_logging(log_level: str) -> None:
    """Configure concise terminal diagnostics once at application startup."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_debug_lines(fps: float, tracking_result: HandTrackingResult | None) -> tuple[str, ...]:
    """Create UI diagnostic text without coupling it to OpenCV calls."""
    if tracking_result is None:
        return (
            f"FPS: {fps:.1f}",
            "Hand tracking: disabled (--camera-only)",
        )

    hand_state = "detected" if tracking_result.has_hands else "none detected"
    lines = [
        f"FPS: {fps:.1f}",
        f"Hands: {tracking_result.hand_count} ({hand_state})",
    ]

    handedness = []
    for hand in tracking_result.hands:
        if hand.handedness is None:
            handedness.append("unknown")
        elif hand.handedness_confidence is None:
            handedness.append(hand.handedness)
        else:
            handedness.append(f"{hand.handedness} ({hand.handedness_confidence:.2f})")
    lines.append(f"Handedness: {', '.join(handedness) if handedness else 'n/a'}")
    return tuple(lines)


def run(config: ApplicationConfig) -> int:
    """Open resources, run the preview loop, and clean them up on every exit path."""
    opencv = camera_module.cv2
    if opencv is None:
        logger.error("OpenCV is not installed. Enter the Nix shell and run 'uv sync'.")
        return 1

    try:
        with Camera(config.camera) as camera:
            if config.camera_only:
                logger.info("Starting webcam-only diagnostic mode.")
                return _run_preview_loop(camera, None, config, opencv)

            with HandTracker(config.tracker) as tracker:
                return _run_preview_loop(camera, tracker, config, opencv)
    except (CameraError, HandTrackerError) as error:
        logger.error("GestureLight could not continue: %s", error)
        logger.debug("Detailed startup or processing error:", exc_info=True)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted; shutting down GestureLight.")
        return 0
    except opencv.error as error:
        logger.error("OpenCV could not display or process the video feed: %s", error)
        logger.debug("Detailed OpenCV error:", exc_info=True)
        return 1
    finally:
        _destroy_opencv_windows(opencv)


def _run_preview_loop(
    camera: Camera,
    tracker: HandTracker | None,
    config: ApplicationConfig,
    opencv: Any,
) -> int:
    """Continuously capture, optionally track hands, and display diagnostics."""
    opencv.namedWindow(WINDOW_TITLE, opencv.WINDOW_NORMAL)
    frame_rate_meter = FrameRateMeter()
    previous_hand_count: int | None = None

    while True:
        frame = camera.read()
        if frame is None:
            logger.error("Stopping because camera frame capture failed.")
            return 1

        if config.mirror:
            # A mirrored selfie-style preview is more intuitive for a user and
            # matches MediaPipe's handedness convention for camera input.
            frame = opencv.flip(frame, HORIZONTAL_FLIP_CODE)

        tracking_result: HandTrackingResult | None = None
        if tracker is not None:
            tracking_result = tracker.process(frame)
            tracker.draw_landmarks(frame, tracking_result)
            if tracking_result.hand_count != previous_hand_count:
                logger.info("Hand detection changed: %s hand(s).", tracking_result.hand_count)
                previous_hand_count = tracking_result.hand_count

        # This time delta includes capture, model inference, rendering, and the
        # previous event wait, so it describes the actual displayed loop rate.
        fps = frame_rate_meter.update(time.perf_counter())
        _draw_debug_overlay(frame, build_debug_lines(fps, tracking_result), opencv)
        opencv.imshow(WINDOW_TITLE, frame)

        pressed_key = opencv.waitKey(KEY_POLL_DELAY_MS) & 0xFF
        if pressed_key in (QUIT_KEY, ESCAPE_KEY):
            logger.info("Exit key received; shutting down GestureLight.")
            return 0


def _draw_debug_overlay(frame: Frame, lines: tuple[str, ...], opencv: Any) -> None:
    """Render readable white debug text with a dark outline over the preview."""
    for line_index, line in enumerate(lines):
        position = (
            OVERLAY_LEFT_MARGIN_PX,
            OVERLAY_TOP_MARGIN_PX + line_index * OVERLAY_LINE_HEIGHT_PX,
        )
        opencv.putText(
            frame,
            line,
            position,
            opencv.FONT_HERSHEY_SIMPLEX,
            OVERLAY_FONT_SCALE,
            OVERLAY_OUTLINE_COLOR_BGR,
            OVERLAY_OUTLINE_THICKNESS,
            opencv.LINE_AA,
        )
        opencv.putText(
            frame,
            line,
            position,
            opencv.FONT_HERSHEY_SIMPLEX,
            OVERLAY_FONT_SCALE,
            OVERLAY_TEXT_COLOR_BGR,
            OVERLAY_TEXT_THICKNESS,
            opencv.LINE_AA,
        )


def _destroy_opencv_windows(opencv: Any) -> None:
    """Close OpenCV windows without hiding the application's primary error."""
    try:
        opencv.destroyAllWindows()
    except Exception:
        logger.debug("Could not destroy one or more OpenCV windows.", exc_info=True)


def main(arguments: Sequence[str] | None = None) -> int:
    """Console-script entry point."""
    config = parse_args(arguments)
    configure_logging(config.log_level)
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
