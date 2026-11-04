"""
rv_systolic_extractor_standalone.py
===================================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για το finding
rv_systolic_function_depressed.

Λογική: τα regex του v6 ΑΥΤΟΥΣΙΑ. Η λίστα mild_only χωρίστηκε σε
MILD / BORDERLINE και το label ορίζεται από δύο flags:
    RV_SYS_MILD_POSITIVE       = True   → ήπια δυσλειτουργία = 1
    RV_SYS_BORDERLINE_POSITIVE = False  → οριακή / κατώτερα φυσ. όρια = 0
Κάθε πρόταση του section "Δεξιά κοιλία" παίρνει grade
(normal / borderline / mild / moderate_severe / no_mention)·
το grade της εξέτασης είναι το σοβαρότερο από τις προτάσεις της.

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση (exam_id, label, grade, status, report_path)
  Evidence : μία γραμμή ανά πρόταση του section RV που έδωσε grade
             (πρόταση, φράση που ταίριαξε, κανόνας, αν καθόρισε το label)

Εξαρτήσεις: pip install beautifulsoup4 openpyxl
            7-Zip μόνο αν υπάρχουν reports σε .CHM
"""

import re
import shutil
import logging
import subprocess
import tempfile
import unicodedata
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[ΠΡΟΕΙΔΟΠΟΙΗΣΗ] Δεν βρέθηκε beautifulsoup4 → fallback σε regex parser. "
          "Συνιστάται: pip install beautifulsoup4")

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("rv_systolic")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από ground_truth_extractor)
# =============================================================================

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
# TEXT HELPERS  (αυτούσια από ground_truth_extractor)
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



# =============================================================================
# FLAGS
# =============================================================================
RV_SYS_MILD_POSITIVE       = True
RV_SYS_BORDERLINE_POSITIVE = False


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v6 (μην τα επεξεργαστείς εδώ)
# =============================================================================

# STEP 1 — v6 step1_normal (14 patterns, ίδια σειρά)
RV_SYS_NORMAL = [
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

# STEP 2 — v6 mild_only (11 patterns) χωρισμένα σε δύο υπο-λίστες.
# Το σχόλιο [i] = θέση στην αρχική mild_only.
RV_SYS_MILD = [
    r'(?:ελαφρ[ώωάα]\w*|[ήη]πια|ηπ[ίι]ω\w*|μικρο[ύυ]\s+βαθμο[ύυ])\s+(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+)',  # [0]
    r'[ήη]πι\w+\s+επηρεασμ[έε]ν\w+',                                   # [3]
    r'mild(?:ly)?\s+(?:impaired|reduced|depressed)',                     # [8]
]
RV_SYS_BORDERLINE = [
    r'οριακ\w+\s+(?:επιμ[ήη]κ\w+\s+)?συ(?:στολικ|σπαστικ|σταλτικ)\w+',  # [1]
    r'κατ[ώω]τερ\w+\s+φυσιολογικ\w+\s+[όο]ρι',                          # [2]
    r'οριακ\w+\s+(?:\w+\s+)?λειτουργ',                                  # [4]
    r'λειτουργ\w*.*?(?:είναι|ειναι)\s+οριακ\w+',                        # [5]
    r'οριακ\w+\s+(?:\w+\s+){1,3}(?:και\s+)?λειτουργ\w+',               # [6]
    r'συσταλτικ[όο]τητα\s+(?:\w+\s+){0,2}(?:είναι\s+)?οριακ\w+',       # [7]
    r'borderline\s+(?:systolic\s+)?function',                           # [9]
    r'low(?:er)?\s+(?:normal|limit)',                                   # [10]
]

# STEP 3 — v6 moderate_severe (16 patterns, ίδια σειρά)
RV_SYS_MOD_SEV = [
    r'(?:μ[έε]τρι\w+|σοβαρ\w+|κρ[ίι]σιμ\w+|μετρ[ίι]ου\s+βαθμο[ύυ]|σοβαρο[ύυ]\s+βαθμο[ύυ]).*?(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|δυσλειτουργ\w*|συ(?:στολικ|σταλτικ|σπαστικ)\w+)',
    r'(?:επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|δυσλειτουργ\w*).*?(?:μ[έε]τρι\w+|σοβαρ\w+|κρ[ίι]σιμ\w+|μετρ[ίι]ου\s+βαθμο[ύυ]|σοβαρο[ύυ]\s+βαθμο[ύυ])',
    r'σημαντικ\w+\s+επηρεασμ[έε]ν\w+',
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
    r'(?:moderate(?:ly)?|severe(?:ly)?)\s+(?:impaired|reduced|depressed)',
    r'(?:impaired|reduced|depressed)\s+(?:systolic\s+)?function',
]

# Guards του v6 (αυτούσια)
_NORMAL_GUARD = r'επηρεασμ[έε]ν\w+|μειωμ[έε]ν\w+|οριακ\w+'
_MILD_GUARD   = r'μ[έε]τρι|σοβαρ|κρ[ίι]σιμ'
_DIL_SEV      = r'(?:σοβαρ|μ[έε]τρι)'
_DIL_WORD     = r'δι[αά]τ[αά](?:ση|σε)'

# ── ADDITIVE ONLY: νέα patterns ΗΠΙΑΣ βαρύτητας από το corpus ────────────────
# Κενό by design. Προσθέτεις ΜΟΝΟ φράσεις που εντοπίστηκαν σε πραγματικά reports
# (βλ. βήμα «συγκομιδής» από το sandbox v7). Ελέγχονται μετά το RV_SYS_MILD,
# με τον ίδιο guard. Κάθε γραμμή: (pattern, παράδειγμα από report / exam_id).
RV_SYS_MILD_ADDED = [
    # (r'(?:ηπια|ελαφρα)\s+δυσλειτουργ\w*', 'Ήπια δυσλειτουργία — exam ...'),
]

GRADE_ORDER = {'no_mention': 0, 'normal': 1, 'borderline': 2, 'mild': 3, 'moderate_severe': 4}


# =============================================================================
# CORE LOGIC — ίδια ροή με v6, επιστρέφει grade αντί για bool
# =============================================================================

def _split_sentences_v6(raw: str) -> list:
    """Αυτούσιος splitter του v6. Επιστρέφει (raw_sentence, normalized)."""
    parts = re.split(r'\.(?=\s*[Α-ΩA-ZΆ-Ώ]|\s*$)', raw)
    return [(p.strip(), normalize(p)) for p in parts if normalize(p)]


def _first_match(patterns, text):
    for i, pat in enumerate(patterns):
        m = re.search(pat, text)
        if m:
            return i, m
    return None, None


def grade_rv_sentence_v6(sent: str) -> tuple:
    """
    Βαθμολογεί μία ΚΑΝΟΝΙΚΟΠΟΙΗΜΕΝΗ πρόταση με τη λογική του v6.
    Returns: (grade, rule, matched_phrase)
      grade ∈ {'normal','mild','borderline','moderate_severe','no_mention'}
    """
    # Βήμα 1 — normal (v6: break στο ΠΡΩΤΟ match· normal μόνο αν δεν υπάρχει impairment word)
    i, m = _first_match(RV_SYS_NORMAL, sent)
    if m and not re.search(_NORMAL_GUARD, sent):
        return 'normal', f'normal[{i}]', m.group()

    # Βήμα 2 — mild_only (v6: mild αν ΚΑΠΟΙΟ pattern ταιριάζει ΚΑΙ δεν υπάρχει severity word)
    if not re.search(_MILD_GUARD, sent):
        i, m = _first_match(RV_SYS_MILD, sent)
        if m:
            return 'mild', f'mild[{i}]', m.group()
        i, m = _first_match([p for p, _ in RV_SYS_MILD_ADDED], sent)
        if m:
            return 'mild', f'mild_added[{i}]', m.group()
        i, m = _first_match(RV_SYS_BORDERLINE, sent)
        if m:
            return 'borderline', f'borderline[{i}]', m.group()

    # Βήμα 3 — moderate/severe (v6: με φίλτρο severity+διάταση)
    for i, pat in enumerate(RV_SYS_MOD_SEV):
        m = re.search(pat, sent)
        if m:
            matched = m.group()
            if re.search(_DIL_SEV, matched) and re.search(_DIL_WORD, matched):
                continue
            return 'moderate_severe', f'mod_sev[{i}]', matched

    return 'no_mention', '', ''


def positive_grades(mild_positive=None, borderline_positive=None) -> set:
    mild_positive = RV_SYS_MILD_POSITIVE if mild_positive is None else mild_positive
    borderline_positive = RV_SYS_BORDERLINE_POSITIVE if borderline_positive is None else borderline_positive
    pos = {'moderate_severe'}
    if mild_positive:
        pos.add('mild')
    if borderline_positive:
        pos.add('borderline')
    return pos


def grade_rv_systolic_v6x(sections: dict, mild_positive=None, borderline_positive=None) -> dict:
    """
    Exam grade = το σοβαρότερο grade από όλες τις προτάσεις του section RV.
    Το dict έχει τα ίδια keys με το grade_rv_systolic() του sandbox v7,
    ώστε να χρησιμοποιείται αυτούσιο το run_batch / Excel review του sandbox.
    """
    best = {'grade': 'no_mention', 'rule': '', 'match': '', 'evidence': '',
            'source': '', 'sent_idx': ''}
    matches = []
    raw = get_sec(sections, 'RV')
    for idx, (sent_raw, sent_norm) in enumerate(_split_sentences_v6(raw) if raw else []):
        grade, rule, match = grade_rv_sentence_v6(sent_norm)
        if grade == 'no_mention':
            continue
        rec = {'grade': grade, 'rule': rule, 'match': match, 'evidence': sent_raw,
               'source': 'RV', 'sent_idx': idx + 1}
        matches.append(rec)
        if GRADE_ORDER[grade] > GRADE_ORDER[best['grade']]:
            best = rec

    pos = positive_grades(mild_positive, borderline_positive)
    out = dict(best)
    out['label']            = 1 if best['grade'] in pos else 0
    out['label_rv_only']    = out['label']
    out['grade_rv_section'] = best['grade']
    out['grade_summary']    = 'no_mention'
    out['matches']          = matches
    return out


def get_rv_systolic_depressed_v6x(sections: dict) -> int:
    """Drop-in αντικατάσταση της get_rv_systolic_depressed (ίδιο signature)."""
    return grade_rv_systolic_v6x(sections)['label']



# =============================================================================
# ΕΝΤΟΠΙΣΜΟΣ ΦΡΑΣΗΣ ΣΤΟ ΑΡΧΙΚΟ ΚΕΙΜΕΝΟ (με τόνους/κεφαλαία)
# =============================================================================

def _normalize_with_map(orig: str) -> tuple:
    """Ίδια κανονικοποίηση με normalize(), κρατώντας τη θέση κάθε χαρακτήρα στο αρχικό."""
    out, idx, prev_space = [], [], True
    for i, ch in enumerate(orig):
        for c in unicodedata.normalize('NFD', ch.lower()):
            if unicodedata.category(c) == 'Mn':
                continue
            if c.isspace():
                if prev_space:
                    continue
                c, prev_space = ' ', True
            else:
                prev_space = False
            out.append(c)
            idx.append(i)
    return ''.join(out), idx


def original_phrase(orig: str, phrase_norm: str) -> str:
    """Επιστρέφει τη φράση όπως είναι γραμμένη στο report (ή την κανονικοποιημένη αν δεν βρεθεί)."""
    phrase_norm = phrase_norm.strip()
    if not orig or not phrase_norm:
        return phrase_norm
    norm, idx = _normalize_with_map(orig)
    pos = norm.find(phrase_norm)
    if pos < 0:
        return phrase_norm
    return orig[idx[pos]: idx[pos + len(phrase_norm) - 1] + 1]


# =============================================================================
# ΑΝΑΓΝΩΣΗ REPORTS (HTML ή CHM)
# =============================================================================

HTML_EXT = {'.html', '.htm'}
CHM_EXT  = {'.chm'}


def find_report_files(root_folder: str) -> list:
    """
    Δομή: <root>/<exam_id>/report/<αρχείο>.html|.htm|.chm
    Προτεραιότητα HTML > CHM· αν >1 ίδιου τύπου, το πιο πρόσφατο.
    """
    root = Path(root_folder)
    if not root.is_dir():
        logger.error(f"Ο φάκελος δεν υπάρχει: {root}")
        return []
    entries = []
    for study in sorted(d for d in root.iterdir() if d.is_dir()):
        report_dirs = [d for d in study.iterdir() if d.is_dir() and d.name.lower() == 'report']
        if not report_dirs:
            continue
        files = [f for f in report_dirs[0].iterdir() if f.is_file()]
        for exts, rtype in ((HTML_EXT, 'html'), (CHM_EXT, 'chm')):
            cand = sorted((f for f in files if f.suffix.lower() in exts),
                          key=lambda f: f.stat().st_mtime, reverse=True)
            if cand:
                entries.append({'exam_id': study.name, 'report_path': str(cand[0]), 'report_type': rtype})
                break
    return entries


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='windows-1253', errors='replace')


def _read_chm(chm_path: str, seven_zip: str):
    """Εξάγει το CHM με 7-Zip και επιστρέφει τη μεγαλύτερη σελίδα HTML (το κυρίως report)."""
    with tempfile.TemporaryDirectory(prefix='chm_') as tmp:
        try:
            subprocess.run([seven_zip, 'x', str(chm_path), f'-o{tmp}', '-y'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=60, check=False,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning(f"7-Zip απέτυχε για {chm_path}: {exc}")
            return None
        pages = [f for f in Path(tmp).rglob('*')
                 if f.is_file() and f.suffix.lower() in HTML_EXT and not f.name.startswith(('#', '$'))]
        if not pages:
            return None
        return _read_text_file(max(pages, key=lambda f: f.stat().st_size))


def read_report(entry: dict, seven_zip: str):
    if entry['report_type'] == 'html':
        return _read_text_file(Path(entry['report_path']))
    return _read_chm(entry['report_path'], seven_zip)


def load_exclusion_list(path) -> set:
    """.txt με ένα exam_id ανά γραμμή (αγνοούνται κενές γραμμές και ό,τι μετά από '#')."""
    if not path:
        return set()
    p = Path(path)
    if not p.is_file():
        logger.warning(f"Exclusion list δεν βρέθηκε: {p} → δεν εξαιρείται καμία εξέταση")
        return set()
    try:
        text = p.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        text = p.read_text(encoding='windows-1253')
    ids = set()
    for line in text.splitlines():
        line = line.split('#', 1)[0]
        ids.update(t.strip() for t in re.split(r'[,;\s]+', line) if t.strip())
    return ids


# =============================================================================
# EXCEL (2 sheets)
# =============================================================================

def write_excel(path: Path, label_rows: list, evidence_rows: list):
    wb = Workbook()
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='305496')
    pos_fill    = PatternFill('solid', fgColor='FCE4D6')

    def fill_sheet(ws, columns, rows, widths, wrap_cols=()):
        ws.append(columns)
        for c in ws[1]:
            c.font, c.fill = header_font, header_fill
        for r in rows:
            ws.append([r.get(col, '') for col in columns])
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
        for col in wrap_cols:
            j = columns.index(col) + 1
            for row in ws.iter_rows(min_row=2, min_col=j, max_col=j):
                row[0].alignment = Alignment(wrap_text=True, vertical='top')
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions

    ws1 = wb.active
    ws1.title = 'Labels'
    cols1 = ['exam_id', 'rv_systolic_function_depressed', 'grade', 'status', 'report_path']
    fill_sheet(ws1, cols1, label_rows, [18, 16, 18, 16, 70])
    for row in ws1.iter_rows(min_row=2):
        if row[1].value == 1:
            for c in row:
                c.fill = pos_fill

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'sentence_no', 'sentence_grade', 'decisive', 'rule',
             'matched_phrase', 'sentence']
    fill_sheet(ws2, cols2, evidence_rows, [18, 11, 18, 10, 16, 40, 90], wrap_cols=('sentence',))
    for row in ws2.iter_rows(min_row=2):
        if row[3].value == 1:
            row[5].font = Font(bold=True, color='C00000')

    wb.save(path)


# =============================================================================
# RUN
# =============================================================================

def run(dataset_dir: str, output_xlsx: str, exclusion_list=None, seven_zip='', max_files=None):
    entries = find_report_files(dataset_dir)
    logger.info(f"Reports που βρέθηκαν: {len(entries)}")

    excluded = load_exclusion_list(exclusion_list)
    if excluded:
        n0 = len(entries)
        entries = [e for e in entries if e['exam_id'] not in excluded]
        logger.info(f"Εξαιρέθηκαν (exclusion list): {n0 - len(entries)}")

    if any(e['report_type'] == 'chm' for e in entries):
        if not (seven_zip and Path(seven_zip).is_file()):
            seven_zip = shutil.which('7z') or shutil.which('7za') or ''
        if not seven_zip:
            logger.error("Υπάρχουν .CHM reports αλλά δεν βρέθηκε 7-Zip (SEVEN_ZIP_PATH).")
            return

    if max_files:
        entries = entries[:max_files]

    label_rows, evidence_rows = [], []
    for i, e in enumerate(entries):
        if i % 200 == 0:
            logger.info(f"  [{i + 1}/{len(entries)}] {e['exam_id']}")

        html = read_report(e, seven_zip)
        if not html:
            label_rows.append({'exam_id': e['exam_id'], 'rv_systolic_function_depressed': '',
                               'grade': '', 'status': 'read_failed', 'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        res = grade_rv_systolic_v6x(sections)
        status = 'ok' if get_sec(sections, 'RV') else 'no_RV_section'

        label_rows.append({'exam_id': e['exam_id'],
                           'rv_systolic_function_depressed': res['label'],
                           'grade': res['grade'], 'status': status,
                           'report_path': e['report_path']})

        for m in res['matches']:
            evidence_rows.append({
                'exam_id':        e['exam_id'],
                'sentence_no':    m['sent_idx'],
                'sentence_grade': m['grade'],
                'decisive':       int(m['sent_idx'] == res['sent_idx']),
                'rule':           m['rule'],
                'matched_phrase': original_phrase(m['evidence'], m['match']),
                'sentence':       m['evidence'],
            })

    out = Path(output_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_excel(out, label_rows, evidence_rows)
    except PermissionError:
        logger.error(f"Το {out} είναι ανοιχτό στο Excel — κλείσ' το και ξανατρέξε.")
        return

    n_ok = sum(1 for r in label_rows if r['status'] != 'read_failed')
    n_pos = sum(1 for r in label_rows if r['rv_systolic_function_depressed'] == 1)
    logger.info("=" * 60)
    logger.info(f"MILD_POSITIVE={RV_SYS_MILD_POSITIVE} | BORDERLINE_POSITIVE={RV_SYS_BORDERLINE_POSITIVE}")
    logger.info(f"Εξετάσεις: {len(label_rows)} | αναγνώστηκαν: {n_ok} | "
                f"αποτυχίες: {len(label_rows) - n_ok}")
    if n_ok:
        logger.info(f"Θετικές (label=1): {n_pos} ({100 * n_pos / n_ok:.1f}%)")
    logger.info(f"Excel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/rv_systolic_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή

    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
