import re
import os
import csv
import shutil
import tempfile
import argparse
import logging
import subprocess
import unicodedata
from pathlib import Path
from typing import Optional

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[ΣΦΑΛΜΑ] Απαιτείται: pip install beautifulsoup4 lxml")

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

SEVEN_ZIP = r"C:/Program Files/7-Zip/7z.exe"  
REPORT_FILENAME = "temp_report.htm"            # το σταθερό όνομα του HTML


# =============================================================================
# DATASET TRAVERSAL
# =============================================================================

def find_all_chm_files(root_folder: str) -> list:
    """
    Δομή: <root>/<exam_id>/report/<file>.CHM
    - Αγνοεί εξετάσεις χωρίς report/ subfolder
    - Αγνοεί εξετάσεις χωρίς CHM αρχείο
    - Αν υπάρχουν >1 CHM, παίρνει το πιο πρόσφατο (βάσει ημερομηνίας τροποποίησης)
    """
    chm_files = []
    root_path = Path(root_folder)

    # 1. Βρίσκουμε μόνο τους πραγματικούς φακέλους report του κάθε study
    # Ταξινομούμε τους φακέλους αλφαβητικά για να έχουμε συνέπεια στην επεξεργασία
    for exam_path in sorted([d for d in root_path.iterdir() if d.is_dir()]):
        exam_id = exam_path.name
        report_path = exam_path / "report"

        if not report_path.is_dir():
            continue

        # 2. Εντοπισμός όλων των CHM αρχείων (case-insensitive ελέγχοντας την κατάληξη)
        all_chm = [f for f in report_path.iterdir() 
                   if f.is_file() and f.suffix.upper() == ".CHM"]

        if not all_chm:
            continue

        # 3. Αν βρεθούν πάνω από ένα, τα ταξινομούμε με βάση το modification time (φθίνουσα σειρά)
        if len(all_chm) > 1:
            all_chm.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            logger.warning(
                f" {exam_id}: {len(all_chm)} CHM αρχεία → χρησιμοποιείται το πιο πρόσφατο '{all_chm[0].name}'"
            )

        chm_files.append({
            "exam_id": exam_id,
            # Επιστρέφουμε string path για να μην "σπάσει" η συμβατότητα με τις επόμενες συναρτήσεις
            "chm_path": str(all_chm[0])
        })

    return chm_files


# =============================================================================
# CHM → SECTIONS DICT
# =============================================================================
def extract_report_html(chm_path: str) -> Optional[str]:
    """
    Εξάγει ΜΟΝΟ το temp_report.htm από το CHM μέσω 7-zip.
    Returns: raw HTML string ή None
    """
    output_dir = tempfile.mkdtemp()  #δημιουργία προσωρινού φακέλου για on-the-fly επεξεργασία των chm αρχείων
    try:
        result = subprocess.run(
            [SEVEN_ZIP, "e", chm_path, "-o" + output_dir, REPORT_FILENAME, "-y"],
            capture_output=True, check=True
        )
        html_path = os.path.join(output_dir, REPORT_FILENAME)
        if not os.path.exists(html_path):
            return None

        #Δυναμικός έλεγχος Encoding 
        try:
            # Δοκιμάζουμε πρώτα utf-8
            with open(html_path, encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Αν εξάγει σφάλμα, σημαίνει ότι είναι παλιότερη κωδικοποίηση και επιλέγεται windows1253 (Ελληνικά Windows).
            with open(html_path, encoding='windows-1253', errors='replace') as f:
                return f.read()

    except subprocess.CalledProcessError:
        return None
    except FileNotFoundError:
        logger.error(f"7-Zip δεν βρέθηκε: {SEVEN_ZIP}")
        return None
    finally:
        shutil.rmtree(output_dir, ignore_errors=True) #διαγραφή προσωρινού φακέλου


# Mapping: canonical key → possible header texts (lowercase, stripped)
# Mapping: canonical key → possible header texts (lowercase, stripped)
SECTION_KEYS = {
    'LV':          ['αριστερή κοιλία', 'αριστερη κοιλια'],
    'RV':          ['δεξιά κοιλία', 'δεξια κοιλια', 'δεξιά κοιλίa', 'δεξια κοιλιa', 'δεξιά κοιλιά', 'δεξια κοιλιά'],
    'LA':          ['αριστερός κόλπος', 'αριστερος κολπος'],
    'RA':          ['δεξιός κόλπος', 'δεξιος κολπος'],
    'MV':          ['μιτροειδής βαλβίδα', 'μιτροειδης βαλβιδα', 'μιτροειδής', 'μιτροειδης'],
    'AV':          ['αορτική βαλβίδα', 'αορτικη βαλβιδα', 'αορτική', 'αορτικη'],
    'TV':          ['τριγλώχινα βαλβίδα', 'τριγλωχινα βαλβιδα', 'τριγλώχινα', 'τριγλωχινα'],
    'PV':          ['πνευμονική βαλβίδα', 'πνευμονικη βαλβιδα'],
    'AORTA':       ['ρίζα αορτής', 'ριζα αορτης', 'ανιούσα αορτή', 'ανιουσα αορτη',
                    'αορτή - ρίζα', 'αορτη - ριζα', 'αορτή', 'αορτη'],
    'IVC':         ['κάτω κοίλη φλέβα', 'κατω κοιλη φλεβα', 'κκφ'],
    'PERICARDIUM': ['περικάρδιο', 'περικαρδιο'],
    'FINDINGS':    ['ευρήματα', 'ευρηματα', 'findings'],
    'CONCLUSIONS': ['συμπεράσματα', 'συμπερασματα', 'conclusions', 'συμπέρασμα', 'συμπερασμα'],
    'COMMENTS':    ['σχόλια', 'σχολια', 'διάγνωση', 'διαγνωση', 'echo summary'],
}

def parse_sections(html: str) -> dict:
    """
    Διαβάζει το temp_report.htm και επιστρέφει dict:
      { 'LV': 'κείμενο...', 'RV': 'κείμενο...', ... }

    Υβριδική λογική (v3):
      - Περίπτωση Α: Underlined headers → αναγνώριση μέσω SECTION_KEYS (ίδια με v2)
      - Περίπτωση Β (orphan paragraphs):
          1. Startswith check ΜΟΝΟ για structural sections (Συμπεράσματα/Σχόλια)
             που δεν έχουν ποτέ underline header → section switch
          2. Αν δεν ταιριάζει → αυστηρή προσθήκη στο τρέχον section (ίδια με v2)

    Αποτρέπει:
      - Cross-section contamination (πρόβλημα v1: keyword detection σε ολόκληρο text)
      - Tail-section leakage (πρόβλημα v2: Συμπεράσματα χύνονται στο τελευταίο section)
    """
    sections = {}
    if not html.strip():
        return sections

    if not BS4_AVAILABLE:
        return _parse_sections_regex(html)

    soup = BeautifulSoup(html, 'html.parser')

    current_section_key = 'FINDINGS'  # Ξεκινάει με ένα γενικό FINDINGS ως μνήμη

    # Structural section keywords: ελέγχονται ΜΟΝΟ στην αρχή orphan paragraphs.
    # Αυτά δεν έχουν ποτέ underline header στα reports.
    # Tuple format: (startswith_pattern, section_key)
    STRUCTURAL_BREAKS = [
        (re.compile(r'^συμπ[εέ]ρ[αά]σμα', re.IGNORECASE),  'CONCLUSIONS'),
        (re.compile(r'^σχ[οόό]λια', re.IGNORECASE),          'COMMENTS'),
        (re.compile(r'^δι[αά]γνωση', re.IGNORECASE),         'COMMENTS'),
        (re.compile(r'^echo\s+summary', re.IGNORECASE),      'COMMENTS'),
    ]

    for p_elem in soup.find_all('p'):
        header_span = p_elem.find('span', style=lambda s: s and 'underline' in s)

        if header_span:
            # ΠΕΡΙΠΤΩΣΗ Α: ΒΡΙΣΚΕΙ ΥΠΟΓΡΑΜΜΙΣΜΕΝΟ ΤΙΤΛΟ
            raw_header = header_span.get_text(strip=True)
            raw_header = re.sub(r'[.:]+\s*$', '', raw_header).lower()
            raw_header = re.sub(r'\s+', ' ', raw_header).strip()

            section_key = None
            for key, aliases in SECTION_KEYS.items():
                if any(alias in raw_header or raw_header in alias for alias in aliases):
                    section_key = key
                    break

            if not section_key:
                section_key = f'UNKNOWN:{raw_header[:30]}'

            # Ενημέρωση της μνήμης
            current_section_key = section_key

            # Εξαγωγή καθαρού κειμένου (αφαιρούμε ΜΟΝΟ το string του τίτλου, όχι το tag)
            full_text = p_elem.get_text(separator=' ', strip=True)
            header_text = header_span.get_text(separator=' ', strip=True)
            section_text = full_text.replace(header_text, '', 1).strip()

            if current_section_key in sections:
                sections[current_section_key] += ' ' + section_text
            else:
                sections[current_section_key] = section_text

        else:
            # ΠΕΡΙΠΤΩΣΗ Β: Παράγραφος χωρίς τίτλο
            section_text = p_elem.get_text(separator=' ', strip=True)

            if not section_text:
                continue

            # ΒΗΜΑ 1: Startswith check — μόνο για structural sections
            # Αν η παράγραφος ΞΕΚΙΝΑΕΙ με keyword → section switch
            text_stripped = section_text.strip()
            for pattern, struct_key in STRUCTURAL_BREAKS:
                if pattern.match(text_stripped):
                    current_section_key = struct_key
                    break

            # ΒΗΜΑ 2: Αυστηρή προσθήκη στο (ενδεχομένως ενημερωμένο) current key
            if current_section_key in sections:
                sections[current_section_key] += ' ' + section_text
            else:
                sections[current_section_key] = section_text

    return sections


def _parse_sections_regex(html: str) -> dict:
    """
    Fallback parser με Lookahead (χωρίς BeautifulSoup).
    v3: Αποκόπτει Συμπεράσματα/Σχόλια από το tail text του τελευταίου section
        και τα δρομολογεί στο σωστό key.
    """
    sections = {}
    if not html.strip():
        return sections

    # Regex για αναγνώριση structural break μέσα σε plain text
    _STRUCT_SPLIT = re.compile(
        r'(?=\b(?:Συμπ[εέ]ρ[αά]σμα(?:τα)?|Σχ[οό]λια|Δι[αά]γνωση|Echo\s+Summary)\b)',
        re.IGNORECASE
    )

    # Lookahead: Σταματάει ΜΟΝΟ όταν βρει το επόμενο underline span ή το τέλος
    pattern = r'<span[^>]*text-decoration:\s*underline[^>]*>(.*?)</span>(.*?)(?=<span[^>]*text-decoration:\s*underline|$)'

    for m in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        raw_header = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        raw_header = re.sub(r'[.:]+\s*$', '', raw_header).lower()
        raw_header = re.sub(r'\s+', ' ', raw_header).strip()

        raw_body = m.group(2)
        # Καθαρισμός HTML tags
        body_text = re.sub(r'<[^>]+>', ' ', raw_body)
        body_text = re.sub(r'\s+', ' ', body_text).strip()

        # Αναγνώριση section key από τον header
        section_key = None
        for key, aliases in SECTION_KEYS.items():
            if any(alias in raw_header or raw_header in alias for alias in aliases):
                section_key = key
                break
        section_key = section_key or f'UNKNOWN:{raw_header[:30]}'

        # Split: αποκοπή structural sections (Συμπεράσματα/Σχόλια) από το body
        parts = _STRUCT_SPLIT.split(body_text)

        # Πρώτο κομμάτι → ανήκει στο section_key
        main_text = parts[0].strip()
        if main_text:
            if section_key in sections:
                sections[section_key] += ' ' + main_text
            else:
                sections[section_key] = main_text

        # Υπόλοιπα κομμάτια → structural sections
        for part in parts[1:]:
            part = part.strip()
            if not part:
                continue
            part_lower = part.lower()
            if part_lower.startswith('συμπ') or part_lower.startswith('σύμπ'):
                struct_key = 'CONCLUSIONS'
            elif part_lower.startswith(('σχόλια', 'σχολια', 'διάγνωση', 'διαγνωση', 'echo')):
                struct_key = 'COMMENTS'
            else:
                struct_key = section_key  # fallback

            if struct_key in sections:
                sections[struct_key] += ' ' + part
            else:
                sections[struct_key] = part

    return sections


def get_sec(sections: dict, key: str) -> str:
    """Helper: επιστρέφει section text ή '' αν δεν υπάρχει."""
    return sections.get(key, '')


# =============================================================================
# 17 BINARY FEATURE EXTRACTORS
# =============================================================================

def normalize(text: str) -> str:
    # 1. Μετατροπή σε πεζά και αφαίρεση κενών στην αρχή/τέλος
    text = text.lower().strip()
    
    # 2. Αφαίρεση τόνων (και άλλων διακριτικών σημαδιών)
    # Η NFD χωρίζει π.χ. το 'ά' στο γράμμα 'α' και στον τόνο '´'.
    # Η συνθήκη != 'Mn' κρατάει μόνο τα γράμματα και πετάει τα τονικά σημάδια.
    text = ''.join(c for c in unicodedata.normalize('NFD', text) 
                   if unicodedata.category(c) != 'Mn')
    
    # 3. Αντικατάσταση πολλαπλών κενών με ένα μονό κενό
    return re.sub(r'\s+', ' ', text)


def _has_negation(text: str, pos: int, window: int = 60) -> bool:
    preceding = text[max(0, pos - window):pos]
    return bool(re.search(
        r'(?:δεν\s+(?:εντοπ[ίι]ζεται|παρατηρε[ίι]ται|υπ[άα]ρχει)|χωρ[ίι][σς])',
        preceding
    ))


def get_pacemaker(sections: dict) -> int:
    """Βηματοδότης."""
    t = normalize(get_sec(sections, 'RV') + ' ' + get_sec(sections, 'FINDINGS') +
                  ' ' + get_sec(sections, 'TV'))

    has_defib = bool(re.search(r'απινιδωτικ[οό]\s+καλ[ώω]διο', t))
    has_pace  = bool(re.search(r'βηματοδοτ\w+', t))

    if has_defib and not has_pace:
        return 0

    for m in re.finditer(r'βηματοδοτ\w+', t):
        if not _has_negation(t, m.start()):
            return 1
    return 0


def get_rv_systolic_depressed(sections: dict) -> int:
    """
    Επηρεασμένη συστολική λειτουργία ΔΚ.
    Label=1 ΜΟΝΟ για μέτρια και άνω δυσλειτουργία.

    Μεθοδολογία: per-sentence evaluation (split στην τελεία πριν κεφαλαίο)
    για αποφυγή cross-sentence false positives, π.χ.:
      "σοβαρού βαθμού διάταση. Φυσιολογική συστολική λειτουργία."

    Σειρά ελέγχου ανά πρόταση: Normal → Mild → Moderate/Severe
    Αν ΟΠΟΙΑΔΗΠΟΤΕ πρόταση → moderate/severe: τελικό label=1.
    """
    raw = get_sec(sections, 'RV')
    if not raw:
        return 0

    # Split σε προτάσεις: τελεία + whitespace + κεφαλαίο (ελληνικό ή λατινικό)
    # Αγνοεί τελείες εντός αριθμών (π.χ. "1.4cm", "TAPSE=2.2")
    sentences = re.split(r'\.(?=\s*[Α-ΩA-ZΆ-Ώ]|\s*$)', raw)
    sentences = [normalize(s) for s in sentences if normalize(s)]

    if not sentences:
        return 0

    # ── STEP 1: Normal patterns ────────────────────────────────────────────
    step1_normal = [
        r'φυσιολογικ\w+\s+(?:\w+\s+){0,3}λειτουργ',
        r'λειτουργ\w*\s+(?:\w+\s+){0,3}(?:είναι\s+)?φυσιολογικ\w+',
        r'(?:είναι|ειναι)\s+φυσιολογικ\w+',
        r'καλ[ήη]\s+(?:επιμ[ήη]κ\w+\s+)?(?:συστολικ\w+\s+)?(?:λειτουργ|συσταλτικ|συσπαστικ)',
        r'καλ\w+\s+(?:επιμ[ήη]κ\w+\s+)?(?:συστολικ\w+\s+)?λειτουργ',
        r'διατηρημ[έε]ν\w+\s+(?:συστολικ\w+\s+)?(?:επιμ[ήη]κ\w+\s+)?λειτουργ',
        r'διατηρημ[έε]ν\w+\s+(?:συστολικ\w+\s+)?(?:επιμ[ήη]κ\w+\s+)?(?:συσταλτικ|συσπαστικ)\w+',
        r'ικανοποιητικ\w+\s+(?:συστολικ\w+\s+)?λειτουργ',
        r'φυσιολογικ\w+\s+(?:επιμ[ήη]κ\w+|συνολικ\w+)\s+(?:συσταλτικ|συσπαστικ|λειτουργ)\w+',
        r'συνολικ\w+\s+συστολικ\w+\s+λειτουργ',
        r'φυσιολογικ\w+\s+(?:\w+\s+){0,2}λειτ[υο]ργ',
        r'normal\s+(?:in\s+)?(?:size\s+(?:and\s+)?)?function',
        r'(?:normal|preserved|maintained)\s+(?:systolic\s+)?function',
        r'(?:good|normal)\s+(?:systolic\s+)?(?:contractility|function)',
    ]

    # ── STEP 2: Mild/Borderline → label 0 ─────────────────────────────────
    # (εκτός αν συνυπάρχει moderate/severe στην ΙΔΙΑ πρόταση)
    mild_only = [
        r'(?:ελαφρ[ώωάα]\w*|[ήη]πια|ηπ[ίι]ω\w*|μικρο[ύυ]\s+βαθμο[ύυ])\s+(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)',
        r'οριακ\w+\s+(?:επιμ[ήη]κ\w+\s+)?συ(?:στολικ|σπαστικ|σταλτικ)\w+',
        r'κατ[ώω]τερ\w+\s+φυσιολογικ\w+\s+[όο]ρι',
        r'[ήη]πι\w+\s+επηρεασμ[έε]ν\w+',
        r'οριακ\w+\s+(?:\w+\s+)?λειτουργ',
        r'λειτουργ\w*.*?(?:είναι|ειναι)\s+οριακ\w+',
        r'οριακ\w+\s+(?:\w+\s+){1,3}(?:και\s+)?λειτουργ\w+',
        r'συσταλτικ[όο]τητα\s+(?:\w+\s+){0,2}(?:είναι\s+)?οριακ\w+',
        r'mild(?:ly)?\s+(?:impaired|reduced|depressed)',
        r'borderline\s+(?:systolic\s+)?function',
        r'low(?:er)?\s+(?:normal|limit)',
    ]

    # ── STEP 3: Moderate/Severe → label 1 ─────────────────────────────────
    moderate_severe = [
        # Severity qualifier + function word (κανονική και αντεστραμμένη σειρά)
        r'(?:μ[έε]τρι\w+|σοβαρ\w+|κρ[ίι]σιμ\w+|μετρ[ίι]ου\s+βαθμο[ύυ]|σοβαρο[ύυ]\s+βαθμο[ύυ]).*?(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|δυσλειτουργ\w*|συ(?:στολικ|σταλτικ|σπαστικ)\w+)',
        r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|δυσλειτουργ\w*).*?(?:μ[έε]τρι\w+|σοβαρ\w+|κρ[ίι]σιμ\w+|μετρ[ίι]ου\s+βαθμο[ύυ]|σοβαρο[ύυ]\s+βαθμο[ύυ])',
        r'σημαντικ\w+\s+επηρεασμ[έε]ν\w+',
        # Impaired/reduced + function word (χωρίς severity qualifier → moderate assumption)
        r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)\s+(?:επιμ[ήη]κ\w+\s+)?(?:συστολικ\w+|συσταλτικ\w+|συσπαστικ\w+)\s+λειτουργ',
        r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)\s+(?:επιμ[ήη]κ\w+\s+)?(?:συσταλτικ[όο]τητα|συσπαστικ[όο]τητα)',
        r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)\s+επιμ[ήη]κ\w+\s+λειτουργ\w+',
        r'λειτουργ\w*.*?(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)',
        r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)\s+συστολικ\w+\s+λειτουργ',
        r'επηρεασμ[έε]ν\w+\s+(?:επιμ[ήη]κ\w+\s+)?λειτουργ\w+',
        r'επηρεασμ[έε]ν\w+\s+συ(?:σταλτικ|σπαστικ)\w+',
        r'συ(?:σταλτικ|σπαστικ)[όο]τητα\s+(?:\w+\s+)?(?:είναι\s+|ειναι\s+)?επηρεασμ[έε]ν\w+',
        r'ε[πη]?ηρεασμ[έε]\w*\s+(?:επιμ[ήη]κ\w+\s+)?(?:συστολικ\w+|συσταλτικ\w+|λειτουργ\w+)',
        r'επηρεασμ[έε]ν\w+\s+(?:επιμ[ήη]κ\w+\s+)?[σς]{1,2}τολικ\w+\s+λειτουργ\w+',
        r'επηρεασμ\w+\s+\w+\s+συστολικ\w+\s+λειτουργ\w+',
        # Αγγλικά
        r'(?:moderate(?:ly)?|severe(?:ly)?)\s+(?:impaired|reduced|depressed)',
        r'(?:impaired|reduced|depressed)\s+(?:systolic\s+)?function',
    ]

    # ── Per-sentence evaluation ────────────────────────────────────────────
    found_moderate_severe = False

    for sent in sentences:
        sent_is_normal = False
        sent_is_mild   = False

        # Βήμα 1: normal σε αυτή την πρόταση;
        for pat in step1_normal:
            if re.search(pat, sent):
                # Δεν είναι normal αν η ΙΔΙΑ πρόταση περιέχει impairment word
                if not re.search(r'επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|οριακ\w+', sent):
                    sent_is_normal = True
                break

        # Βήμα 2: mild σε αυτή την πρόταση (μόνο αν δεν είναι ήδη normal)
        if not sent_is_normal:
            for pat in mild_only:
                if re.search(pat, sent):
                    if not re.search(r'μ[έε]τρι|σοβαρ|κρ[ίι]σιμ', sent):
                        sent_is_mild = True
                    break

        # Βήμα 3: moderate/severe (μόνο αν η πρόταση δεν είναι normal/mild)
        if not sent_is_normal and not sent_is_mild:
            for pat in moderate_severe:
                m = re.search(pat, sent)
                if m:
                    matched = m.group()
                    # ΦΙΛΤΡΟ severity+διάταση: αν η severity αφορά μέγεθος (διάταση)
                    # και ΟΧΙ λειτουργία στην ίδια πρόταση → skip
                    if (re.search(r'(?:σοβαρ|μ[έε]τρι)', matched) and
                            re.search(r'δι[αά]τ[αά](?:ση|σε)', matched)):
                        continue
                    found_moderate_severe = True
                    break

        # Early exit μόλις βρεθεί moderate/severe
        if found_moderate_severe:
            break

    return 1 if found_moderate_severe else 0

def get_rv_dilation(sections: dict) -> int:
    """
    Διάταση ΔΚ. Μόνο μέτριου/σοβαρού → 1. Ήπια/μικρού/φυσιολογικό → 0.

    Μεθοδολογία: per-sentence evaluation (split στην τελεία πριν κεφαλαίο)
    για αποφυγή cross-sentence false positives.
    Σειρά ελέγχου ανά πρόταση: Normal → Mild → Moderate/Severe.
    Αν ΟΠΟΙΑΔΗΠΟΤΕ πρόταση → moderate/severe: τελικό label=1.
    """
    raw = get_sec(sections, 'RV')
    if not raw:
        return 0

    # Split σε προτάσεις: τελεία + whitespace + κεφαλαίο (ελληνικό ή λατινικό)
    sentences = re.split(r'\.(?=\s*[Α-ΩA-ZΆ-Ώ]|\s*$)', raw)
    sentences = [normalize(s) for s in sentences if normalize(s)]
    if not sentences:
        return 0

    # ── STEP 1: Normal size ────────────────────────────────────────────────
    step1_normal_size = [
        r'φυσιολογικ[όο]\s+μ[εέ]γεθο[σς]',
        r'φυσιολογικ[έε][σς]?\s+(?:εσωτερικ[έε]ς\s+)?δι[αά]στ\w*',
        r'φυσιολογικ\w+\s+(?:\w+\s+){0,2}μ[εέ]γεθο[σς]',
        r'normal\s+(?:in\s+)?size',
    ]

    # ── STEP 2: Mild dilation → label 0 ───────────────────────────────────
    step2_mild = [
        r'(?:[ήη]πια?\s+(?:βαθμο[ύυ]\s+)?|μικρο[ύυ]\s+βαθμο[ύυ]\s+)δι[άα]ταση',
        r'μικρο[ύυ]\s+βαθμο[ύυ]\s+δι[αά]τ[αα]ση',
        r'(?:[ήη]πια?|οριακ[άα])\s+αυξημ[εέ]ν[εηοό]\w*\s+δι[αά]στ[άα]σε',   # ήπια/οριακά αυξημένες διαστάσεις
        r'(?:[ήη]πια?|οριακ[άα])\s+αυξημ[εέ]ν[οό]\w*\s+μ[εέ]γεθο[σς]',      # ήπια/οριακά αυξημένο μέγεθος
        r'(?:[ήη]πια?|οριακ[άα])\s+διατεταμ[εέ]ν[ηή]',                        # ήπια/οριακά διατεταμένη
    ]

    # ── STEP 3: Moderate/Severe → label 1 ─────────────────────────────────
    step3_positive = [
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]\s+δι[άα]ταση',
        r'σοβαρ[ήη]?\s+δι[αά]τ[αα]ση',
        r'(?:αυξημ[έε]ν[εη][σς]?|αυξημ[έε]νων)\s+(?:εσωτερικ\w*\s+)?δι[αά]στ[άα]σε',
        r'αυξημ[έε]ν[οό]\s+μ[έε]γεθο[σς]',
        r'με\s+αυξημ[έε]ν[εη][σς]?\s+δι[αά]στ[άα]σε',
        r'αυξημ[έε]ν[ηή]\s+(?:βασικ[ήη]\s+)?δι[άα]μετρο',
        r'διατεταμ[εέ]ν[ηή]',
        r'διατεταμ[εέ]μν[ηή]',                                      # typo variant
        r'(?:εμφαν[ίι]ζει|παρουσι[άα]ζει)\s+δι[άα]ταση(?!\s*(?:[ήη]πι|μικρ))',
        r'(?:εμφαν[ίι]ζεται|ε[ίι]ναι)\s+διατεταμ',
        r'αυξημ[εέ]νων\s+(?:εσωτερικ\w*\s+)?δι[αά]στ[άα]σε',
        r'(?:εμφαν[ίι]ζει|παρουσι[άα]ζει)\s+αυξημ[εέ]ν\w+\s+δι[αά]στ[αά]σε',
        r'αυξημ[εέ]ν[οό]\s+μ[εέ]γεθο[σς]',
        r'δι[άα]ταση\s+τη[σς]\s+δεξι[άα][σς]?\s+κοιλ',
    ]

    # ── Per-sentence evaluation ────────────────────────────────────────────
    found_positive = False

    for sent in sentences:
        sent_is_normal = False
        sent_is_mild   = False

        # Βήμα 1: normal size σε αυτή την πρόταση;
        for pat in step1_normal_size:
            if re.search(pat, sent):
                # Δεν είναι normal αν η ΙΔΙΑ πρόταση περιέχει dilation word
                if not re.search(r'αυξημ[εέ]ν|δι[αά]ταση|διατεταμ', sent):
                    sent_is_normal = True
                break

        # Βήμα 2: mild dilation (μόνο αν δεν είναι normal)
        if not sent_is_normal:
            for pat in step2_mild:
                if re.search(pat, sent):
                    if not re.search(r'μετρ[ίι]ου|σοβαρο[ύυ]', sent):
                        sent_is_mild = True
                    break

        # Βήμα 3: moderate/severe (μόνο αν η πρόταση δεν είναι normal/mild)
        if not sent_is_normal and not sent_is_mild:
            for pat in step3_positive:
                if re.search(pat, sent):
                    found_positive = True
                    break

        # Early exit μόλις βρεθεί moderate/severe
        if found_positive:
            break

    return 1 if found_positive else 0

def get_la_dilation(sections: dict) -> int:
    """
    Διάταση αριστερού κόλπου. Μόνο μέτριου/σοβαρού → 1. Ήπια/μικρού/φυσιολογικό → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά: Negation guards (normal → mild) → Positive patterns.
    """
    t = normalize(get_sec(sections, 'LA'))
    if not t:
        return 0

    # ── 1. NEGATION GUARD — φυσιολογικό μέγεθος ──────────────────────────
    if re.search(r'φυσιολογικ[οό]\s+μ[έε]γεθο[σς]', t):
        return 0
    
    # Ρητή άρνηση (καλή πρακτική για ασφάλεια: "μη διατεταμένος", "χωρίς διάταση")
    if re.search(r'(?:μη\s+|δεν\s+(?:ε[ίι]ναι\s+|παρουσι[άα]ζει\s+|εμφαν[ίι]ζει\s+)|χωρ[ίι]ς\s+)(?:διατεταμ|δι[άα]ταση|[αά][υύ]ξηση)', t):
        return 0

    # ── 2. NEGATION GUARD — μικρού/ήπια + διάταση ή αύξηση όγκου → 0 ────
    if re.search(
        r'(?:μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια[σς]?\s+(?:βαθμο[ύυ]\s+)?)'
        r'\s*(?:[αά][υύ]ξηση\s+(?:του\s+)?[όο]γκου(?:\s+(?:\w+\s+){0,3}κ[όο]λπου)?|δι[άα]ταση)', t
    ):
        return 0

    # ── 3. NEGATION GUARD — ήπια/οριακά + αυξημένες/διατεταμένος/μέγεθος → 0
    if re.search(
        r'(?:[ήη]πια?|οριακ[άα])\s+αυξημ[έε]ν[εη][σς]?\s+δι[αά]στ[άα]σε'           # ήπια/οριακά αυξημένες διαστάσεις
        r'|(?:[ήη]πια?|οριακ[άα])\s+διατεταμ[έε]ν[οό][σς]?'                          # ήπια/οριακά διατεταμένος
        r'|(?:[ήη]πια?|οριακ[άα])\s+αυξημ[έε]ν[οό][σς]?\s+μ[έε]γεθο[σς]'            # ήπια/οριακά αυξημένο μέγεθος
        r'|οριακ[άα]\s+αυξημ[έε]ν[οό][σς]?\s+[όο]γκ'                                # οριακά αυξημένος όγκος
        r'|οριακ[έε]ς\s+δι[αά]στ[άα]σε', t                                         # οριακές διαστάσεις σκέτο
    ):
        return 0

    # ── 4. POSITIVE PATTERNS → 1 ──────────────────────────────────────────
    pos_patterns = [
        # Μέτρια/σοβαρή διάταση — κανονική και αντεστραμμένη σειρά
        # μ[εέ]τρ: καλύπτει τόσο 'μέτρια' (με τόνο) όσο και 'μετρίου' (χωρίς τόνο στο ε)
        r'(?:μ[εέ]τρ[ίι]α[σς]?|μ[εέ]τρ[ίι]ου(?:\s+βαθμο[ύυ])?|σοβαρ[ήη][σς]?|σοβαρο[ύυ](?:\s+βαθμο[ύυ])?)\s+δι[άα]ταση',
        # Αύξηση / αυξημένος όγκος
        r'(?:[αά][υύ]ξηση\s+(?:του\s+)?[όο]γκου|αυξημ[έε]ν\w*\s+[όο]γκ\w*)',
        # "εμφανίζει [βαθμού] διάταση"
        r'εμφαν[ίι]ζει\s+(?:βαθμο[ύυ]\s+)?δι[άα]ταση',
        # Αυξημένο μέγεθος
        r'αυξημ[έε]ν\w*\s+μ[έε]γεθο[σς]',
        # Αυξημένες/ων διαστάσεις/ων (και με typo δισατάσεις)
        r'αυξημ[έε]ν\w*\s+δι[αά]στ[αά]σε\w*',
        r'αυξημ[έε]ν\w*\s+δι[σς]ατ[αά]σε\w*',                    # typo variant
        # "σοβαρά διατεταμένος", "είναι/εμφανίζεται διατεταμένος"
        r'σοβαρ[αά]\s+διατεταμ[εέ]νο[σς]',
        r'(?:ε[ίι]ναι|εμφαν[ίι]ζεται)\s+διατεταμ[εέ]νο[σς]',
        # bare "διατεταμένος" (χωρίς qualifier — moderate assumption)
        r'διατε[τ]?αμ[εέ]νο[σς]',
    ]
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1

    return 0

def get_ra_dilation(sections: dict) -> int:
    """
    Διάταση δεξιού κόλπου. Μόνο μέτριου/σοβαρού → 1. Ήπια/μικρού/φυσιολογικό → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά: Negation guards (normal → explicit negation → mild) → Positive patterns.
    """
    t = normalize(get_sec(sections, 'RA'))
    if not t:
        return 0

    # ── 1. NEGATION GUARD — φυσιολογικό μέγεθος / φυσιολογικές διαστάσεις ──
    if re.search(
        r'φυσιολογικ[οό]\s+μ[έε]γεθο[σς]'
        r'|φυσιολογικ[έεώω][σςν]?\s+δι[αά]στ\w*'  # Καλύπτει: διαστάσεις, διαστάσεων, διαστάσιες
        r'|εντ[όο]ς\s+φυσιολογικ[ώω]ν\s+ορ[ίι]ων', t
    ):
        return 0

    # ── 2. NEGATION GUARD — ρητή άρνηση διάτασης ─────────────────────────
    if re.search(
        r'(?:δεν\s+(?:παρατηρε[ίι]ται|εντοπ[ίι]ζεται|υπ[άα]ρχει)\s+δι[άα]ταση'
        r'|χωρ[ίι][σς]\s+δι[άα]ταση)', t
    ):
        return 0

    # ── 3. NEGATION GUARD — μικρού/ήπια/ελαφριά/οριακή + διάταση/αύξηση → 0
    if re.search(
        r'(?:μικρο[ύυ]\s+(?:βαθμο[ύυ]\s+)?'
        r'|[ήη]πια?\s+(?:βαθμο[ύυ]\s+)?'
        r'|ελαφρ[ιί][αά]?\s+(?:βαθμο[ύυ]\s+)?'
        r'|οριακ[ήη]\s+)'
        r'(?:α[ύυ]ξηση\s+(?:του\s+)?[όο]γκου|δι[άα]ταση)', t
    ):
        return 0

    # ── 4. NEGATION GUARD — ήπια/ελαφρώς/μικρού/οριακά αυξημένες διαστάσεις
    if re.search(
        r'(?:[ήη]πια?|ελαφρ[ώω]ς|μικρο[ύυ]\s+βαθμο[ύυ]|οριακ[άα])\s+αυξημ[έε]ν[εηοό][σς]?\s+(?:δι[αά]στ[άα]σ[ιί]?ε\w*|μ[έε]γεθο[σς])'
        r'|οριακ[έεώω][σςν]?\s+δι[αά]στ[άα]σ[ιί]?ε\w*', t
    ):
        return 0

    # ── 5. POSITIVE PATTERNS → 1 ──────────────────────────────────────────
    pos_patterns = [
        # Μετρίου/σοβαρού/σημαντικού βαθμού διάταση ή αύξηση όγκου
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ]|σημαντικ[οό][ύυ])\s+βαθμο[ύυ]\s+δι[άα]ταση',
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ]|σημαντικ[οό][ύυ])\s+βαθμο[ύυ]\s+α[ύυ]ξηση\s+(?:του\s+)?[όο]γκου',
        # "διάταση του (δεξιού) κόλπου" — bare reference implies moderate+
        r'δι[άα]ταση\s+(?:του\s+)?(?:δεξιο[ύυ]\s+)?κ[όο]λπου',
        # Εμφανίζει / απεικονίζεται / έχει διάταση / διατεταμένος
        r'εμφαν[ίι]ζει\s+δι[άα]ταση',
        r'εμφαν[ίι]ζεται\s+διατεταμ',
        r'απεικον[ίι]ζεται\s+διατεταμ',
        r'(?:έχει|εχει)\s+δι[άα]ταση',
        # Αυξημένο μέγεθος / αύξηση όγκου / αντεστραμμένο μέγεθος αυξημένο
        r'αυξημ[έε]ν\w+\s+μ[έε]γεθο[σς]',
        r'μ[έε]γεθο[σς].{1,25}αυξημ[έε]ν[οό]',  # Καλύπτει: "Το μέγεθος το δεξιού κόλπου είναι αυξημένο"
        r'α[ύυ]ξηση\s+(?:του\s+)?[όο]γκου',
        # Αυξημένες/ων διαστάσεις/ων — όλες οι πτώσεις + typo
        r'με\s+αυξημ[έε]ν[εη][σς]?\s+δι[αά]στ[άα]σ[ιί]?ε',
        r'(?:αυξημ[έε]ν[εη][σς]?)\s+δι[αά]στ[άα]σ[ιί]?ε',
        r'(?:^|\s)αυξημ[εέ]ν[ωώ]ν\s+δι[αά]στ[άα]σ[ιί]?ε',
        r'αυξημ[έε]ν[οό][νσ]?\s+δι[αά]στ[άα]σ[ιί]?ε',
        r'αυξημ[έε]ν\w*\s+δι[σς]ατ\w*',                                          # typo variant
        # Bare "διατεταμένος" — moderate assumption
        r'διατεταμ[έε]ν[οό][σς]?',
    ]
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1

    return 0

def get_mitraclip(sections: dict) -> int:
    t = normalize(get_sec(sections, 'MV'))
    return 1 if re.search(r'mitra\s*clip', t) else 0


def get_mitral_annular_calcification(sections: dict) -> int:
    """
    Επασβέστωση μιτροειδικού δακτυλίου (MAC).
    Μόνο μετρίου/σοβαρού βαθμού ή χωρίς qualifier (bare) → 1.
    Μικρού/ήπια → 0. Μικρού προς μετρίου → 1 (borderline, αλλά label=1).

    Σειρά: Borderline → Mild guard → Positive patterns.
    """
    t = normalize(get_sec(sections, 'MV'))
    if not t:
        return 0

    # ── STEP 1: Borderline — μικρού προς μετρίου → label 1 ───────────────
    if re.search(r'μικρο[ύυ]\s+προς\s+μετρ[ίι]ου\s+βαθμο[ύυ]\s+επασβ[έε]στωση', t):
        return 1
    
    if re.search(r'μικρο[ύυ]\s+προς\s+μετρ[ίι]ου\s+βαθμο[ύυ]\s+επα[σς]{1,2}β[έε]στωσ[ηι][σς]', t):
        return 1

    # ── STEP 2: Mild guard — μικρού βαθμού / ήπια → label 0 ─────────────
    if re.search(r'(?:μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια?)\s+επασβ[έε]στωση', t):
        return 0
    
    if re.search(r'(?:μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια?[σς]?)\s+επα[σς]{1,2}β[έε]στωσ[ηι][σς]', t):
        return 0

    # ── STEP 3: Positive patterns → label 1 ──────────────────────────────
    pos_patterns = [
        # Τυπικές μορφές επασβέστωσης δακτυλίου (με ή χωρίς "οπίσθιου")
        r'επασβ[έε]στωση\s+(?:του\s+)?(?:οπ[ίι]σθιου\s+)?μιτροειδικο[ύυ]\s+δακτυλ[ίι]ου',
        r'επασβ[έε]στωση\s+οπ[ίι]σθιου\s+μιτροειδικο[ύυ]\s+δακτυλ[ίι]ου',
        # "επασβέστωση στον οπίσθιο μιτροειδικό δακτύλιο"
        r'επασβ[έε]στωσ[ηι][σς]?\s+στον\s+οπ[ίι]σθιο\s+μιτροειδικ[οό]\s+δακτ[ύυ]λιο',
        # Επασβέστωση οπίσθιας γλωχίνας
        r'επασβ[έε]στωση\s+(?:της\s+)?οπ[ίι]σθια[σς]\s+γλωχ[ίι]να[σς]',
        # "εμφανίζει επασβέστωση", "εμφανίζεται επασβεστωμένη"
        r'εμφαν[ίι]ζει\s+επασβ[έε]στωση',
        r'εμφαν[ίι]ζεται\s+επασβεστωμ[έε]ν[ηη]',
        # "επασβεστωμένη/ος οπίσθια/ος (γλωχίνα/δακτύλιος)"
        r'επασβεστωμ[έε]ν[ηοό][σς]?\s+οπ[ίι]σθι[αο][σς]?',
        # Επασβέστωση και ακινησία (παθολογική σύζευξη)
        r'επασβ[έε]στωση\s+και\s+ακινησ[ίι]α',
        r'ακινησ[ίι]α\s+(?:\w+\s+){0,3}?επασβ[έε]στωση',
        # Σημαντική επασβέστωση
        r'σημαντικ[ήη]\s+επασβ[εέ]στωση',
        # Μερικώς επασβεστωμένο
        r'μερικ[ώω]ς\s+επασβεστωμ[έε]ν[οό]',
        # Ασβέστωση δακτυλίου (συντομευμένος όρος)
        r'ασβ[έε]στωση\s+(?:του\s+)?(?:οπ[ίι]σθιου\s+)?μιτροειδικο[ύυ]\s+δακτυλ[ίι]ου',
        # Επασβέστωση υπομιτροειδικής συσκευής / δακτυλίου
        r'επασβ[έε]στωση\s+(?:του\s+)?(?:υπο)?μιτροειδ\w+\s+(?:συσκευ[ήη][σς]?|δακτυλ[ίι]ου)',
        # Ασβεστοποιητική μεταβολή δακτυλίου
        r'ασβεστοποιητικ[ήη]\s+μεταβολ[ήη]\s+(?:του\s+)?δακτυλ[ίι]ου',
        # Caseous MAC (αγγλικός/λατινικός όρος)
        r'caseous\s+mitral\s+(?:valve\s+)?calcification',
        # Επασβεστωμένο μόρφωμα (caseous MAC variant)
        r'επασβεστωμ[έε]νο\s+μ[όο]ρφωμα',
        # "επασβέστωσης (της) οπίσθιας/πρόσθιας γλωχίνας"
        r'επα[σς]{1,2}β[έε]στωσ[ηι][σς]\s+(?:της\s+)?(?:οπ[ίι]σθια[σς]|πρ[οό]σθια[σς])\s+γλωχ[ίι]να[σς]',
        # "επασβέστωσης (του) (οπίσθιου) μιτροειδικού δακτυλίου"
        r'επα[σς]{1,2}β[έε]στωσ[ηι][σς]\s+(?:του\s+)?(?:οπ[ίι]σθιου\s+)?μιτροειδικο[ύυ]\s+δακτυλ[ίι]ου',
        #Severity σε γενική — "σοβαρής/μετρίας/σημαντικής επασβέστωσης"
        r'(?:σοβαρ[ήη][σς]?|μ[έε]τρι[αά][σς]?|σημαντικ[ήη][σς]?)\s+επα[σς]{1,2}β[έε]στωσ[ηι][σς]',
        #Adverb + participle — "σημαντικά επασβεστωμένη"
        r'σημαντικ[άα]\s+επασβεστωμ[έε]ν[ηή]',
        #Typo double-σ + anatomy context
        r'επασσβ[έε]στωσ[ηι][σς]?\s+(?:\w+\s+){0,2}(?:οπ[ίι]σθι|πρ[οό]σθι|μιτροειδ|γλωχ[ίι]ν|δακτυλ[ίι])',
        #Causal genitive — "λόγω επασβέστωσης" (bare, without nearby anatomy)
        r'λ[όο]γω\s+(?:\w+\s+)?επα[σς]{1,2}β[έε]στωσ[ηι][σς]',
        #Preventive — "επασβεστωμένη/ος πρόσθια/ος" (symmetric with existing posterior)
        r'επασβεστωμ[έε]ν[ηοό][σς]?\s+πρ[οό]σθι[αο][σς]?',
    ]
    
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1

    return 0

def get_mitral_stenosis(sections: dict) -> int:
    """
    Στένωση μιτροειδούς. Μόνο μέτριου/σοβαρού → 1. Μικρή/ήπια → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά:
      1. Prosthetic guard (μηχανική/προσθετική βαλβίδα → 0 εκτός ρητής στένωσης)
      2. Borderline: μικρού προς μετρίου → 1
      3. Mild guard → 0
      4. Positive patterns → 1
    """
    t = normalize(get_sec(sections, 'MV'))
    if not t:
        return 0

    # ── 1. PROSTHETIC / MECHANICAL VALVE GUARD ────────────────────────────
    # Αν υπάρχει προσθετική βαλβίδα, τα PHT/MVA νούμερα δεν αντιπροσωπεύουν
    # φυσική στένωση → επιστρέφουμε 0 εκτός αν υπάρχει ρητή αναφορά μέτριας/σοβαρής
    if re.search(
        r'(?:μηχανικ[ήη]|προσθετικ[ήη][σς]?|μεταλλικ[ήη]|βιοπροσθετικ[ήη][σς]?)\s+'
        r'(?:βαλβ[ίι]δ|μιτροειδ)', t
    ):
        has_explicit_stenosis = bool(re.search(
            r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?στ[έε]νωσ'
            r'|στ[έε]νωσ.*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]'
            r'|(?:μ[έε]τρια|σοβαρ[ήη])\s+στ[έε]νωσ', t
        ))
        if not has_explicit_stenosis:
            return 0

    # ── 2. BORDERLINE: μικρού προς μετρίου → label 1 ─────────────────────
    if re.search(
        r'μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου\s+(?:βαθμο[ύυ]\s+)?στ[έε]νωσ'
        r'|στ[έε]νωσ\w*\s+(?:ρευματικ[ήη][σς]?\s+αιτιολογ[ίι]α[σς]\s+)?'
        r'(?:\([^)]*\)\s*)?μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου', t
    ):
        return 1

    if re.search(r'μικρ[ήη]\s+προ[σς]\s+μ[έε]τρια\s+στ[έε]νωσ', t):
        return 1

    # ── 3. NEGATION GUARD — mild/ήπια στένωση → label 0 ──────────────────
    # Πιάνει: "μικρή/μικρού βαθμού/ήπια στένωση" (ανεξαρτήτως σειράς)
    # Εξαίρεση: "μικρού προς μετρίου" έχει ήδη πιαστεί στο STEP 2
    if re.search(
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?)\s+'
        r'(?:βαθμο[ύυ]\s+)?(?:περιορισμ[οό][σς]?\s+στη\s+δι[αά]νοιξη|στ[έε]νωσ)', t
    ):
        return 0

    if re.search(
        r'στ[έε]νωσ\w*\s+(?:\([^)]*\)\s+)?(?:ρευματικ[ήη][σς]?\s+αιτιολογ[ίι]α[σς]\s+)?'
        r'(?:μικρο[ύυ]\s+βαθμο[ύυ]|μικρ[ήη](?!\s+προ[σς]))', t
    ):
        return 0

    # ── 4. POSITIVE PATTERNS → label 1 ───────────────────────────────────
    pos_patterns = [
        # Μετρίου/σοβαρού βαθμού στένωση (κανονική και αντεστραμμένη σειρά)
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?στ[έε]νωσ',
        r'στ[έε]νωσ.*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]',
        # Μέτρια / σοβαρή στένωση (adjective form — κανονική και αντεστραμμένη)
        r'(?:μ[έε]τρια|σοβαρ[ήη])\s+στ[έε]νωσ',
        r'στ[έε]νωσ.*?(?:μ[έε]τρια|σοβαρ[ήη])',
    ]
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1

    return 0

def get_mitral_regurgitation(sections: dict) -> int:
    """
    Ανεπάρκεια μιτροειδούς. ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια/ίχνος → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά:
      1. Borderline (μικρού προς μετρίου) → 1
      2. Mild guard (ήπια/μικρή/ίχνος) → 0
      3. Positive (μέτρια/σοβαρή/σημαντική) → 1

    Bidirectional matching: πιάνει τόσο "μέτρια ανεπάρκεια" όσο και
    "ανεπάρκεια ... μετρίου βαθμού" (έως 3 ενδιάμεσες λέξεις).
    """
    t = normalize(get_sec(sections, 'MV'))
    if not t:
        return 0

    # ── 1. BORDERLINE: μικρού/ήπιου προς μετρίου → label 1 ──────────────
    # Καλύπτει: "μικρού προς μετρίου ανεπάρκεια", "ανεπάρκεια μικρή προς μέτρια"
    borderline_pat = (
        r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
    )
    if re.search(borderline_pat, t):
        return 1

    # ── 2. MILD GUARD: ήπια/μικρή/ίχνος → label 0 ───────────────────────
    # Καλύπτει: "ήπια ανεπάρκεια", "ανεπάρκεια μικρού βαθμού", "ίχνος διαφυγής"
    # Εξαίρεση: "μικρού προς μετρίου" έχει ήδη πιαστεί στο STEP 1
    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[εάα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    if re.search(mild_pat, t):
        return 0

    # ── 3. POSITIVE: μέτρια / σοβαρή / σημαντική → label 1 ──────────────
    # Καλύπτει: "μέτρια ανεπάρκεια", "ανεπάρκεια μετρίου βαθμού",
    #           "μετρίου προς σοβαρού", "σημαντική διαφυγή"
    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
    )
    if re.search(pos_pat, t):
        return 1

    return 0


def get_tavr(sections: dict) -> int:
    """Προσθετική αορτική βαλβίδα (TAVR/TAVI / βιοπροσθετική / μηχανική)."""
    t = normalize(get_sec(sections, 'AV'))
    
    pos_patterns = [
        # Χρησιμοποιούμε το \w* στο τέλος των λέξεων για να πιάσουμε όλες 
        # τις πτώσεις (π.χ. βιοπροσθετική, βιοπροσθετικής, βαλβίδα, βαλβίδας, βαλβίδος)
        r'βιοπροσθετικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*',
        r'μηχανικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*',
        r'προσθετικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*',
        
        # Ακρωνύμια (TAVR και TAVI)
        r'\btavr\b',
        r'\btavi\b'
    ]
    
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1
            
    return 0

def get_bicuspid_aov(sections: dict) -> int:
    """Δίπτυχος αορτική βαλβίδα (Bicuspid Aortic Valve — BAV).
    
    'δίφυλλη μηχανική βαλβίδα' = τύπος προσθετικής → label 0.
     φυσική δίπτυχη/δίλοβη αορτική βαλβίδα → label 1.
    """
    t = normalize(get_sec(sections, 'AV'))

    # Εμπλουτισμένη λίστα με όλα τα πιθανά λεκτικά μορφώματα (χωρίς περιορισμό απόστασης)
    pos_patterns = [
        r'δ[ίι]πτυχ\w*',      # δίπτυχη, δίπτυχος, δίπτυχης
        r'δ[ίι]φυλλ\w*',      # δίφυλλη, δίφυλλος
        r'δ[ίι]λοβ\w*',       # δίλοβη, δίλοβος
        r'\bbicuspid\b',      # αγγλικός όρος
        r'δ[ύυ]ο\s+πτυχ[έεήη]\w*' # περιγραφική μορφή
    ]

    for pat in pos_patterns:
        if re.search(pat, t):
            # Ψάχνει οπουδήποτε στο κείμενο αν υπάρχει "μηχανική" ή "προσθετική".
            if not re.search(r'μηχανικ[ήη]|προσθετικ[ήη]', t):
                return 1
                
    return 0

def get_aortic_stenosis(sections: dict) -> int:
    """
    Αορτική στένωση (AS). ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά:
      1. Borderline (μικρού προς μετρίου / οριακά) → 1
      2. Mild guard (ήπια/μικρή) → 0
      3. Positive (μέτρια/σοβαρή/σημαντική + negation guard) → 1

    Bidirectional matching: πιάνει severity→στένωση και στένωση→severity
    με έως 3 ενδιάμεσες λέξεις.
    """
    t = normalize(get_sec(sections, 'AV'))
    if not t:
        return 0

    # ── 1. BORDERLINE (ελέγχεται πρώτο) ──────────────────────────────────
    # Πιάνει: "μικρού προς μετρίου στένωση", "ήπια έως μέτρια στένωση",
    #         "οριακά σοβαρή", "οριακή στένωση"
    borderline_pat = (
        r'(?:μικρ[οόύη]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
        r'|οριακ[άαήη]\s+(?:σοβαρ\w*|σημαντικ\w*|μετρ[ίι]\w*|μ[έε]τρι\w*|στ[εέ]νωσ\w*)'
    )
    if re.search(borderline_pat, t):
        return 1

    # ── 2. MILD GUARD (ελέγχεται δεύτερο) ────────────────────────────────
    # Πιάνει: "ήπια στένωση", "στένωση μικρού βαθμού", "ελαφριά στένωση"
    # Bidirectional
    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
    )
    if re.search(mild_pat, t):
        return 0

    # ── 3. POSITIVE PATTERNS (moderate / severe / significant) ───────────
    # Bidirectional + "τουλάχιστον μετρίου"
    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
        r'|τουλ[άα]χιστον\s+(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+(?:βαθμο[ύυ]\s+)?στ[εέ]νωσ'
    )
    if re.search(pos_pat, t):
        # Negation guard: "χωρίς/δεν εμφανίζει/απουσία ... μέτρια/σοβαρή στένωση"
        negation_guard = (
            r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται|υπ[άα]ρχει)|απουσ[ίι]α)'
            r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*στ[εέ]νωσ'
        )
        if re.search(negation_guard, t):
            return 0
        return 1

    return 0


def get_aortic_regurgitation(sections: dict) -> int:
    """
    Αορτική Ανεπάρκεια (AR). ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια/ίχνος → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά:
      1. Borderline (μικρού/ήπιου προς μετρίου) → 1
      2. Mild guard (ήπια/μικρή/ίχνος) → 0
      3. Positive (μέτρια/σοβαρή/σημαντική + negation guard) → 1

    Bidirectional matching: πιάνει severity→ανεπάρκεια/διαφυγή και
    ανεπάρκεια/διαφυγή→severity (έως 3 ενδιάμεσες λέξεις).
    """
    t = normalize(get_sec(sections, 'AV'))
    if not t:
        return 0

    # ── 1. BORDERLINE: μικρού/ήπιου προς μετρίου → label 1 ──────────────
    borderline_pat = (
        r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
    )
    if re.search(borderline_pat, t):
        return 1

    # ── 2. MILD GUARD: ήπια/μικρή/ίχνος → label 0 ───────────────────────
    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    if re.search(mild_pat, t):
        return 0

    # ── 3. POSITIVE: μέτρια / σοβαρή / σημαντική → label 1 ──────────────
    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
    )
    if re.search(pos_pat, t):
        # Negation guard: "χωρίς/δεν/απουσία ... μέτρια/σοβαρή ανεπάρκεια/διαφυγή"
        negation_guard = (
            r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται)|απουσ[ίι]α)'
            r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        )
        if re.search(negation_guard, t):
            return 0
        return 1

    return 0


def get_tricuspid_regurgitation(sections: dict) -> int:
    """
    Ανεπάρκεια τριγλώχινας (TR). ΜΟΝΟ μετρίου/σοβαρού → 1.
    Μικρή/ήπια/ίχνος/φυσιολογική → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Σειρά:
      1. Negation guard (χωρίς/δεν/απουσία ανεπάρκεια) → 0
         εκτός αν συνυπάρχει ρητό moderate+ στην ίδια πρόταση
      2. Mild guard (μικρή/ήπια) → 0
         εκτός αν υπάρχει mild→moderate transition
      3. Trace / physiologic guard → 0
      4. Mild-to-moderate transition (μικρού προς μετρίου) → 1
      5. Positive patterns (μέτρια/σοβαρή + negation guard) → 1
    """
    t = normalize(get_sec(sections, 'TV'))
    if not t:
        return 0

    # ── 1. NEGATION GUARD: χωρίς/δεν/απουσία ────────────────────────────
    # Guard εκτός αν υπάρχει competing moderate+ αναφορά
    if re.search(
        r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται)|απουσ[ίι]α)\s+'
        r'.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])', t
    ):
        if not re.search(
            r'(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])[,\s]+.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
            r'|(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])', t
        ):
            return 0

    # ── 2. MILD GUARD: μικρή/ήπια ανεπάρκεια → 0 ─────────────────────────
    # (εκτός αν mild-to-mod transition)
    has_mild = bool(re.search(
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια?).*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
        r'|(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μικρο[ύυ]\s+βαθμο[ύυ]|μικρ[ήη]|[ήη]πια?)', t
    ))
    has_mild_to_mod = bool(re.search(
        r'μικρο[ύυ]\s+προ[σς]\s+μ[εέ]τρ[ίι]?[οωυ]?'
        r'|μικρ[ήη]\s+προ[σς]\s+μ[εέ]τρια'
        r'|[ήη]πι\w*\s+προ[σς]\s+μ[εέ]τρ', t
    ))
    if has_mild and not has_mild_to_mod:
        if not re.search(
            r'(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])[,\s]+.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
            r'|(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])', t
        ):
            return 0

    # ── 3. TRACE / PHYSIOLOGIC GUARD → 0 ──────────────────────────────────
    if re.search(r'[ίι]χνο[σς]?\s+(?:ανεπ[αά]ρκεια[σς]?|διαφυγ[ήη][σς]?)', t):
        if not re.search(r'(?:μετρ|σοβαρ|μ[εέ]τρια)', t):
            return 0
    if re.search(r'φυσιολογικ\w+\s+(?:διαφυγ[ήη]|ανεπ[αά]ρκεια)', t):
        return 0

    # ── 4. MILD-TO-MODERATE TRANSITION → 1 ────────────────────────────────
    if has_mild_to_mod and re.search(r'ανεπ[αά]ρκεια|διαφυγ[ήη]', t):
        return 1

    # ── 5. POSITIVE PATTERNS → 1 ──────────────────────────────────────────
    pos_patterns = [
        # Μετρίου/σοβαρού βαθμού (κανονική + αντεστραμμένη)
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
        r'(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]',
        # Μέτρια / σοβαρή (adjective form)
        r'(?:μ[εέ]τρια|σοβαρ[ήη]).*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
        r'(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μ[εέ]τρια|σοβαρ[ήη])',
        # No-accent fallback
        r'σοβαρη\s+ανεπαρκεια',
        # Μετρίου προς σοβαρού
        r'μετρ[ίι]ου\s+προ[σς]\s+σοβαρ\w*\s+.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
        # Τριγλωχινική ανεπάρκεια μετρίου/σοβαρού βαθμού
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?τριγλωχινικ[ήη]\s+ανεπ[αά]ρκεια',
    ]
    negation_guard = (
        r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[αά]ζει|παρατηρε[ίι]ται)|απουσ[ίι]α)\s+'
        r'.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
    )
    for pat in pos_patterns:
        if re.search(pat, t):
            if not re.search(negation_guard, t):
                return 1

    return 0


def get_pericardial_effusion(sections: dict) -> int:
    """
    Περικαρδιακή συλλογή. Μέτρια/σοβαρή → 1. Ίχνος/μικρή/ελεύθερο → 0.

    Pipeline:
      1. Masking: πλευριτικές συλλογές + περικαρδιακό λίπος αποκρύπτονται
         (με τα νούμερά τους) για αποφυγή false positives
      2. Numeric path (εκτελείται ΠΡΩΤΟ αν υπάρχουν τιμές):
         > 20 mm → 1 (severe)  |  > 11 mm → 1 (moderate)  |  ≤ 11 mm → 0 (mild)
      3. Phrase path (αν δεν υπάρχουν νούμερα):
         A1. Borderline → 1
         A2. Slash-separated list with moderate+ → 1
         B.  Mild/trace/free guard → 0
         C.  Positive patterns → 1
    """
    t = normalize(get_sec(sections, 'PERICARDIUM'))
    if not t:
        return 0

    # ── 1. MASKING ────────────────────────────────────────────────────────
    # Αφαιρούμε πλευριτικές συλλογές και λίπος ΜΑΖΙ με τα νούμερά τους
    t_clean = re.split(r'\b(?:συμπ[εέ]ρασμα(?:τα)?|σχ[όο]λια|παρατηρ[ήη]σει[σς])\b', t)[0]
    t_clean = re.sub(r'πλευριτικ[ήηέεςσ][^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)', '[PLEURAL_MASK]', t_clean)
    t_clean = re.sub(r'(?:περικαρδιακ|επι|υπο)καρδιακ[οό]\s+λ[ίι]πο[σς][^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)', '[FAT_MASK]', t_clean)
    t_clean = re.sub(r'πλευριτικ[ήηέεςσ]\s+συλλογ[ήηέεςσ]', '[PLEURAL]', t_clean)
    t_clean = re.sub(r'(?:περικαρδιακ[οό]|επι|υπο)καρδιακ[οό]\s+λ[ίι]πο[σς]', '[FAT]', t_clean)

    # ── 2. NUMERIC PATH (εκτελείται πρώτο αν υπάρχουν τιμές) ──────────────
    max_mm = None
    for m in re.finditer(
        r'(\d+(?:[.,]\d+)?)\s*(?:-\s*(\d+(?:[.,]\d+)?)\s*)?(mm|cm)\b', t_clean, re.I
    ):
        v1 = float(m.group(1).replace(',', '.'))
        v2 = float(m.group(2).replace(',', '.')) if m.group(2) else v1
        val = max(v1, v2)
        if m.group(3).lower() == 'cm':
            val *= 10
        if max_mm is None or val > max_mm:
            max_mm = val

    if max_mm is not None:
        return 1 if max_mm > 11 else 0

    # ── 3. PHRASE PATH (εκτελείται ΜΟΝΟ αν δεν υπάρχουν νούμερα) ─────────

    # STEP A1: Borderline (μικρής προς μέτριας / οριακά μέτρια) → 1
    borderline_pat = (
        r'(?:μικρ[οόύη]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)'
        r'|οριακ[άαήη]\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεγ[άα]λ\w*|σοβαρ\w*)'
    )
    if re.search(borderline_pat, t_clean):
        return 1

    # STEP A2: Slash-separated severity list with moderate+ term → 1
    # e.g. "μικρής/μεσαίου μεγέθους/ευμεγέθους ... συλλογής"
    slash_moderate_pat = (
        r'(?:μικρ\w+|μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)'
        r'\s*/\s*'
        r'(?:μικρ\w+|μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)'
    )
    if re.search(slash_moderate_pat, t_clean) and re.search(r'συλλογ[ήη]', t_clean):
        if re.search(r'(?:μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)', t_clean):
            return 1

    # STEP B: Mild / trace / free / negated → 0
    mild_pat = (
        # Μικρή/ήπια/ελάχιστη/ασήμαντη + συλλογή
        r'(?:μικρ[ήη]|μικρ[ήη][σς]\s+μεγ[έε]θους|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ\w+|αμελητ[έε]|ασ[ήη]μαντ\w+)'
        r'(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]'

        r'|(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]\s+(?:\w+\s+){0,3}'
        r'(?:μικρ[ήη]|μικρ[ήη][σς]\s+μεγ[έε]θους|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ\w+|ασ[ήη]μαντ\w+)'
        r'(?:\s+βαθμο[ύυ])?'

        # ίχνη/ίχνος
        r'|[ίι]χν\w+\s+(?:περικαρδιακ\w*\s+)?(?:συλλογ\w+|υγρ\w+)'
        r'|[ίι]χνο[σς]\s+(?:περικαρδιακο[ύυ]\s+υγρο[ύυ]|υγρο[ύυ]|συλλογ[ήη][σς]?)'

        # Ελεύθερο / χωρίς / δεν παρατηρείται / απουσία
        r'|ελε[ύυ]θερο'
        r'|χωρ[ίι][σς]\s+(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]'
        r'|δεν\s+(?:παρατηρε[ίι]ται|απεικον[ίι]ζεται)\s+(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]'
        r'|απουσ[ίι]α\s+συλλογ[ήη]'
    )
    if re.search(mild_pat, t_clean):
        return 0

    # STEP C: Positive (μέτρια / μεγάλη / σοβαρή / σημαντική) → 1
    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου\s+μεγ[έε]θους|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*|ευμεγ[έε]θ\w*)'
        r'(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]'
        r'|(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]\s+(?:\w+\s+){0,3}'
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*|ευμεγ[έε]θ\w*)'
    )
    if re.search(pos_pat, t_clean):
        # Negation guard: "χωρίς/δεν/απουσία ... μέτρια/σοβαρή συλλογή"
        negation_guard = (
            r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται|υπ[άα]ρχει)|απουσ[ίι]α)'
            r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*συλλογ[ήη]'
        )
        if re.search(negation_guard, t_clean):
            return 0
        return 1

    return 0

def get_aortic_root_dilation(sections: dict) -> int:
    """
    Διάταση ρίζας αορτής → 1. Φυσιολογική/ήπια → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Αρχιτεκτονική:
      1. Smart sentence extractor: κρατά ΜΟΝΟ προτάσεις που αναφέρουν
         ρίζα αορτής (αποκλείει ανιούσα/τόξο με masking)
      2. Phrase extractor: Borderline → Mild guard → Positive patterns

    Σειρά phrase extractor:
      1. Borderline (μικρού προς μετρίου διάταση ρίζας) → 1
      2. Mild guard (φυσιολογική / ήπια / οριακή / χωρίς διάταση ρίζας) → 0
      3. Positive (διάταση/ανεύρυσμα/μέτρια ρίζας) → 1
    """

    # ── Helper: Masking ανιούσας αορτής / τόξου ──────────────────────────
    def _mask_aorta(t: str) -> str:
        """Κρύβει αναφορές σε ανιούσα αορτή και αορτικό τόξο μαζί με τα νούμερά τους."""
        t = re.sub(r'ανιο[ύυ]σ[αη]ς?\s+αορτ[ήη]ς?[^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)?', '[ASC_MASK]', t)
        t = re.sub(r'αορτικ[οό]\s+τ[όο]ξο[^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)?', '[ARCH_MASK]', t)
        t = re.sub(r'κατιο[ύυ]σ[αη]ς?\s+αορτ[ήη]ς?[^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)?', '[DESC_MASK]', t)
        t = re.sub(r'ανιο[ύυ]σ[αη]ς?\s+αορτ[ήη]ς?', '[ASC_AORTA]', t)
        t = re.sub(r'αορτικ[οό]\s+τ[όο]ξο', '[AORTIC_ARCH]', t)
        t = re.sub(r'κατιο[ύυ]σ[αη]ς?\s+αορτ[ήη]ς?', '[DESC_AORTA]', t)
        return t

    # ── Smart sentence extractor ──────────────────────────────────────────
    # Συλλέγει από ΟΛΕΣ τις anatomical ενότητες (εκτός Conclusion/Comments)
    # και κρατά ΜΟΝΟ προτάσεις που αναφέρουν ρίζα αορτής.
    excluded_keys = {'CONCLUSIONS', 'COMMENTS', 'FINDINGS'}
    parts = [text.strip() for key, text in sections.items()
             if key not in excluded_keys and text.strip()]
    full_text = ' '.join(parts)
    if not full_text:
        return 0

    # Failsafe: αποκοπή στο σημείο "συμπέρασμα/σχόλια"
    full_text = re.split(
        r'(?i)\b(?:συμπ[εέ]ρασμα(?:τα)?|σχ[όο]λια|παρατηρ[ήη]σει[σς])\b', full_text
    )[0]

    # Split σε προτάσεις
    text_split = re.sub(r'\.\s+', '|||', full_text)
    text_split = re.sub(r'\n+', '|||', text_split)
    text_split = re.sub(r';\s*', '|||', text_split)
    sentences = text_split.split('|||')

    root_sentences = []
    for s in sentences:
        s_norm = normalize(s)
        if (re.search(r'ρ[ίι]ζ[αη]ς?|\baor\b|\broot\b', s_norm) or
                re.search(r'αορτ[ήη]ς?\s*[:=]\s*\(?\d', s_norm)):
            root_sentences.append(s.strip())

    if not root_sentences:
        return 0

    # Ενοποίηση root sentences + masking
    t_raw = ' ... '.join(root_sentences)
    t_clean = _mask_aorta(normalize(t_raw))

    # ── Phrase extractor ──────────────────────────────────────────────────

    # STEP 1a: "οριακή διάταση ρίζας" → 0
    borderline_normal_pat = (
    r'οριακ[άαήησς]\w*\s+(?:δι[αά]τασ\w*|διατεταμ\w+|διευρυσμ\w+)\s+(?:\w+\s+){0,4}(?:στη\s+)?ρ[ίι]ζ\w*'
    )
    if re.search(borderline_normal_pat, t_clean):
        return 0

    # STEP 1b: "μικρού/ήπιου προς μέτριου βαθμού διάταση ρίζας" → 1
    borderline_dilation_pat = (
        r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,4}δι[αά]τασ\w*\s+(?:\w+\s+){0,4}ρ[ίι]ζ\w*'
    )
    if re.search(borderline_dilation_pat, t_clean):
        return 1

    # STEP 2: Mild / normal / negated → 0
    # Αν η πρόταση περιέχει mild/normal/negation + ρίζα → 0
    # εκτός αν συνυπάρχει ρητό moderate+/ανεύρυσμα ΣΤΟ ΙΔΙΟ ΚΕΙΜΕΝΟ
    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια)(?:\s+βαθμο[ύυ])?\s+δι[αά]τασ\w*\s+(?:\w+\s+){0,4}ρ[ίι]ζ\w*'
        r'|φυσιολογικ[έεήη]\w*\s+(?:διαστ[άα]σει[σς]|μ[έε]γεθο[σς])(?:\s+\w+){0,4}\s+ρ[ίι]ζ\w*'
        r'|(?:χωρ[ίι]ς|δεν\s+παρατηρε[ίι]ται|απουσ[ίι]α)\s+δι[αά]τασ\w*\s+(?:\w+\s+){0,4}ρ[ίι]ζ\w*'
    )
    if re.search(mild_pat, t_clean):
        # Override: αν υπάρχει ρητό moderate+/ανεύρυσμα ΠΑΡΑ ΤΑ MILD
        has_competing = bool(re.search(
            r'(?:μετρ[ίι]\w*|σοβαρ\w*|σημαντικ\w*|ανε[υύ]ρυσμ\w+|οριακ[άαήη])\s+'
            r'(?:\w+\s+){0,4}(?:δι[αά]τασ\w*|ρ[ίι]ζ\w*)', t_clean
        ))
        if not has_competing:
            return 0

    # STEP 3: Positive (διάταση / ανεύρυσμα / μέτρια ρίζας) → 1
    pos_pat = (
        r'(?:δι[αά]τασ\w*|διατεταμ\w+|ανε[υύ]ρυσμ\w+|διευρυσμ\w+)\s+(?:\w+\s+){0,4}(?:της\s+)?ρ[ίι]ζ\w*'
        r'|ρ[ίι]ζ\w*\s+(?:\w+\s+){0,4}(?:δι[αά]τασ\w*|διατεταμ\w+|ανε[υύ]ρυσμ\w+|διευρυσμ\w+)'
        r'|(?:μετρ[ίι]\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+βαθμο[ύυ])?\s+δι[αά]τασ\w*\s+(?:\w+\s+){0,4}ρ[ίι]ζ\w*'
        # Parenthesized enumeration: "διάτασης (της ρίζας..." / "παρουσία διάτασης (της ρίζας..."
        r'|(?:δι[αά]τασ\w*|διατεταμ\w+|ανε[υύ]ρυσμ\w+|διευρυσμ\w+)\s*\(\s*(?:της\s+)?ρ[ίι]ζ\w*'
        r'|παρουσ[ίι]α\s+δι[αά]τασ\w*\s*\(?(?:της\s+)?ρ[ίι]ζ\w*'
    )
    if re.search(pos_pat, t_clean):
        return 1

    return 0

def get_dilated_ivc(sections: dict) -> int:
    """
    Διατεταμένη Κάτω Κοίλη Φλέβα (ΚΚΦ/IVC). → 1.
    Φυσιολογική / δεν διατεταμένη → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.

    Αρχιτεκτονική:
      1. Smart sentence extractor: κρατά ΜΟΝΟ προτάσεις που αναφέρουν
         "κάτω κοίλη" ή "ivc" (από ΟΛΕΣ τις ενότητες)
      2. Phrase extractor: Borderline → Normal guard → Positive patterns

    Σειρά phrase extractor:
      1. Borderline (οριακές διαστάσεις/μέγεθος) → 1
      2. Normal guard (φυσιολογικές / χωρίς διάταση) → 0
      3. Positive (διατεταμένη / αυξημένες διαστάσεις / διάταση ΚΚΦ) → 1
    """

    # ── Smart sentence extractor ──────────────────────────────────────────
    # Συλλέγει από ΟΛΕΣ τις anatomical ενότητες (εκτός Conclusion/Comments)
    # και κρατά ΜΟΝΟ προτάσεις που αναφέρουν "κάτω κοίλη" ή "ivc".
    excluded_keys = {'CONCLUSIONS', 'COMMENTS', 'Conclusion', 'Comments'}
    parts = [text.strip() for key, text in sections.items()
             if key not in excluded_keys and text.strip()]
    full_text = ' '.join(parts)
    if not full_text:
        return 0

    # Failsafe: αποκοπή στο σημείο "συμπέρασμα/σχόλια"
    full_text = re.split(
        r'(?i)\b(?:συμπ[εέ]ρασμα(?:τα)?|σχ[όο]λια|παρατηρ[ήη]σει[σς])\b', full_text
    )[0]

    # Split σε προτάσεις
    text_split = re.sub(r'\.\s+', '|||', full_text)
    text_split = re.sub(r'\n+', '|||', text_split)
    text_split = re.sub(r';\s*', '|||', text_split)
    sentences = text_split.split('|||')

    ivc_sentences = []
    for s in sentences:
        s_norm = normalize(s)
        if re.search(r'κ[άα]τω\s+κο[ίι]λ\w*|\bivc\b', s_norm):
            ivc_sentences.append(s.strip())

    if not ivc_sentences:
        return 0

    t = normalize(' ... '.join(ivc_sentences))

  # ── Phrase extractor ──────────────────────────────────────────────────

    # STEP 1: Borderline (οριακές διαστάσεις / οριακά αυξημένες κ.λπ.) → 0 (Κλινικά Αυστηρό)
    # Πιάνει: "οριακές διαστάσεις", "οριακά αυξημένες διαστάσεις", "οριακά διατεταμένη", "οριακή διάταση"
    if re.search(
        r'οριακ[έεάαήηόο][^\s\.]*\s+'
        r'(?:'
            r'(?:αυξημ[έε]ν[^\s\.]*\s+|διατεταμ[έε]ν[^\s\.]*\s+)?(?:διαστ[άα]σει[σς]|μ[έε]γεθο[σς])'
            r'|δι[άα]ταση'
            r'|διατεταμ[έε]ν[^\s\.]*'
            r'|αυξημ[έε]ν[^\s\.]*'
        r')', 
        t
    ):
        return 0

    # STEP 2: Normal guard — φυσιολογικές / χωρίς/δεν + διατεταμένη → 0
    if re.search(
        r'φυσιολογικ[έεήη][^\s\.]*\s+(?:διαστ[άα]σει[σς]|μ[έε]γεθο[σς])'
        r'|(?:χωρ[ίι]ς|δεν\s+(?:παρατηρε[ίι]ται|εμφαν[ίι]ζεται|απεικον[ίι]ζεται|ε[ίι]ναι))\s+(?:διατεταμ[έε]ν[^\s\.]*|δι[άα]ταση)',
        t
    ):
        # Override ΜΟΝΟ αν υπάρχει ΕΠΙΒΕΒΑΙΩΤΙΚΗ αναφορά (ελέγχεται αν δεν προηγείται negation)
        affirmed = False
        # Αυξημένες διαστάσεις/μέγεθος — δεν χρειάζεται negation check 
        if re.search(r'αυξημ[έε]ν[^\s\.]*\s+(?:διαστ[άα]σει[σς]|μ[έε]γεθο[σς])', t):
            affirmed = True
        # Διάταση ΚΚΦ (bare dilation phrase)
        if re.search(r'δι[άα]ταση\s+(?:[^\.\s]+\s+){0,3}(?:της\s+)?κ[άα]τω\s+κο[ίι]λ[^\s\.]*', t):
            affirmed = True
        # "εμφανίζεται/είναι/παρατηρείται διατεταμένη" — μόνο αν ΔΕΝ προηγείται "δεν"
        for m_aff in re.finditer(
            r'(?:εμφαν[ίι]ζεται|ε[ίι]ναι|παρατηρε[ίι]ται)\s+διατεταμ[έε]ν[^\s\.]*', t
        ):
            preceding = t[max(0, m_aff.start() - 10):m_aff.start()]
            if not re.search(r'δεν\s*$', preceding.rstrip()):
                affirmed = True
                break
        if not affirmed:
            return 0

    # STEP 3: Positive (διατεταμένη / αυξημένες διαστάσεις / διάταση ΚΚΦ) → 1
    if re.search(
        r'διατεταμ[έε]ν[^\s\.]*'
        r'|αυξημ[έε]ν[^\s\.]*\s+(?:διαστ[άα]σει[σς]|μ[έε]γεθο[σς])'
        r'|α[ύυ]ξηση\s+μεγ[έε]θους'
        r'|δι[άα]ταση\s+(?:[^\.\s]+\s+){0,3}(?:της\s+)?κ[άα]τω\s+κο[ίι]λ[^\s\.]*'
        r'|δι[άα]ταση\s+ivc',
        t
    ):
        return 1

    return 0

# =============================================================================
# MASTER EXTRACTOR
# =============================================================================
BINARY_FEATURES = [
    # Right heart
    'pacemaker',
    'rv_systolic_function_depressed',
    'right_ventricle_dilation',
    'right_atrium_dilation',          
    
    # Left atrium
    'left_atrium_dilation',
    
    # Mitral valve
    'mitraclip',
    'mitral_annular_calcification',
    'mitral_stenosis',                 
    'mitral_regurgitation',
    
    # Aortic valve
    'tavr',
    'bicuspid_aov',                    
    'aortic_stenosis',                 
    'aortic_regurgitation',
    
    # Aorta
    'aortic_root_dilation',            
    
    # Tricuspid valve
    'tricuspid_valve_regurgitation',
    
    # Pericardium
    'pericardial_effusion',            
    
    # IVC
    'dilated_ivc',
]


def extract_labels_from_html(html: str) -> dict:
    """Pipeline: HTML → sections dict → binary labels"""
    sections = parse_sections(html)
    return {
        # Right heart
        'pacemaker':                      get_pacemaker(sections),
        'rv_systolic_function_depressed': get_rv_systolic_depressed(sections),
        'right_ventricle_dilation':       get_rv_dilation(sections),
        'right_atrium_dilation':          get_ra_dilation(sections),         # ← NEW
        
        # Left atrium
        'left_atrium_dilation':           get_la_dilation(sections),
        
        # Mitral valve
        'mitraclip':                      get_mitraclip(sections),
        'mitral_annular_calcification':   get_mitral_annular_calcification(sections),
        'mitral_stenosis':                get_mitral_stenosis(sections),     
        'mitral_regurgitation':           get_mitral_regurgitation(sections),
        
        # Aortic valve
        'tavr':                           get_tavr(sections),
        'bicuspid_aov':                   get_bicuspid_aov(sections),        
        'aortic_stenosis':                get_aortic_stenosis(sections),
        'aortic_regurgitation':           get_aortic_regurgitation(sections),
        
        # Aorta
        'aortic_root_dilation':           get_aortic_root_dilation(sections),
        
        # Tricuspid valve
        'tricuspid_valve_regurgitation':  get_tricuspid_regurgitation(sections),
        
        # Pericardium
        'pericardial_effusion':           get_pericardial_effusion(sections),
        
        # IVC
        'dilated_ivc':                    get_dilated_ivc(sections),
    }
# =============================================================================
# BATCH PROCESSING
# =============================================================================

def run_batch(dataset_dir: str, output_csv: str, max_files: int = None):
    chm_entries = find_all_chm_files(dataset_dir)

    if not chm_entries:
        logger.error(f"Δεν βρέθηκαν εξετάσεις στο: {dataset_dir}")
        return

    if max_files:
        chm_entries = chm_entries[:max_files]

    total = len(chm_entries)
    logger.info(f"Βρέθηκαν {total} εξετάσεις — ξεκινά processing...")

    results, failed = [], []

    for i, entry in enumerate(chm_entries):
        exam_id  = entry["exam_id"]
        chm_path = entry["chm_path"]

        if i % 50 == 0:
            logger.info(f" [{i+1}/{total}] {exam_id}")

        html = extract_report_html(chm_path)
        if not html:
            logger.warning(f" ✗ {exam_id}: αποτυχία extraction")
            failed.append({'exam_id': exam_id, 'chm_path': chm_path})
            continue

        labels = extract_labels_from_html(html)
        results.append({'exam_id': exam_id, 'chm_path': chm_path, **labels})

    # ── CSV output ──────────────────────────────────────────────────────────
    fieldnames = ['exam_id', 'chm_path'] + BINARY_FEATURES
    
    # 1. Διασφαλίζουμε ότι ο φάκελος προορισμού υπάρχει
    from pathlib import Path
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)

    # 2. Προστασία από ανοιχτό αρχείο
    try:
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
    except PermissionError:
        # Αν το αρχείο είναι ανοιχτό, σώζουμε σε εναλλακτικό όνομα για να μη χάσουμε τα δεδομένα!
        backup_csv = output_csv.replace('.csv', '_backup.csv')
        logger.error(f"Το αρχείο {output_csv} είναι κλειδωμένο/ανοιχτό! Σώσιμο στο: {backup_csv}")
        with open(backup_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
            
    # ── Στατιστικά ──────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"✓ Επιτυχία: {len(results)}/{total}")
    logger.info(f"✗ Αποτυχίες: {len(failed)}")
    logger.info(f"Output: {output_csv}")

    if results:
        logger.info(f"\nBinary label distribution:")
        logger.info(f"  {'Feature':<42} {'Pos':>5} {'Total':>7} {'%':>6}")
        logger.info(f"  {'-'*58}")
        for feat in BINARY_FEATURES:
            vals  = [r[feat] for r in results]
            pos_n = sum(vals)
            pct   = 100 * pos_n / len(vals) if vals else 0
            logger.info(f"  {feat:<42} {pos_n:>5} {len(vals):>7} {pct:>5.1f}%")
    if failed:
        failed_log = output_csv.replace('.csv', '_failed.csv')
        with open(failed_log, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['exam_id', 'chm_path'])
            writer.writeheader()
            writer.writerows(failed)
        logger.info(f"Αποτυχημένα: {failed_log}")


# =============================================================================
# MAIN / ENTRY POINT (F5 run)
# =============================================================================

if __name__ == "__main__":
  
    DATASET_DIR = r"data/reports" 
 
    OUTPUT_CSV = r"outputs/ground_truth/per_finding/v5_labels.csv"
    
    # Συμπληρώνων έναν αριθμό αν θέλω να τρέξει πρώτα για ένα δείγμα 
    # Αν θέλω να τρέξει για όλο το dataset συμληρώνω None
    MAX_FILES = None
    
    logger.info("Εκκίνηση προγράμματος (F5 Mode)...")
    run_batch(DATASET_DIR, OUTPUT_CSV, MAX_FILES)
    logger.info("Η εκτέλεση ολοκληρώθηκε!")