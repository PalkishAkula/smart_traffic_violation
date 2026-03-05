"""
routers/upload.py – Video file upload + background processing + status polling.

- Uses ThreadPoolExecutor for CPU-heavy ML work
- Captures stdout for progress/logs display
- Extracts evidence frames at each violation and uploads plate crop to Cloudinary
- Never stores annotated video — only plate/bike evidence photos
"""

import os
import re
import sys
import io
import uuid
import shutil
import asyncio
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import cv2
import pymongo
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from dotenv import load_dotenv

from routers.auth import get_current_user

load_dotenv()

router = APIRouter(prefix="/api/upload", tags=["upload"])

# In-memory job status store
_jobs: dict = {}

# Thread pool for ML processing (max 2 concurrent jobs)
_executor = ThreadPoolExecutor(max_workers=2)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "violations_db"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(BASE_DIR)
UPLOADS_DIR = os.path.join(BACKEND_DIR, "uploads")
OUTPUTS_DIR = os.path.join(BACKEND_DIR, "outputs")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

ML_PIPELINE_DIR = os.path.abspath(
    os.path.join(BACKEND_DIR, "..", "integrate")
)

# Regex to parse progress from ML pipeline stdout
# Format: "  Frame 00001/1234 [50.0%]  12.3 FPS  | Tracked: ..."
PROGRESS_RE = re.compile(
    r"Frame\s+(\d+)/(\d+)\s+\[(\d+\.?\d*)%\]\s+(\d+\.?\d*)\s+FPS"
)


class StdoutCapture(io.TextIOBase):
    """Capture stdout from pipeline, parse progress, update job status."""

    def __init__(self, job_id: str, original_stdout):
        super().__init__()
        self.job_id = job_id
        self.original_stdout = original_stdout
        self.log_lines = []

    def write(self, text):
        # Always pass through to original stdout
        if self.original_stdout:
            try:
                self.original_stdout.write(text)
            except Exception:
                pass

        if not text:
            return 0

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            self.log_lines.append(line)
            if len(self.log_lines) > 200:
                self.log_lines = self.log_lines[-200:]

            match = PROGRESS_RE.search(line)
            if match and self.job_id in _jobs:
                _jobs[self.job_id]["current_frame"] = int(match.group(1))
                _jobs[self.job_id]["total_frames"] = int(match.group(2))
                _jobs[self.job_id]["progress_pct"] = float(match.group(3))
                _jobs[self.job_id]["current_fps"] = float(match.group(4))

            if self.job_id in _jobs:
                _jobs[self.job_id]["log_lines"] = self.log_lines[-50:]

        return len(text)  # CRITICAL: must return length for TextIOBase

    def flush(self):
        if self.original_stdout:
            try:
                self.original_stdout.flush()
            except Exception:
                pass

    def fileno(self):
        if self.original_stdout:
            return self.original_stdout.fileno()
        raise io.UnsupportedOperation("fileno")

    @property
    def encoding(self):
        return getattr(self.original_stdout, 'encoding', 'utf-8')


def _extract_evidence_frame(video_path: str, frame_number: int) -> bytes | None:
    """
    Open the video, seek to frame_number, encode as JPEG.
    Returns JPEG bytes or None on failure.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        if not ret:
            return None
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()
    finally:
        cap.release()


def _run_job(job_id: str, input_path: str, output_path: str,
             json_path: str, camera_id: str, user_id: str):
    """
    Runs in a background thread via ThreadPoolExecutor.
    ALWAYS sets job status to 'done' or 'error' — never raises.
    """
    original_stdout = sys.stdout
    capture = StdoutCapture(job_id, original_stdout)
    sync_client = None
    violation_docs = []

    try:
        _jobs[job_id]["status"] = "processing"

        # Ensure ML pipeline is importable
        if ML_PIPELINE_DIR not in sys.path:
            sys.path.insert(0, ML_PIPELINE_DIR)

        # Redirect stdout to capture progress/logs
        sys.stdout = capture

        from main import run_pipeline
        from model_registry import models

        memory = run_pipeline(
            video_path=input_path,
            output_path=output_path,
            json_path=json_path,
            model_registry=models,
        )

        # Restore stdout IMMEDIATELY after pipeline returns
        sys.stdout = original_stdout
        print(f"[JOB {job_id}] Pipeline complete, extracting evidence frames...")

        records = memory.all_records()

        # Deduplicate: skip records with same plate_text + violation_type
        seen = set()
        unique_records = []
        for rec in records:
            key = (rec.plate_text, rec.violation_type)
            if rec.plate_text and key in seen:
                continue
            if rec.plate_text:
                seen.add(key)
            unique_records.append(rec)

        # --- Extract evidence frame for each violation & upload to Cloudinary ---
        for rec in unique_records:
            evidence_url = None
            cloudinary_id = None

            # Extract the frame from the ANNOTATED output video so evidence includes boxes
            jpeg_bytes = _extract_evidence_frame(output_path, rec.frame_number)
            if jpeg_bytes:
                try:
                    from cloudinary_service import upload_violation_image
                    cloud_result = upload_violation_image(
                        jpeg_bytes, camera_id or "UPLOAD", rec.violation_type
                    )
                    evidence_url = cloud_result.get("secure_url")
                    cloudinary_id = cloud_result.get("public_id")
                    print(f"[JOB {job_id}] Evidence uploaded for Track-{rec.track_id}")
                except Exception as cld_err:
                    print(f"[JOB {job_id}] Cloudinary upload failed: {cld_err}")

            doc = {
                "user_id": user_id,
                "camera_id": camera_id or "UPLOAD",
                "track_id": rec.track_id,
                "violation_type": rec.violation_type,
                "plate_text": rec.plate_text,
                "plate_conf": round(rec.plate_conf, 4),
                "frame_number": rec.frame_number,
                "plate_retries": getattr(rec, 'plate_retries', 0),
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "evidence_url": evidence_url,
                "cloudinary_id": cloudinary_id,
            }
            violation_docs.append(doc)

        # Insert into MongoDB
        if violation_docs:
            try:
                sync_client = pymongo.MongoClient(MONGODB_URI)
                violations_col = sync_client[DB_NAME]["violations"]
                violations_col.insert_many(violation_docs)
                # CRITICAL: insert_many mutates dicts in-place adding _id: ObjectId
                for doc in violation_docs:
                    doc.pop("_id", None)
                print(f"[JOB {job_id}] Stored {len(violation_docs)} violations in DB")
            except Exception as db_err:
                print(f"[JOB {job_id}] DB insert failed: {db_err}")
                for doc in violation_docs:
                    doc.pop("_id", None)

        # ── MARK DONE ─────────────────────────────────────────────────────
        _jobs[job_id].update({
            "status": "done",
            "progress_pct": 100.0,
            "violations": violation_docs,
            "error": None,
        })
        print(f"[JOB {job_id}] DONE — {len(violation_docs)} violations")

    except Exception as exc:
        sys.stdout = original_stdout
        print(f"[JOB {job_id}] FAILED: {exc}")
        traceback.print_exc()
        _jobs[job_id].update({
            "status": "error",
            "violations": [],
            "error": str(exc),
        })

    finally:
        # Always restore stdout
        sys.stdout = original_stdout
        if sync_client:
            sync_client.close()
        # Safety: if status is still "processing", force to "done"
        if _jobs.get(job_id, {}).get("status") == "processing":
            print(f"[JOB {job_id}] WARNING: still 'processing' in finally — forcing 'done'")
            _jobs[job_id].update({
                "status": "done",
                "progress_pct": 100.0,
                "violations": violation_docs,
                "error": None,
            })
        # Clean up temp input file
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass


@router.post("/video")
async def upload_video_endpoint(
    user=Depends(get_current_user),
    file: UploadFile = File(...),
    camera_id: str = Query(default="UPLOAD"),
):
    """Upload video file and start pipeline in background."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = {".mp4", ".avi", ".mov", ".mkv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {ext}")

    job_id = str(uuid.uuid4())

    # Save file to disk BEFORE handler returns
    input_path = os.path.join(UPLOADS_DIR, f"{job_id}{ext}")
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    output_path = os.path.join(OUTPUTS_DIR, f"{job_id}_output.mp4")
    json_path = os.path.join(OUTPUTS_DIR, f"{job_id}_violations.json")

    # Set initial status BEFORE submitting to executor
    _jobs[job_id] = {
        "status": "processing",
        "progress_pct": 0.0,
        "current_frame": 0,
        "total_frames": 0,
        "current_fps": 0.0,
        "violations": [],
        "error": None,
        "log_lines": [],
        "input_filename": file.filename,
        "user_id": str(user["_id"]),
    }

    # Submit to thread pool
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor,
        _run_job,
        job_id,
        input_path,
        output_path,
        json_path,
        camera_id,
        str(user["_id"]),
    )

    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def get_upload_status(job_id: str, user=Depends(get_current_user)):
    """Poll job status."""
    job = _jobs.get(job_id)
    if job is None:
        return {
            "status": "not_found",
            "violations": [],
            "error": "Job not found",
        }
    if job.get("user_id") != str(user["_id"]):
        raise HTTPException(status_code=404, detail="Job not found")
    return job
