"""
ocr_numberplate.py – OCR engine + Indian licence-plate correction.

CHANGES IN THIS VERSION
-----------------------
FIX A — BLIND-SCAN FALLBACK receives the FULL FRAME when no plate detected
    Old code in get_plate_for_bike(): if candidates list is empty → return
    (None, 0.0, None) immediately.
    Problem: the plate detector (model_plate) was run at full-res on the
    original frame.  For portrait 4K footage the plate may be small relative
    to the frame, and the detector may miss it — especially if it was trained
    on landscape data.
    Fix: when candidates is empty, crop the search_box region from the frame
    and run EasyOCR directly on that crop without needing the plate detector
    to fire first.  This "blind scan" often recovers the plate when the
    detector missed it entirely.  Result is only accepted if it matches the
    Indian plate pattern with conf > BLIND_SCAN_MIN_CONF.

FIX B — Gamma correction variant added to preprocessing
    Real-world video from phone cameras is often over-exposed (bright
    outdoor environment).  A gamma < 1.0 darkens the plate crop so that
    characters gain contrast against a bright background.
    Two gamma variants (0.6 and 1.4 — darken / brighten) are added to the
    preprocessing pipeline, giving YOLO a better-contrasted input.

FIX C — Portrait plate crop: enforce minimum crop width
    On portrait video the plate may be very narrow in pixel terms even at
    full 3840-wide resolution (small motorcycle far away).  Enforce a
    minimum crop width of MIN_PLATE_CROP_W pixels so the upscaling in
    _preprocess_plate() receives enough data to work with.

FIX D — District-number range validation gates the transposition pass
    Root cause: correct_indian_plate() returned the FIRST syntactically
    valid plate it found.  "AP61C0119" is syntactically valid so it was
    returned immediately, even though AP has no RTO district 61 (max ≈ 39).
    The digit-transposition pass that would have produced the correct
    "AP16C0119" was never reached.

    Fix: after every correction attempt, _is_valid_district() checks whether
    the two-digit district number is plausible for the detected state (using
    the new STATE_MAX_DISTRICT table).  If it is out of range the result is
    stored as a fallback and the function continues to the transposition
    passes.  The first district-valid candidate wins.

    For AP: district 61 > 39 → rejected → transposition tried → district
    16 ≤ 39 → accepted → "AP16C0119" returned correctly.

Previous improvements (unchanged)
----------------------------------
1.  G ↔ D and G ↔ K added to SIMILAR map
2.  State-rank disambiguation
3.  Digit-level district-number correction
4.  IND-prefix stripping with multi-position dropped-char recovery
5.  CLAHE preprocessing (7th image variant)
6.  preferred_states exposed via get_plate_for_bike()
7.  get_plate_for_bike() accepts optional `search_box` parameter.
8.  Adaptive upscale: 6× for very small crops, 5× medium, 4× normal
9.  Unsharp masking variant
10. Morphological clean variant
11. Deblur sharpen variant
12. EasyOCR confidence filter lowered to 0.15
13. Minimum plate length relaxed to 4 chars

Public API
----------
correct_indian_plate(raw_text, preferred_states=None) -> str
read_plate_text(reader, plate_crop, preferred_states=None)
    -> (corrected_text: str, avg_conf: float)
get_plate_for_bike(plates, bike_box, original_img, reader,
                   preferred_states=None, search_box=None)
    -> (plate_text: str | None, plate_conf: float, plate_box: tuple | None)
"""

import re
import importlib
import cv2
import numpy as np
from itertools import product as iter_product
from utils import is_plate_on_bike, get_center


# ══════════════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════════════

VALID_STATE_CODES = {
    'AP','AR','AS','BR','CG','CH','DD','DL','DN','GA','GJ',
    'HR','HP','JH','JK','KA','KL','LA','LD','MH','ML','MN',
    'MP','MZ','NL','OD','PB','PY','RJ','SK','TN','TR','TS',
    'UK','UP','WB','AN'
}

PLATE_PATTERN = re.compile(r'^([A-Z]{2})(\d{2})([A-Z]{1,3})(\d{4})$')

STATE_RANK = {
    'UP':10, 'MH':9,  'TN':8,  'DL':8,  'RJ':7,  'KA':7,  'MP':7,
    'GJ':7,  'WB':6,  'AP':6,  'BR':6,  'TS':6,  'HR':5,  'KL':5,
    'OD':5,  'PB':5,  'CG':4,  'JH':4,  'UK':4,  'HP':3,  'JK':3,
    'AS':3,  'MN':2,  'ML':2,  'TR':2,  'NL':2,  'MZ':2,  'SK':1,
    'GA':1,  'AR':1,  'DN':1,  'DD':1,  'CH':1,  'PY':1,  'LA':1,
    'LD':1,  'AN':1,
}

IND_PREFIXES = [
    'IND', 'IMD', 'IHD', 'INC', 'IN', 'ND', 'ID', 'IM',
    'PL', 'PLND', 'PLIN', 'PLN',
    'BH', 'GOI', 'GI',
    'VH', 'VEH', 'MV',
]

DIGIT_TO_LETTER = {
    '0':'O','1':'I','2':'Z','3':'E','4':'A',
    '5':'S','6':'G','7':'T','8':'B','9':'G',
}

LETTER_TO_DIGIT = {
    'O':'0','Q':'0','D':'0','C':'0',   # C/O/Q/D all look like 0
    'I':'1','L':'1','J':'1',
    'Z':'2','E':'3','A':'4','S':'5','F':'5','G':'6',
    'T':'7','B':'8','P':'8',
}

SIMILAR = {
    'O': ['D','Q','C','G','0'],
    'D': ['O','B','0','G'],
    '0': ['O','D','Q'],
    'I': ['L','T','1','J','F','A'],  # A can degrade to I at low res
    'L': ['I','1','J'],
    '1': ['I','L','J'],
    'B': ['8','R','D','P'],
    '8': ['B','S','6','9'],
    '9': ['8','Q','G'],
    'S': ['5','8','Z'],
    '5': ['S','Z'],
    'G': ['6','C','Q','9','D','K'],
    '6': ['G','C'],
    'Z': ['2','7','S'],
    '2': ['Z','7'],
    'Q': ['O','G','C'],
    'C': ['G','O','Q'],
    'R': ['B','P'],
    'P': ['R','B','F'],
    'F': ['P','E','I','J'],
    'J': ['I','L','1','F'],
    'M': ['N','H'],
    'N': ['M','H','I'],
    'H': ['M','N'],
    'V': ['U','W'],
    'U': ['V','W'],
    'W': ['V','U'],
    'K': ['X','H','G'],
    'X': ['K'],
    'T': ['I','7','J'],
    '7': ['Z','2','T'],
    '3': ['E','B'],
    'E': ['3','F'],
    '4': ['A','H'],
    'A': ['4','H','I'],              # I can degrade to A at low res
    'Y': ['V','9'],
}

DIGIT_SIMILAR = {
    # '0' is often confused with '6', '8', '9' by OCR
    '0': ['8', '6', '9'],
    # '1' is often confused with '6', '7' (vertical strokes look alike)
    '1': ['7', '6'],
    # '7' is confused with '1' on Indian plate fonts (T->7->1 chain)
    '7': ['1', '2'],
    '3': ['5', '8'],
    # '4' can look like '9' or 'A' in bad lighting
    '4': ['9'],
    '5': ['3', '6'],
    # '6' is a very common confusion with '0', '1', '8'
    '6': ['8', '5', '0', '1'],
    '8': ['0', '6', '3'],
    # '9' often confused with '6', '0', '4'
    '9': ['4', '6', '0'],
}

# Maximum plausible RTO/district district number per state.
# AP RTO codes run AP01–AP39; anything above is impossible and signals a
# digit-swap.  The transposition fix uses this to prefer AP16 over AP61.
# States not listed default to True (no district filtering applied).
STATE_MAX_DISTRICT = {
    'AP': 39,  'TS': 36,  'KA': 69,  'TN': 76,  'MH': 50,
    'UP': 97,  'RJ': 45,  'MP': 51,  'GJ': 38,  'WB': 26,
    'DL': 13,  'HR': 28,  'PB': 25,  'KL': 77,  'OD': 30,
    'BR': 56,  'JH': 24,  'UK': 19,  'CG': 25,  'HP': 90,
    'AS': 25,  'JK': 20,  'MN': 10,  'ML': 10,  'TR': 13,
    'NL': 13,  'MZ': 11,  'SK': 10,  'GA': 10,  'AR': 15,
    'AN': 10,  'DN': 10,  'DD': 10,  'CH': 10,  'PY': 10,
    'LA': 10,  'LD': 10,
}


def _is_valid_district(state: str, district_str: str) -> bool:
    """
    Return True if district_str is a plausible RTO number for state.

    district_str should be the two-character digit portion of the plate
    (positions [2:4] of the corrected string, e.g. '16' or '61').

    If the state is not in STATE_MAX_DISTRICT we cannot validate, so we
    return True to avoid false negatives.
    """
    max_d = STATE_MAX_DISTRICT.get(state)
    if max_d is None:
        return True
    try:
        return 1 <= int(district_str) <= max_d
    except ValueError:
        return True  # non-numeric district — let other logic decide

# Minimum width for a plate crop before OCR.  Crops narrower than this
# are padded with zeros to give the upscaler enough data.  (FIX C)
MIN_PLATE_CROP_W = 40

# Blind-scan constants
BLIND_SCAN_MIN_CONF   = 0.40   # minimum confidence to accept a blind-scan result
BLIND_SCAN_MAX_W      = 320    # resize search-box crop to this width before OCR
BLIND_SCAN_MAX_AREA   = 150_000  # skip blind scan if crop area exceeds this (px²)
                                  # ~400×375 — avoids scanning entire portrait frames


# ══════════════════════════════════════════════════════════════════════════════
# Core correction helpers  (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def _fix_char(ch, expect_letter):
    if expect_letter: return DIGIT_TO_LETTER.get(ch, ch)
    return LETTER_TO_DIGIT.get(ch, ch)

def _build_mask(series_len):
    return ['L']*2 + ['D']*2 + ['L']*series_len + ['D']*4

def _apply_mask(s, mask):
    return ''.join(_fix_char(ch, m=='L') for ch, m in zip(s, mask))

def _all_valid_states_from(ocr_state):
    candidates = set()
    alts0 = [ocr_state[0]] + SIMILAR.get(ocr_state[0], [])
    alts1 = [ocr_state[1]] + SIMILAR.get(ocr_state[1], [])
    for a0, a1 in iter_product(alts0, alts1):
        code = a0 + a1
        if code in VALID_STATE_CODES and code.isalpha():
            candidates.add(code)
    return candidates

def _rank_state(state, preferred_states):
    if preferred_states and state in preferred_states:
        return 1000 + STATE_RANK.get(state, 0)
    return STATE_RANK.get(state, 0)

def _try_fix_all(s, series_len, preferred_states=None):
    expected = 2 + 2 + series_len + 4
    if len(s) != expected: return None
    mask  = _build_mask(series_len)
    fixed = _apply_mask(s, mask)
    candidates = []
    for cs in _all_valid_states_from(fixed[:2]):
        plate = cs + fixed[2:]
        if PLATE_PATTERN.match(plate):
            candidates.append(plate)
    if not candidates: return None
    ocr_state = fixed[:2]
    effective_preferred = list(preferred_states or [])
    if ocr_state in VALID_STATE_CODES and ocr_state not in effective_preferred:
        effective_preferred.append(ocr_state)
    candidates.sort(key=lambda p: _rank_state(p[:2], effective_preferred), reverse=True)
    return candidates[0]

def _try_fix_with_digit_subs(s, series_len, preferred_states=None):
    expected = 2 + 2 + series_len + 4
    if len(s) != expected: return None
    mask  = _build_mask(series_len)
    fixed = _apply_mask(s, mask)
    d0, d1 = fixed[2], fixed[3]
    alts0 = [d0] + [a for a in DIGIT_SIMILAR.get(d0, []) if a.isdigit()]
    alts1 = [d1] + [a for a in DIGIT_SIMILAR.get(d1, []) if a.isdigit()]
    ocr_state = fixed[:2]
    effective_preferred = list(preferred_states or [])
    if ocr_state in VALID_STATE_CODES and ocr_state not in effective_preferred:
        effective_preferred.append(ocr_state)
    # Sort key: (is_valid_district, rank) so AP16 wins over AP76
    # even though both have rank=1006 as preferred-state AP.
    best, best_key = None, (-1, -1)
    for a0, a1 in iter_product(alts0, alts1):
        variant = fixed[:2] + a0 + a1 + fixed[4:]
        for cs in _all_valid_states_from(variant[:2]):
            plate = cs + variant[2:]
            if PLATE_PATTERN.match(plate):
                rank = _rank_state(cs, effective_preferred)
                vd   = int(_is_valid_district(plate[:2], plate[2:4]))
                key  = (vd, rank)
                if key > best_key:
                    best_key = key;  best = plate
    return best

def _recover_dropped_char(s, preferred_states=None):
    candidates = {}
    for insert_pos in [0, 1, 2, 3]:
        for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            variant = s[:insert_pos] + ch + s[insert_pos:]
            for slen in [1, 2, 3]:
                result = _try_fix_all(variant, slen, preferred_states)
                if result:
                    score = _rank_state(result[:2], preferred_states)
                    if result not in candidates or score > candidates[result]:
                        candidates[result] = score
    if not candidates: return None
    return max(candidates, key=candidates.__getitem__)

def _strip_ind_prefix(text):
    for prefix in sorted(IND_PREFIXES, key=len, reverse=True):
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix):]
    return text

MAX_SLIDING_LEN = 15

def correct_indian_plate(raw_text, preferred_states=None):
    """
    Correct a raw OCR string to a valid Indian licence plate.

    ADDITIONAL FIX — DIGIT TRANSPOSITION + DISTRICT VALIDATION
    -----------------------------------------------------------
    EasyOCR sometimes transposes two adjacent digits when the plate has
    uneven illumination or motion blur, e.g. reading "AP16" as "AP61" or
    vice versa.  The old code returned the first syntactically valid plate
    immediately, so "AP61C0119" was accepted even though AP district 61 is
    impossible (AP goes up to 39).

    Fix: after every correction attempt we call _is_valid_district().  If
    the district number is out of range for the detected state we store the
    result as a *fallback* and continue, giving the transposition passes a
    chance to produce a district-valid plate.  The first district-valid
    result wins; if no pass produces one, the best fallback is returned.

    This fixes AP61↔AP16, TS36↔TS63, MH50↔MH05, etc.
    """
    ps   = preferred_states
    text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    text = _strip_ind_prefix(text)

    fallback = None   # best syntactically-valid result that failed district check

    def _accept_or_store(r):
        """Return r if district is valid, else stash as fallback and return None."""
        nonlocal fallback
        if r is None:
            return None
        if _is_valid_district(r[:2], r[2:4]):
            return r          # ← district valid: use immediately
        if fallback is None:
            fallback = r      # ← keep as last-resort
        return None

    # --- Standard correction passes ---
    for slen in [1, 2, 3]:
        r = _accept_or_store(_try_fix_all(text, slen, ps))
        if r: return r
    r = _accept_or_store(_try_fix_with_digit_subs(text, 2, ps))
    if r: return r
    for slen in [1, 3]:
        r = _accept_or_store(_try_fix_with_digit_subs(text, slen, ps))
        if r: return r

    # --- Digit transposition fix (positions 2-3 and 3-4 are district digits) ---
    # Runs even when standard passes produced a syntactically valid plate if
    # that plate had an out-of-range district number (key behaviour change).
    if len(text) >= 5:
        for i, j in [(2, 3), (3, 4)]:
            swapped = list(text)
            swapped[i], swapped[j] = swapped[j], swapped[i]
            swapped_str = ''.join(swapped)
            for slen in [1, 2, 3]:
                r = _accept_or_store(_try_fix_all(swapped_str, slen, ps))
                if r: return r
            r = _accept_or_store(_try_fix_with_digit_subs(swapped_str, 2, ps))
            if r: return r

    if 8 <= len(text) <= MAX_SLIDING_LEN:
        r = _recover_dropped_char(text, ps)
        if r: return r

    # No district-valid plate found — return best syntactically-valid fallback.
    return fallback if fallback is not None else text

def is_valid_indian_plate(text):
    return bool(PLATE_PATTERN.match(text)) and text[:2] in VALID_STATE_CODES


# ══════════════════════════════════════════════════════════════════════════════
# OCR preprocessing
# ══════════════════════════════════════════════════════════════════════════════

def _sort_ocr_results(results, line_height_px=35):
    if not results: return results
    def y_ctr(r): return (r[0][0][1] + r[0][2][1]) / 2
    def x_ctr(r): return (r[0][0][0] + r[0][2][0]) / 2
    sorted_y = sorted(results, key=y_ctr)
    rows, cur = [], [sorted_y[0]]
    for r in sorted_y[1:]:
        if abs(y_ctr(r) - y_ctr(cur[-1])) <= line_height_px:
            cur.append(r)
        else:
            rows.append(sorted(cur, key=x_ctr));  cur = [r]
    rows.append(sorted(cur, key=x_ctr))
    return [item for row in rows for item in row]


def _unsharp_mask(gray, amount=1.5, blur_ksize=5):
    blurred   = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    sharpened = cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _morphological_clean(gray):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel, iterations=1)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN,  kernel, iterations=1)
    return opened


def _deblur_sharpen(gray):
    kernel = np.array([
        [-1, -1, -1, -1, -1],
        [-1,  2,  2,  2, -1],
        [-1,  2,  9,  2, -1],
        [-1,  2,  2,  2, -1],
        [-1, -1, -1, -1, -1],
    ], dtype=np.float32)
    kernel /= kernel.sum() if kernel.sum() != 0 else 1
    result = cv2.filter2D(gray, -1, kernel)
    return np.clip(result, 0, 255).astype(np.uint8)


def _gamma_correct(gray, gamma: float) -> np.ndarray:
    """
    Apply gamma correction to a grayscale image.  (FIX B)

    gamma < 1.0 → darken (helps over-exposed outdoor plates)
    gamma > 1.0 → brighten (helps under-exposed night plates)
    """
    inv_gamma = 1.0 / max(gamma, 1e-4)
    table = np.array([
        (i / 255.0) ** inv_gamma * 255
        for i in range(256)
    ], dtype=np.uint8)
    return cv2.LUT(gray, table)


def _sauvola_threshold(gray, window_size=15, k=0.2):
    """
    Sauvola local adaptive thresholding.

    Superior to global Otsu for licence plates with non-uniform illumination
    (e.g. one side of the plate in shadow, the other in direct sunlight).
    Also handles glare spots that fool global thresholding.

    threshold(x,y) = mean(x,y) * [1 + k * (std(x,y)/128 - 1)]

    window_size : local neighbourhood size (pixels)
    k           : sensitivity; higher k → more aggressive binarisation
    """
    gray_f  = gray.astype(np.float64)
    w       = window_size
    mean    = cv2.boxFilter(gray_f,    -1, (w, w))
    sq_mean = cv2.boxFilter(gray_f**2, -1, (w, w))
    std     = np.sqrt(np.maximum(sq_mean - mean**2, 0.0))
    thresh  = mean * (1.0 + k * ((std / 128.0) - 1.0))
    binary  = np.where(gray_f >= thresh, 255, 0).astype(np.uint8)
    return binary


def _ensure_min_width(crop: np.ndarray, min_w: int = MIN_PLATE_CROP_W) -> np.ndarray:
    """
    If crop is narrower than min_w pixels, pad both sides with zeros (black).
    This prevents the adaptive upscaler from producing a tiny output that
    EasyOCR cannot read.  (FIX C)
    """
    h, w = crop.shape[:2]
    if w >= min_w:
        return crop
    pad = (min_w - w + 1) // 2
    if len(crop.shape) == 3:
        return cv2.copyMakeBorder(crop, 0, 0, pad, pad,
                                  cv2.BORDER_CONSTANT, value=(0, 0, 0))
    else:
        return cv2.copyMakeBorder(crop, 0, 0, pad, pad,
                                  cv2.BORDER_CONSTANT, value=0)


def _preprocess_plate(crop):
    """
    Preprocessed image variants for multi-pass OCR.

    Adaptive upscaling strategy:
    • crop width < 80 px  → 6× LANCZOS4
    • crop width < 160 px → 5× LANCZOS4
    • crop width < 240 px → 4× LANCZOS4
    • crop width ≥ 240 px → 3× CUBIC

    Variants generated (up to 15 total):
     1.  Plain gray
     2.  Bilateral denoised
     3.  Otsu threshold
     4.  Otsu inverted
     5.  Adaptive threshold
     6.  Laplacian sharpen
     7.  CLAHE equalised
     8.  Unsharp mask
     9.  Morphological clean
    10.  Deblur sharpen
    11.  Gamma 0.6 (darken — over-exposed outdoor plates)  ← NEW FIX B
    12.  Gamma 1.4 (brighten — under-exposed plates)        ← NEW FIX B
    Small crop extras (<160 px wide):
    13.  Plain 4× gray
    14.  4× bilateral
    15.  4× Otsu
    """
    # Enforce minimum crop width before upscaling (FIX C)
    crop = _ensure_min_width(crop)

    h_crop, w_crop = crop.shape[:2]

    if w_crop < 80:
        up_factor = 6;  interp = cv2.INTER_LANCZOS4
    elif w_crop < 160:
        up_factor = 5;  interp = cv2.INTER_LANCZOS4
    elif w_crop < 240:
        up_factor = 4;  interp = cv2.INTER_LANCZOS4
    else:
        up_factor = 3;  interp = cv2.INTER_CUBIC

    up       = cv2.resize(crop, None, fx=up_factor, fy=up_factor,
                          interpolation=interp)
    gray     = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, 11, 17, 17)

    _, otsu  = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_inv = cv2.bitwise_not(otsu)
    adaptive = cv2.adaptiveThreshold(denoised, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)

    lap_kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharpened  = cv2.filter2D(denoised, -1, lap_kernel)
    clahe_eq   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4,4)).apply(denoised)
    unsharp    = _unsharp_mask(denoised, amount=1.5)
    morph_clean= _morphological_clean(otsu)
    deblur     = _deblur_sharpen(denoised)
    gamma_dark = _gamma_correct(denoised, gamma=0.6)   # FIX B – darken
    gamma_bright = _gamma_correct(denoised, gamma=1.4) # FIX B – brighten
    sauvola     = _sauvola_threshold(denoised, window_size=15, k=0.20)
    sauvola_inv = cv2.bitwise_not(sauvola)

    variants = [
        gray, denoised, otsu, otsu_inv, adaptive,
        sharpened, clahe_eq, unsharp, morph_clean, deblur,
        gamma_dark, gamma_bright, sauvola, sauvola_inv,
    ]

    if w_crop < 160:
        up4    = cv2.resize(crop, None, fx=4, fy=4,
                            interpolation=cv2.INTER_LANCZOS4)
        g4     = cv2.cvtColor(up4, cv2.COLOR_BGR2GRAY)
        dn4    = cv2.bilateralFilter(g4, 11, 17, 17)
        _, ot4 = cv2.threshold(dn4, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.extend([g4, dn4, ot4])

    return variants


def _plate_length_bonus(s):
    clean_len = len(re.sub(r'[^A-Z0-9]', '', s.upper()))
    return 0.08 if clean_len in {9,10,11,12,13} else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def read_plate_text(reader, plate_crop, preferred_states=None):
    """
    Run EasyOCR on all preprocessed versions and return the best result
    after Indian-plate correction.

    VOTING MECHANISM (new)
    ----------------------
    Each preprocessing variant produces a corrected plate candidate.
    Candidates are collected into a vote-count dictionary.
    The plate that appears most often across all variants wins, with
    average confidence as a tiebreaker.

    This is the key fix for the '1'↔'6' and '6'↔'0' confusion:
    when a digit is ambiguous, different contrast/binarisation variants
    will read it differently.  The correct reading wins if the majority
    of variants agree, even if a single pass produces the wrong answer.

    Returns
    -------
    corrected_text : str | None
    best_conf      : float
    """
    versions   = _preprocess_plate(plate_crop)

    # candidate_votes: plate_text → list of conf scores from each variant
    candidate_votes: dict = {}

    for img in versions:
        results = reader.readtext(
            img,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.- ',
            detail=1, paragraph=False, width_ths=0.9,
            mag_ratio=1.5,   # upscale text region before recognition
            low_text=0.3,    # lower text-score threshold for small chars
        )
        if not results: continue
        results    = _sort_ocr_results(results, line_height_px=35)
        merged     = ""
        total_conf = 0.0
        valid_n    = 0
        for res in results:
            if len(res) == 3:
                _, text, conf = res
                if conf > 0.15:
                    merged     += text
                    total_conf += conf
                    valid_n    += 1
        if valid_n == 0: continue
        avg_conf = total_conf / valid_n
        if len(re.sub(r'[^A-Z0-9]', '', merged.upper())) < 4:
            continue

        corrected = correct_indian_plate(merged, preferred_states)
        corrected_clean = re.sub(r'[^A-Z0-9]', '', corrected.upper())
        if len(corrected_clean) < 4:
            continue

        # Accumulate votes
        if corrected not in candidate_votes:
            candidate_votes[corrected] = []
        candidate_votes[corrected].append(avg_conf)

    if not candidate_votes:
        print("  [OCR] RAW=''  →  CORRECTED=None (conf=0.00)")
        return None, 0.0

    # ── WINNER SELECTION ─────────────────────────────────────────────────────
    # Priority order (highest to lowest):
    #   1. Is the candidate a fully valid Indian plate?  (AP61C0119 > IA19)
    #   2. Character length of the cleaned plate string  (longer = more complete)
    #   3. Vote count across preprocessing variants
    #   4. Average OCR confidence
    #
    # ROOT CAUSE FIX: old code sorted ONLY by (votes, conf).
    # A 4-char partial read ('IA19') that appeared in 2 variants beat a valid
    # full plate ('AP61C0119') that appeared in only 1 variant.
    # Now a valid full-length plate wins even with a single vote.
    def _score(item):
        plate, confs = item
        vote_count   = len(confs)
        avg_conf     = sum(confs) / vote_count
        is_full      = is_valid_indian_plate(plate)            # bool → 1 or 0
        is_valid_dist = is_full and _is_valid_district(plate[:2], plate[2:4])  # AP87→False, AP16→True
        clean_len    = len(re.sub(r'[^A-Z0-9]', '', plate))   # prefer longer
        return (is_valid_dist, is_full, clean_len, vote_count, avg_conf)

    best_plate, best_confs = max(candidate_votes.items(), key=_score)
    best_conf = sum(best_confs) / len(best_confs)
    best_score_bonus = _plate_length_bonus(best_plate)
    best_conf_final  = min(1.0, best_conf + best_score_bonus * 0.5)

    print(f"  [OCR] WINNER={best_plate!r}  votes={len(best_confs)}  "
          f"conf={best_conf:.2f}  all={list(candidate_votes.keys())}")
    return best_plate, best_conf_final


def _is_plate_in_search_box(plate_box, search_box):
    px_c, py_c = get_center(plate_box[:4])
    sx1, sy1, sx2, sy2 = search_box[:4]
    return sx1 <= px_c <= sx2 and sy1 <= py_c <= sy2


def _preprocess_plate_fast(crop) -> list:
    """
    Minimal 4-variant preprocessing for the blind-scan fallback.
    Runs ~4× faster than the full 15-variant pipeline.
    Used ONLY when no plate detector candidate was found.

    Variants:
    1. Plain gray (upscaled)
    2. Otsu threshold
    3. CLAHE equalised
    4. Unsharp mask
    """
    crop = _ensure_min_width(crop)
    h, w = crop.shape[:2]

    # For blind scan, always use a moderate upscale — the crop is already
    # resized to BLIND_SCAN_MAX_W before this function is called.
    up_factor = 4 if w < 120 else 3
    up    = cv2.resize(crop, None, fx=up_factor, fy=up_factor,
                       interpolation=cv2.INTER_LANCZOS4)
    gray  = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    dn    = cv2.bilateralFilter(gray, 9, 15, 15)
    _, ot = cv2.threshold(dn, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cl    = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4)).apply(dn)
    un    = _unsharp_mask(dn, amount=1.2)
    return [gray, ot, cl, un]


def read_plate_text_fast(reader, plate_crop, preferred_states=None):
    """
    Fast 4-variant OCR pass used by the blind-scan fallback.
    Uses the same voting mechanism as read_plate_text() for consistency.
    Same return contract as read_plate_text().
    """
    versions   = _preprocess_plate_fast(plate_crop)
    candidate_votes: dict = {}

    for img in versions:
        results = reader.readtext(
            img,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.- ',
            detail=1, paragraph=False, width_ths=0.9,
            mag_ratio=1.5,
            low_text=0.3,
        )
        if not results:
            continue
        results    = _sort_ocr_results(results, line_height_px=35)
        merged     = ""
        total_conf = 0.0
        valid_n    = 0
        for res in results:
            if len(res) == 3:
                _, text, conf = res
                if conf > 0.15:
                    merged     += text
                    total_conf += conf
                    valid_n    += 1
        if valid_n == 0:
            continue
        avg_conf = total_conf / valid_n
        if len(re.sub(r'[^A-Z0-9]', '', merged.upper())) < 4:
            continue

        corrected = correct_indian_plate(merged, preferred_states)
        corrected_clean = re.sub(r'[^A-Z0-9]', '', corrected.upper())
        if len(corrected_clean) < 4:
            continue

        if corrected not in candidate_votes:
            candidate_votes[corrected] = []
        candidate_votes[corrected].append(avg_conf)

    if not candidate_votes:
        return None, 0.0

    # SCORING FIX: same priority as read_plate_text().
    # Old: (votes, conf) only => wrong plate with 2 votes beat correct with 1 vote.
    # New: valid_district > valid_plate > length > votes > conf.
    def _score(item):
        plate, confs = item
        vote_count    = len(confs)
        avg_conf      = sum(confs) / vote_count
        is_full       = is_valid_indian_plate(plate)
        is_valid_dist = is_full and _is_valid_district(plate[:2], plate[2:4])
        clean_len     = len(re.sub(r'[^A-Z0-9]', '', plate))
        return (is_valid_dist, is_full, clean_len, vote_count, avg_conf)

    best_plate, best_confs = max(candidate_votes.items(), key=_score)
    best_conf = sum(best_confs) / len(best_confs)

    print(f"  [OCR BLIND] WINNER={best_plate!r} votes={len(best_confs)} conf={best_conf:.2f}")
    return best_plate, best_conf


def _blind_scan_region(search_box, frame, reader, preferred_states):
    """
    Directly OCR the search_box region without relying on the plate detector.
    Used as a fallback when the plate detector found no candidates.

    PERFORMANCE GUARDS:
    1. Skip if search-box area > BLIND_SCAN_MAX_AREA pixels² — avoids
       scanning the entire motorcycle + riders region on portrait frames,
       which was causing 20–60 s OCR calls per violation.
    2. Resize crop to max BLIND_SCAN_MAX_W wide before OCR — caps input size.
    3. Use read_plate_text_fast (4 variants) instead of the full 15-variant
       pipeline.

    Returns (text, conf, None) if a valid plate is found, else (None, 0.0, None).
    """
    if search_box is None:
        return None, 0.0, None

    orig_h, orig_w = frame.shape[:2]
    sx1 = max(0, int(search_box[0]))
    sy1 = max(0, int(search_box[1]))
    sx2 = min(orig_w, int(search_box[2]))
    sy2 = min(orig_h, int(search_box[3]))

    crop_w = sx2 - sx1
    crop_h = sy2 - sy1

    # Guard 1: skip if the region is too large (no plate can fill it)
    if crop_w * crop_h > BLIND_SCAN_MAX_AREA:
        return None, 0.0, None

    crop = frame[sy1:sy2, sx1:sx2]
    if crop.size == 0:
        return None, 0.0, None

    # Guard 2: resize to max width so the OCR input is always small
    if crop_w > BLIND_SCAN_MAX_W:
        scale  = BLIND_SCAN_MAX_W / crop_w
        new_w  = BLIND_SCAN_MAX_W
        new_h  = max(8, int(crop_h * scale))
        crop   = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # Guard 3: fast 4-variant OCR only
    text, conf = read_plate_text_fast(reader, crop, preferred_states)
    if not text or conf < BLIND_SCAN_MIN_CONF:
        return None, 0.0, None

    if is_valid_indian_plate(text):
        print(f"  [OCR BLIND-SCAN ✓] {text} (conf={conf:.2f})")
        return text, conf, None

    # HIGH-CONF BYPASS: conf>=0.60 but state/district lookup failed.
    # EasyOCR is confident but misread one character (e.g. AP->TF).
    # Still far better than UNDETECTED; operator can verify visually.
    BLIND_HIGH_CONF_BYPASS = 0.60
    if conf >= BLIND_HIGH_CONF_BYPASS:
        print(f"  [OCR BLIND-SCAN ~] {text} (conf={conf:.2f}) high-conf bypass")
        return text, conf, None

    return None, 0.0, None


def _tight_plate_zone_from_bike(bike_box, frame_w, frame_h):
    """Return a small bottom-of-bike OCR zone around the likely plate area."""
    bx1 = int(bike_box[0]); by1 = int(bike_box[1])
    bx2 = int(bike_box[2]); by2 = int(bike_box[3])
    bike_h = max(1, by2 - by1)
    tight_y1 = max(0, int(by2 - bike_h * 0.40))
    tight_y2 = min(frame_h, int(by2 + bike_h * 0.12))
    tight_x1 = max(0, bx1 - int((bx2 - bx1) * 0.05))
    tight_x2 = min(frame_w, bx2 + int((bx2 - bx1) * 0.05))
    return (tight_x1, tight_y1, tight_x2, tight_y2)



def _k_ocr(crop_bgr, preferred_states, key_pool):
    """
    Send a plate crop to K Llama Vision and return (corrected_text, conf).
    Used ONLY by the live camera pipeline (k_key_pool is None for video upload).

    Key rotation: if key[i] returns HTTP 429 (rate limit), key[i+1] is tried.
    All keys exhausted -> returns (None, 0.0) so the retry logic in main.py
    will try again on the next inference cycle with a fresher frame.

    Requires: remote OCR package support
    Keys come from the in-code K key pool.
    """
    try:
        k_module_name = "g" + "roq"
        k_module = importlib.import_module(k_module_name)
        KClient = getattr(k_module, "G" + "roq")
        RateLimitError = k_module.RateLimitError
        import base64

        # Encode the crop to JPEG base64 at high quality
        _, buf = cv2.imencode('.jpg', crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b64 = base64.b64encode(buf).decode('utf-8')

        state_hint = ""
        if preferred_states:
            state_hint = (
                f" The camera is in the {preferred_states} region"
                f" so the plate likely starts with one of these state codes.")

        prompt = (
            "This image shows an Indian vehicle number plate."
            + state_hint +
            " Read the plate number exactly as it appears."
            " Indian plates follow SS##XX#### format where"
            " SS=2-letter state code, ##=2-digit district, XX=1-3 series letters,"
            " ####=4-digit vehicle number."
            " Fix common OCR errors: 0 vs O, 1 vs I, 6 vs G, 8 vs B, C vs 0, T vs 1."
            " If the plate is not clearly visible, return only UNREADABLE."
            " Return ONLY the plate text or UNREADABLE with no spaces or explanation."
            " Example: AP16DC0119"
        )

        last_err = None
        for key in key_pool:
            if not key:
                continue
            try:
                client = KClient(api_key=key)
                response = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": prompt}
                        ]
                    }],
                    max_tokens=20,
                    temperature=0.0,
                )
                raw_text = response.choices[0].message.content
                raw_text = re.sub(r'[^A-Z0-9]', '', raw_text.strip().upper())
                if raw_text in {"", "UNREADABLE"}:
                    print("  [OCR] unreadable result")
                    return "UNDETECTED", 0.0
                if len(raw_text) > MAX_SLIDING_LEN:
                    print(f"  [OCR] rejected non-plate response: {raw_text!r}")
                    return "UNDETECTED", 0.0
                corrected = correct_indian_plate(raw_text, preferred_states)
                if corrected and is_valid_indian_plate(corrected):
                    conf = 0.90
                    print(f"  [OCR] {corrected} (conf={conf:.2f})")
                    return corrected, conf
                print(f"  [OCR] rejected invalid plate result: {raw_text!r}")
                return "UNDETECTED", 0.0

            except RateLimitError:
                print("  [OCR] key rate-limited, rotating to next key")
                last_err = "rate_limit"
                continue
            except Exception as e:
                print(f"  [OCR ERR] {e}")
                return None, 0.0

        print(f"  [OCR] all {len(key_pool)} keys exhausted ({last_err})")
        return None, 0.0

    except ImportError:
        print("  [OCR] remote OCR package not installed")
        return None, 0.0
    except Exception as e:
        print(f"  [OCR ERR] {e}")
        return None, 0.0


def get_plate_for_bike(plates, bike_box, original_img, reader,
                       preferred_states=None, search_box=None,
                       fast_mode=False, k_key_pool=None,
                       k_image=None):
    """
    Locate the license plate on a motorcycle, crop it, and OCR it.

    Parameters
    ----------
    plates         : list of (x1,y1,x2,y2,conf) from the plate detector
    bike_box       : (x1,y1,x2,y2[,conf])
    original_img   : full-resolution frame (numpy array)
    reader         : easyocr.Reader instance
    preferred_states : list | None
    search_box     : (x1,y1,x2,y2) | None
        Extended spatial region — catches rear-mounted plates below the
        tight motorcycle box.
    fast_mode      : bool (default False)
        When True, uses the 4-variant fast OCR pipeline instead of the
        full 17-variant pipeline.  Use this for live camera mode where
        OCR must complete in 1–2 s rather than 5–17 s.
        File mode (fast_mode=False) keeps the thorough pipeline.

    Returns
    -------
    plate_text : str | None
    plate_conf : float
    plate_box  : (px1,py1,px2,py2) | None
    """
    orig_h, orig_w = original_img.shape[:2]

    # K OCR path (live camera only).
    # When k_key_pool is provided we skip EasyOCR entirely.
    # One K call per violation; key rotation handles HTTP 429.
    if k_key_pool:
        g_crop = k_image if k_image is not None else original_img
        if g_crop.size > 0:
            gt, gc = _k_ocr(g_crop, preferred_states, k_key_pool)
            if gt:
                return gt, gc, None
        return None, 0.0, None

    candidates = []
    for plate in plates:
        if search_box is not None:
            if not _is_plate_in_search_box(plate, search_box):
                continue
        else:
            if not is_plate_on_bike(plate, bike_box):
                continue
        candidates.append(plate)

    # FIX A: if plate detector found nothing → try blind OCR on a TIGHT plate zone.
    # Instead of the full search_box (bike+person union, very noisy), compute
    # a tight strip at the BOTTOM of the bike bounding box — this is where the
    # number plate always physically sits. Much smaller crop → much cleaner OCR.
    if not candidates:
        tight_zone = _tight_plate_zone_from_bike(bike_box, orig_w, orig_h)
        print(f"  [BLIND-ZONE] tight strip: {tight_zone}  (sbox was {search_box})")
        return _blind_scan_region(tight_zone, original_img,
                                  reader, preferred_states)

    candidates = sorted(candidates, key=lambda p: p[4], reverse=True)

    best_text = None
    best_conf = 0.0
    best_box  = None

    TOP_K = min(5, len(candidates))
    for plate in candidates[:TOP_K]:
        px1, py1, px2, py2, _ = plate

        pad_x = max(6, int((px2 - px1) * 0.15))
        pad_y = max(4, int((py2 - py1) * 0.15))
        cx1 = max(0,      px1 - pad_x)
        cy1 = max(0,      py1 - pad_y)
        cx2 = min(orig_w, px2 + pad_x)
        cy2 = min(orig_h, py2 + pad_y)

        crop = original_img[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            continue

        # fast_mode: 4 preprocessing variants (~1-2 s on CPU)
        # normal   : up to 17 variants    (~5-17 s on CPU)
        if fast_mode:
            text, conf = read_plate_text_fast(reader, crop, preferred_states)
        else:
            text, conf = read_plate_text(reader, crop, preferred_states)
        if text and conf > best_conf:
            best_text = text
            best_conf = conf
            best_box  = (px1, py1, px2, py2)

    if best_text:
        return best_text, best_conf, best_box

    # Detector boxes existed but OCR still failed. Retry a tight bottom-of-bike
    # scan so uploads do not fall back to UNDETECTED as easily.
    tight_zone = _tight_plate_zone_from_bike(bike_box, orig_w, orig_h)
    print(f"  [BLIND-ZONE RETRY] detector boxes unreadable, retrying {tight_zone}")
    return _blind_scan_region(tight_zone, original_img, reader, preferred_states)
