"""EOD Operator Readiness — Streamlit live demo (dashboard + mission hub).

The full hand-tracking simulator (glove.py) runs locally with a webcam.
Streamlit Cloud hosts this web portal only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
MISSIONS_PATH = ROOT / "config" / "missions.json"
DEFAULT_API = os.environ.get("EOD_API_URL", "https://bombarderio.vercel.app").rstrip("/")


@st.cache_data
def load_missions() -> list:
    if not MISSIONS_PATH.exists():
        return []
    data = json.loads(MISSIONS_PATH.read_text(encoding="utf-8"))
    return data.get("missions", [])


def fetch_sessions(api_base: str) -> tuple[list, str]:
    try:
        r = requests.get(f"{api_base}/api/sessions", timeout=10)
        r.raise_for_status()
        return r.json().get("sessions", []), ""
    except Exception as exc:
        return [], str(exc)


st.set_page_config(
    page_title="EOD Operator Readiness",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("EOD Operator Readiness Platform")
st.caption("Train the human behind the robot — decisions, stress, and remote precision.")

col_a, col_b = st.columns([2, 1])

with col_a:
    st.subheader("Operator certification sessions")
    api_url = st.text_input("Session API URL", value=DEFAULT_API, help="Vercel API base URL (no trailing slash)")
    sessions, err = fetch_sessions(api_url)

    if err:
        st.warning(f"Could not load sessions: {err}")
        st.info("Sessions appear here after you complete a mission locally with EOD_API_URL set.")
    elif not sessions:
        st.info("No sessions yet. Run `python glove.py` on your PC and finish a chapter.")
    else:
        st.success(f"{len(sessions)} certification record(s)")
        st.dataframe(sessions, use_container_width=True, hide_index=True)

with col_b:
    st.subheader("Run the full simulator")
    st.markdown(
        """
**Local only** (webcam + OpenCV):

```powershell
cd d:\\PROJECTS\\opencv_prjct1
pip install -r requirements-local.txt
$env:EOD_API_URL="https://bombarderio.vercel.app"
python glove.py
```

- Green skeletal hand tracking
- Hold fingertip on buttons / wire cut zones
- Results sync to the API above
        """
    )

st.divider()
st.subheader("Story chapters")

missions = load_missions()
if not missions:
    st.warning("missions.json not found in repo.")
else:
    for m in missions:
        story = m.get("story", {})
        with st.expander(f"Ch{m.get('chapter', '?')} — {m.get('name', 'Mission')}", expanded=m.get("chapter") == 1):
            st.markdown(f"**Victim:** {story.get('victim', '—')}")
            st.markdown(f"**Location:** {story.get('location', '—')}")
            st.markdown(f"**Briefing:** {story.get('briefing', m.get('description', ''))}")
            st.markdown(f"**Task:** {story.get('task', '—')}")
            st.caption(f"Tier: {m.get('tier', '—')}  |  Defusal: {m.get('defusal_label', '—')}")

st.divider()
st.markdown(
    """
### Remote teleop pipeline
1. Threat confirmation → Cordon → Robot deploy → Teleop RSP → Post-blast AAR
2. Place fingertip target on buttons — hold to activate
3. Wire cuts: point green target on cut zone and hold steady
4. Biometric calibration on first launch
    """
)
