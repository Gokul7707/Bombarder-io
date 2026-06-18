"""Pre-mission operator scan: hand range, gaze targets, thumbs-up confirm."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from eod_training.animation import ease_in_out_cubic, ease_out_cubic, lerp, pulse


PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "calibration_profile.json"


@dataclass
class CalibrationProfile:
    left_scale: float = 1.0
    right_scale: float = 1.0
    left_offset: Tuple[float, float] = (0.0, 0.0)
    right_offset: Tuple[float, float] = (0.0, 0.0)
    tremor_baseline: float = 0.0
    completed: bool = False

    def save(self) -> None:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(
            json.dumps(
                {
                    "left_scale": self.left_scale,
                    "right_scale": self.right_scale,
                    "left_offset": list(self.left_offset),
                    "right_offset": list(self.right_offset),
                    "tremor_baseline": self.tremor_baseline,
                    "completed": self.completed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> "CalibrationProfile":
        if not PROFILE_PATH.exists():
            return cls()
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            return cls(
                left_scale=data.get("left_scale", 1.0),
                right_scale=data.get("right_scale", 1.0),
                left_offset=tuple(data.get("left_offset", [0, 0])),
                right_offset=tuple(data.get("right_offset", [0, 0])),
                tremor_baseline=data.get("tremor_baseline", 0.0),
                completed=data.get("completed", False),
            )
        except (json.JSONDecodeError, OSError):
            return cls()


@dataclass
class CalStep:
    id: str
    title: str
    instruction: str
    duration: float = 0.0
    require_both_hands: bool = False
    require_gesture: str = ""
    gaze_target: Optional[Tuple[float, float]] = None
    hold_seconds: float = 0.0


class CalibrationFlow:
  STEPS = [
      CalStep("boot", "OPERATOR SCAN", "Initializing biometric link...", 1.8),
      CalStep("hands_show", "HAND DETECTION", "Raise BOTH hands into the scan zone", 0, require_both_hands=True),
      CalStep("palm_front", "PALM ORIENTATION", "Turn palms toward camera — OPEN HAND", 0, require_gesture="open_hand"),
      CalStep("sweep_lr", "RANGE OF MOTION", "Sweep both hands LEFT, then RIGHT", 2.5),
      CalStep("gaze_center", "OPTIC LOCK", "Point index finger at the CENTER reticle", 0, gaze_target=(0.5, 0.42)),
      CalStep("gaze_left", "OPTIC LOCK", "Point at LEFT reticle — turn your focus", 0, gaze_target=(0.22, 0.42)),
      CalStep("gaze_right", "OPTIC LOCK", "Point at RIGHT reticle", 0, gaze_target=(0.78, 0.42)),
      CalStep("confirm_ready", "CONFIRM READY", "Place fingertip target on READY — hold to confirm", 0, gaze_target=(0.5, 0.88), hold_seconds=0.75),
      CalStep("complete", "CONTROL IS YOURS", "Neural link established. Stand by.", 2.0),
  ]

  def __init__(self, width: int, height: int) -> None:
      self.width = width
      self.height = height
      self.profile = CalibrationProfile.load()
      self.step_idx = 0
      self._step_start = time.perf_counter()
      self._scan_line = 0.0
      self._sweep_progress = 0.0
      self._sweep_phase = 0
      self._gaze_hits: List[bool] = []
      self._hand_samples: List[Tuple[float, float]] = []
      self._hold_timer = 0.0
      self._complete_anim = 0.0
      self.finished = self.profile.completed
      self._active = not self.profile.completed

  @property
  def active(self) -> bool:
      return self._active and not self.finished

  @property
  def current(self) -> CalStep:
      return self.STEPS[min(self.step_idx, len(self.STEPS) - 1)]

  def skip_if_cached(self) -> bool:
      if self.profile.completed:
          self.finished = True
          self._active = False
          return True
      return False

  def update(self, hand_data: Dict, dt: float = 1 / 30) -> None:
      if not self.active:
          return
      step = self.current
      elapsed = time.perf_counter() - self._step_start
      self._scan_line = (self._scan_line + dt * 0.35) % 1.0

      if step.id == "boot":
          if elapsed >= step.duration:
              self._advance()
          return

      if step.id == "hands_show":
          if hand_data.get("left_hand") and hand_data.get("right_hand"):
              for side in ("left", "right"):
                  h = hand_data[f"{side}_hand"]
                  self._hand_samples.append(h["center"])
              self._advance()
          return

      if step.id == "palm_front":
          if hand_data.get("open_palm"):
              self._advance()
          return

      if step.id == "sweep_lr":
          self._sweep_progress += dt
          if self._sweep_progress > 1.2:
              self._sweep_phase += 1
              self._sweep_progress = 0.0
          if self._sweep_phase >= 2:
              self._compute_profile_offsets(hand_data)
              self._advance()
          return

      if step.gaze_target:
          tip = self._index_tip(hand_data)
          if step.hold_seconds > 0:
              if tip and self._hit_gaze(tip, step.gaze_target):
                  self._hold_timer += dt
                  if self._hold_timer >= step.hold_seconds:
                      if step.id == "confirm_ready":
                          self.profile.completed = True
                          self.profile.save()
                      self._advance()
              else:
                  self._hold_timer = max(0.0, self._hold_timer - dt * 2)
              return
          if tip and self._hit_gaze(tip, step.gaze_target):
              self._gaze_hits.append(True)
              self._advance()
          return

      if step.id == "complete":
          self._complete_anim = min(1.0, self._complete_anim + dt * 0.8)
          if elapsed >= step.duration:
              self.finished = True
              self._active = False

  def _advance(self) -> None:
      self.step_idx += 1
      self._step_start = time.perf_counter()
      self._sweep_progress = 0.0
      self._sweep_phase = 0
      self._hold_timer = 0.0

  def _index_tip(self, hand_data: Dict) -> Optional[Tuple[int, int]]:
      for key in ("right_hand", "left_hand"):
          h = hand_data.get(key)
          if h:
              tip = h.get("screen_tip") or h.get("index_tip")
              if tip:
                  return tip
      return hand_data.get("primary_center")

  def _has_gesture(self, hand_data: Dict, gesture: str) -> bool:
      for key in ("left_hand", "right_hand"):
          h = hand_data.get(key)
          if h and gesture in h.get("gestures", []):
              return True
      return False

  def _hit_gaze(self, tip: Tuple[int, int], norm_target: Tuple[float, float]) -> bool:
      tx = int(norm_target[0] * self.width)
      ty = int(norm_target[1] * self.height)
      return math.hypot(tip[0] - tx, tip[1] - ty) < 55

  def _compute_profile_offsets(self, hand_data: Dict) -> None:
      for side in ("left", "right"):
          h = hand_data.get(f"{side}_hand")
          if not h:
              continue
          lm = h["landmarks"]
          span = math.hypot(lm[5][0] - lm[17][0], lm[5][1] - lm[17][1])
          scale = max(0.85, min(1.25, span / 120.0))
          if side == "left":
              self.profile.left_scale = scale
          else:
              self.profile.right_scale = scale
      self.profile.save()

  def draw(self, frame, hand_data: Dict) -> None:
      if not self.active:
          return
      step = self.current
      h, w = frame.shape[:2]

      # Scan vignette + grid
      overlay = frame.copy()
      cv2.rectangle(overlay, (0, 0), (w, h), (4, 8, 18), -1)
      cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
      self._draw_scan_grid(frame)
      self._draw_scan_line(frame)

      # HUD frame
      cv2.rectangle(frame, (18, 18), (w - 18, h - 18), (0, 160, 255), 1, cv2.LINE_AA)
      cv2.putText(
          frame, "BIOMETRIC CALIBRATION", (32, 48),
          cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 210, 255), 2, cv2.LINE_AA,
      )

      # Step progress
      for i, s in enumerate(self.STEPS):
          col = (0, 200, 120) if i < self.step_idx else ((0, 160, 220) if i == self.step_idx else (50, 55, 65))
          cv2.circle(frame, (36, 72 + i * 14), 4, col, -1, cv2.LINE_AA)

      # Title + instruction
      cv2.putText(frame, step.title, (w // 2 - 180, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 230, 255), 2, cv2.LINE_AA)
      cv2.putText(
          frame, step.instruction, (w // 2 - 280, 140),
          cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 190, 200), 1, cv2.LINE_AA,
      )

      if step.gaze_target:
          self._draw_reticle(frame, step.gaze_target)

      if step.id == "sweep_lr":
          labels = ["← SWEEP LEFT", "SWEEP RIGHT →"]
          label = labels[min(self._sweep_phase, 1)]
          cv2.putText(frame, label, (w // 2 - 100, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1, cv2.LINE_AA)

      if step.id == "complete":
          alpha = ease_out_cubic(self._complete_anim)
          msg = "CONTROL IS YOURS"
          cv2.putText(
              frame, msg, (w // 2 - 160, h // 2 + 20),
              cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, int(220 * alpha), int(140 * alpha)), 2, cv2.LINE_AA,
          )

      if step.hold_seconds > 0 and step.gaze_target:
          prog = min(1.0, self._hold_timer / step.hold_seconds)
          tx = int(step.gaze_target[0] * self.width)
          ty = int(step.gaze_target[1] * self.height)
          bw, bh = 240, 44
          bx, by = tx - bw // 2, ty - bh // 2
          cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (36, 42, 54), -1)
          cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 200, 255), 2, cv2.LINE_AA)
          cv2.putText(frame, "READY", (bx + 78, by + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
          if prog > 0:
              cv2.rectangle(frame, (bx + 4, by + bh - 10), (bx + 4 + int((bw - 8) * prog), by + bh - 4), (0, 220, 140), -1)

      count = int(bool(hand_data.get("left_hand"))) + int(bool(hand_data.get("right_hand")))
      cv2.putText(frame, f"HANDS: {count}/2", (w - 140, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 180, 255), 1, cv2.LINE_AA)

  def _draw_scan_grid(self, frame) -> None:
      h, w = frame.shape[:2]
      for i in range(0, w, 40):
          cv2.line(frame, (i, 0), (i, h), (20, 40, 60), 1, cv2.LINE_AA)
      for j in range(0, h, 40):
          cv2.line(frame, (0, j), (w, j), (20, 40, 60), 1, cv2.LINE_AA)

  def _draw_scan_line(self, frame) -> None:
      h, w = frame.shape[:2]
      y = int(self._scan_line * h)
      overlay = frame.copy()
      cv2.line(overlay, (0, y), (w, y), (0, 255, 200), 2, cv2.LINE_AA)
      cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

  def _draw_reticle(self, frame, norm: Tuple[float, float]) -> None:
      cx = int(norm[0] * self.width)
      cy = int(norm[1] * self.height)
      t = time.perf_counter()
      r = int(28 + 6 * math.sin(t * 5))
      col = (0, 220, 255)
      cv2.circle(frame, (cx, cy), r, col, 2, cv2.LINE_AA)
      cv2.line(frame, (cx - r - 10, cy), (cx - 8, cy), col, 2, cv2.LINE_AA)
      cv2.line(frame, (cx + 8, cy), (cx + r + 10, cy), col, 2, cv2.LINE_AA)
      cv2.line(frame, (cx, cy - r - 10), (cx, cy - 8), col, 2, cv2.LINE_AA)
      cv2.line(frame, (cx, cy + 8), (cx, cy + r + 10), col, 2, cv2.LINE_AA)
      cv2.putText(frame, "FOCUS", (cx - 28, cy + r + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
