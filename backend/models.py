"""
models.py – Pydantic models for Job and Violation documents.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


class ViolationSummary(BaseModel):
    total: int = 0
    # Dynamic keys for each violation type will be added at runtime


class JobDocument(BaseModel):
    job_id: str
    status: str = "pending"  # pending | processing | done | failed
    progress_pct: float = 0.0
    current_frame: int = 0
    total_frames: int = 0
    current_fps: float = 0.0
    input_filename: str = ""
    input_path: str = ""
    output_path: str = ""
    json_path: str = ""
    error_message: Optional[str] = None
    violation_summary: Dict[str, int] = Field(default_factory=lambda: {"total": 0})
    created_at: str = ""
    finished_at: Optional[str] = None
    log_lines: List[str] = Field(default_factory=list)


class ViolationDocument(BaseModel):
    job_id: str
    track_id: int
    violation_type: str
    plate_text: Optional[str] = None
    plate_conf: float = 0.0
    frame_number: int = 0
    plate_retries: int = 0
    timestamp: float = 0.0
