"""Wire tension physics and precision cut validation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class WireState:
    color: str
    start: Tuple[int, int]
    end: Tuple[int, int]
    control_points: List[Tuple[int, int]]
    cut_zone: Tuple[int, int, int, int]
    is_cut: bool = False
    tension: float = 0.0
    thickness: int = 5
    glow_intensity: int = 0
    circuit_role: str = "firing_circuit"
    snip_progress: float = 0.0
    cut_anim: float = 0.0
    connector_start: Dict = field(default_factory=dict)
    connector_end: Dict = field(default_factory=dict)


class WirePhysicsEngine:
    """Simulates wire sag, tension buildup from hand jitter, and cut precision."""

    WIRE_COLORS = {
        "RED": (0, 0, 255),
        "BLUE": (255, 0, 0),
        "GREEN": (0, 255, 0),
        "YELLOW": (0, 255, 255),
        "WHITE": (255, 255, 255),
        "BLACK": (50, 50, 50),
        "ORANGE": (0, 140, 255),
    }

    def __init__(self, frame_width: int, frame_height: int) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.wires: List[WireState] = []
        self.gravity_sag = 0.15
        self.nearby_hand_distance = 100

    def generate_wires(
        self,
        board_rect: Dict,
        colors: List[str],
        seed: Optional[int] = None,
    ) -> List[WireState]:
        if seed is not None:
            random.seed(seed)
        self.wires = []

        left_x = board_rect["x"]
        right_x = board_rect["x"] + board_rect["width"]
        top_y = board_rect["y"] + 50
        bottom_y = board_rect["y"] + board_rect["height"] - 50
        count = len(colors)

        for i, color in enumerate(colors):
            if count > 1:
                y = int(top_y + i * (bottom_y - top_y) / (count - 1))
            else:
                y = (top_y + bottom_y) // 2

            start = (left_x - 10, y)
            end = (right_x + 10, y + random.randint(-15, 15))
            controls = self._bezier_path(start, end)
            mid = controls[len(controls) // 2]
            cut_zone = (mid[0] - 36, mid[1] - 22, 72, 44)

            wire = WireState(
                color=color,
                start=start,
                end=end,
                control_points=controls,
                cut_zone=cut_zone,
                thickness=random.randint(4, 7),
                circuit_role=random.choice(["firing_circuit", "safe_line", "decoy", "power"]),
                connector_start=self._connector(start),
                connector_end=self._connector(end),
            )
            self.wires.append(wire)
        return self.wires

    def update_tension(
        self,
        hand_center: Optional[Tuple[int, int]],
        tremor_index: float,
        dt: float = 1 / 30,
    ) -> float:
        """Increase wire tension when unstable hand is near cut zones."""
        max_tension = 0.0
        for wire in self.wires:
            if wire.is_cut:
                wire.tension = max(0.0, wire.tension - dt * 0.5)
                continue

            decay = 0.08
            wire.tension = max(0.0, wire.tension - decay * dt * 30)

            if hand_center is None:
                continue

            dist = self._distance_to_wire(hand_center, wire)
            if dist < self.nearby_hand_distance:
                proximity = 1.0 - dist / self.nearby_hand_distance
                wire.tension = min(
                    1.0,
                    wire.tension + proximity * tremor_index * 0.12 + tremor_index * 0.04,
                )
            max_tension = max(max_tension, wire.tension)
        return max_tension

    def can_cut(
        self,
        wire_index: int,
        hand_center: Tuple[int, int],
        tremor_index: float,
        tension_limit: float,
        hold_steady_frames: int,
        steady_counter: int,
    ) -> Tuple[bool, str]:
        if wire_index >= len(self.wires):
            return False, "Invalid wire"

        wire = self.wires[wire_index]
        if wire.is_cut:
            return False, "Already cut"

        if not self._point_in_rect(hand_center, wire.cut_zone):
            dist = self._distance_to_wire(hand_center, wire)
            if dist > 55:
                return False, "Place target on highlighted cut zone"

        if wire.tension > tension_limit:
            return False, f"Tension critical ({wire.tension:.0%}) — hold steady"

        if tremor_index > tension_limit + 0.1:
            return False, "Tremor too high — breathe and stabilize"

        if steady_counter < max(3, hold_steady_frames // 3):
            return False, f"Stabilizing ({steady_counter}/{max(3, hold_steady_frames // 3)})"

        return True, "Cut authorized"

    def apply_cut(self, wire_index: int) -> WireState:
        wire = self.wires[wire_index]
        wire.is_cut = True
        wire.tension = 0.0
        wire.snip_progress = 1.0
        wire.cut_anim = 0.0
        return wire

    def _bezier_path(
        self, start: Tuple[int, int], end: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
        mid_x = (start[0] + end[0]) // 2
        mid_y = (start[1] + end[1]) // 2
        sag = random.randint(-25, 25)
        curve = random.randint(-40, 40)
        return [
            start,
            (start[0] + 70, start[1] + sag),
            (mid_x + curve, mid_y + sag),
            (end[0] - 70, end[1] + sag),
            end,
        ]

    @staticmethod
    def _connector(position: Tuple[int, int]) -> Dict:
        return {
            "position": position,
            "width": 12,
            "height": 8,
            "color": (150, 150, 150),
            "border_color": (100, 100, 100),
        }

    @staticmethod
    def _point_in_rect(point: Tuple[int, int], rect: Tuple[int, int, int, int]) -> bool:
        x, y = point
        rx, ry, rw, rh = rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def _distance_to_wire(self, point: Tuple[int, int], wire: WireState) -> float:
        mid = wire.control_points[len(wire.control_points) // 2]
        return math.hypot(point[0] - mid[0], point[1] - mid[1])

    def get_midpoint(self, wire: WireState) -> Tuple[int, int]:
        return wire.control_points[len(wire.control_points) // 2]
