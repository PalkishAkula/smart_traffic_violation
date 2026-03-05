"""
co_riding.py – Violation Type 3: Co-rider (pillion) without a helmet.

Video pipeline API
------------------
check_co_riding(persons_on_bike, helmets_on_bike, no_helmets_on_bike, bike_box)
    → (violated: bool, details: dict)
"""

from utils import identify_pillion, get_iou

HELMET_IOU_THRESH = 0.20   # IoU required to say a helmet belongs to a person


def _has_helmet(person_box, helmets):
    return any(get_iou(person_box[:4], h[:4]) >= HELMET_IOU_THRESH
               for h in helmets)


def _has_no_helmet(person_box, no_helmets):
    return any(get_iou(person_box[:4], n[:4]) >= HELMET_IOU_THRESH
               for n in no_helmets)


def check_co_riding(persons_on_bike:     list,
                    helmets_on_bike:     list,
                    no_helmets_on_bike:  list,
                    bike_box:            tuple) -> tuple:
    """
    Determine if exactly 2 persons are on the motorcycle and the pillion
    (back-seat passenger) is not wearing a helmet.

    Note: when 3+ persons are present, this is TRIPLE_RIDING – co-riding
    logic is intentionally skipped (triple-riding takes precedence).

    Parameters
    ----------
    persons_on_bike    : list of (x1,y1,x2,y2,conf)  COCO persons on bike
    helmets_on_bike    : list of (x1,y1,x2,y2,conf)  helmet detections on bike
    no_helmets_on_bike : list of (x1,y1,x2,y2,conf)  no-helmet detections on bike
    bike_box           : (x1,y1,x2,y2)

    Returns
    -------
    violated : bool
    details  : dict
        driver_box  – (x1,y1,x2,y2) of the driver
        pillion_box – (x1,y1,x2,y2) of the pillion
    """
    if len(persons_on_bike) != 2:
        return False, {}   # need exactly 2 – triple riding handled separately

    pillion = identify_pillion(persons_on_bike, bike_box)
    if pillion is None:
        return False, {}

    pillion_box = pillion[:4]
    driver = next(
        p for p in persons_on_bike
        if (p[0], p[1]) != (pillion[0], pillion[1])
    )
    driver_box = driver[:4]

    # Pillion has no helmet if:
    #   (a) a no-helmet detection overlaps them, OR
    #   (b) no helmet detection overlaps them
    pillion_violated = (
        _has_no_helmet(pillion_box, no_helmets_on_bike) or
        not _has_helmet(pillion_box, helmets_on_bike)
    )

    if not pillion_violated:
        return False, {}

    details = {
        'driver_box' : driver_box,
        'pillion_box': pillion_box,
    }
    return True, details
