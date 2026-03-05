"""
schemas.py – Pydantic request/response models for all endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class TokenResponse(BaseModel):
    access_token: str
    user: dict

class UserResponse(BaseModel):
    id: str
    email: str
    name: str


# ═══════════════════════════════════════════════════════════════════════════════
# Camera
# ═══════════════════════════════════════════════════════════════════════════════

class CameraCreate(BaseModel):
    camera_id: str
    location: str
    source: str  # int index as string OR rtsp/http URL

class CameraResponse(BaseModel):
    camera_id: str
    location: str
    source: str
    status: str = "stopped"
    created_at: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# Violation
# ═══════════════════════════════════════════════════════════════════════════════

class ViolationResponse(BaseModel):
    id: str
    camera_id: str
    track_id: int
    violation_type: str
    plate_text: Optional[str] = None
    plate_conf: Optional[float] = None
    frame_number: int = 0
    detected_at: str = ""
    evidence_url: Optional[str] = None

class ViolationListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    pages: int


# ═══════════════════════════════════════════════════════════════════════════════
# Upload / Job
# ═══════════════════════════════════════════════════════════════════════════════

class UploadResponse(BaseModel):
    job_id: str

class JobStatusResponse(BaseModel):
    status: str
    progress_pct: float = 0.0
    current_frame: int = 0
    total_frames: int = 0
    current_fps: float = 0.0
    violations: List[dict] = []
    output_video_url: Optional[str] = None
    error_message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════════════

class SummaryResponse(BaseModel):
    total_violations: int = 0
    today_violations: int = 0
    cameras_active: int = 0
    cameras_total: int = 0
    by_type: Dict[str, int] = {}
    recent_violations: List[dict] = []

class TimelineEntry(BaseModel):
    date: str
    count: int

class TimelineResponse(BaseModel):
    data: List[TimelineEntry] = []
