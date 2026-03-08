"""
co_riding.py – Violation Type 3: Co-rider (pillion) without a helmet.

Video pipeline API
------------------
check_co_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike, bike_box)
    → (violated: bool, details: dict)

Root causes fixed
-----------------
All four bugs (2.2 / 2.3 / 2.4 / 3.x equivalents) stem from TWO design flaws
in the previous version:

FLAW 1 — "absence of helmet = violation"
    Old code:
        pillion_violated = _has_no_helmet(pillion, no_helmets) OR
                           NOT _has_helmet(pillion, helmets)

    The second arm fires when there is NO helmet detection on the pillion,
    even if the pillion is genuinely wearing one.  This happened because:
        • The helmet model detects small head-sized boxes.
        • COCO detects large full-body person boxes.
        • IoU(head_box, body_box) is tiny (< 0.20 threshold).
        → "_has_helmet" returned False even with a real helmet.
        → CO_RIDING fired when BOTH riders had helmets  ← Bug 2.4
        → CO_RIDING fired when only the DRIVER had no helmet  ← Bug 2.3

    Fix: only use POSITIVE no-helmet detections.
         pillion_violated = bool(p_no_helmets[pillion_idx])

FLAW 2 — full-body IoU for person-to-helmet matching
    Old _has_helmet / _has_no_helmet compared the full person bounding box
    (large) against helmet detection boxes (head-sized, small).  The IoU is
    naturally tiny, so adjacent riders' detections could bleed across
    person boundaries.

    Fix: use HEAD REGION of person (top 40 % of body box) and the
         assign_head_detections() helper from utils.py, which assigns each
         detection to the person whose head region matches it best.
"""

from utils import (identify_pillion, get_iou,
                   get_head_region, assign_head_detections, HEAD_DET_IOU)

# ── Thresholds ────────────────────────────────────────────────────────────────
PERSON_DISTINCT_MAX_IOU     = 0.60   # IoU above this → same body, not two persons
PERSON_DISTINCT_MIN_CX_FRAC = 0.12   # centres must differ by ≥ 12 % of bike width


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════

def _is_distinct_person_pair(p1, p2, bike_box) -> bool:
    """Two COCO boxes must be geometrically distinct to count as two riders."""
    if get_iou(p1[:4], p2[:4]) >= PERSON_DISTINCT_MAX_IOU:
        return False
    bx1, _by1, bx2, _by2 = bike_box[:4]
    bike_w = max(1.0, float(bx2 - bx1))
    c1x = (p1[0] + p1[2]) / 2.0
    c2x = (p2[0] + p2[2]) / 2.0
    return abs(c1x - c2x) >= (bike_w * PERSON_DISTINCT_MIN_CX_FRAC)


def _has_head_detection(person_box,
                         helmets_on_bike,
                         no_helmets_on_bike) -> bool:
    """
    Guard against false COCO person detections (background objects that have
    no corresponding head in the helmet model's output).

    A real rider always has a head → the helmet model will output either a
    'helmet' or a 'no_helmet' box at the top of their body.  If NO such box
    overlaps this person's head region, reject the person as a false positive.
    """
    head = get_head_region(person_box)
    all_heads = list(helmets_on_bike) + list(no_helmets_on_bike)
    return any(get_iou(head, h[:4]) >= HEAD_DET_IOU for h in all_heads)


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def check_co_riding(persons_on_bike:    list,
                    helmets_on_bike:    list,
                    no_helmets_on_bike: list,
                    bike_box:           tuple) -> tuple:
    """
    Determine if exactly 2 persons are on the motorcycle and the pillion
    (back-seat passenger) has no helmet.

    Called only when triple-riding is NOT detected (main.py guards this).

    Violation logic (per-person, head-region based)
    ------------------------------------------------
    1. Assign every helmet / no-helmet detection to the person whose
       HEAD REGION (top 40 % of body box) it best overlaps.
    2. A person violates iff their assigned no-helmet list is non-empty.
    3. Only the PILLION's status matters for CO_RIDING_NO_HELMET.
       (Driver's no-helmet status is handled by the NO_HELMET check in main.py.)

    Test-case matrix
    ----------------
    2.1  driver NH + pillion NH  →  pillion_violated=True   CO_RIDING ✓
    2.2  driver H  + pillion NH  →  pillion_violated=True   CO_RIDING ✓
    2.3  driver NH + pillion H   →  pillion_violated=False  (no CO_RIDING) ✓
    2.4  driver H  + pillion H   →  pillion_violated=False  (no CO_RIDING) ✓

    Parameters
    ----------
    persons_on_bike    : (x1,y1,x2,y2,conf) COCO persons on bike – MUST be 2
    helmets_on_bike    : helmet detections on bike
    no_helmets_on_bike : no-helmet detections on bike
    bike_box           : (x1,y1,x2,y2) motorcycle bounding box

    Returns
    -------
    violated : bool
    details  : dict  { driver_box, pillion_box }
    """
    if len(persons_on_bike) != 2:
        return False, {}   # triple riding handled separately in main.py

    p1, p2 = persons_on_bike[0], persons_on_bike[1]

    # Guard 1: the two COCO boxes must represent distinct riders
    if not _is_distinct_person_pair(p1, p2, bike_box):
        return False, {}

    # Guard 2: reject false COCO person boxes (no visible head in helmet model)
    if not _has_head_detection(p1, helmets_on_bike, no_helmets_on_bike):
        return False, {}
    if not _has_head_detection(p2, helmets_on_bike, no_helmets_on_bike):
        return False, {}

    # Identify pillion: person whose x-centre is furthest from the bike centre
    pillion = identify_pillion(persons_on_bike, bike_box)
    if pillion is None:
        return False, {}

    try:
        pillion_idx = next(i for i, p in enumerate(persons_on_bike) if p is pillion)
    except StopIteration:
        return False, {}

    driver = persons_on_bike[1 - pillion_idx]

    # Assign helmet / no-helmet detections to each person by head-region IoU.
    # p_no_helmets[i] is non-empty iff person i has an EXPLICIT no-helmet
    # detection on their head — this is the ONLY evidence we use.
    _, p_no_helmets = assign_head_detections(
        persons_on_bike, helmets_on_bike, no_helmets_on_bike)

    # VIOLATION: pillion has a positive no-helmet detection
    if not p_no_helmets[pillion_idx]:
        return False, {}

    return True, {
        'driver_box' : driver[:4],
        'pillion_box': pillion[:4],
    }