"""Dependency-level tests that do not require a physical webcam."""

from __future__ import annotations

import numpy as np

from gesturelight.hand_tracker import HandTracker, HandTrackerConfig


def test_model_initializes_and_processes_a_blank_bgr_frame() -> None:
    """Verify the pinned MediaPipe API and the BGR-to-RGB processing path."""
    blank_bgr_frame = np.zeros((64, 64, 3), dtype=np.uint8)

    with HandTracker(HandTrackerConfig()) as tracker:
        result = tracker.process(blank_bgr_frame)

    assert result.hand_count == 0
    assert not result.has_hands
