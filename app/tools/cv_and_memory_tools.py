"""cv_and_memory_tools.py -- computer vision, autonomous chaining, multimodal
and habit memory for MOON. Real implementations with safe fallbacks.
"""

from __future__ import annotations

import os
import time
import uuid
import pickle
from app.tools.base import BaseTool

MULTIMODAL_DIR = os.path.join(os.path.dirname(__file__), "..", "logs", "moon_multimodal_memory")
os.makedirs(MULTIMODAL_DIR, exist_ok=True)
MULTIMODAL_DB = os.path.join(os.path.dirname(__file__), "..", "logs", "multimodal_db.pkl")
PROFILE_PATH = os.path.expanduser("~/.meow/config.json")


def _load_multimodal():
    try:
        return pickle.load(open(MULTIMODAL_DB, "rb"))
    except Exception:
        return []


def _save_multimodal(db):
    try:
        pickle.dump(db, open(MULTIMODAL_DB, "wb"))
    except Exception:
        pass


def _load_profile():
    try:
        import json
        return json.load(open(PROFILE_PATH))
    except Exception:
        return {"name": "Psycho", "habits": {}}


def _save_profile(p):
    try:
        import json
        json.dump(p, open(PROFILE_PATH, "w"), indent=2)
    except Exception:
        pass


class ObjectTrackTool(BaseTool):
    name = "object_track"
    description = "Run YOLO object detection on a camera (id) or image path for a duration."

    async def execute(self, camera_id: int = 0, image_path: str = "", duration_seconds: float = 3.0,
                      target_object: str = "", **_kw) -> str:
        try:
            import cv2
            from ultralytics import YOLO
        except Exception as e:  # noqa: BLE001
            return f"[object_track] requires opencv + ultralytics (pip install opencv-python ultralytics): {e}"
        try:
            model = YOLO("yolov8n.pt")
        except Exception as e:  # noqa: BLE001
            return f"[object_track] could not load yolov8n.pt: {e}"
        dets = []
        if image_path:
            frame = cv2.imread(image_path)
            if frame is None:
                return f"[object_track] cannot read {image_path}"
            for b in model(frame, verbose=False)[0].boxes:
                label = model.names[int(b.cls[0])]
                if target_object and target_object.lower() not in label.lower():
                    continue
                dets.append(f"{label}({float(b.conf[0]):.2f})")
            return "Detections: " + (", ".join(dets) if dets else "none")
        cap = cv2.VideoCapture(int(camera_id))
        if not cap.isOpened():
            return f"[object_track] cannot open camera {camera_id}"
        start = time.time()
        while time.time() - start < float(duration_seconds or 3.0):
            ret, frame = cap.read()
            if not ret:
                break
            for b in model(frame, verbose=False)[0].boxes:
                label = model.names[int(b.cls[0])]
                if target_object and target_object.lower() not in label.lower():
                    continue
                dets.append(f"{label}({float(b.conf[0]):.2f})")
        cap.release()
        return "Camera detections: " + (", ".join(dets[:15]) if dets else "none")


class AutonomousChainTool(BaseTool):
    name = "autonomous_chain"
    description = "Plan and step through an autonomous task chain returned as a JSON list of subtasks."

    def __init__(self) -> None:
        self._chain: list[str] = []
        self._index = 0

    async def execute(self, action: str = "start", goal: str = "", **_kw) -> str:
        if action == "start":
            # Simple decomposer: split the goal into ordered subtasks via the planner if present.
            try:
                from app.brain.planner import Planner
                from app.services.llm_service import LLMService
                from app.config.settings import get_settings
                cfg = get_settings()
                llm = LLMService(model_name=cfg.model_name, base_url=cfg.model_base_url, api_key=cfg.model_api_key)
                await llm.setup()
                self._chain = await Planner(llm).plan(goal) or [goal]
            except Exception:
                self._chain = [goal]
            self._index = 0
            return "Chain: " + " | ".join(self._chain)
        if action == "step":
            if self._index < len(self._chain):
                task = self._chain[self._index]
                self._index += 1
                return f"NEXT: {task}"
            return "AUTONOMOUS_CHAIN_COMPLETE"
        return "[autonomous_chain] action must be 'start' or 'step'"


class MultimodalStoreTool(BaseTool):
    name = "multimodal_store"
    description = "Store a file (image/audio/doc) into MOON's multimodal memory with a description."

    async def execute(self, file_path: str = "", description: str = "", **_kw) -> str:
        if not file_path or not os.path.exists(file_path):
            return f"[multimodal_store] file not found: {file_path}"
        import shutil
        dest = os.path.join(MULTIMODAL_DIR, f"{uuid.uuid4()}{os.path.splitext(file_path)[1]}")
        try:
            shutil.copy(file_path, dest)
        except Exception as e:  # noqa: BLE001
            return f"[multimodal_store] copy failed: {e}"
        db = _load_multimodal()
        db.append({"file_path": dest, "description": description})
        _save_multimodal(db)
        return f"[multimodal_store] stored: {dest}"


class MultimodalSearchTool(BaseTool):
    name = "multimodal_search"
    description = "Search MOON's multimodal memory by description text."

    async def execute(self, query: str = "", top_k: int = 3, **_kw) -> str:
        db = _load_multimodal()
        hits = [f"{e['file_path']} - {e['description']}" for e in db if query.lower() in e.get("description", "").lower()]
        return "\n".join(hits[:int(top_k)]) if hits else "[multimodal_search] no matches"


class HabitLearnTool(BaseTool):
    name = "habit_learn"
    description = "Learn and persist one of Psycho's habits into the operator profile."

    async def execute(self, habit_name: str = "", frequency: str = "", details: str = "", **_kw) -> str:
        if not habit_name:
            return "[habit_learn] habit_name required"
        p = _load_profile()
        p.setdefault("habits", {})
        p["habits"][habit_name] = {"frequency": frequency, "details": details}
        _save_profile(p)
        return f"[habit_learn] learned habit '{habit_name}'"
