"""Cinematic dialogue boxes with typewriter text and speaker portraits."""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from eod_training.animation import ease_out_cubic, lerp


class DialogueLine:
    def __init__(
        self,
        speaker: str,
        text: str,
        style: str = "distress",
        operator_reply: str = "",
    ) -> None:
        self.speaker = speaker
        self.text = text
        self.style = style
        self.operator_reply = operator_reply


class DialogueSystem:
    SPEAKER_COLORS = {
        "victim": (0, 140, 255),
        "operator": (0, 220, 140),
        "system": (0, 200, 255),
        "command": (200, 180, 80),
    }

    def __init__(self) -> None:
        self.queue: List[DialogueLine] = []
        self._idx = 0
        self._char_count = 0.0
        self._last_tick = time.perf_counter()
        self._slide = 0.0
        self._reply_shown = False
        self._reply_alpha = 0.0
        self._complete = False
        self.active = False

    def load(self, lines: List[Dict]) -> None:
        self.queue = [
            DialogueLine(
                ln.get("speaker", "Unknown"),
                ln.get("text", ""),
                ln.get("style", "distress"),
                ln.get("operator_reply", ""),
            )
            for ln in lines
        ]
        self._idx = 0
        self._char_count = 0.0
        self._slide = 0.0
        self._reply_shown = False
        self._reply_alpha = 0.0
        self._complete = False
        self.active = bool(self.queue)

    def load_chapter_intro(self, mission: Dict) -> None:
        story = mission.get("story", {})
        victim = story.get("victim", "Unknown")
        distress = story.get("distress_call", story.get("briefing", ""))
        reply = story.get("operator_reply", "Copy that. EOD en route. Hold position.")
        lines = [
            {"speaker": victim, "text": distress, "style": "distress", "operator_reply": reply},
        ]
        for extra in mission.get("dialogue", []):
            lines.append(extra)
        self.load(lines)

    @property
    def current(self) -> Optional[DialogueLine]:
        if self._idx < len(self.queue):
            return self.queue[self._idx]
        return None

    def update(self, dt: float | None = None) -> None:
        if not self.active or self._complete:
            return
        now = time.perf_counter()
        if dt is None:
            dt = now - self._last_tick
        self._last_tick = now

        self._slide = min(1.0, self._slide + dt * 3.5)
        line = self.current
        if line is None:
            self._complete = True
            return

        chars_per_sec = 42.0
        self._char_count = min(len(line.text), self._char_count + chars_per_sec * dt)

        if self._char_count >= len(line.text):
            self._reply_alpha = min(1.0, self._reply_alpha + dt * 2.0)

    def advance(self) -> bool:
        """Advance to next line. Returns True if dialogue finished."""
        line = self.current
        if line is None:
            self._complete = True
            return True
        if self._char_count < len(line.text):
            self._char_count = len(line.text)
            return False
        self._idx += 1
        self._char_count = 0.0
        self._reply_alpha = 0.0
        if self._idx >= len(self.queue):
            self._complete = True
            return True
        return False

    def skip_to_end(self) -> None:
        self._complete = True
        self.active = False

    @property
    def finished(self) -> bool:
        return self._complete or not self.active

    def draw(self, frame, y_offset: int = 0) -> None:
        line = self.current
        if not self.active or line is None:
            return

        h, w = frame.shape[:2]
        slide_t = ease_out_cubic(self._slide)
        box_h = 118
        y1 = int(lerp(h, h - box_h - 24 + y_offset, slide_t))
        y2 = y1 + box_h
        x1, x2 = 28, w - 28

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (8, 12, 22), -1)
        cv2.addWeighted(overlay, 0.92, frame, 0.08, 0, frame)

        border_col = self.SPEAKER_COLORS.get(line.style, (0, 180, 255))
        cv2.rectangle(frame, (x1, y1), (x2, y2), border_col, 2, cv2.LINE_AA)
        cv2.line(frame, (x1 + 12, y1 + 4), (x2 - 12, y1 + 4), border_col, 1, cv2.LINE_AA)

        # Speaker badge
        badge_w = min(220, len(line.speaker) * 11 + 24)
        cv2.rectangle(frame, (x1 + 14, y1 + 12), (x1 + 14 + badge_w, y1 + 34), border_col, -1)
        cv2.putText(
            frame, line.speaker.upper(), (x1 + 22, y1 + 28),
            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (10, 12, 18), 1, cv2.LINE_AA,
        )

        visible = line.text[: int(self._char_count)]
        self._wrap_text(frame, visible, x1 + 18, y1 + 56, x2 - x1 - 36, 0.44, (210, 215, 225))

        if line.operator_reply and self._reply_alpha > 0.05:
            ry = y2 + 8
            if ry + 52 < h - 10:
                alpha = self._reply_alpha
                ovl = frame.copy()
                cv2.rectangle(ovl, (x1 + 40, ry), (x2, ry + 48), (12, 28, 22), -1)
                cv2.addWeighted(ovl, 0.85 * alpha, frame, 1 - 0.85 * alpha, 0, frame)
                cv2.rectangle(frame, (x1 + 40, ry), (x2, ry + 48), (0, 180, 120), 1, cv2.LINE_AA)
                cv2.putText(
                    frame, "OPERATOR", (x1 + 52, ry + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.34, (0, 200, 130), 1, cv2.LINE_AA,
                )
                self._wrap_text(
                    frame, line.operator_reply, x1 + 52, ry + 36, x2 - x1 - 60,
                    0.38, (160, 230, 190),
                )

    @staticmethod
    def _wrap_text(frame, text: str, x: int, y: int, max_w: int, scale: float, color: Tuple[int, int, int]) -> None:
        words = text.split()
        line, ly = "", y
        for word in words:
            test = f"{line} {word}".strip()
            tw = cv2.getTextSize(test, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0]
            if tw > max_w and line:
                cv2.putText(frame, line, (x, ly), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
                line = word
                ly += int(22 * scale / 0.4)
            else:
                line = test
        if line:
            cv2.putText(frame, line, (x, ly), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)

    def draw_shout_burst(self, frame, cx: int, cy: int, intensity: float = 1.0) -> None:
        """Animated distress burst behind dialogue."""
        t = time.perf_counter()
        for i in range(3):
            r = int(30 + 20 * i + 8 * math.sin(t * 4 + i))
            alpha = 0.06 * intensity / (i + 1)
            overlay = frame.copy()
            cv2.circle(overlay, (cx, cy), r, (0, 80, 200), 2, cv2.LINE_AA)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

