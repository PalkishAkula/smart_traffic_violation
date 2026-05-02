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
import base64
import uuid
import shutil
import asyncio
import traceback
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
import pymongo
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from dotenv import load_dotenv

from .auth import get_current_user

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
if ML_PIPELINE_DIR not in sys.path:
    sys.path.insert(0, ML_PIPELINE_DIR)

_ml_module_cache: dict[str, Any] = {}


def _ml_module(name: str) -> Any:
    """Import modules from integrate/ without static unresolved-import noise."""
    if ML_PIPELINE_DIR not in sys.path:
        sys.path.insert(0, ML_PIPELINE_DIR)
    if name not in _ml_module_cache:
        _ml_module_cache[name] = importlib.import_module(name)
    return _ml_module_cache[name]


def _backend_module(name: str) -> Any:
    """Import backend sibling modules when this router is loaded as a package."""
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
    return importlib.import_module(name)

# Single-image inference settings (kept consistent with integrate/main.py)
CONF_MOTORCYCLE = 0.40
CONF_PERSON = 0.25
CONF_HELMET = 0.30
CONF_PLATE = 0.10
INFER_SIZE = 640
ASSOC_IOU_THRESH = 0.10
PERSON_BIKE_IOP_THRESH = 0.12
PLATE_SEARCH_DOWN_FRAC = 0.40
LIVE_PLATE_CROP_SCALE = 3.0

V_NO_HELMET = "NO_HELMET"
V_TRIPLE = "TRIPLE_RIDING"
V_CO_RIDING = "CO_RIDING_NO_HELMET"

CLR_BIKE = (0, 255, 0)
CLR_VIOL = (0, 50, 255)
CLR_HELMET = (0, 255, 255)
CLR_NO_HELM = (0, 0, 255)
CLR_PLATE = (255, 0, 0)
CLR_PERSON = (255, 128, 0)

# Regex to parse progress from ML pipeline stdout.
# Accept both "fps" and "FPS" so progress keeps updating regardless of case.
PROGRESS_RE = re.compile(
    r"Frame\s+(\d+)/(\d+)\s+\[(\d+\.?\d*)%\]\s+(\d+\.?\d*)\s+fps",
    re.IGNORECASE,
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


def _persons_on_bike(persons: list, bike_box: tuple) -> list:
    utils = _ml_module("utils")
    return [
        p for p in persons
        if (
            utils.get_iou(p[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
            or utils.get_iop(p[:4], bike_box[:4]) >= PERSON_BIKE_IOP_THRESH
            or utils.is_rider_on_bike(p[:4], bike_box)
        )
    ]


def _dets_on_bike(dets: list, bike_box: tuple) -> list:
    utils = _ml_module("utils")
    return [
        d for d in dets
        if (
            utils.get_iou(d[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
            or utils.is_rider_on_bike(d[:4], bike_box)
        )
    ]


def _plate_search_box(
    bike_box: tuple,
    persons_on: list,
    helmets_on: list,
    no_helmets_on: list,
    frame_h: int,
) -> tuple:
    all_boxes = [bike_box[:4]] + [d[:4] for d in persons_on + helmets_on + no_helmets_on]
    ux1 = int(min(b[0] for b in all_boxes))
    uy1 = int(min(b[1] for b in all_boxes))
    ux2 = int(max(b[2] for b in all_boxes))
    uy2 = int(max(b[3] for b in all_boxes))
    bike_h = bike_box[3] - bike_box[1]
    ext_y2 = min(frame_h, int(uy2 + bike_h * PLATE_SEARCH_DOWN_FRAC))
    return (ux1, uy1, ux2, ext_y2)


def _assign_exclusive(
    persons: list,
    helmets: list,
    no_helmets: list,
    bike_boxes: list,
    plates: list | None = None,
):
    """Assign each detection to the single most likely bike."""
    utils = _ml_module("utils")

    n = len(bike_boxes)
    ap = {i: [] for i in range(n)}
    ah = {i: [] for i in range(n)}
    anh = {i: [] for i in range(n)}
    apl = {i: [] for i in range(n)}

    if n == 0:
        return ap, ah, anh, apl

    def _best_bike(det, score_fn):
        scores = [score_fn(det, bike) for bike in bike_boxes]
        best_i = max(range(n), key=lambda i: scores[i])
        return best_i if scores[best_i] > 0.0 else -1

    def _person_score(person, bike):
        score = max(utils.get_iou(person[:4], bike[:4]), utils.get_iop(person[:4], bike[:4]))
        return score if score >= PERSON_BIKE_IOP_THRESH else 0.0

    def _det_score(det, bike):
        iou = utils.get_iou(det[:4], bike[:4])
        if iou >= ASSOC_IOU_THRESH:
            return iou
        if utils.is_rider_on_bike(det[:4], bike):
            dx = (det[0] + det[2]) / 2.0
            dy = (det[1] + det[3]) / 2.0
            bx_c = (bike[0] + bike[2]) / 2.0
            by_c = (bike[1] + bike[3]) / 2.0
            bike_w = max(1.0, bike[2] - bike[0])
            bike_h = max(1.0, bike[3] - bike[1])
            norm_dist = (
                ((dx - bx_c) ** 2) / (bike_w ** 2)
                + ((dy - by_c) ** 2) / (bike_h ** 2)
            ) ** 0.5
            return max(1e-4, ASSOC_IOU_THRESH * max(0.0, 1.0 - norm_dist))
        return 0.0

    def _plate_score(plate, bike):
        iou = utils.get_iou(plate[:4], bike[:4])
        if iou >= ASSOC_IOU_THRESH:
            return iou
        px_c = (plate[0] + plate[2]) / 2.0
        py_c = (plate[1] + plate[3]) / 2.0
        bx1, by1, bx2, by2 = bike[:4]
        bike_w = max(1.0, bx2 - bx1)
        bike_h = max(1.0, by2 - by1)
        x_margin = bike_w * 0.15
        if not (bx1 - x_margin <= px_c <= bx2 + x_margin):
            return 0.0
        if py_c < by1 + bike_h * 0.40:
            return 0.0
        y_dist = max(0.0, py_c - by2)
        return max(
            1e-4,
            ASSOC_IOU_THRESH * max(0.0, 1.0 - y_dist / (bike_h * 0.5 + 1.0)),
        )

    for person in persons:
        i = _best_bike(person, _person_score)
        if i >= 0:
            ap[i].append(person)
    for helmet in helmets:
        i = _best_bike(helmet, _det_score)
        if i >= 0:
            ah[i].append(helmet)
    for no_helmet in no_helmets:
        i = _best_bike(no_helmet, _det_score)
        if i >= 0:
            anh[i].append(no_helmet)
    for plate in plates or []:
        i = _best_bike(plate, _plate_score)
        if i >= 0:
            apl[i].append(plate)

    return ap, ah, anh, apl


def _to_box_4(box: tuple) -> list:
    return [int(box[0]), int(box[1]), int(box[2]), int(box[3])]


def _to_box_5(box: tuple) -> list:
    return [int(box[0]), int(box[1]), int(box[2]), int(box[3]), round(float(box[4]), 4)]


def _draw_box(img: np.ndarray, box: tuple, color: tuple, thick: int = 2):
    cv2.rectangle(
        img,
        (int(box[0]), int(box[1])),
        (int(box[2]), int(box[3])),
        color,
        thick,
    )


def _draw_text(img: np.ndarray, text: str, x: int, y: int, color: tuple):
    cv2.putText(
        img,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
        cv2.LINE_AA,
    )


def _violation_label(vtype: str) -> str:
    if vtype == V_NO_HELMET:
        return "NO HELMET"
    if vtype == V_TRIPLE:
        return "TRIPLE RIDING"
    return "CO-RIDER NO HELMET"


def _analyze_image_sync(image_bytes: bytes) -> dict:
    models = _backend_module("model_registry").models
    utils = _ml_module("utils")
    helmet_logic = _ml_module("helmet_logic")
    triple_riding = _ml_module("triple_riding")
    co_riding = _ml_module("co_riding")
    ocr_numberplate = _ml_module("ocr_numberplate")
    tracker_module = _ml_module("tracker")

    if not models.is_loaded:
        raise RuntimeError("MODELS_NOT_READY")

    np_buf = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(np_buf, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid image file")

    src_h, src_w = frame.shape[:2]

    coco_boxes = models.coco_model(frame, imgsz=INFER_SIZE, verbose=False)[0].boxes
    helmet_boxes = models.helmet_model(frame, imgsz=INFER_SIZE, verbose=False)[0].boxes
    plate_boxes = models.plate_model(frame, verbose=False)[0].boxes

    bikes = []
    persons = []
    for b in coco_boxes:
        cls = int(b.cls[0])
        conf = float(b.conf[0])
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        det = (x1, y1, x2, y2, conf)
        if cls == 3 and conf >= CONF_MOTORCYCLE:
            bikes.append(det)
        elif cls == 0 and conf >= CONF_PERSON:
            persons.append(det)

    helmets = []
    no_helmets = []
    for b in helmet_boxes:
        cls = int(b.cls[0])
        conf = float(b.conf[0])
        if conf < CONF_HELMET:
            continue
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        scaled = (x1, y1, x2, y2, conf)
        if cls == 1:
            helmets.append(scaled)
        elif cls == 2:
            no_helmets.append(scaled)

    plates = []
    for b in plate_boxes:
        conf = float(b.conf[0])
        if conf < CONF_PLATE:
            continue
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        plates.append((x1, y1, x2, y2, conf))

    def _clip_box(box4: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        x1, y1, x2, y2 = map(int, box4)
        x1 = max(0, min(src_w - 1, x1))
        y1 = max(0, min(src_h - 1, y1))
        x2 = max(0, min(src_w - 1, x2))
        y2 = max(0, min(src_h - 1, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2)

    # Mirror video pipeline behavior: use SORT tracker association with NMS.
    # We run 2 association rounds on the same image so tracks can become confirmed.
    tracker = tracker_module.SOTTracker(max_age=10, iou_thresh=0.25)
    detections = [([b[0], b[1], b[2], b[3]], b[4]) for b in bikes]
    tracked = []
    if detections:
        for _ in range(2):
            tracker.predict_all()
            tracked = tracker.associate(detections)

    bike_candidates = []
    if tracked:
        for trk in tracked:
            raw = trk.get_ltrb().astype(int).tolist()
            clipped = _clip_box((raw[0], raw[1], raw[2], raw[3]))
            if clipped is None:
                continue
            bike_candidates.append(
                {
                    "track_id": int(trk.track_id),
                    "bike": (clipped[0], clipped[1], clipped[2], clipped[3], float(trk.conf)),
                }
            )
    else:
        for idx, b in enumerate(bikes, start=1):
            clipped = _clip_box((b[0], b[1], b[2], b[3]))
            if clipped is None:
                continue
            bike_candidates.append(
                {
                    "track_id": idx,
                    "bike": (clipped[0], clipped[1], clipped[2], clipped[3], float(b[4])),
                }
            )

    bike_boxes = [candidate["bike"] for candidate in bike_candidates]
    assigned_persons, assigned_helmets, assigned_no_helmets, assigned_plates = (
        _assign_exclusive(persons, helmets, no_helmets, bike_boxes, plates=plates)
    )

    violations = []
    bikes_out = []
    ocr_success = 0
    all_plate_boxes = list(plates)

    for bike_idx, candidate in enumerate(bike_candidates):
        bike_id = int(candidate["track_id"])
        bike = candidate["bike"]
        bike_box = bike[:4]

        persons_on = assigned_persons[bike_idx]
        helmets_on = assigned_helmets[bike_idx]
        no_helmets_on = assigned_no_helmets[bike_idx]
        plates_on = list(assigned_plates[bike_idx])
        sbox = _plate_search_box(bike, persons_on, helmets_on, no_helmets_on, src_h)

        # Extra plate pass in bike search region to help with small/blurred plates.
        sx1 = max(0, min(src_w, int(sbox[0])))
        sy1 = max(0, min(src_h, int(sbox[1])))
        sx2 = max(0, min(src_w, int(sbox[2])))
        sy2 = max(0, min(src_h, int(sbox[3])))
        if sx2 > sx1 and sy2 > sy1:
            pcrop = frame[sy1:sy2, sx1:sx2]
            if pcrop.size > 0:
                ch, cw = pcrop.shape[:2]
                up = cv2.resize(
                    pcrop,
                    (int(cw * LIVE_PLATE_CROP_SCALE), int(ch * LIVE_PLATE_CROP_SCALE)),
                    interpolation=cv2.INTER_LANCZOS4,
                )
                for pb in models.plate_model(up, verbose=False)[0].boxes:
                    pconf = float(pb.conf[0])
                    if pconf < CONF_PLATE:
                        continue
                    px1, py1, px2, py2 = map(int, pb.xyxy[0])
                    candidate = (
                        int(px1 / LIVE_PLATE_CROP_SCALE) + sx1,
                        int(py1 / LIVE_PLATE_CROP_SCALE) + sy1,
                        int(px2 / LIVE_PLATE_CROP_SCALE) + sx1,
                        int(py2 / LIVE_PLATE_CROP_SCALE) + sy1,
                        pconf,
                    )
                    if not any(utils.get_iou(candidate[:4], p[:4]) > 0.40 for p in all_plate_boxes):
                        all_plate_boxes.append(candidate)
                        plates_on.append(candidate)

        _, person_no_helmets = utils.assign_head_detections(
            persons_on, helmets_on, no_helmets_on
        )
        if len(persons_on) >= 2:
            bike_cx = (bike_box[0] + bike_box[2]) / 2.0
            di = min(
                range(len(persons_on)),
                key=lambda i: abs((persons_on[i][0] + persons_on[i][2]) / 2.0 - bike_cx),
            )
            coi = [i for i in range(len(persons_on)) if i != di]
            dnh = person_no_helmets[di]
        elif len(persons_on) == 1:
            di = 0
            coi = []
            dnh = person_no_helmets[0]
        else:
            di = None
            coi = []
            dnh = []

        bike_violations = []

        tv, _ = triple_riding.check_triple_riding(persons_on, helmets_on, no_helmets_on)
        if tv:
            bike_violations.append(V_TRIPLE)

        if tv:
            cv = any(person_no_helmets[i] for i in coi) if coi else len(no_helmets_on) >= 1
        else:
            cv, _ = co_riding.check_co_riding(persons_on, helmets_on, no_helmets_on, bike_box)
        if cv:
            bike_violations.append(V_CO_RIDING)

        # NO_HELMET is only for the rider/driver. Co-rider helmet failures
        # stay under CO_RIDING_NO_HELMET, including triple-riding cases.
        if di is None:
            nh_v = False
        else:
            nh_v, _ = helmet_logic.check_helmet_violation(dnh, helmets_on)
        if nh_v:
            bike_violations.append(V_NO_HELMET)

        plate_text, plate_conf, plate_box = ocr_numberplate.get_plate_for_bike(
            plates_on,
            bike_box,
            frame,
            models.ocr_reader,
            None,
            search_box=sbox,
        )
        if plate_text:
            ocr_success += 1

        bike_result = {
            "track_id": bike_id,
            "bike_box": _to_box_5(bike),
            "search_box": _to_box_4(sbox),
            "person_count": len(persons_on),
            "helmet_count": len(helmets_on),
            "no_helmet_count": len(no_helmets_on),
            "violation_types": bike_violations,
            "plate_text": plate_text,
            "plate_conf": round(float(plate_conf), 4) if plate_conf else 0.0,
            "plate_box": _to_box_4(plate_box) if plate_box else None,
            "boxes": {
                "persons": [_to_box_5(p) for p in persons_on],
                "helmets": [_to_box_5(h) for h in helmets_on],
                "no_helmets": [_to_box_5(nh) for nh in no_helmets_on],
            },
        }
        bikes_out.append(bike_result)

        for vtype in bike_violations:
            violations.append(
                {
                    "track_id": bike_id,
                    "violation_type": vtype,
                    "plate_text": plate_text,
                    "plate_conf": round(float(plate_conf), 4) if plate_conf else 0.0,
                    "bike_box": _to_box_4(bike[:4]),
                    "plate_box": _to_box_4(plate_box) if plate_box else None,
                }
            )

    annotated = frame.copy()
    for p in persons:
        _draw_box(annotated, p, CLR_PERSON, 1)
    for h in helmets:
        _draw_box(annotated, h, CLR_HELMET, 1)
    for nh in no_helmets:
        _draw_box(annotated, nh, CLR_NO_HELM, 2)
        _draw_text(annotated, f"No Helmet {nh[4]:.2f}", int(nh[0]), int(max(18, nh[1] - 8)), CLR_NO_HELM)
    for pl in all_plate_boxes:
        _draw_box(annotated, pl, CLR_PLATE, 1)

    for bike in bikes_out:
        bx1, by1, bx2, by2 = bike["bike_box"][:4]
        has_violation = bool(bike["violation_types"])
        bike_color = CLR_VIOL if has_violation else CLR_BIKE
        _draw_box(annotated, (bx1, by1, bx2, by2), bike_color, 3 if has_violation else 2)
        _draw_text(annotated, f"Bike#{bike['track_id']}", bx1, max(20, by1 - 10), bike_color)

        line_y = max(22, by1 - 32)
        for vtype in bike["violation_types"]:
            _draw_text(annotated, _violation_label(vtype), bx1, line_y, CLR_NO_HELM)
            line_y -= 22

        if bike.get("plate_box"):
            _draw_box(annotated, tuple(bike["plate_box"]), CLR_PLATE, 2)

        plate_text = bike.get("plate_text") or "UNDETECTED"
        _draw_text(annotated, f"Plate: {plate_text}", bx1, min(src_h - 10, by2 + 22), CLR_PLATE)

    ok, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise RuntimeError("Failed to encode annotated image")

    return {
        "summary": {
            "total_bikes": len(bike_candidates),
            "total_violations": len(violations),
            "total_ocr_reads": ocr_success,
            "total_plate_boxes": len(all_plate_boxes),
        },
        "violations": violations,
        "bikes": bikes_out,
        "annotated_image_b64": base64.b64encode(jpg.tobytes()).decode("ascii"),
    }


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

        main_module = importlib.import_module("main")
        main_module = importlib.reload(main_module)
        run_pipeline = main_module.run_pipeline
        models = _backend_module("model_registry").models

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
                    upload_violation_image = _backend_module(
                        "cloudinary_service"
                    ).upload_violation_image
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


@router.post("/image")
async def upload_image_endpoint(
    user=Depends(get_current_user),
    file: UploadFile = File(...),
):
    """Upload one image and return annotated detections + OCR + violations."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    ext = os.path.splitext(file.filename)[1].lower()
    content_type = file.content_type or ""
    if ext not in allowed and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {ext}")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _analyze_image_sync, image_bytes)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except RuntimeError as err:
        if str(err) == "MODELS_NOT_READY":
            raise HTTPException(
                status_code=503,
                detail="Models are still loading. Try again in a few seconds.",
            )
        raise HTTPException(status_code=500, detail=str(err))
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Image processing failed: {err}")

    result["filename"] = file.filename
    return result


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
