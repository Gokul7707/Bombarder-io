"""
EOD Operator Readiness Platform v4.0
Remote robot teleop simulation — hand controls virtual UGV arm, not the device directly.
"""

from __future__ import annotations

import random
import time
import warnings
from enum import Enum
from typing import Dict, List, Optional, Tuple

import cv2

from eod_training.audio_engine import AudioEngine
from eod_training.biometric_analyzer import BiometricAnalyzer, BiometricSnapshot
from eod_training.bomb_renderer import BombRenderer
from eod_training.calibration_flow import CalibrationFlow
from eod_training.chapter_mechanics import ChapterMechanics, MechanicState
from eod_training.dialogue_system import DialogueSystem
from eod_training.eod_protocols import EODProtocolEngine
from eod_training.fps_counter import FPSCounter
from eod_training.hand_tracker import HandTracker
from eod_training.hand_ui import HandUIController
from eod_training.mission_manager import MissionManager
from eod_training.performance_evaluator import PerformanceEvaluator, PerformanceReport
from eod_training.platform_ui import PlatformUI
from eod_training.robot_teleop import RobotTeleopSystem
from eod_training.session_reporter import SessionReporter
from eod_training.ui_layout import UILayout
from eod_training.virtual_workspace import VirtualWorkspace
from eod_training.wire_physics import WirePhysicsEngine
from eod_training.wire_cut_coach import WireCutCoach

warnings.filterwarnings("ignore")


class OpPhase(str, Enum):
    CALIBRATION = "calibration"
    MENU = "menu"
    CHAPTER_INTRO = "chapter_intro"
    THREAT_CONFIRMATION = "threat_confirmation"
    CORDON = "cordon"
    ROBOT_DEPLOY = "robot_deploy"
    TELEOP_RSP = "teleop_rsp"
    POST_BLAST_REPORT = "post_blast_report"
    SUCCESS = "success"
    FAILURE = "failure"


class EODReadinessPlatform:
    TAGLINE = "Train the human behind the robot — decisions, stress, and remote precision."

    def __init__(self) -> None:
        print("EOD Operator Readiness Platform v4.0")
        print(self.TAGLINE)
        self.cap = self._open_camera()
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.hand_tracker = HandTracker(self.frame_width, self.frame_height)
        self.hand_ui = HandUIController()
        self.wire_coach = WireCutCoach()
        self.ui = PlatformUI()
        self.biometrics = BiometricAnalyzer()
        self.protocols = EODProtocolEngine()
        self.missions = MissionManager()
        self.wire_engine = WirePhysicsEngine(self.frame_width, self.frame_height)
        self.renderer = BombRenderer(self.frame_width, self.frame_height)
        self.workspace = VirtualWorkspace(self.frame_width, self.frame_height)
        self.mechanics = ChapterMechanics()
        self.mechanic_state: Optional[MechanicState] = None
        self.robot = RobotTeleopSystem(self.frame_width, self.frame_height)
        self.audio = AudioEngine()
        self.evaluator = PerformanceEvaluator(self.protocols.get_grading_weights())
        self.reporter = SessionReporter()

        self.calibration = CalibrationFlow(self.frame_width, self.frame_height)
        self.dialogue = DialogueSystem()
        self._menu_dialogue_mission: Optional[str] = None
        self.fps = FPSCounter()

        self.phase = OpPhase.CALIBRATION if not self.calibration.skip_if_cached() else OpPhase.MENU
        self.menu_selection = 0
        self.timer_start: Optional[float] = None
        self.time_limit = 300
        self.wire_sequence: List[str] = []
        self.wire_target_idx = 0
        self.steady_counter = 0
        self.manual_lines: List[str] = []
        self.shake_intensity = 0.0
        self.final_report: Optional[PerformanceReport] = None
        self._last_stability = 1.0
        self._status_msg = ""
        self._status_until = 0.0

        self.confirm_btn = (0, 0, 0, 0)
        self.start_btn = (0, 0, 0, 0)
        self.aar_btn = (0, 0, 0, 0)
        self.layout = UILayout(self.frame_width, self.frame_height)
        self._apply_layout_buttons()
        self._sync_workspace_layout()
        if self.calibration.profile.completed:
            self.workspace.apply_calibration(self.calibration.profile)

    def _apply_layout_buttons(self) -> None:
        self.start_btn = self.layout.deploy_btn
        self.confirm_btn = self.layout.confirm_btn
        self.aar_btn = self.layout.aar_btn

    def _sync_display_dimensions(self, cam_w: int, cam_h: int) -> None:
        if cam_w == self.frame_width and cam_h == self.frame_height:
            return
        self.frame_width = cam_w
        self.frame_height = cam_h
        self.hand_tracker.sync_dimensions(cam_w, cam_h)
        self.layout.resize(cam_w, cam_h)
        self.workspace = VirtualWorkspace(cam_w, cam_h)
        self.renderer = BombRenderer(cam_w, cam_h)
        self.robot = RobotTeleopSystem(cam_w, cam_h)
        self.wire_engine = WirePhysicsEngine(cam_w, cam_h)
        self.calibration.width = cam_w
        self.calibration.height = cam_h
        self._apply_layout_buttons()
        self._sync_workspace_layout()
        if self.calibration.profile.completed:
            self.workspace.apply_calibration(self.calibration.profile)

    def _begin_chapter_intro(self) -> None:
        m = self.missions.current
        self.dialogue.load_chapter_intro(m)
        self.phase = OpPhase.CHAPTER_INTRO
        self.hand_ui.reset_holds()

    def _sync_workspace_layout(self) -> None:
        layout = {
            "bomb_rect": self.workspace.bomb_rect,
            "board_rect": self.workspace.board_rect,
            "bench_rect": self.workspace.bench_rect,
        }
        self.renderer.apply_layout(layout)

    @staticmethod
    def _map_point_to_scene(pt: Tuple[int, int], cam_w: int, cam_h: int, bomb_rect: Dict) -> Tuple[int, int]:
        nx = pt[0] / max(1, cam_w)
        ny = pt[1] / max(1, cam_h)
        return (
            int(bomb_rect["x"] + 30 + nx * (bomb_rect["width"] - 60)),
            int(bomb_rect["y"] + 40 + ny * (bomb_rect["height"] - 100)),
        )

    def _map_hand_to_scene(self, hand_data: Dict) -> Dict:
        mapped = dict(hand_data)
        br = self.renderer.bomb_rect
        w, h = self.frame_width, self.frame_height
        if hand_data.get("primary_center"):
            mapped["primary_center"] = self._map_point_to_scene(hand_data["primary_center"], w, h, br)
        for side in ("left", "right"):
            hand = hand_data.get(f"{side}_hand")
            if hand:
                tip = hand.get("screen_tip") or hand.get("index_tip")
                if tip:
                    mh = dict(hand)
                    mh["index_tip"] = self._map_point_to_scene(tip, w, h, br)
                    mh["screen_tip"] = mh["index_tip"]
                    mapped[f"{side}_hand"] = mh
        return mapped

    def _open_camera(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            for i in range(1, 5):
                cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    break
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _steady_required(self) -> int:
        return max(4, 10 - self.missions.current.get("difficulty", 1))

    def _teleop_cursor(self, hand_data: Dict) -> Optional[Tuple[int, int]]:
        """Index fingertip in full-screen coords — direct 1:1 tracking."""
        return self.hand_ui.get_cursor(hand_data)

    def _teleop_tool_point(self, hand_data: Dict) -> Optional[Tuple[int, int]]:
        cursor = self._teleop_cursor(hand_data)
        if cursor is None:
            return None
        br = self.renderer.bomb_rect
        pad = 40
        zone = (br["x"] - pad, br["y"] - pad, br["width"] + pad * 2, br["height"] + pad * 2)
        if not self.hand_ui.point_in_rect(cursor, zone, pad=0):
            return None
        return (
            max(br["x"], min(br["x"] + br["width"], cursor[0])),
            max(br["y"], min(br["y"] + br["height"], cursor[1])),
        )

    def _notify(self, msg: str, duration: float = 2.5) -> None:
        self._status_msg = msg
        self._status_until = time.time() + duration

    def _start_mission(self, mission_id: Optional[str] = None) -> None:
        ml = self.missions.list_missions()
        if mission_id:
            if not self.missions.select_mission(mission_id):
                return
        else:
            sel = ml[self.menu_selection]
            if not sel.get("unlocked"):
                self._notify("Complete prior operation to unlock")
                return
            self.missions.select_mission(sel["id"])

        m = self.missions.current
        self.reporter = SessionReporter()
        self.protocols.reset_checklist()
        self.biometrics.reset()
        self.hand_tracker.smoother.reset()
        self.robot.reset()
        self.robot.configure(m)
        self.evaluator.reset(len(m.get("phases", [])))
        self.renderer.effects.reset()
        self.wire_target_idx = 0
        self.steady_counter = 0
        self.final_report = None
        self.time_limit = m.get("time_limit_sec", 300)
        self.timer_start = None

        colors = self.missions.wire_colors_for_mission()
        self.mechanic_state = self.mechanics.setup(m)
        if colors:
            override = m.get("wire_sequence_override")
            if override:
                self.wire_sequence = [w for w in override if w in colors]
            else:
                self.wire_sequence = self.protocols.compute_wire_sequence(colors, m.get("ruleset", "basic_rsp"))
            self.wire_engine.generate_wires(self.renderer.board_rect, colors)
        else:
            self.wire_sequence = []
            self.wire_engine.wires = []
        self.manual_lines = self._build_teleop_manual(colors)
        self.renderer.serial_number = random.randint(100000, 999999)
        self._sync_workspace_layout()

        self.hand_ui.reset_holds()
        self.wire_coach.reset()
        self._begin_chapter_intro()
        self.reporter.log_event("mission_start", {"mission_id": m["id"], "mode": "remote_teleop"})
        self._notify(f"Op loaded: {m['name']}")
        print(f"RSP sequence (remote cutter): {' -> '.join(self.wire_sequence)}")

    def _build_teleop_manual(self, wires: List[str]) -> List[str]:
        m = self.missions.current
        story = m.get("story", {})
        lines = [
            f"CH{m.get('chapter', '?')} — {story.get('victim', 'Unknown')}",
            story.get("task", m.get("description", ""))[:54],
            f"Defusal: {m.get('defusal_label', 'REMOTE TELEOP')}",
        ]
        if self.wire_sequence:
            labels = m.get("wire_labels", {})
            lines.append(f"Cut order: {' -> '.join(self.wire_sequence)}")
            nxt = self.wire_sequence[self.wire_target_idx] if self.wire_target_idx < len(self.wire_sequence) else None
            if nxt:
                reason = labels.get(nxt, m.get("wire_cut_brief", f"Isolate {nxt} circuit"))
                lines.append(f"NEXT: {nxt} — {reason[:48]}")
        elif m.get("mechanic_targets"):
            lines.append(f"Sequence: {' -> '.join(m['mechanic_targets'])}")
        return lines[:5]

    def _remaining_time(self) -> float:
        if self.timer_start is None:
            return float(self.time_limit)
        return max(0.0, self.time_limit - (time.time() - self.timer_start))

    def _phase_order(self) -> List[OpPhase]:
        return [
            OpPhase.THREAT_CONFIRMATION,
            OpPhase.CORDON,
            OpPhase.ROBOT_DEPLOY,
            OpPhase.TELEOP_RSP,
            OpPhase.POST_BLAST_REPORT,
        ]

    def _advance_phase(self) -> None:
        phases = set(self.missions.current.get("phases", []))
        mapping = {p.value: p for p in self._phase_order()}
        order = self._phase_order()
        try:
            idx = order.index(self.phase)
        except ValueError:
            return
        for nxt in order[idx + 1 :]:
            if nxt.value not in phases:
                continue
            if nxt == OpPhase.TELEOP_RSP and self.timer_start is None:
                self.timer_start = time.time()
            self.phase = nxt
            self.protocols.record_phase(nxt.value)
            self.evaluator.record_phase()
            self.reporter.log_event("phase_advance", {"phase": nxt.value})
            self._notify(PlatformUI.PHASE_LABELS.get(nxt.value, nxt.value))
            self.hand_ui.reset_holds()
            return

    def _cordon_rects(self) -> List[Tuple[int, int, int, int]]:
        return self.layout.cordon_rects(len(self.protocols.five_cs))

    def _handle_menu(self, frame, hand_data: Dict) -> None:
        missions = self.missions.list_missions()
        rects = self.layout.mission_row_rects(len(missions))
        prev_sel = self.menu_selection

        for i, rect in enumerate(rects):
            m = missions[i]
            row_cursor = self.hand_ui.get_cursor(hand_data, rect)
            if self.hand_ui.point_in_rect(row_cursor, rect) and m.get("unlocked"):
                self.menu_selection = i
            PlatformUI.draw_mission_row(
                frame, rect,
                m["name"],
                i == self.menu_selection, m.get("unlocked", False), m.get("completed", False),
                chapter=m.get("chapter", i + 1), theme=m.get("theme", ""),
            )

        if self.menu_selection != prev_sel or self._menu_dialogue_mission != missions[self.menu_selection]["id"]:
            sel_m = missions[self.menu_selection]
            self._menu_dialogue_mission = sel_m["id"]
            self.dialogue.load_chapter_intro(sel_m)

        sel_mission = missions[self.menu_selection]
        self.workspace.draw_chapter_preview(frame, sel_mission, True, self.layout.preview_rect)
        self.dialogue.update()
        self.dialogue.draw(frame, y_offset=-130)

        hovered = self.hand_ui.point_in_rect(
            self.hand_ui.get_cursor(hand_data, self.start_btn), self.start_btn
        )
        ok, prog = self.hand_ui.hold_confirm(hand_data, "start", self.start_btn, 0.5)
        self.hand_ui.draw_button(frame, self.start_btn, "TARGET — DEPLOY CHAPTER", hovered, prog, (0, 190, 255))
        if ok and missions[self.menu_selection].get("unlocked"):
            self._start_mission(missions[self.menu_selection]["id"])

        recal, _ = self.hand_ui.gesture_hold(hand_data, "peace", 2.5, blocked=hand_data.get("pinch_active"))
        if recal:
            self.calibration = CalibrationFlow(self.frame_width, self.frame_height)
            self.calibration.profile.completed = False
            self.calibration.finished = False
            self.calibration._active = True
            self.phase = OpPhase.CALIBRATION
            self.hand_tracker.reload_calibration()
            self._notify("Recalibrating operator biometric link")

    def _dialogue_advance_rect(self) -> Tuple[int, int, int, int]:
        w, h = self.frame_width, self.frame_height
        return (32, h - 200, w - 64, 120)

    def _handle_chapter_intro(self, frame, hand_data: Dict, dt: float) -> None:
        self.dialogue.update(dt)
        self.dialogue.draw(frame, y_offset=0)
        self.dialogue.draw_shout_burst(frame, self.frame_width // 2, 120, 0.8)

        dlg_rect = self._dialogue_advance_rect()
        if not self.dialogue.finished:
            ok, _ = self.hand_ui.hold_confirm(hand_data, "dlg_adv", dlg_rect, 0.4)
            if ok:
                self.dialogue.advance()
            cv2.rectangle(frame, dlg_rect, (40, 50, 60), 1, cv2.LINE_AA)
            return

        hovered = self.hand_ui.point_in_rect(self.hand_ui.get_cursor(hand_data, self.confirm_btn), self.confirm_btn)
        ok, prog = self.hand_ui.hold_confirm(hand_data, "intro_ready", self.confirm_btn, 0.55)
        self.hand_ui.draw_button(frame, self.confirm_btn, "TARGET — TAKE CONTROL", hovered, prog, (0, 220, 140))
        if ok:
            self.phase = OpPhase.THREAT_CONFIRMATION
            self.hand_ui.reset_holds()
            self._notify("Control is yours — proceed to threat confirmation")

    def _handle_threat_confirmation(self, frame, hand_data: Dict) -> None:
        hovered = self.hand_ui.point_in_rect(
            self.hand_ui.get_cursor(hand_data, self.confirm_btn), self.confirm_btn
        )
        ok, prog = self.hand_ui.hold_confirm(hand_data, "threat_ok", self.confirm_btn, 0.45)
        self.hand_ui.draw_button(frame, self.confirm_btn, "TARGET — CONFIRM THREAT", hovered, prog)
        if ok:
            self._advance_phase()

    def _handle_cordon(self, hand_data: Dict) -> None:
        for i, rect in enumerate(self._cordon_rects()):
            c = self.protocols.five_cs[i]
            if c["id"] in self.protocols.completed_cs:
                continue
            ok, _ = self.hand_ui.hold_confirm(hand_data, f"c_{c['id']}", rect, 0.65)
            if ok:
                if self.protocols.complete_c(c["id"]):
                    self.audio.protocol_ack()
                    self._notify(f"Cordon: {c['name']}")
                if self.protocols.all_cs_complete():
                    self._advance_phase()
                break

    def _handle_teleop_rsp(self, hand_data: Dict, bio: BiometricSnapshot, scene) -> str:
        """Returns live coach hint for the hint bar."""
        m = self.missions.current
        cursor = self._teleop_cursor(hand_data)
        tool = self._teleop_tool_point(hand_data)
        self.robot.update(hand_data, bio, self.renderer.bomb_rect, tool or cursor)
        tool = self.robot.get_tool_pos() or tool
        default_hint = m.get("defusal_label", "Complete defusal task")

        if m.get("robot_fault") and self.robot.state.fault_active and not self.robot.state.fault_cleared:
            ok, _ = self.hand_ui.gesture_hold(hand_data, "peace", 1.0)
            if ok:
                self.robot.state.fault_cleared = True
                self._notify("Robot arm fault cleared")
            return "Peace sign 1s — clear robot arm fault"

        if self.robot.state.estop:
            return "E-STOP active — open palm cleared, resume when ready"

        if self.mechanic_state and not self.mechanics.uses_wire_rsp(self.mechanic_state):
            if bio.tremor_index < m.get("tremor_threshold", 0.4):
                self.steady_counter += 1
            else:
                self.steady_counter = max(0, self.steady_counter - 1)
            self.evaluator.sample_biometrics(bio.stability, bio.tremor_index)
            result = self.mechanics.update_non_wire(
                self.mechanic_state, m, hand_data, self.hand_ui, cursor, tool, bio, self.steady_counter, self.renderer.bomb_rect,
            )
            if result == "complete":
                self._advance_phase()
            elif result == "fail":
                self._fail("Wrong sequence — device functioned")
            elif result == "stage":
                self.manual_lines = self._build_teleop_manual([])
                self._notify(f"Stage {self.mechanic_state.stage_idx}/{len(self.mechanic_state.stages)} complete")
            return default_hint

        if tool is None:
            self.steady_counter = 0
            for w in self.wire_engine.wires:
                w.snip_progress = 0.0
            msg = self.wire_coach.coach_message(
                None,
                self.wire_sequence[self.wire_target_idx] if self.wire_target_idx < len(self.wire_sequence) else "?",
                m.get("wire_labels", {}),
                None, (0, 0, 0, 0), False, 0.0, True, bio.tremor_index, 0,
                self.wire_target_idx, len(self.wire_sequence), 999.0,
            )
            self.wire_coach.queue_overlay(None, None, "", False, 0.0, msg)
            return msg.primary

        max_tension = self.wire_engine.update_tension(tool, bio.tremor_index)
        self.audio.update_heartbeat(bio.stress_level, max_tension)
        self.evaluator.sample_biometrics(bio.stability, bio.tremor_index)

        req = self._steady_required()
        if bio.tremor_index < m.get("tremor_threshold", 0.4):
            self.steady_counter += 1
        else:
            self.steady_counter = max(0, self.steady_counter - 2)

        if m.get("device_type") == "victim_operated_ied" and bio.shiver_detected:
            self._fail("BOOM — approach disturbance detected on device")
            return default_hint

        if self.wire_target_idx >= len(self.wire_sequence):
            return "All circuits isolated — stand by"

        if self.wire_coach.in_success_pause:
            done_msg = self.wire_coach.coach_message(
                wire, target, labels, tool, cz, on_target, 1.0, False,
                bio.tremor_index, self.steady_counter, self.wire_target_idx, len(self.wire_sequence), dist,
            )
            self.wire_coach.queue_overlay(wire, cz, target, on_target, 1.0, done_msg)
            return done_msg.primary

        target = self.wire_sequence[self.wire_target_idx]
        wire_idx = next((i for i, w in enumerate(self.wire_engine.wires) if w.color == target and not w.is_cut), None)
        if wire_idx is None:
            return default_hint

        wire = self.wire_engine.wires[wire_idx]
        labels = m.get("wire_labels", {})
        cz = wire.cut_zone
        cx, cy = cz[0] + cz[2] // 2, cz[1] + cz[3] // 2
        dist = ((tool[0] - cx) ** 2 + (tool[1] - cy) ** 2) ** 0.5
        on_target = self.hand_ui.point_in_rect(self._teleop_cursor(hand_data), cz, pad=8)

        for i, other in enumerate(self.wire_engine.wires):
            if other.is_cut or other.color == target:
                continue
            if self.wire_engine._point_in_rect(tool, other.cut_zone) or self.wire_engine._distance_to_wire(tool, other) < 50:
                self.evaluator.record_cut(False)
                self._fail(f"Wrong circuit — {other.color} is not next in analysis")
                return default_hint

        blocked = bio.tremor_index > m.get("tremor_threshold", 0.4) or self.steady_counter < max(3, req // 3)
        ok_hold, prog = self.hand_ui.hold_confirm(
            hand_data, f"wire_{wire_idx}", cz, self.wire_coach.HOLD_DURATION, blocked=blocked
        )
        for w in self.wire_engine.wires:
            if w is not wire and not w.is_cut:
                w.snip_progress = max(0.0, w.snip_progress - 0.15)

        coach_msg = self.wire_coach.coach_message(
            wire, target, labels, tool, cz, on_target, prog, blocked,
            bio.tremor_index, self.steady_counter, self.wire_target_idx, len(self.wire_sequence), dist,
        )
        self.wire_coach.queue_overlay(wire, cz, target, on_target, prog, coach_msg)

        if not ok_hold:
            return coach_msg.primary

        ok, msg = self.wire_engine.can_cut(
            wire_idx, tool, bio.tremor_index,
            m.get("wire_tension_limit", 0.85), req, self.steady_counter,
        )
        if not ok:
            warn = self.wire_coach.coach_message(
                wire, target, labels, tool, cz, on_target, prog, True,
                bio.tremor_index, self.steady_counter, self.wire_target_idx, len(self.wire_sequence), dist,
            )
            warn.primary = msg
            warn.tone = "warn"
            self.wire_coach.queue_overlay(wire, cz, target, on_target, prog, warn)
            return msg

        wire = self.wire_engine.apply_cut(wire_idx)
        self.renderer.trigger_cut_sparks(wire)
        self.audio.wire_cut_spark()
        self.evaluator.record_cut(True)
        self.wire_target_idx += 1
        self.steady_counter = 0
        self.hand_ui.reset_holds()
        self.manual_lines = self._build_teleop_manual([])
        self.wire_coach.trigger_success(target)
        self.reporter.log_event("teleop_cut", {"color": target, "lag_ms": m.get("comms_lag_ms", 0)})

        if self.wire_target_idx >= len(self.wire_sequence):
            if self.mechanic_state and self.mechanic_state.defusal_type == "multi_stage":
                nxt = self.mechanics._advance_multi(self.mechanic_state)
                if nxt == "stage":
                    self._notify(f"Stage {self.mechanic_state.stage_idx}/{len(self.mechanic_state.stages)} — continue defusal")
                    return coach_msg.primary
            self._advance_phase()
        return coach_msg.primary

    def _handle_post_blast(self, frame, hand_data: Dict) -> None:
        hovered = self.hand_ui.point_in_rect(
            self.hand_ui.get_cursor(hand_data, self.aar_btn), self.aar_btn
        )
        ok, prog = self.hand_ui.hold_confirm(hand_data, "aar", self.aar_btn, 0.65)
        self.hand_ui.draw_button(frame, self.aar_btn, "TARGET — SUBMIT AAR", hovered, prog, (0, 200, 120))
        if ok:
            self._succeed()

    def _succeed(self) -> None:
        self.evaluator.report_submitted = True
        self.final_report = self.evaluator.evaluate(self.missions.current.get("pass_score", 70), True)
        self.missions.complete_current(self.final_report.passed)
        self.audio.success_chime()
        self.phase = OpPhase.SUCCESS
        self._save_session(True)
        self._notify("Operator certified — render safe")

    def _fail(self, reason: str) -> None:
        self.protocols.record_violation(reason)
        self.evaluator.add_violation(reason)
        self.final_report = self.evaluator.evaluate(self.missions.current.get("pass_score", 70), False)
        self.renderer.trigger_explosion()
        self.audio.detonation()
        self.shake_intensity = 18.0
        self.phase = OpPhase.FAILURE
        self._save_session(False)
        self._notify("DETONATION — " + reason[:28])

    def _save_session(self, success: bool) -> None:
        bio_summary = {
            "avg_stability": round(sum(self.evaluator.steadiness_samples) / max(1, len(self.evaluator.steadiness_samples)), 3),
            "avg_tremor": round(sum(self.evaluator.tremor_samples) / max(1, len(self.evaluator.tremor_samples)), 3),
            "teleop_mode": "remote_ugv",
            "comms_lag_ms": self.missions.current.get("comms_lag_ms", 0),
        }
        wire_data = {"sequence": self.wire_sequence, "cuts": self.wire_target_idx, "wires": [w.color for w in self.wire_engine.wires]}
        perf = {
            "passed": self.final_report.passed if self.final_report else False,
            "overall_score": self.final_report.overall_score if self.final_report else 0,
            "grade": self.final_report.grade if self.final_report else "FAIL",
            "categories": self.final_report.categories if self.final_report else {},
            "violations": self.final_report.violations if self.final_report else [],
            "recommendations": self.final_report.recommendations if self.final_report else [],
        }
        report = self.reporter.build_report(self.missions.current, perf, bio_summary, wire_data)
        path = self.reporter.save_local(report)
        if self.reporter.sync_to_api(report):
            print(f"Session synced to API: {self.reporter.api_url}")
        print(f"Certification AAR saved: {path}")

    def _current_wire_index(self) -> Optional[int]:
        if self.wire_target_idx >= len(self.wire_sequence):
            return None
        t = self.wire_sequence[self.wire_target_idx]
        for i, w in enumerate(self.wire_engine.wires):
            if w.color == t and not w.is_cut:
                return i
        return None

    def _draw_cordon_screen(self, frame) -> None:
        cv2.putText(frame, "CORDON & 5 Cs — establish remote ops perimeter", (40, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1)
        y = 72
        for i, c in enumerate(self.protocols.five_cs):
            done = c["id"] in self.protocols.completed_cs
            mark, col = ("[X]", (0, 220, 140)) if done else ("[ ]", (220, 222, 228))
            cv2.rectangle(frame, (35, y - 8), (self.frame_width - 35, y + 32), (18, 22, 28), -1)
            cv2.putText(frame, f"{mark} {c['name']}: {c['description'][:50]}", (45, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
            y += 52

    def _draw_steady_meter(self, frame, progress: float) -> None:
        x, y, w, h = self.frame_width // 2 - 110, 168, 220, 14
        cv2.rectangle(frame, (x, y), (x + w, y + h), (35, 38, 45), -1)
        cv2.rectangle(frame, (x, y), (x + int(w * progress), y + h), (0, 200, 110), -1)
        cv2.putText(frame, f"TELEOP STEADY {int(progress * 100)}%", (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 220, 180), 1)

    def run(self) -> None:
        print("\nVIRTUAL TELEOP BAY — 8 story chapters")
        print("  Biometric calibration on first launch")
        print("  Green skeletal hand — corner cam preview, tracking spans full display")
        print("  Point fingertip target on buttons/zones — hold to activate  |  Fist 2.5s = quit\n")

        last_frame = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt = now - last_frame
            last_frame = now

            ret, camera = self.cap.read()
            if not ret:
                break
            camera = cv2.flip(camera, 1)
            self._sync_display_dimensions(camera.shape[1], camera.shape[0])
            hand_data = self.hand_tracker.process(camera, stability=self._last_stability, mirror=True)

            bio = BiometricSnapshot(1, 0, 0, 0, False, 0, "")
            track_pt = hand_data.get("primary_center")
            if track_pt:
                bio = self.biometrics.update(track_pt, time.time())
                self._last_stability = bio.stability

            if self.timer_start and self._remaining_time() <= 0 and self.phase == OpPhase.TELEOP_RSP:
                self._fail("Timer expired — device functioned")

            progress = self.wire_target_idx / max(1, len(self.wire_sequence) or 1)
            teleop_status = self.robot.state.status_line if self.phase not in (OpPhase.MENU, OpPhase.CALIBRATION) else "STANDBY"

            if self.phase == OpPhase.CALIBRATION:
                scene = self.workspace.create_scene("command")
                self.calibration.update(hand_data, dt)
                self.calibration.draw(scene, hand_data)
                if self.calibration.finished:
                    self.workspace.apply_calibration(self.calibration.profile)
                    self.hand_tracker.reload_calibration()
                    self.phase = OpPhase.MENU
                    self._notify("Neural link established — Control is yours")
            elif self.phase == OpPhase.MENU:
                ml = self.missions.list_missions()
                menu_theme = ml[self.menu_selection].get("theme", "warehouse") if ml else "warehouse"
                scene = self.workspace.create_scene(menu_theme)
                PlatformUI.draw_menu_header(scene)
                self._handle_menu(scene, hand_data)
                quit_blocked = hand_data.get("pinch_active")
                done, _ = self.hand_ui.gesture_hold(hand_data, "fist", 2.5, blocked=quit_blocked)
                if done:
                    break
            else:
                m = self.missions.current
                theme = m.get("theme", "warehouse")
                scene = self.workspace.create_scene(theme)
                story = m.get("story", {})
                self.workspace.draw_header(scene, m.get("name", "OPERATION")[:48], story.get("victim", ""))
                if self.phase != OpPhase.CHAPTER_INTRO:
                    self.workspace.draw_story_panel(scene, story, m.get("chapter", 1))

            if self.phase == OpPhase.CHAPTER_INTRO:
                m = self.missions.current
                self._handle_chapter_intro(scene, hand_data, dt)
                PlatformUI.draw_hint_bar(scene, "Hold target on dialogue box to advance  |  Then TARGET — TAKE CONTROL")

            elif self.phase == OpPhase.THREAT_CONFIRMATION:
                m = self.missions.current
                self.renderer.draw_device(scene, self.wire_engine.wires, m.get("device_type", "training_ied"),
                    self._remaining_time(), self.robot.state.deployed)
                self.robot.draw(scene, self.renderer.bomb_rect, self.phase.value)
                PlatformUI.draw_ops_panel(scene, self.phase.value, m["name"], bio, 0, teleop_status, self.manual_lines)
                self._handle_threat_confirmation(scene, hand_data)
                PlatformUI.draw_hint_bar(scene, "Place target on CONFIRM THREAT — hold to activate")

            elif self.phase == OpPhase.CORDON:
                self._draw_cordon_screen(scene)
                self._handle_cordon(hand_data)
                PlatformUI.draw_hint_bar(scene, "Place target on each C row — hold to confirm")

            elif self.phase in (OpPhase.ROBOT_DEPLOY, OpPhase.TELEOP_RSP):
                teleop_hint = m.get("defusal_label", "Complete defusal task")
                if self.phase == OpPhase.TELEOP_RSP:
                    req = self._steady_required()
                    self._draw_steady_meter(scene, min(1.0, self.steady_counter / req))
                    self.wire_coach.update_animations(self.wire_engine.wires, dt)
                    teleop_hint = self._handle_teleop_rsp(hand_data, bio, scene)

                self.renderer.draw_device(
                    scene, self.wire_engine.wires, m.get("device_type", "training_ied"),
                    self._remaining_time(), self.robot.state.deployed,
                    highlight_wire=self._current_wire_index() if self.phase == OpPhase.TELEOP_RSP else None,
                    show_cut_zones=self.phase == OpPhase.TELEOP_RSP and self.mechanics.uses_wire_rsp(self.mechanic_state or MechanicState()),
                )
                self.robot.draw(scene, self.renderer.bomb_rect, self.phase.value)
                if self.phase == OpPhase.TELEOP_RSP and self.mechanic_state:
                    self.mechanics.draw(scene, self.renderer.bomb_rect, self.mechanic_state, m)
                PlatformUI.draw_ops_panel(scene, self.phase.value, m["name"], bio, progress, teleop_status, self.manual_lines)
                PlatformUI.draw_gesture_legend_compact(scene)

                if self.phase == OpPhase.ROBOT_DEPLOY:
                    zone = self.robot.deploy_zone_rect()
                    ok, prog = self.hand_ui.hold_confirm(hand_data, "deploy", zone, 1.0, require_pinch=False)
                    if self.hand_ui.point_in_rect(self.hand_ui.get_cursor(hand_data, zone), zone):
                        cv2.rectangle(scene, (zone[0], zone[1]), (zone[0] + zone[2], zone[1] + zone[3]), (0, 200, 255), 2)
                    if ok:
                        self.robot.mark_deployed()
                        self.evaluator.remote_tool_placed = True
                        self.audio.protocol_ack()
                        self._notify("UGV deployed — virtual link live")
                        self._advance_phase()
                    PlatformUI.draw_hint_bar(scene, "Place target in DEPLOY zone — hold 1 second")
                else:
                    if self.mechanics.uses_wire_rsp(self.mechanic_state or MechanicState()):
                        self.wire_coach.draw_overlay(scene)
                    PlatformUI.draw_hint_bar(scene, teleop_hint)

            elif self.phase == OpPhase.POST_BLAST_REPORT:
                self.renderer.draw_device(scene, self.wire_engine.wires, m.get("device_type", "training_ied"), 0, True)
                PlatformUI.draw_ops_panel(scene, self.phase.value, m["name"], bio, 1.0, "Submit certification AAR", self.manual_lines)
                self._handle_post_blast(scene, hand_data)
                PlatformUI.draw_hint_bar(scene, "Place target on SUBMIT AAR — hold to activate")

            elif self.phase in (OpPhase.SUCCESS, OpPhase.FAILURE):
                m = self.missions.current
                self.renderer.draw_device(scene, self.wire_engine.wires, m.get("device_type", "training_ied"), 0, True)
                if self.final_report:
                    PlatformUI.draw_certification_result(scene, self.final_report, self.phase == OpPhase.SUCCESS)
                ok, _ = self.hand_ui.gesture_hold(hand_data, "open_hand", 1.0, blocked=hand_data.get("pinch_active"))
                if ok:
                    self.phase = OpPhase.MENU
                    self.hand_ui.reset_holds()
                    self.robot.reset()
                    self.renderer.effects.reset()

            self.workspace.draw_pip(scene, camera)
            self.workspace.draw_tracking_fov(scene)
            if hand_data.get("left_hand") or hand_data.get("right_hand"):
                self.hand_ui.draw_cursors(scene, hand_data)
                self.hand_ui.draw_tracking_skeleton(scene, hand_data)

            if self._status_until > time.time() and self._status_msg:
                cv2.rectangle(scene, (self.frame_width // 2 - 230, 38), (self.frame_width // 2 + 230, 68), (0, 0, 0), -1)
                cv2.putText(scene, self._status_msg[:46], (self.frame_width // 2 - 220, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

            if self.shake_intensity > 0:
                scene = self.renderer.apply_screen_shake(scene, self.shake_intensity)
                self.shake_intensity *= 0.88

            fps_val = self.fps.update()
            self.fps.draw(scene, fps_val)

            cv2.imshow("EOD Operator Readiness Platform — Virtual Teleop Bay", scene)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.cleanup()

    def cleanup(self) -> None:
        self.cap.release()
        self.hand_tracker.release()
        self.audio.shutdown()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    try:
        EODReadinessPlatform().run()
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as exc:
        import traceback
        print(exc)
        traceback.print_exc()
