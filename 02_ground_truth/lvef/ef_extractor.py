import re
import os
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
# ΠΑΡΑΜΕΤΡΟΙ ΕΚΤΕΛΕΣΗΣ (Άλλαξέ τα πριν πατήσεις F5)
# =============================================================================

SEVEN_ZIP = r"C:/Program Files/7-Zip/7z.exe"
DATASET_DIR = r"data/reports"
OUTPUT_CSV = r"outputs/ground_truth/ef_ground_truth.csv"
EXCLUSION_LIST = r"data/lists/exclusion_ids.txt"
OUTPUT_EXCEL_STATS = r"outputs/ground_truth/extraction_statistics_ef.xlsx"
MAX_FILES = None
REPORT_FILENAME = "temp_report.htm"


# =============================================================================
# EXCLUSION LIST & DATASET TRAVERSAL
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

        all_chm = sorted([f for f in os.listdir(report_path)
                          if f.upper().endswith(".CHM")])

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
            # Δοκιμή 2: Fallback σε windows-1253 (τυπική ελληνική κωδικοποίηση Windows)
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
# HTML PARSING — Μόνο τα sections που χρειάζεται το EF
# =============================================================================

SECTION_KEYS = {
    'LV':          ['αριστερή κοιλία', 'αριστερη κοιλια'],
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
# EXTRACTOR — EF (Κλάσμα Εξώθησης)
# =============================================================================

EF_PATTERN = re.compile(
    r'(?:'
    r'[eEεΕ]?[fFφΦ]|'
    r'κ\.?\s*ε\.?|'
    r'κλ[άα]σμ[αα]?\s+εξ[ώω]θησ[ηι][σς]?'
    r')'
    r'\s*(?:[:=]|εκτιμ[άα]ται\s+στ[οη]v?)?\s*'
    r'([<>\~]?)\s*'
    r'(\d{2})'
    r'(?:\s*(?:-|έως|εως)\s*(\d{2}))?'
    r'\s*[%]?',
    re.IGNORECASE
)

def _extract_numeric(pattern: re.Pattern, text: str) -> dict:
    """
    Επιστρέφει dict με:
      - exact_value:    float ή None (ακριβής τιμή, μόνο αν δεν είναι range/modifier)
      - modifier_value: str ή None  (π.χ. ">55", "<60", "~50")
      - range_value:    str ή None  (π.χ. "55-60")
      - status:         'exact' | 'modifier' | 'range' | 'not_found'
    """
    result = {'exact_value': None, 'modifier_value': None, 'range_value': None, 'status': 'not_found'}

    if not text.strip():
        return result

    match = pattern.search(text)
    if not match:
        return result

    modifier = match.group(1)
    val1     = int(match.group(2))
    val2     = match.group(3)

    if val2:
        result['range_value'] = f"{val1}-{val2}"
        result['status'] = 'range'
    elif modifier in ('<', '>', '~'):
        result['modifier_value'] = f"{modifier}{val1}"
        result['status'] = 'modifier'
    else:
        result['exact_value'] = float(val1)
        result['status'] = 'exact'

    return result

def extract_ef(sections: dict) -> dict:
    text = get_sec(sections, 'LV') + ' ' + get_sec(sections, 'CONCLUSIONS')
    return _extract_numeric(EF_PATTERN, text)

def extract_labels_from_html(html: str) -> dict:
    sections = parse_sections(html)
    ef = extract_ef(sections)
    return {
        'ef_exact':    ef['exact_value'],
        'ef_modifier': ef['modifier_value'],
        'ef_range':    ef['range_value'],
        'ef_status':   ef['status'],
    }


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def run_batch():
    exclusion_ids = load_exclusion_list(EXCLUSION_LIST)
    chm_entries = find_all_chm_files(DATASET_DIR, exclusion_ids)

    if not chm_entries:
        return

    if MAX_FILES:
        chm_entries = chm_entries[:MAX_FILES]

    total = len(chm_entries)
    logger.info(f"Ξεκινά το EF extraction για {total} εξετάσεις...")

    results, skipped, failed = [], [], []

    found_count = 0
    skip_counts = {'not_found': 0, 'range': 0, 'modifier': 0}

    for i, entry in enumerate(chm_entries):
        exam_id  = entry["exam_id"]
        chm_path = entry["chm_path"]

        if i % 50 == 0 and i > 0:
            logger.info(f"  Επεξεργασία... [{i}/{total}]")

        html = extract_report_html(chm_path)
        if not html:
            logger.warning(f"  ✗ {exam_id}: αποτυχία extraction")
            failed.append({'exam_id': exam_id, 'chm_path': chm_path})
            continue

        labels = extract_labels_from_html(html)

        if labels['ef_status'] == 'exact':
            found_count += 1
        else:
            skip_counts[labels['ef_status']] += 1

        results.append({
            'exam_id':     exam_id,
            'ef_exact':    labels['ef_exact'],
            'ef_modifier': labels['ef_modifier'],
            'ef_range':    labels['ef_range'],
        })

        if labels['ef_status'] != 'exact':
            skipped.append({
                'exam_id':   exam_id,
                'ef_status': labels['ef_status'],
            })

    # --- Αποθήκευση αποτελεσμάτων (Main CSV) ---
    fieldnames = ['exam_id', 'ef_exact', 'ef_modifier', 'ef_range']
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # --- Αποθήκευση παραλειφθέντων (Skipped CSV) ---
    skipped_csv = OUTPUT_CSV.replace('.csv', '_skipped.csv')
    with open(skipped_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['exam_id', 'ef_status'])
        writer.writeheader()
        writer.writerows(skipped)

    # --- Στατιστικά για Terminal ---
    total_processed = total - len(failed)
    ef_pct = (found_count / total_processed * 100) if total_processed > 0 else 0
    ef_skipped = total_processed - found_count

    logger.info(f"\n{'='*60}")
    logger.info(f"ΣΥΝΟΛΙΚΗ ΑΝΑΦΟΡΑ — EF Extraction")
    logger.info(f"{'='*60}")
    logger.info(f"  Εξετάσεις προς επεξεργασία : {total}")
    logger.info(f"  Extraction αποτυχίες       : {len(failed)}")
    logger.info(f"  Επιτυχώς επεξεργάστηκαν    : {total_processed}")
    logger.info(f"\n--- Ανάλυση EF (Κλάσμα Εξώθησης) ---")
    logger.info(f"  ✓ Κρατήθηκαν (ακριβής) : {found_count}  ({ef_pct:.1f}%)")
    logger.info(f"  ✗ Παραλείφθηκαν        : {ef_skipped}  ({100-ef_pct:.1f}%)")
    logger.info(f"      → Δεν βρέθηκε      : {skip_counts['not_found']}")
    logger.info(f"      → Εύρος (π.χ. 55-60): {skip_counts['range']}")
    logger.info(f"      → Σύμβολα (π.χ. >55): {skip_counts['modifier']}")

    logger.info(f"\n{'='*60}")
    logger.info(f"Output CSV     : {OUTPUT_CSV}")
    logger.info(f"Skipped CSV    : {skipped_csv}")

    if failed:
        failed_log = OUTPUT_CSV.replace('.csv', '_failed.csv')
        with open(failed_log, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['exam_id', 'chm_path'])
            writer.writeheader()
            writer.writerows(failed)
        logger.info(f"Failed CSV     : {failed_log}")

    # --- Δημιουργία Excel Στατιστικών ---
    df_general = pd.DataFrame([{
        "Συνολικές Εξετάσεις (Μετά την Exclusion List)": total,
        "Αποτυχίες Ανάγνωσης (Failed)": len(failed),
        "Επιτυχώς Επεξεργάστηκαν": total_processed
    }])

    df_ef = pd.DataFrame([{
        "Μεταβλητή": "EF (Κλάσμα Εξώθησης)",
        "Βρέθηκε Ακριβής Τιμή": found_count,
        "Ποσοστό Εύρεσης (%)": round(ef_pct, 1),
        "Παραλείφθηκε (Skipped)": ef_skipped,
        "Ποσοστό Παράλειψης (%)": round(100 - ef_pct, 1),
        "Αιτία: Δεν βρέθηκε πουθενά": skip_counts['not_found'],
        "Αιτία: Ήταν εύρος (π.χ. 55-60)": skip_counts['range'],
        "Αιτία: Είχε σύμβολα (π.χ. >55)": skip_counts['modifier'],
    }])

    try:
        with pd.ExcelWriter(OUTPUT_EXCEL_STATS, engine='openpyxl') as writer:
            df_general.to_excel(writer, sheet_name='Γενικά_Στοιχεία', index=False)
            df_ef.to_excel(writer, sheet_name='Ανάλυση_EF', index=False)
        logger.info(f"Excel Στατιστικών: {OUTPUT_EXCEL_STATS}")
    except Exception as e:
        logger.error(f"Αποτυχία δημιουργίας Excel Στατιστικών: {e}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    run_batch()