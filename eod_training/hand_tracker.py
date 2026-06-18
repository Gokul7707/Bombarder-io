"""MediaPipe Tasks hand tracking — high-accuracy model, responsive 1:1 screen mapping."""

from __future__ import annotations

import math
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from eod_training.hand_overlay import LandmarkSmoother
from eod_training.viewport_mapper import ViewportMapper
from eod_training.calibration_flow import CalibrationProfile

MODEL_BASE = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
# Official MediaPipe bundle — float32 variant is not published (404 on CDN)
MODEL_CANDIDATES = [
    MODEL_BASE,
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
]
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker.task"
LEGACY_FP32_PATH = Path(__file__).resolve().parent.parent / "models" / "hand_landmarker_fp32.task"


def _ensure_model() -> str:
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 100_000:
        return str(MODEL_PATH)

    # Remove empty/partial download from failed float32 attempt
    if LEGACY_FP32_PATH.exists() and LEGACY_FP32_PATH.stat().st_size < 100_000:
        LEGACY_FP32_PATH.unlink(missing_ok=True)

    last_err: Exception | None = None
    for url in MODEL_CANDIDATES:
        try:
            print(f"Downloading hand_landmarker model from MediaPipe...")
            urllib.request.urlretrieve(url, MODEL_PATH)
            if MODEL_PATH.stat().st_size > 100_000:
                print(f"Model saved to {MODEL_PATH}")
                return str(MODEL_PATH)
        except Exception as exc:
            last_err = exc
            MODEL_PATH.unlink(missing_ok=True)
            print(f"Download failed ({exc}), trying next source...")

    raise RuntimeError(
        "Could not download hand_landmarker.task. Check your internet connection "
        f"or place the model manually at: {MODEL_PATH}"
    ) from last_err


class HandTracker:
    FINGER_TIPS = [4, 8, 12, 16, 20]
    FINGER_PIPS = [3, 6, 10, 14, 18]
    FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]
    TRACK_MAX_WIDTH = 640

    def __init__(self, frame_width: int, frame_height: int) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self._clock_start = time.perf_counter()
        self.smoother = LandmarkSmoother()
        self.cursor_smoother = LandmarkSmoother(ema_alpha=0.62, responsive=True)
        self.viewport = ViewportMapper(frame_width, frame_height, frame_width, frame_height)
        self._cal = CalibrationProfile.load()

        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=_ensure_model()),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.55,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)

    def reload_calibration(self) -> None:
        self._cal = CalibrationProfile.load()

    def _apply_individual_offset(self, label: str, pt: Tuple[int, int]) -> Tuple[int, int]:
        if not self._cal.completed:
            return pt
        scale = self._cal.left_scale if label == "left" else self._cal.right_scale
        off = self._cal.left_offset if label == "left" else self._cal.right_offset
        cx, cy = self.frame_width // 2, self.frame_height // 2
        x = int(cx + (pt[0] - cx) * scale + off[0] * self.frame_width * 0.02)
        y = int(cy + (pt[1] - cy) * scale + off[1] * self.frame_height * 0.02)
        return (
            max(0, min(self.frame_width - 1, x)),
            max(0, min(self.frame_height - 1, y)),
        )

    def sync_dimensions(self, cam_w: int, cam_h: int, display_w: int | None = None, display_h: int | None = None) -> None:
        dw = display_w or cam_w
        dh = display_h or cam_h
        self.frame_width = cam_w
        self.frame_height = cam_h
        self.viewport.set_camera(cam_w, cam_h)
        self.viewport.set_display(dw, dh)

    def _timestamp_ms(self) -> int:
        return int((time.perf_counter() - self._clock_start) * 1000)

    def process(self, frame, stability: float = 1.0, mirror: bool = True) -> Dict[str, Any]:
        cam_h, cam_w = frame.shape[:2]
        if cam_w != self.frame_width or cam_h != self.frame_height:
            self.sync_dimensions(cam_w, cam_h)

        track_frame = frame
        if cam_w > self.TRACK_MAX_WIDTH:
            tw = self.TRACK_MAX_WIDTH
            th = max(1, int(cam_h * tw / cam_w))
            track_frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_LINEAR)

        rgb = cv2.cvtColor(track_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = self._timestamp_ms()
        result = self.landmarker.detect_for_video(mp_image, ts)
        now = time.perf_counter()

        data: Dict[str, Any] = {
            "left_hand": None,
            "right_hand": None,
            "primary_center": None,
            "pinch_active": False,
            "pointing_active": False,
            "open_palm": False,
            "peace_active": False,
            "fist_active": False,
            "thumbs_up_active": False,
            "finger_count": 0,
        }

        if not result.hand_landmarks:
            return data

        total_fingers = 0
        world_list = result.hand_world_landmarks or []

        for idx, hand_landmarks in enumerate(result.hand_landmarks):
            label = "right"
            if result.handedness and idx < len(result.handedness):
                cats = result.handedness[idx]
                if cats:
                    label = cats[0].category_name.lower()
            if mirror:
                label = "left" if label == "right" else "right"

            norm = [(lm.x, lm.y, lm.z) for lm in hand_landmarks]
            world = None
            if idx < len(world_list):
                world = [(lm.x, lm.y, lm.z) for lm in world_list[idx]]

            raw = [
                (int(lm.x * self.frame_width), int(lm.y * self.frame_height))
                for lm in hand_landmarks
            ]
            landmarks = self.smoother.smooth(label, raw, now)
            cursor_pts = self.cursor_smoother.smooth(f"cursor_{label}", raw, now)

            display_landmarks = self.viewport.map_landmarks_to_display(landmarks)
            display_cursor = self.viewport.map_landmarks_to_display(cursor_pts)

            fingers = self._finger_states(display_landmarks, norm)
            palm_span = self._palm_span(norm)
            finger_count = sum(1 for v in fingers.values() if v)
            total_fingers += finger_count
            gestures = self._classify_gestures(display_landmarks, fingers, palm_span)
            center = self._center(display_landmarks)
            index_tip = self._apply_individual_offset(label, display_landmarks[8])
            screen_tip = self._apply_individual_offset(label, display_cursor[8])

            hand_info = {
                "landmarks": display_landmarks,
                "norm_landmarks": norm,
                "world_landmarks": world,
                "center": center,
                "index_tip": index_tip,
                "screen_tip": screen_tip,
                "fingers": fingers,
                "gestures": gestures,
                "finger_count": finger_count,
                "palm_span": palm_span,
            }
            data[f"{label}_hand"] = hand_info

            if data["primary_center"] is None:
                data["primary_center"] = screen_tip
            if "pointing" in gestures:
                data["pointing_active"] = True
                data["primary_center"] = screen_tip
            if "pinch" in gestures:
                data["pinch_active"] = True
            if "open_hand" in gestures:
                data["open_palm"] = True
            if "peace" in gestures:
                data["peace_active"] = True
            if "fist" in gestures:
                data["fist_active"] = True
            if "thumbs_up" in gestures:
                data["thumbs_up_active"] = True

        data["finger_count"] = total_fingers
        return data

    def _finger_states(
        self, landmarks: List[Tuple[int, int]], norm: List[Tuple[float, float, float]]
    ) -> Dict[str, bool]:
        states = {}
        for i, (tip, pip) in enumerate(zip(self.FINGER_TIPS, self.FINGER_PIPS)):
            if i == 0:
                extended = landmarks[tip][0] > landmarks[pip][0] + 5
            else:
                extended = landmarks[tip][1] < landmarks[pip][1] - max(5, int(self._palm_span(norm) * 30))
            states[self.FINGER_NAMES[i]] = extended
        return states

    @staticmethod
    def _palm_span(norm: List[Tuple[float, float, float]]) -> float:
        return math.hypot(norm[5][0] - norm[17][0], norm[5][1] - norm[17][1])

    def _classify_gestures(
        self,
        landmarks: List[Tuple[int, int]],
        fingers: Dict[str, bool],
        palm_span: float,
    ) -> List[str]:
        thumb, index = landmarks[4], landmarks[8]
        pinch_thresh = max(36, int(palm_span * self.viewport.display_w * 0.11))
        pinch_dist = math.hypot(thumb[0] - index[0], thumb[1] - index[1])
        pinching = pinch_dist < pinch_thresh

        gestures: List[str] = []

        if pinching:
            gestures.append("pinch")
            return gestures

        if not any(fingers.values()):
            gestures.append("fist")
            return gestures

        if fingers.get("index") and fingers.get("middle") and not fingers.get("ring"):
            gestures.append("peace")

        if self._is_thumbs_up(landmarks, fingers):
            gestures.append("thumbs_up")

        if (
            fingers.get("index")
            and not fingers.get("middle")
            and not fingers.get("ring")
            and not fingers.get("pinky")
        ):
            gestures.append("pointing")

        extended_count = sum(1 for v in fingers.values() if v)
        if extended_count >= 4 and not pinching:
            gestures.append("open_hand")

        return gestures

    @staticmethod
    def _is_thumbs_up(landmarks: List[Tuple[int, int]], fingers: Dict[str, bool]) -> bool:
        if not fingers.get("thumb"):
            return False
        if any(fingers.get(f) for f in ("index", "middle", "ring", "pinky")):
            return False
        wrist = landmarks[0]
        thumb_tip = landmarks[4]
        return thumb_tip[1] < wrist[1] - 12

    @staticmethod
    def _center(landmarks: List[Tuple[int, int]]) -> Tuple[int, int]:
        xs = [p[0] for p in landmarks]
        ys = [p[1] for p in landmarks]
        return sum(xs) // len(xs), sum(ys) // len(ys)

    def release(self) -> None:
        self.landmarker.close()
