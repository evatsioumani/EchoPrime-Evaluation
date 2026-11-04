import os
import re
import csv
import shutil
import tempfile
import logging
import subprocess
from pathlib import Path
from typing import Optional
import pandas as pd

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[ΣΦΑΛΜΑ] Απαιτείται: pip install beautifulsoup4 lxml")

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# ΠΑΡΑΜΕΤΡΟΙ ΕΚΤΕΛΕΣΗΣ
# =============================================================================

SEVEN_ZIP        = r"C:/Program Files/7-Zip/7z.exe"
DATASET_DIR      = r"data/reports"
OUTPUT_CSV       = r"outputs/ground_truth/rvsp_ground_truth.csv"
EXCLUSION_LIST   = r"data/lists/exclusion_ids.txt"
OUTPUT_EXCEL_STATS = r"outputs/ground_truth/extraction_statistics_rvsp.xlsx"
MAX_FILES        = None
REPORT_FILENAME  = "temp_report.htm"

THRESHOLD = 35   # mmHg — ≥ αυτής → label 1, < αυτής → label 0


# =============================================================================
# EXCLUSION LIST & DATASET TRAVERSAL  (ίδια με ef_extractor)
# =============================================================================

def load_exclusion_list(exclusion_list_path) -> set:
    if not exclusion_list_path:
        return set()
    path = Path(exclusion_list_path)
    if not path.exists():
        logger.warning(f"  ⚠ Η exclusion list δεν βρέθηκε στο: {path} — Συνεχίζω χωρίς εξαιρέσεις.")
        return set()
    ids = set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.add(line)
    logger.info(f"Φορτώθηκε Exclusion List: {len(ids)} εξετάσεις θα παραλειφθούν.")
    return ids


def find_all_chm_files(root_folder: str, exclusion_ids: set) -> list:
    chm_files = []
    skipped_excluded = 0
    if not os.path.exists(root_folder):
        logger.error(f"Το directory {root_folder} δεν υπάρχει. Έλεγξε το DATASET_DIR.")
        return chm_files
    for exam_id in sorted(os.listdir(root_folder)):
        if exam_id in exclusion_ids:
            skipped_excluded += 1
            continue
        exam_path   = os.path.join(root_folder, exam_id)
        report_path = os.path.join(exam_path, "report")
        if not os.path.isdir(report_path):
            continue
        all_chm = sorted([f for f in os.listdir(report_path) if f.upper().endswith(".CHM")])
        if not all_chm:
            continue
        if len(all_chm) > 1:
            logger.warning(f"  ⚠ {exam_id}: {len(all_chm)} CHM αρχεία → χρησιμοποιείται '{all_chm[0]}'")
        chm_files.append({
            "exam_id":  exam_id,
            "chm_path": os.path.join(report_path, all_chm[0])
        })
    if skipped_excluded > 0:
        logger.info(f"Συνολικά {skipped_excluded} εξετάσεις παραλείφθηκαν λόγω της Exclusion List.")
    return chm_files


def extract_report_html(chm_path: str) -> Optional[str]:
    output_dir = tempfile.mkdtemp()
    try:
        subprocess.run(
            [SEVEN_ZIP, "e", chm_path, "-o" + output_dir, REPORT_FILENAME, "-y"],
            capture_output=True, check=True
        )
        html_path = os.path.join(output_dir, REPORT_FILENAME)
        if not os.path.exists(html_path):
            return None
            
        # --- Ενσωμάτωση του fallback μηχανισμού ανάγνωσης ---
        try:
            # Δοκιμή 1: Αυστηρή ανάγνωση ως UTF-8
            with open(html_path, encoding='utf-8', errors='strict') as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            pass # Αν αποτύχει, προχωράμε στην επόμενη δοκιμή
            
        try:
            # Δοκιμή 2: Fallback σε windows-1253
            with open(html_path, encoding='windows-1253', errors='replace') as f:
                return f.read()
        except Exception:
            return None
        # ---------------------------------------------------

    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        logger.error(f"7-Zip δεν βρέθηκε: {SEVEN_ZIP}")
        return None
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


# =============================================================================
# HTML PARSING — Sections που χρειάζεται το RVSP
# =============================================================================

SECTION_KEYS = {
    'TV':          ['τριγλώχινα', 'τριγλωχινα', 'tricuspid'],
    'RV':          ['δεξιά κοιλία', 'δεξια κοιλια', 'right ventricle'],
    'PA':          ['πνευμονική', 'πνευμονικη', 'pulmonary'],
    'CONCLUSIONS': ['συμπεράσματα', 'συμπερασματα', 'conclusions'],
}

def parse_sections(html: str) -> dict:
    if not BS4_AVAILABLE:
        return _parse_sections_regex(html)
    soup = BeautifulSoup(html, 'html.parser')
    sections = {}
    for p_tag in soup.find_all('p'):
        header_span = p_tag.find('span', style=lambda s: s and 'underline' in s)
        if not header_span:
            continue
        raw_header = header_span.get_text(strip=True)
        raw_header = re.sub(r'[.:]+\s*$', '', raw_header).strip().lower()
        section_key = None
        for key, aliases in SECTION_KEYS.items():
            if any(alias in raw_header or raw_header in alias for alias in aliases):
                section_key = key
                break
        if not section_key:
            continue
        header_span.extract()
        section_text = p_tag.get_text(separator=' ', strip=True)
        if section_key in sections:
            sections[section_key] += ' ' + section_text
        else:
            sections[section_key] = section_text
    return sections

def _parse_sections_regex(html: str) -> dict:
    sections = {}
    pattern = r'<span[^>]*text-decoration:\s*underline[^>]*>(.*?)</span>(.*?)</p>'
    for m in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        raw_header = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        raw_header = re.sub(r'[.:]+\s*$', '', raw_header).lower()
        section_text = re.sub(r'<[^>]+>', ' ', m.group(2)).strip()
        for key, aliases in SECTION_KEYS.items():
            if any(alias in raw_header or raw_header in alias for alias in aliases):
                if key in sections:
                    sections[key] += ' ' + section_text
                else:
                    sections[key] = section_text
                break
    return sections

def get_sec(sections: dict, key: str) -> str:
    return sections.get(key, '')


# =============================================================================
# RVSP PATTERNS
# =============================================================================

# ---------------------------------------------------------------------------
# A) Label pattern — αναγνωρίζει ΠΟΥ αναφέρεται η RVSP/sPAP μέσα στο κείμενο
# ---------------------------------------------------------------------------
RVSP_LABEL_RE = re.compile(
    r'(?:'
    # --- Ακρωνύμια ---
    r'rvsp|r\.?v\.?s\.?p\.?|pasp|p\.?a\.?s\.?p\.?|'
    r'δκπ|'
    r'spap|s\.?p\.?a\.?p\.?|'
    r'paps|p\.?a\.?p\.?s\.?|'
    # --- Ελληνικά: [εκτιμώμενη] [συστολική] πίεση [της] [δεξιάς] κοιλίας [(…)] ---
    r'(?:εκτιμ[ώω]μεν[ηη]\s+)?(?:συστολικ[ήη]\s+)?π[ιί]εσ[ηη]\s+(?:της\s+)?(?:δεξι[αά][σς]?\s+)?κοιλ[ιί][αα][σς]?(?:\s*\([^\)]*\))?|'
    # --- English: [systolic] right ventricular [systolic] pressure [(…)] ---
    r'(?:systolic\s+)?right\s+ventricular\s+(?:systolic\s+)?pressure(?:\s*\([^\)]*\))?|'
    # --- Ελληνικά: [εκτιμώμενη] [μέση/συστολική] πνευμονική πίεση [(…)] ---
    r'(?:εκτιμ[ώω]μεν[ηη]\s+)?(?:μ[εέ]σ[ηη]\s+|συστολικ[ήη]\s+)?πνευμονικ[ήη]\s+π[ιί]εσ[ηη](?:\s*\([^\)]*\))?|'
    # --- Ελληνικά: [συστολική] πίεση [της] πνευμονικής [αρτηρίας] [(…)] ---
    r'(?:συστολικ[ήη]\s+)?π[ιί]εσ[ηη]\s+(?:της\s+)?πνευμονικ[ήη][σς]?(?:\s+αρτηρ[ιί][αα][σς]?)?(?:\s*\([^\)]*\))?'
    r')',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# B) Numeric pattern — ψάχνει αριθμό μέσα στο window μετά το label
#   Αντέχει και (<35) και <(35) και ≤ 35 mmHg κλπ.
# ---------------------------------------------------------------------------
NUMERIC_RE = re.compile(
    r'[(\[]?\s*'
    r'([<>~≈≤≥]?)\s*'
    r'[(\[]?\s*'
    r'(\d{2,3})'
    r'\s*[)\]]?'
    r'(?:\s*[-–]\s*(\d{2,3})\s*[)\]]?)?'
    r'\s*(?:mm\s*[Hh]g)?',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# C) Qualitative patterns — ποιοτικές εκτιμήσεις
# ---------------------------------------------------------------------------

# Label 0 — Window-based (κοντά σε RVSP label)
NORMAL_WINDOW_RE = re.compile(
    r'(?:'
    r'εντ[οό]ς\s+φυσιολογικ[ωώ]ν\s+ορ[ιί]ων|'
    r'φυσιολογικ[ήη]\s+π[ιί]εσ[ηη]|'
    r'φυσιολογικ[έε]ς\s+πι[εέ]σ[εη]ι?ς|'
    r'normal\s+(?:pulmonary\s+)?pressure|'
    r'within\s+normal\s+limits'
    r')',
    re.IGNORECASE
)

# Label 1 — Window-based (κοντά σε RVSP label)
ELEVATED_WINDOW_RE = re.compile(
    r'(?:'
    r'αυξημ[εέ]ν[ηη]|'
    r'(?:ελαφρ[ωώ]ς|ελαφρ[αά]|μετρ[ιί]ως?|σοβαρ[ήη]|σημαντικ[αά])\s+αυξημ[εέ]ν[ηη]|'
    r'elevated|'
    r'increased'
    r')',
    re.IGNORECASE
)

# Label 0 — Standalone: αρνητική αναφορά σε πνευμονική υπέρταση
NEGATED_PH_RE = re.compile(
    r'(?:δεν|χωρ[ιί]ς|[αά]νευ|δ[ιί]χως)\s+(?:\w+\s+){0,5}πνευμονικ[ήη][σς]?\s+υπ[εέ]ρτασ[ηη]',
    re.IGNORECASE
)

# Label 1 — Standalone: θετική αναφορά σε πνευμονική υπέρταση
PH_RE = re.compile(
    r'πνευμονικ[ήη][σς]?\s+υπ[εέ]ρτασ[ηη]',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# D) Not-estimable pattern — "δεν εκτιμήθηκε", "αδύνατη η μέτρηση" κλπ.
# ---------------------------------------------------------------------------
NOT_ESTIMABLE_RE = re.compile(
    r'(?:'
    r'δεν\s+(?:\w+\s+){0,3}(?:εκτιμ[ήη]θηκε|υπολογ[ιί]στηκε|μετρ[ήη]θηκε|δ[ύυ]ναται|ε[ιί]ναι\s+(?:δυνατ|εφικτ))|'
    r'αδ[ύυ]νατ[ηη]\s+(?:η\s+)?(?:εκτ[ιί]μησ[ηη]|μ[εέ]τρησ[ηη])|'
    r'(?:not|cannot|could\s+not)\s+(?:be\s+)?(?:estimat|measur|assess)'
    r')',
    re.IGNORECASE
)


# =============================================================================
# EXTRACTION LOGIC — Multi-pass
# =============================================================================

def _get_window(text: str, start: int, max_len: int = 150) -> str:
    """Κόβει παράθυρο κειμένου μετά το label, μέχρι τέλος πρότασης ή max_len."""
    window = text[start:start + max_len]
    # Κόψε στο τέλος πρότασης (τελεία + κενό + κεφαλαίο)
    m = re.search(r'\.\s+[Α-ΩA-ZΆΈΉΊΌΎΏϊϋ]', window)
    if m:
        window = window[:m.start() + 1]
    return window


def _find_all_numeric(text: str) -> list:
    """
    Βρίσκει ΟΛΕΣ τις αριθμητικές τιμές RVSP κοντά σε RVSP labels.
    Επιστρέφει λίστα με dicts: type (exact|modifier|range|not_estimable),
    value(s), modifier, raw text.
    """
    findings = []

    for match in RVSP_LABEL_RE.finditer(text):
        window = _get_window(text, match.end())

        # Πρώτα τσέκαρε not-estimable
        if NOT_ESTIMABLE_RE.search(window):
            findings.append({
                'type': 'not_estimable',
                'raw':  window.strip()[:80]
            })
            continue

        num = NUMERIC_RE.search(window)
        if not num:
            continue

        modifier = num.group(1) or ''
        val1 = int(num.group(2))
        val2_str = num.group(3)

        if val2_str:
            findings.append({
                'type': 'range',
                'val1': val1,
                'val2': int(val2_str),
                'raw':  num.group(0).strip()
            })
        elif modifier:
            findings.append({
                'type':     'modifier',
                'modifier': modifier,
                'value':    val1,
                'raw':      num.group(0).strip()
            })
        else:
            findings.append({
                'type':  'exact',
                'value': val1,
                'raw':   num.group(0).strip()
            })

    return findings


def _resolve_modifier(modifier: str, value: int) -> Optional[int]:
    """
    Αποφασίζει label από modifier + τιμή αναφοράς.
    Επιστρέφει 0, 1, ή None (ambiguous).

    Λογική:
      < X  όπου X ≤ 35  → 0  (σίγουρα κάτω)
      ≤ X  όπου X ≤ 35  → 0  (κλινικά: φυσιολογικό)
      > X  όπου X ≥ 34  → 1  (>34 σημαίνει ≥35)
      ≥ X  όπου X ≥ 35  → 1  (σίγουρα πάνω)
      ~ X  →  1 αν X ≥ 40, 0 αν X ≤ 30, αλλιώς None
    """
    if modifier in ('<',):
        return 0 if value <= THRESHOLD else None
    elif modifier in ('≤',):
        return 0 if value <= THRESHOLD else None
    elif modifier in ('>',):
        return 1 if value >= THRESHOLD - 1 else None      # >34 → ≥35
    elif modifier in ('≥',):
        return 1 if value >= THRESHOLD else None
    elif modifier in ('~', '≈'):
        if value >= THRESHOLD + 5:
            return 1
        elif value <= THRESHOLD - 5:
            return 0
        return None
    return None


def _resolve_range(val1: int, val2: int) -> Optional[int]:
    """
    Αποφασίζει label από εύρος τιμών.
    Επιστρέφει 0, 1, ή None (ambiguous — το εύρος σπάει στο threshold).
    """
    low, high = min(val1, val2), max(val1, val2)
    if high < THRESHOLD:
        return 0
    if low >= THRESHOLD:
        return 1
    return None


def _find_qualitative(text: str) -> Optional[dict]:
    """
    Ψάχνει ποιοτικές εκτιμήσεις σε δύο επίπεδα:
      a) Μέσα σε window μετά από RVSP label  (εντός φυσιολογικών ορίων, αυξημένη…)
      b) Standalone στο κείμενο               (πνευμονική υπέρταση, negated ή positive)

    Normal (label 0) ελέγχεται ΠΡΙΝ από elevated (label 1) ώστε η
    άρνηση «δεν προκύπτει πνευμονική υπέρταση» να κερδίσει.
    """
    # --- A) Window-based: normal ---
    for match in RVSP_LABEL_RE.finditer(text):
        window = _get_window(text, match.end())
        m = NORMAL_WINDOW_RE.search(window)
        if m:
            return {'label': 0, 'phrase': m.group(0).strip()}

    # --- B) Standalone: negated πνευμονική υπέρταση ---
    m = NEGATED_PH_RE.search(text)
    if m:
        return {'label': 0, 'phrase': m.group(0).strip()}

    # --- C) Window-based: elevated ---
    for match in RVSP_LABEL_RE.finditer(text):
        window = _get_window(text, match.end())
        m = ELEVATED_WINDOW_RE.search(window)
        if m:
            return {'label': 1, 'phrase': m.group(0).strip()}

    # --- D) Standalone: positive πνευμονική υπέρταση ---
    m = PH_RE.search(text)
    if m:
        # Βεβαιώσου ότι ΔΕΝ είναι negated (σε περίπτωση που η negation
        # δεν πιάστηκε στο βήμα B — π.χ. ασυνήθιστη σύνταξη)
        full_match_start = m.start()
        prefix = text[max(0, full_match_start - 30):full_match_start]
        if not re.search(r'(?:δεν|χωρ[ιί]ς|[αά]νευ|δ[ιί]χως)\s*$', prefix, re.IGNORECASE):
            return {'label': 1, 'phrase': m.group(0).strip()}

    return None


def extract_rvsp_binary(sections: dict) -> dict:
    """
    Κεντρική συνάρτηση: εφαρμόζει τα 4 passes με σειρά προτεραιότητας.
    Επιστρέφει dict:
      label          : 0 | 1 | None
      method         : exact | modifier | qualitative | range |
                       not_found | not_estimable | ambiguous
      raw_value      : str — τι ακριβώς ταίριαξε (για audit)
      numeric_value  : float | None — αριθμητική τιμή αν υπάρχει
    """
    text = ' '.join(
        get_sec(sections, k) for k in ('TV', 'RV', 'PA', 'CONCLUSIONS')
    )

    result = {
        'label':         None,
        'method':        'not_found',
        'raw_value':     None,
        'numeric_value': None,
    }

    if not text.strip():
        return result

    # Μάζεψε ΟΛΑ τα αριθμητικά findings κοντά σε labels
    numerics = _find_all_numeric(text)

    has_real_values = any(n['type'] in ('exact', 'modifier', 'range') for n in numerics)

    # --- Ειδική περίπτωση: not estimable (μόνο αν δεν υπάρχει κανένα αριθμητικό) ---
    not_est = [n for n in numerics if n['type'] == 'not_estimable']
    if not_est and not has_real_values:
        result['method']    = 'not_estimable'
        result['raw_value'] = not_est[0]['raw']
        return result

    # --- Pass 1: Exact numeric ---
    exacts = [n for n in numerics if n['type'] == 'exact']
    if exacts:
        val = exacts[0]['value']
        result['label']         = 1 if val >= THRESHOLD else 0
        result['method']        = 'exact'
        result['numeric_value'] = float(val)
        result['raw_value']     = exacts[0]['raw']
        return result

    # --- Pass 2: Modifier (deterministic μόνο) ---
    modifiers = [n for n in numerics if n['type'] == 'modifier']
    for mod in modifiers:
        resolved = _resolve_modifier(mod['modifier'], mod['value'])
        if resolved is not None:
            result['label']         = resolved
            result['method']        = 'modifier'
            result['numeric_value'] = float(mod['value'])
            result['raw_value']     = mod['raw']
            return result

    # --- Pass 3: Qualitative phrases ---
    qual = _find_qualitative(text)
    if qual:
        result['label']     = qual['label']
        result['method']    = 'qualitative'
        result['raw_value'] = qual['phrase']
        return result

    # --- Pass 4: Range (deterministic μόνο) ---
    ranges = [n for n in numerics if n['type'] == 'range']
    for rng in ranges:
        resolved = _resolve_range(rng['val1'], rng['val2'])
        if resolved is not None:
            result['label']     = resolved
            result['method']    = 'range'
            result['raw_value'] = rng['raw']
            return result

    # --- Τίποτα δεν έδωσε deterministic αποτέλεσμα ---
    if numerics:
        result['method']    = 'ambiguous'
        result['raw_value'] = numerics[0]['raw']

    return result


def extract_labels_from_html(html: str) -> dict:
    sections = parse_sections(html)
    rvsp = extract_rvsp_binary(sections)
    return {
        'rvsp_label':     rvsp['label'],
        'rvsp_method':    rvsp['method'],
        'rvsp_raw':       rvsp['raw_value'],
        'rvsp_numeric':   rvsp['numeric_value'],
    }


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def run_batch():
    exclusion_ids = load_exclusion_list(EXCLUSION_LIST)
    chm_entries   = find_all_chm_files(DATASET_DIR, exclusion_ids)

    if not chm_entries:
        return
    if MAX_FILES:
        chm_entries = chm_entries[:MAX_FILES]

    total = len(chm_entries)
    logger.info(f"Ξεκινά το RVSP binary extraction για {total} εξετάσεις (threshold = {THRESHOLD} mmHg)...")

    results, unresolved, failed = [], [], []

    # Μετρητές ανά method
    method_counts = {
        'exact': 0, 'modifier': 0, 'qualitative': 0, 'range': 0,
        'not_found': 0, 'not_estimable': 0, 'ambiguous': 0,
    }
    label_counts = {0: 0, 1: 0}

    for i, entry in enumerate(chm_entries):
        exam_id  = entry["exam_id"]
        chm_path = entry["chm_path"]

        if i % 50 == 0 and i > 0:
            logger.info(f"  Επεξεργασία... [{i}/{total}]")

        html = extract_report_html(chm_path)
        if not html:
            logger.warning(f"  ✗ {exam_id}: αποτυχία extraction HTML")
            failed.append({'exam_id': exam_id, 'chm_path': chm_path})
            continue

        labels = extract_labels_from_html(html)
        method = labels['rvsp_method']
        method_counts[method] += 1

        if labels['rvsp_label'] is not None:
            label_counts[labels['rvsp_label']] += 1

        results.append({
            'exam_id':      exam_id,
            'rvsp_label':   labels['rvsp_label'],
            'rvsp_method':  method,
            'rvsp_raw':     labels['rvsp_raw'],
            'rvsp_numeric': labels['rvsp_numeric'],
        })

        if labels['rvsp_label'] is None:
            unresolved.append({
                'exam_id':     exam_id,
                'rvsp_status': method,
                'rvsp_raw':    labels['rvsp_raw'] or '',
            })

    # --- Αποθήκευση αποτελεσμάτων ---
    fieldnames = ['exam_id', 'rvsp_label', 'rvsp_method', 'rvsp_raw', 'rvsp_numeric']
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    unresolved_csv = OUTPUT_CSV.replace('.csv', '_unresolved.csv')
    with open(unresolved_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['exam_id', 'rvsp_status', 'rvsp_raw'])
        writer.writeheader()
        writer.writerows(unresolved)

    # --- Στατιστικά Terminal ---
    total_processed = total - len(failed)
    resolved_count  = label_counts[0] + label_counts[1]
    resolved_pct    = (resolved_count / total_processed * 100) if total_processed > 0 else 0

    logger.info(f"\n{'='*65}")
    logger.info(f"ΣΥΝΟΛΙΚΗ ΑΝΑΦΟΡΑ — RVSP Binary Extraction (threshold {THRESHOLD} mmHg)")
    logger.info(f"{'='*65}")
    logger.info(f"  Εξετάσεις προς επεξεργασία   : {total}")
    logger.info(f"  Extraction αποτυχίες (HTML)   : {len(failed)}")
    logger.info(f"  Επιτυχώς επεξεργάστηκαν      : {total_processed}")

    logger.info(f"\n--- Resolved Labels ---")
    logger.info(f"  ✓ Συνολικά resolved          : {resolved_count}  ({resolved_pct:.1f}%)")
    logger.info(f"      → Label 0 (φυσιολογική)  : {label_counts[0]}")
    logger.info(f"      → Label 1 (αυξημένη)     : {label_counts[1]}")

    logger.info(f"\n--- Ανά method εξαγωγής ---")
    logger.info(f"      Pass 1 — Exact numeric   : {method_counts['exact']}")
    logger.info(f"      Pass 2 — Modifier        : {method_counts['modifier']}")
    logger.info(f"      Pass 3 — Qualitative     : {method_counts['qualitative']}")
    logger.info(f"      Pass 4 — Range           : {method_counts['range']}")

    unresolved_count = total_processed - resolved_count
    logger.info(f"\n--- Unresolved ---")
    logger.info(f"  ✗ Συνολικά unresolved        : {unresolved_count}  ({100-resolved_pct:.1f}%)")
    logger.info(f"      → not_found              : {method_counts['not_found']}")
    logger.info(f"      → not_estimable          : {method_counts['not_estimable']}")
    logger.info(f"      → ambiguous              : {method_counts['ambiguous']}")

    logger.info(f"\n{'='*65}")
    logger.info(f"Output CSV      : {OUTPUT_CSV}")
    logger.info(f"Unresolved CSV  : {unresolved_csv}")

    if failed:
        failed_log = OUTPUT_CSV.replace('.csv', '_failed.csv')
        with open(failed_log, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['exam_id', 'chm_path'])
            writer.writeheader()
            writer.writerows(failed)
        logger.info(f"Failed CSV      : {failed_log}")

    # --- Excel Στατιστικών ---
    df_general = pd.DataFrame([{
        "Συνολικές Εξετάσεις (Μετά Exclusion)": total,
        "Αποτυχίες Ανάγνωσης (Failed)": len(failed),
        "Επιτυχώς Επεξεργάστηκαν": total_processed,
    }])

    df_resolved = pd.DataFrame([{
        "Resolved (Label assigned)": resolved_count,
        "Ποσοστό Resolved (%)": round(resolved_pct, 1),
        "Label 0 — Φυσιολογική (< 35)": label_counts[0],
        "Label 1 — Αυξημένη (≥ 35)": label_counts[1],
    }])

    df_methods = pd.DataFrame([
        {"Method": "Pass 1 — Exact numeric",   "Πλήθος": method_counts['exact']},
        {"Method": "Pass 2 — Modifier",         "Πλήθος": method_counts['modifier']},
        {"Method": "Pass 3 — Qualitative",      "Πλήθος": method_counts['qualitative']},
        {"Method": "Pass 4 — Range",             "Πλήθος": method_counts['range']},
        {"Method": "--- Unresolved ---",         "Πλήθος": ""},
        {"Method": "not_found",                  "Πλήθος": method_counts['not_found']},
        {"Method": "not_estimable",              "Πλήθος": method_counts['not_estimable']},
        {"Method": "ambiguous",                  "Πλήθος": method_counts['ambiguous']},
    ])

    try:
        with pd.ExcelWriter(OUTPUT_EXCEL_STATS, engine='openpyxl') as writer:
            df_general.to_excel(writer, sheet_name='Γενικά_Στοιχεία', index=False)
            df_resolved.to_excel(writer, sheet_name='Labels', index=False)
            df_methods.to_excel(writer, sheet_name='Methods_Breakdown', index=False)
        logger.info(f"Excel Στατιστικών: {OUTPUT_EXCEL_STATS}")
    except Exception as e:
        logger.error(f"Αποτυχία δημιουργίας Excel: {e}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    run_batch()