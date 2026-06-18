"""Unique defusal mechanics per story chapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2


@dataclass
class MechanicState:
    defusal_type: str = "wire_rsp"
    progress: int = 0
    targets: List[str] = field(default_factory=list)
    all_targets: List[str] = field(default_factory=list)
    screw_hits: List[bool] = field(default_factory=list)
    switch_done: List[bool] = field(default_factory=list)
    pressure_open_frames: int = 0
    freq_value: float = 0.5
    stage_idx: int = 0
    stages: List[str] = field(default_factory=list)


class ChapterMechanics:
    KEYPAD_LAYOUT = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["CLR", "0", "OK"],
    ]

    def setup(self, mission: Dict) -> MechanicState:
        dtype = mission.get("defusal_type", "wire_rsp")
        all_targets = list(mission.get("mechanic_targets", []))
        targets = all_targets
        if dtype == "multi_stage":
            targets = all_targets[:3] if len(all_targets) >= 3 else ["ARM", "SAFE", "CUT"]
        state = MechanicState(
            defusal_type=dtype,
            targets=targets,
            all_targets=all_targets,
            screw_hits=[False] * max(3, len(targets)),
            switch_done=[False] * max(1, len(targets)),
            stages=list(mission.get("stages", [])),
        )
        return state

    def uses_wire_rsp(self, state: MechanicState) -> bool:
        if state.defusal_type == "multi_stage" and state.stages:
            return state.stages[state.stage_idx] == "wire_rsp"
        return state.defusal_type == "wire_rsp"

    def draw(self, frame, bomb_rect: Dict, state: MechanicState, mission: Dict) -> None:
        dtype = state.defusal_type
        if dtype == "multi_stage" and state.stages:
            dtype = state.stages[min(state.stage_idx, len(state.stages) - 1)]

        bx, by = bomb_rect["x"], bomb_rect["y"]
        bw, bh = bomb_rect["width"], bomb_rect["height"]

        if dtype == "keypad":
            self._draw_keypad(frame, bx + bw - 130, by + 40, state)
        elif dtype == "screw_panel":
            self._draw_screws(frame, bx + 30, by + 60, state)
        elif dtype == "switch_bank":
            self._draw_switches(frame, bx + bw - 100, by + 80, state)
        elif dtype == "pressure_release":
            self._draw_pressure_panel(frame, bx + bw // 2 - 80, by + bh - 90, state)
        elif dtype == "dual_pinch":
            self._draw_dual_targets(frame, bx + 80, by + 100, bx + bw - 120, by + 100, state)
        elif dtype == "frequency_align":
            self._draw_frequency_bar(frame, bx + 40, by + 50, bw - 80, state)

        label = mission.get("defusal_label", dtype.replace("_", " ").upper())
        cv2.putText(frame, label, (bx + 12, by + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 200, 255), 1)

    def _draw_keypad(self, frame, x, y, state: MechanicState) -> None:
        for row_i, row in enumerate(self.KEYPAD_LAYOUT):
            for col_i, key in enumerate(row):
                kx, ky = x + col_i * 38, y + row_i * 38
                done = state.progress > row_i * 3 + col_i and state.progress > 0
                col = (0, 140, 90) if done else (50, 54, 62)
                cv2.rectangle(frame, (kx, ky), (kx + 34, ky + 34), col, -1)
                cv2.rectangle(frame, (kx, ky), (kx + 34, ky + 34), (0, 180, 220), 1)
                cv2.putText(frame, key, (kx + 10, ky + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 232, 235), 1)
        if state.targets:
            need = " ".join(str(t) for t in state.targets[: state.progress + 1])
            cv2.putText(frame, f"CODE: {need}", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 220, 180), 1)

    def _draw_screws(self, frame, x, y, state: MechanicState) -> None:
        for i, hit in enumerate(state.screw_hits):
            sx, sy = x, y + i * 55
            col = (0, 200, 120) if hit else (80, 85, 95)
            cv2.circle(frame, (sx, sy), 18, col, -1)
            cv2.circle(frame, (sx, sy), 18, (0, 180, 255), 2)
            cv2.putText(frame, f"S{i+1}", (sx - 10, sy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (20, 22, 28), 1)

    def _draw_switches(self, frame, x, y, state: MechanicState) -> None:
        colors = [(0, 0, 220), (0, 180, 0), (220, 140, 0), (220, 0, 180), (200, 200, 0)]
        for i, name in enumerate(state.targets or ["A", "B", "C", "D"]):
            sy = y + i * 42
            done = state.switch_done[i] if i < len(state.switch_done) else False
            col = (0, 160, 90) if done else colors[i % len(colors)]
            cv2.rectangle(frame, (x, sy), (x + 70, sy + 32), col, -1)
            cv2.putText(frame, name[:6], (x + 8, sy + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    def _draw_pressure_panel(self, frame, x, y, state: MechanicState) -> None:
        prog = min(1.0, state.pressure_open_frames / 45.0)
        cv2.rectangle(frame, (x, y), (x + 160, y + 50), (40, 44, 52), -1)
        cv2.rectangle(frame, (x + 4, y + 30), (x + 4 + int(152 * prog), y + 46), (0, 200, 120), -1)
        cv2.putText(frame, "OPEN PALM HOLD", (x + 8, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 205, 210), 1)
        cv2.putText(frame, "then PINCH RELEASE", (x + 8, y + 62), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 255), 1)

    def _draw_dual_targets(self, frame, lx, ly, rx, ry, state: MechanicState) -> None:
        l_done = state.progress >= 1
        r_done = state.progress >= 2
        cv2.circle(frame, (lx, ly), 22, (0, 180, 90) if l_done else (0, 120, 220), -1)
        cv2.circle(frame, (rx, ry), 22, (0, 180, 90) if r_done else (0, 120, 220), -1)
        cv2.putText(frame, "L", (lx - 6, ly + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "R", (rx - 6, ry + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    def _draw_frequency_bar(self, frame, x, y, w, state: MechanicState) -> None:
        cv2.rectangle(frame, (x, y), (x + w, y + 20), (35, 38, 45), -1)
        target = 0.65
        tx = x + int(w * target)
        cv2.line(frame, (tx, y - 4), (tx, y + 24), (0, 220, 140), 2)
        cx = x + int(w * state.freq_value)
        cv2.rectangle(frame, (cx - 6, y + 2), (cx + 6, y + 18), (0, 180, 255), -1)
        cv2.putText(frame, "Align frequency — move index finger L/R", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 170, 180), 1)

    def _keypad_rects(self, x, y) -> Dict[str, Tuple[int, int, int, int]]:
        rects = {}
        for row_i, row in enumerate(self.KEYPAD_LAYOUT):
            for col_i, key in enumerate(row):
                rects[key] = (x + col_i * 38, y + row_i * 38, 34, 34)
        return rects

    def update_non_wire(
        self,
        state: MechanicState,
        mission: Dict,
        hand_data: Dict,
        hand_ui,
        cursor: Optional[Tuple[int, int]],
        tool_pos: Optional[Tuple[int, int]],
        bio,
        steady_counter: int,
        bomb_rect: Dict,
    ) -> Optional[str]:
        """Returns 'complete', 'fail', or None (still in progress)."""
        dtype = state.defusal_type
        if dtype == "multi_stage" and state.stages:
            dtype = state.stages[min(state.stage_idx, len(state.stages) - 1)]

        bx, by = bomb_rect["x"], bomb_rect["y"]
        bw = bomb_rect["width"]

        if dtype == "keypad":
            rects = self._keypad_rects(bx + bw - 130, by + 40)
            if cursor is None:
                return None
            expected = state.targets
            if state.progress >= len(expected):
                return "complete"
            for key, rect in rects.items():
                if key in ("CLR", "OK"):
                    continue
                ok, _ = hand_ui.hold_confirm(hand_data, f"key_{key}_{state.progress}", rect, 0.4)
                if not ok:
                    continue
                if key == str(expected[state.progress]):
                    state.progress += 1
                    if state.progress >= len(expected):
                        return self._advance_multi(state)
                else:
                    return "fail"
            return None

        if dtype == "screw_panel":
            if tool_pos is None or steady_counter < 8:
                return None
            screws = [(bx + 30, by + 60 + i * 55) for i in range(len(state.screw_hits))]
            for i, (sx, sy) in enumerate(screws):
                if state.screw_hits[i]:
                    continue
                if abs(tool_pos[0] - sx) < 28 and abs(tool_pos[1] - sy) < 28:
                    state.screw_hits[i] = True
                    if all(state.screw_hits):
                        return self._advance_multi(state)
            return None

        if dtype == "switch_bank":
            if cursor is None:
                return None
            names = state.targets or ["A", "B", "C", "D"]
            x, y = bx + bw - 100, by + 80
            for i, name in enumerate(names):
                rect = (x, y + i * 42, 70, 32)
                if state.switch_done[i]:
                    continue
                ok, _ = hand_ui.hold_confirm(hand_data, f"sw_{name}_{state.progress}", rect, 0.45)
                if not ok:
                    continue
                if name == names[state.progress]:
                    state.switch_done[i] = True
                    state.progress += 1
                    if state.progress >= len(names):
                        return self._advance_multi(state)
                    return None
                return "fail"
            return None

        if dtype == "pressure_release":
            if state.progress == 0:
                if hand_data.get("open_palm"):
                    state.pressure_open_frames += 1
                else:
                    state.pressure_open_frames = max(0, state.pressure_open_frames - 2)
                if state.pressure_open_frames >= 45:
                    state.progress = 1
            elif state.progress == 1 and hand_data.get("pinch_active"):
                return self._advance_multi(state)
            return None

        if dtype == "dual_pinch":
            lh = hand_data.get("left_hand")
            rh = hand_data.get("right_hand")
            lp = lh and "pinch" in lh.get("gestures", [])
            rp = rh and "pinch" in rh.get("gestures", [])
            if lp:
                state.progress = max(state.progress, 1)
            if rp:
                state.progress = max(state.progress, 2)
            if lp and rp:
                return self._advance_multi(state)
            return None

        if dtype == "frequency_align":
            if cursor:
                rel = (cursor[0] - (bx + 40)) / max(1, bw - 80)
                state.freq_value = max(0.0, min(1.0, rel))
            lock_rect = (bx + int((bw - 80) * 0.62) - 20, by + 20, 40, 30)
            ok, _ = hand_ui.hold_confirm(hand_data, "freq_lock", lock_rect, 0.5, blocked=steady_counter < 6)
            if ok and abs(state.freq_value - 0.65) < 0.06:
                return self._advance_multi(state)
            return None

        return None

    def _advance_multi(self, state: MechanicState) -> str:
        if state.defusal_type != "multi_stage" or not state.stages:
            return "complete"
        state.stage_idx += 1
        state.progress = 0
        state.screw_hits = [False] * len(state.screw_hits)
        state.switch_done = [False] * len(state.switch_done)
        state.pressure_open_frames = 0
        if state.stage_idx >= len(state.stages):
            return "complete"
        nxt = state.stages[state.stage_idx]
        if nxt == "keypad" and len(state.all_targets) >= 6:
            state.targets = state.all_targets[-3:]
        elif nxt == "switch_bank":
            state.targets = state.all_targets[:3]
            state.switch_done = [False] * len(state.targets)
        return "stage"
