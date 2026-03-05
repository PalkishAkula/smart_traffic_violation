"""
main.py – Motorcycle Helmet & Riding Violation Detection System
===============================================================
Optimised video pipeline: SORT tracker + frame-skipping + extended plate search.

Violation types detected
------------------------
  1. NO_HELMET            – Any rider on a motorcycle is not wearing a helmet.
  2. TRIPLE_RIDING        – 3+ persons detected on one motorcycle.
  3. CO_RIDING_NO_HELMET  – 2 persons on bike; the pillion has no helmet.

Two operating modes
-------------------
  1. FILE MODE   – run_pipeline(video_path, output_path, json_path, ...)
       Process a recorded video file; write annotated output + JSON summary.
       API: unchanged from previous version.

  2. LIVE MODE   – run_pipeline_live(camera_source, camera_id, stop_event,
                                     violation_callback, frame_callback, ...)
       Process a live camera stream (USB / IP / RTSP) in a background thread.
       Stops when stop_event is set.
       Calls violation_callback(record, frame_crop) on each new violation.
       Calls frame_callback(jpeg_bytes) on every annotated frame for streaming.

Speed Optimisations
-------------------
  1. FRAME SKIPPING  – YOLO inference runs only on every Nth frame (default N=4).
  2. LOWER INFERENCE RESOLUTION  – 416×256 instead of 640×384.
  3. OCR runs only once per (track_id, violation_type) + limited retries.
  4. verbose=False on YOLO suppresses per-frame print overhead.

Plate Detection Improvements
-----------------------------
  • Extended search box catches rear plates below the motorcycle box.
  • OCR retry loop converts UNDETECTED → real plate numbers over time.
"""

import cv2
import time
import os
import json
import threading
from typing import Callable, Optional

import numpy as np
from ultralytics import YOLO
import easyocr

from utils           import is_rider_on_bike, get_iou
from helmet_logic    import check_helmet_violation
from triple_riding   import check_triple_riding
from co_riding       import check_co_riding
from ocr_numberplate import get_plate_for_bike
from tracker         import SOTTracker, ViolationMemory, ViolationRecord


# ══════════════════════════════════════════════════════════════════════════════
# ▸▸  UPDATE THESE PATHS / SETTINGS  ◂◂
# ══════════════════════════════════════════════════════════════════════════════

MODEL_COCO   = "yolov8n.pt"
MODEL_HELMET = r"D:\Final year project\user interface\models\helmet\best.pt"
MODEL_PLATE  = r"D:\Final year project\user interface\models\license\best.pt"

VIDEO_PATH   = r"D:\Final year project\user interface\singletest11.mp4"
OUTPUT_VIDEO = r"D:\Final year project\user interface\output.mp4"
OUTPUT_JSON  = r"D:\Final year project\user interface\violations.json"

# ── Detection confidence thresholds ──────────────────────────────────────────
CONF_MOTORCYCLE = 0.40
CONF_PERSON     = 0.30
CONF_HELMET     = 0.35
CONF_PLATE      = 0.10

# ── Frame skipping ────────────────────────────────────────────────────────────
PROCESS_EVERY_N_FRAMES = 2

# ── Inference resolution ──────────────────────────────────────────────────────
INFER_W, INFER_H = 416, 256

# ── Plate search box extension ────────────────────────────────────────────────
PLATE_SEARCH_DOWN_FRAC = 0.40

# ── Plate OCR retry cadence ───────────────────────────────────────────────────
PLATE_RETRY_FRAME_GAP = 16

# ── Spatial association threshold ────────────────────────────────────────────
ASSOC_IOU_THRESH = 0.10

# ── State code(s) for OCR disambiguation ─────────────────────────────────────
PREFERRED_STATES = None

# ── Live stream settings ──────────────────────────────────────────────────────
# JPEG quality for frame streaming (0-100). Lower = smaller, faster over socket.
LIVE_STREAM_JPEG_QUALITY = 80
# How many frames to skip between JPEG emissions to limit bandwidth.
# 1 = every annotated frame is emitted; 2 = every other frame, etc.
LIVE_STREAM_EMIT_EVERY   = 1

LIVE_PLATE_CROP_SCALE = 2.0


# ══════════════════════════════════════════════════════════════════════════════
# Violation type constants
# ══════════════════════════════════════════════════════════════════════════════

V_NO_HELMET = 'NO_HELMET'
V_TRIPLE    = 'TRIPLE_RIDING'
V_CO_RIDING = 'CO_RIDING_NO_HELMET'


# ══════════════════════════════════════════════════════════════════════════════
# Colour palette (BGR)
# ══════════════════════════════════════════════════════════════════════════════

CLR_BIKE    = (0,   255,   0)
CLR_VIOL    = (0,    50, 255)
CLR_HELMET  = (0,   255, 255)
CLR_NO_HELM = (0,     0, 255)
CLR_PLATE   = (255,   0,   0)
CLR_PERSON  = (255, 128,   0)
CLR_PILLION = (180,   0, 255)


# ══════════════════════════════════════════════════════════════════════════════
# Detection association helpers
# ══════════════════════════════════════════════════════════════════════════════

def _persons_on_bike(persons: list, bike_box: tuple) -> list:
    return [p for p in persons if is_rider_on_bike(p[:4], bike_box)]


def _detections_on_bike(dets: list, bike_box: tuple) -> list:
    return [d for d in dets
            if (get_iou(d[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
                or is_rider_on_bike(d[:4], bike_box))]


# ══════════════════════════════════════════════════════════════════════════════
# Extended plate search box
# ══════════════════════════════════════════════════════════════════════════════

def _build_plate_search_box(bike_box, persons_on, helmets_on, no_helmets_on, frame_h):
    bx1, by1, bx2, by2 = bike_box[:4]
    bike_h = by2 - by1
    all_boxes = [bike_box[:4]]
    for det in (persons_on + helmets_on + no_helmets_on):
        all_boxes.append(det[:4])
    ux1 = int(min(b[0] for b in all_boxes))
    uy1 = int(min(b[1] for b in all_boxes))
    ux2 = int(max(b[2] for b in all_boxes))
    uy2 = int(max(b[3] for b in all_boxes))
    extended_y2 = min(frame_h, int(uy2 + bike_h * PLATE_SEARCH_DOWN_FRAC))
    return (ux1, uy1, ux2, extended_y2)


# ══════════════════════════════════════════════════════════════════════════════
# Drawing helpers
# ══════════════════════════════════════════════════════════════════════════════

def _txt(img, text, pt, colour, scale=0.55, thick=2):
    cv2.putText(img, text, pt,
                cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thick, cv2.LINE_AA)


def _box(img, b, colour, thick=2):
    cv2.rectangle(img,
                  (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                  colour, thick)


def draw_frame(frame, tracked, persons, helmets, no_helmets, plates, memory):
    active_ids = {t.track_id for t in tracked}
    rec_lookup = {(r.track_id, r.violation_type): r
                  for r in memory.all_records()
                  if r.track_id in active_ids}

    for h  in helmets:    _box(frame, h, CLR_HELMET, 1)
    for nh in no_helmets:
        _box(frame, nh, CLR_NO_HELM, 2)
        _txt(frame, f"No Helmet {nh[4]:.2f}",
             (int(nh[0]), int(nh[1]) - 6), CLR_NO_HELM, scale=0.45)
    for p  in persons:    _box(frame, p, CLR_PERSON, 1)
    for pl in plates:     _box(frame, pl, CLR_PLATE, 1)

    for trk in tracked:
        lb  = trk.get_ltrb().astype(int)
        tid = trk.track_id
        viols = [v for (tid2, _), v in rec_lookup.items() if tid2 == tid]

        bike_col = CLR_VIOL if viols else CLR_BIKE
        _box(frame, lb, bike_col, 3 if viols else 2)
        _txt(frame, f"Bike#{tid}", (lb[0], lb[1] - 10), bike_col, scale=0.5)

        y_top = lb[1] - 28
        for rec in viols:
            if rec.violation_type == V_NO_HELMET:
                label, col = "!! NO HELMET",          CLR_NO_HELM
            elif rec.violation_type == V_TRIPLE:
                label, col = "!! TRIPLE RIDING",      CLR_PERSON
            else:
                label, col = "!! CO-RIDER NO HELMET", CLR_PILLION
            _txt(frame, label, (lb[0], y_top), col, scale=0.60, thick=2)
            y_top -= 22
            plate_str = rec.plate_text or "PLATE UNREAD"
            _txt(frame, f"Plate: {plate_str}",
                 (lb[0], lb[3] + 20), CLR_PLATE, scale=0.55)

    return frame


# ══════════════════════════════════════════════════════════════════════════════
# Evidence crop helper  (NEW – used by both file & live pipelines)
# ══════════════════════════════════════════════════════════════════════════════

def capture_violation_crop(frame: np.ndarray, bike_box: tuple,
                            pad_frac: float = 0.25) -> np.ndarray:
    """
    Return a padded crop of the motorcycle area as evidence for a violation.

    Parameters
    ----------
    frame    : full BGR frame
    bike_box : (x1, y1, x2, y2) of the motorcycle
    pad_frac : proportional padding around the box

    Returns
    -------
    crop : np.ndarray  – BGR image crop (may be a full frame if box is invalid)
    """
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bike_box[:4])
    bw, bh = x2 - x1, y2 - y1
    px = int(bw * pad_frac)
    py = int(bh * pad_frac)
    cx1 = max(0, x1 - px)
    cy1 = max(0, y1 - py)
    cx2 = min(w, x2 + px)
    cy2 = min(h, y2 + py)
    crop = frame[cy1:cy2, cx1:cx2]
    return crop if crop.size > 0 else frame.copy()


def encode_jpeg(img: np.ndarray, quality: int = LIVE_STREAM_JPEG_QUALITY) -> bytes:
    """Encode a BGR numpy array as a JPEG byte string."""
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return bytes(buf) if ok else b''


# ══════════════════════════════════════════════════════════════════════════════
# Console / export helpers
# ══════════════════════════════════════════════════════════════════════════════

def print_summary(memory: ViolationMemory):
    print("\n" + "═" * 66)
    print("  VIOLATION SUMMARY")
    print("═" * 66)
    print(memory.summary())
    print("═" * 66 + "\n")


def export_json(memory: ViolationMemory, path: str):
    data = [{"track_id":       rec.track_id,
             "violation_type": rec.violation_type,
             "plate_text":     rec.plate_text,
             "plate_conf":     round(rec.plate_conf, 4),
             "frame_number":   rec.frame_number,
             "plate_retries":  rec.plate_retries,
             "timestamp":      rec.timestamp}
            for rec in memory.all_records()]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[*] Violations JSON saved → {path}")


# ══════════════════════════════════════════════════════════════════════════════
# Shared per-frame processing logic  (used by BOTH pipelines)
# ══════════════════════════════════════════════════════════════════════════════

def _process_inference_frame(frame, coco_model, helmet_model, plate_model,
                              reader, tracker, memory, frame_num, src_w, src_h,
                              violation_callback=None,
                              live_mode: bool = False):
    """
    Run YOLO inference + violation detection on a single frame.

    Parameters
    ----------
    violation_callback : callable(record: ViolationRecord, bike_box: tuple) | None
        Called immediately when a NEW violation is confirmed.
        bike_box is the (x1,y1,x2,y2) motorcycle box in full-frame coords.
        In live mode, the caller should crop evidence from the *annotated*
        frame after draw_frame() so evidence includes bounding boxes.
        Pass None in file-mode (violations are just stored in memory).

    Returns
    -------
    tracked        : confirmed KalmanTracks
    last_persons   : parsed person detections (full-frame coords)
    last_helmets   : parsed helmet detections
    last_no_helmets: parsed no-helmet detections
    last_plates    : parsed plate detections
    """
    det_frame  = cv2.resize(frame, (INFER_W, INFER_H))
    coco_res   = coco_model(det_frame,  verbose=False)[0]
    helmet_res = helmet_model(det_frame, verbose=False)[0]
    plate_res  = plate_model(frame,      verbose=False)[0]   # full-res for plate

    sx = src_w / INFER_W
    sy = src_h / INFER_H

    def scale(box):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        return (int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy),
                float(box.conf[0]))

    motorcycles, persons = [], []
    for box in coco_res.boxes:
        cls = int(box.cls[0]); conf = float(box.conf[0])
        if cls == 3 and conf >= CONF_MOTORCYCLE:
            motorcycles.append(scale(box))
        elif cls == 0 and conf >= CONF_PERSON:
            persons.append(scale(box))

    helmets, no_helmets = [], []
    for box in helmet_res.boxes:
        cls = int(box.cls[0]); conf = float(box.conf[0])
        if conf < CONF_HELMET: continue
        entry = scale(box)
        if cls == 1:   helmets.append(entry)
        elif cls == 2: no_helmets.append(entry)

    plates = []
    for box in plate_res.boxes:
        conf = float(box.conf[0])
        if conf >= CONF_PLATE:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            plates.append((x1, y1, x2, y2, conf))

    moto_dets = [([m[0],m[1],m[2],m[3]], m[4]) for m in motorcycles]
    tracked   = tracker.associate(moto_dets)

    for trk in tracked:
        bike_box   = tuple(trk.get_ltrb().astype(int))
        tid        = trk.track_id
        persons_on    = _persons_on_bike(persons, bike_box)
        helmets_on    = _detections_on_bike(helmets,    bike_box)
        no_helmets_on = _detections_on_bike(no_helmets, bike_box)
        search_box    = _build_plate_search_box(
            bike_box, persons_on, helmets_on, no_helmets_on, src_h)

        if live_mode:
            sx1, sy1, sx2, sy2 = map(int, search_box[:4])
            h, w = frame.shape[:2]
            sx1, sy1 = max(0, sx1), max(0, sy1)
            sx2, sy2 = min(w, sx2), min(h, sy2)
            crop = frame[sy1:sy2, sx1:sx2]
            if crop.size > 0:
                cw, ch = crop.shape[1], crop.shape[0]
                up = cv2.resize(
                    crop,
                    (int(cw * LIVE_PLATE_CROP_SCALE), int(ch * LIVE_PLATE_CROP_SCALE)),
                    interpolation=cv2.INTER_CUBIC,
                )
                crop_res = plate_model(up, verbose=False)[0]
                for box in crop_res.boxes:
                    conf = float(box.conf[0])
                    if conf < CONF_PLATE:
                        continue
                    px1, py1, px2, py2 = map(int, box.xyxy[0])
                    px1 = int(px1 / LIVE_PLATE_CROP_SCALE) + sx1
                    py1 = int(py1 / LIVE_PLATE_CROP_SCALE) + sy1
                    px2 = int(px2 / LIVE_PLATE_CROP_SCALE) + sx1
                    py2 = int(py2 / LIVE_PLATE_CROP_SCALE) + sy1
                    cand = (px1, py1, px2, py2, conf)
                    if not any(get_iou(cand[:4], p[:4]) > 0.40 for p in plates):
                        plates.append(cand)

        def _check_and_log(vtype, violated):
            if violated and not memory.has(tid, vtype):
                pt, pc, _ = get_plate_for_bike(
                    plates, bike_box, frame, reader,
                    PREFERRED_STATES, search_box=search_box)
                rec = ViolationRecord(tid, vtype, pt, pc, frame_num)
                memory.add(rec)
                if violation_callback is not None:
                    violation_callback(rec, bike_box)

        # Triple riding takes precedence
        violated, _ = check_triple_riding(persons_on, helmets_on, no_helmets_on)
        _check_and_log(V_TRIPLE, violated)

        violated, _ = check_co_riding(persons_on, helmets_on, no_helmets_on, bike_box)
        _check_and_log(V_CO_RIDING, violated)

        violated, _ = check_helmet_violation(no_helmets_on, helmets_on)
        _check_and_log(V_NO_HELMET, violated)

        # OCR retries
        for vtype in (V_TRIPLE, V_CO_RIDING, V_NO_HELMET):
            if memory.needs_plate_retry(tid, vtype, frame_num=frame_num,
                                        retry_frame_gap=PLATE_RETRY_FRAME_GAP):
                pt, pc, _ = get_plate_for_bike(
                    plates, bike_box, frame, reader,
                    PREFERRED_STATES, search_box=search_box)
                memory.increment_retry(tid, vtype, frame_num=frame_num)
                if pt:
                    memory.update_plate(tid, vtype, pt, pc)

    return tracked, persons, helmets, no_helmets, plates


# ══════════════════════════════════════════════════════════════════════════════
# FILE MODE pipeline  (unchanged public interface)
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(video_path:  str,
                 output_path: str,
                 json_path:   str | None = None,
                 model_registry=None) -> ViolationMemory:
    """
    Process a video file frame by frame and write an annotated output video.

    Parameters
    ----------
    video_path      : path to source video
    output_path     : path for annotated output video
    json_path       : path for JSON violation export (None = skip)
    model_registry  : pre-loaded ModelRegistry (None = load fresh)

    Returns
    -------
    ViolationMemory with all detected violations.
    """
    if model_registry is not None:
        coco_model   = model_registry.coco_model
        helmet_model = model_registry.helmet_model
        plate_model  = model_registry.plate_model
        reader       = model_registry.ocr_reader
        print("[*] Using pre-loaded models from registry")
    else:
        print("[*] Loading models…")
        coco_model   = YOLO(MODEL_COCO)
        helmet_model = YOLO(MODEL_HELMET)
        plate_model  = YOLO(MODEL_PLATE)
        reader       = easyocr.Reader(['en'], gpu=False)
        print("[*] Models loaded.\n")

    tracker = SOTTracker(max_age=10 * PROCESS_EVERY_N_FRAMES, iou_thresh=0.25)
    memory  = ViolationMemory()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    src_fps      = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_w        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h        = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    print(f"[*] Input  : {src_w}×{src_h} @ {src_fps:.1f} FPS ({total_frames} frames)")
    print(f"[*] Config : process every {PROCESS_EVERY_N_FRAMES} frames | "
          f"inference at {INFER_W}×{INFER_H} | "
          f"plate search extended ↓{int(PLATE_SEARCH_DOWN_FRAC*100)}% | "
          f"plate retries: {ViolationMemory.MAX_PLATE_RETRIES}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    writer = cv2.VideoWriter(
        output_path, cv2.VideoWriter_fourcc(*'mp4v'),
        src_fps, (src_w, src_h))

    last_persons, last_helmets, last_no_helmets, last_plates = [], [], [], []
    frame_num, infer_count = 0, 0
    t_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1
        is_inference = (frame_num % PROCESS_EVERY_N_FRAMES == 0 or frame_num == 1)
        tracker.predict_all()

        if is_inference:
            infer_count += 1
            tracked, last_persons, last_helmets, last_no_helmets, last_plates = \
                _process_inference_frame(
                    frame, coco_model, helmet_model, plate_model,
                    reader, tracker, memory, frame_num, src_w, src_h,
                    violation_callback=None,
                    live_mode=False)   # file mode – no callback needed
        else:
            tracked = tracker.confirmed_tracks()

        annotated = draw_frame(
            frame, tracked,
            last_persons, last_helmets, last_no_helmets, last_plates, memory)
        writer.write(annotated)

        if frame_num % 30 == 0:
            elapsed  = time.time() - t_start
            fps_real = frame_num / elapsed if elapsed > 0 else 0.0
            pct      = (f"{100*frame_num/total_frames:.1f}%" if total_frames > 0 else "?")
            undetected = sum(1 for r in memory.all_records() if r.plate_text is None)
            print(f"  Frame {frame_num:05d}/{total_frames} [{pct}]  "
                  f"{fps_real:.1f} FPS  | Tracked: {len(tracked)}  "
                  f"| Violations: {len(memory.all_records())}  "
                  f"| Undetected plates: {undetected}")

    cap.release()
    writer.release()

    elapsed = time.time() - t_start
    print(f"\n[*] Done — {frame_num} frames in {elapsed:.1f}s "
          f"({frame_num/elapsed:.1f} FPS avg) | YOLO ran on {infer_count}/{frame_num} frames")
    print(f"[*] Annotated video saved → {output_path}")

    if json_path:
        export_json(memory, json_path)

    print_summary(memory)
    return memory


# ══════════════════════════════════════════════════════════════════════════════
# LIVE MODE pipeline  (NEW)
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline_live(
    camera_source:       int | str,
    camera_id:           str,
    stop_event:          threading.Event,
    violation_callback:  Callable[[ViolationRecord, bytes], None],
    frame_callback:      Optional[Callable[[bytes], None]] = None,
    reconnect_on_fail:   bool = True,
    max_reconnect_wait:  int  = 10,
    model_registry=None,
) -> ViolationMemory:
    """
    Run the violation-detection pipeline on a live camera stream.

    Designed to run in a dedicated background thread managed by the web server.
    The function blocks until stop_event is set.

    Parameters
    ----------
    camera_source : int | str
        • int   → USB/built-in webcam index (0, 1, 2 …)
        • str   → RTSP/HTTP/MJPEG URL, e.g.
                  "rtsp://admin:pass@192.168.1.10:554/stream1"
                  "http://192.168.1.10:8080/video"
    camera_id : str
        Unique identifier for this camera (stored on ViolationRecords and
        passed to callbacks so the web layer can route records correctly).
    stop_event : threading.Event
        Set this from the web layer to gracefully stop the camera loop.
    violation_callback : callable(record: ViolationRecord, crop_jpeg: bytes)
        Called (in this background thread) whenever a NEW violation is
        detected.  crop_jpeg is a JPEG-encoded crop of the offending
        motorcycle — upload this to Cloudinary or store it in the DB.
        The callback should be non-blocking (e.g. submit to a thread pool).
    frame_callback : callable(jpeg_bytes: bytes) | None
        Called on every annotated frame. Use this for live MJPEG/WebSocket
        streaming to the browser. Pass None if streaming is not needed.
    reconnect_on_fail : bool
        If True, reconnect to the camera after a read failure (network hiccup).
    max_reconnect_wait : int
        Maximum seconds to wait between reconnection attempts (exponential
        back-off capped at this value).

    Returns
    -------
    ViolationMemory containing all violations detected during this session.

    Thread safety
    -------------
    • All callbacks are called from THIS thread — they must be thread-safe.
    • violation_callback typically pushes records onto a queue consumed by the
      main web-server thread (or a DB worker).
    • stop_event.set() from any thread will cleanly exit the loop after the
      current frame completes processing.

    Example usage (inside a FastAPI / Flask / Django view)
    -------------------------------------------------------
    import threading
    from main import run_pipeline_live
    from tracker import ViolationRecord

    stop_event = threading.Event()

    def on_violation(rec: ViolationRecord, jpeg: bytes):
        # Upload jpeg to Cloudinary, save rec to DB, emit Socket.IO event …
        pass

    def on_frame(jpeg: bytes):
        # Emit to all subscribed WebSocket clients for this camera
        socketio.emit(f"frame:{camera_id}", jpeg)

    t = threading.Thread(
        target=run_pipeline_live,
        args=(0, "CAM-001", stop_event, on_violation, on_frame),
        daemon=True
    )
    t.start()

    # To stop: stop_event.set()
    """

    if model_registry is not None:
        coco_model   = model_registry.coco_model
        helmet_model = model_registry.helmet_model
        plate_model  = model_registry.plate_model
        reader       = model_registry.ocr_reader
        print(f"[LIVE:{camera_id}] Using pre-loaded models from registry")
    else:
        print(f"[LIVE:{camera_id}] Loading models…")
        coco_model   = YOLO(MODEL_COCO)
        helmet_model = YOLO(MODEL_HELMET)
        plate_model  = YOLO(MODEL_PLATE)
        reader       = easyocr.Reader(['en'], gpu=False)
        print(f"[LIVE:{camera_id}] Models loaded.\n")

    tracker = SOTTracker(max_age=10 * PROCESS_EVERY_N_FRAMES, iou_thresh=0.25)
    memory  = ViolationMemory()

    last_persons:     list = []
    last_helmets:     list = []
    last_no_helmets:  list = []
    last_plates:      list = []

    frame_num     = 0
    emit_counter  = 0
    reconnect_wait = 2   # seconds; doubles on each failure up to max

    def _open_capture():
        cap = cv2.VideoCapture(camera_source)
        if not cap.isOpened():
            return None
        # Reduce OpenCV's internal buffer to minimise latency.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    cap = _open_capture()
    if cap is None:
        print(f"[LIVE:{camera_id}] ERROR – cannot open camera: {camera_source}")
        return memory

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[LIVE:{camera_id}] Stream opened: {src_w}×{src_h}  source={camera_source}")

    pending_violations: list[tuple[ViolationRecord, tuple]] = []

    # ── Main live loop ────────────────────────────────────────────────────────
    t_start = time.time()

    while not stop_event.is_set():
        ret, frame = cap.read()

        # ── Handle read failure / stream end ──────────────────────────────────
        if not ret:
            print(f"[LIVE:{camera_id}] Frame read failed.")
            cap.release()
            if not reconnect_on_fail or stop_event.is_set():
                break
            print(f"[LIVE:{camera_id}] Reconnecting in {reconnect_wait}s…")
            stop_event.wait(timeout=reconnect_wait)
            reconnect_wait = min(reconnect_wait * 2, max_reconnect_wait)
            cap = _open_capture()
            if cap is None:
                print(f"[LIVE:{camera_id}] Reconnect failed, retrying…")
            else:
                src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"[LIVE:{camera_id}] Reconnected ({src_w}×{src_h})")
                reconnect_wait = 2
            continue

        reconnect_wait = 2   # reset on successful read
        frame_num += 1

        is_inference = (frame_num % PROCESS_EVERY_N_FRAMES == 0 or frame_num == 1)
        tracker.predict_all()

        if is_inference:
            pending_violations = []

            def _queue_violation(rec: ViolationRecord, bike_box: tuple):
                pending_violations.append((rec, bike_box))

            tracked, last_persons, last_helmets, last_no_helmets, last_plates = \
                _process_inference_frame(
                    frame, coco_model, helmet_model, plate_model,
                    reader, tracker, memory, frame_num, src_w, src_h,
                    violation_callback=_queue_violation,
                    live_mode=True)
        else:
            tracked = tracker.confirmed_tracks()

        # ── Annotate frame ────────────────────────────────────────────────────
        annotated = draw_frame(
            frame, tracked,
            last_persons, last_helmets, last_no_helmets, last_plates, memory)

        # ── Evidence crops (from annotated frame so boxes/labels are visible) ─
        for rec, bike_box in pending_violations:
            rec.camera_id = camera_id
            crop = capture_violation_crop(annotated, bike_box)
            jpeg_bytes = encode_jpeg(crop)
            try:
                violation_callback(rec, jpeg_bytes)
            except Exception as exc:
                print(f"[LIVE:{camera_id}] violation_callback error: {exc}")

        # ── Overlay camera ID and live timestamp ──────────────────────────────
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S")
        _txt(annotated, f"{camera_id}  {ts_str}",
             (10, src_h - 14), (200, 200, 200), scale=0.50, thick=1)

        # ── Emit annotated frame to web layer ─────────────────────────────────
        if frame_callback is not None:
            emit_counter += 1
            if emit_counter % LIVE_STREAM_EMIT_EVERY == 0:
                jpeg = encode_jpeg(annotated)
                try:
                    frame_callback(jpeg)
                except Exception as exc:
                    print(f"[LIVE:{camera_id}] frame_callback error: {exc}")

        # ── Progress log every 150 frames ─────────────────────────────────────
        if frame_num % 150 == 0:
            elapsed  = time.time() - t_start
            fps_real = frame_num / elapsed if elapsed > 0 else 0.0
            print(f"[LIVE:{camera_id}] Frame {frame_num}  {fps_real:.1f} FPS  "
                  f"| Tracked: {len(tracked)}  "
                  f"| Violations: {len(memory.all_records())}")

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if cap is not None:
        cap.release()

    elapsed = time.time() - t_start
    print(f"\n[LIVE:{camera_id}] Stopped — {frame_num} frames in {elapsed:.1f}s")
    print_summary(memory)
    return memory


# ══════════════════════════════════════════════════════════════════════════════
# Entry point  (FILE MODE)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    memory = run_pipeline(
        video_path  = VIDEO_PATH,
        output_path = OUTPUT_VIDEO,
        json_path   = OUTPUT_JSON,
    )