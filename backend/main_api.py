"""
main_api.py – FastAPI application with all route definitions.
"""

import os
import uuid
import shutil
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import (
    jobs_collection,
    violations_collection,
    create_indexes,
)
from job_manager import start_job

app = FastAPI(title="Drive Defender API", version="1.0.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories for file storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)


@app.on_event("startup")
async def startup():
    await create_indexes()


# ═══════════════════════════════════════════════════════════════════════════════
# POST /upload
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Accept video upload, create job, start pipeline in background."""

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_exts = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Allowed: {', '.join(allowed_exts)}"
        )

    job_id = str(uuid.uuid4())

    # Save uploaded file
    input_path = os.path.join(UPLOADS_DIR, f"{job_id}{ext}")
    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Output paths
    output_path = os.path.join(OUTPUTS_DIR, f"{job_id}_output.mp4")
    json_path = os.path.join(OUTPUTS_DIR, f"{job_id}_violations.json")

    # Create job document in MongoDB
    job_doc = {
        "job_id": job_id,
        "status": "pending",
        "progress_pct": 0.0,
        "current_frame": 0,
        "total_frames": 0,
        "current_fps": 0.0,
        "input_filename": file.filename,
        "input_path": input_path,
        "output_path": output_path,
        "json_path": json_path,
        "error_message": None,
        "violation_summary": {"total": 0},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "log_lines": [],
    }
    await jobs_collection.insert_one(job_doc)

    # Start pipeline in background thread
    start_job(job_id, input_path, output_path, json_path)

    return {"job_id": job_id, "status": "pending"}


# ═══════════════════════════════════════════════════════════════════════════════
# GET /status/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Return job document from MongoDB."""
    job = await jobs_collection.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ═══════════════════════════════════════════════════════════════════════════════
# GET /results/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/results/{job_id}")
async def get_results(job_id: str):
    """Return all violation documents for a job."""
    job = await jobs_collection.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    violations = []
    cursor = violations_collection.find({"job_id": job_id}, {"_id": 0})
    async for doc in cursor:
        violations.append(doc)

    return {"job": job, "violations": violations}


# ═══════════════════════════════════════════════════════════════════════════════
# GET /video/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/video/{job_id}")
async def get_video(job_id: str):
    """Stream the annotated output video file."""
    job = await jobs_collection.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_path = job.get("output_path", "")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output video not found")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"annotated_{job.get('input_filename', 'output.mp4')}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GET /jobs
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/jobs")
async def list_jobs():
    """Return all job documents sorted by created_at descending."""
    jobs = []
    cursor = jobs_collection.find({}, {"_id": 0}).sort("created_at", -1)
    async for doc in cursor:
        jobs.append(doc)
    return jobs


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE /jobs/{job_id}
# ═══════════════════════════════════════════════════════════════════════════════

@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete job + violations from MongoDB, remove video files from disk."""
    job = await jobs_collection.find_one({"job_id": job_id})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove files from disk
    for path_key in ["input_path", "output_path", "json_path"]:
        path = job.get(path_key, "")
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

    # Delete from MongoDB
    await violations_collection.delete_many({"job_id": job_id})
    await jobs_collection.delete_one({"job_id": job_id})

    return {"message": f"Job {job_id} deleted successfully"}
