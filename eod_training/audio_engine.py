"""Procedural audio — heartbeat, tension, ambient (optional pygame)."""

from __future__ import annotations

import math
import threading
import time
from typing import Optional


class AudioEngine:
    """Cross-platform audio cues. Uses pygame if available, else console beeps."""

    def __init__(self) -> None:
        self.enabled = False
        self._pygame = None
        self._last_heartbeat = 0.0
        self._tension_thread: Optional[threading.Thread] = None
        self._stop_tension = False

        try:
            import pygame

            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self._pygame = pygame
            self.enabled = True
        except Exception:
            self.enabled = False

    def play_tone(self, frequency: int, duration_ms: int = 100, volume: float = 0.3) -> None:
        if not self.enabled or self._pygame is None:
            return
        try:
            import numpy as np

            sample_rate = 22050
            n = int(sample_rate * duration_ms / 1000)
            t = np.linspace(0, duration_ms / 1000, n, False)
            wave = (32767 * volume * np.sin(2 * np.pi * frequency * t)).astype(np.int16)
            sound = self._pygame.sndarray.make_sound(wave)
            sound.play()
        except Exception:
            pass

    def wire_cut_spark(self) -> None:
        self.play_tone(880, 80, 0.4)
        self.play_tone(1200, 60, 0.2)

    def detonation(self) -> None:
        for freq in (60, 40, 30):
            self.play_tone(freq, 400, 0.6)

    def success_chime(self) -> None:
        for freq in (523, 659, 784):
            self.play_tone(freq, 120, 0.25)
            time.sleep(0.05)

    def update_heartbeat(self, stress_level: float, tension: float) -> None:
        now = time.time()
        interval = max(0.35, 1.2 - stress_level * 0.8 - tension * 0.4)
        if now - self._last_heartbeat >= interval:
            self.play_tone(50, 40, 0.15 + stress_level * 0.2)
            self._last_heartbeat = now

    def tension_alarm(self, tension: float) -> None:
        if tension > 0.75:
            self.play_tone(440, 50, min(0.5, tension))

    def protocol_ack(self) -> None:
        self.play_tone(600, 60, 0.2)

    def shutdown(self) -> None:
        self._stop_tension = True
        if self._pygame:
            self._pygame.mixer.quit()
