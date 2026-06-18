"""Virtual EOD teleop workspace — chapter scenes with full-screen camera composite."""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from eod_training.animation import ease_in_out_cubic, lerp, pulse

THEME_COLORS = {
    "warehouse": ((18, 22, 32), (28, 32, 48), (40, 90, 60)),
    "school": ((22, 28, 38), (35, 42, 58), (50, 80, 120)),
    "bridge": ((15, 20, 28), (30, 35, 45), (70, 70, 80)),
    "embassy": ((20, 18, 28), (38, 32, 48), (80, 60, 40)),
    "hospital": ((24, 30, 34), (40, 48, 52), (60, 100, 90)),
    "metro": ((12, 14, 18), (25, 28, 35), (55, 55, 65)),
    "chemical": ((16, 22, 18), (30, 40, 32), (40, 100, 50)),
    "command": ((14, 16, 24), (28, 30, 42), (90, 70, 40)),
}


class VirtualWorkspace:
    """Full-frame virtual ops bay with per-chapter environmental art."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pulse = 0.0
        self._bg_blend = 1.0
        self._bg_from = "warehouse"
        self._bg_to = "warehouse"
        self._bg_t = 1.0
        self._scene_cache: Dict[str, np.ndarray] = {}
        self._preview_cache: Dict[str, np.ndarray] = {}
        self._init_layout()

    def _init_layout(self) -> None:
        cx, cy = self.width // 2, self.height // 2 - 20
        self.bench_rect = {"x": cx - 270, "y": cy - 200, "width": 540, "height": 400}
        self.bomb_rect = {"x": cx - 260, "y": cy - 190, "width": 520, "height": 380}
        margin = 35
        self.board_rect = {
            "x": self.bomb_rect["x"] + margin,
            "y": self.bomb_rect["y"] + margin,
            "width": self.bomb_rect["width"] - margin * 2,
            "height": self.bomb_rect["height"] - margin * 2 - 40,
        }
        self.pip_rect = (self.width - 200, 52, 175, 130)

    def set_theme_transition(self, theme: str, speed: float = 0.04) -> None:
        if theme != self._bg_to:
            self._bg_from = self._bg_to
            self._bg_to = theme
            self._bg_t = 0.0
        if self._bg_t < 1.0:
            self._bg_t = min(1.0, self._bg_t + speed)

    def create_scene(self, theme: str = "warehouse") -> np.ndarray:
        self.set_theme_transition(theme)
        t = ease_in_out_cubic(self._bg_t)
        key_a = f"{self._bg_from}_{self.width}_{self.height}"
        key_b = f"{self._bg_to}_{self.width}_{self.height}"
        if key_a not in self._scene_cache:
            self._scene_cache[key_a] = self._build_themed_scene(self._bg_from)
        if t >= 1.0:
            if key_b not in self._scene_cache:
                self._scene_cache[key_b] = self._build_themed_scene(self._bg_to)
            return self._scene_cache[key_b].copy()
        if key_b not in self._scene_cache:
            self._scene_cache[key_b] = self._build_themed_scene(self._bg_to)
        return cv2.addWeighted(self._scene_cache[key_a], 1 - t, self._scene_cache[key_b], t, 0)

    def _build_themed_scene(self, theme: str) -> np.ndarray:
        top, mid, accent = THEME_COLORS.get(theme, THEME_COLORS["warehouse"])
        scene = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        for y in range(self.height):
            t = y / max(1, self.height - 1)
            c = tuple(int(top[i] * (1 - t) + mid[i] * t) for i in range(3))
            scene[y, :] = c

        horizon = int(self.height * 0.52)
        cv2.line(scene, (0, horizon), (self.width, horizon), accent, 1, cv2.LINE_AA)
        self._draw_perspective_grid(scene, horizon)

        painters = {
            "warehouse": self._paint_warehouse,
            "school": self._paint_school,
            "bridge": self._paint_bridge,
            "embassy": self._paint_embassy,
            "hospital": self._paint_hospital,
            "metro": self._paint_metro,
            "chemical": self._paint_chemical,
            "command": self._paint_command,
        }
        painters.get(theme, self._paint_warehouse)(scene, horizon, accent)

        if theme not in ("warehouse",):
            self._draw_workbench(scene, alpha=0.35)
        else:
            self._draw_workbench(scene)
        self._draw_ambient_lights(scene, accent)
        self._draw_vignette(scene)
        return scene

    def _draw_vignette(self, frame) -> None:
        h, w = frame.shape[:2]
        overlay = np.zeros_like(frame)
        cv2.ellipse(overlay, (w // 2, h // 2), (w // 2 + 40, h // 2 + 60), 0, 0, 360, (20, 20, 30), -1)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.ellipse(mask, (w // 2, h // 2), (int(w * 0.48), int(h * 0.48)), 0, 0, 360, 255, -1)
        inv = cv2.bitwise_not(mask)
        for c in range(3):
            frame[:, :, c] = np.where(inv > 0, (frame[:, :, c] * 0.55).astype(np.uint8), frame[:, :, c])

    def _paint_warehouse(self, frame, horizon: int, accent) -> None:
        for i in range(5):
            x = 80 + i * 220
            h = 60 + i * 25
            cv2.rectangle(frame, (x, horizon - h), (x + 140, horizon), (32, 36, 44), -1)
            cv2.rectangle(frame, (x + 10, horizon - h + 20), (x + 50, horizon - 10), (50, 55, 65), -1)

    def _paint_school(self, frame, horizon: int, accent) -> None:
        # School building silhouette
        bx = self.width // 2 - 200
        cv2.rectangle(frame, (bx, horizon - 140), (bx + 400, horizon), (45, 50, 70), -1)
        for wx in range(bx + 30, bx + 370, 55):
            cv2.rectangle(frame, (wx, horizon - 120), (wx + 35, horizon - 60), (80, 100, 140), -1)
        cv2.rectangle(frame, (bx + 160, horizon - 50), (bx + 240, horizon), (60, 65, 80), -1)
        # Flag pole
        cv2.line(frame, (bx + 380, horizon - 160), (bx + 380, horizon), (90, 90, 100), 2)
        cv2.rectangle(frame, (bx + 382, horizon - 155), (bx + 420, horizon - 135), (40, 60, 180), -1)
        cv2.putText(frame, "RIVERSIDE HIGH", (bx + 80, horizon - 155), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 210, 230), 1, cv2.LINE_AA)

    def _paint_bridge(self, frame, horizon: int, accent) -> None:
        for i in range(-6, 7):
            xb = self.width // 2 + i * 70
            cv2.line(frame, (xb, horizon - 80), (xb, horizon + 30), (55, 58, 68), 3, cv2.LINE_AA)
        cv2.line(frame, (0, horizon - 60), (self.width, horizon - 55), (70, 72, 82), 4, cv2.LINE_AA)
        water_y = horizon + 20
        for x in range(0, self.width, 30):
            cv2.line(frame, (x, water_y), (x + 20, water_y + 8), (30, 50, 70), 1, cv2.LINE_AA)

    def _paint_embassy(self, frame, horizon: int, accent) -> None:
        cv2.rectangle(frame, (self.width // 2 - 180, horizon - 160), (self.width // 2 + 180, horizon), (38, 35, 50), -1)
        for col in range(6):
            cx = self.width // 2 - 150 + col * 55
            cv2.rectangle(frame, (cx, horizon - 130), (cx + 30, horizon - 70), accent, -1)
        cv2.rectangle(frame, (self.width // 2 - 40, horizon - 45), (self.width // 2 + 40, horizon), (55, 50, 45), -1)

    def _paint_hospital(self, frame, horizon: int, accent) -> None:
        cv2.rectangle(frame, (120, horizon - 130), (320, horizon), (50, 58, 62), -1)
        cx, cy = 220, horizon - 80
        cv2.rectangle(frame, (cx - 35, cy - 8), (cx + 35, cy + 8), (200, 200, 210), -1)
        cv2.rectangle(frame, (cx - 8, cy - 35), (cx + 8, cy + 35), (200, 200, 210), -1)
        cv2.putText(frame, "ST. MARY'S ER", (130, horizon - 140), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 200, 195), 1, cv2.LINE_AA)

    def _paint_metro(self, frame, horizon: int, accent) -> None:
        cv2.rectangle(frame, (0, horizon - 20), (self.width, horizon + 80), (22, 24, 28), -1)
        for x in range(0, self.width, 80):
            cv2.line(frame, (x, horizon - 100), (x, horizon + 60), (40, 42, 48), 2, cv2.LINE_AA)
        cv2.line(frame, (0, horizon + 40), (self.width, horizon + 40), (60, 60, 70), 3, cv2.LINE_AA)
        # Water reflection
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, horizon + 45), (self.width, horizon + 90), (20, 40, 60), -1)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

    def _paint_chemical(self, frame, horizon: int, accent) -> None:
        for i in range(4):
            x = 150 + i * 250
            cv2.rectangle(frame, (x, horizon - 100 - i * 10), (x + 80, horizon), (35, 45, 38), -1)
            cv2.circle(frame, (x + 40, horizon - 110 - i * 10), 25, (30, 80, 40), 2, cv2.LINE_AA)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, horizon - 30), (self.width, horizon), (20, 60, 30), -1)
        cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)

    def _paint_command(self, frame, horizon: int, accent) -> None:
        cv2.rectangle(frame, (self.width // 2 - 220, horizon - 150), (self.width // 2 + 220, horizon), (30, 32, 42), -1)
        for i in range(8):
            lx = self.width // 2 - 190 + i * 50
            col = accent if i % 2 == 0 else (50, 45, 35)
            cv2.rectangle(frame, (lx, horizon - 120), (lx + 35, horizon - 80), col, -1)
        cv2.putText(frame, "FORWARD COMMAND POST", (self.width // 2 - 160, horizon - 160), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 180, 100), 1, cv2.LINE_AA)

    def _draw_perspective_grid(self, frame, horizon: int) -> None:
        vanish = (self.width // 2, horizon - 30)
        for i in range(-8, 9):
            xb = self.width // 2 + i * 90
            cv2.line(frame, vanish, (xb, self.height), (35, 40, 50), 1, cv2.LINE_AA)
        for row in range(6):
            t = (row + 1) / 7.0
            y = int(horizon + (self.height - horizon) * t)
            half = int(self.width * 0.15 + self.width * 0.42 * t)
            cv2.line(frame, (vanish[0] - half, y), (vanish[0] + half, y), (30, 35, 45), 1, cv2.LINE_AA)

    def _draw_workbench(self, frame, alpha: float = 1.0) -> None:
        r = self.bench_rect
        x, y, w, h = r["x"], r["y"], r["width"], r["height"]
        pts = np.array([[x, y + 20], [x + w, y + 20], [x + w + 18, y + h], [x - 18, y + h]], np.int32)
        if alpha < 1.0:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], (42, 44, 50))
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
        else:
            cv2.fillPoly(frame, [pts], (42, 44, 50))
            cv2.polylines(frame, [pts], True, (70, 72, 78), 2, cv2.LINE_AA)

    def _draw_ambient_lights(self, frame, accent: Tuple[int, int, int]) -> None:
        overlay = frame.copy()
        cv2.circle(overlay, (self.width // 4, 80), 120, accent, -1, cv2.LINE_AA)
        cv2.circle(overlay, (3 * self.width // 4, 90), 100, (0, 80, 120), -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)

    def draw_header(self, frame, title: str, subtitle: str = "") -> None:
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (self.width, 40), (8, 10, 16), -1)
        cv2.addWeighted(overlay, 0.9, frame, 0.1, 0, frame)
        cv2.line(frame, (0, 40), (self.width, 40), (0, 160, 220), 1, cv2.LINE_AA)
        cv2.putText(frame, title[:72], (14, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 210, 255), 1, cv2.LINE_AA)
        if subtitle:
            cv2.putText(frame, subtitle[:60], (self.width - 480, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 130, 140), 1, cv2.LINE_AA)

    def draw_story_panel(self, frame, story: Dict, chapter: int) -> None:
        if not story:
            return
        x, y, w, h = 470, 48, self.width - 490, 100
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (10, 12, 18), -1)
        cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 160, 210), 1)
        cv2.putText(frame, f"CH.{chapter} — {story.get('victim', 'Unknown')}", (x + 12, y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1)
        cv2.putText(frame, story.get("location", "")[:58], (x + 12, y + 46), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 150, 160), 1)
        cv2.putText(frame, story.get("briefing", "")[:72], (x + 12, y + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (200, 205, 210), 1)

    def draw_chapter_preview(
        self, frame, mission: Dict, selected: bool, rect: Optional[Tuple[int, int, int, int]] = None
    ) -> None:
        """Large preview panel for chapter select."""
        if rect:
            x, y, w, h = rect
        else:
            x, y = self.width - 420, 58
            w, h = 390, self.height - 180
        theme = mission.get("theme", "warehouse")
        cache_key = f"{theme}_{w}_{h}"
        if cache_key not in self._preview_cache:
            preview = self._build_themed_scene(theme)
            self._preview_cache[cache_key] = cv2.resize(preview, (w, h))
        preview = self._preview_cache[cache_key]
        border_col = (0, 220, 255) if selected else (60, 70, 80)
        cv2.rectangle(frame, (x - 3, y - 3), (x + w + 3, y + h + 3), border_col, 2, cv2.LINE_AA)
        frame[y : y + h, x : x + w] = preview

        story = mission.get("story", {})
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y + h - 90), (x + w, y + h), (8, 10, 16), -1)
        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        cv2.putText(frame, story.get("victim", "")[:28], (x + 12, y + h - 62), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 200, 255), 1)
        cv2.putText(frame, story.get("location", "")[:40], (x + 12, y + h - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (150, 160, 170), 1)
        cv2.putText(frame, mission.get("tier", ""), (x + w - 90, y + h - 62), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 180, 80), 1)

    def draw_pip(self, frame, camera_frame) -> None:
        """Corner camera preview — hand tracking still covers the full display."""
        x, y, w, h = self.pip_rect
        cam = cv2.resize(camera_frame, (w, h), interpolation=cv2.INTER_LINEAR)
        cv2.rectangle(frame, (x - 2, y - 2), (x + w + 2, y + h + 2), (0, 180, 255), 1, cv2.LINE_AA)
        frame[y : y + h, x : x + w] = cam
        cv2.putText(frame, "CAM PREVIEW", (x + 6, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "track: full display", (x + 6, y + h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (100, 180, 200), 1, cv2.LINE_AA)

    def draw_tracking_fov(self, frame) -> None:
        """Light border — backend maps camera hands across entire display."""
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (40, 90, 60), 1, cv2.LINE_AA)

    def apply_calibration(self, profile) -> None:
        pass
