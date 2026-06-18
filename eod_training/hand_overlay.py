"""Fast complete FPS hand mesh — palmar + dorsal + wrist, balanced smoothing."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

INDEX_ID = 8
WRIST = 0
THUMB_TIP = 4
MCP_IDS = [5, 9, 13, 17]
FINGER_CHAINS = [
    [0, 1, 2, 3, 4],
    [0, 5, 6, 7, 8],
    [0, 9, 10, 11, 12],
    [0, 13, 14, 15, 16],
    [0, 17, 18, 19, 20],
]

SKIN_FILL = (70, 45, 20)
DORSAL_FILL = (55, 35, 15)
WIRE_OUTER = (255, 195, 50)
WIRE_INNER = (255, 235, 130)
WIRE_GRID = (180, 120, 35)
WIRE_DIM = (110, 70, 22)
THUMBS_GLOW = (0, 255, 200)
PINCH_GLOW = (0, 255, 255)

LEFT_HOME = (0.18, 0.84)
RIGHT_HOME = (0.82, 0.84)
FOLLOW_X = 0.72
FOLLOW_Y = 0.50
SCALE_MULT = 3.6


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.015) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self._x: Optional[float] = None
        self._dx: float = 0.0
        self._t: Optional[float] = None

    def filter(self, value: float, timestamp: float) -> float:
        if self._x is None:
            self._x = value
            self._t = timestamp
            return value
        dt = max(timestamp - self._t, 1e-4)
        dx = (value - self._x) / dt
        alpha_d = self._alpha(dt, 1.0)
        self._dx = alpha_d * dx + (1 - alpha_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        alpha = self._alpha(dt, cutoff)
        self._x = alpha * value + (1 - alpha) * self._x
        self._t = timestamp
        return self._x

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)


class LandmarkSmoother:
    JITTER_GATE = 1.5

    def __init__(self, ema_alpha: float = 0.50, responsive: bool = False) -> None:
        self.ema_alpha = ema_alpha
        self.responsive = responsive
        self._euro: Dict[str, List[List[OneEuroFilter]]] = {}
        self._ema: Dict[str, List[Tuple[float, float]]] = {}

    def reset(self, label: Optional[str] = None) -> None:
        if label:
            keys = [k for k in self._euro if k == label or k.startswith(f"cursor_{label}")]
            for k in keys:
                self._euro.pop(k, None)
                self._ema.pop(k, None)
        else:
            self._euro.clear()
            self._ema.clear()

    def smooth(self, label: str, landmarks: List[Tuple[int, int]], t: float) -> List[Tuple[int, int]]:
        fast = self.responsive or label.startswith("cursor_")
        euro_cut = 1.2 if fast else 0.9
        ema = 0.62 if fast else min(self.ema_alpha, 0.48)

        if label not in self._euro:
            self._euro[label] = [[OneEuroFilter(euro_cut, 0.015) for _ in range(2)] for _ in range(21)]
            self._ema[label] = [(float(x), float(y)) for x, y in landmarks]

        out: List[Tuple[int, int]] = []
        buf = self._ema[label]
        key_ids = {INDEX_ID, THUMB_TIP, WRIST, 5, 9, 13, 17}
        for i, (x, y) in enumerate(landmarks):
            fx = self._euro[label][i][0].filter(float(x), t)
            fy = self._euro[label][i][1].filter(float(y), t)
            ox, oy = buf[i]
            if not fast and math.hypot(fx - ox, fy - oy) < self.JITTER_GATE and i not in key_ids:
                sx, sy = ox, oy
            else:
                sx = ox * (1 - ema) + fx * ema
                sy = oy * (1 - ema) + fy * ema
            buf[i] = (sx, sy)
            out.append((int(round(sx)), int(round(sy))))
        return out


class FPSHandMapper:
    def __init__(self) -> None:
        self._anchor: Dict[str, Tuple[float, float]] = {}
        self._cal_scale: Dict[str, float] = {"left": 1.0, "right": 1.0}

    def apply_calibration(self, profile) -> None:
        self._cal_scale["left"] = getattr(profile, "left_scale", 1.0)
        self._cal_scale["right"] = getattr(profile, "right_scale", 1.0)

    def map_to_screen(self, norm: List[Tuple[float, float, float]], side: str, sw: int, sh: int) -> List[Tuple[int, int]]:
        if len(norm) < 21:
            return []
        wrist = norm[WRIST]
        palm = max(0.06, (math.hypot(norm[5][0] - norm[17][0], norm[5][1] - norm[17][1]) + math.hypot(norm[0][0] - norm[9][0], norm[0][1] - norm[9][1])) * 0.5)
        scale = palm * sh * SCALE_MULT * self._cal_scale.get(side, 1.0)
        home = LEFT_HOME if side == "left" else RIGHT_HOME
        rax = home[0] * sw + (wrist[0] - 0.5) * sw * FOLLOW_X
        ray = home[1] * sh + (wrist[1] - 0.55) * sh * FOLLOW_Y
        prev = self._anchor.get(side, (rax, ray))
        ax = prev[0] * 0.28 + rax * 0.72
        ay = prev[1] * 0.28 + ray * 0.72
        self._anchor[side] = (ax, ay)
        return [(int(ax + (x - wrist[0]) * scale), int(ay + (y - wrist[1]) * scale)) for x, y, _ in norm]


class CompleteHandMesh:
    """Palmar + dorsal + fingers + wrist cuff — one blended draw pass."""

    @staticmethod
    def _offset_dorsal(pts: List[Tuple[int, int]], amount: float) -> List[Tuple[int, int]]:
        w, m = pts[WRIST], pts[9]
        dx, dy = m[0] - w[0], m[1] - w[1]
        ln = math.hypot(dx, dy) or 1.0
        px, py = -dy / ln * amount, dx / ln * amount
        out = []
        for i, (x, y) in enumerate(pts):
            mul = 0.55 if i == WRIST else (0.85 if i in MCP_IDS else 0.65)
            out.append((int(x + px * mul), int(y + py * mul)))
        return out

    def draw(self, frame, pts: List[Tuple[int, int]], side: str, pinching: bool) -> None:
        if len(pts) < 21:
            return
        h = frame.shape[0]
        palm_span = math.hypot(pts[5][0] - pts[17][0], pts[5][1] - pts[17][1])
        dorsal_off = max(8.0, palm_span * 0.14)
        dorsal = self._offset_dorsal(pts, dorsal_off)

        overlay = frame.copy()

        # --- Wrist cuff + forearm ---
        wx, wy = pts[WRIST]
        spread = 42 if side == "right" else -42
        elbow = (wx + spread, min(h - 4, wy + int(h * 0.12)))
        cuff_w = int(palm_span * 0.55)
        cuff = np.array([
            [wx - cuff_w, wy + 6], [wx + cuff_w, wy + 6],
            [elbow[0] + cuff_w // 2, elbow[1]], [elbow[0] - cuff_w // 2, elbow[1]],
        ], np.int32)
        cv2.fillPoly(overlay, [cuff], DORSAL_FILL)
        cv2.polylines(overlay, [cuff], True, WIRE_DIM, 1, cv2.LINE_AA)
        cv2.line(overlay, (wx, wy), elbow, WIRE_DIM, 4, cv2.LINE_AA)
        for off in (-10, 0, 10):
            cv2.line(overlay, (wx + off, wy), (elbow[0] + off, elbow[1]), WIRE_GRID, 1, cv2.LINE_AA)

        # --- Dorsal (back of hand) ---
        dorsal_palm = np.array([dorsal[i] for i in [0, 5, 9, 13, 17]], np.int32)
        cv2.fillPoly(overlay, [dorsal_palm], DORSAL_FILL)
        for i in range(len(MCP_IDS)):
            for j in range(i + 1, len(MCP_IDS)):
                cv2.line(overlay, dorsal[MCP_IDS[i]], dorsal[MCP_IDS[j]], WIRE_GRID, 1, cv2.LINE_AA)
        cv2.line(overlay, dorsal[0], dorsal[9], WIRE_OUTER, 1, cv2.LINE_AA)
        cv2.line(overlay, dorsal[5], dorsal[17], WIRE_OUTER, 1, cv2.LINE_AA)

        # --- Palmar (palm face) ---
        palmar = np.array([pts[i] for i in [0, 5, 9, 13, 17]], np.int32)
        cv2.fillPoly(overlay, [palmar], SKIN_FILL)
        for i in range(len(MCP_IDS)):
            for j in range(i + 1, len(MCP_IDS)):
                cv2.line(overlay, pts[MCP_IDS[i]], pts[MCP_IDS[j]], WIRE_DIM, 1, cv2.LINE_AA)

        # --- Finger bones + side rails (volume) ---
        for chain in FINGER_CHAINS:
            for a, b in zip(chain[:-1], chain[1:]):
                cv2.line(overlay, pts[a], pts[b], WIRE_INNER, 2, cv2.LINE_AA)
                cv2.line(overlay, dorsal[a], dorsal[b], WIRE_OUTER, 1, cv2.LINE_AA)
                if chain[0] != 0:
                    cv2.line(overlay, pts[a], dorsal[a], WIRE_GRID, 1, cv2.LINE_AA)
                    cv2.line(overlay, pts[b], dorsal[b], WIRE_GRID, 1, cv2.LINE_AA)

        # --- Knuckle bridge ---
        for i in MCP_IDS:
            cv2.line(overlay, pts[i], dorsal[i], WIRE_OUTER, 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.68, frame, 0.32, 0, frame)

        if pinching:
            cv2.line(frame, pts[4], pts[8], PINCH_GLOW, 3, cv2.LINE_AA)
            mx = (pts[4][0] + pts[8][0]) // 2
            my = (pts[4][1] + pts[8][1]) // 2
            cv2.circle(frame, (mx, my), 12, PINCH_GLOW, 2, cv2.LINE_AA)


class VirtualHandRenderer:
    def __init__(self) -> None:
        self._mapper = FPSHandMapper()
        self._mesh = CompleteHandMesh()
        self._smooth: Dict[str, List[Tuple[float, float]]] = {}

    def apply_calibration(self, profile) -> None:
        self._mapper.apply_calibration(profile)

    def _smooth_pts(self, key: str, pts: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        prev = self._smooth.setdefault(key, [(float(x), float(y)) for x, y in pts])
        if len(prev) != len(pts):
            prev[:] = [(float(x), float(y)) for x, y in pts]
        out = []
        for i, (x, y) in enumerate(pts):
            ox, oy = prev[i]
            a = 0.55 if i in (INDEX_ID, THUMB_TIP) else 0.48
            sx, sy = ox * (1 - a) + x * a, oy * (1 - a) + y * a
            prev[i] = (sx, sy)
            out.append((int(round(sx)), int(round(sy))))
        return out

    def draw_idle_glove(self, frame, anchor: Tuple[int, int], side: str, pulse: float) -> None:
        off = -50 if side == "left" else 50
        y = anchor[1]
        arr = np.array([
            [anchor[0] + off - 20, y], [anchor[0] + off + 30, y + 20],
            [anchor[0] + off + 25, y + 60], [anchor[0] + off - 25, y + 55],
        ], np.int32)
        cv2.polylines(frame, [arr], True, WIRE_DIM, 2, cv2.LINE_AA)

    def draw_glove(
        self, frame, landmarks, anchor, side: str, gestures: List[str],
        cam_w: int, cam_h: int, norm_landmarks: Optional[List[Tuple[float, float, float]]] = None,
    ) -> None:
        if norm_landmarks:
            raw = self._mapper.map_to_screen(norm_landmarks, side, frame.shape[1], frame.shape[0])
        else:
            raw = self._mapper.map_to_screen(
                [(x / max(cam_w, 1), y / max(cam_h, 1), 0.0) for x, y in landmarks],
                side, frame.shape[1], frame.shape[0],
            )
        if not raw:
            return
        pts = self._smooth_pts(f"mesh_{side}", raw)
        self._mesh.draw(frame, pts, side, "pinch" in gestures)


class HandOverlayRenderer(VirtualHandRenderer):
    def draw(self, *args, **kwargs) -> None:
        pass
