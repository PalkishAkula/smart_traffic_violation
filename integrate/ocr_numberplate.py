"""
ocr_numberplate.py – OCR engine + Indian licence-plate correction.

Key fixes in this version
--------------------------
1.  G ↔ D and G ↔ K added to SIMILAR map
2.  State-rank disambiguation
3.  Digit-level district-number correction
4.  IND-prefix stripping with multi-position dropped-char recovery
5.  CLAHE preprocessing (7th image variant)
6.  preferred_states exposed via get_plate_for_bike()

Change in this version
----------------------
7.  get_plate_for_bike() now accepts an optional `search_box` parameter.
    When provided, plate detections are spatially filtered against
    `search_box` (the extended union box built in main.py) rather than
    the raw `bike_box`. This allows the plate to be found even when it
    is detected BELOW or BESIDE the tight motorcycle bounding box, which
    is common for rear-mounted Indian number plates.

    bike_box  : still used for is_plate_on_bike() fallback check
    search_box: wider box (bike + persons + no-helmets extended downward)
                used as the PRIMARY spatial filter

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
    'IND', 'IMD', 'IHD', 'INC', 'IN', 'ND', 'ID', 'IM',  # original
    'PL', 'PLND', 'PLIN', 'PLN',   # "PLATE" border text
    'BH', 'GOI', 'GI',             # Bharat / Govt. of India watermarks
    'VH', 'VEH', 'MV',             # "VEHICLE" abbreviations on some plates
]

DIGIT_TO_LETTER = {
    '0':'O','1':'I','2':'Z','3':'E','4':'A',
    '5':'S','6':'G','7':'T','8':'B','9':'G',
}

LETTER_TO_DIGIT = {
    'O':'0','Q':'0','D':'0','I':'1','L':'1','J':'1',
    'Z':'2','E':'3','A':'4','S':'5','F':'5','G':'6',
    'T':'7','B':'8','P':'8',
}

SIMILAR = {
    'O': ['D','Q','C','G','0'],
    'D': ['O','B','0','G'],
    '0': ['O','D','Q'],
    'I': ['L','T','1','J','F'],
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
    'A': ['4','H'],
    'Y': ['V','9'],
}

DIGIT_SIMILAR = {
    '0':['8'],'1':['7'],'3':['5','8'],
    '5':['3','6'],'6':['8','5'],'8':['0','6','3'],'9':['4'],
}


# ══════════════════════════════════════════════════════════════════════════════
# Core correction helpers
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
    # Give the OCR-read state code strong preference over SIMILAR-map
    # alternatives so that a correctly-read state (e.g. 'HR') is not
    # replaced by a higher-population-ranked state (e.g. 'MP').
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
    # Give the OCR-read state strong preference (same logic as _try_fix_all).
    ocr_state = fixed[:2]
    effective_preferred = list(preferred_states or [])
    if ocr_state in VALID_STATE_CODES and ocr_state not in effective_preferred:
        effective_preferred.append(ocr_state)
    best, best_rank = None, -1
    for a0, a1 in iter_product(alts0, alts1):
        variant = fixed[:2] + a0 + a1 + fixed[4:]
        for cs in _all_valid_states_from(variant[:2]):
            plate = cs + variant[2:]
            if PLATE_PATTERN.match(plate):
                rank = _rank_state(cs, effective_preferred)
                if rank > best_rank:
                    best_rank = rank;  best = plate
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
    for prefix in IND_PREFIXES:
        if text.startswith(prefix):
            remainder = text[len(prefix):]
            if 8 <= len(remainder) <= 11:
                return remainder
    return None

def _sliding_window_extract(text, preferred_states=None):
    for slen in [1, 2, 3]:
        target = 2 + 2 + slen + 4
        for start in range(len(text) - target + 1):
            substr = text[start:start+target]
            r = _try_fix_all(substr, slen, preferred_states)
            if r: return r
            r = _try_fix_with_digit_subs(substr, slen, preferred_states)
            if r: return r
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Main correction entry point
# ══════════════════════════════════════════════════════════════════════════════

def correct_indian_plate(raw_text, preferred_states=None):
    """
    Correct an OCR-read licence plate string to a valid Indian plate format.
    Returns best corrected plate, or cleaned original text if nothing matches.
    """
    text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    if len(text) < 7 or len(text) > 15:
        return raw_text.strip()
    ps = preferred_states
    for slen in [1,2,3]:
        r = _try_fix_all(text, slen, ps)
        if r: return r
    for slen in [1,2,3]:
        r = _try_fix_with_digit_subs(text, slen, ps)
        if r: return r
    stripped = _strip_ind_prefix(text)
    if stripped:
        for slen in [1,2,3]:
            r = _try_fix_all(stripped, slen, ps)
            if r: return r
        for slen in [1,2,3]:
            r = _try_fix_with_digit_subs(stripped, slen, ps)
            if r: return r
        r = _recover_dropped_char(stripped, ps)
        if r: return r
    # ── Guard: if text is much longer than the longest valid Indian plate ──────
    # A valid plate is at most XX00XXX0000 = 11 chars.
    # OCR commonly prepends 2-4 extra chars from plate border printing
    # (e.g. "PL", "IND", "GOI") giving strings 12-15 chars long.
    # We MUST still run sliding-window on these to extract the real plate.
    #
    # Old guard was MAX_PLATE_LEN = 11  →  blocked sliding window for 12+ char
    # strings  →  OCR returned raw garbled text  →  PLATE UNREAD.
    #
    # Fix: raise the sliding-window limit to 15.  Strings longer than 15 are
    # genuine multi-region noise (two separate texts merged by EasyOCR) and
    # should be returned as-is rather than risk wrong extractions.
    MAX_SLIDING_LEN = 15   # was 11 – too restrictive
    if len(text) > MAX_SLIDING_LEN:
        return text

    r = _sliding_window_extract(text, ps)
    if r: return r
    if 8 <= len(text) <= MAX_SLIDING_LEN:
        r = _recover_dropped_char(text, ps)
        if r: return r
    return text

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


def _preprocess_plate(crop):
    """
    Preprocessed image variants for multi-pass OCR.

    Base: 7 variants at 3× upscale.
    Extra: 3 additional variants at 4× upscale when the crop is small
           (< 120 px wide).  Motorcycle rear plates are often tiny in the
           frame; the extra resolution helps EasyOCR resolve individual chars.
    """
    h_crop, w_crop = crop.shape[:2]

    # ── 3× variants (always generated) ───────────────────────────────────────
    up       = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray     = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, 11, 17, 17)
    _, otsu  = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_inv = cv2.bitwise_not(otsu)
    adaptive = cv2.adaptiveThreshold(denoised, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)
    kernel    = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharpened = cv2.filter2D(denoised, -1, kernel)
    clahe_eq  = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4,4)).apply(denoised)
    variants  = [gray, denoised, otsu, otsu_inv, adaptive, sharpened, clahe_eq]

    # ── 4× extra variants for small crops ────────────────────────────────────
    if w_crop < 120:
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
    Run EasyOCR on all 7 preprocessed versions and return the best result
    after Indian-plate correction.

    Returns
    -------
    corrected_text : str
    best_conf      : float
    """
    versions   = _preprocess_plate(plate_crop)
    best_text  = ""
    best_score = 0.0

    for img in versions:
        results = reader.readtext(
            img,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.- ',
            detail=1, paragraph=False, width_ths=0.9,
        )
        if not results: continue
        results    = _sort_ocr_results(results, line_height_px=35)
        merged     = ""
        total_conf = 0.0
        valid_n    = 0
        for res in results:
            if len(res) == 3:
                _, text, conf = res
                if conf > 0.20:
                    merged     += text
                    total_conf += conf
                    valid_n    += 1
        if valid_n == 0: continue
        avg_conf = total_conf / valid_n
        score    = avg_conf + _plate_length_bonus(merged)
        if score > best_score and len(re.sub(r'[^A-Z0-9]', '', merged.upper())) >= 6:
            best_score = avg_conf
            best_text  = merged

    if not best_text:
        print("  [OCR] RAW=''  →  CORRECTED=None (conf=0.00)")
        return None, 0.0

    corrected = correct_indian_plate(best_text, preferred_states)
    corrected_clean = re.sub(r'[^A-Z0-9]', '', corrected.upper())
    if len(corrected_clean) < 6:
        print(f"  [OCR] RAW={best_text!r}  →  CORRECTED=None "
              f"(too short: {corrected!r}, conf={best_score:.2f})")
        return None, 0.0

    print(f"  [OCR] RAW={best_text!r}  →  CORRECTED={corrected!r}  "
          f"(conf={best_score:.2f})")
    return corrected, best_score


def _is_plate_in_search_box(plate_box, search_box):
    """
    Return True if the centre of plate_box falls within search_box.
    search_box may be wider/taller than the raw motorcycle box
    (e.g. extended downward to catch rear plates).
    """
    px_c, py_c = get_center(plate_box[:4])
    sx1, sy1, sx2, sy2 = search_box[:4]
    return sx1 <= px_c <= sx2 and sy1 <= py_c <= sy2


def get_plate_for_bike(plates, bike_box, original_img, reader,
                       preferred_states=None, search_box=None):
    """
    Locate the license plate on a motorcycle, crop it, and OCR it.

    Parameters
    ----------
    plates         : list of (x1,y1,x2,y2,conf)
    bike_box       : (x1,y1,x2,y2[,conf]) – tight motorcycle box from tracker
    original_img   : full-resolution frame (numpy array)
    reader         : easyocr.Reader instance
    preferred_states : list | None
    search_box     : (x1,y1,x2,y2) | None
        Extended spatial region for plate lookup. When provided, plates are
        matched against this wider box FIRST (union of bike + persons +
        no-helmets, extended 40% downward). Falls back to is_plate_on_bike()
        with the raw bike_box if search_box is None.

        This is the key improvement: Indian rear number plates are often
        detected BELOW the motorcycle's tight bounding box. The search_box
        extends downward to catch them.

    Returns
    -------
    plate_text : str | None
    plate_conf : float
    plate_box  : (px1,py1,px2,py2) | None
    """
    orig_h, orig_w = original_img.shape[:2]

    candidates = []
    for plate in plates:
        if search_box is not None:
            if not _is_plate_in_search_box(plate, search_box):
                continue
        else:
            if not is_plate_on_bike(plate, bike_box):
                continue
        candidates.append(plate)

    if not candidates:
        return None, 0.0, None

    # Sort by detector confidence descending — but we still try multiple and pick
    # the best OCR result (the top detector box is often blurry in live mode).
    candidates = sorted(candidates, key=lambda p: p[4], reverse=True)

    best_text = None
    best_conf = 0.0
    best_box = None

    # Try up to top-K candidates to keep runtime bounded
    TOP_K = min(4, len(candidates))
    for plate in candidates[:TOP_K]:
        px1, py1, px2, py2, _ = plate
        pad_x = max(4, int((px2 - px1) * 0.10))
        pad_y = max(4, int((py2 - py1) * 0.10))
        cx1 = max(0,      px1 - pad_x)
        cy1 = max(0,      py1 - pad_y)
        cx2 = min(orig_w, px2 + pad_x)
        cy2 = min(orig_h, py2 + pad_y)

        crop = original_img[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            continue

        text, conf = read_plate_text(reader, crop, preferred_states)
        if text and conf > best_conf:
            best_text = text
            best_conf = conf
            best_box = (px1, py1, px2, py2)

    if best_text:
        return best_text, best_conf, best_box
    return None, 0.0, None