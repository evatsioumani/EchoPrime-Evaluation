r"""
pericardial_effusion_v6x2.py
============================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για το finding
pericardial_effusion.

ΝΕΟΣ ΚΑΝΟΝΑΣ
  label = 1 : υπάρχει περικαρδιακή συλλογή οποιουδήποτε μεγέθους
              (μικρή / μέτρια / μεγάλη / αμφίσημοι όροι / μόνο μέτρηση σε mm /
               σκέτο «συλλογή» χωρίς χαρακτηρισμό)
  label = 0 : ίχνος/ίχνη, απουσία συλλογής (ελεύθερο, χωρίς, δεν παρατηρείται,
              απουσία, άρνηση), trivial (0 mm), καμία αναφορά

  Κλίμακα μεγέθους (numeric path):
      Trivial  = 0 mm      → 0
      Small    < 10 mm     → 1
      Moderate 10–20 mm    → 1
      Large    > 20 mm     → 1

ΔΕΥΤΕΡΟ LABEL (v6x3) — label_mod_severe  (στήλη pericardial_effusion_mod_severe)
  Ίδια εξαγωγή, ίδια αποφασιστική πηγή (Απόφαση Α), ίδιο grade. Το grade και
  το any-size label ΔΕΝ αλλάζουν.
      1 : moderate (10–20 mm), large (> 20 mm), moderate_large_phrase,
          ΕΚΤΟΣ αν ισχύει κάποιο από τα (α)/(β)/(γ)
      0 : όλα τα υπόλοιπα, ΚΑΙ borderline, slash_list, present_unspecified,
          small, small_phrase
    (α) «<X», «μικρότερη των / κάτω από X»  → τιμή < X  → μετράει μόνο αν X > 10
    (β) «ως / έως / μέχρι X», «≤X» (άνω όριο) → μετράει μόνο αν X > 10
        (απλός αριθμός χωρίς προσδιοριστικό: ≥ 10 mm, ESC)
    (γ) ρητό «μικρή / ελάχιστη / μικρού βαθμού / ήπια» στην ίδια πηγή → 0,
        ό,τι κι αν γράφει ο αριθμός
  Εγγυάται label_mod_severe ≤ label (υποσύνολο του any-size).
  Νέα flags (δεν αλλάζουν κανένα label):
      mixed_severity                     ίδια πηγή: ένδειξη small ΚΑΙ moderate+
                                         (π.χ. «μέτρια συλλογή 8 mm» → small)
      severity_conflict_between_sources  δύο πηγές θετικές (any-size) αλλά
                                         διαφωνούν στο moderate+
      modsev_excluded_qualifier          moderate+ = 0 λόγω (α)/(β)
      modsev_excluded_small_phrase       moderate+ = 0 λόγω (γ)
  Στο Evidence ο κανόνας γράφεται π.χ. numeric:moderate[upto] / [lt].

ΣΕΙΡΑ ΕΛΕΓΧΩΝ
  1. Masking (από v5· διορθωμένο μόνο το mask λίπους ώστε να πιάνει
     περι/επι/υποκαρδιακό λίπος σε όλες τις πτώσεις)
  2. Ίχνος                   → 0   (υπερισχύει και αριθμών)
  3. Απουσία συλλογής        → 0
  4. Numeric path            → trivial 0 / small·moderate·large 1
  5. Phrase path (χωρίς αριθμούς):
       A1 borderline → 1
       A2 slash list → 1
       B  μικρή/ήπια/ελάχιστη/αμελητέα/ασήμαντη → 1  (με negation guard)
       C  μέτρια/μεγάλη/σοβαρή/σημαντική      → 1  (με negation guard)
       D  ΝΕΟ: σκέτο «συλλογή»                → 1  (με negation guard)
  6. Τίποτα από τα παραπάνω → 0

ΠΗΓΕΣ ΤΟΥ REPORT (τα βήματα 1–6 εφαρμόζονται σε κάθε πηγή ξεχωριστά)
  PERICARDIUM       section «Περικάρδιο» (ολόκληρο)
  PERICARDIUM_TAIL  ό,τι ακολουθεί «συμπέρασμα/σχόλια/παρατηρήσεις» μέσα στο ίδιο section
  CONCLUSIONS       Συμπεράσματα
  COMMENTS          Σχόλια / Διάγνωση / Echo summary
  Στις 3 τελευταίες κρατιούνται ΜΟΝΟ οι προτάσεις που αναφέρουν περικάρδιο/συλλογή.
  Συνδυασμός:
    a. Ίχνος σε ΟΠΟΙΑΔΗΠΟΤΕ πηγή → 0 (τέλος)
    b. Αλλιώς αποφασίζει το «Περικάρδιο» αν δίνει σαφή απάντηση (Απόφαση Α)·
       αν όχι, η πρώτη πηγή με σαφή απάντηση (TAIL → CONCLUSIONS → COMMENTS)
    c. Διαφωνία μεταξύ πηγών → flag conflict_between_sources (δεν αλλάζει το label)

ΑΛΛΑΓΕΣ v6x2 (σε σχέση με v6x)
  - Mask πλευριτικής: πλευριτικ\w*\s+συλλογ\w* (όλες οι καταλήξεις)
  - Νέο pattern απουσίας absent[4]: «δεν προκύπτουν/υπάρχει/ανευρίσκεται/
    διαπιστώνεται ... (περικαρδιακή) συλλογή»

Τα regex του v5 είναι ΑΥΤΟΥΣΙΑ. Το mild_pat του v5 χωρίστηκε στα alternation
branches του (κείμενο αμετάβλητο) σε PE_SMALL / PE_TRACE / PE_ABSENT.
Το μόνο νέο pattern είναι το PE_BARE (βήμα D).

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση (label, grade, max_mm, label_v5,
             changed_vs_v5, flags, κείμενο περικαρδίου)
  Evidence : μία γραμμή ανά κανόνα/μέτρηση που ταίριαξε
             (βήμα, κανόνας, φράση, τιμή mm, αν καθόρισε το label, context)

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
logger = logging.getLogger("pericardial_effusion")


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
# v5 — ΑΥΤΟΥΣΙΑ η αρχική συνάρτηση (μόνο για σύγκριση label_v5 / changed_vs_v5)
# =============================================================================

def get_pericardial_effusion_v5(sections: dict) -> int:
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


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v5 (μην τα επεξεργαστείς εδώ)
# =============================================================================

# STEP 1 — Masking (v5, ίδια σειρά). Tuple: (pattern, replacement)
PE_SECTION_CUT = r'\b(?:συμπ[εέ]ρασμα(?:τα)?|σχ[όο]λια|παρατηρ[ήη]σει[σς])\b'
PE_MASKS = [
    # ΔΙΟΡΘΩΣΗ (v6x2): πλευριτικ[ήηέεςσ] → πλευριτικ\w* (όλες οι καταλήξεις/πτώσεις)
    (r'πλευριτικ\w*[^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)', '[PLEURAL_MASK]'),
    # ΔΙΟΡΘΩΣΗ (v6x): το v5 είχε (?:περικαρδιακ|επι|υπο)καρδιακ[οό] → δεν έπιανε ποτέ
    # το «περικαρδιακό λίπος». Πλέον: περι/επι/υποκαρδιακό + όλες οι πτώσεις
    # (λίπος / λίπους, περικαρδιακό / περικαρδιακού).
    (r'(?:περι|επι|υπο)καρδιακ\w*\s+λ[ίι]π\w*[^.]{0,40}?(?:\d+[.,]\d+|\d+)\s*(?:mm|cm)', '[FAT_MASK]'),
    # ΔΙΟΡΘΩΣΗ (v6x2): το v5 επέτρεπε ΕΝΑ γράμμα κατάληξης → δεν έπιανε
    # «πλευριτικής συλλογής», «πλευριτικές συλλογές» κ.λπ.
    (r'πλευριτικ\w*\s+συλλογ\w*', '[PLEURAL]'),
    (r'(?:περι|επι|υπο)καρδιακ\w*\s+λ[ίι]π\w*', '[FAT]'),
]

# Numeric (v5)
PE_NUMERIC = r'(\d+(?:[.,]\d+)?)\s*(?:-\s*(\d+(?:[.,]\d+)?)\s*)?(mm|cm)\b'

# A1 — borderline (v5 borderline_pat)
PE_BORDERLINE = (
    r'(?:μικρ[οόύη]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)'
    r'|οριακ[άαήη]\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεγ[άα]λ\w*|σοβαρ\w*)'
)

# A2 — slash list (v5 slash_moderate_pat + τα δύο συνοδευτικά checks)
PE_SLASH = (
    r'(?:μικρ\w+|μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)'
    r'\s*/\s*'
    r'(?:μικρ\w+|μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)'
)
PE_SLASH_SYLLOGI = r'συλλογ[ήη]'
PE_SLASH_MODPLUS = r'(?:μεσα[ίι]ου\s+μεγ[έε]θους|ευμεγ[έε]θ\w*|μετρ[ίι]\w*|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)'

# v5 mild_pat χωρισμένο στα alternation branches του. Σχόλιο [i] = θέση στο mild_pat.
# B — μικρή / ήπια / ελάχιστη / αμελητέα / ασήμαντη  (ΠΛΕΟΝ → 1)
PE_SMALL = [
    r'(?:μικρ[ήη]|μικρ[ήη][σς]\s+μεγ[έε]θους|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ\w+|αμελητ[έε]|ασ[ήη]μαντ\w+)'
    r'(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]',                       # [0]
    r'(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]\s+(?:\w+\s+){0,3}'
    r'(?:μικρ[ήη]|μικρ[ήη][σς]\s+μεγ[έε]θους|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ\w+|ασ[ήη]μαντ\w+)'
    r'(?:\s+βαθμο[ύυ])?',                                                                          # [1]
]
# Ίχνος / ίχνη  (→ 0, ελέγχεται ΠΡΩΤΟ)
PE_TRACE = [
    r'[ίι]χν\w+\s+(?:περικαρδιακ\w*\s+)?(?:συλλογ\w+|υγρ\w+)',                                      # [2]
    r'[ίι]χνο[σς]\s+(?:περικαρδιακο[ύυ]\s+υγρο[ύυ]|υγρο[ύυ]|συλλογ[ήη][σς]?)',                      # [3]
]
# Απουσία συλλογής  (→ 0, ελέγχεται ΔΕΥΤΕΡΟ)
PE_ABSENT = [
    r'ελε[ύυ]θερο',                                                                                # [4]
    r'χωρ[ίι][σς]\s+(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]',                                            # [5]
    r'δεν\s+(?:παρατηρε[ίι]ται|απεικον[ίι]ζεται)\s+(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]',             # [6]
    r'απουσ[ίι]α\s+συλλογ[ήη]',                                                                    # [7]
    # ΝΕΟ (v6x2): «δεν προκύπτουν στοιχεία συνηγορούντα υπέρ περικαρδιακής συλλογής»,
    # «δεν υπάρχει περικαρδιακή συλλογή», «δεν ανευρίσκεται / διαπιστώνεται συλλογή»
    r'δεν\s+(?:προκυπτ\w+|υπαρχ\w+|ανευρισκ\w+|διαπιστων\w+)\s+(?:\w+\s+){0,4}(?:περικαρδιακ\w*\s+)?συλλογ',  # [8]
]

# C — μέτρια / μεγάλη / σοβαρή / σημαντική (v5 pos_pat)
PE_POSITIVE = (
    r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου\s+μεγ[έε]θους|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*|ευμεγ[έε]θ\w*)'
    r'(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]'
    r'|(?:περικαρδιακ[ήη]\s+)?συλλογ[ήη]\s+(?:\w+\s+){0,3}'
    r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*|ευμεγ[έε]θ\w*)'
)

# Negation guard (v5, αυτούσιο)
PE_NEGATION = (
    r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται|υπ[άα]ρχει)|απουσ[ίι]α)'
    r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|μεσα[ίι]ου|μεγ[άα]λ\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*συλλογ[ήη]'
)

# ── ΝΕΟ PATTERN (το μόνο που προστέθηκε) ─────────────────────────────────────
# D — σκέτο «(περικαρδιακή) συλλογή» χωρίς μέγεθος/αριθμό.
# Αγνοείται αν μέσα στους 20 προηγούμενους χαρακτήρες υπάρχει «πλευριτ»
# (το mask [PLEURAL] του v5 πιάνει μόνο ονομαστική ενικού, όχι γενική/πληθυντικό).
PE_BARE = r'(?:περικαρδιακ\w*\s+)?συλλογ\w*'
PE_BARE_PLEURAL_LOOKBACK = 20

# ── GUARD για absent[0] «ελε[ύυ]θερο» (το regex μένει αυτούσιο) ─────────────────
# Το match ΑΓΝΟΕΙΤΑΙ όταν:
#   (α) ακολουθεί γράμμα → άλλη λέξη/πτώση (ελεύθερου, ελεύθερος, ελεύθερη …)
#   (β) ακολουθεί «τοίχωμα» → ανατομικός όρος (ελεύθερο τοίχωμα = free wall)
# π.χ. «πέριξ του ελεύθερου τοιχώματος της ΑΚ» ΔΕΝ σημαίνει ελεύθερο περικάρδιο.
PE_ELEFTHERO_GUARD = r'^(?:\w|\s+τοιχωμ)'


def _absent_match(t: str):
    """Όπως _first_match(PE_ABSENT, t), αλλά το absent[0] περνάει από το PE_ELEFTHERO_GUARD."""
    for i, pat in enumerate(PE_ABSENT):
        for m in re.finditer(pat, t):
            if i == 0 and re.match(PE_ELEFTHERO_GUARD, t[m.end():]):
                continue
            return i, m
    return None, None

# Διαγνωστικό (ΔΕΝ επηρεάζει το label): αναφορά σε λίπος που ΔΕΝ καλύφθηκε από το mask
# (π.χ. σκέτο «λίπος 5 mm» χωρίς περι/επι/υπο-καρδιακό) → έλεγχος στο Excel
PE_FAT_UNMASKED = r'\bλ[ίι]π(?:ος|ους|ωδ)\w*'


# =============================================================================
# ΚΛΙΜΑΚΑ ΜΕΓΕΘΟΥΣ & GRADES
# =============================================================================

def size_category(mm: float) -> str:
    """Trivial = 0 | Small < 10 | Moderate 10–20 | Large > 20 (mm)."""
    if mm <= 0:
        return 'trivial'
    if mm < 10:
        return 'small'
    if mm <= 20:
        return 'moderate'
    return 'large'


POSITIVE_GRADES = {'small', 'moderate', 'large',                 # numeric
                   'borderline', 'slash_list', 'small_phrase',    # phrase
                   'moderate_large_phrase', 'present_unspecified'}
NEGATIVE_GRADES = {'trace', 'absent', 'trivial', 'negated', 'no_mention', 'no_section'}

# Moderate or severe (label_mod_severe). Υποσύνολο του POSITIVE_GRADES.
# borderline / slash_list / present_unspecified → 0 (απόφαση χρήστη).
# Τα grades αυτά είναι ΑΝΑΓΚΑΙΑ αλλά όχι ΙΚΑΝΑ: βλ. (α)/(β)/(γ) στο _grade_text.
MOD_SEVERE_GRADES = {'moderate', 'large', 'moderate_large_phrase'}
assert MOD_SEVERE_GRADES <= POSITIVE_GRADES

# Προσδιοριστικό ΑΜΕΣΩΣ πριν από τον αριθμό (κείμενο normalize()-αρισμένο, χωρίς τόνους)
#   lt   : «<10 mm», «μικρότερη των / κάτω από 10 mm»     → τιμή < X
#   upto : «ως / έως / μέχρι 10 mm», «≤10 mm»            → τιμή ≤ X (άνω όριο)
PE_QUAL_LT   = r'(?:<|μικροτερ\w*\s+(?:των|απο)|κατω\s+(?:των|απο))\s*$'
PE_QUAL_UPTO = r'(?:\b(?:ως|εως|μεχρι)|≤|=<)\s*$'
PE_QUAL_LOOKBACK = 25
MOD_SEVERE_MM = 10   # ESC: moderate 10–20 mm


def _numeric_qualifier(t: str, pos: int) -> str:
    before = t[max(0, pos - PE_QUAL_LOOKBACK): pos]
    if re.search(PE_QUAL_LT, before):
        return 'lt'
    if re.search(PE_QUAL_UPTO, before):
        return 'upto'
    return ''


def _numeric_is_mod_severe(rec: dict) -> bool:
    """Απλός αριθμός: ≥ 10 mm. Με «<» ή «ως/έως/μέχρι» (άνω όριο): μόνο αν X > 10 mm."""
    v = rec['value_mm']
    return v > MOD_SEVERE_MM if rec.get('qualifier') else v >= MOD_SEVERE_MM


# =============================================================================
# CORE LOGIC
# =============================================================================

def _first_match(patterns, text):
    for i, pat in enumerate(patterns):
        m = re.search(pat, text)
        if m:
            return i, m
    return None, None


def _context(text: str, m, before=40, after=20) -> str:
    return text[max(0, m.start() - before): m.end() + after]


# =============================================================================
# ΠΗΓΕΣ ΤΟΥ REPORT
# =============================================================================
# Σειρά προτεραιότητας (Απόφαση Α): το section «Περικάρδιο» αποφασίζει αν δίνει
# σαφή απάντηση· οι υπόλοιπες πηγές χρησιμοποιούνται μόνο ως fallback, με αυτή τη σειρά.
#   PERICARDIUM       : το section «Περικάρδιο» (ολόκληρο, όπως στο v5)
#   PERICARDIUM_TAIL  : ό,τι ακολουθεί μέσα στο ίδιο section μετά από
#                       «συμπέρασμα / σχόλια / παρατηρήσεις» (στο v5 πεταγόταν)
#   CONCLUSIONS       : Συμπεράσματα
#   COMMENTS          : Σχόλια / Διάγνωση / Echo summary
# Το ΙΧΝΟΣ σε ΟΠΟΙΑΔΗΠΟΤΕ πηγή → label 0 και η απόφαση τελειώνει εκεί.
SOURCE_ORDER = ['PERICARDIUM', 'PERICARDIUM_TAIL', 'CONCLUSIONS', 'COMMENTS']

# Για τις πηγές εκτός «Περικάρδιο» κρατάμε ΜΟΝΟ προτάσεις που αναφέρουν
# περικάρδιο ή συλλογή (μετά το masking), ώστε άσχετοι αριθμοί (π.χ. «ρίζα αορτής
# 38 mm») και άσχετο «ελεύθερο» να μην μπαίνουν στους κανόνες.
PE_SENTENCE_SPLIT = r'\.(?!\d)|;'          # τελεία (όχι δεκαδική) ή ελληνικό ερωτηματικό
PE_SENTENCE_KEEP  = r'περικαρδ|συλλογ'


def _mask(t: str) -> str:
    for pat, rep in PE_MASKS:
        t = re.sub(pat, rep, t)
    return t


def _relevant_sentences(t_masked: str) -> str:
    sents = [s.strip() for s in re.split(PE_SENTENCE_SPLIT, t_masked)]
    keep = [s for s in sents if s and re.search(PE_SENTENCE_KEEP, s)]
    return '. '.join(keep) + '.' if keep else ''


def build_sources(sections: dict) -> dict:
    """Επιστρέφει {source: (masked_text, raw_text)} μόνο για τις πηγές που υπάρχουν."""
    out = {}
    raw_p = get_sec(sections, 'PERICARDIUM')
    t = normalize(raw_p)
    if t:
        parts = re.split(PE_SECTION_CUT, t)
        out['PERICARDIUM'] = (_mask(parts[0]), raw_p)
        if len(parts) > 1:
            tail = _relevant_sentences(_mask(' '.join(parts[1:])))
            if tail:
                out['PERICARDIUM_TAIL'] = (tail, raw_p)
    for key in ('CONCLUSIONS', 'COMMENTS'):
        raw = get_sec(sections, key)
        if normalize(raw):
            txt = _relevant_sentences(_mask(normalize(raw)))
            if txt:
                out[key] = (txt, raw)
    return out


def clean_pericardium_text(raw: str) -> str:
    """normalize → αποκοπή συμπερασμάτων/σχολίων → masking (για το section «Περικάρδιο»)."""
    return _mask(re.split(PE_SECTION_CUT, normalize(raw))[0])


def _grade_text(t: str) -> dict:
    """
    Εφαρμόζει τους κανόνες σε ΕΝΑ (ήδη masked) κείμενο.
    Κάθε probe τρέχει πάντα (για το Evidence sheet)· η απόφαση ακολουθεί τη σειρά
    trace → absent → numeric → borderline → slash → small → positive → bare.
    """
    matches = []

    def add(step, rule, m, value_mm=''):
        rec = {'step': step, 'rule': rule, 'match': m.group(), 'value_mm': value_mm,
               'context': _context(t, m)}
        matches.append(rec)
        return rec

    # ── Probes ────────────────────────────────────────────────────────────
    i, m = _first_match(PE_TRACE, t)
    trace = add('1_trace', f'trace[{i}]', m) if m else None

    i, m = _absent_match(t)
    absent = add('2_absent', f'absent[{i}]', m) if m else None

    numeric = []
    for m in re.finditer(PE_NUMERIC, t, re.I):
        v1 = float(m.group(1).replace(',', '.'))
        v2 = float(m.group(2).replace(',', '.')) if m.group(2) else v1
        val = max(v1, v2)
        if m.group(3).lower() == 'cm':
            val *= 10
        qual = _numeric_qualifier(t, m.start())
        rec = add('3_numeric', f'numeric:{size_category(val)}' + (f'[{qual}]' if qual else ''),
                  m, round(val, 2))
        rec['qualifier'] = qual
        numeric.append(rec)
    max_rec = max(numeric, key=lambda r: r['value_mm']) if numeric else None

    m = re.search(PE_BORDERLINE, t)
    borderline = add('4a_borderline', 'borderline', m) if m else None

    slash = None
    m = re.search(PE_SLASH, t)
    if m and re.search(PE_SLASH_SYLLOGI, t) and re.search(PE_SLASH_MODPLUS, t):
        slash = add('4b_slash', 'slash_list', m)

    i, m = _first_match(PE_SMALL, t)
    small = add('4c_small', f'small[{i}]', m) if m else None

    m = re.search(PE_POSITIVE, t)
    positive = add('4d_positive', 'moderate_large', m) if m else None

    bare = None
    for m in re.finditer(PE_BARE, t):
        if 'πλευριτ' in t[max(0, m.start() - PE_BARE_PLEURAL_LOOKBACK): m.start()]:
            continue
        bare = add('4e_bare', 'bare_syllogi', m)
        break

    m = re.search(PE_NEGATION, t)
    negation = add('neg_guard', 'negation_guard', m) if m else None

    # ── Απόφαση ──────────────────────────────────────────────────────────
    if trace:
        grade, decisive = 'trace', trace
    elif absent:
        grade, decisive = 'absent', absent
    elif max_rec:
        grade, decisive = size_category(max_rec['value_mm']), max_rec
    elif borderline:
        grade, decisive = 'borderline', borderline
    elif slash:
        grade, decisive = 'slash_list', slash
    elif small:
        grade, decisive = ('negated', negation) if negation else ('small_phrase', small)
    elif positive:
        grade, decisive = ('negated', negation) if negation else ('moderate_large_phrase', positive)
    elif bare:
        grade, decisive = ('negated', negation) if negation else ('present_unspecified', bare)
    else:
        grade, decisive = 'no_mention', None

    # ── Flags για review (δεν αλλάζουν το label) ─────────────────────────
    flags = []
    pos_evidence = any([borderline, slash, small, positive]) or \
        any(r['value_mm'] > 0 for r in numeric)
    if (trace or absent) and pos_evidence:
        flags.append('conflict_neg_vs_pos')
    if re.search(PE_FAT_UNMASKED, t):
        flags.append('fat_unmasked')
    if len(numeric) > 1:
        flags.append('multiple_numbers')
    small_ev = bool(small) or any(0 < r['value_mm'] < 10 for r in numeric)
    modplus_ev = bool(positive) or any(r['value_mm'] >= 10 for r in numeric)
    if small_ev and modplus_ev:
        flags.append('mixed_severity')

    # ── Moderate or severe (label_mod_severe) ────────────────────────────
    # Το grade ΔΕΝ αλλάζει (άρα ούτε το any-size label)· εδώ αποφασίζεται μόνο
    # αν το θετικό grade μετράει και ως moderate+.
    mod_severe, mod_excluded = 0, ''
    if grade in ('moderate', 'large'):
        # (α)/(β): αριθμός με «<» ή «ως/έως/μέχρι» μετράει μόνο αν X > 10 mm
        if any(_numeric_is_mod_severe(r) for r in numeric):
            mod_severe = 1
        else:
            mod_excluded = 'modsev_excluded_qualifier'
    elif grade == 'moderate_large_phrase':
        mod_severe = 1
    # (γ): ρητό «μικρή/ελάχιστη/μικρού βαθμού» στην ίδια πηγή → 0
    if mod_severe and small:
        mod_severe, mod_excluded = 0, 'modsev_excluded_small_phrase'

    for rec in matches:
        rec['decisive'] = int(rec is decisive)

    return {
        'grade':    grade,
        'decisive': decisive,
        'max_mm':   max_rec['value_mm'] if max_rec else '',
        'flags':    flags,
        'matches':  matches,
        'mod_severe':   mod_severe,
        'mod_excluded': mod_excluded,
    }


def grade_pericardial_effusion(sections: dict) -> dict:
    """
    Συνδυάζει τις πηγές:
      1. Ίχνος σε ΟΠΟΙΑΔΗΠΟΤΕ πηγή → 0 (τέλος).
      2. Αλλιώς η ΠΡΩΤΗ πηγή (κατά SOURCE_ORDER) με σαφή απάντηση (grade ≠ no_mention).
      3. Αλλιώς no_mention (ή no_section αν δεν υπάρχει καμία πηγή).
    Επιστρέφει dict με: label, label_mod_severe, grade, decisive_source, rule, match, max_mm, flags,
    source_grades, matches(list με key 'source'), raw (κείμενο της αποφασιστικής πηγής).
    """
    out = {'label': 0, 'label_mod_severe': 0, 'grade': 'no_section', 'decisive_source': '', 'rule': '',
           'match': '', 'max_mm': '', 'flags': '', 'source_grades': '',
           'matches': [], 'raw': get_sec(sections, 'PERICARDIUM')}

    srcs = build_sources(sections)
    if not srcs:
        return out

    per = {}
    for src in SOURCE_ORDER:
        if src not in srcs:
            continue
        text, raw = srcs[src]
        r = _grade_text(text)
        r['raw'] = raw
        for m in r['matches']:
            m['source'], m['raw'] = src, raw
        per[src] = r

    # 1. Ίχνος οπουδήποτε
    chosen = next((s for s in SOURCE_ORDER if s in per and per[s]['grade'] == 'trace'), None)
    # 2. Πρώτη πηγή με σαφή απάντηση (Απόφαση Α)
    if chosen is None:
        chosen = next((s for s in SOURCE_ORDER if s in per and per[s]['grade'] != 'no_mention'), None)

    flags, matches = [], []
    for src, r in per.items():
        if src != chosen:
            for m in r['matches']:
                m['decisive'] = 0
        matches.extend(r['matches'])
        for f in r['flags']:
            if f not in flags:
                flags.append(f)

    if chosen is None:
        grade, r = 'no_mention', None
    else:
        r = per[chosen]
        grade = r['grade']
        label = 1 if grade in POSITIVE_GRADES else 0
        others = [1 if per[s]['grade'] in POSITIVE_GRADES else 0
                  for s in per if s != chosen and per[s]['grade'] != 'no_mention']
        if any(o != label for o in others):
            flags.append('conflict_between_sources')
        # Σοβαρότητα: μόνο ανάμεσα σε πηγές που είναι ΚΑΙ οι δύο θετικές (any-size)
        if label == 1:
            others_mod = [per[s]['mod_severe']
                          for s in per if s != chosen and per[s]['grade'] in POSITIVE_GRADES]
            if any(o != r['mod_severe'] for o in others_mod):
                flags.append('severity_conflict_between_sources')
        if r['mod_excluded']:
            flags.append(r['mod_excluded'])

    dec = r['decisive'] if r else None
    out.update({
        'label':           1 if grade in POSITIVE_GRADES else 0,
        'label_mod_severe': r['mod_severe'] if r else 0,
        'grade':           grade,
        'decisive_source': chosen or '',
        'rule':            dec['rule'] if dec else '',
        'match':           dec['match'] if dec else '',
        'max_mm':          r['max_mm'] if r else '',
        'flags':           ';'.join(flags),
        'source_grades':   ' | '.join(f"{s}:{per[s]['grade']}" for s in per),
        'matches':         matches,
        'raw':             r['raw'] if r else out['raw'],
    })
    return out


def get_pericardial_effusion_v6x(sections: dict) -> int:
    """Drop-in αντικατάσταση της get_pericardial_effusion (ίδιο signature)."""
    return grade_pericardial_effusion(sections)['label']


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
# ΑΝΑΓΝΩΣΗ REPORTS (HTML ή CHM)  — ίδιο με rv_systolic_v6x
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
    chg_font    = Font(bold=True, color='C00000')

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
    cols1 = ['exam_id', 'pericardial_effusion', 'pericardial_effusion_mod_severe', 'grade',
             'decisive_source', 'max_mm',
             'decisive_rule', 'decisive_phrase', 'label_v5', 'changed_vs_v5', 'flags',
             'source_grades', 'status', 'pericardium_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 12, 14, 22, 18, 9, 18, 34, 9, 12, 30, 50, 22, 80, 60],
               wrap_cols=('pericardium_text', 'source_grades'))
    i_chg = cols1.index('changed_vs_v5')
    for row in ws1.iter_rows(min_row=2):
        if row[1].value == 1:
            for c in row:
                c.fill = pos_fill
        if row[i_chg].value == 1:
            row[i_chg].font = chg_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'source', 'step', 'rule', 'matched_phrase', 'value_mm', 'decisive', 'context']
    fill_sheet(ws2, cols2, evidence_rows, [18, 18, 14, 18, 40, 10, 10, 80], wrap_cols=('context',))
    i_dec, i_ph = cols2.index('decisive'), cols2.index('matched_phrase')
    for row in ws2.iter_rows(min_row=2):
        if row[i_dec].value == 1:
            row[i_ph].font = chg_font

    wb.save(path)


# =============================================================================
# SELF-TEST (synthetic περιπτώσεις — τρέχει πριν το batch)
# =============================================================================

SELF_TESTS = [
    # (κείμενο section Περικάρδιο, αναμενόμενο label, αναμενόμενο grade, known_issue)
    ('Ίχνος περικαρδιακής συλλογής.',                      0, 'trace',                 False),
    ('Ίχνος συλλογής 2 mm.',                               0, 'trace',                 False),
    ('Ελεύθερο.',                                          0, 'absent',                False),
    ('Χωρίς περικαρδιακή συλλογή.',                        0, 'absent',                False),
    ('Δεν παρατηρείται συλλογή.',                          0, 'absent',                False),
    ('Δεν εμφανίζει περικαρδιακή συλλογή.',                0, 'negated',               False),
    ('Περικαρδιακή συλλογή 0 mm.',                         0, 'trivial',               False),
    ('Περικαρδιακή συλλογή 6 mm.',                         1, 'small',                 False),
    ('Συλλογή 12 mm πίσω από την ΑΚ.',                     1, 'moderate',              False),
    ('Περικαρδιακή συλλογή 2,5 cm.',                       1, 'large',                 False),
    ('Συλλογή 8-14 mm.',                                   1, 'moderate',              False),
    ('Μικρή περικαρδιακή συλλογή.',                        1, 'small_phrase',          False),
    ('Ελάχιστη περικαρδιακή συλλογή.',                     1, 'small_phrase',          False),
    ('Συλλογή μικρού βαθμού.',                             1, 'small_phrase',          False),
    ('Μέτρια περικαρδιακή συλλογή.',                       1, 'moderate_large_phrase', False),
    ('Μικρή προς μέτρια συλλογή.',                         1, 'borderline',            False),
    ('Μικρής/μεσαίου μεγέθους συλλογή.',                   1, 'slash_list',            False),
    ('Περικαρδιακή συλλογή.',                              1, 'present_unspecified',   False),
    ('Πλευριτική συλλογή αριστερά.',                       0, 'no_mention',            False),
    ('Πλευριτικής συλλογής αριστερά.',                     0, 'no_mention',            False),
    ('Πλευριτική συλλογή 15 mm.',                          0, 'no_mention',            False),
    ('Επικαρδιακό λίπος 6 mm.',                            0, 'no_mention',            False),
    ('Περικαρδιακό λίπος 6 mm.',                           0, 'no_mention',            False),
    ('Περικαρδιακό λίπος.',                                0, 'no_mention',            False),
    ('Παρουσία περικαρδιακού λίπους 8 mm.',                0, 'no_mention',            False),
    ('Υποκαρδιακό λίπος 3 mm.',                            0, 'no_mention',            False),
    ('Περικαρδιακό λίπος 5 mm. Συλλογή 7 mm.',             1, 'small',                 False),
    ('Επικαρδιακό λίπος. Μικρή περικαρδιακή συλλογή.',     1, 'small_phrase',          False),
]

# Πολλαπλές πηγές: (sections dict, label, grade, αναμενόμενη αποφασιστική πηγή)
SELF_TESTS_MULTI = [
    # Απόφαση Α: το «Περικάρδιο» έχει σαφή απάντηση → κερδίζει (με conflict flag)
    ({'PERICARDIUM': 'Ελεύθερο.', 'CONCLUSIONS': 'Μικρή περικαρδιακή συλλογή.'},
     0, 'absent', 'PERICARDIUM'),
    # Fallback: «Περικάρδιο» χωρίς αναφορά → Συμπεράσματα
    ({'PERICARDIUM': 'Περικαρδιακό λίπος.', 'CONCLUSIONS': 'Περικαρδιακή συλλογή 12 mm.'},
     1, 'moderate', 'CONCLUSIONS'),
    # Χωρίς section «Περικάρδιο» → Συμπεράσματα· ο αριθμός της ρίζας ΔΕΝ μετράει
    ({'CONCLUSIONS': 'Περικαρδιακή συλλογή 8 mm. Ρίζα αορτής 38 mm.'},
     1, 'small', 'CONCLUSIONS'),
    ({'CONCLUSIONS': 'Περικαρδιακή συλλογή 1.2 cm.'},
     1, 'moderate', 'CONCLUSIONS'),
    ({'COMMENTS': 'Διάγνωση: Περικαρδιακή συλλογή.'},
     1, 'present_unspecified', 'COMMENTS'),
    # Ίχνος οπουδήποτε → 0, ακόμα κι αν το «Περικάρδιο» δίνει αριθμό
    ({'PERICARDIUM': 'Συλλογή 5 mm.', 'CONCLUSIONS': 'Ίχνος περικαρδιακής συλλογής.'},
     0, 'trace', 'CONCLUSIONS'),
    # Tail μέσα στο section: «Περικάρδιο» χωρίς αναφορά, μετά «Συμπέρασμα: ...»
    ({'PERICARDIUM': 'Κ.Φ. Συμπέρασμα: μέτρια περικαρδιακή συλλογή.'},
     1, 'moderate_large_phrase', 'PERICARDIUM_TAIL'),
    # Άσχετα Συμπεράσματα → καμία πηγή
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς. Ρίζα αορτής 40 mm.'},
     0, 'no_section', ''),
    ({'CONCLUSIONS': 'Πλευριτική συλλογή 20 mm.'},
     0, 'no_section', ''),
    ({'CONCLUSIONS': 'Αμφοτερόπλευρη πλευριτικής συλλογής. Ελεύθερο περικάρδιο.'},
     0, 'absent', 'CONCLUSIONS'),
    # Guard «ελεύθερο»: ανατομικός όρος ελεύθερο(υ) τοίχωμα ΔΕΝ είναι απουσία
    ({'PERICARDIUM': '.:Παρουσία μικρής περικαρδιακής συλλογής με εντόπιση αντίστοιχα '
                     'πέριξ του ελεύθερου τοιχώματος της αριστερής κοιλίας, χωρίς '
                     'αιμοδυναμικές επιπτώσεις, έως 0.6cm'},
     1, 'small', 'PERICARDIUM'),
    ({'CONCLUSIONS': 'Μικρή περικαρδιακή συλλογή πέριξ του ελεύθερου τοιχώματος της ΔΚ.'},
     1, 'small_phrase', 'CONCLUSIONS'),
    ({'PERICARDIUM': 'Συλλογή πίσω από το ελεύθερο τοίχωμα της ΔΚ.'},
     1, 'present_unspecified', 'PERICARDIUM'),
    ({'PERICARDIUM': 'Ελεύθερο περικάρδιο.'},
     0, 'absent', 'PERICARDIUM'),
    ({'PERICARDIUM': 'Περικάρδιο ελεύθερο.'},
     0, 'absent', 'PERICARDIUM'),
    # v6x2 — πλευριτική σε όλες τις πτώσεις + νέο pattern απουσίας
    ({'PERICARDIUM': 'Δεν προκύπτουν στοιχεία συνηγορούντα  υπερ περικαρδιακής συλλογής  '
                     'αλλά μόνο ελάχιστης πλευριτικής συλλογής.'},
     0, 'absent', 'PERICARDIUM'),
    ({'CONCLUSIONS': 'Δεν προκύπτουν στοιχεία συνηγορούντα υπέρ περικαρδιακής συλλογής.'},
     0, 'absent', 'CONCLUSIONS'),
    ({'PERICARDIUM': 'Δεν υπάρχει περικαρδιακή συλλογή.'},
     0, 'absent', 'PERICARDIUM'),
    ({'PERICARDIUM': 'Δεν ανευρίσκεται συλλογή.'},
     0, 'absent', 'PERICARDIUM'),
    ({'PERICARDIUM': 'Μικρής πλευριτικής συλλογής αριστερά.'},
     0, 'no_mention', ''),
    ({'PERICARDIUM': 'Ελάχιστης πλευριτικής συλλογής.'},
     0, 'no_mention', ''),
    ({'PERICARDIUM': 'Μέτριες πλευριτικές συλλογές αμφοτερόπλευρα.'},
     0, 'no_mention', ''),
    ({'PERICARDIUM': 'Πλευριτικής συλλογής 15 mm.'},
     0, 'no_mention', ''),
    ({'PERICARDIUM': 'Ελάχιστης πλευριτικής συλλογής. Μικρή περικαρδιακή συλλογή 5 mm.'},
     1, 'small', 'PERICARDIUM'),
    ({'PERICARDIUM': 'Δεν υπάρχουν ενδείξεις επιπωματισμού. Μικρή περικαρδιακή συλλογή.'},
     1, 'small_phrase', 'PERICARDIUM'),
]


# Moderate or severe: (sections, label any-size, label_mod_severe, grade,
#                      required_flags, forbidden_flags)
SELF_TESTS_MOD = [
    # numeric — όριο 10 mm
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 6 mm.'},    1, 0, 'small',    [], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 9.5 mm.'},  1, 0, 'small',    [], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 10 mm.'},   1, 1, 'moderate', [], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 20 mm.'},   1, 1, 'moderate', [], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 2,5 cm.'},  1, 1, 'large',    [], []),
    ({'PERICARDIUM': 'Συλλογή 8-14 mm.'},              1, 1, 'moderate', [], []),
    # phrase
    ({'PERICARDIUM': 'Μικρή περικαρδιακή συλλογή.'},   1, 0, 'small_phrase',          [], ['mixed_severity']),
    ({'PERICARDIUM': 'Μέτρια περικαρδιακή συλλογή.'},  1, 1, 'moderate_large_phrase', [], ['mixed_severity']),
    ({'PERICARDIUM': 'Μεγάλη περικαρδιακή συλλογή.'},  1, 1, 'moderate_large_phrase', [], []),
    # αποκλεισμένα από το moderate+ (απόφαση χρήστη)
    ({'PERICARDIUM': 'Μικρή προς μέτρια συλλογή.'},          1, 0, 'borderline',          [], []),
    ({'PERICARDIUM': 'Μικρής/μεσαίου μεγέθους συλλογή.'},    1, 0, 'slash_list',          [], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή.'},               1, 0, 'present_unspecified', [], []),
    # αρνητικά
    ({'PERICARDIUM': 'Ίχνος περικαρδιακής συλλογής.'}, 0, 0, 'trace',      [], []),
    ({'PERICARDIUM': 'Ελεύθερο.'},                     0, 0, 'absent',     [], []),
    ({'PERICARDIUM': 'Περικαρδιακό λίπος 15 mm.'},     0, 0, 'no_mention', [], []),
    ({'PERICARDIUM': 'Πλευριτικής συλλογής 15 mm.'},   0, 0, 'no_mention', [], []),
    # η μέτρηση υπερισχύει της φράσης → small, με flag
    ({'PERICARDIUM': 'Μέτρια περικαρδιακή συλλογή 8 mm.'}, 1, 0, 'small', ['mixed_severity'], []),
    # Απόφαση Α: αποφασίζει το «Περικάρδιο», η διαφωνία σοβαρότητας σημαίνεται
    ({'PERICARDIUM': 'Μικρή περικαρδιακή συλλογή.', 'CONCLUSIONS': 'Μέτρια περικαρδιακή συλλογή.'},
     1, 0, 'small_phrase', ['severity_conflict_between_sources'], ['conflict_between_sources']),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 12 mm.', 'CONCLUSIONS': 'Μέτρια περικαρδιακή συλλογή.'},
     1, 1, 'moderate', [], ['severity_conflict_between_sources']),
    # Αρνητικό «Περικάρδιο» + μέτρια στα Συμπεράσματα → 0/0 (υποσύνολο διατηρείται)
    ({'PERICARDIUM': 'Ελεύθερο.', 'CONCLUSIONS': 'Μέτρια περικαρδιακή συλλογή.'},
     0, 0, 'absent', ['conflict_between_sources'], ['severity_conflict_between_sources']),
    # Fallback στα Συμπεράσματα
    ({'CONCLUSIONS': 'Περικαρδιακή συλλογή 1.2 cm.'}, 1, 1, 'moderate', [], []),

    # ── (α) «<» / «μικρότερη των» → τιμή < X ─────────────────────────────
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή <10 mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή < 1 cm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή μικρότερη των 10 mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή κάτω από 10 mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή <15 mm.'},
     1, 1, 'moderate', [], ['modsev_excluded_qualifier']),
    # ── (β) «ως / έως / μέχρι X» → μόνο αν X > 10 ───────────────────────
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή ως 10mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή έως 1 cm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή μέχρι 10 mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή ≤10 mm.'},
     1, 0, 'moderate', ['modsev_excluded_qualifier'], []),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή ως 12 mm.'},
     1, 1, 'moderate', [], ['modsev_excluded_qualifier']),
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 8 έως 12 mm.'},
     1, 1, 'moderate', [], []),
    # απλός αριθμός 10 mm → moderate (ESC)
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 10mm.'},
     1, 1, 'moderate', [], ['modsev_excluded_qualifier']),
    # δύο αριθμοί: ο ένας με «ως 10», ο άλλος απλός 14 → μετράει ο απλός
    ({'PERICARDIUM': 'Συλλογή ως 10 mm προσθίως και 14 mm οπισθίως.'},
     1, 1, 'moderate', [], ['modsev_excluded_qualifier']),
    # ── (γ) ρητό «μικρή» → 0, ό,τι κι αν γράφει ο αριθμός ───────────────
    ({'PERICARDIUM': 'Μικρή περικαρδιακή συλλογή 12 mm.'},
     1, 0, 'moderate', ['modsev_excluded_small_phrase', 'mixed_severity'], []),
    ({'PERICARDIUM': 'Μικρή περικαρδιακή συλλογή ως 10mm.'},
     1, 0, 'moderate', ['mixed_severity'], []),
    ({'PERICARDIUM': 'Ελάχιστη περικαρδιακή συλλογή 2,5 cm.'},
     1, 0, 'large', ['modsev_excluded_small_phrase'], []),
    # δύο απλοί αριθμοί (5 και 15 mm), χωρίς «μικρή» → moderate+ (το (γ) θέλει ΦΡΑΣΗ)
    ({'PERICARDIUM': 'Συλλογή 5 mm προσθίως και 15 mm οπισθίως.'},
     1, 1, 'moderate', ['mixed_severity'], ['modsev_excluded_small_phrase']),
    # (γ) στην ΑΠΟΦΑΣΙΣΤΙΚΗ πηγή μόνο: «μικρή» στα Συμπεράσματα δεν επηρεάζει το Περικάρδιο
    ({'PERICARDIUM': 'Περικαρδιακή συλλογή 15 mm.', 'CONCLUSIONS': 'Μικρή περικαρδιακή συλλογή.'},
     1, 1, 'moderate', ['severity_conflict_between_sources'], ['modsev_excluded_small_phrase']),
]


def run_self_test() -> bool:
    ok_all = True
    logger.info("SELF-TEST (section «Περικάρδιο»)")
    for text, exp_label, exp_grade, known in SELF_TESTS:
        res = grade_pericardial_effusion({'PERICARDIUM': text})
        ok = (res['label'] == exp_label and res['grade'] == exp_grade)
        tag = 'PASS' if ok else ('KNOWN' if known else 'FAIL')
        if not ok and not known:
            ok_all = False
        logger.info(f"  [{tag:5}] {text:<42} → label={res['label']} grade={res['grade']}"
                    f"{'' if ok else f'  (αναμενόταν {exp_label}/{exp_grade})'}"
                    f"{'  flags=' + res['flags'] if res['flags'] else ''}")
    logger.info("SELF-TEST (πολλαπλές πηγές)")
    for secs, exp_label, exp_grade, exp_src in SELF_TESTS_MULTI:
        res = grade_pericardial_effusion(secs)
        ok = (res['label'] == exp_label and res['grade'] == exp_grade
              and res['decisive_source'] == exp_src)
        if not ok:
            ok_all = False
        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items())
        logger.info(f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
                    f"          → label={res['label']} grade={res['grade']} "
                    f"source={res['decisive_source'] or '-'}"
                    f"{'' if ok else f'  (αναμενόταν {exp_label}/{exp_grade}/{exp_src})'}"
                    f"{'  flags=' + res['flags'] if res['flags'] else ''}")
    logger.info("SELF-TEST (moderate or severe)")
    for secs, exp_any, exp_mod, exp_grade, req, forb in SELF_TESTS_MOD:
        res = grade_pericardial_effusion(secs)
        fl = [f for f in res['flags'].split(';') if f]
        missing = [f for f in req if f not in fl]
        present = [f for f in forb if f in fl]
        ok = (res['label'] == exp_any and res['label_mod_severe'] == exp_mod
              and res['grade'] == exp_grade and not missing and not present
              and res['label_mod_severe'] <= res['label'])
        if not ok:
            ok_all = False
        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items())
        logger.info(f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
                    f"          → any={res['label']} mod={res['label_mod_severe']} grade={res['grade']}"
                    f"{'' if ok else f'  (αναμενόταν {exp_any}/{exp_mod}/{exp_grade})'}"
                    f"{'  λείπουν=' + str(missing) if missing else ''}"
                    f"{'  δεν έπρεπε=' + str(present) if present else ''}"
                    f"{'  flags=' + res['flags'] if res['flags'] else ''}")
    logger.info(f"SELF-TEST: {'ΟΚ' if ok_all else 'ΑΠΕΤΥΧΕ'}")
    return ok_all


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
            label_rows.append({'exam_id': e['exam_id'], 'pericardial_effusion': '',
                               'grade': '', 'status': 'read_failed', 'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        res = grade_pericardial_effusion(sections)
        v5 = get_pericardial_effusion_v5(sections)
        status = 'ok' if get_sec(sections, 'PERICARDIUM') else 'no_PERICARDIUM_section'

        label_rows.append({'exam_id':              e['exam_id'],
                           'pericardial_effusion': res['label'],
                           'pericardial_effusion_mod_severe': res['label_mod_severe'],
                           'grade':                res['grade'],
                           'decisive_source':      res['decisive_source'],
                           'source_grades':        res['source_grades'],
                           'max_mm':               res['max_mm'],
                           'decisive_rule':        res['rule'],
                           'decisive_phrase':      original_phrase(res['raw'], res['match']),
                           'label_v5':             v5,
                           'changed_vs_v5':        int(v5 != res['label']),
                           'flags':                res['flags'],
                           'status':               status,
                           'pericardium_text':     get_sec(sections, 'PERICARDIUM'),
                           'report_path':          e['report_path']})

        for m in res['matches']:
            evidence_rows.append({
                'exam_id':        e['exam_id'],
                'source':         m['source'],
                'step':           m['step'],
                'rule':           m['rule'],
                'matched_phrase': original_phrase(m['raw'], m['match']),
                'value_mm':       m['value_mm'],
                'decisive':       m['decisive'],
                'context':        m['context'],
            })

    out = Path(output_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_excel(out, label_rows, evidence_rows)
    except PermissionError:
        logger.error(f"Το {out} είναι ανοιχτό στο Excel — κλείσ' το και ξανατρέξε.")
        return

    ok_rows = [r for r in label_rows if r['status'] != 'read_failed']
    n_pos   = sum(1 for r in ok_rows if r['pericardial_effusion'] == 1)
    n_v5    = sum(1 for r in ok_rows if r.get('label_v5') == 1)
    n_chg   = sum(1 for r in ok_rows if r.get('changed_vs_v5') == 1)
    logger.info("=" * 60)
    logger.info(f"Εξετάσεις: {len(label_rows)} | αναγνώστηκαν: {len(ok_rows)} | "
                f"αποτυχίες: {len(label_rows) - len(ok_rows)}")
    if ok_rows:
        n_mod = sum(1 for r in ok_rows if r.get('pericardial_effusion_mod_severe') == 1)
        logger.info(f"Θετικές v6x (label=1): {n_pos} ({100 * n_pos / len(ok_rows):.1f}%) | "
                    f"v5: {n_v5} | άλλαξαν: {n_chg}")
        logger.info(f"Moderate or severe: {n_mod} ({100 * n_mod / len(ok_rows):.1f}%)")
        grades = {}
        for r in ok_rows:
            grades[r['grade']] = grades.get(r['grade'], 0) + 1
        for g, n in sorted(grades.items(), key=lambda x: -x[1]):
            logger.info(f"  {g:<24} {n:>6}")
        srcs = {}
        for r in ok_rows:
            if r.get('decisive_source'):
                srcs[r['decisive_source']] = srcs.get(r['decisive_source'], 0) + 1
        logger.info("Αποφασιστική πηγή:")
        for s, n in sorted(srcs.items(), key=lambda x: -x[1]):
            logger.info(f"  {s:<24} {n:>6}")
    logger.info(f"Excel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/pericardial_effusion_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
