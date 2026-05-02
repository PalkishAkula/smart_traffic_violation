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
import sys
import importlib.util

import json

import threading

import concurrent.futures

from dataclasses import dataclass, field

from typing import Callable, Optional, List

from urllib.parse import urlparse, urlunparse

import numpy as np

from ultralytics import YOLO

import easyocr



from utils           import (is_rider_on_bike, get_iou, get_iop,

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

# Lowered CONF_PERSON  0.30 → 0.25 and CONF_HELMET 0.35 → 0.30.

# AI-generated test images have unnaturally clean edges; real-world footage

# from phone cameras has compression artifacts, motion blur, and varied

# lighting — models score real riders slightly lower for the same scene.

CONF_MOTORCYCLE = 0.40

CONF_PERSON     = 0.25   # was 0.30

CONF_HELMET     = 0.30   # was 0.35

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

# CRITICAL FIX: replaced INFER_W=416, INFER_H=256 with a single square size.

#

# ROOT CAUSE OF PORTRAIT VIDEO FAILURE

# Old code: cv2.resize(frame, (416, 256)) then pass to YOLO.

# For a portrait 4K frame (e.g. 2160×3840, phone-recorded):

#   scale = min(416/2160, 256/3840) = 0.067

#   effective content width = 2160 × 0.067 = ~144 px

# Riders in a 144-px-wide strip are invisible to YOLO — zero detections.

#

# NEW APPROACH: pass the original frame directly to YOLO with imgsz=INFER_SIZE.

# YOLO handles its own aspect-ratio-preserving letterboxing internally and

# returns bounding boxes already in original-frame coordinates.

# No manual cv2.resize, no sx/sy scale factors needed.

#

# 640×640 is the YOLOv8 standard inference size and works correctly for both

# landscape (1280×720) and portrait (2160×3840) source frames.

INFER_SIZE = 640



# ── Plate search box extension ────────────────────────────────────────────────

PLATE_SEARCH_DOWN_FRAC = 0.40



# ── OCR retry gap (in inference cycles, not display frames) ──────────────────

PLATE_RETRY_INFER_GAP = 15



# ── FILE MODE: run YOLO on every Nth frame (2 = every other frame, fastest) ──

# Lower  = more accurate, slower.   2 is the best balance for most videos.

FILE_PROCESS_EVERY_N = 2



# ── Spatial association ───────────────────────────────────────────────────────

ASSOC_IOU_THRESH = 0.10



# Minimum fraction of a COCO person box that must overlap the motorcycle box.

# This filters out pedestrians standing adjacent to a bike in traffic scenes.

# Real riders: IoP ≈ 0.20–0.50 (legs/hips inside bike box).

# Nearby pedestrians: IoP ≈ 0.0–0.08 (body doesn't touch the bike box).

PERSON_BIKE_IOP_THRESH = 0.12



# ── Preferred licence-plate state codes ──────────────────────────────────────

# Set to the most common state codes seen by your camera location.

# The OCR correction engine will rank these higher when a plate is ambiguous.

# For Vijayawada / Andhra Pradesh: AP is primary, TS (Telangana, bordering

# state) is secondary.  Add 'KA' (Karnataka) if on a highway towards Bengaluru.

PREFERRED_STATES = ['AP', 'TS']



# K OCR key pool (live camera only)
# When key[i] hits rate-limit (HTTP 429), key[i+1] is tried automatically.
# Video upload pipeline does NOT use these keys (uses EasyOCR only).
# Graceful fallback: if the backend key file is missing (e.g. web-server
# deploy without the local secrets file), K_KEY_POOL defaults to [] and
# the pipeline falls through to EasyOCR for all OCR work.
try:
    _BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
    _KEY_POOL_PATH = os.path.join(_BACKEND_DIR, "test_file.py")
    _key_pool_spec = importlib.util.spec_from_file_location("backend_test_file", _KEY_POOL_PATH)
    if _key_pool_spec is None or _key_pool_spec.loader is None:
        raise ImportError(f"Key pool module not found at {_KEY_POOL_PATH}")
    _key_pool_module = importlib.util.module_from_spec(_key_pool_spec)
    _key_pool_spec.loader.exec_module(_key_pool_module)
    K_KEY_POOL = getattr(_key_pool_module, "K_KEY_POOL", [])
except Exception as _kp_err:
    print(f"[*] K key pool not loaded ({_kp_err}) — using EasyOCR only")
    K_KEY_POOL = []

# Delay before the first K OCR request for a newly detected live violation.
# Applies only in live camera mode (this thread) and only to the first attempt.
LIVE_K_DELAY_SECONDS = 30.0



# ── Webcam settings ───────────────────────────────────────────────────────────

WEBCAM_WIDTH  = 1280

WEBCAM_HEIGHT = 720

WEBCAM_FPS    = 30

# Read timeout for network captures so cap.read() does not block forever.
# This allows graceful thread shutdown before capture release.
CAPTURE_READ_TIMEOUT_MSEC = 1000

# Grace window for capture thread to exit after stop signal.
CAPTURE_JOIN_TIMEOUT_SEC = 8.0



# OCR_MAX_WAIT removed — violations are saved to DB immediately as
# PROCESSING. plate_resolved_callback patches the DB record when OCR
# completes. Final-retry exhaustion writes UNDETECTED automatically.



# ── Streaming ─────────────────────────────────────────────────────────────────

LIVE_STREAM_JPEG_QUALITY = 75



# ── Local preview window ──────────────────────────────────────────────────────

SHOW_LOCAL_WINDOW = False



# ── Plate crop upscale for webcam ─────────────────────────────────────────────

LIVE_PLATE_CROP_SCALE = 3.0


# ── Live tracking / dedup controls ───────────────────────────────────────────

# Keep stale live tracks for fewer inference cycles so a bike that left the
# scene does not keep its ID for too long and get reused for a later rider.
LIVE_TRACK_MAX_AGE = 10

# Suppress duplicate live events caused by short-lived track-ID switches.
# If the same violation type appears on a highly overlapping bike box within
# this many inference cycles, it is treated as the same event.
LIVE_EVENT_DEDUP_INFER_GAP = 6
LIVE_EVENT_DEDUP_IOU = 0.45

# Show only recent violation labels on live overlay for an active track.
LIVE_VIOLATION_LABEL_WINDOW_INFER = 6

# Suppress standalone NO_HELMET when a multi-rider violation is active in the
# same inference cycle.
# FIX: Set to False so that NO_HELMET is ALWAYS reported independently,
# even when TRIPLE_RIDING or CO_RIDING_NO_HELMET fires on the same bike.
# Example: 3 unhelmeted riders → all 3 violation types must be recorded.
SUPPRESS_NO_HELMET_ON_MULTI_RIDER = False





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

    """

    Return COCO person detections that are physically on this motorcycle.



    Uses TWO independent criteria — either is sufficient:



    1. IoU >= ASSOC_IOU_THRESH (0.10)

       Catches the standard case where the person box overlaps the bike box.



    2. IoP >= PERSON_BIKE_IOP_THRESH (0.12)

       Intersection-over-Person-area: at least 12 % of the person's body

       must lie inside the motorcycle bounding box.



       WHY IoP AND NOT is_rider_on_bike():

       The old is_rider_on_bike() Check B used bike_w × 2.0, which would

       include pedestrians standing 2 bike-widths away in dense traffic.

       IoP is purely overlap-based: a pedestrian 1 m from a bike has

       IoP ≈ 0 while a real rider always has IoP ≥ 0.20 (legs on the bike).

       This eliminates the "person standing nearby counted as triple rider"

       false-positive in traffic scenes.

    """

    result = []

    for p in persons:

        iou = get_iou(p[:4], bike_box[:4])

        iop = get_iop(p[:4], bike_box[:4])

        if iou >= ASSOC_IOU_THRESH or iop >= PERSON_BIKE_IOP_THRESH:

            result.append(p)

    return result



def _dets_on_bike(dets, bike_box):

    """

    Associate helmet / no-helmet / plate detections to a motorcycle.



    Uses is_rider_on_bike() (x-centre + tightened vertical-overlap check).

    IoP is NOT used here because head-sized boxes are small and typically sit

    ABOVE the bike box — their area overlap with the bike box is near zero

    even for real riders.  The x-centre check (Check A in is_rider_on_bike)

    is the correct filter: a pedestrian's head 1+ bike-widths away has its

    x-centre clearly outside the bike's horizontal span.

    """

    return [d for d in dets

            if (get_iou(d[:4], bike_box[:4]) >= ASSOC_IOU_THRESH

                or is_rider_on_bike(d[:4], bike_box))]



def _assign_exclusive(persons, helmets, no_helmets, bike_boxes,
                      plates=None):
    """
    Exclusively assign each person / helmet / no-helmet / plate detection
    to the ONE bike with the highest overlap score.

    WHY THIS IS NEEDED
    ------------------
    _persons_on_bike() and _dets_on_bike() each test a detection independently
    against every bike using a simple threshold.  When two bikes are close, the
    same no-helmet or person detection can pass the threshold for BOTH bikes —
    contaminating Bike A's lists with Bike B's riders.

    Typical failure: Bike A has 2 riders (both no-helmet) + Bike B has 1
    no-helmet rider nearby.  Without exclusive assignment, Bike A's nhon list
    gets 3 entries → head_count=3 → FALSE TRIPLE RIDING.

    FIX: compute a scalar score for every (detection, bike) pair and assign
    each detection to the SINGLE highest-scoring bike.  A detection that does
    not clear the minimum threshold for any bike is dropped entirely.

    PLATES (new):
    The same contamination happens with plates when two bikes are close.
    Passing plates=list(...) enables exclusive plate assignment so each plate
    goes to exactly one bike.  This prevents Bike B's plate being OCR'd as
    Bike A's violation evidence.

    Returns four dicts keyed by bike index (position in bike_boxes):
        assigned_persons    {idx: [person, ...]}
        assigned_helmets    {idx: [helmet, ...]}
        assigned_no_helmets {idx: [no_helmet, ...]}
        assigned_plates     {idx: [plate, ...]}   <- always present
    """
    n = len(bike_boxes)
    ap  = {i: [] for i in range(n)}
    ah  = {i: [] for i in range(n)}
    anh = {i: [] for i in range(n)}
    apl = {i: [] for i in range(n)}

    if n == 0:
        return ap, ah, anh, apl

    def _best_bike(det, score_fn):
        scores = [score_fn(det, b) for b in bike_boxes]
        best_i = max(range(n), key=lambda i: scores[i])
        return best_i if scores[best_i] > 0.0 else -1

    def _p_score(p, b):
        s = max(get_iou(p[:4], b[:4]), get_iop(p[:4], b[:4]))
        return s if s >= PERSON_BIKE_IOP_THRESH else 0.0

    def _d_score(d, b):
        iou = get_iou(d[:4], b[:4])
        if iou >= ASSOC_IOU_THRESH:
            return iou
        if is_rider_on_bike(d[:4], b):
            # is_rider_on_bike passed but IoU is low (head above bike box).
            # Use 2-D Euclidean distance from detection centre to bike centre
            # as tiebreaker so the detection goes to the spatially closest
            # bike when two bikes are side-by-side OR stacked vertically.
            # (Old code used only x-distance, which failed for bikes arranged
            # diagonally or in narrow lanes where they are separated mainly
            # in the y direction.)
            dx      = (d[0] + d[2]) / 2.0
            dy      = (d[1] + d[3]) / 2.0
            bx_c    = (b[0] + b[2]) / 2.0
            by_c    = (b[1] + b[3]) / 2.0
            bike_w  = max(1.0, b[2] - b[0])
            bike_h  = max(1.0, b[3] - b[1])
            # Normalise distances by bike dimensions so the score is scale-
            # invariant (a head 0.5 bike-widths to the right scores the same
            # regardless of whether the bike is 100 or 300 px wide).
            norm_dist = ((dx - bx_c) ** 2 / bike_w ** 2 +
                         (dy - by_c) ** 2 / bike_h ** 2) ** 0.5
            return max(1e-4, ASSOC_IOU_THRESH * max(0.0, 1.0 - norm_dist))
        return 0.0

    def _pl_score(pl, b):
        """
        Score for assigning a plate detection to a bike.

        Plates sit BELOW or at the bottom of a bike box, so they often
        have low IoU with the bike box itself.  We use a combination of:
          1. IoU with the bike box (direct overlap)
          2. x-centre proximity — a plate whose horizontal centre is inside
             the bike box almost certainly belongs to that bike.
          3. y-centre proximity — plates are near the bike's bottom edge.
        """
        iou = get_iou(pl[:4], b[:4])
        if iou >= ASSOC_IOU_THRESH:
            return iou
        px_c = (pl[0] + pl[2]) / 2.0
        py_c = (pl[1] + pl[3]) / 2.0
        bx1, by1, bx2, by2 = b[0], b[1], b[2], b[3]
        bike_w = max(1.0, bx2 - bx1)
        bike_h = max(1.0, by2 - by1)
        x_margin = bike_w * 0.15
        if not (bx1 - x_margin <= px_c <= bx2 + x_margin):
            return 0.0
        if py_c < by1 + bike_h * 0.40:
            return 0.0   # plate is above mid-bike — unlikely to be this bike
        y_dist = max(0.0, py_c - by2)
        return max(1e-4, ASSOC_IOU_THRESH * max(0.0, 1.0 - y_dist / (bike_h * 0.5 + 1.0)))

    for p in persons:
        i = _best_bike(p, _p_score)
        if i >= 0:
            ap[i].append(p)
    for h in helmets:
        i = _best_bike(h, _d_score)
        if i >= 0:
            ah[i].append(h)
    for nh in no_helmets:
        i = _best_bike(nh, _d_score)
        if i >= 0:
            anh[i].append(nh)
    for pl in (plates or []):
        i = _best_bike(pl, _pl_score)
        if i >= 0:
            apl[i].append(pl)

    return ap, ah, anh, apl


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

               fps_infer:   float = 0.0,

               history_window_infer: Optional[int] = None) -> np.ndarray:

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

                  if (r.track_id in active_ids
                      and (history_window_infer is None
                           or r.frame_number >= (snap.infer_count - history_window_infer)))}



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



    # ── HUD ──────────────────────────────────────────────────────────────────

    h = frame.shape[0]

    _txt(frame, f"Display:{fps_display:.0f}fps  Infer:{fps_infer:.0f}fps",

         (10, h - 12), (170, 170, 170), scale=0.45, thick=1)

    return frame





# ══════════════════════════════════════════════════════════════════════════════

# Utility

# ══════════════════════════════════════════════════════════════════════════════



def capture_violation_crop(frame, bike_box, extra_boxes=None,
                           side_pad=0.06, top_pad=0.0, bottom_pad=0.03):

    h, w = frame.shape[:2]

    boxes = [bike_box[:4]]
    if extra_boxes:
        for box in extra_boxes:
            if box is None or len(box) < 4:
                continue
            boxes.append(box[:4])

    x1 = min(int(b[0]) for b in boxes)
    y1 = min(int(b[1]) for b in boxes)
    x2 = max(int(b[2]) for b in boxes)
    y2 = max(int(b[3]) for b in boxes)

    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    px = int(bw * side_pad)
    py_top = int(bh * top_pad)
    py_bottom = int(bh * bottom_pad)

    crop = frame[
        max(0, y1 - py_top):min(h, y2 + py_bottom),
        max(0, x1 - px):min(w, x2 + px)
    ]

    return crop if crop.size > 0 else frame.copy()


def capture_annotated_violation_crop(frame, bike_box, tracked, persons,
                                     helmets, no_helmets, plates, memory,
                                     related_boxes=None):

    annotated = draw_frame(
        frame.copy(),
        DetectionSnapshot(
            tracked=list(tracked),
            persons=list(persons),
            helmets=list(helmets),
            no_helmets=list(no_helmets),
            plates=list(plates),
            infer_count=0,
            infer_time=0.0,
        ),
        memory,
        fps_display=0.0,
        fps_infer=0.0,
    )
    return capture_violation_crop(annotated, bike_box,
                                  extra_boxes=related_boxes)



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



# Minimum OCR confidence to accept a plate reading.
OCR_MIN_ACCEPT_CONF = 0.20

def _harvest_ocr(ocr_futures: dict, memory: ViolationMemory,
                 plate_resolved_cb=None):
    """
    Harvest completed OCR futures.

    KEY DESIGN — 3-TUPLE KEY: (tid, vtype, record_id)
    --------------------------------------------------
    ocr_futures uses (tid, vtype, record_id) as the key with a bare Future
    as the value.  Including record_id in the KEY means each record has its
    own unique slot — no two records ever share a slot even when they have
    the same (tid, vtype) due to track reuse.

    Previously the key was (tid, vtype) and the value was (Future, record_id).
    When the Royal Enfield's NO_HELMET OCR was submitted at frame 8, it
    overwrote Honda's OCR future in the dict (same 2-tuple key, different
    record).  Honda's future completed with AP16DC0119 but nobody harvested
    it — the key was gone.  The 3-tuple key completely eliminates this race.

    record_id is extracted directly from the key for memory.get_by_id().
    """
    for key in [k for k, f in ocr_futures.items() if f.done()]:

        tid, vtype, record_id = key

        if not vtype:
            print(f"  [OCR WARN] Discarding future with invalid vtype for Track-{tid}")
            ocr_futures.pop(key, None)
            continue

        try:

            pt, pc, _ = ocr_futures.pop(key).result(timeout=0)

            # Route result to the exact record that submitted this OCR task.
            rec = memory.get_by_id(record_id)
            if rec is None:
                continue

            if pt == "UNDETECTED":

                if rec.plate_text is None:
                    rec.plate_text = "UNDETECTED"
                    rec.plate_conf = 0.0
                    print(f"  [OCR] Track-{tid:03d} {vtype} → UNDETECTED")
                    if plate_resolved_cb is not None:
                        try:
                            plate_resolved_cb(rec)
                        except Exception as _e:
                            print(f"  [OCR] plate_resolved_cb error: {_e}")

            elif pt and pc >= OCR_MIN_ACCEPT_CONF:

                updated_recs, previous_plate, accepted = memory.apply_event_plate_result(
                    record_id, pt, pc)
                if not accepted:
                    prev_text, prev_conf = previous_plate or ("UNKNOWN", 0.0)
                    print(f"  [OCR SKIP weaker] Track-{tid:03d} {vtype} "
                          f"→ {pt} ({pc:.2f}) kept {prev_text} ({prev_conf:.2f})")
                    continue

                if any(r.record_id == rec.record_id for r in updated_recs):
                    print(f"  [PLATE RETRY ✓] Track-{tid:03d} "
                          f"{vtype} → {pt} (conf={pc:.2f})")

                if previous_plate is not None and previous_plate[0] != pt:
                    print(f"  [OCR UPGRADE ✓] Track-{tid:03d} event "
                          f"{previous_plate[0]} → {pt} ({pc:.2f})")

                for sibling in updated_recs:
                    if sibling.record_id != rec.record_id:
                        print(f"  [OCR SHARE ✓] Track-{sibling.track_id:03d} "
                              f"{sibling.violation_type} → {pt} ({pc:.2f})")

                print(f"  [OCR ✓] Track-{tid:03d} {vtype} → {pt} ({pc:.2f})")

                if plate_resolved_cb is not None:
                    for sibling in updated_recs:
                        try:
                            plate_resolved_cb(sibling)
                        except Exception as _e:
                            print(f"  [OCR] plate_resolved_cb error: {_e}")

            elif pt:

                print(f"  [OCR SKIP low-conf] Track-{tid:03d} {vtype} "
                      f"→ {pt} conf={pc:.2f} < {OCR_MIN_ACCEPT_CONF}")

        except Exception as e:

            print(f"  [OCR ERR] {key}: {e}")

            ocr_futures.pop(key, None)

    # ── Final-retry exhaustion guard ─────────────────────────────────────────
    for rec in memory.all_records():
        if (rec.plate_text is None
                and rec.plate_retries >= ViolationMemory.MAX_PLATE_RETRIES):
            rec.plate_text = "UNDETECTED"
            rec.plate_conf = 0.0
            print(f"  [OCR EXHAUSTED] Track-{rec.track_id:03d} "
                  f"{rec.violation_type} → UNDETECTED (retries exhausted)")
            if plate_resolved_cb is not None:
                try:
                    plate_resolved_cb(rec)
                except Exception as _e:
                    print(f"  [OCR] plate_resolved_cb exhausted error: {_e}")





# ══════════════════════════════════════════════════════════════════════════════

# THREAD 1 – CAPTURE

# ══════════════════════════════════════════════════════════════════════════════



def _thread_capture(cap, state: SharedState, stop: threading.Event, cam_id: str):

    """Reads webcam frames and overwrites SharedState.latest_frame continuously."""

    fail = 0

    try:
        while not stop.is_set():
            try:
                ret, frame = cap.read()
            except Exception as e:
                print(f"[CAPTURE:{cam_id}] read error: {e}")
                ret, frame = False, None

            if not ret:
                fail += 1
                if fail >= 30:
                    print(f"[CAPTURE:{cam_id}] 30 consecutive fails — stopping")
                    stop.set()
                    break
                time.sleep(0.005)
                continue

            fail = 0
            state.write_frame(frame)
    finally:
        try:
            cap.release()
        except Exception:
            pass
        print(f"[CAPTURE:{cam_id}] exited")





# ══════════════════════════════════════════════════════════════════════════════

# THREAD 2 – INFERENCE BACKEND  (the batch processing)

# ══════════════════════════════════════════════════════════════════════════════



def _thread_inference(coco_model, helmet_model, plate_model, reader,

                      state: SharedState, memory: ViolationMemory,

                      tracker: SOTTracker, stop: threading.Event,

                      cam_id: str, src_w: int, src_h: int,

                      ocr_executor, ocr_futures: dict, ocr_lock: threading.Lock,

                      violation_cb: Optional[Callable],

                      plate_resolved_cb: Optional[Callable]):

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

    # Recent live events used to suppress duplicate logs when SORT briefly
    # switches track IDs for the same motorcycle in adjacent frames.
    recent_live_events: list[dict] = []



    print(f"[INFER:{cam_id}] started (~{1000//INFERENCE_INTERVAL_MS} runs/s, imgsz={INFER_SIZE})")



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

        # Pass the original frame with imgsz=INFER_SIZE.

        # YOLO letterboxes internally (aspect-ratio-preserving) and returns

        # bounding boxes already in original-frame pixel coordinates.

        # No cv2.resize, no sx/sy scaling needed — this is the portrait fix.

        coco_res   = coco_model(frame,  imgsz=INFER_SIZE, verbose=False)[0]

        helmet_res = helmet_model(frame, imgsz=INFER_SIZE, verbose=False)[0]



        bikes, persons = [], []

        for b in coco_res.boxes:

            cls, conf = int(b.cls[0]), float(b.conf[0])

            x1, y1, x2, y2 = map(int, b.xyxy[0])

            if cls == 3 and conf >= CONF_MOTORCYCLE:

                bikes.append((x1, y1, x2, y2, conf))

            elif cls == 0 and conf >= CONF_PERSON:

                persons.append((x1, y1, x2, y2, conf))



        helmets, no_helmets = [], []

        for b in helmet_res.boxes:

            cls, conf = int(b.cls[0]), float(b.conf[0])

            if conf < CONF_HELMET: continue

            x1, y1, x2, y2 = map(int, b.xyxy[0])

            e = (x1, y1, x2, y2, conf)

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

        # Use only freshly matched tracks (age==0) for violation logic.
        # Confirmed-but-unmatched tracks are kept for drawing continuity, but
        # should not consume per-frame person/helmet/no-helmet assignments.
        tracked_live = [t for t in tracked if t.age == 0]

        recent_live_events = [
            _ev for _ev in recent_live_events
            if (n - _ev['frame_num']) <= LIVE_EVENT_DEDUP_INFER_GAP
        ]



        # ── Harvest done OCR futures ──────────────────────────────────────────

        _harvest_ocr(ocr_futures, memory, plate_resolved_cb)



        # ── Per-bike plate enhancement passes (BEFORE exclusive assignment) ───
        # FIX 1 & 2: All per-bike tight-crop and upscale plate passes now run
        # in a SEPARATE pre-loop BEFORE violation detection.  Previously these
        # passes were inside the per-bike violation loop and appended directly
        # to the shared `plates` list, meaning Bike N saw all plates newly
        # found for Bikes 0..N-1.  This caused:
        #   • Bike 2's IoU deduplication suppressing its own real plate
        #   • OCR for Bike 2 attempting to read Bike 1's plate
        #   • False plate counts in the detection snapshot
        # Collecting into a per-bike temp list and merging into a fresh
        # `plates` copy at the end ensures every bike's passes are isolated.
        _bike_boxes_live = [tuple(t.get_ltrb().astype(int)) for t in tracked_live]
        _per_bike_extra_plates: dict = {i: [] for i in range(len(_bike_boxes_live))}

        for _pbi, _pbike in enumerate(_bike_boxes_live):
            _pbx1, _pby1, _pbx2, _pby2 = _pbike
            _pbh = _pby2 - _pby1

            # Tight bottom-crop pass (2× upscale to catch small plates)
            _tc_y1 = max(0,      int(_pby2 - _pbh * 0.55))
            _tc_y2 = min(src_h,  _pby2 + int(_pbh * 0.15))
            _tc_x1 = max(0,      int(_pbx1 - (_pbx2 - _pbx1) * 0.05))
            _tc_x2 = min(src_w,  int(_pbx2 + (_pbx2 - _pbx1) * 0.05))
            _tc_crop = frame[_tc_y1:_tc_y2, _tc_x1:_tc_x2]
            if _tc_crop.size > 0:
                _tc_h, _tc_w = _tc_crop.shape[:2]
                _tc_up = cv2.resize(_tc_crop,
                                    (int(_tc_w * 2.0), int(_tc_h * 2.0)),
                                    interpolation=cv2.INTER_LANCZOS4)
                for _b in plate_model(_tc_up, imgsz=640, verbose=False)[0].boxes:
                    _conf = float(_b.conf[0])
                    if _conf < CONF_PLATE:
                        continue
                    _px1, _py1, _px2, _py2 = map(int, _b.xyxy[0])
                    _cand = (int(_px1 / 2.0) + _tc_x1,
                             int(_py1 / 2.0) + _tc_y1,
                             int(_px2 / 2.0) + _tc_x1,
                             int(_py2 / 2.0) + _tc_y1, _conf)
                    # Deduplicate only within this bike's own candidate list +
                    # the frame-level plates.  Do NOT look at other bikes' lists.
                    _existing = plates + _per_bike_extra_plates[_pbi]
                    if not any(get_iou(_cand[:4], _ep[:4]) > 0.40
                               for _ep in _existing):
                        _per_bike_extra_plates[_pbi].append(_cand)

            # Upscale search-box pass (LIVE_PLATE_CROP_SCALE ×)
            # Compute sbox without relying on violation-loop variables
            # (use just the bike box extended downward).
            _sx1 = max(0,      _pbx1)
            _sy1 = max(0,      _pby1)
            _sx2 = min(src_w,  _pbx2)
            _sy2 = min(src_h,  _pby2 + int(_pbh * PLATE_SEARCH_DOWN_FRAC))
            _pcrop = frame[_sy1:_sy2, _sx1:_sx2]
            if _pcrop.size > 0:
                _cw, _ch = _pcrop.shape[1], _pcrop.shape[0]
                _up = cv2.resize(_pcrop,
                                 (int(_cw * LIVE_PLATE_CROP_SCALE),
                                  int(_ch * LIVE_PLATE_CROP_SCALE)),
                                 interpolation=cv2.INTER_LANCZOS4)
                for _b in plate_model(_up, verbose=False)[0].boxes:
                    _conf = float(_b.conf[0])
                    if _conf < CONF_PLATE:
                        continue
                    _px1, _py1, _px2, _py2 = map(int, _b.xyxy[0])
                    _cand = (int(_px1 / LIVE_PLATE_CROP_SCALE) + _sx1,
                             int(_py1 / LIVE_PLATE_CROP_SCALE) + _sy1,
                             int(_px2 / LIVE_PLATE_CROP_SCALE) + _sx1,
                             int(_py2 / LIVE_PLATE_CROP_SCALE) + _sy1, _conf)
                    _existing = plates + _per_bike_extra_plates[_pbi]
                    if not any(get_iou(_cand[:4], _ep[:4]) > 0.40
                               for _ep in _existing):
                        _per_bike_extra_plates[_pbi].append(_cand)

        # Merge all per-bike extras into a single combined plates list for the
        # snapshot (display thread shows them all) while keeping per-bike lists
        # separate for exclusive assignment.
        _all_extra_plates = [p
                             for _pbi_plates in _per_bike_extra_plates.values()
                             for p in _pbi_plates]
        plates_for_snapshot = plates + _all_extra_plates

        # ── Exclusive pre-assignment (prevents cross-bike contamination) ─────
        # Persons, helmets, no-helmets AND plates are each assigned to exactly
        # ONE bike.  Plates are built from frame-level detections + this bike's
        # own enhancement passes only — no other bike's extra plates leak in.
        # Build a flat plate list for _assign_exclusive (it assigns each plate
        # to the best bike; per-bike extras are already spatially isolated but
        # the frame-level plates still need exclusive assignment).
        _ap_live, _ah_live, _anh_live, _apl_live = _assign_exclusive(
            persons, helmets, no_helmets, _bike_boxes_live,
            plates=plates_for_snapshot)

        # ── Per-bike violation detection ──────────────────────────────────────

        for _bi_live, trk in enumerate(tracked_live):

            bike  = _bike_boxes_live[_bi_live]

            tid   = trk.track_id

            pon   = _ap_live[_bi_live]

            hon   = _ah_live[_bi_live]

            nhon  = _anh_live[_bi_live]

            # FIX 3: Use exclusively-assigned plates for this bike.
            # Old code: plon = _dets_on_bike(plates, bike) which included
            # plates newly appended for ALL previous bikes in the loop.
            # New code: _apl_live[_bi_live] contains only plates whose
            # geometric centre is closest to THIS bike via _assign_exclusive.
            plon  = _apl_live[_bi_live]

            sbox  = _plate_search_box(bike, pon, hon, nhon, src_h)

            # ── Async OCR submit ──────────────────────────────────────────────

            def _ocr(tid_=tid, vtype_="", plates_=plon, f_=frame, s_=sbox,
                     b_=bike, pon_=pon, hon_=hon, nhon_=nhon, plon_=plon):
                if not vtype_:
                    print(f"  [OCR WARN] _ocr called without vtype for Track-{tid_} — skipped")
                    return

                _current_rec = memory.get(tid_, vtype_)
                if _current_rec is None:
                    return

                # 3-TUPLE KEY: (tid, vtype, record_id) — each record owns its
                # own unique slot so track-reuse never overwrites a prior future.
                key = (tid_, vtype_, _current_rec.record_id)

                if key in ocr_futures and not ocr_futures[key].done():
                    return   # this record's OCR task is already running

                _pl = list(plates_);  _fr = f_.copy();  _s = s_
                _rec = _current_rec
                _delay_first_k = (
                    bool(K_KEY_POOL)
                    and _rec.plate_text is None
                    and _rec.plate_retries == 0
                )

                def _task():

                    if _delay_first_k and LIVE_K_DELAY_SECONDS > 0:
                        time.sleep(LIVE_K_DELAY_SECONDS)

                    with ocr_lock:
                        _k_img = (capture_violation_crop(
                                         _fr, b_, extra_boxes=[*pon_, *hon_, *nhon_, *plon_]
                                     )
                                     if K_KEY_POOL else None)

                        return get_plate_for_bike(
                            _pl, b_, _fr, reader,
                            PREFERRED_STATES, _s,
                            not bool(K_KEY_POOL),
                            K_KEY_POOL or None,
                            _k_img)

                ocr_futures[key] = ocr_executor.submit(_task)



            # ── Log violation helper ──────────────────────────────────────────

            # DEFAULT-ARG CAPTURE: captures tid, bike, n at the time _log is

            # defined (each loop iteration), not when it may be called later.

            # This prevents the classic Python closure-in-loop bug where all

            # closures see the final value of the loop variable.

            def _log(vtype, violated,

                     _tid=tid, _bike=bike, _n=n, _frame=frame,
                     _tracked=tracked, _persons=persons, _helmets=helmets,
                     _no_helmets=no_helmets, _plates=plon,
                     _pon=pon, _hon=hon, _nhon=nhon, _plon=plon):

                if not violated or memory.has(_tid, vtype):
                    return

                # Cross-track dedup: suppress near-duplicate events when
                # track IDs switch for the same motorcycle in adjacent frames.
                _dup = any(
                    (_ev['vtype'] == vtype)
                    and ((_n - _ev['frame_num']) <= LIVE_EVENT_DEDUP_INFER_GAP)
                    and (get_iou(_bike[:4], _ev['bike_box']) >= LIVE_EVENT_DEDUP_IOU)
                    for _ev in recent_live_events
                )
                if _dup:
                    return

                rec = ViolationRecord(_tid, vtype, None, 0.0, _n)

                memory.add(rec)
                recent_live_events.append({
                    'track_id': _tid,
                    'vtype': vtype,
                    'frame_num': _n,
                    'bike_box': _bike[:4],
                })

                _ocr(tid_=_tid, vtype_=vtype)

                # Fire violation_callback IMMEDIATELY with plate=None.
                # Backend saves as PROCESSING; plate_resolved_cb patches it later.
                if violation_cb is not None:
                    _crop = capture_annotated_violation_crop(
                        _frame, _bike, _tracked, _persons,
                        _helmets, _no_helmets, _plates, memory,
                        related_boxes=[*_pon, *_hon, *_nhon, *_plon]
                    )
                    try:
                        violation_cb(rec, encode_jpeg(_crop))
                    except Exception as _e:
                        print(f"  [INFER:{cam_id}] violation_cb error: {_e}")



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

            # TRACK-REUSE FIX (live pipeline)
            # ─────────────────────────────────────────────────────────────────
            # The SORT tracker reuses track IDs when a new motorcycle enters
            # the frame at the same screen position as a recently departed one.
            #
            # Symptom: Honda (1 rider) → Track-001 → NO_HELMET logged.
            # Honda leaves.  Royal Enfield (3 riders) enters same position →
            # SORT assigns Track-001.  ViolationMemory already has
            # (Track-001, NO_HELMET) → _log() skips it → missing violation.
            #
            # Detection: if TRIPLE_RIDING just fired on a track that previously
            # had NO_HELMET but NOT TRIPLE_RIDING, the rider count changed
            # dramatically — this is almost certainly a different physical bike.
            # Invalidate the stale single-rider records so they are re-logged
            # with the correct plate of the new multi-rider bike.
            #
            # SAFETY: Only invalidate if we're SURE this is truly triple riding.
            # Verify: coco_count >= 3 (required by triple_riding.py).
            # Extra guard: len(pon) >= 3 prevents false invalidation from 2-rider
            # frames where helmet model sees 2 distinct heads.
            if tv and not memory.has(tid, V_TRIPLE) and len(pon) >= 3:
                memory.invalidate_single_rider_violations(tid)

            _log(V_TRIPLE, tv)

            if tv:

                # FIX: when triple riding is confirmed and COCO has no co-rider
                # index (coi empty), any no-helmet detection means a pillion
                # is unhelmeted — use >=1, not >1.
                co_v = any(p_nh[i] for i in coi) if coi else len(nhon)>=1

            else:

                cv2_v, _ = check_co_riding(pon, hon, nhon, bike)

                co_v = cv2_v

            _log(V_CO_RIDING, co_v)

            # NO_HELMET means the rider/driver has no helmet.
            # Co-rider helmet failures are reported as CO_RIDING_NO_HELMET.
            if di is None:
                nh_v = False
            else:
                nh_v, _ = check_helmet_violation(dnh, hon)

            # SUPPRESS when TRIPLE_RIDING: If 3+ riders, co-rider helmet status
            # is already reported as CO_RIDING_NO_HELMET. Don't also report
            # NO_HELMET for the driver — the core violation is the pillion(s).
            # If driver is unhelmeted, it's already captured by CO_RIDING logic.
            if tv:
                nh_v = False

            _log(V_NO_HELMET, nh_v)



            # OCR retries

            for vt in (V_TRIPLE, V_CO_RIDING, V_NO_HELMET):

                if memory.needs_plate_retry(tid, vt, frame_num=n,

                                            retry_frame_gap=PLATE_RETRY_INFER_GAP):

                    _retry_rec = memory.get(tid, vt)

                    if _retry_rec is None:
                        continue

                    # 3-tuple key: each record has its own slot
                    key = (tid, vt, _retry_rec.record_id)

                    already_running = (key in ocr_futures

                                       and not ocr_futures[key].done())

                    if not already_running:

                        memory.increment_retry(tid, vt, frame_num=n)

                        _ocr(tid_=tid, vtype_=vt)



        # ── Write snapshot for display thread ─────────────────────────────────

        state.write_detections(DetectionSnapshot(

            tracked=list(tracked), persons=persons, helmets=helmets,

            no_helmets=no_helmets, plates=plates_for_snapshot,

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

                    frame_cb: Optional[Callable]):

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

        annotated = draw_frame(
            frame, snap, memory, fps_d, fps_i,
            history_window_infer=LIVE_VIOLATION_LABEL_WINDOW_INFER
        )



        # Timestamp overlay

        _txt(annotated, f"{cam_id}  {time.strftime('%H:%M:%S')}",

             (10, annotated.shape[0]-32), (200,200,200), scale=0.45, thick=1)



        # Violation callbacks fire immediately from _thread_inference.
        # plate_resolved_cb patches the DB when OCR completes.
        # No dispatch gating needed in the display thread.



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

    camera_source:           int | str,

    camera_id:               str,

    stop_event:              threading.Event,

    violation_callback:      Callable[[ViolationRecord, bytes], None],

    plate_resolved_callback: Optional[Callable] = None,

    frame_callback:          Optional[Callable[[bytes], None]] = None,

    reconnect_on_fail:       bool = True,

    max_reconnect_wait:      int  = 10,

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

    def _candidate_sources(src: int | str) -> list:
        if not isinstance(src, str):
            return [src]

        s = src.strip()
        if not (s.startswith("http://") or s.startswith("https://")):
            return [src]

        u = urlparse(s)
        if not u.netloc:
            return [src]

        base = urlunparse((u.scheme, u.netloc, "", "", "", ""))

        # IP Webcam (Android) commonly serves MJPEG at /video
        candidates = [
            s,
            base + "/video",
            base + "/videofeed",
            base + "/mjpegfeed",
            base + "/mjpeg",
            base + "/?action=stream",
        ]

        # De-dupe while preserving order
        out = []
        seen = set()
        for c in candidates:
            if c not in seen:
                out.append(c)
                seen.add(c)
        return out

    def _open():

        for src in _candidate_sources(camera_source):
            # FIX: integer sources (webcam index) use DirectShow on Windows.
            # The default MSMF backend enumerates all media devices and takes
            # 5-10 s to open.  CAP_DSHOW skips that and opens in < 1 s.
            # URL sources (IP cameras) always use the default backend.
            if isinstance(src, int):
                c = cv2.VideoCapture(src, cv2.CAP_DSHOW)
            else:
                c = cv2.VideoCapture(src)
            if not c.isOpened():
                try:
                    c.release()
                except Exception:
                    pass
                continue

            c.set(cv2.CAP_PROP_FRAME_WIDTH,  WEBCAM_WIDTH)

            c.set(cv2.CAP_PROP_FRAME_HEIGHT, WEBCAM_HEIGHT)

            c.set(cv2.CAP_PROP_FPS,          WEBCAM_FPS)

            c.set(cv2.CAP_PROP_BUFFERSIZE,   1)

            if not isinstance(src, int) and hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
                c.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, CAPTURE_READ_TIMEOUT_MSEC)

            w = int(c.get(cv2.CAP_PROP_FRAME_WIDTH))

            h = int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))

            print(f"[LIVE:{camera_id}] Camera {w}×{h} (source={src})")

            return c, w, h

        return None, 0, 0



    cap, src_w, src_h = _open()

    if cap is None:

        if not reconnect_on_fail:
            print(f"[LIVE:{camera_id}] Cannot open camera: {camera_source}")
            return ViolationMemory()

        print(f"[LIVE:{camera_id}] Cannot open camera: {camera_source} — retrying…")
        rw = 1
        while not stop_event.is_set() and cap is None:
            time.sleep(rw)
            cap, src_w, src_h = _open()
            if cap is not None:
                break
            rw = min(rw * 2, max_reconnect_wait)

        if cap is None:
            print(f"[LIVE:{camera_id}] Camera open retries exhausted: {camera_source}")
            return ViolationMemory()


    # ── Shared objects ────────────────────────────────────────────────────────

    state   = SharedState()

    memory  = ViolationMemory()

    tracker = SOTTracker(max_age=LIVE_TRACK_MAX_AGE, iou_thresh=0.25)



    ocr_lock    = threading.Lock()

    ocr_futures: dict = {}



    # OCR runs in a separate thread — 1 worker ensures EasyOCR is never called

    # concurrently, which would cause crashes or wrong results

    ocr_exec = concurrent.futures.ThreadPoolExecutor(

        max_workers=1, thread_name_prefix="ocr")



    # vcrops/vclock removed — violations now fire immediately in _thread_inference



    # ── Create threads ────────────────────────────────────────────────────────

    t1 = threading.Thread(target=_thread_capture,

                          args=(cap, state, stop_event, camera_id),

                          name=f"t1_capture_{camera_id}", daemon=True)



    t2 = threading.Thread(target=_thread_inference,

                          args=(coco_m, helm_m, plat_m, reader,

                                state, memory, tracker, stop_event, camera_id,

                                src_w, src_h,

                                ocr_exec, ocr_futures, ocr_lock,

                                violation_callback, plate_resolved_callback),

                          name=f"t2_infer_{camera_id}", daemon=True)



    t3 = threading.Thread(target=_thread_display,

                          args=(state, memory, stop_event, camera_id,

                                frame_callback),

                          name=f"t3_display_{camera_id}", daemon=True)



    print(f"\n[LIVE:{camera_id}] ── Starting 3-Thread Pipeline ──")

    print(f"  Thread 1 – Capture  : full camera speed")

    print(f"  Thread 2 – Inference: every {INFERENCE_INTERVAL_MS} ms  "

          f"(~{1000//INFERENCE_INTERVAL_MS} runs/s, imgsz={INFER_SIZE}×{INFER_SIZE})")

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

        t2.join(timeout=3.0)
        t3.join(timeout=3.0)

        t1.join(timeout=CAPTURE_JOIN_TIMEOUT_SEC)
        if t1.is_alive():
            print(f"[LIVE:{camera_id}] Capture thread still alive after timeout; forcing capture release")
            try:
                cap.release()
            except Exception:
                pass
            t1.join(timeout=2.0)

        if SHOW_LOCAL_WINDOW:

            cv2.destroyAllWindows()

        ocr_exec.shutdown(wait=True, cancel_futures=False)

        _harvest_ocr(ocr_futures, memory, plate_resolved_callback)

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



    # Detect portrait vs landscape for informational logging

    orientation = "portrait" if src_h > src_w else "landscape"



    print(f"[*] Input : {src_w}×{src_h} @ {src_fps:.0f} fps  "

          f"({total} frames)  [{orientation}]")

    print(f"[*] Config: inference every {FILE_PROCESS_EVERY_N} frames | "

          f"imgsz={INFER_SIZE}×{INFER_SIZE} square | async OCR")



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

        _current_rec = memory.get(tid_, vtype_)
        if _current_rec is None:
            return

        # 3-TUPLE KEY: each record owns its own slot — no overwrite possible.
        key = (tid_, vtype_, _current_rec.record_id)

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

            # Pass frame directly — YOLO letterboxes internally.

            # Returns coords in original frame space; no scaling needed.

            coco_res   = coco_m(frame, imgsz=INFER_SIZE, verbose=False)[0]

            helmet_res = helm_m(frame, imgsz=INFER_SIZE, verbose=False)[0]

            plate_boxes = plat_m(frame, verbose=False)[0].boxes  # full-res



            # ── Parse detections ────────────────────────────────────────────

            bikes, persons = [], []

            for b in coco_res.boxes:

                cls, conf = int(b.cls[0]), float(b.conf[0])

                x1, y1, x2, y2 = map(int, b.xyxy[0])

                if cls == 3 and conf >= CONF_MOTORCYCLE:

                    bikes.append((x1, y1, x2, y2, conf))

                elif cls == 0 and conf >= CONF_PERSON:

                    persons.append((x1, y1, x2, y2, conf))



            helmets, no_helmets = [], []

            for b in helmet_res.boxes:

                cls, conf = int(b.cls[0]), float(b.conf[0])

                if conf < CONF_HELMET: continue

                x1, y1, x2, y2 = map(int, b.xyxy[0])

                e = (x1, y1, x2, y2, conf)

                if cls == 1:   helmets.append(e)

                elif cls == 2: no_helmets.append(e)



            plates = []

            for b in plate_boxes:

                conf = float(b.conf[0])

                if conf >= CONF_PLATE:

                    x1, y1, x2, y2 = map(int, b.xyxy[0])

                    plates.append((x1, y1, x2, y2, conf))



            # ── Track ──────────────────────────────────────────────────────

            tracked = tracker.associate(

                [([m[0],m[1],m[2],m[3]], m[4]) for m in bikes])



            # ── Harvest completed OCR futures ──────────────────────────────

            _harvest_ocr(ocr_futures, memory)



            # ── Per-bike plate enhancement passes (file pipeline parity) ──
            _bike_boxes_file = [tuple(t.get_ltrb().astype(int)) for t in tracked]
            _per_bike_extra_plates: dict = {i: [] for i in range(len(_bike_boxes_file))}

            for _pbi, _pbike in enumerate(_bike_boxes_file):
                _pbx1, _pby1, _pbx2, _pby2 = _pbike
                _pbh = _pby2 - _pby1

                _tc_y1 = max(0, int(_pby2 - _pbh * 0.55))
                _tc_y2 = min(src_h, _pby2 + int(_pbh * 0.15))
                _tc_x1 = max(0, int(_pbx1 - (_pbx2 - _pbx1) * 0.05))
                _tc_x2 = min(src_w, int(_pbx2 + (_pbx2 - _pbx1) * 0.05))
                _tc_crop = frame[_tc_y1:_tc_y2, _tc_x1:_tc_x2]
                if _tc_crop.size > 0:
                    _tc_h, _tc_w = _tc_crop.shape[:2]
                    _tc_up = cv2.resize(
                        _tc_crop,
                        (int(_tc_w * 2.0), int(_tc_h * 2.0)),
                        interpolation=cv2.INTER_LANCZOS4,
                    )
                    for _b in plat_m(_tc_up, imgsz=640, verbose=False)[0].boxes:
                        _conf = float(_b.conf[0])
                        if _conf < CONF_PLATE:
                            continue
                        _px1, _py1, _px2, _py2 = map(int, _b.xyxy[0])
                        _cand = (
                            int(_px1 / 2.0) + _tc_x1,
                            int(_py1 / 2.0) + _tc_y1,
                            int(_px2 / 2.0) + _tc_x1,
                            int(_py2 / 2.0) + _tc_y1,
                            _conf,
                        )
                        _existing = plates + _per_bike_extra_plates[_pbi]
                        if not any(get_iou(_cand[:4], _ep[:4]) > 0.40 for _ep in _existing):
                            _per_bike_extra_plates[_pbi].append(_cand)

                _sx1 = max(0, _pbx1)
                _sy1 = max(0, _pby1)
                _sx2 = min(src_w, _pbx2)
                _sy2 = min(src_h, _pby2 + int(_pbh * PLATE_SEARCH_DOWN_FRAC))
                _pcrop = frame[_sy1:_sy2, _sx1:_sx2]
                if _pcrop.size > 0:
                    _cw, _ch = _pcrop.shape[1], _pcrop.shape[0]
                    _up = cv2.resize(
                        _pcrop,
                        (int(_cw * LIVE_PLATE_CROP_SCALE), int(_ch * LIVE_PLATE_CROP_SCALE)),
                        interpolation=cv2.INTER_LANCZOS4,
                    )
                    for _b in plat_m(_up, verbose=False)[0].boxes:
                        _conf = float(_b.conf[0])
                        if _conf < CONF_PLATE:
                            continue
                        _px1, _py1, _px2, _py2 = map(int, _b.xyxy[0])
                        _cand = (
                            int(_px1 / LIVE_PLATE_CROP_SCALE) + _sx1,
                            int(_py1 / LIVE_PLATE_CROP_SCALE) + _sy1,
                            int(_px2 / LIVE_PLATE_CROP_SCALE) + _sx1,
                            int(_py2 / LIVE_PLATE_CROP_SCALE) + _sy1,
                            _conf,
                        )
                        _existing = plates + _per_bike_extra_plates[_pbi]
                        if not any(get_iou(_cand[:4], _ep[:4]) > 0.40 for _ep in _existing):
                            _per_bike_extra_plates[_pbi].append(_cand)

            _all_extra_plates = [
                p for _pbi_plates in _per_bike_extra_plates.values() for p in _pbi_plates
            ]
            plates_for_snapshot = plates + _all_extra_plates

            # ── Exclusive pre-assignment (prevents cross-bike contamination) ──
            _ap_file, _ah_file, _anh_file, _apl_file = _assign_exclusive(
                persons, helmets, no_helmets, _bike_boxes_file,
                plates=plates_for_snapshot)

            # ── Per-bike violation detection ───────────────────────────────

            for _bi_file, trk in enumerate(tracked):

                bike  = _bike_boxes_file[_bi_file]

                tid   = trk.track_id

                pon   = _ap_file[_bi_file]

                hon   = _ah_file[_bi_file]

                nhon  = _anh_file[_bi_file]

                # Use exclusively-assigned plates (not shared full-frame list)
                plon_file = _apl_file[_bi_file]

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

                         _tid=tid, _plates=plon_file, _frame=frame,

                         _bike=bike, _sbox=sbox, _fn=fn):

                    if not violated or memory.has(_tid, vtype):

                        return

                    # Log immediately with plate=None; OCR fills it async

                    memory.add(ViolationRecord(_tid, vtype, None, 0.0, _fn))

                    _submit_file_ocr(_tid, vtype, _plates, _frame, _bike, _sbox)



                tv, _ = check_triple_riding(pon, hon, nhon)

                # TRACK-REUSE FIX (file pipeline) — see live pipeline comment
                # for full explanation.  Short version: when TRIPLE_RIDING
                # fires for the first time on a track that already has
                # NO_HELMET, that NO_HELMET is almost certainly from a
                # different physical bike that the tracker re-ID'd.  Clear it
                # so it gets freshly logged for the new multi-rider vehicle.
                #
                # SAFETY: Only invalidate if len(pon) >= 3 to prevent false
                # invalidation from 2-rider frames.
                if tv and not memory.has(tid, V_TRIPLE) and len(pon) >= 3:
                    memory.invalidate_single_rider_violations(tid)

                _log(V_TRIPLE, tv)

                if tv:

                    # FIX: >= 1 (not > 1) — triple riding confirmed means
                    # pillion exists; any no-helmet is a co-riding violation.
                    co_v = any(p_nh[i] for i in coi) if coi else len(nhon) >= 1

                else:

                    cv_v, _ = check_co_riding(pon, hon, nhon, bike)

                    co_v = cv_v

                _log(V_CO_RIDING, co_v)

                # NO_HELMET means the rider/driver has no helmet.
                # Co-rider helmet failures are reported as CO_RIDING_NO_HELMET.
                if di is None:
                    nh_v = False
                else:
                    nh_v, _ = check_helmet_violation(dnh, hon)

                # SUPPRESS when TRIPLE_RIDING: If 3+ riders, co-rider helmet status
                # is already reported as CO_RIDING_NO_HELMET. Don't also report
                # NO_HELMET for the driver — the core violation is the pillion(s).
                if tv:
                    nh_v = False

                _log(V_NO_HELMET, nh_v)



                # OCR retries (async — no blocking)

                # FIX: only increment the retry counter if _submit_file_ocr

                # actually queued a new task.  Previously increment_retry()

                # was called unconditionally, burning the retry budget even

                # when the previous OCR future was still running and

                # _submit_file_ocr returned early without submitting.

                for vt in (V_TRIPLE, V_CO_RIDING, V_NO_HELMET):

                    if memory.needs_plate_retry(tid, vt,

                                                frame_num=infer_n,

                                                retry_frame_gap=PLATE_RETRY_INFER_GAP):

                        _retry_rec = memory.get(tid, vt)

                        if _retry_rec is None:
                            continue

                        # 3-tuple key: each record owns its own slot
                        key = (tid, vt, _retry_rec.record_id)

                        already_running = (key in ocr_futures

                                           and not ocr_futures[key].done())

                        if not already_running:

                            memory.increment_retry(tid, vt, frame_num=infer_n)

                            _submit_file_ocr(tid, vt, plates_for_snapshot, frame, bike, sbox)



            # ── Build new snapshot ─────────────────────────────────────────

            snap = DetectionSnapshot(

                tracked=list(tracked), persons=persons,

                helmets=helmets, no_helmets=no_helmets, plates=plates_for_snapshot,

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

    # FINAL CLEANUP: any plate still None after OCR drain means the plate
    # detector/EasyOCR could not read it.  Mark explicitly as UNDETECTED so
    # the web frontend never receives a null/empty plate field.
    for _rec in memory.all_records():
        if _rec.plate_text is None:
            _rec.plate_text = "UNDETECTED"
            _rec.plate_conf = 0.0
            print(f"  [OCR FINAL] Track-{_rec.track_id:03d} "
                  f"{_rec.violation_type} → UNDETECTED (no read after drain)")

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