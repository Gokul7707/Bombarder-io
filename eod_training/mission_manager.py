"""Mission and difficulty progression manager."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class MissionManager:
    CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "missions.json"

    TIERS = ["RECRUIT", "OPERATOR", "EOD_TECH"]

    def __init__(self) -> None:
        with open(self.CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        self.missions: List[Dict[str, Any]] = data["missions"]
        self.current_index = 0
        self.unlocked = {m["id"] for m in self.missions if m["difficulty"] == 1}
        self.completed: List[str] = []

    @property
    def current(self) -> Dict[str, Any]:
        return self.missions[self.current_index]

    def select_mission(self, mission_id: str) -> bool:
        for i, m in enumerate(self.missions):
            if m["id"] == mission_id and mission_id in self.unlocked:
                self.current_index = i
                return True
        return False

    def next_mission(self) -> Optional[Dict[str, Any]]:
        if self.current_index + 1 < len(self.missions):
            self.current_index += 1
            self.unlocked.add(self.missions[self.current_index]["id"])
            return self.current
        return None

    def complete_current(self, passed: bool) -> None:
        mid = self.current["id"]
        if passed and mid not in self.completed:
            self.completed.append(mid)
            nxt = self.current_index + 1
            if nxt < len(self.missions):
                self.unlocked.add(self.missions[nxt]["id"])

    def list_missions(self) -> List[Dict[str, Any]]:
        result = []
        for m in self.missions:
            result.append(
                {
                    **m,
                    "unlocked": m["id"] in self.unlocked,
                    "completed": m["id"] in self.completed,
                }
            )
        return result

    def wire_colors_for_mission(self) -> List[str]:
        count = self.current.get("wire_count", 3)
        if count <= 0:
            return []
        pool = ["RED", "BLUE", "GREEN", "YELLOW", "WHITE", "BLACK", "ORANGE"]
        import random

        return random.sample(pool, min(count, len(pool)))
