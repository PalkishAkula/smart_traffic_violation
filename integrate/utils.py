"""
utils.py – Shared geometry helpers used by all detection modules.
"""

import numpy as np


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


# ══════════════════════════════════════════════════════════════════════════════
# Spatial association helpers
# ══════════════════════════════════════════════════════════════════════════════

def is_rider_on_bike(rider_box, bike_box):
    """
    True if a rider/person detection is spatially on a motorcycle.
    The rider's x-centre must be within the bike's width + 20 % margin,
    and the rider's top edge must be above the bike's bottom edge.
    """
    rx_c = (rider_box[0] + rider_box[2]) / 2.0
    bx1, by1, bx2, by2 = bike_box[:4]
    margin = (bx2 - bx1) * 0.20
    return (bx1 - margin) <= rx_c <= (bx2 + margin) and rider_box[1] < by2


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
    the pillion (furthest x-centre from the motorcycle's horizontal centre).
    Returns None if fewer than 2 persons are given.
    """
    if len(persons_on_bike) < 2:
        return None
    bx1, _by1, bx2, _by2 = bike_box[:4]
    bike_cx = (bx1 + bx2) / 2.0
    return max(persons_on_bike,
               key=lambda p: abs((p[0]+p[2])/2.0 - bike_cx))


# ══════════════════════════════════════════════════════════════════════════════
# Per-person helmet assignment
# ══════════════════════════════════════════════════════════════════════════════

# Fraction of a person's bounding box (from the top) treated as the head region.
# 0.40 → top 40 % of the body box, which reliably covers the head/helmet for
# both seated and standing poses regardless of camera distance.
HEAD_FRAC = 0.40

# Minimum IoU between a helmet/no-helmet detection box and a person's head
# region to consider them a match.  Kept deliberately low (0.05) because
# head-sized detection boxes are much smaller than full-body person boxes,
# so their IoU with even the restricted "head region" is naturally small.
HEAD_DET_IOU = 0.05


def get_head_region(person_box, head_frac=HEAD_FRAC):
    """
    Return the head region of a person box: the top ``head_frac`` of the
    body bounding box.

    This region is used to match helmet / no-helmet detections to the
    correct person — detections whose centre falls in this region belong
    to this rider.

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

    This is the single authoritative function that decides which detections
    belong to the driver and which belong to the pillion / co-riders.  Using
    HEAD REGIONS (top 40 % of body) instead of full body boxes prevents a
    co-rider's helmet detection from being attributed to the driver (or vice
    versa) when the two person boxes overlap.

    Key design decision — only POSITIVE detections count:
        If a person has a no-helmet detection on their head → they are
        violating.  The ABSENCE of a helmet detection is NOT used as
        evidence of a violation.  This fixes the root cause of cases 2.3
        and 2.4 (CO_RIDING firing when pillion has a helmet).

    Parameters
    ----------
    persons    : list of (x1,y1,x2,y2,conf) COCO person boxes on this bike
    helmets    : list of (x1,y1,x2,y2,conf) helmet detections on this bike
    no_helmets : list of (x1,y1,x2,y2,conf) no-helmet detections on this bike

    Returns
    -------
    p_helmets    : list[list]
        p_helmets[i] = list of helmet detections assigned to person i
    p_no_helmets : list[list]
        p_no_helmets[i] = list of no-helmet detections assigned to person i

    Usage
    -----
    p_helmets, p_no_helmets = assign_head_detections(persons, helmets, no_helmets)
    driver_has_no_helmet = bool(p_no_helmets[driver_idx])
    pillion_has_no_helmet = bool(p_no_helmets[pillion_idx])
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