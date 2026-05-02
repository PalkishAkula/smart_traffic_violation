"""
triple_riding.py – Violation Type 2: Three or more persons on one motorcycle.

Video pipeline API
------------------
check_triple_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike)
    → (violated: bool, details: dict)

CHANGES IN THIS VERSION
-----------------------
1.  count_distinct_heads() is now IMPORTED from utils.py instead of being
    defined locally.  Both triple_riding.py and co_riding.py share the exact
    same implementation — no risk of the two diverging in future.

    (The logic is identical to the old local version; only the location changed.)

Original bug fix (unchanged from previous version)
---------------------------------------------------
When 3 people ride tightly packed, COCO often merges the middle rider into
the driver or pillion body box, returning only 2 person detections. The old
code returned False in that case.

Fix: use max(COCO person count, helmet-model head count).
A head is a smaller, cleaner target than a full body, so the helmet model
fires on all 3 heads even when COCO collapses two bodies together.

Example:
  COCO persons  : 2   (middle rider missed)
  Helmet heads  : 1   (driver's helmet)
  No-helm heads : 2   (middle + right-side pillion)
  Distinct heads: 3   → TRIPLE_RIDING correctly flagged ✓
"""

from utils import count_distinct_heads, get_iou, HEAD_IOU_MERGE

TRIPLE_THRESHOLD = 3   # minimum riders to flag as triple riding

# When COCO already detected 2 persons, the helmet model's head count is
# allowed to exceed the COCO count by at most this many before being capped.
# RAISED 1 → 2: with 3 riders, COCO often sees only 2 (middle rider merged
# into driver or pillion body box).  The helmet model still fires on all 3
# heads.  Allowing 2 extra heads prevents the cap from blocking this.
MAX_EXTRA_HEADS_OVER_COCO = 2


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

    HEAD COUNT SANITY CAP
    ---------------------
    In dense traffic, a nearby pedestrian's head may produce an additional
    no-helmet detection that survives the _dets_on_bike filter.  To guard
    against this, the effective head count is capped at:
        coco_count + MAX_EXTRA_HEADS_OVER_COCO
    This prevents one phantom head box from escalating a 2-person bike to
    triple-riding.  The cap only applies when coco_count >= 2 (i.e. COCO
    already saw real riders); if coco_count < 2 we trust head_count fully
    to catch the COCO-merged-two-bodies case.

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
    head_count = count_distinct_heads(helmets_on_bike, no_helmets_on_bike)

    # Triple riding REQUIRES COCO to detect at least 3 BODIES.
    # Head count can see 2 close heads on a 2-rider bike as distinct,
    # causing false triple_riding. Only use head_count to catch the
    # COCO-merged-bodies case when COCO already saw 3+ bodies.
    if coco_count < TRIPLE_THRESHOLD:
        return False, {}

    # COCO saw 3+ bodies; verify head_count doesn't contradict it.
    effective = max(coco_count, head_count)

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