# EOD Operator Readiness Platform

Remote EOD teleop training simulator with MediaPipe hand tracking, premium FPS-style UI, and session certification reporting.

## What runs where

| Component | Where | Purpose |
|-----------|-------|---------|
| `glove.py` | **Local PC** (webcam + OpenCV) | Full training simulator |
| `api/` + `public/` | **Vercel** | Session API + certification dashboard |

The OpenCV app cannot run on Vercel — only the API and static dashboard deploy there. After a mission, local sessions sync to your deployed API when `EOD_API_URL` is set.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-local.txt
python glove.py
```

On first run, the MediaPipe hand model auto-downloads to `models/hand_landmarker.task`.

### Controls

- **UI buttons** — place your index fingertip target on a button and **hold** until the progress bar fills (no pinch)
- **Wire defusal** — point green skeletal fingertip on highlighted cut zone, hold steady (~0.5s)
- **Full-display tracking** — webcam stays in the corner PIP; your hand maps across the whole UI for targeting
- **Peace sign 2.5s** — recalibrate biometric link (menu)
- **Fist 2.5s** — quit
- **Open palm 1s** — return to chapter select (after mission end)

FPS is shown top-left; green = 30+ FPS target.

Delete `config/calibration_profile.json` to force a fresh per-operator calibration scan.

## Sync sessions to Vercel

After deploying (below), set the API URL when running locally:

```bash
# Windows PowerShell
$env:EOD_API_URL="https://your-project.vercel.app"
python glove.py
```

Sessions save locally in `reports/` and POST to `/sessions` on the API.

## Deploy to GitHub

```bash
git init
git add .
git commit -m "EOD Operator Readiness Platform v4"
git branch -M main
git remote add origin https://github.com/YOUR_USER/opencv_prjct1.git
git push -u origin main
```

## Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import your GitHub repo.
2. Framework preset: **Other** (no build command needed).
3. Root `requirements.txt` contains only FastAPI deps for the Python serverless function.
4. Deploy. Routes are defined in `vercel.json`:
   - `/` — certification dashboard (`public/index.html`)
   - `/sessions`, `/health` — FastAPI backend (`api/index.py`)

### Environment variables (optional)

| Variable | Used by | Description |
|----------|---------|-------------|
| `EOD_API_URL` | `glove.py` (local) | Your Vercel deployment URL for session sync |

## Project structure

```
glove.py                 # Main OpenCV training app
eod_training/            # Hand tracking, UI, missions, protocols
api/main.py              # FastAPI session storage
public/index.html        # Vercel dashboard
config/missions.json     # 8 story chapters
vercel.json              # Vercel routing
requirements.txt         # API deps (Vercel)
requirements-local.txt   # Full local deps (OpenCV, MediaPipe)
```

## Performance tips (30+ FPS)

- Tracking runs at 640px width internally; display stays full resolution
- Camera buffer size set to 1 for lower latency
- Scene/preview caching reduces draw cost
- Close other camera apps; use good lighting for stable hand detection

## License

Training simulation for educational / readiness use. Not for live EOD operations.
