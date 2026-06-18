"""Realistic IED device rendering — PCB, components, wires, HUD."""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from eod_training.bomb_effects import BombEffects
from eod_training.platform_ui import PlatformUI
from eod_training.wire_physics import WirePhysicsEngine, WireState


class BombRenderer:
    DEVICE_LABELS = {
        "training_ied": "TRAINING DEVICE — TD-100",
        "command_wire_ied": "CMD WIRE IED — CW-220",
        "victim_operated_ied": "VOIED — MERCURY SWITCH",
        "time_initiated_ied": "TIME IED — TC-88",
        "complex_ied": "COMPLEX IED — MULTI-INIT",
    }

    def __init__(self, frame_width: int, frame_height: int) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.serial_number = random.randint(100000, 999999)
        self.effects = BombEffects()
        self._init_layout()
        self.components = self._generate_components()

    def _init_layout(self, layout: Optional[Dict] = None) -> None:
        if layout:
            self.bomb_rect = dict(layout.get("bomb_rect", {}))
            self.board_rect = dict(layout.get("board_rect", {}))
            self.bench_rect = layout.get("bench_rect", self.bomb_rect)
            return
        cx, cy = self.frame_width // 2, self.frame_height // 2 - 20
        self.bomb_rect = {
            "x": cx - 260,
            "y": cy - 190,
            "width": 520,
            "height": 380,
        }
        margin = 35
        self.board_rect = {
            "x": self.bomb_rect["x"] + margin,
            "y": self.bomb_rect["y"] + margin,
            "width": self.bomb_rect["width"] - margin * 2,
            "height": self.bomb_rect["height"] - margin * 2 - 40,
        }

    def apply_layout(self, layout: Dict) -> None:
        self._init_layout(layout)
        self.components = self._generate_components()

    def _generate_components(self) -> Dict:
        bx, by = self.board_rect["x"], self.board_rect["y"]
        bw, bh = self.board_rect["width"], self.board_rect["height"]
        caps, resistors, chips = [], [], []

        for i in range(8):
            caps.append(
                {
                    "x": bx + random.randint(25, bw - 45),
                    "y": by + random.randint(25, bh - 45),
                    "w": random.randint(12, 18),
                    "h": random.randint(22, 32),
                    "color": random.choice([(100, 100, 200), (200, 180, 80), (180, 80, 80)]),
                }
            )
        band_colors = [
            (0, 0, 0),
            (139, 69, 19),
            (255, 0, 0),
            (255, 165, 0),
            (255, 255, 0),
            (0, 128, 0),
            (0, 0, 255),
        ]
        for _ in range(10):
            resistors.append(
                {
                    "x": bx + random.randint(25, bw - 50),
                    "y": by + random.randint(25, bh - 20),
                    "bands": random.sample(band_colors, 4),
                }
            )
        for i in range(3):
            chips.append(
                {
                    "x": bx + random.randint(40, bw - 90),
                    "y": by + random.randint(40, bh - 60),
                    "w": random.randint(45, 65),
                    "h": random.randint(22, 28),
                    "pins": random.choice([8, 14, 16]),
                    "label": f"U{i+1}",
                }
            )
        return {"capacitors": caps, "resistors": resistors, "chips": chips}

    def draw_device(
        self,
        frame,
        wires: List[WireState],
        device_type: str,
        timer_remaining: float,
        remote_tool_placed: bool,
        highlight_wire: Optional[int] = None,
        show_cut_zones: bool = False,
    ) -> None:
        self.effects.update()
        self._draw_casing(frame)
        self._draw_pcb(frame)
        self._draw_components(frame)
        self._draw_timer(frame, timer_remaining)
        self._draw_wires(frame, wires, highlight_wire, show_cut_zones)
        self._draw_labels(frame, device_type, remote_tool_placed)
        self.effects.draw(frame)

    def _draw_casing(self, frame) -> None:
        r = self.bomb_rect
        x, y, w, h = r["x"], r["y"], r["width"], r["height"]
        base = (35, 35, 40)
        cv2.rectangle(frame, (x, y), (x + w, y + h), base, -1)
        hi = (75, 75, 80)
        sh = (15, 15, 18)
        cv2.rectangle(frame, (x, y), (x + w, y + 6), hi, -1)
        cv2.rectangle(frame, (x, y), (x + 6, y + h), hi, -1)
        cv2.rectangle(frame, (x, y + h - 6, x + w, y + h), sh, -1)
        cv2.rectangle(frame, (x + w - 6, y, x + w, y + h), sh, -1)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (90, 90, 95), 2)
        for bx, by in [(x + 18, y + 18), (x + w - 28, y + 18), (x + 18, y + h - 28), (x + w - 28, y + h - 28)]:
            cv2.circle(frame, (bx, by), 7, (60, 60, 65), -1)
            cv2.circle(frame, (bx, by), 7, (110, 110, 115), 1)

    def _draw_pcb(self, frame) -> None:
        b = self.board_rect
        cv2.rectangle(frame, (b["x"], b["y"]), (b["x"] + b["width"], b["y"] + b["height"]), (0, 55, 0), -1)
        trace = (0, 120, 0)
        for i in range(7):
            y = b["y"] + 25 + i * 28
            cv2.line(frame, (b["x"] + 15, y), (b["x"] + b["width"] - 15, y), trace, 1)
        for i in range(10):
            x = b["x"] + 25 + i * 38
            cv2.line(frame, (x, b["y"] + 15), (x, b["y"] + b["height"] - 15), trace, 1)

    def _draw_components(self, frame) -> None:
        for cap in self.components["capacitors"]:
            cv2.rectangle(
                frame,
                (cap["x"], cap["y"]),
                (cap["x"] + cap["w"], cap["y"] + cap["h"]),
                cap["color"],
                -1,
            )
        for res in self.components["resistors"]:
            cv2.rectangle(frame, (res["x"], res["y"]), (res["x"] + 28, res["y"] + 8), (200, 180, 140), -1)
            for i, bc in enumerate(res["bands"]):
                cv2.rectangle(frame, (res["x"] + 4 + i * 5, res["y"]), (res["x"] + 7 + i * 5, res["y"] + 8), bc, -1)
        for chip in self.components["chips"]:
            cv2.rectangle(
                frame,
                (chip["x"], chip["y"]),
                (chip["x"] + chip["w"], chip["y"] + chip["h"]),
                (18, 18, 18),
                -1,
            )
            cv2.putText(
                frame,
                chip["label"],
                (chip["x"] + 4, chip["y"] + chip["h"] // 2 + 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (180, 180, 180),
                1,
            )

    def _draw_timer(self, frame, remaining: float) -> None:
        dx = self.bomb_rect["x"] + (self.bomb_rect["width"] - 140) // 2
        dy = self.bomb_rect["y"] + 18
        cv2.rectangle(frame, (dx - 8, dy - 4), (dx + 148, dy + 42), (0, 0, 0), -1)
        cv2.rectangle(frame, (dx - 8, dy - 4), (dx + 148, dy + 42), (40, 40, 40), 2)
        mins, secs = int(remaining) // 60, int(remaining) % 60
        if remaining > 60:
            color = (0, 220, 0)
        elif remaining > 30:
            color = (0, 220, 220)
        else:
            color = (0, 0, 255) if int(time.time() * 3) % 2 else (255, 255, 255)
        text = f"{mins:02d}:{secs:02d}"
        cv2.putText(frame, text, (dx + 10, dy + 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

    def _draw_wires(self, frame, wires: List[WireState], highlight: Optional[int], show_cut_zones: bool) -> None:
        for i, wire in enumerate(wires):
            color = list(WirePhysicsEngine.WIRE_COLORS.get(wire.color, (128, 128, 128)))
            if wire.tension > 0.5:
                pulse = int(wire.tension * 80)
                color = [min(255, c + pulse) for c in color]
            self.effects.draw_wire_with_effects(
                frame, wire, tuple(color), wire.thickness, i == highlight, show_cut_zones
            )
            if wire.tension > 0.3:
                cz = wire.cut_zone
                cv2.putText(
                    frame,
                    f"T:{wire.tension:.0%}",
                    (cz[0], cz[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    (0, 140, 255),
                    1,
                )

    def trigger_cut_sparks(self, wire: WireState) -> None:
        mid = wire.control_points[len(wire.control_points) // 2]
        self.effects.spawn_sparks(mid[0], mid[1])

    def trigger_explosion(self) -> None:
        cx = self.bomb_rect["x"] + self.bomb_rect["width"] // 2
        cy = self.bomb_rect["y"] + self.bomb_rect["height"] // 2
        self.effects.spawn_explosion(cx, cy)

    def _draw_labels(self, frame, device_type: str, remote_placed: bool) -> None:
        r = self.bomb_rect
        label = self.DEVICE_LABELS.get(device_type, "UNKNOWN DEVICE")
        cv2.rectangle(frame, (r["x"] + 12, r["y"] + r["height"] - 52), (r["x"] + 240, r["y"] + r["height"] - 12), (0, 0, 160), -1)
        cv2.putText(frame, label, (r["x"] + 18, r["y"] + r["height"] - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.putText(frame, f"SN:{self.serial_number}", (r["x"] + r["width"] - 110, r["y"] + r["height"] - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
        rt_color = (0, 200, 0) if remote_placed else (0, 0, 200)
        rt_text = "REMOTE TOOL: PLACED" if remote_placed else "REMOTE TOOL: NOT PLACED"
        cv2.putText(frame, rt_text, (r["x"] + 260, r["y"] + r["height"] - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, rt_color, 1)

    def draw_remote_tool_zone(self, frame) -> Tuple[int, int, int, int]:
        """Designated zone for 'placing' remote cutting tool via pointing gesture."""
        x = self.frame_width - 180
        y = self.frame_height // 2 - 60
        w, h = 160, 120
        cv2.rectangle(frame, (x, y), (x + w, y + h), (40, 40, 60), -1)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 180, 255), 2)
        cv2.putText(frame, "REMOTE", (x + 28, y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1)
        cv2.putText(frame, "TOOL ZONE", (x + 18, y + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1)
        cv2.putText(frame, "Point to place", (x + 22, y + 95), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
        return (x, y, w, h)

    def draw_hud(
        self,
        frame,
        mission_name: str,
        phase: str,
        biometrics,
        progress: float,
        manual_lines: List[str],
        five_cs_done: int,
        five_cs_total: int,
    ) -> None:
        overlay = frame.copy()
        cv2.rectangle(overlay, (8, 8), (420, 130), (0, 0, 0), -1)
        frame[:] = cv2.addWeighted(overlay, 0.55, frame, 0.45, 0)
        cv2.putText(frame, mission_name[:38], (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1)
        cv2.putText(frame, f"Phase: {phase.upper()}", (16, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.putText(frame, f"5Cs: {five_cs_done}/{five_cs_total}", (16, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.putText(
            frame,
            f"Steadiness:{biometrics.stability:.0%} Tremor:{biometrics.tremor_index:.0%} Stress:{biometrics.stress_level:.0%}",
            (16, 96),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (180, 220, 180),
            1,
        )
        cv2.putText(frame, biometrics.recommendation[:50], (16, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 200, 255), 1)
        bar_x, bar_y, bar_w, bar_h = 16, 140, 300, 14
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), -1)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + int(bar_w * progress), bar_y + bar_h), (0, 200, 0), -1)

        panel_y = self.frame_height - 160
        cv2.rectangle(frame, (8, panel_y), (450, self.frame_height - 8), (0, 0, 0), -1)
        cv2.rectangle(frame, (8, panel_y), (450, self.frame_height - 8), (80, 80, 80), 1)
        for i, line in enumerate(manual_lines[:5]):
            cv2.putText(frame, line[:52], (16, panel_y + 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1)

    def draw_menu(self, frame, missions: List[Dict], selected: int) -> None:
        cv2.rectangle(frame, (0, 0), (self.frame_width, self.frame_height), (20, 22, 28), -1)
        cv2.putText(frame, "EOD TRAINING SIMULATOR v2.0", (self.frame_width // 2 - 220, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
        cv2.putText(frame, "IMAS 09.31 Compliant Training Environment", (self.frame_width // 2 - 200, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
        y = 130
        for i, m in enumerate(missions):
            locked = "" if m.get("unlocked") else " [LOCKED]"
            done = " [DONE]" if m.get("completed") else ""
            color = (0, 255, 200) if i == selected else (180, 180, 180)
            if not m.get("unlocked"):
                color = (80, 80, 80)
            cv2.putText(
                frame,
                f"{i+1}. [{m['tier']}] {m['name']}{done}{locked}",
                (60, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                color,
                1,
            )
            y += 32
        PlatformUI.draw_hint_bar(frame, "Point mission | PINCH DEPLOY OP to start | FIST 2.5s to quit | Q key")

    def draw_result(self, frame, report, success: bool) -> None:
        color = (0, 200, 0) if success else (0, 0, 220)
        title = "RENDER SAFE — MISSION PASS" if success else "DETONATION — MISSION FAIL"
        cv2.putText(frame, title, (self.frame_width // 2 - 280, self.frame_height // 2 - 80), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
        cv2.putText(frame, f"Score: {report.overall_score} — Grade: {report.grade}", (self.frame_width // 2 - 180, self.frame_height // 2 - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        y = self.frame_height // 2 + 10
        for k, v in report.categories.items():
            cv2.putText(frame, f"{k}: {v}%", (self.frame_width // 2 - 160, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            y += 24
        cv2.putText(frame, "OPEN PALM 1s = return to menu", (self.frame_width // 2 - 140, y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

    def draw_five_cs_checklist(self, frame, five_cs: List[Dict], completed: List[str]) -> None:
        cv2.putText(frame, "5 Cs — POINT at row, PINCH 1s to confirm each", (40, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1)
        y = 80
        for i, c in enumerate(five_cs):
            done = c["id"] in completed
            mark = "[X]" if done else "[ ]"
            color = (0, 255, 0) if done else (255, 255, 255)
            cv2.rectangle(frame, (35, y - 18), (self.frame_width - 35, y + 28), (30, 30, 35), -1)
            cv2.putText(frame, f"{mark} {c['name']}: {c['description'][:55]}", (45, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1)
            y += 55

    def apply_screen_shake(self, frame, intensity: float) -> np.ndarray:
        if intensity < 0.5:
            return frame
        sx = random.randint(-int(intensity), int(intensity))
        sy = random.randint(-int(intensity), int(intensity))
        m = np.float32([[1, 0, sx], [0, 1, sy]])
        return cv2.warpAffine(frame, m, (self.frame_width, self.frame_height))
