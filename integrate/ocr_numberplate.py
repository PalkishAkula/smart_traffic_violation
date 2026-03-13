"""
ocr_numberplate.py – OCR engine + Indian licence-plate correction.

IMPROVEMENTS IN THIS VERSION (Webcam / Low-Quality Fix)
---------------------------------------------------------
8.  SUPER-RESOLUTION UPSCALING
    Old: 3× bicubic upscale.
    New: Adaptive upscale: 6× for very small crops (< 80 px wide), 5× for
         medium (< 160 px), 4× for normal crops.  INTER_LANCZOS4 is used
         throughout (sharpest sub-pixel interpolation in OpenCV).

9.  UNSHARP MASKING (new variant)
    Applies a Gaussian blur and subtracts it from the original to
    enhance high-frequency details (character edges).  This recovers
    character boundaries that are blurred by a webcam lens.

10. MORPHOLOGICAL CLEANUP (new variant)
    A small dilation followed by erosion (closing) connects broken
    strokes in thin-font plates. This is especially important when the
    camera is far from the plate or the focus is off.

11. DEBLUR KERNEL (new variant)
    A mild sharpening kernel tuned for lens blur (PSF approximation).
    Complements the unsharp mask for motion-blurred frames.

12. CONF THRESHOLD LOWERED FOR WEBCAM
    EasyOCR confidence filter for merging tokens lowered from 0.20 → 0.15
    so faint characters in a low-quality webcam image are not discarded.

13. MIN LENGTH GUARD RELAXED FOR WEBCAM
    Plates shorter than 6 characters (after correction) are now still
    returned if they look like a valid partial plate (≥ 4 chars).

Previous fixes (unchanged)
---------------------------
1.  G ↔ D and G ↔ K added to SIMILAR map
2.  State-rank disambiguation
3.  Digit-level district-number correction
4.  IND-prefix stripping with multi-position dropped-char recovery
5.  CLAHE preprocessing (7th image variant)
6.  preferred_states exposed via get_plate_for_bike()
7.  get_plate_for_bike() accepts optional `search_box` parameter.

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
# Core correction helpers  (unchanged from previous version)
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
    for prefix in sorted(IND_PREFIXES, key=len, reverse=True):
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix):]
    return text

MAX_SLIDING_LEN = 15

def correct_indian_plate(raw_text, preferred_states=None):
    ps   = preferred_states
    text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    text = _strip_ind_prefix(text)
    # Try all series lengths
    for slen in [1, 2, 3]:
        r = _try_fix_all(text, slen, ps)
        if r: return r
    r = _try_fix_with_digit_subs(text, 2, ps)
    if r: return r
    for slen in [1, 3]:
        r = _try_fix_with_digit_subs(text, slen, ps)
        if r: return r
    if 8 <= len(text) <= MAX_SLIDING_LEN:
        r = _recover_dropped_char(text, ps)
        if r: return r
    return text

def is_valid_indian_plate(text):
    return bool(PLATE_PATTERN.match(text)) and text[:2] in VALID_STATE_CODES


# ══════════════════════════════════════════════════════════════════════════════
# OCR preprocessing  – IMPROVED for webcam / low-quality images
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
    """
    Unsharp masking: enhances character edges.
    amount > 1.0 → more aggressive sharpening.
    Works well for slight motion blur or soft-focus webcam images.
    """
    blurred = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    sharpened = cv2.addWeighted(gray, 1.0 + amount, blurred, -amount, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _morphological_clean(gray):
    """
    Closing (dilate → erode) to connect broken character strokes,
    then opening (erode → dilate) to remove small noise spots.
    Helps with thin-print plates photographed from a distance.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel, iterations=1)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN,  kernel, iterations=1)
    return opened


def _deblur_sharpen(gray):
    """
    Stronger deblur kernel tuned for mild lens / motion blur.
    Goes beyond the simple Laplacian sharpening used previously.
    """
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


def _preprocess_plate(crop):
    """
    Preprocessed image variants for multi-pass OCR.

    Adaptive upscaling strategy (NEW):
    • crop width < 80 px  → 6× upscale (very small / far-away plate)
    • crop width < 160 px → 5× upscale (medium distance / webcam)
    • crop width < 240 px → 4× upscale (normal)
    • crop width ≥ 240 px → 3× upscale (close / high-res)

    Variants generated (up to 13 total):
    1.  Plain gray         (base for all other ops)
    2.  Bilateral denoised
    3.  Otsu threshold
    4.  Otsu inverted
    5.  Adaptive threshold
    6.  Laplacian sharpen
    7.  CLAHE equalised
    8.  Unsharp mask  ← NEW: best for soft webcam images
    9.  Morphological clean ← NEW: best for thin/broken strokes
    10. Deblur sharpen ← NEW: best for motion blur
    If crop is small (< 160 px wide), add 4× extra variants:
    11. Plain 4× gray
    12. 4× bilateral
    13. 4× Otsu
    """
    h_crop, w_crop = crop.shape[:2]

    # ── Adaptive upscale factor ────────────────────────────────────────────────
    if w_crop < 80:
        up_factor = 6
        interp    = cv2.INTER_LANCZOS4
    elif w_crop < 160:
        up_factor = 5
        interp    = cv2.INTER_LANCZOS4
    elif w_crop < 240:
        up_factor = 4
        interp    = cv2.INTER_LANCZOS4
    else:
        up_factor = 3
        interp    = cv2.INTER_CUBIC

    up       = cv2.resize(crop, None, fx=up_factor, fy=up_factor,
                          interpolation=interp)
    gray     = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    denoised = cv2.bilateralFilter(gray, 11, 17, 17)

    # Threshold variants
    _, otsu  = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_inv = cv2.bitwise_not(otsu)
    adaptive = cv2.adaptiveThreshold(denoised, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)

    # Sharpening variants
    lap_kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharpened  = cv2.filter2D(denoised, -1, lap_kernel)

    # CLAHE
    clahe_eq = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4,4)).apply(denoised)

    # NEW: Unsharp mask
    unsharp = _unsharp_mask(denoised, amount=1.5)

    # NEW: Morphological clean (applied on otsu binary)
    morph_clean = _morphological_clean(otsu)

    # NEW: Deblur sharpen
    deblur = _deblur_sharpen(denoised)

    variants = [
        gray, denoised, otsu, otsu_inv, adaptive,
        sharpened, clahe_eq, unsharp, morph_clean, deblur
    ]

    # ── Extra 4× variants for small/medium crops ──────────────────────────────
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

    Changes from previous version:
    • confidence filter lowered from 0.20 → 0.15  (webcam fix #12)
    • minimum cleaned length lowered from 6 → 4   (webcam fix #13)
    • more preprocessing variants generated by _preprocess_plate()

    Returns
    -------
    corrected_text : str | None
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
                # Lowered threshold 0.20 → 0.15 for webcam (fix #12)
                if conf > 0.15:
                    merged     += text
                    total_conf += conf
                    valid_n    += 1
        if valid_n == 0: continue
        avg_conf = total_conf / valid_n
        score    = avg_conf + _plate_length_bonus(merged)
        # Relaxed min-length 6 → 4 for webcam partial reads (fix #13)
        if score > best_score and len(re.sub(r'[^A-Z0-9]', '', merged.upper())) >= 4:
            best_score = avg_conf
            best_text  = merged

    if not best_text:
        print("  [OCR] RAW=''  →  CORRECTED=None (conf=0.00)")
        return None, 0.0

    corrected = correct_indian_plate(best_text, preferred_states)
    corrected_clean = re.sub(r'[^A-Z0-9]', '', corrected.upper())
    if len(corrected_clean) < 4:
        print(f"  [OCR] RAW={best_text!r}  →  CORRECTED=None "
              f"(too short: {corrected!r}, conf={best_score:.2f})")
        return None, 0.0

    print(f"  [OCR] RAW={best_text!r}  →  CORRECTED={corrected!r}  "
          f"(conf={best_score:.2f})")
    return corrected, best_score


def _is_plate_in_search_box(plate_box, search_box):
    px_c, py_c = get_center(plate_box[:4])
    sx1, sy1, sx2, sy2 = search_box[:4]
    return sx1 <= px_c <= sx2 and sy1 <= py_c <= sy2


def get_plate_for_bike(plates, bike_box, original_img, reader,
                       preferred_states=None, search_box=None):
    """
    Locate the license plate on a motorcycle, crop it, and OCR it.

    IMPROVEMENT: tries up to TOP_K=5 plate candidates (was 4) so that
    when the highest-confidence detection is blurry, a lower-confidence
    but sharper crop can still succeed.

    Parameters
    ----------
    plates         : list of (x1,y1,x2,y2,conf)
    bike_box       : (x1,y1,x2,y2[,conf])
    original_img   : full-resolution frame (numpy array)
    reader         : easyocr.Reader instance
    preferred_states : list | None
    search_box     : (x1,y1,x2,y2) | None
        Extended spatial region (union of bike + persons + no-helmets,
        extended 40 % downward) — catches rear-mounted plates that are
        below the tight motorcycle box.

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

    candidates = sorted(candidates, key=lambda p: p[4], reverse=True)

    best_text = None
    best_conf = 0.0
    best_box  = None

    # Increased TOP_K from 4 → 5 so we try more candidates before giving up
    TOP_K = min(5, len(candidates))
    for plate in candidates[:TOP_K]:
        px1, py1, px2, py2, _ = plate

        # Slightly larger padding (15 % instead of 10 %) to include border
        # characters that the detector may have clipped
        pad_x = max(6, int((px2 - px1) * 0.15))
        pad_y = max(4, int((py2 - py1) * 0.15))
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
            best_box  = (px1, py1, px2, py2)

    if best_text:
        return best_text, best_conf, best_box
    return None, 0.0, None