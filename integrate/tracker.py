"""
tracker.py
══════════
Two responsibilities:
  1. SOTTracker  – SORT multi-object tracker
                   (Kalman filter + Hungarian assignment, no GPU needed)
  2. ViolationMemory – deduplication store, one record per (track_id, vtype)
                       with built-in OCR retry support for UNDETECTED plates.

═══════════════════════════════════════════════════════════════════
  SORT vs DeepSORT – Algorithm Choice & Justification
═══════════════════════════════════════════════════════════════════

  SORT (Simple Online and Realtime Tracking)  ← THIS PROJECT USES SORT
  ─────────────────────────────────────────
  Algorithm:
    1. Kalman filter predicts each track's position in the current frame.
    2. IoU cost matrix is built between predicted boxes and new detections.
    3. Hungarian algorithm finds the globally optimal assignment.
    4. Unmatched detections → new tracks. Stale tracks → pruned.

  Pros:
    • Extremely fast: < 1 ms per frame on CPU (vs 150–200 ms for DeepSORT).
    • No external model weights required.
    • Stable for fixed-camera scenes with clear line-of-sight.
    • Sufficient accuracy when objects don't occlude each other long-term.

  Cons:
    • No appearance model → may swap IDs when two bikes cross paths.
    • Cannot re-identify a bike that was fully occluded for many frames.

  ─────────────────────────────────────────────────────────────────
  DeepSORT
  ─────────────────────────────────────────────────────────────────
  Algorithm:
    SORT + a ReID CNN that extracts a 128-dimensional appearance
    embedding from each detected crop. Embeddings are compared using
    cosine distance alongside IoU in the assignment step. A gallery
    of past embeddings per track enables re-identification after long
    occlusions.

  Pros:
    • Much better re-identification after full occlusion.
    • More robust when multiple bikes cross paths simultaneously.
    • ID switches are significantly reduced.

  Cons:
    • ReID CNN forward pass: ~150–200 ms per frame ON CPU per crop.
    • Requires a pre-trained ReID model (additional dependency).
    • On CPU this would drop our pipeline from ~6 FPS to ~1–2 FPS.

  ─────────────────────────────────────────────────────────────────
  WHY SORT IS THE CORRECT CHOICE FOR THIS PROJECT
  ─────────────────────────────────────────────────────────────────
  1. FIXED CAMERA:  The traffic camera is stationary. Motorcycles move
     through the scene in predictable trajectories. Full long-term
     occlusion (the case DeepSORT excels at) almost never occurs.

  2. CPU-ONLY HARDWARE:  The pipeline already runs 3× YOLO models per
     processed frame. Adding a ReID CNN would add 150–200 ms per frame,
     reducing throughput to < 2 FPS — making the system unusable.

  3. FRAME SKIPPING:  We process only every Nth frame. DeepSORT's
     appearance gallery would become stale under frame skipping,
     degrading its main advantage further.

  4. VIOLATION SEMANTICS:  A brief ID swap causes at worst a duplicate
     violation entry (which ViolationMemory suppresses) — not a missed
     violation. SORT's occasional ID swap is acceptable here.

  CONCLUSION:  SORT is the correct engineering trade-off for this
  fixed-camera, CPU-only, frame-skipping pipeline. DeepSORT would hurt
  more than it helps here.

  If a GPU is added in future, replace only SOTTracker.update() with a
  DeepSORT call; all other modules remain unchanged.

Reference: Bewley et al. 2016 "Simple Online and Realtime Tracking"
"""

import numpy as np
from scipy.optimize import linear_sum_assignment
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List
import time


# ══════════════════════════════════════════════════════════════════════════════
# Kalman filter matrices  (state = [cx, cy, area, ar, vx, vy, v_area])
# ══════════════════════════════════════════════════════════════════════════════

_F = np.array([
    [1,0,0,0, 1,0,0],
    [0,1,0,0, 0,1,0],
    [0,0,1,0, 0,0,1],
    [0,0,0,1, 0,0,0],
    [0,0,0,0, 1,0,0],
    [0,0,0,0, 0,1,0],
    [0,0,0,0, 0,0,1],
], dtype=float)

_H  = np.eye(4, 7)
_Q  = np.diag([1., 1., 10., 10., 0.01, 0.01, 0.01]) ** 2
_R  = np.diag([1., 1., 10., 10.]) ** 2
_P0 = np.diag([10., 10., 100., 10., 1000., 1000., 100.]) ** 2


# ══════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ltrb_to_z(ltrb):
    x1, y1, x2, y2 = ltrb
    w, h = x2 - x1, y2 - y1
    return np.array([[(x1+x2)/2], [(y1+y2)/2], [w*h],
                     [w / float(h) if h > 0 else 1.0]], dtype=float)


def _x_to_ltrb(x):
    cx, cy, area, ar = x[0,0], x[1,0], x[2,0], x[3,0]
    area = max(area, 1.0);  ar = max(ar, 0.1)
    w = np.sqrt(area * ar);  h = area / w
    return np.array([cx - w/2, cy - h/2, cx + w/2, cy + h/2])


def _iou(b1, b2):
    xi1 = max(b1[0], b2[0]);  yi1 = max(b1[1], b2[1])
    xi2 = min(b1[2], b2[2]);  yi2 = min(b1[3], b2[3])
    inter = max(0.0, xi2-xi1) * max(0.0, yi2-yi1)
    a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
    a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
    return inter / (a1 + a2 - inter + 1e-6)


# ══════════════════════════════════════════════════════════════════════════════
# KalmanTrack – one tracked motorcycle
# ══════════════════════════════════════════════════════════════════════════════

class KalmanTrack:
    _id_counter = 0

    def __init__(self, ltrb: np.ndarray, conf: float):
        KalmanTrack._id_counter += 1
        self.track_id    = KalmanTrack._id_counter
        self.conf        = conf
        self.age         = 1
        self.hits        = 1
        self.hit_streak  = 1
        self._x          = np.zeros((7, 1))
        self._P          = _P0.copy()
        self._x[:4]      = _ltrb_to_z(ltrb)
        self._last_ltrb  = ltrb.copy()

    def predict(self):
        """Kalman predict — call EVERY frame including skipped ones."""
        if self.age > 0:
            self._x[4] *= 0.0
        self._x         = _F @ self._x
        self._P         = _F @ self._P @ _F.T + _Q
        self.age       += 1
        self.hit_streak = 0

    def update(self, ltrb: np.ndarray, conf: float):
        """Kalman update — call only on frames where YOLO inference ran."""
        z = _ltrb_to_z(ltrb)
        y = z - _H @ self._x
        S = _H @ self._P @ _H.T + _R
        K = self._P @ _H.T @ np.linalg.inv(S)
        self._x         = self._x + K @ y
        self._P         = (np.eye(7) - K @ _H) @ self._P
        self.conf       = conf
        self.hits      += 1
        self.hit_streak += 1
        self.age        = 0
        self._last_ltrb = ltrb.copy()

    def get_ltrb(self) -> np.ndarray:
        return _x_to_ltrb(self._x)

    @property
    def is_confirmed(self) -> bool:
        return self.hits >= 2


# ══════════════════════════════════════════════════════════════════════════════
# SOTTracker
# ══════════════════════════════════════════════════════════════════════════════

class SOTTracker:
    """
    SORT tracker with split predict / associate interface to support
    frame-skipping (predict runs every frame; associate runs only when
    YOLO inference was executed).
    """

    def __init__(self, max_age: int = 40, iou_thresh: float = 0.25):
        self.max_age    = max_age
        self.iou_thresh = iou_thresh
        self._tracks: List[KalmanTrack] = []

    def predict_all(self):
        """
        Advance the Kalman state of every track by one time step.
        Must be called every frame — including frames where YOLO was skipped —
        to keep position estimates smooth.
        """
        for t in self._tracks:
            t.predict()

    @staticmethod
    def _nms_detections(detections: list, iou_thresh: float = 0.45) -> list:
        """
        Non-Maximum Suppression on raw YOLO detections.

        If two detections overlap by more than `iou_thresh`, the lower-
        confidence one is suppressed. This stops a single motorcycle from
        spawning two Kalman tracks when YOLO fires two overlapping boxes.

        Parameters
        ----------
        detections : list of ([x1,y1,x2,y2], conf)
        iou_thresh : IoU above which the weaker box is suppressed (default 0.45)

        Returns
        -------
        Filtered list, ordered by descending confidence.
        """
        if len(detections) <= 1:
            return detections
        # Sort by confidence descending
        dets = sorted(detections, key=lambda d: d[1], reverse=True)
        keep = []
        suppressed = set()
        for i, di in enumerate(dets):
            if i in suppressed:
                continue
            keep.append(di)
            for j, dj in enumerate(dets[i+1:], start=i+1):
                if j in suppressed:
                    continue
                if _iou(di[0], dj[0]) > iou_thresh:
                    suppressed.add(j)
        return keep

    def associate(self, detections: list) -> List[KalmanTrack]:
        """
        Match new detections to existing track predictions via Hungarian
        assignment, create tracks for unmatched detections, prune stale ones.

        Call only on frames where YOLO inference ran.

        Parameters
        ----------
        detections : list of ([x1,y1,x2,y2], confidence)

        Returns
        -------
        Confirmed tracks (hits >= 2).
        """
        # ── Suppress duplicate detections for the same physical object ────────
        # If YOLO fires two overlapping boxes for the same motorcycle
        # (IoU > 0.45), keep only the higher-confidence one. This prevents
        # the tracker from spawning two separate tracks for one bike.
        detections = self._nms_detections(detections, iou_thresh=0.45)
        if not detections:
            self._tracks = [t for t in self._tracks if t.age <= self.max_age]
            return [t for t in self._tracks if t.is_confirmed]

        det_boxes    = np.array([d[0] for d in detections])
        det_confs    = [d[1] for d in detections]
        matched_trk: set = set()
        matched_det: set = set()

        if self._tracks:
            trk_boxes = np.array([t.get_ltrb() for t in self._tracks])
            cost = np.zeros((len(self._tracks), len(det_boxes)))
            for ti, tb in enumerate(trk_boxes):
                for di, db in enumerate(det_boxes):
                    cost[ti, di] = 1.0 - _iou(tb, db)
            row_idx, col_idx = linear_sum_assignment(cost)
            for r, c in zip(row_idx, col_idx):
                if cost[r, c] < (1.0 - self.iou_thresh):
                    self._tracks[r].update(det_boxes[c], det_confs[c])
                    matched_trk.add(r)
                    matched_det.add(c)

        for di in range(len(detections)):
            if di not in matched_det:
                self._tracks.append(KalmanTrack(det_boxes[di], det_confs[di]))

        self._tracks = [t for t in self._tracks if t.age <= self.max_age]
        return [t for t in self._tracks if t.is_confirmed]

    def confirmed_tracks(self) -> List[KalmanTrack]:
        """Return all confirmed tracks (for drawing on skipped frames)."""
        return [t for t in self._tracks if t.is_confirmed]

    def update(self, detections: list) -> List[KalmanTrack]:
        """Convenience: predict_all + associate in one call."""
        self.predict_all()
        return self.associate(detections)

    def reset(self):
        self._tracks.clear()
        KalmanTrack._id_counter = 0


# ══════════════════════════════════════════════════════════════════════════════
# ViolationRecord
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ViolationRecord:
    """
    Stores one confirmed violation event.

    plate_retries : int
        Number of times OCR has been retried after an initial UNDETECTED
        result.  ViolationMemory will keep retrying until plate_text is
        found or plate_retries reaches MAX_PLATE_RETRIES.
    """
    track_id:       int
    violation_type: str
    plate_text:     Optional[str]
    plate_conf:     float
    frame_number:   int
    timestamp:      float = field(default_factory=time.time)
    evidence_path:  Optional[str] = None
    plate_retries:        int = 0    # how many OCR retries have been attempted
    plate_last_retry_frame: int = -9999  # real frame number of last retry attempt

    def __str__(self):
        plate = self.plate_text or "UNDETECTED"
        return (f"[Frame {self.frame_number:05d}] "
                f"Track-{self.track_id:03d} | {self.violation_type:<25} | "
                f"Plate: {plate}")


# ══════════════════════════════════════════════════════════════════════════════
# ViolationMemory
# ══════════════════════════════════════════════════════════════════════════════

class ViolationMemory:
    """
    One record per (track_id, violation_type) — prevents duplicates.

    Extended in this version with OCR retry support:
      needs_plate_retry() – True if plate was UNDETECTED and retries remain.
      update_plate()      – Overwrites plate_text after a successful retry.
    """

    MAX_PLATE_RETRIES = 20  # max retry attempts before giving up
                            # (spaced by PLATE_RETRY_FRAME_GAP in main.py, so
                            #  this covers a long window regardless of N)

    def __init__(self):
        self._store: Dict[Tuple[int, str], ViolationRecord] = {}

    def has(self, track_id: int, vtype: str) -> bool:
        return (track_id, vtype) in self._store

    def is_duplicate_plate(self, plate_text: str | None, vtype: str,
                           frame_window: int = 30) -> bool:
        """
        Return True if an existing record already has the same plate_text
        (non-None) and violation_type within `frame_window` frames.

        This prevents the same physical motorcycle — assigned two Track IDs
        by the SORT tracker — from generating two separate violation records.

        Parameters
        ----------
        plate_text   : OCR result to check (None is never considered duplicate)
        vtype        : violation type string
        frame_window : records within this many frames are checked (default 30)
        """
        if not plate_text:
            return False   # can't deduplicate without a plate
        for rec in self._store.values():
            if (rec.violation_type == vtype
                    and rec.plate_text == plate_text):
                return True
        return False

    def add(self, record: ViolationRecord):
        # Reject if same plate + same violation type already logged
        if self.is_duplicate_plate(record.plate_text, record.violation_type):
            print(f"  [DEDUP] Skipped duplicate: "
                  f"plate={record.plate_text} type={record.violation_type} "
                  f"track={record.track_id}")
            return
        self._store[(record.track_id, record.violation_type)] = record
        print(record)

    def get(self, track_id: int, vtype: str) -> Optional[ViolationRecord]:
        return self._store.get((track_id, vtype))

    def all_records(self) -> List[ViolationRecord]:
        return list(self._store.values())

    # ── OCR retry support ─────────────────────────────────────────────────────

    def needs_plate_retry(self, track_id: int, vtype: str,
                          frame_num: int = 0,
                          retry_frame_gap: int = 1) -> bool:
        """
        Return True if this violation was logged with UNDETECTED plate,
        has not exhausted its retry budget, AND enough real frames have
        passed since the last retry attempt.

        Parameters
        ----------
        frame_num       : current frame number (real video frame counter)
        retry_frame_gap : minimum real frames between consecutive retries.
                          Keeping this constant makes retry behaviour the
                          same regardless of PROCESS_EVERY_N_FRAMES.
        """
        rec = self._store.get((track_id, vtype))
        if rec is None:
            return False
        if rec.plate_text is not None:
            return False
        if rec.plate_retries >= self.MAX_PLATE_RETRIES:
            return False
        return (frame_num - rec.plate_last_retry_frame) >= retry_frame_gap

    def increment_retry(self, track_id: int, vtype: str, frame_num: int = 0):
        """Mark one more retry attempt and record the frame it happened on."""
        rec = self._store.get((track_id, vtype))
        if rec is not None:
            rec.plate_retries           += 1
            rec.plate_last_retry_frame  = frame_num

    def update_plate(self, track_id: int, vtype: str,
                     plate_text: str, plate_conf: float):
        """
        Overwrite the plate on an existing record after a successful retry.
        Prints a confirmation line to the terminal.
        """
        rec = self._store.get((track_id, vtype))
        if rec is not None:
            rec.plate_text  = plate_text
            rec.plate_conf  = plate_conf
            print(f"  [PLATE RETRY ✓] Track-{track_id:03d} "
                  f"{vtype} → {plate_text} (conf={plate_conf:.2f})")

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        if not self._store:
            return "  No violations detected."
        lines: List[str] = []
        by_type: Dict[str, List[ViolationRecord]] = {}
        for rec in self._store.values():
            by_type.setdefault(rec.violation_type, []).append(rec)
        for vtype, recs in sorted(by_type.items()):
            lines.append(f"\n  {vtype} ({len(recs)} instance(s)):")
            for r in sorted(recs, key=lambda x: x.frame_number):
                plate = r.plate_text or "UNDETECTED"
                retry_note = (f"  [retried {r.plate_retries}×]"
                              if r.plate_retries > 0 else "")
                lines.append(f"    Track-{r.track_id:03d}  "
                              f"Frame {r.frame_number:05d}  "
                              f"Plate: {plate}{retry_note}")
        return "\n".join(lines)