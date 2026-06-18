"""Clean platform HUD for EOD Operator Readiness."""

from __future__ import annotations

from typing import List, Optional

import cv2

TAGLINE = "Train the human behind the robot — decisions, stress, and remote precision."


class PlatformUI:
    PHASE_LABELS = {
        "calibration": "BIOMETRIC SCAN",
        "menu": "CHAPTER SELECT",
        "chapter_intro": "MISSION BRIEFING",
        "threat_confirmation": "THREAT CONFIRMATION",
        "cordon": "CORDON & 5 Cs",
        "robot_deploy": "ROBOT DEPLOY",
        "teleop_rsp": "TELEOP DEFUSAL",
        "post_blast_report": "POST-BLAST AAR",
        "success": "CERTIFIED",
        "failure": "INCIDENT FAIL",
    }

    @staticmethod
    def _blend_roi(frame, y1: int, y2: int, x1: int, x2: int, color, alpha: float = 0.88) -> None:
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return
        overlay = roi.copy()
        cv2.rectangle(overlay, (0, 0), (x2 - x1, y2 - y1), color, -1)
        frame[y1:y2, x1:x2] = cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0)

    @staticmethod
    def draw_menu_header(frame, selected_mission: str = "") -> None:
        h, w = frame.shape[:2]
        PlatformUI._blend_roi(frame, 0, 110, 0, w, (12, 14, 18), 0.92)
        cv2.putText(frame, "EOD OPERATOR READINESS — 8 CHAPTERS", (24, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 215, 255), 2)
        cv2.putText(frame, TAGLINE, (24, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 150, 160), 1)
        cv2.putText(frame, "Virtual teleop bay  |  Camera controls operator gloves  |  IMAS 09.31", (24, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (90, 100, 110), 1)

    @staticmethod
    def draw_mission_row(
        frame, rect, text: str, selected: bool, unlocked: bool, completed: bool,
        chapter: int = 0, theme: str = "",
    ) -> None:
        x, y, w, h = rect
        if not unlocked:
            bg, fg, accent = (20, 22, 28), (65, 68, 75), (40, 42, 48)
        elif selected:
            bg, fg, accent = (18, 32, 48), (0, 235, 255), (0, 180, 255)
        else:
            bg, fg, accent = (16, 20, 28), (190, 195, 205), (50, 58, 68)

        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), bg, -1)
        cv2.addWeighted(overlay, 0.92, frame, 0.08, 0, frame)
        cv2.rectangle(frame, (x, y), (x + w, y + h), accent, 1, cv2.LINE_AA)

        if selected and unlocked:
            cv2.rectangle(frame, (x, y), (x + 5, y + h), (0, 200, 255), -1)
            glow = frame.copy()
            cv2.rectangle(glow, (x - 2, y - 2), (x + w + 2, y + h + 2), (0, 160, 220), 1, cv2.LINE_AA)
            cv2.addWeighted(glow, 0.25, frame, 0.75, 0, frame)

        if chapter:
            cv2.putText(frame, f"CH{chapter}", (x + 12, y + h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.38, accent, 1, cv2.LINE_AA)
            text_x = x + 52
        else:
            text_x = x + 14

        suffix = "  [DONE]" if completed else ("  [LOCKED]" if not unlocked else "")
        display = text if len(text) < 42 else text[:39] + "..."
        cv2.putText(frame, display + suffix, (text_x, y + h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.42, fg, 1, cv2.LINE_AA)

        if theme and unlocked:
            cv2.putText(frame, theme.upper()[:8], (x + w - 72, y + h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (90, 100, 115), 1, cv2.LINE_AA)

    @staticmethod
    def draw_ops_panel(
        frame,
        phase: str,
        mission_name: str,
        bio,
        progress: float,
        teleop_status: str,
        cert_lines: Optional[List[str]] = None,
    ) -> None:
        cert_lines = cert_lines or []
        panel_h = 118
        PlatformUI._blend_roi(frame, 34, 34 + panel_h, 0, 440, (10, 12, 16), 0.82)

        phase_label = PlatformUI.PHASE_LABELS.get(phase, phase.upper())
        cv2.putText(frame, phase_label, (14, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 220, 255), 1)
        cv2.putText(frame, mission_name[:36], (14, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 170, 180), 1)
        cv2.putText(
            frame,
            f"Readiness {bio.stability:.0%}  |  Tremor {bio.tremor_index:.0%}  |  Stress {bio.stress_level:.0%}",
            (14, 98),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (120, 200, 140),
            1,
        )
        cv2.putText(frame, teleop_status[:42], (14, 118), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (100, 180, 255), 1)
        cv2.putText(frame, bio.recommendation[:44], (14, 138), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (140, 140, 150), 1)

        bx, by, bw, bh = 14, 148, 320, 8
        cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (40, 42, 48), -1)
        cv2.rectangle(frame, (bx, by), (bx + int(bw * progress), by + bh), (0, 190, 120), -1)

        py = frame.shape[0] - 155
        cv2.rectangle(frame, (8, py), (460, frame.shape[0] - 58), (10, 12, 16), -1)
        cv2.rectangle(frame, (8, py), (460, frame.shape[0] - 58), (45, 50, 58), 1)
        for i, line in enumerate(cert_lines[:4]):
            cv2.putText(frame, line[:54], (16, py + 22 + i * 20), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (210, 212, 218), 1)

    @staticmethod
    def draw_hint_bar(frame, text: str) -> None:
        y = frame.shape[0] - 42
        cv2.rectangle(frame, (0, y - 8), (frame.shape[1], frame.shape[0]), (8, 10, 14), -1)
        cv2.putText(frame, text, (16, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 210, 255), 1)

    @staticmethod
    def draw_gesture_legend_compact(frame) -> None:
        x, y = frame.shape[1] - 200, frame.shape[0] - 148
        cv2.rectangle(frame, (x, y), (frame.shape[1] - 8, frame.shape[0] - 50), (15, 18, 22), -1)
        cv2.rectangle(frame, (x, y), (frame.shape[1] - 8, frame.shape[0] - 50), (50, 60, 70), 1)
        lines = ["Target = UI + cut zones", "Hold steady = actuate", "Palm = E-STOP", "Peace = recalibrate", "Fist 2.5s = quit"]
        cv2.putText(frame, "GESTURES", (x + 8, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 255), 1)
        for i, line in enumerate(lines):
            cv2.putText(frame, line, (x + 8, y + 34 + i * 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (170, 180, 190), 1)

    @staticmethod
    def draw_certification_result(frame, report, success: bool) -> None:
        h, w = frame.shape[:2]
        x1, y1 = w // 2 - 300, h // 2 - 120
        x2, y2 = w // 2 + 300, h // 2 + 140
        PlatformUI._blend_roi(frame, y1, y2, x1, x2, (12, 14, 18), 0.88)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255) if success else (0, 0, 200), 2)

        title = "OPERATOR CERTIFIED — RENDER SAFE" if success else "READINESS FAIL — REVIEW AAR"
        color = (0, 220, 140) if success else (0, 80, 255)
        cv2.putText(frame, title, (w // 2 - 280, h // 2 - 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        cv2.putText(frame, f"Score {report.overall_score}  |  Grade {report.grade}", (w // 2 - 160, h // 2 - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 222, 228), 1)
        y = h // 2 - 10
        for k, v in report.categories.items():
            label = k.replace("_", " ").title()
            cv2.putText(frame, f"{label}: {v}%", (w // 2 - 180, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (170, 175, 185), 1)
            y += 22
        cv2.putText(frame, "OPEN PALM 1s — return to chapters", (w // 2 - 160, h // 2 + 110), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 130, 140), 1)
