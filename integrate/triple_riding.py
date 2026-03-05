"""
triple_riding.py – Violation Type 2: Three or more persons on one motorcycle.

Video pipeline API
------------------
check_triple_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike)
    → (violated: bool, details: dict)
"""

TRIPLE_THRESHOLD = 3   # minimum persons to flag as triple riding


def check_triple_riding(persons_on_bike:    list,
                         helmets_on_bike:   list,
                         no_helmets_on_bike: list) -> tuple:
    """
    Determine if three or more persons are riding one motorcycle.

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
        person_count   – total persons detected on bike
        person_boxes   – list of (x1,y1,x2,y2)
        helmet_boxes   – helmeted riders (x1,y1,x2,y2)
        nh_boxes       – un-helmeted riders (x1,y1,x2,y2)
    """
    count = len(persons_on_bike)

    if count < TRIPLE_THRESHOLD:
        return False, {}

    details = {
        'person_count': count,
        'person_boxes': [p[:4] for p in persons_on_bike],
        'helmet_boxes': [h[:4] for h in helmets_on_bike],
        'nh_boxes'    : [n[:4] for n in no_helmets_on_bike],
    }
    return True, details
