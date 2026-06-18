"""Session export and optional remote API sync."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import urllib.request
    import urllib.error

    HAS_URLLIB = True
except ImportError:
    HAS_URLLIB = False


class SessionReporter:
    OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports"

    def __init__(self, api_url: Optional[str] = None) -> None:
        self.api_url = api_url or os.environ.get("EOD_API_URL")
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = datetime.now()
        self.events: list = []

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        self.events.append(
            {
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data,
            }
        )

    def build_report(
        self,
        mission: Dict,
        performance: Dict,
        biometrics_summary: Dict,
        wire_data: Dict,
    ) -> Dict[str, Any]:
        duration = (datetime.now() - self.start_time).total_seconds() / 60
        return {
            "session_summary": {
                "session_id": self.session_id,
                "duration_minutes": duration,
                "mission_id": mission.get("id"),
                "mission_name": mission.get("name"),
                "tier": mission.get("tier"),
                "difficulty": mission.get("difficulty"),
                "passed": performance.get("passed", False),
                "overall_score": performance.get("overall_score", 0),
                "grade": performance.get("grade", "N/A"),
            },
            "performance_metrics": performance.get("categories", {}),
            "biometrics": biometrics_summary,
            "wire_data": wire_data,
            "protocol_violations": performance.get("violations", []),
            "recommendations": performance.get("recommendations", []),
            "events": self.events,
            "framework": "IMAS 09.31 / STM-EOD Training Simulation v2.0",
        }

    def save_local(self, report: Dict[str, Any]) -> Path:
        self.OUTPUT_DIR.mkdir(exist_ok=True)
        path = self.OUTPUT_DIR / f"eod_session_{self.session_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return path

    def sync_to_api(self, report: Dict[str, Any]) -> bool:
        if not self.api_url or not HAS_URLLIB:
            return False
        try:
            url = self.api_url.rstrip("/") + "/api/sessions"
            data = json.dumps(report).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False
