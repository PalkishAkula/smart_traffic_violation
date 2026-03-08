"""
triple_riding.py – Violation Type 2: Three or more persons on one motorcycle.

Video pipeline API
------------------
check_triple_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike)
    → (violated: bool, details: dict)

BUG FIX
-------
Old code:  count = len(persons_on_bike)   ← COCO only

Problem:   When 3 people ride tightly packed, COCO often merges the middle
           rider into the person box of the driver or pillion, returning only
           2 person detections.  The function then returned False, causing
           TRIPLE_RIDING to be missed entirely.

Fix:       Also count distinct rider HEADS from the helmet model
           (helmets + no-helmets).  A head is a smaller, cleaner target than
           a full body, so the helmet model fires on all 3 heads even when
           COCO collapses two bodies together.

           Effective count = max(COCO person count, distinct head count)

Example (Image 1):
  COCO persons  : 2   (middle rider missed)
  Helmet heads  : 1   (driver's helmet)
  No-helm heads : 2   (middle + right-side pillion)
  Distinct heads: 3   → TRIPLE_RIDING correctly flagged ✓
"""

from utils import get_iou

TRIPLE_THRESHOLD = 3      # minimum riders to flag as triple riding
HEAD_IOU_MERGE   = 0.30   # two head boxes with IoU > this = same head


# ══════════════════════════════════════════════════════════════════════════════
# Internal – count distinct heads from helmet-model output
# ══════════════════════════════════════════════════════════════════════════════

def _count_distinct_heads(helmets_on_bike: list,
                           no_helmets_on_bike: list) -> int:
    """
    Count distinct rider heads visible on this motorcycle using the
    helmet-model's detections.

    Two detections with IoU > HEAD_IOU_MERGE are merged as the same head.
    This handles the case where one rider's head produces both a 'helmet'
    and a 'no-helmet' detection at slightly different positions.
    """
    all_heads = list(helmets_on_bike) + list(no_helmets_on_bike)
    if not all_heads:
        return 0
    distinct = []
    for h in all_heads:
        if not any(get_iou(h[:4], d[:4]) > HEAD_IOU_MERGE for d in distinct):
            distinct.append(h)
    return len(distinct)


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def check_triple_riding(persons_on_bike:    list,
                         helmets_on_bike:   list,
                         no_helmets_on_bike: list) -> tuple:
    """
    Determine if three or more persons are riding one motorcycle.

    Uses max(COCO person count, helmet-model head count) so that a missed
    COCO body detection does not cause a false negative.

    Parameters
    ----------
    persons_on_bike     : list of (x1,y1,x2,y2,conf) COCO person detections
                          already associated to this bike.
    helmets_on_bike     : list of (x1,y1,x2,y2,conf) helmet detections.
    no_helmets_on_bike  : list of (x1,y1,x2,y2,conf) no-helmet detections.

    Returns
    -------
    violated : bool
    details  : dict
        person_count  – effective count used for the decision
        coco_count    – raw COCO body count
        head_count    – raw helmet-model head count
        person_boxes  – COCO person boxes  (x1,y1,x2,y2)
        helmet_boxes  – helmeted rider boxes
        nh_boxes      – un-helmeted rider boxes
    """
    coco_count = len(persons_on_bike)
    head_count = _count_distinct_heads(helmets_on_bike, no_helmets_on_bike)
    effective  = max(coco_count, head_count)

    if effective < TRIPLE_THRESHOLD:
        return False, {}

    details = {
        'person_count': effective,
        'coco_count'  : coco_count,
        'head_count'  : head_count,
        'person_boxes': [p[:4] for p in persons_on_bike],
        'helmet_boxes': [h[:4] for h in helmets_on_bike],
        'nh_boxes'    : [n[:4] for n in no_helmets_on_bike],
    }
    return True, details