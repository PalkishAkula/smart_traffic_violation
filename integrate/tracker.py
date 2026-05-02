"""
tracker.py
══════════
Two responsibilities:
  1. SOTTracker  – SORT multi-object tracker
                   (Kalman filter + Hungarian assignment, no GPU needed)
  2. ViolationMemory – deduplication store, one record per (track_id, vtype)
                       with built-in OCR retry support for UNDETECTED plates.

CHANGES IN THIS VERSION
-----------------------
1.  KalmanTrack._id_counter is a CLASS variable — it persists between
    pipeline runs in the same process.  When run_pipeline() or
    run_pipeline_live() is called a second time (e.g. web server processing
    a second video), track IDs continue from where the last run left off.
    This means ViolationMemory deduplication (which keys on track_id) still
    works, but track IDs in the JSON report become confusingly large.

    Fix: SOTTracker.reset() now calls KalmanTrack.reset_counter() to bring
    the counter back to 0.  The counter is still a class variable (so all
    KalmanTrack instances share the same sequence within one run), but it is
    explicitly zeroed at the start of each pipeline run via SOTTracker.reset().

2.  SOTTracker.__init__() now calls self.reset() so a freshly constructed
    tracker always starts with counter=0 and an empty track list — even if
    a previous instance left the counter at a large value.

═══════════════════════════════════════════════════════════════════
  SORT vs DeepSORT – Algorithm Choice & Justification
═══════════════════════════════════════════════════════════════════

  SORT is used here.  See previous version's comments for full
  algorithm comparison.  Summary: SORT is the correct trade-off
  for a fixed-camera, CPU-only, frame-skipping pipeline.

Reference: Bewley et al. 2016 "Simple Online and Realtime Tracking"
"""

import itertools
import re
import numpy as np
from scipy.optimize import linear_sum_assignment
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List
import time

# Thread-safe monotonic counter for unique ViolationRecord IDs.
# itertools.count is safe under CPython's GIL; each __next__() is atomic.
_rec_id_counter = itertools.count(1)

_EVENT_PLATE_PATTERN = re.compile(r'^[A-Z]{2}\d{2}[A-Z]{1,3}\d{4}$')


def _plate_rank(plate_text: str | None, plate_conf: float) -> tuple:
    """Rank OCR results for one bike event: full valid plate beats partial text."""
    text = plate_text or ""
    return (1 if _EVENT_PLATE_PATTERN.match(text) else 0, float(plate_conf))


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

    @classmethod
    def reset_counter(cls):
        """
        Reset the global track ID counter to 0.

        Call this at the start of each pipeline run (via SOTTracker.reset())
        so that track IDs in JSON reports always start from 1, regardless of
        how many previous pipeline runs have been executed in the same process.
        """
        cls._id_counter = 0

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
        # Reset the ID counter whenever a new tracker is created so that
        # each pipeline run starts track IDs from 1.
        KalmanTrack.reset_counter()

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
        """
        if len(detections) <= 1:
            return detections
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
        """
        Clear all active tracks and reset the ID counter.

        Call this between pipeline runs to start track IDs from 1 again.
        """
        self._tracks.clear()
        KalmanTrack.reset_counter()


# ══════════════════════════════════════════════════════════════════════════════
# ViolationRecord
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ViolationRecord:
    """
    Stores one confirmed violation event.

    record_id : int
        Globally unique ID assigned at construction via a monotonic counter.
        Used by ViolationMemory.get_by_id() so that OCR futures can update
        the EXACT record they were submitted for, even if the memory store
        was invalidated and a new record was created at the same (track_id,
        violation_type) key (track-reuse scenario).

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
    plate_retries:        int = 0
    plate_last_retry_frame: int = -9999
    record_id:      int   = field(default_factory=lambda: next(_rec_id_counter))

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

    Extended with OCR retry support:
      needs_plate_retry() – True if plate was UNDETECTED and retries remain.
      update_plate()      – Overwrites plate_text after a successful retry.

    OCR RECORD-PINNING
    ------------------
    When a track ID is reused (new physical bike matched to old track), the
    old violation record is removed from _store but kept in _all_records.
    OCR futures carry the record_id of the record they were submitted for.
    _harvest_ocr calls get_by_id(record_id) to update the EXACT record,
    ensuring Honda OCR → Honda record and Royal Enfield OCR → RE record,
    even when both share the same (track_id, violation_type) key.
    """

    MAX_PLATE_RETRIES = 20

    def __init__(self):
        self._store: Dict[Tuple[int, str], ViolationRecord] = {}
        # All records ever added (including removed ones) keyed by record_id.
        # This lets OCR callbacks find the right record even after removal.
        self._all_records: Dict[int, ViolationRecord] = {}

    def has(self, track_id: int, vtype: str) -> bool:
        return (track_id, vtype) in self._store

    def is_duplicate_plate(self, track_id: int, plate_text: str | None,
                           vtype: str) -> bool:
        """
        Return True if an existing record for the SAME track_id already has
        the same plate_text (non-None) and violation_type.
        """
        if not plate_text:
            return False
        for rec in self._store.values():
            if (rec.track_id      == track_id
                    and rec.violation_type == vtype
                    and rec.plate_text     == plate_text):
                return True
        return False

    def add(self, record: ViolationRecord):
        if self.is_duplicate_plate(record.track_id,
                                   record.plate_text,
                                   record.violation_type):
            print(f"  [DEDUP] Skipped duplicate: "
                  f"plate={record.plate_text} type={record.violation_type} "
                  f"track={record.track_id}")
            return
        self._store[(record.track_id, record.violation_type)] = record
        self._all_records[record.record_id] = record   # ← always keep by ID
        print(record)

    def get(self, track_id: int, vtype: str) -> Optional[ViolationRecord]:
        return self._store.get((track_id, vtype))

    def get_by_id(self, record_id: int) -> Optional[ViolationRecord]:
        """
        Return the ViolationRecord with this exact record_id regardless of
        whether it is still in _store (it may have been removed by
        invalidate_single_rider_violations during track reuse).

        Used by _harvest_ocr to pin OCR results to the specific record
        that submitted the OCR task.
        """
        return self._all_records.get(record_id)

    def all_records(self) -> List[ViolationRecord]:
        return list(self._store.values())

    # ── OCR retry support ─────────────────────────────────────────────────────

    def needs_plate_retry(self, track_id: int, vtype: str,
                          frame_num: int = 0,
                          retry_frame_gap: int = 1) -> bool:
        rec = self._store.get((track_id, vtype))
        if rec is None:
            return False
        if rec.plate_text is not None:
            return False
        if rec.plate_retries >= self.MAX_PLATE_RETRIES:
            return False
        return (frame_num - rec.plate_last_retry_frame) >= retry_frame_gap

    def increment_retry(self, track_id: int, vtype: str, frame_num: int = 0):
        rec = self._store.get((track_id, vtype))
        if rec is not None:
            rec.plate_retries          += 1
            rec.plate_last_retry_frame  = frame_num

    def remove(self, track_id: int, vtype: str):
        """
        Remove a record from the active _store but KEEP it in _all_records.

        Any in-flight OCR future that was submitted for this record carries
        its record_id.  When OCR completes, _harvest_ocr calls
        get_by_id(record_id) which finds the record in _all_records and
        updates plate_text on the correct instance — this patches the DB
        entry for the original (Honda) bike even though its memory entry
        has been cleared to make room for the new (Royal Enfield) bike.
        """
        key = (track_id, vtype)
        if key in self._store:
            # Leave in _all_records so OCR callbacks can still resolve it
            del self._store[key]
            print(f"  [MEM REMOVE] Track-{track_id:03d} {vtype} cleared "
                  f"(track reuse / rider-count change detected)")

    def invalidate_single_rider_violations(self, track_id: int):
        """
        When TRIPLE_RIDING is newly detected on a track that previously had
        only single-rider violations, the SORT tracker has almost certainly
        re-assigned the track ID to a different physical motorcycle.

        Remove stale single-rider records (NO_HELMET) for this track so they
        can be freshly logged with the plate of the new bike.

        CO_RIDING_NO_HELMET and TRIPLE_RIDING records are left untouched —
        they will be logged normally by _log() after this call.
        """
        for vtype in ('NO_HELMET',):
            self.remove(track_id, vtype)

    def update_plate(self, track_id: int, vtype: str,
                     plate_text: str, plate_conf: float):
        rec = self._store.get((track_id, vtype))
        if rec is not None:
            rec.plate_text  = plate_text
            rec.plate_conf  = plate_conf
            print(f"  [PLATE RETRY ✓] Track-{track_id:03d} "
                  f"{vtype} → {plate_text} (conf={plate_conf:.2f})")

    def propagate_plate_from_record(self, record_id: int,
                                    plate_text: str,
                                    plate_conf: float) -> List[ViolationRecord]:
        """
        Share one successful OCR result with sibling violations from the same
        bike event (same track_id and frame_number).

        Only unresolved records are updated, so an existing stronger read is
        never overwritten.
        """
        src = self._all_records.get(record_id)
        if src is None:
            return []

        updated: List[ViolationRecord] = []
        for rec in self._store.values():
            if rec.track_id != src.track_id or rec.frame_number != src.frame_number:
                continue
            if rec.record_id != src.record_id and rec.plate_text not in (None, "UNDETECTED"):
                continue
            rec.plate_text = plate_text
            rec.plate_conf = plate_conf
            updated.append(rec)
        return updated

    def event_records(self, record_id: int) -> List[ViolationRecord]:
        """Return active violation records from the same tracked bike event."""
        src = self._all_records.get(record_id)
        if src is None:
            return []
        return [
            rec for rec in self._store.values()
            if rec.track_id == src.track_id and rec.frame_number == src.frame_number
        ]

    def apply_event_plate_result(self, record_id: int,
                                 plate_text: str,
                                 plate_conf: float) -> tuple:
        """
        Apply an OCR result to every violation from the same bike event.

        A later higher-quality result can replace an earlier weaker one. This
        keeps TRIPLE / CO_RIDING / NO_HELMET records consistent while still
        letting the best OCR read win.
        """
        records = self.event_records(record_id)
        if not records:
            return [], None, False

        existing = [
            rec for rec in records
            if rec.plate_text not in (None, "UNDETECTED")
        ]
        previous_plate = None
        if existing:
            best_existing = max(
                existing,
                key=lambda rec: _plate_rank(rec.plate_text, rec.plate_conf),
            )
            previous_plate = (best_existing.plate_text, best_existing.plate_conf)
            candidate_rank = _plate_rank(plate_text, plate_conf)
            existing_rank = _plate_rank(best_existing.plate_text, best_existing.plate_conf)
            if candidate_rank < existing_rank:
                return [], previous_plate, False

        for rec in records:
            rec.plate_text = plate_text
            rec.plate_conf = plate_conf

        return records, previous_plate, True

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
