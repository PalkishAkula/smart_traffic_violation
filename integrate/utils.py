"""
utils.py – Shared geometry helpers used by all detection modules.

CHANGES IN THIS VERSION
-----------------------
1. count_distinct_heads() moved HERE from triple_riding.py
   Both triple_riding.py and co_riding.py now share one implementation.

2. is_rider_on_bike() improved
   Old: only checks that rider x-centre is within bike width + 20 % margin
        and rider top is above bike bottom.
   Problem: for portrait / zoomed-in frames (phone 4K), bikes are tall and
            thin; the x-centre check alone was sufficient for landscape but
            fails when the bike occupies most of the frame height (person box
            may be outside the bike box vertically).
   Fix: added VERTICAL OVERLAP check — rider and bike boxes must share at
        least MIN_VERT_OVERLAP_FRAC of the rider's height.  The original
        x-centre check remains as a parallel fast-path.

3. identify_pillion() improved
   Old: selects the person whose x-centre is furthest from the bike centre.
        Works well for side-view cameras but fails for front / rear views
        where both riders have nearly the same x-centre.
   Fix: if the two x-centres differ by < PILLION_X_TIE_FRAC of bike width
        (front/rear view), fall back to selecting the person with the
        SMALLER bounding-box area (more occluded = pillion riding behind).

4. HEAD_IOU_MERGE exported as a constant
   triple_riding.py and co_riding.py both import it so the threshold is
   changed in one place.
"""

import numpy as np


# ══════════════════════════════════════════════════════════════════════════════
# Shared constants
# ══════════════════════════════════════════════════════════════════════════════

# Two head boxes with IoU above this are considered the same head.
HEAD_IOU_MERGE = 0.30

# Top fraction of a person box treated as the head region.
HEAD_FRAC = 0.40

# Minimum IoU for matching a helmet / no-helmet detection to a person's head.
HEAD_DET_IOU = 0.05

# Minimum vertical overlap (as fraction of rider height) to consider a rider
# to be on a bike.  Keeps the check useful for portrait/zoomed frames.
MIN_VERT_OVERLAP_FRAC = 0.30

# If the two rider x-centres differ by less than this fraction of bike width,
# we treat the shot as front/rear-facing and fall back to area-based pillion ID.
PILLION_X_TIE_FRAC = 0.18

# Minimum fraction of a person's body area that must fall inside the
# motorcycle bounding box to count as "on the bike".
# A real rider's lower body (legs, hips) always intersects the bike box.
# A pedestrian standing nearby has near-zero overlap.
MIN_IOP_FRAC = 0.12


# ══════════════════════════════════════════════════════════════════════════════
# Basic geometry
# ══════════════════════════════════════════════════════════════════════════════

def get_center(box):
    """Return (cx, cy) of an (x1,y1,x2,y2) box."""
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def get_iou(b1, b2):
    """Intersection-over-Union of two (x1,y1,x2,y2) boxes."""
    ix1 = max(b1[0], b2[0]);  iy1 = max(b1[1], b2[1])
    ix2 = min(b1[2], b2[2]);  iy2 = min(b1[3], b2[3])
    inter = max(0.0, ix2-ix1) * max(0.0, iy2-iy1)
    a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
    a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
    union = a1 + a2 - inter
    return inter / (union + 1e-6)


def get_iop(person_box, bike_box):
    """
    Intersection-over-Person-area.

    Returns the fraction of the person's bounding box that physically overlaps
    the motorcycle bounding box.

    WHY THIS IS THE CORRECT METRIC FOR PERSON→BIKE ASSOCIATION
    -----------------------------------------------------------
    IoU is symmetric: a tall rider's body extends above the bike so their
    full-body IoU with the bike is naturally low (~0.1–0.2) even when they
    are clearly on it.  Raising the IoU threshold to fix this causes real
    riders to be missed.

    IoP is asymmetric: it measures how much of the *person* is inside the
    bike box.  A real rider always has at least their lower body (legs, hips)
    inside the motorcycle box, giving IoP ≈ 0.20–0.50.  A pedestrian
    standing adjacent to the bike has IoP ≈ 0.0–0.08, because their body
    does not physically overlap the bike bounding box.

    This cleanly separates riders from nearby pedestrians without needing
    any hand-tuned x-distance margin.
    """
    px1, py1, px2, py2 = [float(v) for v in person_box[:4]]
    bx1, by1, bx2, by2 = [float(v) for v in bike_box[:4]]
    ix1 = max(px1, bx1);  iy1 = max(py1, by1)
    ix2 = min(px2, bx2);  iy2 = min(py2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    person_area = max(1.0, (px2 - px1) * (py2 - py1))
    return inter / person_area


# ══════════════════════════════════════════════════════════════════════════════
# Head counting (shared by triple_riding.py and co_riding.py)
# ══════════════════════════════════════════════════════════════════════════════

def count_distinct_heads(helmets: list, no_helmets: list) -> int:
    """
    Count distinct rider heads visible on one motorcycle using the
    helmet-model's detections.

    Two detections with IoU > HEAD_IOU_MERGE are merged as the same head.
    This handles cases where one rider's head produces both a 'helmet'
    and a 'no-helmet' detection at slightly different positions.

    Parameters
    ----------
    helmets     : list of (x1,y1,x2,y2,conf) helmet detections on this bike
    no_helmets  : list of (x1,y1,x2,y2,conf) no-helmet detections on this bike

    Returns
    -------
    Number of distinct heads (int).
    """
    all_heads = list(helmets) + list(no_helmets)
    if not all_heads:
        return 0
    distinct = []
    for h in all_heads:
        if not any(get_iou(h[:4], d[:4]) > HEAD_IOU_MERGE for d in distinct):
            distinct.append(h)
    return len(distinct)


# ══════════════════════════════════════════════════════════════════════════════
# Spatial association helpers
# ══════════════════════════════════════════════════════════════════════════════

def is_rider_on_bike(rider_box, bike_box):
    """
    True if a rider / person detection is spatially on a motorcycle.

    Three checks (any passing check is sufficient):
    A) X-CENTRE CHECK  – rider x-centre within bike width + 20 % margin,
       AND rider top edge above bike bottom.  Fast; works for side-view cameras.

    B) VERTICAL OVERLAP CHECK  – rider and bike boxes share at least
       MIN_VERT_OVERLAP_FRAC of the rider's height AND the x-centres
       are within 0.65× the bike's width.
       (Was 2.0× in the old version — that caused pedestrians standing
       nearby to be counted as riders.  0.65× keeps the rider's centre
       inside or just at the edge of the bike box.)

    C) IOP CHECK  – at least MIN_IOP_FRAC (12 %) of the rider's area
       must physically overlap the bike box.  Handles portrait/zoomed
       frames where both A and B fail but the rider clearly overlaps the bike.

    FIX: old Check B used bike_w * 2.0, which admitted pedestrians standing
    1–2 bike-widths away.  Reduced to 0.65× and added Check C as a
    defence-in-depth guard.
    """
    bx1, by1, bx2, by2 = bike_box[:4]
    rx1, ry1, rx2, ry2 = rider_box[:4]

    # ── Check A: x-centre + top-above-bottom (original logic) ────────────────
    rx_c   = (rx1 + rx2) / 2.0
    margin = (bx2 - bx1) * 0.20
    check_a = ((bx1 - margin) <= rx_c <= (bx2 + margin)
               and ry1 < by2)

    if check_a:
        return True

    # ── Check B: vertical overlap — TIGHTENED (portrait / zoomed-in fix) ──────
    rider_h       = max(1.0, float(ry2 - ry1))
    vert_inter    = max(0.0, min(ry2, by2) - max(ry1, by1))
    vert_overlap  = vert_inter / rider_h

    bike_w  = max(1.0, float(bx2 - bx1))
    rx_c    = (rx1 + rx2) / 2.0
    bx_c    = (bx1 + bx2) / 2.0
    # OLD: bike_w * 2.0  →  admitted pedestrians 2 bike-widths away
    # NEW: bike_w * 0.65 →  rider centre must be within / just at bike edge
    x_close = abs(rx_c - bx_c) <= bike_w * 0.65

    if vert_overlap >= MIN_VERT_OVERLAP_FRAC and x_close:
        return True

    # ── Check C: IoP guard — catches portrait frames where A & B fail ─────────
    return get_iop(rider_box, bike_box) >= MIN_IOP_FRAC


def is_plate_on_bike(plate_box, bike_box):
    """
    True if a license-plate centre falls inside (or near) the motorcycle box.
    """
    px_c, py_c = get_center(plate_box[:4])
    bx1, by1, bx2, by2 = bike_box[:4]
    mx = (bx2 - bx1) * 0.15
    my = (by2 - by1) * 0.15
    return (bx1-mx) <= px_c <= (bx2+mx) and (by1-my) <= py_c <= (by2+my)


# ══════════════════════════════════════════════════════════════════════════════
# Crop & coordinate utilities (used in video pipeline)
# ══════════════════════════════════════════════════════════════════════════════

def safe_crop(img, x1, y1, x2, y2, pad_frac=0.10):
    """
    Crop img[y1:y2, x1:x2] with optional proportional padding.
    Clamps coordinates to image boundaries.

    Returns
    -------
    crop    : np.ndarray  – cropped image (may be empty)
    offset  : (ox, oy)    – top-left corner of crop in frame coordinates
    """
    h, w = img.shape[:2]
    pad_x = int((x2 - x1) * pad_frac)
    pad_y = int((y2 - y1) * pad_frac)
    cx1 = max(0, int(x1) - pad_x)
    cy1 = max(0, int(y1) - pad_y)
    cx2 = min(w, int(x2) + pad_x)
    cy2 = min(h, int(y2) + pad_y)
    return img[cy1:cy2, cx1:cx2], (cx1, cy1)


def detections_to_frame(dets, offset):
    """
    Translate a list of (x1,y1,x2,y2,conf) detections from crop-space
    to full-frame space by adding (ox, oy).

    Parameters
    ----------
    dets   : list of (x1, y1, x2, y2, conf)
    offset : (ox, oy)

    Returns
    -------
    list of (x1, y1, x2, y2, conf) in full-frame coordinates
    """
    ox, oy = offset
    return [(x1+ox, y1+oy, x2+ox, y2+oy, conf)
            for x1, y1, x2, y2, conf in dets]


# ══════════════════════════════════════════════════════════════════════════════
# Pillion identification (used by co-riding logic)
# ══════════════════════════════════════════════════════════════════════════════

def identify_pillion(persons_on_bike, bike_box):
    """
    Among exactly 2 persons on a bike, return the one most likely to be
    the pillion (back-seat passenger).

    Strategy
    --------
    PRIMARY  – x-distance from bike centre.
               Works well for side-view cameras (most traffic intersections).
               The pillion sits BEHIND the driver → further from the bike's
               horizontal midpoint.

    FALLBACK – bounding-box area.
               When the two x-centres are nearly the same (front/rear-facing
               camera, PILLION_X_TIE_FRAC threshold), the pillion is partially
               hidden behind the driver → their visible bounding box is smaller.

    FIX vs old version: old code only used x-distance.  For front/rear-facing
    shots both riders have similar x-centres, so the old code picked the
    pillion arbitrarily.  The fallback now uses occlusion (box area) instead.

    Returns None if fewer than 2 persons are given.
    """
    if len(persons_on_bike) < 2:
        return None

    bx1, _by1, bx2, _by2 = bike_box[:4]
    bike_cx = (bx1 + bx2) / 2.0
    bike_w  = max(1.0, float(bx2 - bx1))

    p1, p2 = persons_on_bike[0], persons_on_bike[1]
    c1x = (p1[0] + p1[2]) / 2.0
    c2x = (p2[0] + p2[2]) / 2.0

    x_diff_frac = abs(c1x - c2x) / bike_w

    if x_diff_frac >= PILLION_X_TIE_FRAC:
        # Side-view: use x-distance (original method)
        return max(persons_on_bike,
                   key=lambda p: abs((p[0]+p[2])/2.0 - bike_cx))
    else:
        # Front/rear view: use bounding-box area — smaller = more occluded = pillion
        def _area(p):
            return max(1.0, float(p[2]-p[0])) * max(1.0, float(p[3]-p[1]))
        return min(persons_on_bike, key=_area)


# ══════════════════════════════════════════════════════════════════════════════
# Per-person helmet assignment
# ══════════════════════════════════════════════════════════════════════════════

def get_head_region(person_box, head_frac=HEAD_FRAC):
    """
    Return the head region of a person box: the top ``head_frac`` of the
    body bounding box.

    Parameters
    ----------
    person_box : (x1, y1, x2, y2[, conf])
    head_frac  : fraction of box height counted as the head (default 0.40)

    Returns
    -------
    (x1, y1, x2, head_y2) — a tighter box covering only the head/shoulders
    """
    x1, y1, x2, y2 = [float(v) for v in person_box[:4]]
    return (x1, y1, x2, y1 + (y2 - y1) * head_frac)


def assign_head_detections(persons, helmets, no_helmets):
    """
    Assign each helmet / no-helmet detection to the person whose HEAD REGION
    has the highest IoU with that detection.

    Key design decision — only POSITIVE detections count:
        A person violates iff their assigned no-helmet list is non-empty.
        The ABSENCE of a helmet detection is NOT used as evidence of a violation.

    Parameters
    ----------
    persons    : list of (x1,y1,x2,y2,conf) COCO person boxes on this bike
    helmets    : list of (x1,y1,x2,y2,conf) helmet detections on this bike
    no_helmets : list of (x1,y1,x2,y2,conf) no-helmet detections on this bike

    Returns
    -------
    p_helmets    : list[list]  –  p_helmets[i]    = helmets assigned to person i
    p_no_helmets : list[list]  –  p_no_helmets[i] = no-helmets assigned to person i
    """
    n = len(persons)
    p_helmets    = [[] for _ in range(n)]
    p_no_helmets = [[] for _ in range(n)]

    if n == 0:
        return p_helmets, p_no_helmets

    heads = [get_head_region(p) for p in persons]

    for h in helmets:
        ious = [get_iou(hr, h[:4]) for hr in heads]
        best = max(range(n), key=lambda i: ious[i])
        if ious[best] >= HEAD_DET_IOU:
            p_helmets[best].append(h)

    for nh in no_helmets:
        ious = [get_iou(hr, nh[:4]) for hr in heads]
        best = max(range(n), key=lambda i: ious[i])
        if ious[best] >= HEAD_DET_IOU:
            p_no_helmets[best].append(nh)

    return p_helmets, p_no_helmets