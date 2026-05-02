# CHAPTER 5 SOURCE CODE

## 5.1 Import Packages

```python
import os
import cv2
import json
import time
import uuid
import asyncio
import threading
import numpy as np
import concurrent.futures

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, Callable

from ultralytics import YOLO
import easyocr

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import socketio

from motor.motor_asyncio import AsyncIOMotorClient
from jose import jwt, JWTError
from pydantic import BaseModel
```

This project uses a full-stack architecture:

1. Computer vision pipeline (YOLO + OCR) for violation detection.
2. FastAPI + Socket.IO backend for APIs and live streaming.
3. React frontend for dashboard, camera monitoring, upload, and results.

## 5.2 Model and Database Initialization

```python
# backend/model_registry.py
MODEL_COCO   = "yolov8n.pt"
MODEL_HELMET = r"D:\Final year project\user interface\models\helmet\best.pt"
MODEL_PLATE  = r"D:\Final year project\user interface\models\license\best.pt"

class ModelRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._loaded = False
        return cls._instance

    def load(self):
        if self._loaded:
            return
        self.coco_model = YOLO(MODEL_COCO)
        self.helmet_model = YOLO(MODEL_HELMET)
        self.plate_model = YOLO(MODEL_PLATE)
        self.ocr_reader = easyocr.Reader(['en'], gpu=False)
        self._loaded = True

models = ModelRegistry()
```

```python
# backend/database.py
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "violations_db"

client = AsyncIOMotorClient(MONGODB_URI)
db = client[DB_NAME]

users_collection = db["users"]
cameras_collection = db["cameras"]
violations_collection = db["violations"]

async def create_indexes():
    await users_collection.create_index("email", unique=True)
    await cameras_collection.create_index("camera_id", unique=True)
    await violations_collection.create_index("camera_id")
    await violations_collection.create_index("violation_type")
    await violations_collection.create_index("detected_at")
```

## 5.3 Data Preprocessing and Association

The system associates persons/helmet/plate detections with each motorcycle before deciding violations.

```python
# integrate/main.py
ASSOC_IOU_THRESH = 0.10
PERSON_BIKE_IOP_THRESH = 0.12
PLATE_SEARCH_DOWN_FRAC = 0.40


def _persons_on_bike(persons, bike_box):
    result = []
    for p in persons:
        iou = get_iou(p[:4], bike_box[:4])
        iop = get_iop(p[:4], bike_box[:4])
        if iou >= ASSOC_IOU_THRESH or iop >= PERSON_BIKE_IOP_THRESH:
            result.append(p)
    return result


def _dets_on_bike(dets, bike_box):
    return [
        d for d in dets
        if (get_iou(d[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
            or is_rider_on_bike(d[:4], bike_box))
    ]


def _plate_search_box(bike_box, persons_on, helmets_on, no_helmets_on, frame_h):
    all_boxes = [bike_box[:4]] + [d[:4] for d in persons_on + helmets_on + no_helmets_on]
    ux1 = int(min(b[0] for b in all_boxes))
    uy1 = int(min(b[1] for b in all_boxes))
    ux2 = int(max(b[2] for b in all_boxes))
    uy2 = int(max(b[3] for b in all_boxes))
    bike_h = bike_box[3] - bike_box[1]
    ext_y2 = min(frame_h, int(uy2 + bike_h * PLATE_SEARCH_DOWN_FRAC))
    return (ux1, uy1, ux2, ext_y2)
```

## 5.4 Violation Logic Modules

### 5.4.1 Helmet Violation

```python
# integrate/helmet_logic.py

def check_helmet_violation(no_helmets_on_bike: list, helmets_on_bike: list) -> tuple:
    if not no_helmets_on_bike:
        return False, {}

    details = {
        'rider_boxes': [b[:4] for b in no_helmets_on_bike],
        'helmet_boxes': [b[:4] for b in helmets_on_bike],
        'n_no_helmet': len(no_helmets_on_bike),
        'n_helmet': len(helmets_on_bike),
    }
    return True, details
```

### 5.4.2 Triple Riding Violation

```python
# integrate/triple_riding.py
TRIPLE_THRESHOLD = 3


def check_triple_riding(persons_on_bike: list, helmets_on_bike: list, no_helmets_on_bike: list) -> tuple:
    coco_count = len(persons_on_bike)
    head_count = count_distinct_heads(helmets_on_bike, no_helmets_on_bike)
    effective = max(coco_count, head_count)

    if effective < TRIPLE_THRESHOLD:
        return False, {}

    details = {
        'person_count': effective,
        'coco_count': coco_count,
        'head_count': head_count,
        'person_boxes': [p[:4] for p in persons_on_bike],
    }
    return True, details
```

### 5.4.3 Co-riding without Helmet

```python
# integrate/co_riding.py

def check_co_riding(persons_on_bike: list, helmets_on_bike: list, no_helmets_on_bike: list, bike_box: tuple) -> tuple:
    if len(persons_on_bike) != 2:
        return False, {}

    pillion = identify_pillion(persons_on_bike, bike_box)
    if pillion is None:
        return False, {}

    _, p_no_helmets = assign_head_detections(persons_on_bike, helmets_on_bike, no_helmets_on_bike)

    pillion_idx = 0 if persons_on_bike[0] is pillion else 1
    if not p_no_helmets[pillion_idx]:
        return False, {}

    return True, {
        'pillion_box': pillion[:4],
        'path': 'two_person',
    }
```

## 5.5 OCR and Number Plate Correction

```python
# integrate/ocr_numberplate.py

def get_plate_for_bike(plates, bike_box, original_img, reader,
                       preferred_states=None, search_box=None,
                       fast_mode=True, k_key_pool=None, k_image=None):
    """
    1) Find candidate plate boxes on bike
    2) Run OCR (EasyOCR / K fallback)
    3) Correct Indian plate format
    """
    # Real implementation includes:
    # - search-box constrained OCR
    # - blind scan fallback
    # - Indian state/district correction
    # - confidence filtering
    pass
```

## 5.6 Single Workflow Detection Pipeline (No Threads)

This is the sequential workflow used for uploaded videos in the application.

```python
# integrate/main.py
def run_pipeline(video_path: str, output_path: str,
                 json_path: str | None = None,
                 model_registry=None) -> ViolationMemory:
    coco_m = model_registry.coco_model
    helm_m = model_registry.helmet_model
    plat_m = model_registry.plate_model

    tracker = SOTTracker(max_age=10 * FILE_PROCESS_EVERY_N, iou_thresh=0.25)
    memory = ViolationMemory()

    cap = cv2.VideoCapture(video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(
        output_path,
        cv2.VideoWriter_fourcc(*'mp4v'),
        src_fps,
        (src_w, src_h),
    )

    fn = 0
    infer_n = 0
    snap = DetectionSnapshot()
    last_annotated = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        fn += 1
        tracker.predict_all()
        is_infer = (fn % FILE_PROCESS_EVERY_N == 0 or fn == 1)

        if is_infer:
            infer_n += 1
            coco_res = coco_m(frame, imgsz=INFER_SIZE, verbose=False)[0]
            helmet_res = helm_m(frame, imgsz=INFER_SIZE, verbose=False)[0]
            plate_res = plat_m(frame, verbose=False)[0]

            # parse detections -> associate riders to bikes
            # check NO_HELMET / TRIPLE_RIDING / CO_RIDING
            # update violation memory

            snap = DetectionSnapshot(
                tracked=tracked,
                persons=persons,
                helmets=helmets,
                no_helmets=no_helmets,
                plates=plates,
                infer_count=infer_n,
            )
            last_annotated = draw_frame(frame, snap, memory)

        elif last_annotated is not None:
            # non-inference frame: reuse previous detections on current frame
            last_annotated = draw_frame(frame, snap, memory)

        out_frame = last_annotated if last_annotated is not None else frame
        writer.write(out_frame)

    cap.release()
    writer.release()

    if json_path:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(memory.to_json(), f, indent=2)

    return memory
```

## 5.7 Pipeline Connections (Live + Upload)

### 5.7.1 Live Pipeline (Camera Mode)

```python
# backend/camera_manager.py
def _run_camera(source, camera_id, stop_event,
                violation_cb, plate_resolved_cb, frame_cb, on_exit):
    run_pipeline_live = importlib.import_module("main").run_pipeline_live
    from model_registry import models

    run_pipeline_live(
        camera_source=source,
        camera_id=camera_id,
        stop_event=stop_event,
        violation_callback=violation_cb,
        plate_resolved_callback=plate_resolved_cb,
        frame_callback=frame_cb,
        model_registry=models,
    )
```

### 5.7.2 Video Upload Pipeline (Sequential)

```python
# backend/routers/upload.py
main_module = importlib.import_module("main")
main_module = importlib.reload(main_module)
run_pipeline = main_module.run_pipeline

memory = run_pipeline(
    video_path=input_path,
    output_path=output_path,
    json_path=json_path,
    model_registry=models,
)

records = memory.all_records()
_jobs[job_id].update({
    "status": "done",
    "progress_pct": 100.0,
    "violations": violation_docs,
})
```

## 5.8 FastAPI + Socket.IO Backend

```python
# backend/app.py
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["http://localhost:3000", "http://localhost:5173"],
)

app = FastAPI(title="Drive Defender API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(violations.router)
app.include_router(upload.router)
app.include_router(stats.router)

socket_app = socketio.ASGIApp(sio, app)
```

### 5.8.1 Authentication Endpoints

```python
# backend/routers/auth.py
@router.post("/register")
async def register(req: RegisterRequest):
    ...

@router.post("/login")
async def login(req: LoginRequest):
    ...

@router.get("/me")
async def me(user=Depends(get_current_user)):
    ...
```

### 5.8.2 Camera Management Endpoints

```python
# backend/routers/cameras.py
@router.get("")
async def list_cameras(user=Depends(get_current_user)):
    ...

@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, user=Depends(get_current_user)):
    ...

@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, user=Depends(get_current_user)):
    ...
```

### 5.8.3 Violation and Stats Endpoints

```python
# backend/routers/violations.py
@router.get("")
async def list_violations(...):
    ...

@router.delete("/{violation_id}")
async def delete_violation(violation_id: str, user=Depends(get_current_user)):
    ...

# backend/routers/stats.py
@router.get("/summary")
async def get_summary(user=Depends(get_current_user)):
    ...

@router.get("/timeline")
async def get_timeline(days: int = Query(7, ge=1, le=90), user=Depends(get_current_user)):
    ...
```

## 5.9 Frontend Integration (React + Zustand + Socket.IO)

```javascript
// frontend/src/services/api.js
import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export default api;
```

```javascript
// frontend/src/services/socket.js
import { io } from "socket.io-client";

const socket = io("http://localhost:8000", {
  autoConnect: false,
  transports: ["websocket", "polling"],
});

export function connectSocket() {
  if (!socket.connected) socket.connect();
}

export default socket;
```

```javascript
// frontend/src/store/cameraStore.js
import { create } from "zustand";
import api from "../services/api";

const useCameraStore = create((set) => ({
  cameras: [],
  frames: {},

  fetchCameras: async () => {
    const res = await api.get("/api/cameras");
    set({ cameras: res.data });
  },

  startCamera: async (cameraId) => {
    await api.post(`/api/cameras/${cameraId}/start`);
  },

  stopCamera: async (cameraId) => {
    await api.post(`/api/cameras/${cameraId}/stop`);
  },
}));

export default useCameraStore;
```

## 5.10 Key Frontend Pages and Language Support

The following snippets are intentionally short and represent the core logic used in the UI pages.

### 5.10.1 Camera Page

```javascript
// frontend/src/pages/Cameras.jsx
useEffect(() => {
  fetchCameras();
  connectSocket();

  const handleFrame = (data) => updateFrame(data.camera_id, data.jpeg_b64);
  const handleCameraStatus = (data) =>
    updateCameraStatus(data.camera_id, data.status);

  socket.on("frame", handleFrame);
  socket.on("camera_status", handleCameraStatus);

  return () => {
    socket.off("frame", handleFrame);
    socket.off("camera_status", handleCameraStatus);
  };
}, []);

const handleAdd = async (e) => {
  e.preventDefault();
  await addCamera(form);
};
```

### 5.10.2 Upload Page

```javascript
// frontend/src/pages/Upload.jsx
const handleUpload = async () => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await api.post("/api/upload/video", formData);
  setJobId(res.data.job_id);
  setJobStatus("processing");
};

useEffect(() => {
  if (!jobId) return;

  const interval = setInterval(async () => {
    const { data } = await api.get(`/api/upload/status/${jobId}`);
    setProgressPct(data.progress_pct || 0);

    if (data.status === "done") {
      setJobStatus("done");
      setViolations(data.violations || []);
      clearInterval(interval);
    }
  }, 2000);

  return () => clearInterval(interval);
}, [jobId]);
```

### 5.10.3 Violations Page

```javascript
// frontend/src/pages/Violations.jsx
useEffect(() => {
  fetchViolations();
  fetchCameras();
}, [page]);

useEffect(() => {
  connectSocket();
  socket.on("violation_new", handleViolationNew);
  socket.on("violation_plate_update", handlePlateUpdate);

  return () => {
    socket.off("violation_new", handleViolationNew);
    socket.off("violation_plate_update", handlePlateUpdate);
  };
}, []);

const exportCSV = () => {
  const headers = [
    "Camera ID",
    "Violation Type",
    "Plate",
    "Confidence",
    "Detected At",
  ];
  const rows = violations.map((v) => [
    v.camera_id,
    v.violation_type,
    v.plate_text || "UNDETECTED",
  ]);
  const csv = [headers, ...rows].map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "violations_export.csv";
  a.click();
};
```

### 5.10.4 Language Support (i18n)

```javascript
// frontend/src/i18n.js
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      /* ...full English keys... */
    },
  },
  hi: {
    translation: {
      /* ...full Hindi keys... */
    },
  },
  te: {
    translation: {
      /* ...full Telugu keys... */
    },
  },
  ta: {
    translation: {
      /* ...full Tamil keys... */
    },
  },
  mr: {
    translation: {
      /* ...full Marathi keys... */
    },
  },
};

i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem("app_lang") || "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});
```

```javascript
// frontend/src/components/Navbar.jsx
const handleLanguageChange = (e) => {
  const nextLang = e.target.value;
  i18n.changeLanguage(nextLang);
  localStorage.setItem("app_lang", nextLang);
};

<select
  value={i18n.resolvedLanguage || i18n.language || "en"}
  onChange={handleLanguageChange}
>
  <option value="en">English</option>
  <option value="hi">Hindi</option>
  <option value="te">Telugu</option>
  <option value="ta">Tamil</option>
  <option value="mr">Marathi</option>
</select>;
```

## 5.11 Model Training Script (License Plate)

```python
# models/license/license_plate.py
import torch
from ultralytics import YOLO

DATA_YAML = "License-Plate-Recognition-6/data.yaml"
device = 0 if torch.cuda.is_available() else "cpu"

model = YOLO("yolov8n.pt")
model.train(
    data=DATA_YAML,
    epochs=20,
    imgsz=640,
    batch=16,
    device=device,
    workers=2,
    patience=10,
    name="traffic_violation_model",
)
```

## 5.12 Output Artifacts

The system generates:

1. Annotated output videos for uploaded files.
2. JSON violation reports.
3. MongoDB violation records.
4. Cloudinary evidence image URLs.
5. Real-time Socket.IO events for frontend alerts.

This Chapter 5 source code represents the complete implementation of the smart traffic violation detection platform (NO_HELMET, TRIPLE_RIDING, CO_RIDING_NO_HELMET) with OCR-based license plate extraction and full-stack deployment support.
