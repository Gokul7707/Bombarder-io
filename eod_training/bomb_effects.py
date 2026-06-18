"""Bomb visual effects — sparks, explosions, wire sway, cut gaps."""

from __future__ import annotations

import math
import random
import time
from typing import List, Tuple

import cv2

from eod_training.animation import ease_out_cubic
from eod_training.wire_physics import WireState


class BombEffects:
    def __init__(self) -> None:
        self.particles: List[dict] = []
        self._t0 = time.time()

    def reset(self) -> None:
        self.particles.clear()

    def spawn_sparks(self, x: int, y: int, count: int = 18) -> None:
        for _ in range(count):
            self.particles.append(
                {
                    "x": float(x),
                    "y": float(y),
                    "vx": random.uniform(-4, 4),
                    "vy": random.uniform(-5, 2),
                    "life": 1.0,
                    "color": random.choice([(0, 255, 255), (0, 200, 255), (0, 255, 200), (255, 255, 255)]),
                    "size": random.randint(2, 4),
                }
            )

    def spawn_explosion(self, cx: int, cy: int, count: int = 80) -> None:
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2, 12)
            self.particles.append(
                {
                    "x": float(cx),
                    "y": float(cy),
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed,
                    "life": random.uniform(0.6, 1.2),
                    "color": random.choice([(0, 80, 255), (0, 120, 255), (0, 0, 255), (0, 200, 255)]),
                    "size": random.randint(3, 8),
                }
            )

    def update(self) -> None:
        alive = []
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.25
            p["life"] -= 0.04
            p["vx"] *= 0.97
            if p["life"] > 0:
                alive.append(p)
        self.particles = alive

    def draw(self, frame) -> None:
        for p in self.particles:
            alpha = max(0, p["life"])
            col = tuple(int(c * alpha) for c in p["color"])
            cv2.circle(frame, (int(p["x"]), int(p["y"])), p["size"], col, -1, cv2.LINE_AA)

    def sway_offset(self, wire: WireState) -> Tuple[int, int]:
        t = time.time() - self._t0
        amp = int(wire.tension * 6 + 1)
        return int(math.sin(t * 8 + hash(wire.color) % 10) * amp), int(math.cos(t * 6) * amp * 0.5)

    def draw_wire_with_effects(
        self,
        frame,
        wire: WireState,
        color: Tuple[int, int, int],
        thickness: int,
        highlight: bool,
        show_cut_zone: bool,
    ) -> None:
        ox, oy = self.sway_offset(wire)
        pts = [(p[0] + ox, p[1] + oy) for p in wire.control_points]
        mid = len(pts) // 2
        mid_pt = pts[mid]

        if highlight:
            glow = frame.copy()
            self._draw_curve(glow, pts, color, thickness + 6)
            cv2.addWeighted(glow, 0.35, frame, 0.65, 0, frame)
            self._draw_curve(frame, pts, color, thickness + 2)

        if not wire.is_cut:
            self._draw_curve(frame, pts, color, thickness)

            # Active cut laser while holding
            if wire.snip_progress > 0.02 and highlight:
                self._draw_snip_laser(frame, mid_pt, wire.snip_progress)

            cz = wire.cut_zone
            cz_draw = (cz[0] + ox, cz[1] + oy, cz[2], cz[3])
            if show_cut_zone or highlight:
                border = (0, 255, 200) if wire.snip_progress > 0.1 else ((0, 255, 255) if wire.tension < 0.5 else (0, 120, 255))
                cv2.rectangle(frame, (cz_draw[0], cz_draw[1]), (cz_draw[0] + cz_draw[2], cz_draw[1] + cz_draw[3]), border, 1, cv2.LINE_AA)
        else:
            gap_max = 16
            gap = int(gap_max * ease_out_cubic(wire.cut_anim))
            first, second = pts[: mid + 1], pts[mid:]
            stub_col = tuple(int(c * 0.55) for c in color)
            if first:
                end = first[-1]
                first_end = (end[0] - gap, end[1])
                self._draw_curve(frame, first[:-1] + [first_end], stub_col, max(2, thickness - 1))
            if second:
                start = second[0]
                second_start = (start[0] + gap, start[1])
                self._draw_curve(frame, [second_start] + second[1:], stub_col, max(2, thickness - 1))
            cut_x, cut_y = mid_pt[0], mid_pt[1]
            spark_a = ease_out_cubic(wire.cut_anim)
            if spark_a > 0.1:
                cv2.line(frame, (cut_x - gap, cut_y - 3), (cut_x + gap, cut_y + 3), (220, 240, 255), 2, cv2.LINE_AA)
                cv2.circle(frame, (cut_x, cut_y), int(6 + 8 * spark_a), (0, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(frame, wire.color[:6], (mid_pt[0] - 18, mid_pt[1] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)

    def _draw_snip_laser(self, frame, mid_pt: Tuple[int, int], progress: float) -> None:
        t = ease_out_cubic(progress)
        half = int(6 + 22 * t)
        y = mid_pt[1]
        x1, x2 = mid_pt[0] - half, mid_pt[0] + half
        overlay = frame.copy()
        cv2.line(overlay, (x1, y), (x2, y), (0, 255, 255), 4, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.45 + 0.35 * t, frame, 1.0 - (0.45 + 0.35 * t), 0, frame)
        if t > 0.35 and int(t * 12) % 4 == 0:
            self.spawn_sparks(mid_pt[0], mid_pt[1], count=2)

    @staticmethod
    def _draw_curve(frame, points, color, thickness) -> None:
        for i in range(len(points) - 1):
            cv2.line(frame, points[i], points[i + 1], color, thickness, cv2.LINE_AA)
