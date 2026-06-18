"""Duolingo-style guided wire cut flow — live coaching + smooth cut animations."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import cv2

from eod_training.animation import TimedValue, ease_in_out_cubic, ease_out_cubic, pulse
from eod_training.wire_physics import WireState


@dataclass
class CoachMessage:
    primary: str
    secondary: str
    step_label: str
    tone: str = "guide"  # guide | good | warn | success


class WireCutCoach:
    HOLD_DURATION = 0.72

    def __init__(self) -> None:
        self._smooth_hold = TimedValue(0.0, 0.12)
        self._pulse_t = 0.0
        self._success_until = 0.0
        self._success_label = ""
        self._last_message = CoachMessage("Ready", "", "")
        self._pending_zone: Optional[Tuple[int, int, int, int]] = None
        self._pending_wire: Optional[WireState] = None
        self._pending_color = ""
        self._pending_on_target = False
        self._pending_hold = 0.0

    def reset(self) -> None:
        self._smooth_hold = TimedValue(0.0, 0.12)
        self._success_until = 0.0
        self._success_label = ""
        self._pending_zone = None
        self._pending_wire = None

    def queue_overlay(
        self,
        wire: Optional[WireState],
        cut_zone: Optional[Tuple[int, int, int, int]],
        wire_color: str,
        on_target: bool,
        hold_prog: float,
        msg: CoachMessage,
    ) -> None:
        self._pending_wire = wire
        self._pending_zone = cut_zone
        self._pending_color = wire_color
        self._pending_on_target = on_target
        self._pending_hold = hold_prog
        self._last_message = msg

    def draw_overlay(self, frame) -> None:
        if self._pending_wire and self._pending_zone:
            self.draw_cut_zone(
                frame, self._pending_wire, self._pending_zone,
                self._pending_hold, self._pending_color, self._pending_on_target,
            )
        self.draw_coach_panel(frame, self._last_message)
        self.draw_success_flash(frame)

    @property
    def in_success_pause(self) -> bool:
        return time.time() < self._success_until

    def trigger_success(self, wire_color: str, seconds: float = 1.15) -> None:
        self._success_label = wire_color
        self._success_until = time.time() + seconds
        self._smooth_hold.set_target(0.0, 0.2)

    def update_animations(self, wires, dt: float) -> None:
        self._pulse_t += dt
        for wire in wires:
            if wire.is_cut and wire.cut_anim < 1.0:
                wire.cut_anim = min(1.0, wire.cut_anim + dt * 2.2)

    def coach_message(
        self,
        wire: Optional[WireState],
        wire_color: str,
        labels: Dict[str, str],
        tool: Optional[Tuple[int, int]],
        cut_zone: Tuple[int, int, int, int],
        on_target: bool,
        hold_prog: float,
        blocked: bool,
        tremor: float,
        steady: int,
        step_idx: int,
        total_steps: int,
        distance: float,
    ) -> CoachMessage:
        reason = labels.get(wire_color, f"Isolate the {wire_color} circuit")
        step_label = f"Wire {step_idx + 1} of {total_steps}"

        if self.in_success_pause:
            return CoachMessage(
                f"{wire_color} wire isolated!",
                "Great control — preparing next step...",
                step_label,
                "success",
            )

        if hold_prog >= 0.92:
            return CoachMessage(
                "Finishing cut...",
                "Keep your fingertip perfectly still",
                step_label,
                "good",
            )
        if hold_prog >= 0.2:
            pct = int(hold_prog * 100)
            return CoachMessage(
                f"Cutting {wire_color} wire — {pct}%",
                "Hold steady on the glowing zone",
                step_label,
                "good",
            )
        if on_target and blocked:
            if tremor > 0.38:
                return CoachMessage(
                    "Ease your breathing",
                    "Lower tremor before the cutter engages",
                    step_label,
                    "warn",
                )
            return CoachMessage(
                "Stabilize your hand",
                f"Almost ready — {wire_color}: {reason}",
                step_label,
                "warn",
            )
        if on_target:
            return CoachMessage(
                "Perfect — hold to start cutting",
                reason,
                step_label,
                "good",
            )
        if distance < 55:
            return CoachMessage(
                f"Place fingertip on the {wire_color} cut zone",
                reason,
                step_label,
                "guide",
            )
        if distance < 120:
            return CoachMessage(
                f"Move closer to the {wire_color} wire",
                "Follow the highlighted cut marker",
                step_label,
                "guide",
            )
        if tool is not None:
            return CoachMessage(
                f"Approach the {wire_color} wire",
                reason,
                step_label,
                "guide",
            )
        return CoachMessage(
            "Point your green fingertip at the device",
            f"Next: cut {wire_color} wire — {reason}",
            step_label,
            "guide",
        )

    def update_smooth_hold(self, hold_prog: float) -> float:
        self._smooth_hold.set_target(hold_prog, 0.1)
        return self._smooth_hold.update()

    def draw_cut_zone(
        self,
        frame,
        wire: WireState,
        cut_zone: Tuple[int, int, int, int],
        hold_prog: float,
        wire_color: str,
        on_target: bool,
    ) -> None:
        x, y, w, h = cut_zone
        cx, cy = x + w // 2, y + h // 2
        smooth = self.update_smooth_hold(hold_prog)
        wire.snip_progress = smooth

        ring = int(34 + 8 * math.sin(self._pulse_t * 5))
        glow = int(180 + 60 * pulse(self._pulse_t, 3.5))
        ring_col = (0, glow, 255) if on_target else (0, 140, 200)
        cv2.circle(frame, (cx, cy), ring, ring_col, 2, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), ring - 10, (ring_col[0] // 2, ring_col[1] // 2, ring_col[2] // 2), 1, cv2.LINE_AA)

        # Rounded zone fill
        overlay = frame.copy()
        fill_a = 0.22 + smooth * 0.35
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 200, 120), -1)
        cv2.addWeighted(overlay, fill_a, frame, 1.0 - fill_a, 0, frame)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 230, 140), 2, cv2.LINE_AA)

        # Smooth bottom progress pill
        pill_w = w - 12
        pill_h = 10
        px, py = x + 6, y + h - 14
        cv2.rectangle(frame, (px, py), (px + pill_w, py + pill_h), (30, 40, 48), -1, cv2.LINE_AA)
        if smooth > 0:
            fill_w = max(4, int(pill_w * ease_out_cubic(smooth)))
            cv2.rectangle(frame, (px, py), (px + fill_w, py + pill_h), (0, 230, 130), -1, cv2.LINE_AA)

        label = f"CUT {wire_color}"
        cv2.putText(frame, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 240, 160), 1, cv2.LINE_AA)

    def draw_coach_panel(self, frame, msg: CoachMessage) -> None:
        self._last_message = msg
        h, w = frame.shape[:2]
        pw, ph = 520, 96
        px = (w - pw) // 2
        py = h - 168

        tones = {
            "guide": ((22, 28, 38), (0, 190, 255), (200, 210, 220)),
            "good": ((18, 36, 30), (0, 220, 140), (210, 230, 215)),
            "warn": ((38, 28, 18), (0, 160, 255), (230, 210, 190)),
            "success": ((18, 38, 28), (0, 240, 150), (210, 255, 220)),
        }
        bg, accent, fg = tones.get(msg.tone, tones["guide"])

        overlay = frame.copy()
        cv2.rectangle(overlay, (px, py), (px + pw, py + ph), bg, -1)
        cv2.addWeighted(overlay, 0.92, frame, 0.08, 0, frame)
        cv2.rectangle(frame, (px, py), (px + pw, py + ph), accent, 2, cv2.LINE_AA)
        cv2.rectangle(frame, (px + 2, py + 2), (px + pw - 2, py + ph - 2), accent, 1, cv2.LINE_AA)

        cv2.putText(frame, msg.step_label, (px + 14, py + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, accent, 1, cv2.LINE_AA)
        cv2.putText(frame, msg.primary, (px + 14, py + 50), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, msg.secondary[:64], (px + 14, py + 78), cv2.FONT_HERSHEY_SIMPLEX, 0.4, fg, 1, cv2.LINE_AA)

    def draw_success_flash(self, frame) -> None:
        if not self.in_success_pause:
            return
        remaining = self._success_until - time.time()
        alpha = ease_in_out_cubic(min(1.0, remaining / 1.15))
        h, w = frame.shape[:2]
        cx, cy = w // 2, h // 2 - 40
        r = int(40 + 20 * (1.0 - alpha))
        cv2.circle(frame, (cx, cy), r, (0, 220, 130), 3, cv2.LINE_AA)
        cv2.putText(
            frame, f"{self._success_label} CUT OK",
            (cx - 90, cy + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 240, 150), 2, cv2.LINE_AA,
        )

    @property
    def hint_text(self) -> str:
        return self._last_message.primary
