"""On-screen hand UI — point target on button, hold to activate (no pinch)."""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import cv2

_TRACKING_CHAINS = [
    [0, 1, 2, 3, 4],
    [0, 5, 6, 7, 8],
    [0, 9, 10, 11, 12],
    [0, 13, 14, 15, 16],
    [0, 17, 18, 19, 20],
]


class HandUIController:
    """Dual-hand pointer UI: place fingertip target on button, hold to confirm."""

    DEFAULT_HOLD = 0.65

    def __init__(self) -> None:
        self._hold_key: Optional[str] = None
        self._hold_start: float = 0.0
        self._hold_hand: Optional[str] = None
        self._gesture_key: Optional[str] = None
        self._gesture_start: float = 0.0

    def reset_holds(self) -> None:
        self._hold_key = None
        self._hold_start = 0.0
        self._hold_hand = None
        self._gesture_key = None
        self._gesture_start = 0.0

    @staticmethod
    def point_in_rect(
        point: Optional[Tuple[int, int]], rect: Tuple[int, int, int, int], pad: int = 12
    ) -> bool:
        if point is None:
            return False
        x, y = point
        rx, ry, rw, rh = rect
        return (rx - pad) <= x <= (rx + rw + pad) and (ry - pad) <= y <= (ry + rh + pad)

    @staticmethod
    def _target_point(hand: Dict) -> Optional[Tuple[int, int]]:
        """Index fingertip is the aim target (like skeletal tracking)."""
        return hand.get("screen_tip") or hand.get("index_tip")

    def get_hand_cursors(self, hand_data: Dict) -> Dict[str, Tuple[int, int]]:
        cursors: Dict[str, Tuple[int, int]] = {}
        for side in ("left", "right"):
            hand = hand_data.get(f"{side}_hand")
            if hand:
                tip = self._target_point(hand)
                if tip:
                    cursors[side] = tip
        return cursors

    def _hand_on_target(
        self, hand_data: Dict, rect: Tuple[int, int, int, int], pad: int = 12
    ) -> Optional[str]:
        for side in ("left", "right"):
            hand = hand_data.get(f"{side}_hand")
            if not hand:
                continue
            tip = self._target_point(hand)
            if tip and self.point_in_rect(tip, rect, pad=pad):
                return side
        return None

    def get_cursor(self, hand_data: Dict, rect: Optional[Tuple[int, int, int, int]] = None) -> Optional[Tuple[int, int]]:
        cursors = self.get_hand_cursors(hand_data)
        if not cursors:
            return hand_data.get("primary_center")
        if rect is not None:
            on = self._hand_on_target(hand_data, rect)
            if on:
                return cursors[on]
            rx, ry, rw, rh = rect
            cx, cy = rx + rw // 2, ry + rh // 2
            best, dist = None, float("inf")
            for tip in cursors.values():
                d = math.hypot(tip[0] - cx, tip[1] - cy)
                if d < dist:
                    dist, best = d, tip
            return best
        return cursors.get("right") or cursors.get("left") or hand_data.get("primary_center")

    def hold_confirm(
        self,
        hand_data: Dict,
        key: str,
        rect: Tuple[int, int, int, int],
        duration: float = DEFAULT_HOLD,
        require_pinch: bool = False,
        blocked: bool = False,
    ) -> Tuple[bool, float]:
        """Hover target on button and hold — opens when progress completes."""
        if blocked:
            if self._hold_key == key:
                self._hold_key = None
                self._hold_hand = None
            return False, 0.0

        on_side = self._hand_on_target(hand_data, rect)
        active = on_side is not None

        if not active:
            if self._hold_key == key:
                self._hold_key = None
                self._hold_hand = None
            return False, 0.0

        if self._hold_key != key or self._hold_hand != on_side:
            self._hold_key = key
            self._hold_hand = on_side
            self._hold_start = time.time()

        elapsed = time.time() - self._hold_start
        if elapsed >= duration:
            self._hold_key = None
            self._hold_hand = None
            return True, 1.0
        return False, min(1.0, elapsed / duration)

    def gesture_hold(
        self,
        hand_data: Dict,
        gesture: str,
        duration: float = 1.0,
        *,
        blocked: bool = False,
    ) -> Tuple[bool, float]:
        if blocked:
            if self._gesture_key == f"gesture:{gesture}":
                self._gesture_key = None
            return False, 0.0

        active = any(
            hand_data.get(hk) and gesture in hand_data[hk].get("gestures", [])
            for hk in ("right_hand", "left_hand")
        )
        gkey = f"gesture:{gesture}"
        if not active:
            if self._gesture_key == gkey:
                self._gesture_key = None
            return False, 0.0

        if self._gesture_key != gkey:
            self._gesture_key = gkey
            self._gesture_start = time.time()

        elapsed = time.time() - self._gesture_start
        if elapsed >= duration:
            self._gesture_key = None
            return True, 1.0
        return False, min(1.0, elapsed / duration)

    def draw_button(
        self,
        frame,
        rect: Tuple[int, int, int, int],
        label: str,
        hovered: bool,
        progress: float = 0.0,
        color: Tuple[int, int, int] = (0, 200, 255),
    ) -> None:
        x, y, w, h = rect
        bg = (36, 42, 54) if not hovered else (52, 60, 76)
        cv2.rectangle(frame, (x, y), (x + w, y + h), bg, -1)
        border = color if hovered else (75, 85, 100)
        cv2.rectangle(frame, (x, y), (x + w, y + h), border, 2, cv2.LINE_AA)
        if hovered:
            cv2.rectangle(frame, (x + 2, y + 2), (x + w - 2, y + h - 2), color, 1, cv2.LINE_AA)
        if progress > 0:
            fill_w = max(0, int(w * progress))
            cv2.rectangle(frame, (x + 3, y + h - 11), (x + 3 + fill_w, y + h - 3), color, -1)
        sub = "Hold target here..." if hovered and progress < 1 else ""
        ts = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)[0]
        cv2.putText(
            frame, label, (x + max(6, (w - ts[0]) // 2), y + (h + ts[1]) // 2 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2, cv2.LINE_AA,
        )
        if sub:
            cv2.putText(frame, sub, (x + 8, y + h - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.32, color, 1, cv2.LINE_AA)

    def draw_cursors(self, frame, hand_data: Dict) -> None:
        """Green/cyan fingertip targets like skeletal hand tracking."""
        colors = {"left": (80, 255, 80), "right": (255, 200, 80)}
        for side, tip in self.get_hand_cursors(hand_data).items():
            x, y = tip
            col = colors[side]
            cv2.circle(frame, (x, y), 9, col, 2, cv2.LINE_AA)
            cv2.circle(frame, (x, y), 3, (40, 40, 200), -1, cv2.LINE_AA)
            cv2.putText(frame, side[0].upper(), (x + 10, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1, cv2.LINE_AA)

    def draw_cursor(self, frame, hand_data: Dict) -> None:
        self.draw_cursors(frame, hand_data)

    def draw_hand_hint(self, frame, text: str, y: Optional[int] = None) -> None:
        y = y or frame.shape[0] - 55
        cv2.rectangle(frame, (20, y - 10), (frame.shape[1] - 20, y + 28), (0, 0, 0), -1)
        cv2.putText(frame, text, (30, y + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 220, 255), 1)

    def draw_tracking_skeleton(self, frame, hand_data: Dict) -> None:
        """Green bone lines + red joint dots (MediaPipe-style aim overlay)."""
        line_col = (60, 255, 60)
        joint_col = (40, 40, 220)
        for side in ("left", "right"):
            hand = hand_data.get(f"{side}_hand")
            if not hand:
                continue
            pts = hand.get("landmarks") or []
            if len(pts) < 21:
                continue
            for chain in _TRACKING_CHAINS:
                for a, b in zip(chain, chain[1:]):
                    cv2.line(frame, pts[a], pts[b], line_col, 2, cv2.LINE_AA)
            for p in pts:
                cv2.circle(frame, p, 4, joint_col, -1, cv2.LINE_AA)
