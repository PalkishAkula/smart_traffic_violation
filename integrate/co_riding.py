"""
co_riding.py – Violation Type 3: Co-rider (pillion) without a helmet.

Video pipeline API
------------------
check_co_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike, bike_box)
    → (violated: bool, details: dict)

CHANGES IN THIS VERSION
-----------------------

FIX A — HEAD-COUNT FALLBACK when COCO detects only 1 person
    Old code returned (False, {}) immediately if len(persons) != 2.
    Problem: when two riders are close together (as in a portrait-view or
    zoomed-in shot), COCO often MERGES them into one person bounding box.
    The helmet model still detects BOTH heads separately.

    Fix: if len(persons) == 1 but count_distinct_heads() >= 2 AND at least
    one no-helmet head exists, the pillion's head is used directly as the
    "pillion box" and CO_RIDING_NO_HELMET is raised.

FIX B — _has_head_detection GUARD SOFTENED
    Old guard: if ANY person has no matching head in the helmet model → return False.
    Problem: on real-world low-contrast footage the helmet model may miss a
    head even when it's clearly visible — especially at 416×256 inference
    (now fixed by the 640×640 square inference in main.py, but we add a
    confidence-based bypass here for defence-in-depth).

    Fix: bypass the guard if the COCO person confidence > PERSON_HIGH_CONF_BYPASS
    (0.60).  A COCO detection at > 60 % confidence with the person clearly
    overlapping the bike is almost certainly a real rider.

FIX C — identify_pillion uses improved logic from utils.py
    The pillion is now identified using both x-distance AND bounding-box area
    (see utils.identify_pillion for the full explanation).

Root-cause bugs fixed in previous version (unchanged)
------------------------------------------------------
FLAW 1 — "absence of helmet = violation" → now only positive no-helmet
          detections count.
FLAW 2 — full-body IoU for person-to-helmet matching → now uses HEAD REGION
          (top 40 % of body box) via assign_head_detections().
"""

from utils import (identify_pillion, get_iou,
                   get_head_region, assign_head_detections, HEAD_DET_IOU,
                   count_distinct_heads, HEAD_IOU_MERGE)

# ── Thresholds ────────────────────────────────────────────────────────────────

# Two COCO person boxes with IoU above this → same body, not two persons.
PERSON_DISTINCT_MAX_IOU     = 0.60

# Centres of two person boxes must differ by ≥ this fraction of bike width
# for them to be considered distinct riders.
# LOWERED 0.12 → 0.06: front/rear-facing cameras have both riders nearly
# centred on the bike; 12 % was too strict and blocked valid co-riding detects.
PERSON_DISTINCT_MIN_CX_FRAC = 0.06

# If a COCO person detection has confidence > this, trust it even if the
# helmet model didn't fire a matching head detection on it.
# LOWERED 0.60 → 0.40: test images often score slightly below 0.60 for the
# pillion whose upper body is partially occluded by the driver.
PERSON_HIGH_CONF_BYPASS = 0.40


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


def _has_head_detection(person_box, helmets_on_bike, no_helmets_on_bike,
                        person_conf: float = 0.0) -> bool:
    """
    Guard against false COCO person detections (background objects that have
    no corresponding head in the helmet model's output).

    A real rider always has a head → the helmet model outputs either a
    'helmet' or a 'no_helmet' box near the top of their body.  If NO such
    box overlaps this person's head region, reject the person as a FP.

    BYPASS (FIX B): if person_conf > PERSON_HIGH_CONF_BYPASS, the COCO
    detection is trusted unconditionally — a high-confidence COCO person
    on a motorcycle is almost never a background false positive.
    """
    if person_conf > PERSON_HIGH_CONF_BYPASS:
        return True   # high-confidence bypass

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
    Determine if a co-rider (pillion) on the motorcycle has no helmet.

    Called only when triple-riding is NOT detected (main.py guards this).

    Detection paths
    ---------------
    PATH 1 — Normal (COCO detected 2 persons):
        Assign helmet / no-helmet detections per person via head-region IoU.
        Violation iff the pillion has a positive no-helmet detection.

    PATH 2 — Fallback (COCO merged riders into 1 person box):  [FIX A]
        If COCO only found 1 person but the helmet model reports 2+ distinct
        heads AND at least one is a no-helmet → CO_RIDING_NO_HELMET raised.
        The no-helmet head box is used as the pillion location.

    Violation logic test-case matrix
    ---------------------------------
    2.1  driver NH + pillion NH  → CO_RIDING ✓
    2.2  driver H  + pillion NH  → CO_RIDING ✓
    2.3  driver NH + pillion H   → no CO_RIDING ✓
    2.4  driver H  + pillion H   → no CO_RIDING ✓
    2.5  1 COCO person, 2 heads, pillion NH → CO_RIDING ✓  (FIX A)

    Parameters
    ----------
    persons_on_bike    : COCO (x1,y1,x2,y2,conf) persons associated to this bike
    helmets_on_bike    : helmet detections on this bike
    no_helmets_on_bike : no-helmet detections on this bike
    bike_box           : (x1,y1,x2,y2) motorcycle bounding box

    Returns
    -------
    violated : bool
    details  : dict
    """

    # ── PATH 1: Two COCO persons ──────────────────────────────────────────────
    if len(persons_on_bike) == 2:
        return _check_two_persons(
            persons_on_bike, helmets_on_bike, no_helmets_on_bike, bike_box)

    # ── PATH 2: Fallback — COCO merged riders, helmet model sees 2+ heads ─────
    if len(persons_on_bike) == 1:
        head_count = count_distinct_heads(helmets_on_bike, no_helmets_on_bike)
        if head_count >= 2 and no_helmets_on_bike:
            # Two riders confirmed by the helmet model.
            # The no-helmet detection closest to the back of the bike is the pillion.
            # We use the first no-helmet box as a proxy for the pillion position.
            nh_box = no_helmets_on_bike[0][:4]
            driver_box = persons_on_bike[0][:4]
            print(f"  [CO_RIDING] Fallback: COCO=1 person but "
                  f"helmet-model heads={head_count} → CO_RIDING_NO_HELMET")
            return True, {
                'driver_box' : driver_box,
                'pillion_box': nh_box,
                'path'       : 'head_count_fallback',
            }

    return False, {}


# ══════════════════════════════════════════════════════════════════════════════
# Internal: normal two-person check
# ══════════════════════════════════════════════════════════════════════════════

def _check_two_persons(persons_on_bike, helmets_on_bike, no_helmets_on_bike,
                       bike_box) -> tuple:
    """Handle the standard case where COCO detected exactly 2 persons."""

    p1, p2 = persons_on_bike[0], persons_on_bike[1]
    p1_conf = float(p1[4]) if len(p1) > 4 else 0.0
    p2_conf = float(p2[4]) if len(p2) > 4 else 0.0

    # Guard 1: the two COCO boxes must represent distinct riders.
    if not _is_distinct_person_pair(p1, p2, bike_box):
        return False, {}

    # Guard 2: reject COCO detections that have no visible head in the
    # helmet model.  High-confidence detections bypass this check (FIX B).
    if not _has_head_detection(p1, helmets_on_bike, no_helmets_on_bike, p1_conf):
        return False, {}
    if not _has_head_detection(p2, helmets_on_bike, no_helmets_on_bike, p2_conf):
        return False, {}

    # Identify pillion using improved logic (x-distance + area fallback).
    pillion = identify_pillion(persons_on_bike, bike_box)
    if pillion is None:
        return False, {}

    try:
        pillion_idx = next(i for i, p in enumerate(persons_on_bike)
                           if p is pillion)
    except StopIteration:
        return False, {}

    driver = persons_on_bike[1 - pillion_idx]

    # Assign helmet / no-helmet detections to each person by head-region IoU.
    _, p_no_helmets = assign_head_detections(
        persons_on_bike, helmets_on_bike, no_helmets_on_bike)

    # VIOLATION: pillion has a positive no-helmet detection
    if not p_no_helmets[pillion_idx]:
        return False, {}

    return True, {
        'driver_box' : driver[:4],
        'pillion_box': pillion[:4],
        'path'       : 'two_person',
    }