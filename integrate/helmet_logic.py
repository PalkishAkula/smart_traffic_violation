"""
helmet_logic.py – Violation Type 1: Rider without a helmet.

Video pipeline API
------------------
In the video pipeline, detections are already filtered to one motorcycle.
This module receives pre-filtered lists for that single bike.

check_helmet_violation(no_helmets_on_bike, helmets_on_bike)
    → (violated: bool, details: dict)
"""


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
        rider_boxes    – list of (x1,y1,x2,y2) of riders without helmets
        helmet_boxes   – list of (x1,y1,x2,y2) of riders with helmets
        n_no_helmet    – count of riders without helmets
        n_helmet       – count of riders with helmets
    """
    if not no_helmets_on_bike:
        return False, {}

    details = {
        'rider_boxes' : [b[:4] for b in no_helmets_on_bike],
        'helmet_boxes': [b[:4] for b in helmets_on_bike],
        'n_no_helmet' : len(no_helmets_on_bike),
        'n_helmet'    : len(helmets_on_bike),
    }
    return True, details