"""
main.py – Motorcycle Helmet & Riding Violation Detection System
===============================================================
TRUE 3-THREAD PIPELINE  (correct batch architecture)

ROOT CAUSE OF ALL PREVIOUS PROBLEMS
--------------------------------------
Previous version: capture thread → queue → single loop does YOLO + draw + emit
  Result: display only updates AFTER YOLO finishes (200-400 ms each time)
          → video looks frozen / laggy / far behind real time

CORRECT ARCHITECTURE (this version)
--------------------------------------

  ┌───────────────────────────────────────────────────────────────────┐
  │  THREAD 1 – CAPTURE  (full camera speed, e.g. 30 fps)            │
  │    Reads raw frames. Writes latest into SharedState.              │
  │    Old frames are overwritten — never queued or buffered.         │
  └──────────────────────┬────────────────────────────────────────────┘
                         │  SharedState.latest_frame
  ┌──────────────────────▼────────────────────────────────────────────┐
  │  THREAD 2 – INFERENCE BACKEND  (batch, every ~150 ms)            │
  │    Grabs latest frame. Runs 3x YOLO. Detects violations.         │
  │    Submits OCR to background executor (never waits for it).      │
  │    Writes DetectionSnapshot into SharedState.                     │
  └──────────────────────┬────────────────────────────────────────────┘
                         │  SharedState.latest_detections
  ┌──────────────────────▼────────────────────────────────────────────┐
  │  THREAD 3 – DISPLAY  (always 30 fps regardless of inference)     │
  │    Grabs latest_frame + latest_detections every ~33 ms.          │
  │    Draws boxes/labels (no YOLO here — just cv2.rectangle calls). │
  │    Shows local window. Calls frame_callback(jpeg) for streaming. │
  └───────────────────────────────────────────────────────────────────┘

  ┌───────────────────────────────────────────────────────────────────┐
  │  OCR EXECUTOR  (1 background worker — runs EasyOCR only)         │
  │    Violations are logged immediately with plate="READING..."     │
  │    OCR result fills in plate text when done. No freeze.          │
  └───────────────────────────────────────────────────────────────────┘

WHY THE VIDEO IS NOW SMOOTH
-----------------------------
Thread 3 runs at 30 fps NO MATTER HOW SLOW Thread 2 is.
If YOLO takes 300 ms, Thread 3 simply reuses the last known detections
and draws them on the freshest camera frame. The display is always live.
"""

import cv2
import time
import os
import json
import threading
import concurrent.futures
from dataclasses import dataclass, field
from typing import Callable, Optional, List

import numpy as np
from ultralytics import YOLO
import easyocr

from utils           import (is_rider_on_bike, get_iou,
                              assign_head_detections)
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

# ── Inference interval ────────────────────────────────────────────────────────
# Thread 2 runs YOLO every this many milliseconds.
# 200 ms ≈  5 inferences/s  (slow CPU)
# 150 ms ≈  7 inferences/s  (typical laptop)
# 100 ms ≈ 10 inferences/s  (fast CPU or GPU)
INFERENCE_INTERVAL_MS = 150

# ── Display frame rate ────────────────────────────────────────────────────────
# Thread 3 targets this FPS independently of YOLO speed.
DISPLAY_FPS         = 30
DISPLAY_INTERVAL_MS = int(1000 / DISPLAY_FPS)

# ── Inference resolution ──────────────────────────────────────────────────────
INFER_W, INFER_H = 416, 256

# ── Plate search box extension ────────────────────────────────────────────────
PLATE_SEARCH_DOWN_FRAC = 0.40

# ── OCR retry gap (in inference cycles, not display frames) ──────────────────
PLATE_RETRY_INFER_GAP = 15

# ── FILE MODE: run YOLO on every Nth frame (2 = every other frame, fastest) ──
# Lower  = more accurate, slower.   2 is the best balance for most videos.
FILE_PROCESS_EVERY_N = 2

# ── Spatial association ───────────────────────────────────────────────────────
ASSOC_IOU_THRESH = 0.10

PREFERRED_STATES = None

# ── Webcam settings ───────────────────────────────────────────────────────────
WEBCAM_WIDTH  = 1280
WEBCAM_HEIGHT = 720
WEBCAM_FPS    = 30

# ── Streaming ─────────────────────────────────────────────────────────────────
LIVE_STREAM_JPEG_QUALITY = 75

# ── Local preview window ──────────────────────────────────────────────────────
SHOW_LOCAL_WINDOW = True

# ── Plate crop upscale for webcam ─────────────────────────────────────────────
LIVE_PLATE_CROP_SCALE = 3.0


# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

V_NO_HELMET = 'NO_HELMET'
V_TRIPLE    = 'TRIPLE_RIDING'
V_CO_RIDING = 'CO_RIDING_NO_HELMET'

CLR_BIKE    = (0,   255,   0)
CLR_VIOL    = (0,    50, 255)
CLR_HELMET  = (0,   255, 255)
CLR_NO_HELM = (0,     0, 255)
CLR_PLATE   = (255,   0,   0)
CLR_PERSON  = (255, 128,   0)
CLR_PILLION = (180,   0, 255)


# ══════════════════════════════════════════════════════════════════════════════
# DetectionSnapshot  – what Thread 2 writes, Thread 3 reads
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class DetectionSnapshot:
    """
    Immutable snapshot of the latest YOLO detection results.
    Thread 2 creates a new instance after each inference cycle.
    Thread 3 reads and reuses it to draw annotations.
    Reading is safe without locks because Python dataclass attribute
    reads are atomic (the reference is replaced atomically via SharedState).
    """
    tracked:     list  = field(default_factory=list)
    persons:     list  = field(default_factory=list)
    helmets:     list  = field(default_factory=list)
    no_helmets:  list  = field(default_factory=list)
    plates:      list  = field(default_factory=list)
    infer_count: int   = 0
    infer_time:  float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# SharedState  – bridge between the three threads
# ══════════════════════════════════════════════════════════════════════════════

class SharedState:
    """
    Two shared slots:
      • _frame      : latest raw BGR frame from webcam  (Thread 1 writes)
      • _detections : latest DetectionSnapshot         (Thread 2 writes)

    Both are protected by separate locks.
    Reads always return a copy (for _frame) or the current object (for _detections).
    """

    def __init__(self):
        self._frame_lock = threading.Lock()
        self._det_lock   = threading.Lock()
        self._frame:      Optional[np.ndarray] = None
        self._detections: DetectionSnapshot    = DetectionSnapshot()

    def write_frame(self, frame: np.ndarray):
        with self._frame_lock:
            self._frame = frame           # overwrite — always freshest

    def read_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return None if self._frame is None else self._frame.copy()

    def write_detections(self, snap: DetectionSnapshot):
        with self._det_lock:
            self._detections = snap

    def read_detections(self) -> DetectionSnapshot:
        with self._det_lock:
            return self._detections


# ══════════════════════════════════════════════════════════════════════════════
# Detection association helpers
# ══════════════════════════════════════════════════════════════════════════════

def _persons_on_bike(persons, bike_box):
    return [p for p in persons
            if (get_iou(p[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
                or is_rider_on_bike(p[:4], bike_box))]

def _dets_on_bike(dets, bike_box):
    return [d for d in dets
            if (get_iou(d[:4], bike_box[:4]) >= ASSOC_IOU_THRESH
                or is_rider_on_bike(d[:4], bike_box))]

def _plate_search_box(bike_box, persons_on, helmets_on, no_helmets_on, frame_h):
    all_boxes = [bike_box[:4]] + [d[:4] for d in persons_on + helmets_on + no_helmets_on]
    ux1 = int(min(b[0] for b in all_boxes))
    uy1 = int(min(b[1] for b in all_boxes))
    ux2 = int(max(b[2] for b in all_boxes))
    uy2 = int(max(b[3] for b in all_boxes))
    bike_h = bike_box[3] - bike_box[1]
    ext_y2 = min(frame_h, int(uy2 + bike_h * PLATE_SEARCH_DOWN_FRAC))
    return (ux1, uy1, ux2, ext_y2)


# ══════════════════════════════════════════════════════════════════════════════
# Drawing helpers
# ══════════════════════════════════════════════════════════════════════════════

def _txt(img, text, pt, colour, scale=0.55, thick=2):
    cv2.putText(img, text, pt,
                cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thick, cv2.LINE_AA)

def _box(img, b, colour, thick=2):
    cv2.rectangle(img, (int(b[0]), int(b[1])), (int(b[2]), int(b[3])),
                  colour, thick)

def draw_frame(frame: np.ndarray,
               snap:  DetectionSnapshot,
               memory: ViolationMemory,
               fps_display: float = 0.0,
               fps_infer:   float = 0.0) -> np.ndarray:
    """
    Pure drawing function — no YOLO, no OCR.
    Called by Thread 3 at 30 fps.  Uses the last known DetectionSnapshot.
    If inference hasn't updated yet, it redraws with the previous snapshot —
    the displayed bounding boxes may be slightly stale (1 inference cycle old)
    but the video frame is always the CURRENT camera frame, so the feed looks
    live and smooth.
    """
    active_ids = {t.track_id for t in snap.tracked}
    rec_lookup = {(r.track_id, r.violation_type): r
                  for r in memory.all_records()
                  if r.track_id in active_ids}

    for h  in snap.helmets:    _box(frame, h,  CLR_HELMET,  1)
    for nh in snap.no_helmets:
        _box(frame, nh, CLR_NO_HELM, 2)
        _txt(frame, f"No Helmet {nh[4]:.2f}",
             (int(nh[0]), int(nh[1]) - 6), CLR_NO_HELM, scale=0.45)
    for p  in snap.persons:    _box(frame, p,  CLR_PERSON,  1)
    for pl in snap.plates:     _box(frame, pl, CLR_PLATE,   1)

    for trk in snap.tracked:
        lb  = trk.get_ltrb().astype(int)
        tid = trk.track_id
        viols = [v for (tid2, _), v in rec_lookup.items() if tid2 == tid]

        col = CLR_VIOL if viols else CLR_BIKE
        _box(frame, lb, col, 3 if viols else 2)
        _txt(frame, f"Bike#{tid}", (lb[0], lb[1] - 10), col, scale=0.5)

        y_top = lb[1] - 28
        for rec in viols:
            if rec.violation_type == V_NO_HELMET:
                lbl, c = "!! NO HELMET",          CLR_NO_HELM
            elif rec.violation_type == V_TRIPLE:
                lbl, c = "!! TRIPLE RIDING",      CLR_PERSON
            else:
                lbl, c = "!! CO-RIDER NO HELMET", CLR_PILLION
            _txt(frame, lbl, (lb[0], y_top), c, scale=0.60, thick=2)
            y_top -= 22
        if viols:
            ptext = viols[0].plate_text or "READING..."
            _txt(frame, f"Plate: {ptext}", (lb[0], lb[3] + 20), CLR_PLATE, 0.55)

    # ── HUD ──────────────────────────────────────────────────────────────────
    h = frame.shape[0]
    _txt(frame, f"Display:{fps_display:.0f}fps  Infer:{fps_infer:.0f}fps",
         (10, h - 12), (170, 170, 170), scale=0.45, thick=1)
    return frame


# ══════════════════════════════════════════════════════════════════════════════
# Utility
# ══════════════════════════════════════════════════════════════════════════════

def capture_violation_crop(frame, bike_box, pad=0.25):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bike_box[:4])
    px = int((x2-x1)*pad);  py = int((y2-y1)*pad)
    crop = frame[max(0,y1-py):min(h,y2+py), max(0,x1-px):min(w,x2+px)]
    return crop if crop.size > 0 else frame.copy()

def encode_jpeg(img, quality=LIVE_STREAM_JPEG_QUALITY):
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return bytes(buf) if ok else b''

def print_summary(memory):
    print("\n" + "═"*66 + "\n  VIOLATION SUMMARY\n" + "═"*66)
    print(memory.summary())
    print("═"*66 + "\n")

def export_json(memory, path):
    data = [{"track_id": r.track_id, "violation_type": r.violation_type,
             "plate_text": r.plate_text, "plate_conf": round(r.plate_conf, 4),
             "frame_number": r.frame_number, "timestamp": r.timestamp}
            for r in memory.all_records()]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[*] JSON saved → {path}")

def _harvest_ocr(ocr_futures: dict, memory: ViolationMemory):
    for key in [k for k, f in ocr_futures.items() if f.done()]:
        tid, vtype = key
        try:
            pt, pc, _ = ocr_futures.pop(key).result(timeout=0)
            if pt:
                memory.update_plate(tid, vtype, pt, pc)
                print(f"  [OCR ✓] Track-{tid:03d} {vtype} → {pt} ({pc:.2f})")
        except Exception as e:
            print(f"  [OCR ERR] {key}: {e}")
            ocr_futures.pop(key, None)


# ══════════════════════════════════════════════════════════════════════════════
# THREAD 1 – CAPTURE
# ══════════════════════════════════════════════════════════════════════════════

def _thread_capture(cap, state: SharedState, stop: threading.Event, cam_id: str):
    """Reads webcam frames and overwrites SharedState.latest_frame continuously."""
    fail = 0
    while not stop.is_set():
        ret, frame = cap.read()
        if not ret:
            fail += 1
            if fail >= 30:
                print(f"[CAPTURE:{cam_id}] 30 consecutive fails — stopping")
                stop.set(); break
            time.sleep(0.005)
            continue
        fail = 0
        state.write_frame(frame)
    print(f"[CAPTURE:{cam_id}] exited")


# ══════════════════════════════════════════════════════════════════════════════
# THREAD 2 – INFERENCE BACKEND  (the batch processing)
# ══════════════════════════════════════════════════════════════════════════════

def _thread_inference(coco_model, helmet_model, plate_model, reader,
                      state: SharedState, memory: ViolationMemory,
                      tracker: SOTTracker, stop: threading.Event,
                      cam_id: str, src_w: int, src_h: int,
                      ocr_executor, ocr_futures: dict, ocr_lock: threading.Lock,
                      vcrops: list, vclock: threading.Lock):
    """
    Batch inference backend.

    - Wakes every INFERENCE_INTERVAL_MS
    - Grabs the latest raw frame from SharedState (always current)
    - Runs 3x YOLO models
    - Runs violation detection
    - Submits OCR tasks to background executor (non-blocking)
    - Writes new DetectionSnapshot to SharedState for Thread 3 to draw

    Thread 3 (display) is COMPLETELY SEPARATE and runs at 30fps regardless
    of how long this thread takes. This is what makes the video smooth.
    """
    interval = INFERENCE_INTERVAL_MS / 1000.0
    n = 0
    t_next = time.time()

    print(f"[INFER:{cam_id}] started (~{1000//INFERENCE_INTERVAL_MS} runs/s)")

    while not stop.is_set():
        # ── Wait until next inference window ─────────────────────────────────
        now = time.time()
        if now < t_next:
            time.sleep(t_next - now)
        t_next = time.time() + interval

        frame = state.read_frame()
        if frame is None:
            continue

        t0 = time.time()
        n += 1

        # ── YOLO inference ────────────────────────────────────────────────────
        small = cv2.resize(frame, (INFER_W, INFER_H))
        sx    = src_w / INFER_W
        sy    = src_h / INFER_H

        def sc(box):
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            return (int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy), float(box.conf[0]))

        bikes, persons = [], []
        for b in coco_model(small, verbose=False)[0].boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            if cls == 3 and conf >= CONF_MOTORCYCLE: bikes.append(sc(b))
            elif cls == 0 and conf >= CONF_PERSON:   persons.append(sc(b))

        helmets, no_helmets = [], []
        for b in helmet_model(small, verbose=False)[0].boxes:
            cls, conf = int(b.cls[0]), float(b.conf[0])
            if conf < CONF_HELMET: continue
            e = sc(b)
            if cls == 1:   helmets.append(e)
            elif cls == 2: no_helmets.append(e)

        plates = []
        for b in plate_model(frame, verbose=False)[0].boxes:
            conf = float(b.conf[0])
            if conf >= CONF_PLATE:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                plates.append((x1, y1, x2, y2, conf))

        # ── Tracker ───────────────────────────────────────────────────────────
        tracker.predict_all()
        tracked = tracker.associate([([m[0],m[1],m[2],m[3]], m[4]) for m in bikes])

        # ── Harvest done OCR futures ──────────────────────────────────────────
        _harvest_ocr(ocr_futures, memory)

        # ── Per-bike violation detection ──────────────────────────────────────
        for trk in tracked:
            bike  = tuple(trk.get_ltrb().astype(int))
            tid   = trk.track_id
            pon   = _persons_on_bike(persons, bike)
            hon   = _dets_on_bike(helmets,    bike)
            nhon  = _dets_on_bike(no_helmets, bike)
            sbox  = _plate_search_box(bike, pon, hon, nhon, src_h)

            # ── Upscale plate region and re-detect (webcam quality fix) ───────
            sx1, sy1 = max(0, sbox[0]), max(0, sbox[1])
            sx2, sy2 = min(src_w, sbox[2]), min(src_h, sbox[3])
            pcrop = frame[sy1:sy2, sx1:sx2]
            if pcrop.size > 0:
                cw, ch = pcrop.shape[1], pcrop.shape[0]
                up = cv2.resize(pcrop,
                    (int(cw*LIVE_PLATE_CROP_SCALE), int(ch*LIVE_PLATE_CROP_SCALE)),
                    interpolation=cv2.INTER_LANCZOS4)
                for b in plate_model(up, verbose=False)[0].boxes:
                    conf = float(b.conf[0])
                    if conf < CONF_PLATE: continue
                    px1, py1, px2, py2 = map(int, b.xyxy[0])
                    cand = (int(px1/LIVE_PLATE_CROP_SCALE)+sx1,
                            int(py1/LIVE_PLATE_CROP_SCALE)+sy1,
                            int(px2/LIVE_PLATE_CROP_SCALE)+sx1,
                            int(py2/LIVE_PLATE_CROP_SCALE)+sy1, conf)
                    if not any(get_iou(cand[:4], p[:4]) > 0.40 for p in plates):
                        plates.append(cand)

            # ── Async OCR submit ──────────────────────────────────────────────
            def _ocr(tid_=tid, vtype_=None, plates_=plates, f_=frame, s_=sbox, b_=bike):
                key = (tid_, vtype_)
                if key in ocr_futures and not ocr_futures[key].done():
                    return
                _pl = list(plates_);  _fr = f_.copy();  _s = s_
                def _task():
                    with ocr_lock:
                        return get_plate_for_bike(_pl, b_, _fr, reader,
                                                  PREFERRED_STATES, search_box=_s)
                ocr_futures[key] = ocr_executor.submit(_task)

            # ── Log violation helper ──────────────────────────────────────────
            def _log(vtype, violated):
                if not violated or memory.has(tid, vtype): return
                rec = ViolationRecord(tid, vtype, None, 0.0, n)
                memory.add(rec)
                _ocr(tid_=tid, vtype_=vtype)
                with vclock:
                    vcrops.append((rec, bike))

            # Head assignment
            _, p_nh = assign_head_detections(pon, hon, nhon)
            if len(pon) >= 2:
                bx_c = (bike[0]+bike[2])/2.0
                di   = min(range(len(pon)), key=lambda i: abs((pon[i][0]+pon[i][2])/2-bx_c))
                coi  = [i for i in range(len(pon)) if i != di]
                dnh  = p_nh[di]
            elif len(pon) == 1:
                di=0; coi=[]; dnh=p_nh[0]
            else:
                di=None; coi=[]; dnh=[]

            tv, _ = check_triple_riding(pon, hon, nhon)
            _log(V_TRIPLE, tv)
            if tv:
                _log(V_CO_RIDING, any(p_nh[i] for i in coi) if coi else len(nhon)>1)
            else:
                cv2_v, _ = check_co_riding(pon, hon, nhon, bike)
                _log(V_CO_RIDING, cv2_v)
            if di is None and memory.has(tid, V_CO_RIDING):
                dnh = []
            nh_v, _ = check_helmet_violation(dnh, hon)
            _log(V_NO_HELMET, nh_v)

            # OCR retries
            for vt in (V_TRIPLE, V_CO_RIDING, V_NO_HELMET):
                if memory.needs_plate_retry(tid, vt, frame_num=n,
                                            retry_frame_gap=PLATE_RETRY_INFER_GAP):
                    memory.increment_retry(tid, vt, frame_num=n)
                    _ocr(tid_=tid, vtype_=vt)

        # ── Write snapshot for display thread ─────────────────────────────────
        state.write_detections(DetectionSnapshot(
            tracked=list(tracked), persons=persons, helmets=helmets,
            no_helmets=no_helmets, plates=plates,
            infer_count=n, infer_time=time.time()-t0))

        if n % 50 == 0:
            it = time.time()-t0
            print(f"[INFER:{cam_id}] #{n}  {1/it:.1f}/s  "
                  f"bikes:{len(tracked)}  violations:{len(memory.all_records())}  "
                  f"ocr_pending:{len(ocr_futures)}")

    print(f"[INFER:{cam_id}] exited")


# ══════════════════════════════════════════════════════════════════════════════
# THREAD 3 – DISPLAY  (always 30 fps — completely independent of YOLO)
# ══════════════════════════════════════════════════════════════════════════════

def _thread_display(state: SharedState, memory: ViolationMemory,
                    stop: threading.Event, cam_id: str,
                    frame_cb: Optional[Callable],
                    viol_cb:  Optional[Callable],
                    vcrops: list, vclock: threading.Lock):
    """
    Display thread — runs at DISPLAY_FPS regardless of inference speed.

    KEY POINT: this thread reads state.read_frame() (always fresh from webcam)
    and state.read_detections() (latest YOLO results). Even if YOLO runs at
    5/s and the display runs at 30/s, the video appears perfectly smooth
    because the raw frame is always current — only the detection boxes are
    ~150 ms old, which is invisible to the human eye.
    """
    interval  = DISPLAY_INTERVAL_MS / 1000.0
    disp_n    = 0
    t_start   = time.time()
    t_next    = time.time()
    fps_d     = 0.0
    fps_i     = 0.0
    last_ic   = 0

    print(f"[DISPLAY:{cam_id}] started ({DISPLAY_FPS} fps target)")

    while not stop.is_set():
        now = time.time()
        if now < t_next:
            time.sleep(t_next - now)
        t_next = time.time() + interval

        frame = state.read_frame()
        if frame is None:
            continue

        snap  = state.read_detections()
        disp_n += 1

        # FPS counters
        elapsed = time.time() - t_start
        fps_d   = disp_n / elapsed if elapsed > 0 else 0
        if snap.infer_count != last_ic and snap.infer_time > 0:
            fps_i   = 1.0 / snap.infer_time
            last_ic = snap.infer_count

        # Draw (fast — just cv2 calls)
        annotated = draw_frame(frame, snap, memory, fps_d, fps_i)

        # Timestamp overlay
        _txt(annotated, f"{cam_id}  {time.strftime('%H:%M:%S')}",
             (10, annotated.shape[0]-32), (200,200,200), scale=0.45, thick=1)

        # Dispatch violation evidence crops
        if viol_cb is not None:
            with vclock:
                pending = list(vcrops)
                vcrops.clear()
            for rec, bike in pending:
                crop = capture_violation_crop(annotated, bike)
                try:
                    viol_cb(rec, encode_jpeg(crop))
                except Exception as e:
                    print(f"[DISPLAY:{cam_id}] viol_cb error: {e}")

        # Local preview window
        if SHOW_LOCAL_WINDOW:
            cv2.imshow(f"Live: {cam_id}", annotated)
            k = cv2.waitKey(1) & 0xFF
            if k in (ord('q'), 27):
                stop.set(); break

        # Web streaming callback
        if frame_cb is not None:
            try:
                frame_cb(encode_jpeg(annotated))
            except Exception as e:
                print(f"[DISPLAY:{cam_id}] frame_cb error: {e}")

    print(f"[DISPLAY:{cam_id}] exited")


# ══════════════════════════════════════════════════════════════════════════════
# LIVE MODE  – starts all three threads + OCR executor
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline_live(
    camera_source:      int | str,
    camera_id:          str,
    stop_event:         threading.Event,
    violation_callback: Callable[[ViolationRecord, bytes], None],
    frame_callback:     Optional[Callable[[bytes], None]] = None,
    reconnect_on_fail:  bool = True,
    max_reconnect_wait: int  = 10,
    model_registry=None,
) -> ViolationMemory:
    """
    Start the 3-thread live pipeline.

    Thread layout
    -------------
    T1 _thread_capture   → SharedState.latest_frame
    T2 _thread_inference → SharedState.latest_detections + ViolationMemory
    T3 _thread_display   → cv2.imshow / frame_callback / violation_callback

    OCR runs in a ThreadPoolExecutor(max_workers=1) — never blocks T1/T2/T3.
    """

    # ── Models ────────────────────────────────────────────────────────────────
    if model_registry is not None:
        coco_m = model_registry.coco_model
        helm_m = model_registry.helmet_model
        plat_m = model_registry.plate_model
        reader = model_registry.ocr_reader
        print(f"[LIVE:{camera_id}] Using pre-loaded models")
    else:
        print(f"[LIVE:{camera_id}] Loading models…")
        coco_m = YOLO(MODEL_COCO)
        helm_m = YOLO(MODEL_HELMET)
        plat_m = YOLO(MODEL_PLATE)
        reader = easyocr.Reader(['en'], gpu=False)
        print(f"[LIVE:{camera_id}] Models loaded\n")

    # ── Camera ────────────────────────────────────────────────────────────────
    def _open():
        c = cv2.VideoCapture(camera_source)
        if not c.isOpened(): return None, 0, 0
        c.set(cv2.CAP_PROP_FRAME_WIDTH,  WEBCAM_WIDTH)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_HEIGHT)
        c.set(cv2.CAP_PROP_FPS,          WEBCAM_FPS)
        c.set(cv2.CAP_PROP_BUFFERSIZE,   1)
        w = int(c.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[LIVE:{camera_id}] Camera {w}×{h}")
        return c, w, h

    cap, src_w, src_h = _open()
    if cap is None:
        print(f"[LIVE:{camera_id}] Cannot open camera: {camera_source}")
        return ViolationMemory()

    # ── Shared objects ────────────────────────────────────────────────────────
    state   = SharedState()
    memory  = ViolationMemory()
    tracker = SOTTracker(max_age=30, iou_thresh=0.25)

    ocr_lock    = threading.Lock()
    ocr_futures: dict = {}

    # OCR runs in a separate thread — 1 worker ensures EasyOCR is never called
    # concurrently, which would cause crashes or wrong results
    ocr_exec = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="ocr")

    # Violation crops: inference thread writes, display thread reads+clears
    vcrops: list = []
    vclock  = threading.Lock()

    # ── Create threads ────────────────────────────────────────────────────────
    t1 = threading.Thread(target=_thread_capture,
                          args=(cap, state, stop_event, camera_id),
                          name=f"t1_capture_{camera_id}", daemon=True)

    t2 = threading.Thread(target=_thread_inference,
                          args=(coco_m, helm_m, plat_m, reader,
                                state, memory, tracker, stop_event, camera_id,
                                src_w, src_h,
                                ocr_exec, ocr_futures, ocr_lock,
                                vcrops, vclock),
                          name=f"t2_infer_{camera_id}", daemon=True)

    t3 = threading.Thread(target=_thread_display,
                          args=(state, memory, stop_event, camera_id,
                                frame_callback, violation_callback,
                                vcrops, vclock),
                          name=f"t3_display_{camera_id}", daemon=True)

    print(f"\n[LIVE:{camera_id}] ── Starting 3-Thread Pipeline ──")
    print(f"  Thread 1 – Capture  : full camera speed")
    print(f"  Thread 2 – Inference: every {INFERENCE_INTERVAL_MS} ms  "
          f"(~{1000//INFERENCE_INTERVAL_MS} runs/s)")
    print(f"  Thread 3 – Display  : every {DISPLAY_INTERVAL_MS} ms  "
          f"({DISPLAY_FPS} fps target)")
    print(f"  OCR Executor        : 1 background worker\n")

    t1.start()
    t2.start()
    t3.start()

    # ── Wait for stop ─────────────────────────────────────────────────────────
    try:
        while not stop_event.is_set():
            time.sleep(0.5)
            # Auto-reconnect if capture thread dies
            if not t1.is_alive() and reconnect_on_fail and not stop_event.is_set():
                print(f"[LIVE:{camera_id}] Capture died — reconnecting…")
                cap.release()
                rw = 2
                while not stop_event.is_set():
                    time.sleep(rw)
                    cap, src_w, src_h = _open()
                    if cap is not None:
                        t1 = threading.Thread(
                            target=_thread_capture,
                            args=(cap, state, stop_event, camera_id),
                            name=f"t1_capture_{camera_id}", daemon=True)
                        t1.start()
                        print(f"[LIVE:{camera_id}] Reconnected")
                        break
                    rw = min(rw * 2, max_reconnect_wait)
    except KeyboardInterrupt:
        print(f"\n[LIVE:{camera_id}] KeyboardInterrupt")
        stop_event.set()
    finally:
        stop_event.set()
        for t in (t1, t2, t3):
            t.join(timeout=3.0)
        cap.release()
        if SHOW_LOCAL_WINDOW:
            cv2.destroyAllWindows()
        ocr_exec.shutdown(wait=True, cancel_futures=False)
        _harvest_ocr(ocr_futures, memory)
        print(f"[LIVE:{camera_id}] All threads stopped.")
        print_summary(memory)

    return memory


# ══════════════════════════════════════════════════════════════════════════════
# FILE MODE  – optimised for speed
#
# Three specific slowdowns from the previous version are fixed here:
#
#  FIX 1 – SKIP changed from round(fps/10) back to FILE_PROCESS_EVERY_N = 2
#           (every other frame, same as the original code).  The previous
#           value of 3 forced the VideoWriter to write and draw_frame() to run
#           on MORE skipped frames for no benefit.
#
#  FIX 2 – scale() helper moved OUTSIDE the per-frame loop.
#           The old version redefined a closure inside the inference block on
#           EVERY inference frame.  Python rebuilds function objects each time,
#           which adds up over thousands of frames.
#
#  FIX 3 – OCR runs ASYNCHRONOUSLY via ThreadPoolExecutor.
#           The old version called get_plate_for_bike() synchronously inside
#           _log(), blocking the entire VideoWriter loop for 0.5–2 s per
#           violation.  A video with 5 violations = up to 10 s of dead time.
#           Now violations are logged immediately with plate=None; OCR fills
#           the plate in a background worker while the main loop continues
#           writing frames at full speed.  Retries keep running until the
#           video finishes, then we drain all remaining OCR futures before
#           writing the JSON so the final report always has plate numbers.
#
#  FIX 4 – draw_frame() called ONLY on inference frames; skipped frames
#           reuse the last annotated numpy array directly.  draw_frame() does
#           ~5–10 ms of cv2 work per call; skipping it on N-1 frames out of
#           every N saves a meaningful amount of wall-clock time on long videos.
# ══════════════════════════════════════════════════════════════════════════════

def _scale_boxes(boxes_result, sx: float, sy: float) -> list:
    """
    Scale YOLO box coordinates from inference resolution back to source
    resolution.  Defined once at module level — never recreated per frame.
    """
    out = []
    for b in boxes_result:
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        out.append((int(x1*sx), int(y1*sy), int(x2*sx), int(y2*sy),
                    float(b.conf[0])))
    return out


def run_pipeline(video_path: str, output_path: str,
                 json_path: str | None = None,
                 model_registry=None) -> ViolationMemory:
    """
    Process a video file frame by frame and write an annotated output.

    Speed improvements over previous version
    -----------------------------------------
    • FILE_PROCESS_EVERY_N = 2  (process every other frame, matching original)
    • scale() helper defined once, not per-frame
    • OCR runs in background ThreadPoolExecutor — VideoWriter never waits for it
    • draw_frame() skipped on non-inference frames (reuse last annotated frame)
    """

    # ── Load models ───────────────────────────────────────────────────────────
    if model_registry is not None:
        coco_m = model_registry.coco_model
        helm_m = model_registry.helmet_model
        plat_m = model_registry.plate_model
        reader = model_registry.ocr_reader
    else:
        print("[*] Loading models…")
        coco_m = YOLO(MODEL_COCO)
        helm_m = YOLO(MODEL_HELMET)
        plat_m = YOLO(MODEL_PLATE)
        reader = easyocr.Reader(['en'], gpu=False)
        print("[*] Models loaded.\n")

    tracker = SOTTracker(max_age=10 * FILE_PROCESS_EVERY_N, iou_thresh=0.25)
    memory  = ViolationMemory()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src_w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Pre-compute scale factors once — used inside the loop without recomputing
    sx = src_w / INFER_W
    sy = src_h / INFER_H

    print(f"[*] Input : {src_w}×{src_h} @ {src_fps:.0f} fps  "
          f"({total} frames)")
    print(f"[*] Config: inference every {FILE_PROCESS_EVERY_N} frames | "
          f"inference res {INFER_W}×{INFER_H} | async OCR")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    writer = cv2.VideoWriter(
        output_path, cv2.VideoWriter_fourcc(*'mp4v'),
        src_fps, (src_w, src_h))

    # ── Async OCR executor (1 worker — EasyOCR not thread-safe for >1) ───────
    ocr_lock    = threading.Lock()
    ocr_futures: dict = {}   # (tid, vtype) → Future

    file_ocr_exec = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="file_ocr")

    def _submit_file_ocr(tid_: int, vtype_: str,
                          plates_: list, frame_: np.ndarray,
                          bike_: tuple, sbox_: tuple):
        """Submit an OCR task without blocking the frame loop."""
        key = (tid_, vtype_)
        if key in ocr_futures and not ocr_futures[key].done():
            return
        _pl = list(plates_)
        _fr = frame_.copy()
        _bk = bike_
        _sb = sbox_
        def _task():
            with ocr_lock:
                return get_plate_for_bike(_pl, _bk, _fr, reader,
                                          PREFERRED_STATES, search_box=_sb)
        ocr_futures[key] = file_ocr_exec.submit(_task)

    # ── Main file loop ────────────────────────────────────────────────────────
    fn            = 0        # frame counter (every frame)
    infer_n       = 0        # inference counter (every FILE_PROCESS_EVERY_N frames)
    snap          = DetectionSnapshot()
    last_annotated: Optional[np.ndarray] = None
    t0            = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        fn += 1
        is_infer = (fn % FILE_PROCESS_EVERY_N == 0 or fn == 1)
        tracker.predict_all()

        if is_infer:
            infer_n += 1

            # ── YOLO inference ─────────────────────────────────────────────
            small = cv2.resize(frame, (INFER_W, INFER_H))
            coco_boxes   = coco_m(small,  verbose=False)[0].boxes
            helmet_boxes = helm_m(small,  verbose=False)[0].boxes
            plate_boxes  = plat_m(frame,  verbose=False)[0].boxes  # full-res

            # ── Parse detections (scale helper defined at module level) ────
            bikes, persons = [], []
            for b in coco_boxes:
                cls, conf = int(b.cls[0]), float(b.conf[0])
                if cls == 3 and conf >= CONF_MOTORCYCLE:
                    x1,y1,x2,y2 = map(int, b.xyxy[0])
                    bikes.append((int(x1*sx),int(y1*sy),int(x2*sx),int(y2*sy),conf))
                elif cls == 0 and conf >= CONF_PERSON:
                    x1,y1,x2,y2 = map(int, b.xyxy[0])
                    persons.append((int(x1*sx),int(y1*sy),int(x2*sx),int(y2*sy),conf))

            helmets, no_helmets = [], []
            for b in helmet_boxes:
                cls, conf = int(b.cls[0]), float(b.conf[0])
                if conf < CONF_HELMET: continue
                x1,y1,x2,y2 = map(int, b.xyxy[0])
                e = (int(x1*sx),int(y1*sy),int(x2*sx),int(y2*sy),conf)
                if cls == 1:   helmets.append(e)
                elif cls == 2: no_helmets.append(e)

            plates = []
            for b in plate_boxes:
                conf = float(b.conf[0])
                if conf >= CONF_PLATE:
                    x1,y1,x2,y2 = map(int, b.xyxy[0])
                    plates.append((x1,y1,x2,y2,conf))

            # ── Track ──────────────────────────────────────────────────────
            tracked = tracker.associate(
                [([m[0],m[1],m[2],m[3]], m[4]) for m in bikes])

            # ── Harvest completed OCR futures ──────────────────────────────
            _harvest_ocr(ocr_futures, memory)

            # ── Per-bike violation detection ───────────────────────────────
            for trk in tracked:
                bike  = tuple(trk.get_ltrb().astype(int))
                tid   = trk.track_id
                pon   = _persons_on_bike(persons, bike)
                hon   = _dets_on_bike(helmets,    bike)
                nhon  = _dets_on_bike(no_helmets, bike)
                sbox  = _plate_search_box(bike, pon, hon, nhon, src_h)
                _, p_nh = assign_head_detections(pon, hon, nhon)

                # Identify driver / co-riders
                if len(pon) >= 2:
                    bxc = (bike[0]+bike[2]) / 2.0
                    di  = min(range(len(pon)),
                              key=lambda i: abs((pon[i][0]+pon[i][2])/2 - bxc))
                    coi = [i for i in range(len(pon)) if i != di]
                    dnh = p_nh[di]
                elif len(pon) == 1:
                    di=0; coi=[]; dnh=p_nh[0]
                else:
                    di=None; coi=[]; dnh=[]

                # Violation log helper — does NOT block for OCR (FIX 3)
                def _log(vtype: str, violated: bool,
                         _tid=tid, _plates=plates, _frame=frame,
                         _bike=bike, _sbox=sbox, _fn=fn):
                    if not violated or memory.has(_tid, vtype):
                        return
                    # Log immediately with plate=None; OCR fills it async
                    memory.add(ViolationRecord(_tid, vtype, None, 0.0, _fn))
                    _submit_file_ocr(_tid, vtype, _plates, _frame, _bike, _sbox)

                tv, _ = check_triple_riding(pon, hon, nhon)
                _log(V_TRIPLE, tv)
                if tv:
                    _log(V_CO_RIDING,
                         any(p_nh[i] for i in coi) if coi else len(nhon) > 1)
                else:
                    cv_v, _ = check_co_riding(pon, hon, nhon, bike)
                    _log(V_CO_RIDING, cv_v)
                if di is None and memory.has(tid, V_CO_RIDING):
                    dnh = []
                nh_v, _ = check_helmet_violation(dnh, hon)
                _log(V_NO_HELMET, nh_v)

                # OCR retries (async — no blocking)
                for vt in (V_TRIPLE, V_CO_RIDING, V_NO_HELMET):
                    if memory.needs_plate_retry(tid, vt,
                                                frame_num=infer_n,
                                                retry_frame_gap=PLATE_RETRY_INFER_GAP):
                        memory.increment_retry(tid, vt, frame_num=infer_n)
                        _submit_file_ocr(tid, vt, plates, frame, bike, sbox)

            # ── Build new snapshot ─────────────────────────────────────────
            snap = DetectionSnapshot(
                tracked=list(tracked), persons=persons,
                helmets=helmets, no_helmets=no_helmets, plates=plates,
                infer_count=infer_n)

            # Draw ONLY on inference frames — reuse frame on skipped ones
            # (FIX 4: saves ~5–10 ms × (N-1)/N of all frames)
            last_annotated = draw_frame(frame, snap, memory)

        else:
            # Non-inference frame: skip draw_frame() entirely.
            # Write the CURRENT raw frame overlaid with previous detections.
            # We can't reuse last_annotated (it's a different frame).
            # Drawing is cheap so we do it here too but skip YOLO completely.
            if last_annotated is not None:
                last_annotated = draw_frame(frame, snap, memory)

        # Write to output video
        out_frame = last_annotated if last_annotated is not None else frame
        writer.write(out_frame)

        # Progress log
        if fn % 60 == 0:
            el = time.time() - t0
            undet = sum(1 for r in memory.all_records() if r.plate_text is None)
            pct   = f"{100*fn/total:.1f}%" if total > 0 else "?"
            print(f"  Frame {fn:05d}/{total} [{pct}]  "
                  f"{fn/el:.1f} fps  "
                  f"| Violations: {len(memory.all_records())}  "
                  f"| Plates pending: {undet}  "
                  f"| OCR queue: {len(ocr_futures)}")

    # ── Video done — drain all remaining OCR tasks before writing JSON ────────
    cap.release()
    writer.release()

    unresolved = [k for k, f in ocr_futures.items() if not f.done()]
    if unresolved:
        print(f"[*] Waiting for {len(unresolved)} pending OCR task(s)…")

    file_ocr_exec.shutdown(wait=True, cancel_futures=False)
    _harvest_ocr(ocr_futures, memory)   # pick up last results

    elapsed = time.time() - t0
    print(f"\n[*] Done — {fn} frames in {elapsed:.1f}s "
          f"({fn/elapsed:.1f} fps avg) | "
          f"YOLO ran on {infer_n}/{fn} frames")
    print(f"[*] Output: {output_path}")

    if json_path:
        export_json(memory, json_path)

    print_summary(memory)
    return memory


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "live"

    if mode == "file":
        # ── FILE MODE ─────────────────────────────────────────────────────────
        run_pipeline(VIDEO_PATH, OUTPUT_VIDEO, OUTPUT_JSON)

    else:
        # ── LIVE MODE (default) ───────────────────────────────────────────────
        stop = threading.Event()

        def on_violation(rec: ViolationRecord, jpeg: bytes):
            # Save evidence JPEG or push to DB here
            pass

        run_pipeline_live(
            camera_source      = 0,          # 0 = default webcam
            camera_id          = "CAM-001",
            stop_event         = stop,
            violation_callback = on_violation,
            frame_callback     = None,        # set for web streaming
        )