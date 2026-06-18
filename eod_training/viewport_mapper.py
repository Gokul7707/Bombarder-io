"""Full-display viewport mapping — camera FOV maps 1:1 to the entire screen."""

from __future__ import annotations

from typing import List, Tuple


class ViewportMapper:
    """Maps camera-normalized landmarks to full display coordinates."""

    def __init__(self, display_w: int, display_h: int, cam_w: int, cam_h: int) -> None:
        self.display_w = display_w
        self.display_h = display_h
        self.cam_w = max(1, cam_w)
        self.cam_h = max(1, cam_h)
        self._sync_scale()

    def _sync_scale(self) -> None:
        # Camera may not match requested resolution — scale to fill display
        self._sx = self.display_w / self.cam_w
        self._sy = self.display_h / self.cam_h

    def set_display(self, w: int, h: int) -> None:
        self.display_w = w
        self.display_h = h
        self._sync_scale()

    def set_camera(self, w: int, h: int) -> None:
        self.cam_w = max(1, w)
        self.cam_h = max(1, h)
        self._sync_scale()

    def camera_to_display(self, x: int, y: int) -> Tuple[int, int]:
        """Map camera pixel → full display pixel."""
        dx = int(round(x * self._sx))
        dy = int(round(y * self._sy))
        return (
            max(0, min(self.display_w - 1, dx)),
            max(0, min(self.display_h - 1, dy)),
        )

    def norm_to_display(self, nx: float, ny: float) -> Tuple[int, int]:
        """Map normalized 0–1 landmark → full display pixel."""
        return self.camera_to_display(int(nx * self.cam_w), int(ny * self.cam_h))

    def map_landmarks_to_display(
        self, landmarks: List[Tuple[int, int]]
    ) -> List[Tuple[int, int]]:
        return [self.camera_to_display(x, y) for x, y in landmarks]

    @property
    def tracking_rect(self) -> Tuple[int, int, int, int]:
        """Full display is the active tracking zone (x, y, w, h)."""
        return (0, 0, self.display_w, self.display_h)
