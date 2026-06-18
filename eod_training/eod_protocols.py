"""EOD protocol engine — 5 Cs, 9 procedures, RSP rulesets."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional


class EODProtocolEngine:
    CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "eod_protocols.json"

    def __init__(self) -> None:
        with open(self.CONFIG_PATH, encoding="utf-8") as f:
            self.config = json.load(f)
        self.five_cs = self.config["five_cs"]
        self.procedures = self.config["nine_procedures"]
        self.rsp_principles = self.config["rsp_principles"]
        self.grading = self.config["grading_rubric"]
        self.completed_cs: List[str] = []
        self.completed_phases: List[str] = []
        self.protocol_violations: List[str] = []

    def reset_checklist(self) -> None:
        self.completed_cs = []
        self.completed_phases = []
        self.protocol_violations = []

    def complete_c(self, c_id: str) -> bool:
        if c_id not in self.completed_cs:
            self.completed_cs.append(c_id)
            return True
        return False

    def all_cs_complete(self) -> bool:
        return len(self.completed_cs) >= len(self.five_cs)

    def record_phase(self, phase: str) -> None:
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)

    def record_violation(self, message: str) -> None:
        self.protocol_violations.append(message)

    def compute_wire_sequence(
        self,
        active_wires: List[str],
        ruleset: str = "basic_rsp",
        serial_odd: Optional[bool] = None,
    ) -> List[str]:
        """Derive cut sequence from circuit analysis — not random Hollywood rules."""
        wires = list(active_wires)
        sequence: List[str] = []
        serial_odd = serial_odd if serial_odd is not None else random.choice([True, False])

        if serial_odd and "RED" in wires:
            sequence.append("RED")
            wires.remove("RED")

        if wires.count("BLUE") >= 2:
            blues = [i for i, w in enumerate(active_wires) if w == "BLUE"]
            if len(blues) >= 2:
                sequence.append("BLUE")
                wires.remove("BLUE")

        if "YELLOW" not in wires and "GREEN" in wires:
            sequence.append("GREEN")
            wires.remove("GREEN")

        for w in sorted(wires):
            if w not in sequence:
                sequence.append(w)

        return sequence[: max(3, min(len(active_wires), 5))]

    def build_manual_text(self, wires: List[str], sequence: List[str], device_type: str) -> List[str]:
        lines = [
            "═══ EOD TECHNICIAN MANUAL — TRAINING EDITION ═══",
            f"Device classification: {device_type.upper().replace('_', ' ')}",
            "",
            "RSP PRINCIPLES (mandatory):",
        ]
        for p in self.rsp_principles[:3]:
            lines.append(f"  • {p}")
        lines += [
            "",
            f"Active circuits: {', '.join(wires)}",
            f"Analysis sequence: {' → '.join(sequence)}",
            "",
            "⚠ Remote tool MUST be placed before manual wire interruption.",
        ]
        return lines

    def get_grading_weights(self) -> Dict[str, float]:
        return {k: v["weight"] for k, v in self.grading["categories"].items()}

    def pass_threshold(self) -> int:
        return self.grading["pass_threshold"]
