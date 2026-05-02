"""
app.py – FastAPI application entrypoint with Socket.IO integration.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

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
_live_violation_doc_ids = {}
_pending_live_plate_updates = {}
event_loop = None
PLATE_POLL_INTERVAL_SECONDS = 0.25
PLATE_POLL_TIMEOUT_SECONDS = 45.0
LATE_PLATE_UPDATE_TIMEOUT_SECONDS = 25.0


def _extract_camera_id(data) -> str:
    if isinstance(data, dict):
        value = data.get("camera_id", "")
    elif isinstance(data, str):
        value = data
    else:
        value = ""
    return str(value).strip()


@sio.event
async def connect(sid, environ):
    print(f"[WS] Client connected: {sid}")


@sio.event
async def disconnect(sid):
    # Remove from all subscriptions
    for cam_id in list(_camera_subscribers):
        _camera_subscribers[cam_id].discard(sid)
        if not _camera_subscribers[cam_id]:
            del _camera_subscribers[cam_id]
    print(f"[WS] Client disconnected: {sid}")


@sio.event
async def subscribe_camera(sid, data):
    cam_id = _extract_camera_id(data)
    if not cam_id:
        return
    if cam_id not in _camera_subscribers:
        _camera_subscribers[cam_id] = set()
    if sid not in _camera_subscribers[cam_id]:
        _camera_subscribers[cam_id].add(sid)
        print(f"[WS] {sid} subscribed to {cam_id}")


@sio.event
async def unsubscribe_camera(sid, data):
    cam_id = _extract_camera_id(data)
    if not cam_id:
        return
    if cam_id in _camera_subscribers and sid in _camera_subscribers[cam_id]:
        _camera_subscribers[cam_id].discard(sid)
        if not _camera_subscribers[cam_id]:
            del _camera_subscribers[cam_id]
        print(f"[WS] {sid} unsubscribed from {cam_id}")


# ═══════════════════════════════════════════════════════════════════════════════
# Violation + Frame handlers for CameraManager callbacks
# ═══════════════════════════════════════════════════════════════════════════════

async def _save_violation(camera_id: str, rec, jpeg: bytes, plate_text: str):
    """Upload evidence, save the violation, and emit realtime events."""
    user_id = None
    try:
        cam = await cameras_collection.find_one({"camera_id": camera_id})
        if cam:
            user_id = cam.get("user_id")
    except Exception:
        user_id = None

    # â”€â”€ Deduplication guard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    # Skip if the same plate + violation type was already saved in the
    # last 60 seconds for this camera (prevents duplicate records from
    # the SORT tracker assigning multiple track IDs to one physical bike).
    if plate_text and plate_text != "UNDETECTED":
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        existing = await violations_collection.find_one({
            "user_id": user_id,
            "camera_id": camera_id,
            "plate_text": plate_text,
            "violation_type": rec.violation_type,
            "detected_at": {"$gte": cutoff},
        })
        if existing:
            print(f"[DB DEDUP] Skipped: {plate_text} / {rec.violation_type} â€” "
                  f"already logged in last 60s")
            return

    cloud_result = {}
    try:
        loop = asyncio.get_running_loop()
        cloud_result = await loop.run_in_executor(
            None, upload_violation_image, jpeg, camera_id, rec.violation_type
        )
    except Exception as e:
        print(f"[Cloudinary] Upload failed: {e}")

    doc = {
        "user_id": user_id,
        "camera_id": camera_id,
        "track_id": rec.track_id,
        "violation_type": rec.violation_type,
        "plate_text": plate_text,
        "plate_conf": round(rec.plate_conf, 4) if rec.plate_conf else 0.0,
        "frame_number": rec.frame_number,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "evidence_url": cloud_result.get("secure_url"),
        "cloudinary_id": cloud_result.get("public_id"),
    }
    await violations_collection.insert_one(doc)
    print(f"[Violation] Saved: camera={camera_id} type={rec.violation_type} "
          f"plate={plate_text}")

    payload = {
        "camera_id": camera_id,
        "violation_type": rec.violation_type,
        "plate_text": plate_text,
        "evidence_url": cloud_result.get("secure_url"),
        "detected_at": doc["detected_at"],
    }
    await sio.emit("violation", payload)
    await sio.emit("violation_new", payload)


async def _wait_for_plate_and_save(camera_id: str, rec, jpeg: bytes):
    """Poll the live OCR result without blocking the callback thread."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PLATE_POLL_TIMEOUT_SECONDS

    while rec.plate_text is None and loop.time() < deadline:
        await asyncio.sleep(PLATE_POLL_INTERVAL_SECONDS)

    plate_text = rec.plate_text
    if plate_text is not None:
        print(f"[on_violation] Plate resolved: {plate_text}")
    else:
        print("[on_violation] Plate timeout â€” saving UNDETECTED")
        plate_text = "UNDETECTED"

    try:
        await _save_violation(camera_id, rec, jpeg, plate_text)
    except Exception as exc:
        print(f"[on_violation] Failed to save violation: {exc}")


async def _emit_violation_payload_v2(event_name: str, camera_id: str, rec,
                                     plate_text: str, evidence_url: str | None,
                                     detected_at: str):
    payload = {
        "camera_id": camera_id,
        "violation_type": rec.violation_type,
        "plate_text": plate_text,
        "evidence_url": evidence_url,
        "detected_at": detected_at,
    }
    await sio.emit(event_name, payload)


def _build_live_violation_summary(rec, plate_text: str) -> str:
    plate = plate_text or "UNDETECTED"
    return (
        f"{rec.violation_type} | "
        f"track={rec.track_id} | frame={rec.frame_number} | plate={plate}"
    )


def _live_event_key(camera_id: str, rec) -> tuple[str, int, str, int]:
    """Build a stable key per violation event (camera+track+type+frame)."""
    return (
        camera_id,
        int(getattr(rec, "track_id", -1)),
        str(getattr(rec, "violation_type", "")),
        int(getattr(rec, "frame_number", -1)),
    )


async def _save_violation_v2(camera_id: str, rec, jpeg: bytes, plate_text: str):
    user_id = None
    try:
        cam = await cameras_collection.find_one({"camera_id": camera_id})
        if cam:
            user_id = cam.get("user_id")
    except Exception:
        user_id = None

    if plate_text and plate_text not in {"UNDETECTED", "PROCESSING"}:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        existing = await violations_collection.find_one({
            "user_id": user_id,
            "camera_id": camera_id,
            "plate_text": plate_text,
            "violation_type": rec.violation_type,
            "detected_at": {"$gte": cutoff},
        })
        if existing:
            print(f"[DB DEDUP] Skipped: {plate_text} / {rec.violation_type} - already logged in last 60s")
            return None, None, None

    cloud_result = {}
    try:
        loop = asyncio.get_running_loop()
        cloud_result = await loop.run_in_executor(
            None, upload_violation_image, jpeg, camera_id, rec.violation_type
        )
    except Exception as exc:
        print(f"[Cloudinary] Upload failed: {exc}")

    doc = {
        "user_id": user_id,
        "camera_id": camera_id,
        "track_id": rec.track_id,
        "violation_type": rec.violation_type,
        "plate_text": plate_text,
        "plate_number": plate_text,
        "plate_conf": round(rec.plate_conf, 4) if plate_text not in {"PROCESSING", "UNDETECTED"} and rec.plate_conf else 0.0,
        "violation_summary": _build_live_violation_summary(rec, plate_text),
        "frame_number": rec.frame_number,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "evidence_url": cloud_result.get("secure_url"),
        "cloudinary_id": cloud_result.get("public_id"),
    }
    result = await violations_collection.insert_one(doc)
    print(f"[Violation] Saved: camera={camera_id} type={rec.violation_type} plate={plate_text}")

    payload = {
        "id": str(result.inserted_id),
        "camera_id": camera_id,
        "track_id": rec.track_id,
        "violation_type": rec.violation_type,
        "plate_number": plate_text,
        "plate_text": plate_text,
        "plate_conf": doc["plate_conf"],
        "evidence_url": cloud_result.get("secure_url"),
        "detected_at": doc["detected_at"],
    }

    return result.inserted_id, doc, payload


async def _find_processing_violation_id(camera_id: str, rec, event_key=None):
    primary_query = {
        "camera_id": camera_id,
        "track_id": rec.track_id,
        "violation_type": rec.violation_type,
        "frame_number": rec.frame_number,
        "$or": [
            {"plate_text": "PROCESSING"},
            {"plate_number": "PROCESSING"},
        ],
    }

    doc = await violations_collection.find_one(
        primary_query,
        sort=[("detected_at", -1)],
    )

    # Backward-compatible fallback for older rows that may not have frame_number.
    if not doc and event_key is not None:
        fallback_query = {
            "camera_id": camera_id,
            "track_id": rec.track_id,
            "violation_type": rec.violation_type,
            "$or": [
                {"plate_text": "PROCESSING"},
                {"plate_number": "PROCESSING"},
            ],
        }
        doc = await violations_collection.find_one(
            fallback_query,
            sort=[("detected_at", -1)],
        )

    if not doc:
        return None
    return doc.get("_id")


async def _update_saved_violation_plate_v2(saved_id, camera_id: str, rec, emit_event: bool = True):
    plate_text = rec.plate_text or "UNDETECTED"
    summary = _build_live_violation_summary(rec, plate_text)
    print(f"[on_plate_resolved] Summary: {summary}")

    if plate_text not in {"UNDETECTED", "PROCESSING"}:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        duplicate = await violations_collection.find_one(
            {
                "_id": {"$ne": saved_id},
                "camera_id": camera_id,
                "violation_type": rec.violation_type,
                "detected_at": {"$gte": cutoff},
                "$or": [
                    {"plate_text": plate_text},
                    {"plate_number": plate_text},
                ],
            },
            sort=[("detected_at", -1)],
        )
        if duplicate is not None:
            await violations_collection.delete_one({"_id": saved_id})
            print(
                f"[DB DEDUP] Dropped duplicate resolved violation: "
                f"camera={camera_id} type={rec.violation_type} plate={plate_text}"
            )
            return None

    update = {
        "plate_text": plate_text,
        "plate_number": plate_text,
        "plate_conf": round(rec.plate_conf, 4) if plate_text != "UNDETECTED" and rec.plate_conf else 0.0,
        "violation_summary": summary,
    }
    result = await violations_collection.update_one({"_id": saved_id}, {"$set": update})
    if result.matched_count <= 0:
        print(f"[on_plate_resolved] No saved violation found for _id={saved_id}")
        return None

    print(f"[on_plate_resolved] Plate saved: {plate_text}")
    if emit_event:
        await sio.emit("violation_plate_update", {
            "id": str(saved_id),
            "plate_number": plate_text,
            "plate_text": plate_text,
            "plate_conf": update["plate_conf"],
        })
    return update


async def violation_handler(camera_id: str, rec, jpeg: bytes):
    """Called from camera thread when a violation is detected."""
    try:
        key = _live_event_key(camera_id, rec)
        saved_id, _, payload = await _save_violation_v2(camera_id, rec, jpeg, "PROCESSING")
        if saved_id is not None:
            _live_violation_doc_ids[key] = saved_id
            pending_rec = _pending_live_plate_updates.pop(key, None)
            if pending_rec is not None:
                update = await _update_saved_violation_plate_v2(
                    saved_id, camera_id, pending_rec, emit_event=False
                )
                _live_violation_doc_ids.pop(key, None)
                if update:
                    payload.update(update)
            await sio.emit("violation_new", payload)
    except Exception as exc:
        print(f"[on_violation] Failed to save violation: {exc}")


async def plate_resolved_handler(camera_id: str, rec):
    """Called from camera thread when OCR resolves or exhausts retries."""
    key = _live_event_key(camera_id, rec)
    saved_id = _live_violation_doc_ids.get(key)
    if saved_id is None:
        saved_id = await _find_processing_violation_id(camera_id, rec, key)
        if saved_id is None:
            _pending_live_plate_updates[key] = rec
            print(f"[on_plate_resolved] Deferred plate update until violation save completes for {key}")
            return
        print(f"[on_plate_resolved] Recovered saved violation id for {key}")

    try:
        await _update_saved_violation_plate_v2(saved_id, camera_id, rec)
        _live_violation_doc_ids.pop(key, None)
        _pending_live_plate_updates.pop(key, None)
    except Exception as exc:
        print(f"[on_plate_resolved] Failed to update violation: {exc}")
    return

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
    global camera_mgr, event_loop

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
    event_loop = loop
    camera_mgr = CameraManager(
        violation_handler, plate_resolved_handler, frame_handler, loop,
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
