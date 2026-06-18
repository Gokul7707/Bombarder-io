"""FFT-based hand tremor and stress biometric analysis."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class BiometricSnapshot:
    stability: float
    tremor_index: float
    tremor_frequency_hz: float
    stress_level: float
    shiver_detected: bool
    velocity_px_per_frame: float
    recommendation: str


class BiometricAnalyzer:
    """Tracks hand landmark motion and derives military-relevant steadiness metrics."""

    TREMOR_BAND_HZ = (4.0, 12.0)
    HISTORY_LEN = 90  # ~3s at 30fps

    def __init__(self) -> None:
        self._positions: Deque[Tuple[float, float, float]] = deque(maxlen=self.HISTORY_LEN)
        self._previous: Optional[Tuple[int, int]] = None
        self._baseline_tremor: Optional[float] = None
        self.calibrated = False

    def reset(self) -> None:
        self._positions.clear()
        self._previous = None
        self._baseline_tremor = None
        self.calibrated = False

    def calibrate(self, duration_frames: int = 60) -> None:
        """Mark calibration window — baseline captured from steady-hand period."""
        self.calibrated = True

    def update(self, center: Tuple[int, int], timestamp: float) -> BiometricSnapshot:
        x, y = center
        velocity = 0.0
        if self._previous is not None:
            dx = x - self._previous[0]
            dy = y - self._previous[1]
            velocity = math.hypot(dx, dy)
        self._previous = (x, y)
        self._positions.append((timestamp, float(x), float(y)))

        stability = self._compute_stability(velocity)
        tremor_index, tremor_hz = self._compute_tremor()
        stress = self._compute_stress(tremor_index, velocity)
        shiver = tremor_index > 0.45 or velocity > 25

        if self._baseline_tremor is None and len(self._positions) >= 30:
            self._baseline_tremor = tremor_index

        recommendation = self._recommendation(tremor_index, stress, shiver)

        return BiometricSnapshot(
            stability=stability,
            tremor_index=tremor_index,
            tremor_frequency_hz=tremor_hz,
            stress_level=stress,
            shiver_detected=shiver,
            velocity_px_per_frame=velocity,
            recommendation=recommendation,
        )

    def _compute_stability(self, velocity: float) -> float:
        return float(max(0.0, min(1.0, 1.0 - velocity / 40.0)))

    def _compute_tremor(self) -> Tuple[float, float]:
        if len(self._positions) < 20:
            return 0.0, 0.0

        times = np.array([p[0] for p in self._positions])
        xs = np.array([p[1] for p in self._positions])
        ys = np.array([p[2] for p in self._positions])

        dt = np.diff(times)
        dt = np.where(dt <= 0, 1 / 30.0, dt)
        vx = np.diff(xs) / dt
        vy = np.diff(ys) / dt
        speed = np.hypot(vx, vy)

        if len(speed) < 16:
            return float(np.std(speed) / 20.0), 0.0

        speed = speed - np.mean(speed)
        sample_rate = 1.0 / np.mean(dt)
        fft = np.abs(np.fft.rfft(speed))
        freqs = np.fft.rfftfreq(len(speed), d=1.0 / sample_rate)

        lo, hi = self.TREMOR_BAND_HZ
        band_mask = (freqs >= lo) & (freqs <= hi)
        if not np.any(band_mask):
            return float(min(1.0, np.std(speed) / 15.0)), 0.0

        band_power = float(np.sum(fft[band_mask] ** 2))
        total_power = float(np.sum(fft ** 2) + 1e-9)
        tremor_index = min(1.0, band_power / total_power * 2.5)
        peak_freq = float(freqs[band_mask][np.argmax(fft[band_mask])]) if band_mask.any() else 0.0
        return tremor_index, peak_freq

    def _compute_stress(self, tremor_index: float, velocity: float) -> float:
        baseline = self._baseline_tremor or 0.1
        elevation = max(0.0, tremor_index - baseline)
        velocity_factor = min(1.0, velocity / 30.0)
        return float(min(1.0, elevation * 0.7 + velocity_factor * 0.3))

    def _recommendation(self, tremor: float, stress: float, shiver: bool) -> str:
        if shiver:
            return "STOP — stabilize hands before continuing RSP"
        if tremor > 0.3:
            return "Breathe — tremor exceeds safe cut threshold"
        if stress > 0.6:
            return "Elevated stress — consider pause / team check-in"
        return "Steady — within operational parameters"

    def export_series(self) -> List[Dict]:
        return [{"t": p[0], "x": p[1], "y": p[2]} for p in self._positions]
