"""
app.py – FastAPI application entrypoint with Socket.IO integration.
"""

import os
import sys
import asyncio
import base64
import time
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import socketio

from database import create_indexes, violations_collection, cameras_collection
from cloudinary_service import configure_cloudinary, upload_violation_image
from camera_manager import CameraManager
from model_registry import models
from routers import auth, cameras, violations, upload, stats

# ═══════════════════════════════════════════════════════════════════════════════
# Socket.IO server
# ═══════════════════════════════════════════════════════════════════════════════

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["http://localhost:3000", "http://localhost:5173"],
)

# Track which clients are subscribed to which camera
_camera_subscribers = {}  # camera_id -> set of sid


@sio.event
async def connect(sid, environ):
    print(f"[WS] Client connected: {sid}")


@sio.event
async def disconnect(sid):
    # Remove from all subscriptions
    for cam_id in list(_camera_subscribers):
        _camera_subscribers[cam_id].discard(sid)
    print(f"[WS] Client disconnected: {sid}")


@sio.event
async def subscribe_camera(sid, data):
    cam_id = data.get("camera_id", "")
    if cam_id not in _camera_subscribers:
        _camera_subscribers[cam_id] = set()
    _camera_subscribers[cam_id].add(sid)
    print(f"[WS] {sid} subscribed to {cam_id}")


@sio.event
async def unsubscribe_camera(sid, data):
    cam_id = data.get("camera_id", "")
    if cam_id in _camera_subscribers:
        _camera_subscribers[cam_id].discard(sid)
    print(f"[WS] {sid} unsubscribed from {cam_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# Violation + Frame handlers for CameraManager callbacks
# ═══════════════════════════════════════════════════════════════════════════════

async def violation_handler(camera_id: str, rec, jpeg: bytes):
    """Called from camera thread when a violation is detected."""

    user_id = None
    try:
        cam = await cameras_collection.find_one({"camera_id": camera_id})
        if cam:
            user_id = cam.get("user_id")
    except Exception:
        user_id = None

    # ── Deduplication guard ────────────────────────────────────────────────
    # Skip if the same plate + violation type was already saved in the
    # last 60 seconds for this camera (prevents duplicate records from
    # the SORT tracker assigning multiple track IDs to one physical bike).
    if rec.plate_text:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        existing = await violations_collection.find_one({
            "user_id": user_id,
            "camera_id": camera_id,
            "plate_text": rec.plate_text,
            "violation_type": rec.violation_type,
            "detected_at": {"$gte": cutoff},
        })
        if existing:
            print(f"[DB DEDUP] Skipped: {rec.plate_text} / {rec.violation_type} — "
                  f"already logged in last 60s")
            return  # skip the insert entirely

    # 1. Upload evidence to Cloudinary
    cloud_result = {}
    try:
        loop = asyncio.get_event_loop()
        cloud_result = await loop.run_in_executor(
            None, upload_violation_image, jpeg, camera_id, rec.violation_type
        )
    except Exception as e:
        print(f"[Cloudinary] Upload failed: {e}")

    # 2. Save to MongoDB
    doc = {
        "user_id": user_id,
        "camera_id": camera_id,
        "track_id": rec.track_id,
        "violation_type": rec.violation_type,
        "plate_text": rec.plate_text,
        "plate_conf": round(rec.plate_conf, 4) if rec.plate_conf else 0.0,
        "frame_number": rec.frame_number,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "evidence_url": cloud_result.get("secure_url"),
        "cloudinary_id": cloud_result.get("public_id"),
    }
    await violations_collection.insert_one(doc)
    print(f"[Violation] Saved: camera={camera_id} type={rec.violation_type} "
          f"plate={rec.plate_text}")

    # 3. Emit real-time event to all connected clients
    await sio.emit("violation", {
        "camera_id": camera_id,
        "violation_type": rec.violation_type,
        "plate_text": rec.plate_text,
        "evidence_url": cloud_result.get("secure_url"),
        "detected_at": doc["detected_at"],
    })


# Frame rate limiting per camera
_last_frame_emit = {}

async def frame_handler(camera_id: str, jpeg: bytes):
    """Called from camera thread on each annotated frame."""
    now = time.time()
    last = _last_frame_emit.get(camera_id, 0)

    # Throttle to ~10 FPS
    if now - last < 0.1:
        return

    _last_frame_emit[camera_id] = now

    # Only send to subscribed clients
    subscribers = _camera_subscribers.get(camera_id, set())
    if not subscribers:
        return

    jpeg_b64 = base64.b64encode(jpeg).decode("ascii")
    for sid in subscribers:
        try:
            await sio.emit("frame", {
                "camera_id": camera_id,
                "jpeg_b64": jpeg_b64,
            }, to=sid)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI app
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Drive Defender API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(cameras.router)
app.include_router(violations.router)
app.include_router(upload.router)
app.include_router(stats.router)

# Serve output video files
OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)


@app.get("/api/video/{job_id}")
async def serve_video(job_id: str):
    """Serve annotated output video file."""
    for f in os.listdir(OUTPUTS_DIR):
        if f.startswith(job_id) and f.endswith("_output.mp4"):
            return FileResponse(
                os.path.join(OUTPUTS_DIR, f),
                media_type="video/mp4",
            )
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Video not found")


@app.get("/api/health")
async def health():
    """Frontend can poll this to know when models are ready."""
    return {
        "status": "ready" if models.is_loaded else "loading",
        "models_loaded": models.is_loaded,
    }


# CameraManager instance
camera_mgr = None


@app.on_event("startup")
async def startup():
    global camera_mgr

    # Create DB indexes
    await create_indexes()

    # Configure Cloudinary
    configure_cloudinary()

    # Camera status callback — updates DB + emits Socket.IO event
    async def camera_status_handler(camera_id: str, status: str):
        await cameras_collection.update_one(
            {"camera_id": camera_id},
            {"$set": {"status": status}}
        )
        await sio.emit("camera_status", {
            "camera_id": camera_id,
            "status": status,
        })
        print(f"[CameraManager] Status update: {camera_id} -> {status}")

    # Initialize CameraManager
    loop = asyncio.get_event_loop()
    camera_mgr = CameraManager(
        violation_handler, frame_handler, loop,
        status_callback=camera_status_handler
    )
    cameras.set_camera_manager(camera_mgr)

    # Reset all cameras to stopped on startup
    await cameras_collection.update_many({}, {"$set": {"status": "stopped"}})

    # Load ML models in a background thread (NON-BLOCKING)
    # Server starts accepting requests immediately; /api/health
    # returns models_loaded=false until loading finishes.
    import threading
    def _load_models_bg():
        print("[*] Loading ML models in background...")
        models.load()
        print("[*] ML models ready — cameras and uploads will use pre-loaded models")
    threading.Thread(target=_load_models_bg, daemon=True, name="model-loader").start()

    print("[*] Drive Defender API v2.0 started — models loading in background")


@app.on_event("shutdown")
async def shutdown():
    if camera_mgr:
        camera_mgr.stop_all()
    print("[*] Shutdown complete")


# ═══════════════════════════════════════════════════════════════════════════════
# Wrap FastAPI with Socket.IO ASGI app
# ═══════════════════════════════════════════════════════════════════════════════

# The final ASGI application that uvicorn should serve
socket_app = socketio.ASGIApp(sio, app)
