"""Easing, interpolation, and timed transitions for smooth UI motion."""

from __future__ import annotations

import math
import time
from typing import Tuple


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t)


def lerp_pt(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return lerp(a[0], b[0], t), lerp(a[1], b[1], t)


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4.0 * t * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def ease_out_elastic(t: float) -> float:
    t = clamp(t)
    if t == 0 or t == 1:
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def pulse(t: float, speed: float = 2.0) -> float:
    return 0.5 + 0.5 * math.sin(time.perf_counter() * speed)


class TimedValue:
    """Animates a float toward a target over duration with easing."""

    def __init__(self, initial: float = 0.0, duration: float = 0.35) -> None:
        self.value = initial
        self._from = initial
        self._to = initial
        self._start = time.perf_counter()
        self.duration = duration

    def set_target(self, target: float, duration: float | None = None) -> None:
        self._from = self.value
        self._to = target
        self._start = time.perf_counter()
        if duration is not None:
            self.duration = duration

    def update(self) -> float:
        elapsed = time.perf_counter() - self._start
        t = ease_out_cubic(elapsed / max(self.duration, 1e-4))
        self.value = lerp(self._from, self._to, t)
        return self.value


class FadeTransition:
    def __init__(self, duration: float = 0.5) -> None:
        self.duration = duration
        self._start: float | None = None
        self._active = False

    def begin(self) -> None:
        self._start = time.perf_counter()
        self._active = True

    def alpha(self) -> float:
        if not self._active or self._start is None:
            return 1.0
        t = (time.perf_counter() - self._start) / self.duration
        if t >= 1.0:
            self._active = False
            return 1.0
        return ease_in_out_cubic(t)

    @property
    def running(self) -> bool:
        return self._active
