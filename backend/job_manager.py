"""
job_manager.py – Background job runner + stdout capture + MongoDB updates.

Runs the ML pipeline in a background thread. Captures stdout to parse
progress lines and update the job document in MongoDB in real time.
Uses synchronous pymongo (not Motor) because this runs in a thread,
not in the async event loop.
"""

import sys
import os
import re
import threading
import time
import io
from datetime import datetime, timezone

import pymongo
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "violations_db"

# Path to the ML pipeline code
ML_PIPELINE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "integrate")
)

# Regex to parse progress lines like:
# "  Frame 00060/192  [31.2%]  14.8 FPS  |  ..."
PROGRESS_RE = re.compile(
    r"Frame\s+(\d+)/(\d+)\s+\[(\d+\.?\d*)%\]\s+(\d+\.?\d*)\s+FPS"
)


class StdoutCapture(io.TextIOBase):
    """
    A writable stream that captures every print() from the pipeline,
    updates the MongoDB job document with parsed progress, and also
    stores recent log lines for the frontend to display.
    """

    def __init__(self, job_id: str, original_stdout):
        super().__init__()
        self.job_id = job_id
        self.original_stdout = original_stdout
        self.log_lines = []
        self._buffer = ""

        # Synchronous pymongo client for the background thread
        self._client = pymongo.MongoClient(MONGODB_URI)
        self._jobs = self._client[DB_NAME]["jobs"]

    def write(self, text: str):
        # Also write to the real stdout so we can still see logs in terminal
        if self.original_stdout:
            self.original_stdout.write(text)

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            self.log_lines.append(line)
            # Keep only the last 200 lines
            if len(self.log_lines) > 200:
                self.log_lines = self.log_lines[-200:]

            # Try to parse progress
            match = PROGRESS_RE.search(line)
            if match:
                current_frame = int(match.group(1))
                total_frames = int(match.group(2))
                progress_pct = float(match.group(3))
                current_fps = float(match.group(4))

                self._jobs.update_one(
                    {"job_id": self.job_id},
                    {"$set": {
                        "current_frame": current_frame,
                        "total_frames": total_frames,
                        "progress_pct": progress_pct,
                        "current_fps": current_fps,
                        "log_lines": self.log_lines[-50:],
                    }}
                )
            else:
                # Still update log_lines for non-progress lines
                self._jobs.update_one(
                    {"job_id": self.job_id},
                    {"$set": {"log_lines": self.log_lines[-50:]}}
                )

    def flush(self):
        if self.original_stdout:
            self.original_stdout.flush()

    def close(self):
        if self._client:
            self._client.close()
        super().close()


def _run_pipeline_thread(job_id: str, video_path: str,
                         output_path: str, json_path: str):
    """
    The actual function that runs in the background thread.
    Imports and calls the ML pipeline's run_pipeline().
    """
    # Synchronous pymongo client for this thread
    sync_client = pymongo.MongoClient(MONGODB_URI)
    jobs_col = sync_client[DB_NAME]["jobs"]
    violations_col = sync_client[DB_NAME]["violations"]

    # Redirect stdout to capture pipeline output
    original_stdout = sys.stdout
    capture = StdoutCapture(job_id, original_stdout)

    try:
        # Update status to processing
        jobs_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "processing"}}
        )

        # Add ML pipeline directory to sys.path
        if ML_PIPELINE_DIR not in sys.path:
            sys.path.insert(0, ML_PIPELINE_DIR)

        sys.stdout = capture

        # Import and run the pipeline
        from main import run_pipeline

        memory = run_pipeline(
            video_path=video_path,
            output_path=output_path,
            json_path=json_path,
        )

        # Restore stdout
        sys.stdout = original_stdout

        # Get all violation records
        records = memory.all_records()

        # Build violation summary dynamically
        summary = {"total": len(records)}
        for rec in records:
            vtype = rec.violation_type
            summary[vtype] = summary.get(vtype, 0) + 1

        # Insert violation documents into MongoDB
        if records:
            violation_docs = []
            for rec in records:
                violation_docs.append({
                    "job_id": job_id,
                    "track_id": rec.track_id,
                    "violation_type": rec.violation_type,
                    "plate_text": rec.plate_text,
                    "plate_conf": round(rec.plate_conf, 4),
                    "frame_number": rec.frame_number,
                    "plate_retries": rec.plate_retries,
                    "timestamp": rec.timestamp,
                })
            violations_col.insert_many(violation_docs)

        # Update job as done
        jobs_col.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "done",
                "progress_pct": 100.0,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "violation_summary": summary,
                "log_lines": capture.log_lines[-50:],
            }}
        )

    except Exception as e:
        sys.stdout = original_stdout
        error_msg = str(e)
        print(f"[ERROR] Pipeline failed for job {job_id}: {error_msg}")

        jobs_col.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error_message": error_msg,
                "log_lines": capture.log_lines[-50:],
            }}
        )

    finally:
        sys.stdout = original_stdout
        capture.close()
        sync_client.close()


def start_job(job_id: str, video_path: str,
              output_path: str, json_path: str):
    """
    Launch the pipeline in a daemon background thread.
    Returns immediately so the API handler is not blocked.
    """
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(job_id, video_path, output_path, json_path),
        daemon=True,
    )
    thread.start()
    return thread
