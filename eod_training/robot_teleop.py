"""Virtual UGV teleoperation — hand gestures drive remote robot end-effector."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class TeleopState:
    deployed: bool = False
    estop: bool = False
    fault_active: bool = False
    fault_cleared: bool = False
    cutter_charged: bool = False
    zoom: float = 1.0
    tool_x: float = 0.0
    tool_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    comms_lag_ms: int = 0
    status_line: str = "STANDBY"


class RobotTeleopSystem:
    """Maps operator hand gestures to a virtual EOD robot arm (remote teleop)."""

    GESTURE_MAP = {
        "pointing": "Index target = move cutter",
        "open_hand": "E-STOP / abort",
        "peace": "Fault reset / joint recovery",
    }

    def __init__(self, frame_width: int, frame_height: int) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.state = TeleopState()
        self._pos_history: Deque[Tuple[float, float, float]] = deque(maxlen=120)
        self._smooth_alpha = 0.72
        self.ugv_base = (80, frame_height - 120)
        self.deploy_zone = (frame_width // 2 - 70, frame_height // 2 + 120, 140, 70)
        self.ai_suggested_wrong: Optional[str] = None
        self._pulse = 0.0

    def reset(self) -> None:
        self.state = TeleopState()
        self._pos_history.clear()
        self.ai_suggested_wrong = None

    def configure(self, mission: Dict) -> None:
        self.state.comms_lag_ms = int(mission.get("comms_lag_ms", 0))
        self.state.fault_active = bool(mission.get("robot_fault", False))
        self.state.fault_cleared = not self.state.fault_active
        if mission.get("ai_wrong_suggestion") and mission.get("wire_count", 3) > 0:
            pool = ["RED", "BLUE", "GREEN", "YELLOW", "WHITE"]
            self.ai_suggested_wrong = pool[mission.get("difficulty", 1) % len(pool)]

    def deploy_zone_rect(self) -> Tuple[int, int, int, int]:
        return self.deploy_zone

    def update(
        self,
        hand_data: Dict,
        bio,
        bomb_rect: Dict,
        cursor: Optional[Tuple[int, int]],
    ) -> TeleopState:
        self._pulse += 0.1
        s = self.state

        if hand_data.get("open_palm") and not hand_data.get("pinch_active"):
            s.estop = True
            s.status_line = "E-STOP ACTIVE — fist to reset"
            s.cutter_charged = False
        elif hand_data.get("peace_active"):
            if s.fault_active and not s.fault_cleared:
                s.fault_cleared = True
                s.status_line = "Joint fault cleared — resume teleop"
        else:
            if s.estop:
                s.estop = False
                s.status_line = "E-STOP cleared"
            s.cutter_charged = s.deployed and cursor is not None

        if not s.deployed or cursor is None or s.estop:
            return s

        if s.fault_active and not s.fault_cleared:
            s.status_line = "ARM FAULT — peace sign 1s to reset"
            return s

        bx = bomb_rect["x"] + 20
        by = bomb_rect["y"] + 20
        bw = bomb_rect["width"] - 40
        bh = bomb_rect["height"] - 40
        tx = float(np.clip(cursor[0], bx, bx + bw))
        ty = float(np.clip(cursor[1], by, by + bh))

        if bio.tremor_index > 0.55:
            s.status_line = "TELEOP BLOCKED — operator tremor too high"
            return s

        s.target_x, s.target_y = tx, ty
        now = time.time()
        self._pos_history.append((now, tx, ty))

        lag_s = s.comms_lag_ms / 1000.0
        if lag_s > 0:
            target_time = now - lag_s
            lx, ly = tx, ty
            for t, x, y in reversed(self._pos_history):
                if t <= target_time:
                    lx, ly = x, y
                    break
            s.tool_x = s.tool_x * (1 - self._smooth_alpha) + lx * self._smooth_alpha
            s.tool_y = s.tool_y * (1 - self._smooth_alpha) + ly * self._smooth_alpha
            s.status_line = f"TELEOP ACTIVE — comms lag {s.comms_lag_ms}ms"
        else:
            s.tool_x = s.tool_x * (1 - self._smooth_alpha) + tx * self._smooth_alpha
            s.tool_y = s.tool_y * (1 - self._smooth_alpha) + ty * self._smooth_alpha
            s.status_line = "TELEOP ACTIVE — nominal link"

        return s

    def get_tool_pos(self) -> Optional[Tuple[int, int]]:
        if not self.state.deployed or self.state.estop:
            return None
        if self.state.fault_active and not self.state.fault_cleared:
            return None
        return int(self.state.tool_x), int(self.state.tool_y)

    def mark_deployed(self) -> None:
        self.state.deployed = True
        self.state.status_line = "UGV DEPLOYED — teleop link established"

    @staticmethod
    def _both_hands_open(hand_data: Dict) -> bool:
        lh = hand_data.get("left_hand")
        rh = hand_data.get("right_hand")
        return bool(
            lh and rh
            and "open_hand" in lh.get("gestures", [])
            and "open_hand" in rh.get("gestures", [])
        )

    @staticmethod
    def _both_hands_spread(hand_data: Dict) -> bool:
        lh = hand_data.get("left_hand")
        rh = hand_data.get("right_hand")
        if not lh or not rh:
            return False
        lc, rc = lh.get("center"), rh.get("center")
        if not lc or not rc:
            return False
        return math.hypot(lc[0] - rc[0], lc[1] - rc[1]) > 280

    def draw(self, frame, bomb_rect: Dict, phase: str) -> None:
        s = self.state
        self._draw_ugv(frame)

        if s.deployed:
            tool = (int(s.tool_x), int(s.tool_y)) if s.tool_x else None
            if tool and tool[0] > 0:
                self._draw_arm(frame, self.ugv_base, tool, s.estop or (s.fault_active and not s.fault_cleared))
                self._draw_tool_head(frame, tool, s.cutter_charged)
            self._draw_link_status(frame, s.comms_lag_ms, s.estop)

        if phase == "robot_deploy" and not s.deployed:
            x, y, w, h = self.deploy_zone
            pulse = int(3 * math.sin(self._pulse))
            cv2.rectangle(frame, (x - pulse, y - pulse), (x + w + pulse, y + h + pulse), (0, 200, 255), 2)
            cv2.putText(frame, "DEPLOY UGV", (x + 12, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2)
            cv2.putText(frame, "Point + hold", (x + 22, y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)

        if s.estop:
            cv2.rectangle(frame, (0, 0), (self.frame_width, 36), (0, 0, 180), -1)
            cv2.putText(frame, "REMOTE E-STOP — OPEN PALM ACTIVE", (20, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        if self.ai_suggested_wrong and phase == "teleop_rsp":
            cv2.rectangle(frame, (bomb_rect["x"], bomb_rect["y"] - 28), (bomb_rect["x"] + 420, bomb_rect["y"] - 4), (0, 0, 120), -1)
            cv2.putText(
                frame,
                f"AI ADVISOR: cut {self.ai_suggested_wrong} (VERIFY — may be wrong)",
                (bomb_rect["x"] + 8, bomb_rect["y"] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (180, 180, 255),
                1,
            )

    def _draw_operator_station_banner(self, frame) -> None:
        cv2.rectangle(frame, (0, 0), (self.frame_width, 32), (18, 22, 28), -1)
        cv2.putText(
            frame,
            "EOD READINESS PLATFORM  |  REMOTE TELEOP STATION  |  Operator controls robot — not device",
            (12, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 210, 255),
            1,
        )

    def _draw_ugv(self, frame) -> None:
        bx, by = self.ugv_base
        cv2.rectangle(frame, (bx - 40, by - 20), (bx + 50, by + 25), (50, 50, 55), -1)
        cv2.rectangle(frame, (bx - 40, by - 20), (bx + 50, by + 25), (100, 100, 110), 2)
        cv2.circle(frame, (bx - 25, by + 20), 10, (30, 30, 30), -1)
        cv2.circle(frame, (bx + 30, by + 20), 10, (30, 30, 30), -1)
        cv2.putText(frame, "UGV-1", (bx - 30, by - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
        link_color = (0, 200, 0) if self.state.deployed else (80, 80, 80)
        cv2.putText(frame, "LINK", (bx + 5, by + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, link_color, 1)

    def _draw_arm(self, frame, base: Tuple[int, int], tool: Tuple[int, int], blocked: bool) -> None:
        color = (80, 80, 90) if blocked else (0, 180, 255)
        elbow = ((base[0] + tool[0]) // 2, (base[1] + tool[1]) // 2 - 40)
        cv2.line(frame, base, elbow, color, 4, cv2.LINE_AA)
        cv2.line(frame, elbow, tool, color, 3, cv2.LINE_AA)
        cv2.circle(frame, elbow, 6, (200, 200, 200), -1)
        cv2.line(frame, base, tool, (40, 40, 50), 1, cv2.LINE_AA)

    def _draw_tool_head(self, frame, tool: Tuple[int, int], charged: bool) -> None:
        col = (0, 220, 140) if charged else (0, 200, 255)
        cv2.drawMarker(frame, tool, col, cv2.MARKER_TILTED_CROSS, 16, 2, cv2.LINE_AA)
        cv2.circle(frame, tool, 14, col, 1, cv2.LINE_AA)
        cv2.putText(frame, "CUTTER", (tool[0] + 18, tool[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)

    def _draw_link_status(self, frame, lag_ms: int, estop: bool) -> None:
        x = self.frame_width - 220
        cv2.rectangle(frame, (x, 38), (self.frame_width - 10, 95), (20, 24, 30), -1)
        cv2.putText(frame, f"COMMS LAG: {lag_ms}ms", (x + 8, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 200, 180), 1)
        cv2.putText(frame, "SAT-LINK 9600", (x + 8, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 140, 120), 1)
        st = "E-STOP" if estop else "NOMINAL"
        cv2.putText(frame, st, (x + 8, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255) if estop else (0, 200, 0), 1)

    def draw_gesture_legend(self, frame) -> None:
        x, y = 12, self.frame_height - 130
        cv2.rectangle(frame, (x, y), (x + 280, y + 115), (15, 18, 22), -1)
        cv2.rectangle(frame, (x, y), (x + 280, y + 115), (50, 60, 70), 1)
        cv2.putText(frame, "TELEOP GESTURES", (x + 8, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 200, 255), 1)
        lines = [
            "Target on zone = cut/hold",
            "Open palm     = E-STOP",
            "Peace         = fault reset",
        ]
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (x + 8, y + 38 + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (170, 180, 190), 1)
