"""
helmet_logic.py – Violation Type 1: Rider without a helmet.

Video pipeline API
------------------
check_helmet_violation(no_helmets_on_bike, helmets_on_bike)
    → (violated: bool, details: dict)

CHANGES IN THIS VERSION
-----------------------
FIX A — Deduplicate overlapping no-helmet detections before deciding.
    Problem: when a rider's head is close to the inference-resolution
    boundary, YOLO can fire 2 overlapping no-helmet boxes for the same head.
    This inflated n_no_helmet and could cause triple-riding to fire
    unnecessarily if the count was fed into that check.

    Fix: merge no-helmet detections with IoU > NH_MERGE_IOU before
    returning details.  The violated flag itself is unaffected (any single
    no-helmet detection still means violated=True), but the details dict
    now contains deduplicated boxes and an accurate count.

FIX B — Cross-suppress a no-helmet detection if a high-confidence helmet
    detection covers the same head region.
    Problem: at low inference resolution some helmet detections score below
    CONF_HELMET and are filtered out, leaving a lone no-helmet box on a
    rider who is actually helmeted.  With the new lower threshold
    (CONF_HELMET=0.30 in main.py) this should be rare, but we add an
    explicit guard: if a helmet box overlaps a no-helmet box by more than
    HELM_NH_SUPPRESS_IOU, suppress the no-helmet detection.

    This only fires if the helmet box survived the confidence filter, so
    it never silently swallows a real violation.
"""

from utils import get_iou

# Two no-helmet boxes with IoU > this are the same head — keep higher conf.
NH_MERGE_IOU = 0.40

# If a surviving helmet box overlaps a no-helmet box by more than this,
# suppress the no-helmet detection (the rider has a helmet).
HELM_NH_SUPPRESS_IOU = 0.30


def _deduplicate(dets: list, iou_thresh: float) -> list:
    """
    Greedy NMS: keep the highest-confidence box; suppress overlapping ones.
    Input: list of (x1,y1,x2,y2,conf). Returns filtered list.
    """
    if len(dets) <= 1:
        return list(dets)
    sorted_dets = sorted(dets, key=lambda d: d[4], reverse=True)
    kept = []
    for d in sorted_dets:
        if not any(get_iou(d[:4], k[:4]) > iou_thresh for k in kept):
            kept.append(d)
    return kept


def check_helmet_violation(no_helmets_on_bike: list,
                            helmets_on_bike:    list) -> tuple:
    """
    Determine if any rider on this motorcycle is not wearing a helmet.

    Parameters
    ----------
    no_helmets_on_bike : list of (x1,y1,x2,y2,conf)
        No-helmet detections already associated to this bike.
    helmets_on_bike    : list of (x1,y1,x2,y2,conf)
        Helmet detections already associated to this bike.

    Returns
    -------
    violated : bool
    details  : dict
        rider_boxes    – deduplicated list of (x1,y1,x2,y2) of no-helmet riders
        helmet_boxes   – list of (x1,y1,x2,y2) of helmeted riders
        n_no_helmet    – deduplicated count of riders without helmets
        n_helmet       – count of riders with helmets
    """
    if not no_helmets_on_bike:
        return False, {}

    # FIX A: merge overlapping no-helmet boxes for the same head
    deduped_nh = _deduplicate(no_helmets_on_bike, NH_MERGE_IOU)

    # FIX B: cross-suppress no-helmet boxes that are covered by a helmet box
    # (only possible if helmet passed the confidence filter in main.py)
    if helmets_on_bike:
        deduped_nh = [
            nh for nh in deduped_nh
            if not any(get_iou(nh[:4], h[:4]) > HELM_NH_SUPPRESS_IOU
                       for h in helmets_on_bike)
        ]

    if not deduped_nh:
        return False, {}

    details = {
        'rider_boxes' : [b[:4] for b in deduped_nh],
        'helmet_boxes': [b[:4] for b in helmets_on_bike],
        'n_no_helmet' : len(deduped_nh),
        'n_helmet'    : len(helmets_on_bike),
    }
    return True, details