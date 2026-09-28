"""OpenCV webcam capture with explicit configuration and cleanup."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Self

import numpy as np
from numpy.typing import NDArray

try:
    import cv2
except ImportError:  # Let the command-line program provide a helpful error.
    cv2: Any | None = None


logger = logging.getLogger(__name__)

DEFAULT_CAMERA_INDEX = 0
DEFAULT_FRAME_WIDTH = 1280
DEFAULT_FRAME_HEIGHT = 720

Frame = NDArray[np.uint8]


class CameraError(RuntimeError):
    """Raised when the webcam cannot be opened, configured, or read."""


@dataclass(frozen=True, slots=True)
class CameraConfig:
    """Requested webcam settings.

    Width, height, and FPS are requests: a webcam driver can choose the
    closest mode it supports. The actual values are logged when the camera
    opens.
    """

    index: int = DEFAULT_CAMERA_INDEX
    width: int | None = DEFAULT_FRAME_WIDTH
    height: int | None = DEFAULT_FRAME_HEIGHT
    fps: float | None = None
    backend: int | None = None

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("Camera index must be zero or greater.")
        if self.width is not None and self.width <= 0:
            raise ValueError("Requested camera width must be positive.")
        if self.height is not None and self.height <= 0:
            raise ValueError("Requested camera height must be positive.")
        if self.fps is not None and self.fps <= 0:
            raise ValueError("Requested camera FPS must be positive.")
        if self.backend is not None and self.backend < 0:
            raise ValueError("OpenCV backend identifier must be zero or greater.")


class Camera:
    """Own one ``cv2.VideoCapture`` instance and release it deterministically."""

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._capture: Any | None = None

    @property
    def config(self) -> CameraConfig:
        """Return the requested camera configuration."""
        return self._config

    @property
    def is_open(self) -> bool:
        """Whether this wrapper currently owns an open capture device."""
        return self._capture is not None

    def open(self) -> None:
        """Open and configure the requested webcam.

        Raises:
            CameraError: If OpenCV is unavailable or the webcam cannot be used.
        """
        if self._capture is not None:
            return
        if cv2 is None:
            raise CameraError("OpenCV is not installed. Enter the Nix shell and run 'uv sync'.")

        try:
            capture = self._create_capture()
        except Exception as error:
            raise CameraError(
                f"Could not create a capture for camera index {self._config.index}."
            ) from error

        if not capture.isOpened():
            capture.release()
            raise CameraError(
                f"Could not open camera index {self._config.index}. "
                "Check the index, permissions, and whether another program is using it."
            )

        try:
            self._configure_capture(capture)
        except Exception as error:
            capture.release()
            raise CameraError(f"Could not configure camera index {self._config.index}.") from error

        self._capture = capture
        self._log_reported_properties(capture)

    def read(self) -> Frame | None:
        """Return one BGR video frame, or ``None`` when capture fails.

        OpenCV frames are BGR-ordered by default. The hand tracker converts
        them to RGB only for MediaPipe; the UI continues to draw on BGR frames.
        """
        if self._capture is None:
            raise CameraError("Cannot read a frame before the camera has been opened.")

        try:
            success, frame = self._capture.read()
        except Exception as error:
            raise CameraError(
                f"An error occurred while reading camera index {self._config.index}."
            ) from error

        if not success or frame is None:
            logger.warning("Camera index %s returned no frame.", self._config.index)
            return None
        return frame

    def release(self) -> None:
        """Release the webcam. Safe to call more than once."""
        if self._capture is None:
            return

        capture, self._capture = self._capture, None
        try:
            capture.release()
            logger.info("Released camera index %s.", self._config.index)
        except Exception:
            logger.warning(
                "An error occurred while releasing camera index %s.",
                self._config.index,
                exc_info=True,
            )

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def _create_capture(self) -> Any:
        if self._config.backend is None:
            return cv2.VideoCapture(self._config.index)
        return cv2.VideoCapture(self._config.index, self._config.backend)

    def _configure_capture(self, capture: Any) -> None:
        if self._config.width is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
        if self._config.height is not None:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
        if self._config.fps is not None:
            capture.set(cv2.CAP_PROP_FPS, self._config.fps)

    def _log_reported_properties(self, capture: Any) -> None:
        """Log driver-selected settings without making diagnostics a failure point."""
        try:
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = capture.get(cv2.CAP_PROP_FPS)
        except Exception:
            logger.debug("Could not read the webcam's reported properties.", exc_info=True)
            return

        logger.info(
            "Opened camera index %s; driver reports %sx%s at %.1f FPS.",
            self._config.index,
            width,
            height,
            fps,
        )
