"""FPS counter for runtime performance monitoring."""

from __future__ import annotations

import time
from collections import deque


class FPSCounter:
    def __init__(self, window: int = 30) -> None:
        self._times: deque[float] = deque(maxlen=window)
        self._last_fps = 0.0

    def update(self) -> float:
        now = time.perf_counter()
        self._times.append(now)
        if len(self._times) < 2:
            return 0.0
        elapsed = self._times[-1] - self._times[0]
        if elapsed <= 0:
            return self._last_fps
        self._last_fps = (len(self._times) - 1) / elapsed
        return self._last_fps

    def draw(self, frame, fps: float | None = None, x: int = 12, y: int = 58) -> None:
        import cv2

        fps = fps if fps is not None else self._last_fps
        col = (0, 220, 120) if fps >= 28 else (0, 180, 255) if fps >= 22 else (0, 80, 255)
        label = f"{fps:.0f} FPS - HAND TRACKING" if fps > 0 else "HAND TRACKING"
        cv2.rectangle(frame, (x - 4, y - 16), (x + 210, y + 6), (10, 12, 18), -1)
        cv2.putText(frame, label, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.48, col, 1, cv2.LINE_AA)
