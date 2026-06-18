"""FastAPI backend — Vercel entrypoint (app must live in this file)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="EOD Training API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = Path("/tmp/eod_reports") if os.environ.get("VERCEL") else _ROOT / "reports"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


class SessionPayload(BaseModel):
    session_summary: Dict[str, Any]
    performance_metrics: Optional[Dict[str, Any]] = None
    biometrics: Optional[Dict[str, Any]] = None
    wire_data: Optional[Dict[str, Any]] = None
    events: Optional[List[Any]] = None


@app.get("/")
def root():
    return {
        "service": "EOD Training Session API",
        "version": "2.0.0",
        "endpoints": ["/sessions", "/sessions/{id}", "/health"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/sessions")
def create_session(payload: SessionPayload):
    sid = payload.session_summary.get("session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    path = SESSIONS_DIR / f"api_{sid}.json"
    data = payload.model_dump()
    data["received_at"] = datetime.utcnow().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"ok": True, "session_id": sid, "path": str(path.name)}


@app.get("/sessions")
def list_sessions():
    files = sorted(SESSIONS_DIR.glob("*.json"), reverse=True)[:50]
    sessions = []
    for f in files:
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            summary = data.get("session_summary", data)
            sessions.append(
                {
                    "session_id": summary.get("session_id", f.stem),
                    "mission": summary.get("mission_name", "Unknown"),
                    "score": summary.get("overall_score", 0),
                    "passed": summary.get("passed", False),
                    "grade": summary.get("grade", "N/A"),
                }
            )
        except Exception:
            continue
    return {"sessions": sessions}


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    for pattern in [f"api_{session_id}.json", f"eod_session_{session_id}.json", f"*{session_id}*.json"]:
        matches = list(SESSIONS_DIR.glob(pattern))
        if matches:
            with open(matches[0], encoding="utf-8") as f:
                return json.load(f)
    raise HTTPException(status_code=404, detail="Session not found")


handler = app
application = app
