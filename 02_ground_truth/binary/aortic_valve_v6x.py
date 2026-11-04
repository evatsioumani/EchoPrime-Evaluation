r"""
aortic_valve_v6x.py
===================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για τα findings
της ΑΟΡΤΙΚΗΣ βαλβίδας:

  aortic_stenosis        (στένωση αορτικής)
  aortic_regurgitation   (ανεπάρκεια αορτικής)

Πρότυπο: mitral_valve_v6x.py. Η infrastructure (parsing, ανάγνωση reports,
Excel, run) είναι αυτούσια· αλλάζουν μόνο τα findings και η πηγή κειμένου.

Για ΚΑΘΕ finding παράγονται ΔΥΟ labels:

  ΑΝΑΛΥΣΗ STRICT   — <finding>
      Θετικά ΜΟΝΟ μέτριου/σοβαρού βαθμού. Ακριβώς η συμπεριφορά του v5.

  ΑΝΑΛΥΣΗ INCLUSIVE — <finding>_incl_mild
      Θετικά ΚΑΙ τα ήπια/μικρού βαθμού (mild + moderate + severe).
      Το ΙΧΝΟΣ δεν είναι ποτέ θετικό — ούτε εδώ.

ΒΑΣΙΚΗ ΑΡΧΗ ΥΛΟΠΟΙΗΣΗΣ
  Κανένα επιβεβαιωμένο regex του v5 δεν τροποποιήθηκε. Τα patterns αντιγράφηκαν
  ΑΥΤΟΥΣΙΑ ως σταθερές.

  aortic_stenosis: το mild guard του v5 είναι ΕΝΑ bidirectional regex χωρίς ίχνος
  → ΔΕΝ χρειάζεται split. Μένει ως μία σταθερά AS_MILD_PAT.

  aortic_regurgitation: το mild guard του v5 έχει τρία alternations
  (mild-forward | mild-reverse | ίχνος) → split σε τρεις σταθερές:

      AR_MILD_FWD | AR_MILD_REV | AR_TRACE   ==  το αρχικό mild_pat του v5

  (ελέγχεται χαρακτήρα-προς-χαρακτήρα στο self-test #0)

ΣΕΙΡΑ ΕΛΕΓΧΟΥ

  aortic_stenosis   (ΧΩΡΙΣ prosthetic guard — δεν υπάρχει στο v5)
    STRICT    : borderline → 1 | mild → 0 | positive → [negation → 0] → 1
    INCLUSIVE : borderline → 1 | mild → 1 | positive → [negation → 0] → 1

  aortic_regurgitation
    STRICT    : borderline → 1 | (mild Ή ίχνος) → 0 | positive → [negation → 0] → 1
    INCLUSIVE : borderline → 1 | mild → 1 | positive → [negation → 0] → 1 | ίχνος → 0

  Το negation guard εφαρμόζεται ΜΟΝΟ μετά τα positive, όπως στο v5, και στις δύο
  αναλύσεις. Όταν αποφασίζει, καταγράφεται στο Evidence ως rule 'negation_guard'.

  Τα «ελαφρά» / «ελάχιστη» είναι μέσα στα mild patterns του v5 → 0 / 1.
  Τα «ελαφριά», «ήπιου βαθμού», «αμελητέα» ΔΕΝ πιάνονται από τα v5 regex
  (κανένα regex δεν τροποποιήθηκε, όπως και στο mitral) → μένουν 0 / 0 και
  σημαδεύονται με flag *_mild_uncovered για manual έλεγχο.

ΠΗΓΗ ΚΕΙΜΕΝΟΥ — AV με fallback
  1. Αν υπάρχει (μη κενό) section AV → χρησιμοποιείται αυτούσιο, όπως στο v5.
  2. Αλλιώς Συμπεράσματα + Σχόλια/Διάγνωση, ανά πρόταση, μόνο προτάσεις με ρητή
     αναφορά στην αορτική (AORTIC_CTX), με clause φιλτράρισμα στις multi-valve.
  3. Αλλιώς «Imported Findings», με το ίδιο φιλτράρισμα.

  Το `\bav\b` ΔΕΝ είναι στο AORTIC_CTX: στην καρδιολογία σημαίνει συνήθως
  atrioventricular (AV block, AV node).

  Το `αορτ[ηή]` πιάνει και την αορτή ως αγγείο (ρίζα, ανιούσα, ισθμός, τόξο).
  Ο v5 δεν είχε αυτό το πρόβλημα, γιατί διάβαζε μόνο το section AV (τα κείμενα της
  αορτής πήγαιναν στο section AORTA με βάση τον header). Στο fallback δεν υπάρχουν
  headers, οπότε τέτοιες προτάσεις σημαδεύονται με aortic_ctx_nonvalve για manual
  έλεγχο — ΧΩΡΙΣ αλλαγή στο label.

  ΣΥΝΕΠΕΙΑ ΓΙΑ ΤΟ SANITY CHECK: η ταύτιση STRICT ↔ v5 απαιτείται ΜΟΝΟ στις
  εξετάσεις με source == 'AV'. Στα fallback rows κάθε διαφορά = fallback_gain.

ΣΚΟΠΟΣ
  Πρόχειρο check ορθότητας των ground truth labels, ΟΧΙ το τελικό CSV.

FLAGS (στήλη flags) — οι γραμμές με flag ΕΛΕΓΧΟΥ χρωματίζονται πορτοκαλί:
  as_incl_only / ar_incl_only      μόνο στην INCLUSIVE θετικό (χωρίς χρώμα)
  ar_trace                         εντοπίστηκε ίχνος (χωρίς χρώμα)
  fallback_source                  λείπει AV section → εναλλακτική πηγή
  imported_findings                η πηγή ήταν το «Imported Findings»
  fallback_gain                    το fallback έδωσε θετικό που το v5 έχανε
  multi_valve_sentence             πρόταση με >1 βαλβίδα → clause φιλτράρισμα  [ΕΛΕΓΧΟΣ]
  aortic_ctx_nonvalve              πρόταση fallback για την αορτή ως αγγείο    [ΕΛΕΓΧΟΣ]
  as_mild_suspect / ar_mild_suspect
                                   το mild match που έδωσε INCLUSIVE=1 περιέχει
                                   άρνηση ή το ουσιαστικό του άλλου finding
                                   (π.χ. «ήπια πάχυνση χωρίς στένωση»)        [ΕΛΕΓΧΟΣ]
  as_mild_uncovered / ar_mild_uncovered
                                   INCLUSIVE=0 αλλά υπάρχει mild όρος που τα v5
                                   regex δεν καλύπτουν (ελαφριά, ήπιου, αμελητέα,
                                   μικρής)                                    [ΕΛΕΓΧΟΣ]
  as_prosthetic_context / ar_prosthetic_context
                                   INCLUSIVE=1 σε report με TAVI/προσθετική
                                   (π.χ. παραβαλβιδική διαφυγή)               [ΕΛΕΓΧΟΣ]
  ar_strict_blocked                INCLUSIVE moderate/severe αλλά STRICT=0     [ΕΛΕΓΧΟΣ]
  strict_vs_v5_mismatch            η STRICT διαφέρει από το v5 — ΣΦΑΛΜΑ        [ΕΛΕΓΧΟΣ]
  non_monotonic                    STRICT=1 αλλά INCLUSIVE=0 — ΣΦΑΛΜΑ          [ΕΛΕΓΧΟΣ]

  Όλα τα flags είναι ΕΝΗΜΕΡΩΤΙΚΑ — κανένα δεν αλλάζει label.

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά pattern που ταίριαξε

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
logger = logging.getLogger("aortic")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από mitral_valve_v6x)
# =============================================================================

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
    # ΠΡΟΣΟΧΗ ΣΤΗ ΣΕΙΡΑ: το IMPORTED ΠΡΕΠΕΙ να προηγείται του FINDINGS.
    # Ο matcher ελέγχει `alias in raw_header`, οπότε το 'findings' του FINDINGS
    # ταιριάζει και στο 'imported findings'. Αν το IMPORTED μπει μετά το
    # FINDINGS δεν θα χρησιμοποιηθεί ΠΟΤΕ.
    'IMPORTED':    ['imported findings', 'imported finding', 'imported'],
    'FINDINGS':    ['ευρήματα', 'ευρηματα', 'findings'],
    'CONCLUSIONS': ['συμπεράσματα', 'συμπερασματα', 'conclusions', 'συμπέρασμα', 'συμπερασμα'],
    'COMMENTS':    ['σχόλια', 'σχολια', 'διάγνωση', 'διαγνωση', 'echo summary'],
}


def parse_sections(html: str) -> dict:
    """
    Διαβάζει το temp_report.htm και επιστρέφει dict:
      { 'LV': 'κείμενο...', 'RV': 'κείμενο...', ... }

    Υβριδική λογική (v3):
      - Περίπτωση Α: Underlined headers → αναγνώριση μέσω SECTION_KEYS
      - Περίπτωση Β (orphan paragraphs):
          1. Startswith check ΜΟΝΟ για structural sections (Συμπεράσματα/Σχόλια)
          2. Αν δεν ταιριάζει → αυστηρή προσθήκη στο τρέχον section
    """
    sections = {}
    if not html.strip():
        return sections

    if not BS4_AVAILABLE:
        return _parse_sections_regex(html)

    soup = BeautifulSoup(html, 'html.parser')

    current_section_key = 'FINDINGS'

    STRUCTURAL_BREAKS = [
        (re.compile(r'^συμπ[εέ]ρ[αά]σμα', re.IGNORECASE),  'CONCLUSIONS'),
        (re.compile(r'^σχ[οόό]λια', re.IGNORECASE),        'COMMENTS'),
        (re.compile(r'^δι[αά]γνωση', re.IGNORECASE),       'COMMENTS'),
        (re.compile(r'^echo\s+summary', re.IGNORECASE),    'COMMENTS'),
    ]

    for p_elem in soup.find_all('p'):
        header_span = p_elem.find('span', style=lambda s: s and 'underline' in s)

        if header_span:
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

            current_section_key = section_key

            full_text = p_elem.get_text(separator=' ', strip=True)
            header_text = header_span.get_text(separator=' ', strip=True)
            section_text = full_text.replace(header_text, '', 1).strip()

            if current_section_key in sections:
                sections[current_section_key] += ' ' + section_text
            else:
                sections[current_section_key] = section_text

        else:
            section_text = p_elem.get_text(separator=' ', strip=True)
            if not section_text:
                continue

            text_stripped = section_text.strip()
            for pattern, struct_key in STRUCTURAL_BREAKS:
                if pattern.match(text_stripped):
                    current_section_key = struct_key
                    break

            if current_section_key in sections:
                sections[current_section_key] += ' ' + section_text
            else:
                sections[current_section_key] = section_text

    return sections


def _parse_sections_regex(html: str) -> dict:
    """Fallback parser με Lookahead (χωρίς BeautifulSoup)."""
    sections = {}
    if not html.strip():
        return sections

    _STRUCT_SPLIT = re.compile(
        r'(?=\b(?:Συμπ[εέ]ρ[αά]σμα(?:τα)?|Σχ[οό]λια|Δι[αά]γνωση|Echo\s+Summary)\b)',
        re.IGNORECASE
    )

    pattern = r'<span[^>]*text-decoration:\s*underline[^>]*>(.*?)</span>(.*?)(?=<span[^>]*text-decoration:\s*underline|$)'

    for m in re.finditer(pattern, html, re.DOTALL | re.IGNORECASE):
        raw_header = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        raw_header = re.sub(r'[.:]+\s*$', '', raw_header).lower()
        raw_header = re.sub(r'\s+', ' ', raw_header).strip()

        raw_body = m.group(2)
        body_text = re.sub(r'<[^>]+>', ' ', raw_body)
        body_text = re.sub(r'\s+', ' ', body_text).strip()

        section_key = None
        for key, aliases in SECTION_KEYS.items():
            if any(alias in raw_header or raw_header in alias for alias in aliases):
                section_key = key
                break
        section_key = section_key or f'UNKNOWN:{raw_header[:30]}'

        parts = _STRUCT_SPLIT.split(body_text)

        main_text = parts[0].strip()
        if main_text:
            if section_key in sections:
                sections[section_key] += ' ' + main_text
            else:
                sections[section_key] = main_text

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
                struct_key = section_key

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
    text = text.lower().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', text)


# =============================================================================
# v5 — ΑΥΤΟΥΣΙΕΣ οι αρχικές συναρτήσεις (μόνο για σύγκριση / sanity check)
# =============================================================================

def get_aortic_stenosis_v5(sections: dict) -> int:
    """
    Αορτική στένωση (AS). ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.
    """
    t = normalize(get_sec(sections, 'AV'))
    if not t:
        return 0

    borderline_pat = (
        r'(?:μικρ[οόύη]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
        r'|οριακ[άαήη]\s+(?:σοβαρ\w*|σημαντικ\w*|μετρ[ίι]\w*|μ[έε]τρι\w*|στ[εέ]νωσ\w*)'
    )
    if re.search(borderline_pat, t):
        return 1

    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
    )
    if re.search(mild_pat, t):
        return 0

    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
        r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
        r'|τουλ[άα]χιστον\s+(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+(?:βαθμο[ύυ]\s+)?στ[εέ]νωσ'
    )
    if re.search(pos_pat, t):
        negation_guard = (
            r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται|υπ[άα]ρχει)|απουσ[ίι]α)'
            r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*στ[εέ]νωσ'
        )
        if re.search(negation_guard, t):
            return 0
        return 1

    return 0


def get_aortic_regurgitation_v5(sections: dict) -> int:
    """
    Αορτική Ανεπάρκεια (AR). ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια/ίχνος → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.
    """
    t = normalize(get_sec(sections, 'AV'))
    if not t:
        return 0

    borderline_pat = (
        r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
    )
    if re.search(borderline_pat, t):
        return 1

    mild_pat = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    if re.search(mild_pat, t):
        return 0

    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
    )
    if re.search(pos_pat, t):
        negation_guard = (
            r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται)|απουσ[ίι]α)'
            r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        )
        if re.search(negation_guard, t):
            return 0
        return 1

    return 0


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v5 (μην τα επεξεργαστείς εδώ)
# =============================================================================

# ── ΣΤΕΝΩΣΗ ΑΟΡΤΙΚΗΣ ─────────────────────────────────────────────────────────
AS_BORDERLINE = (
    r'(?:μικρ[οόύη]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
    r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
    r'|οριακ[άαήη]\s+(?:σοβαρ\w*|σημαντικ\w*|μετρ[ίι]\w*|μ[έε]τρι\w*|στ[εέ]νωσ\w*)'
)
# Ένα bidirectional regex ΧΩΡΙΣ ίχνος → δεν χρειάζεται split.
AS_MILD_PAT = (
    r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
    r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
)
AS_POSITIVE = (
    r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}στ[εέ]νωσ'
    r'|στ[εέ]νωσ\w*\s+(?:\w+\s+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
    r'|τουλ[άα]χιστον\s+(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+(?:βαθμο[ύυ]\s+)?στ[εέ]νωσ'
)
AS_NEGATION = (
    r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται|υπ[άα]ρχει)|απουσ[ίι]α)'
    r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*στ[εέ]νωσ'
)

# ── ΑΝΕΠΑΡΚΕΙΑ ΑΟΡΤΙΚΗΣ ──────────────────────────────────────────────────────
AR_BORDERLINE = (
    r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
    r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
)

# Τα τρία alternations του v5 mild_pat, σπασμένα ώστε το ΙΧΝΟΣ να μένει χωριστά.
# AR_MILD_FWD + '|' + AR_MILD_REV + '|' + AR_TRACE  ==  το αρχικό mild_pat.
AR_MILD_FWD = r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
AR_MILD_REV = r'(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
AR_TRACE    = r'[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'

AR_POSITIVE = (
    r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
    r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
)
AR_NEGATION = (
    r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται|καταγρ[άα]φεται)|απουσ[ίι]α)'
    r'\s+(?:\w+\s+){0,4}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)?(?:\s+βαθμο[ύυ])?\s*(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
)

# Ανασύνθεση του v5 mild_pat από τα τρία κομμάτια — ελέγχεται στο self-test.
AR_MILD_PAT_V5 = AR_MILD_FWD + '|' + AR_MILD_REV + '|' + AR_TRACE


# =============================================================================
# ΕΝΗΜΕΡΩΤΙΚΑ PATTERNS — ΝΕΑ, μόνο για flags (δεν επηρεάζουν κανένα label)
# Γράφονται ΧΩΡΙΣ τόνους, γιατί εφαρμόζονται σε normalize()-αρισμένο κείμενο.
# =============================================================================

# Μέσα στο mild match: άρνηση → το «ήπια» πιθανότατα αφορά κάτι άλλο
SUSPECT_NEGATION = r'\b(?:χωρις|δεν|απουσια|ουτε)\b'
# Μέσα στο mild match: το ουσιαστικό του ΑΛΛΟΥ finding
SUSPECT_OTHER_NOUN_AS = r'ανεπαρκ|διαφυγ'      # για mild της στένωσης
SUSPECT_OTHER_NOUN_AR = r'στενωσ'              # για mild της ανεπάρκειας

# Mild όροι που ΔΕΝ καλύπτονται από τα v5 regex
_UNCOVERED_MILD = r'(?:ελαφρι\w*|ελαφρως|ηπιου|αμελητ\w*)'
AS_UNCOVERED = (
    _UNCOVERED_MILD + r'(?:\s+βαθμου)?\s+(?:\w+\s+){0,3}στενωσ'
    r'|στενωσ\w*\s+(?:\w+\s+){0,3}' + _UNCOVERED_MILD
)
AR_UNCOVERED = (
    _UNCOVERED_MILD + r'(?:\s+βαθμου)?\s+(?:\w+\s+){0,3}(?:ανεπαρκ|διαφυγ)'
    r'|(?:ανεπαρκ|διαφυγ)\w*\s+(?:\w+\s+){0,3}' + _UNCOVERED_MILD
)

# Report με προσθετική βαλβίδα / TAVI (π.χ. παραβαλβιδική διαφυγή)
PROSTHETIC_CTX = (
    r'\btav[ir]\b|προσθετικ|μηχανικ\w*\s+(?:\w+\s+)?βαλβιδ|μεταλλικ\w*\s+(?:\w+\s+)?βαλβιδ'
    r'|παραβαλβιδ|περιβαλβιδ'
)


# =============================================================================
# CORE LOGIC
# =============================================================================

def _context(text: str, m, before=40, after=30) -> str:
    return text[max(0, m.start() - before): m.end() + after]


def _rec(matches: list, rule: str, m, text: str, raw: str) -> dict:
    rec = {'rule': rule, 'match': m.group(), 'context': _context(text, m),
           'raw': raw, 'decisive_strict': 0, 'decisive_incl': 0, 'end': m.end()}
    matches.append(rec)
    return rec


def _finish(out: dict, dec_strict, dec_incl) -> dict:
    if dec_strict:
        dec_strict['decisive_strict'] = 1
        out['rule_strict'] = dec_strict['rule']
        out['phrase_strict'] = dec_strict['match']
        out['raw_strict'] = dec_strict['raw']
    if dec_incl:
        dec_incl['decisive_incl'] = 1
        out['rule_incl'] = dec_incl['rule']
        out['phrase_incl'] = dec_incl['match']
        out['raw_incl'] = dec_incl['raw']
    return out


def _blank(finding: str) -> dict:
    return {'finding': finding, 'label_strict': 0, 'label_incl': 0, 'grade': 'none',
            'flags': [], 'rule_strict': '', 'phrase_strict': '', 'raw_strict': '',
            'rule_incl': '', 'phrase_incl': '', 'raw_incl': '', 'matches': [],
            'source': 'none'}


# =============================================================================
# ΕΠΙΛΟΓΗ ΠΗΓΗΣ ΚΕΙΜΕΝΟΥ — AV, με fallback σε Συμπεράσματα / Σχόλια / Imported
# =============================================================================

# Πρόταση που αφορά την ΑΟΡΤΙΚΗ.
# - αορτικ / αορτ[ηή] : αορτική, αορτικής, αορτή, αορτής
# - aortic            : αγγλικός όρος
# - avr / ava         : aortic valve replacement / aortic valve area
# ΔΕΝ περιλαμβάνεται το \bav\b: στην καρδιολογία σημαίνει συνήθως
# atrioventricular (AV block, AV node).
# ΣΗΜΕΙΩΣΗ: το `αορτ[ηή]` πιάνει ΚΑΙ την αορτή ως αγγείο → βλ. AORTA_NONVALVE.
AORTIC_CTX = r'αορτικ|αορτ[ηή]|\baortic\b|\bavr\b|\bava\b'
# Πρόταση που αφορά ΑΛΛΗ βαλβίδα → multi-valve, clause φιλτράρισμα.
# Οι συντομογραφίες της μιτροειδούς (mv/mva/mvr) ΜΠΑΙΝΟΥΝ — δεν είναι αμφίσημες
# όπως το AV. Οι TV / TR ΔΕΝ μπαίνουν (αμφίσημες).
OTHER_VALVE_CTX = (r'μιτροειδ|τριγλωχ|πνευμονικ|\bmitral\b|\btricuspid\b'
                   r'|\bmv\b|\bmva\b|\bmvr\b')
# Πρόταση fallback που αφορά την αορτή ως ΑΓΓΕΙΟ, όχι τη βαλβίδα
# (ισθμός/coarctation, υποαορτική, ρίζα, ανιούσα, κατιούσα, τόξο).
# Μόνο flag aortic_ctx_nonvalve — ΔΕΝ αλλάζει το label.
AORTA_NONVALVE = r'ισθμ|υποαορτ|ριζ[αη]|ανιουσ|κατιουσ|\bτοξ(?:ο|ου)\b|coarct'

# Διαχωρισμός σε προτάσεις: τελεία (όχι δεκαδική), άνω τελεία, αλλαγή γραμμής
AV_SENT_SPLIT = r'\.(?!\d)|;|\n'

# Επίπεδο 2 του fallback
FALLBACK_KEYS = ('CONCLUSIONS', 'COMMENTS')
# Επίπεδο 3 του fallback — εξετάζεται ΜΟΝΟ αν το επίπεδο 2 δεν έδωσε τίποτα
IMPORTED_KEYS = ('IMPORTED',)

# Διαχωρισμός πρότασης σε clauses — μόνο για multi-valve προτάσεις
CLAUSE_SPLIT = r',|·|\sκαι\s|\sκαθ[ωώ]ς\s|/'


def _aortic_clauses(sent: str) -> str:
    """
    Από πρόταση που αναφέρει ΠΑΝΩ ΑΠΟ ΜΙΑ βαλβίδα, κρατά μόνο τα clauses που
    αφορούν την αορτική. Ίδιος αλγόριθμος με το _mitral_clauses():
      1. Clause που ονομάζει βαλβίδα ανήκει σε αυτήν.
      2. Clause χωρίς όνομα βαλβίδας κληρονομεί το ΠΡΟΗΓΟΥΜΕΝΟ όργανο.
      3. Αρχικά clauses χωρίς προηγούμενο όργανο κληρονομούν το ΕΠΟΜΕΝΟ.
    """
    parts = [p.strip() for p in re.split(CLAUSE_SPLIT, sent, flags=re.IGNORECASE) if p.strip()]
    if len(parts) < 2:
        return sent

    owners = []
    for p in parts:
        pn = normalize(p)
        if re.search(AORTIC_CTX, pn):
            owners.append('AORTIC')
        elif re.search(OTHER_VALVE_CTX, pn):
            owners.append('OTHER')
        else:
            owners.append(None)

    cur = None
    for i, o in enumerate(owners):
        if o:
            cur = o
        elif cur:
            owners[i] = cur
    nxt = None
    for i in range(len(owners) - 1, -1, -1):
        if owners[i]:
            nxt = owners[i]
        elif nxt:
            owners[i] = nxt

    kept = [p for p, o in zip(parts, owners) if o == 'AORTIC']
    return ', '.join(kept)


def _scan_sections(sections: dict, keys: tuple) -> tuple:
    """
    Σαρώνει τα δοσμένα sections ανά πρόταση και κρατά ΜΟΝΟ όσες αναφέρουν ρητά
    την αορτική (AORTIC_CTX).

    - Σκέτο «μέτρια ανεπάρκεια» χωρίς όργανο → αγνοείται (αμφίσημο).
    - Πρόταση που αναφέρει ΚΑΙ άλλη βαλβίδα → clause φιλτράρισμα
      + flag multi_valve_sentence.
    - Κρατημένη πρόταση για την αορτή ως αγγείο → flag aortic_ctx_nonvalve.

    Επιστρέφει: (kept_sentences, used_keys, flags)
    """
    kept, used_keys, flags = [], [], []
    for key in keys:
        raw_k = get_sec(sections, key)
        if not raw_k.strip():
            continue
        for sent in re.split(AV_SENT_SPLIT, raw_k):
            sent = sent.strip()
            if not sent:
                continue
            sent_norm = normalize(sent)
            if not re.search(AORTIC_CTX, sent_norm):
                continue
            if re.search(OTHER_VALVE_CTX, sent_norm):
                if 'multi_valve_sentence' not in flags:
                    flags.append('multi_valve_sentence')
                sent = _aortic_clauses(sent)
                if not sent.strip():
                    continue
            if re.search(AORTA_NONVALVE, normalize(sent)):
                if 'aortic_ctx_nonvalve' not in flags:
                    flags.append('aortic_ctx_nonvalve')
            kept.append(sent)
            if key not in used_keys:
                used_keys.append(key)
    return kept, used_keys, flags


def resolve_aortic_text(sections: dict) -> dict:
    """
    Επιλέγει το κείμενο πάνω στο οποίο θα τρέξουν οι extractors.
    Τρία επίπεδα, αυστηρά ιεραρχικά — το πρώτο που δίνει αποτέλεσμα κερδίζει:

    1. AV — αν υπάρχει (μη κενό) section «Αορτική βαλβίδα». Ταυτόσημο με v5.
    2. CONCLUSIONS + COMMENTS — per-sentence.
    3. IMPORTED — «Imported Findings», per-sentence.

    Επιστρέφει: {'raw': κείμενο, 'source': ετικέτα πηγής, 'flags': [...]}
    source ∈ {'AV', 'CONCLUSIONS', 'COMMENTS', 'CONCLUSIONS+COMMENTS',
              'IMPORTED', 'none'}
    """
    raw_av = get_sec(sections, 'AV')
    if raw_av.strip():
        return {'raw': raw_av, 'source': 'AV', 'flags': []}

    kept, used_keys, flags = _scan_sections(sections, FALLBACK_KEYS)
    if kept:
        return {'raw': '. '.join(kept),
                'source': '+'.join(used_keys),
                'flags': ['fallback_source'] + flags}

    kept, used_keys, flags = _scan_sections(sections, IMPORTED_KEYS)
    if kept:
        return {'raw': '. '.join(kept),
                'source': '+'.join(used_keys),
                'flags': ['fallback_source', 'imported_findings'] + flags}

    return {'raw': '', 'source': 'none', 'flags': []}


def _info_flags(out: dict, prefix: str, t: str, rec_mild, other_noun: str, uncovered_pat: str):
    """Ενημερωτικά flags — ΔΕΝ αλλάζουν κανένα label."""
    # mild που έδωσε INCLUSIVE=1 αλλά:
    #   (α) περιέχει άρνηση ή το άλλο ουσιαστικό μέσα στο match
    #       («ήπια πάχυνση χωρίς στένωση», «ήπια στένωση χωρίς ανεπάρκεια»), ή
    #   (β) ακολουθείται αμέσως (≤2 λέξεις) από το άλλο ουσιαστικό — το «ήπια»
    #       αφορά το ΑΛΛΟ finding («σοβαρή στένωση και ήπια ανεπάρκεια» → εδώ ο
    #       v5 βγάζει AS=0 παρά τη σοβαρή στένωση)
    if out['grade'] == 'mild' and rec_mild and rec_mild['decisive_incl']:
        after = t[rec_mild['end']:]
        if (re.search(SUSPECT_NEGATION, rec_mild['match'])
                or re.search(other_noun, rec_mild['match'])
                or re.match(r'\s*(?:\w+\s+){0,2}(?:' + other_noun + ')', after)):
            out['flags'].append(f'{prefix}_mild_suspect')
    # INCLUSIVE=0 ενώ υπάρχει ακάλυπτος mild όρος
    if out['label_incl'] == 0 and re.search(uncovered_pat, t):
        out['flags'].append(f'{prefix}_mild_uncovered')
    # INCLUSIVE=1 σε report με TAVI / προσθετική
    if out['label_incl'] == 1 and re.search(PROSTHETIC_CTX, t):
        out['flags'].append(f'{prefix}_prosthetic_context')


def grade_aortic_stenosis(sections: dict, resolved: dict = None) -> dict:
    """
    Στένωση αορτικής — STRICT + INCLUSIVE σε ένα πέρασμα.

    STRICT    : borderline(1) → mild(0) → positive → [negation(0)] → 1
    INCLUSIVE : borderline(1) → mild(1) → positive → [negation(0)] → 1

    ΧΩΡΙΣ prosthetic guard (δεν υπάρχει στο v5 για την AS).
    """
    out = _blank('aortic_stenosis')
    resolved = resolved or resolve_aortic_text(sections)
    raw = resolved['raw']
    out['source'] = resolved['source']
    t = normalize(raw)
    if not t:
        return out
    M = out['matches']

    m_border = re.search(AS_BORDERLINE, t)
    m_mild   = re.search(AS_MILD_PAT, t)
    m_pos    = re.search(AS_POSITIVE, t)
    m_neg    = re.search(AS_NEGATION, t) if m_pos else None

    rec_border = _rec(M, 'borderline', m_border, t, raw) if m_border else None
    rec_mild   = _rec(M, 'mild', m_mild, t, raw) if m_mild else None
    rec_pos    = _rec(M, 'positive', m_pos, t, raw) if m_pos else None
    rec_neg    = _rec(M, 'negation_guard', m_neg, t, raw) if m_neg else None

    # ── STRICT (ταυτόσημο με v5) ─────────────────────────────────────────
    if rec_border:
        out['label_strict'], dec_strict = 1, rec_border
    elif rec_mild:
        out['label_strict'], dec_strict = 0, rec_mild
    elif rec_pos:
        if rec_neg:
            out['label_strict'], dec_strict = 0, rec_neg
        else:
            out['label_strict'], dec_strict = 1, rec_pos
    else:
        out['label_strict'], dec_strict = 0, None

    # ── INCLUSIVE ────────────────────────────────────────────────────────
    if rec_border:
        out['label_incl'], out['grade'], dec_incl = 1, 'borderline', rec_border
    elif rec_mild:
        out['label_incl'], out['grade'], dec_incl = 1, 'mild', rec_mild
    elif rec_pos and not rec_neg:
        out['label_incl'], out['grade'], dec_incl = 1, 'moderate_severe', rec_pos
    elif rec_pos and rec_neg:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', rec_neg
    else:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', None

    _finish(out, dec_strict, dec_incl)

    # ── FLAGS ────────────────────────────────────────────────────────────
    if out['label_incl'] == 1 and out['label_strict'] == 0:
        out['flags'].append('as_incl_only')
    _info_flags(out, 'as', t, rec_mild, SUSPECT_OTHER_NOUN_AS, AS_UNCOVERED)
    return out


def grade_aortic_regurgitation(sections: dict, resolved: dict = None) -> dict:
    """
    Ανεπάρκεια αορτικής — STRICT + INCLUSIVE σε ένα πέρασμα.

    STRICT    : borderline(1) → [mild Ή ίχνος](0) → positive → [negation(0)] → 1
                (ισοδύναμο με το ενιαίο mild_pat του v5)
    INCLUSIVE : borderline(1) → mild(1) → positive → [negation(0)] → 1 → ίχνος(0)
    """
    out = _blank('aortic_regurgitation')
    resolved = resolved or resolve_aortic_text(sections)
    raw = resolved['raw']
    out['source'] = resolved['source']
    t = normalize(raw)
    if not t:
        return out
    M = out['matches']

    m_border = re.search(AR_BORDERLINE, t)
    m_mild_f = re.search(AR_MILD_FWD, t)
    m_mild_r = re.search(AR_MILD_REV, t)
    m_trace  = re.search(AR_TRACE, t)
    m_pos    = re.search(AR_POSITIVE, t)
    m_neg    = re.search(AR_NEGATION, t) if m_pos else None

    rec_border = _rec(M, 'borderline', m_border, t, raw) if m_border else None
    rec_mild_f = _rec(M, 'mild_forward', m_mild_f, t, raw) if m_mild_f else None
    rec_mild_r = _rec(M, 'mild_reverse', m_mild_r, t, raw) if m_mild_r else None
    rec_trace  = _rec(M, 'trace', m_trace, t, raw) if m_trace else None
    rec_pos    = _rec(M, 'positive', m_pos, t, raw) if m_pos else None
    rec_neg    = _rec(M, 'negation_guard', m_neg, t, raw) if m_neg else None

    rec_mild = rec_mild_f or rec_mild_r

    # ── STRICT (ταυτόσημο με v5) ─────────────────────────────────────────
    if rec_border:
        out['label_strict'], dec_strict = 1, rec_border
    elif rec_mild or rec_trace:
        out['label_strict'], dec_strict = 0, (rec_mild or rec_trace)
    elif rec_pos:
        if rec_neg:
            out['label_strict'], dec_strict = 0, rec_neg
        else:
            out['label_strict'], dec_strict = 1, rec_pos
    else:
        out['label_strict'], dec_strict = 0, None

    # ── INCLUSIVE ────────────────────────────────────────────────────────
    if rec_border:
        out['label_incl'], out['grade'], dec_incl = 1, 'borderline', rec_border
    elif rec_mild:
        out['label_incl'], out['grade'], dec_incl = 1, 'mild', rec_mild
    elif rec_pos and not rec_neg:
        out['label_incl'], out['grade'], dec_incl = 1, 'moderate_severe', rec_pos
    elif rec_trace:
        out['label_incl'], out['grade'], dec_incl = 0, 'trace', rec_trace
    elif rec_pos and rec_neg:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', rec_neg
    else:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', None

    _finish(out, dec_strict, dec_incl)

    # ── FLAGS ────────────────────────────────────────────────────────────
    if rec_trace:
        out['flags'].append('ar_trace')
    if out['label_incl'] == 1 and out['label_strict'] == 0:
        out['flags'].append('ar_incl_only')
        if out['grade'] in ('moderate_severe', 'borderline'):
            # Η STRICT το μηδένισε λόγω ίχνους παρότι υπάρχει moderate+ αναφορά
            out['flags'].append('ar_strict_blocked')
    _info_flags(out, 'ar', t, rec_mild, SUSPECT_OTHER_NOUN_AR, AR_UNCOVERED)
    return out


# ── Drop-in wrappers (ίδιο signature με τις v5 συναρτήσεις) ──────────────────

def get_aortic_stenosis(sections: dict) -> int:
    return grade_aortic_stenosis(sections)['label_strict']


def get_aortic_stenosis_incl_mild(sections: dict) -> int:
    return grade_aortic_stenosis(sections)['label_incl']


def get_aortic_regurgitation(sections: dict) -> int:
    return grade_aortic_regurgitation(sections)['label_strict']


def get_aortic_regurgitation_incl_mild(sections: dict) -> int:
    return grade_aortic_regurgitation(sections)['label_incl']


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
    phrase_norm = (phrase_norm or '').strip()
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

FLAG_FILL = PatternFill('solid', fgColor='FFC000')   # έντονο πορτοκαλί

# Μόνο αυτά τα flags χρωματίζουν τη γραμμή (τα υπόλοιπα είναι αναμενόμενο delta)
REVIEW_FLAGS = {'multi_valve_sentence', 'aortic_ctx_nonvalve',
                'as_mild_suspect', 'ar_mild_suspect',
                'as_mild_uncovered', 'ar_mild_uncovered',
                'as_prosthetic_context', 'ar_prosthetic_context',
                'ar_strict_blocked',
                'strict_vs_v5_mismatch', 'non_monotonic'}


def write_excel(path: Path, label_rows: list, evidence_rows: list):
    wb = Workbook()
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='305496')
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
    cols1 = ['exam_id', 'source',
             'aortic_stenosis', 'aortic_stenosis_incl_mild', 'as_delta', 'as_grade',
             'as_rule_incl', 'as_phrase_incl', 'as_v5',
             'aortic_regurgitation', 'aortic_regurgitation_incl_mild', 'ar_delta', 'ar_grade',
             'ar_rule_incl', 'ar_phrase_incl', 'ar_v5',
             'flags', 'status', 'aortic_text', 'av_text',
             'conclusions_text', 'comments_text', 'imported_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 20,
                16, 20, 10, 20, 18, 36, 8,
                20, 24, 10, 20, 18, 36, 8,
                36, 18, 70, 70, 60, 60, 60, 60],
               wrap_cols=('aortic_text', 'av_text', 'conclusions_text',
                          'comments_text', 'imported_text'))
    i_flag = cols1.index('flags')
    i_das, i_dar = cols1.index('as_delta'), cols1.index('ar_delta')
    for row in ws1.iter_rows(min_row=2):
        flags = row[i_flag].value or ''
        if any(f in REVIEW_FLAGS for f in flags.split(';') if f):
            for c in row:
                c.fill = FLAG_FILL
        for j in (i_das, i_dar):
            if row[j].value == 1:
                row[j].font = chg_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'finding', 'rule', 'matched_phrase',
             'decisive_strict', 'decisive_incl', 'context']
    fill_sheet(ws2, cols2, evidence_rows, [18, 22, 26, 42, 15, 14, 80], wrap_cols=('context',))

    wb.save(path)


# =============================================================================
# SELF-TEST (synthetic περιπτώσεις — τρέχει πριν το batch)
# =============================================================================

def AV(text: str) -> dict:
    """Helper: sections dict με μόνο το AV section."""
    return {'AV': text} if text else {}


# (AV text, as_strict, as_incl, as_grade, ar_strict, ar_incl, ar_grade, required_flags)
SELF_TESTS = [
    # ── ΣΤΕΝΩΣΗ ──────────────────────────────────────────────────────────
    ('Μέτρια στένωση αορτικής βαλβίδας.',
     1, 1, 'moderate_severe', 0, 0, 'none', []),
    ('Σοβαρού βαθμού στένωση.',
     1, 1, 'moderate_severe', 0, 0, 'none', []),
    ('Στένωση μετρίου βαθμού.',
     1, 1, 'moderate_severe', 0, 0, 'none', []),
    ('Ήπια στένωση.',
     0, 1, 'mild', 0, 0, 'none', ['as_incl_only']),
    ('Μικρού βαθμού στένωση.',
     0, 1, 'mild', 0, 0, 'none', []),
    ('Ελαφρά στένωση.',
     0, 1, 'mild', 0, 0, 'none', []),
    ('Ελάχιστη στένωση.',
     0, 1, 'mild', 0, 0, 'none', []),
    ('Οριακή στένωση.',
     1, 1, 'borderline', 0, 0, 'none', []),
    ('Μικρού προς μετρίου βαθμού στένωση.',
     1, 1, 'borderline', 0, 0, 'none', []),
    # Negation guard → 0 και στις δύο
    ('Χωρίς σημαντική στένωση.',
     0, 0, 'none', 0, 0, 'none', []),
    # ΓΝΩΣΤΟ v5: το «έως» (με τόνο) στο borderline δεν ταιριάζει ποτέ μετά το
    # normalize() → πιάνεται από το mild. STRICT=0 όπως στο v5.
    ('Ήπια έως μέτρια στένωση.',
     0, 1, 'mild', 0, 0, 'none', []),
    # «ήπια» που αφορά την πάχυνση → INCLUSIVE=1 (v5 regex), flag για έλεγχο
    ('Ήπια πάχυνση χωρίς στένωση.',
     0, 1, 'mild', 0, 0, 'none', ['as_mild_suspect']),
    # Ακάλυπτος mild όρος → 0/0 + flag
    ('Αμελητέα στένωση.',
     0, 0, 'none', 0, 0, 'none', ['as_mild_uncovered']),
    # Προσθετική με σημαντική στένωση → label αμετάβλητο, flag
    ('Μηχανική αορτική βαλβίδα με σημαντική στένωση.',
     1, 1, 'moderate_severe', 0, 0, 'none', ['as_prosthetic_context']),

    # ── ΑΝΕΠΑΡΚΕΙΑ ───────────────────────────────────────────────────────
    ('Μέτρια ανεπάρκεια αορτικής.',
     0, 0, 'none', 1, 1, 'moderate_severe', []),
    ('Ανεπάρκεια σοβαρού βαθμού.',
     0, 0, 'none', 1, 1, 'moderate_severe', []),
    ('Σημαντική διαφυγή.',
     0, 0, 'none', 1, 1, 'moderate_severe', []),
    ('Ήπια ανεπάρκεια.',
     0, 0, 'none', 0, 1, 'mild', ['ar_incl_only']),
    ('Ανεπάρκεια μικρού βαθμού.',
     0, 0, 'none', 0, 1, 'mild', []),
    ('Ελαφρά ανεπάρκεια.',
     0, 0, 'none', 0, 1, 'mild', []),
    ('Ελάχιστη διαφυγή.',
     0, 0, 'none', 0, 1, 'mild', []),
    # ΙΧΝΟΣ — 0 και στις δύο
    ('Ίχνος ανεπάρκειας.',
     0, 0, 'none', 0, 0, 'trace', ['ar_trace']),
    ('Ίχνος διαφυγής.',
     0, 0, 'none', 0, 0, 'trace', ['ar_trace']),
    # Ίχνος + σοβαρή: STRICT=0 (v5), INCLUSIVE=1 → ar_strict_blocked
    ('Σοβαρή ανεπάρκεια. Ίχνος διαφυγής.',
     0, 0, 'none', 0, 1, 'moderate_severe', ['ar_strict_blocked', 'ar_trace']),
    # ΓΝΩΣΤΟ: το «μέτρια» της στένωσης πιάνεται από το reverse positive του AR
    # → INCLUSIVE AR=1 (λάθος), STRICT=0 → ar_strict_blocked για έλεγχο
    ('Ίχνος ανεπάρκειας, μέτρια στένωση.',
     1, 1, 'moderate_severe', 0, 1, 'moderate_severe', ['ar_strict_blocked']),
    ('Μικρού προς μετρίου βαθμού ανεπάρκεια.',
     0, 0, 'none', 1, 1, 'borderline', []),
    ('Χωρίς σημαντική ανεπάρκεια.',
     0, 0, 'none', 0, 0, 'none', []),
    # Ακάλυπτοι mild όροι → 0/0 + flag
    ('Ελαφριά ανεπάρκεια.',
     0, 0, 'none', 0, 0, 'none', ['ar_mild_uncovered']),
    ('Ήπιου βαθμού ανεπάρκεια.',
     0, 0, 'none', 0, 0, 'none', ['ar_mild_uncovered']),
    # TAVI + παραβαλβιδική διαφυγή → INCLUSIVE=1, flag
    ('Βιοπροσθετική αορτική βαλβίδα (TAVI) με ήπια παραβαλβιδική διαφυγή.',
     0, 0, 'none', 0, 1, 'mild', ['ar_prosthetic_context']),
    ('Καλή διάνοιξη των πτυχών.',
     0, 0, 'none', 0, 0, 'none', []),

    # ── ΣΥΝΔΥΑΣΜΟΙ ───────────────────────────────────────────────────────
    ('Σοβαρή στένωση με μέτρια ανεπάρκεια.',
     1, 1, 'moderate_severe', 1, 1, 'moderate_severe', []),
    # ΓΝΩΣΤΟ v5 false negative: το «ήπια» της ανεπάρκειας πιάνεται από το reverse
    # mild της στένωσης → AS STRICT=0 παρά τη σοβαρή στένωση → flag
    ('Σοβαρού βαθμού στένωση και ήπια ανεπάρκεια.',
     0, 1, 'mild', 0, 1, 'mild', ['as_mild_suspect']),
    # «ήπια» της στένωσης πιάνεται από το mild του AR → flag
    ('Ήπια στένωση χωρίς ανεπάρκεια.',
     0, 1, 'mild', 0, 1, 'mild', ['ar_mild_suspect']),
    # v5 false negative για AR (το «ήπια» της στένωσης μπλοκάρει το «μέτρια») → flag
    ('Ήπια στένωση και μέτρια ανεπάρκεια.',
     0, 1, 'mild', 0, 1, 'mild', ['ar_mild_suspect']),
    ('Μικρού βαθμού στένωση και ανεπάρκεια.',
     0, 1, 'mild', 0, 1, 'mild', ['ar_mild_suspect']),
    ('',
     0, 0, 'none', 0, 0, 'none', []),
]

# (sections, as_strict, as_incl, as_grade, ar_strict, ar_incl, ar_grade, source, required_flags)
SELF_TESTS_FALLBACK = [
    # Χωρίς AV section — εύρημα στα Συμπεράσματα
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής βαλβίδας.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', ['fallback_source']),
    # Εύρημα στη Διάγνωση (→ COMMENTS)
    ({'COMMENTS': 'Διάγνωση: Ήπια ανεπάρκεια αορτικής.'},
     0, 0, 'none', 0, 1, 'mild', 'COMMENTS', []),
    # Πρόταση για ΑΛΛΗ βαλβίδα → αγνοείται
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 0, 0, 'none', 'none', []),
    # Σκέτο «μέτρια ανεπάρκεια» → αμφίσημο
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια.'},
     0, 0, 'none', 0, 0, 'none', 'none', []),
    # Multi-valve, σειρά 1: αορτική πρώτα
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής και ήπια ανεπάρκεια μιτροειδούς.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Multi-valve, σειρά 2: χωρίς φιλτράρισμα το «μέτρια ανεπάρκεια» θα έδινε AR=1
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς και ήπια στένωση αορτικής.'},
     0, 1, 'mild', 0, 0, 'none', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Clause χωρίς βαλβίδα κληρονομεί το προηγούμενο όργανο
    ({'CONCLUSIONS': 'Ανεπάρκεια αορτικής, μετρίου βαθμού, και ήπια στένωση μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Επιλογή της σχετικής πρότασης μέσα από πολλές
    ({'CONCLUSIONS': 'Φυσιολογική μιτροειδής βαλβίδα. Ήπια ανεπάρκεια αορτικής. '
                     'Φυσιολογική συστολική λειτουργία.'},
     0, 0, 'none', 0, 1, 'mild', 'CONCLUSIONS', []),
    # Ίχνος στα Συμπεράσματα
    ({'CONCLUSIONS': 'Ίχνος ανεπάρκειας αορτικής.'},
     0, 0, 'none', 0, 0, 'trace', 'CONCLUSIONS', []),
    # Συντομογραφία AVA
    ({'CONCLUSIONS': 'Μέτρια στένωση, AVA 1.2 cm2.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', []),
    # Συντομογραφία MV μέσα σε multi-valve πρόταση
    ({'COMMENTS': 'Ήπια ανεπάρκεια MV και σοβαρή στένωση αορτικής.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'COMMENTS', ['multi_valve_sentence']),
    # AV block → ΔΕΝ θεωρείται αορτική
    ({'CONCLUSIONS': 'Κολποκοιλιακός αποκλεισμός 1ου βαθμού (AV block). Μέτρια ανεπάρκεια.'},
     0, 0, 'none', 0, 0, 'none', 'none', []),
    # ΓΝΩΣΤΟ: στένωση ισθμού αορτής → AS=1 (λάθος), flag για manual έλεγχο
    ({'CONCLUSIONS': 'Σοβαρή στένωση ισθμού αορτής.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', ['aortic_ctx_nonvalve']),
    # Αορτή ως αγγείο χωρίς εύρημα βαλβίδας → μόνο flag
    ({'CONCLUSIONS': 'Διάταση ρίζας αορτής.'},
     0, 0, 'none', 0, 0, 'none', 'CONCLUSIONS', ['aortic_ctx_nonvalve']),
    # ΥΠΑΡΧΕΙ AV section → ΔΕΝ ενεργοποιείται fallback
    ({'AV': 'Τρίπτυχη, καλή διάνοιξη.', 'CONCLUSIONS': 'Σοβαρή στένωση αορτικής.'},
     0, 0, 'none', 0, 0, 'none', 'AV', []),
    # Κενό AV section → fallback
    ({'AV': '   ', 'CONCLUSIONS': 'Σοβαρή στένωση αορτικής.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', []),
    # ── ΕΠΙΠΕΔΟ 3: Imported Findings ─────────────────────────────────────
    ({'IMPORTED': 'Μέτρια ανεπάρκεια αορτικής.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'IMPORTED', ['imported_findings']),
    ({'CONCLUSIONS': 'Τυπική μελέτη.', 'IMPORTED': 'Ήπια στένωση αορτικής.'},
     0, 1, 'mild', 0, 0, 'none', 'IMPORTED', []),
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής.', 'IMPORTED': 'Ήπια στένωση αορτικής.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS', []),
    ({'AV': 'Καλή διάνοιξη.', 'IMPORTED': 'Σοβαρή στένωση αορτικής.'},
     0, 0, 'none', 0, 0, 'none', 'AV', []),
    ({'IMPORTED': 'Σοβαρή ανεπάρκεια μιτροειδούς και ήπια στένωση αορτικής.'},
     0, 1, 'mild', 0, 0, 'none', 'IMPORTED', ['multi_valve_sentence']),
    ({'IMPORTED': 'Φυσιολογική συστολική λειτουργία αριστερής κοιλίας.'},
     0, 0, 'none', 0, 0, 'none', 'none', []),
    # Τίποτα πουθενά
    ({'CONCLUSIONS': 'Τυπική μελέτη.'},
     0, 0, 'none', 0, 0, 'none', 'none', []),
]


def run_self_test() -> bool:
    ok_all = True
    logger.info("SELF-TEST")

    # 0. Η ανασύνθεση του v5 mild_pat της AR πρέπει να είναι χαρακτήρα-προς-χαρακτήρα ίδια
    expected_mild_v5 = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    same = (AR_MILD_PAT_V5 == expected_mild_v5)
    ok_all &= same
    logger.info(f"  [{'PASS' if same else 'FAIL':5}] ανασύνθεση v5 mild_pat από AR_MILD_FWD|AR_MILD_REV|AR_TRACE")

    cases = [(AV(av), a, b, c, d, e, f, 'AV' if av else 'none', fl)
             for av, a, b, c, d, e, f, fl in SELF_TESTS]
    cases += SELF_TESTS_FALLBACK

    n_pass = 0
    for secs, e_ass, e_asi, e_asg, e_ars, e_ari, e_arg, e_src, e_flags in cases:
        resolved = resolve_aortic_text(secs)
        a_s = grade_aortic_stenosis(secs, resolved)
        a_r = grade_aortic_regurgitation(secs, resolved)
        as_v5 = get_aortic_stenosis_v5(secs)
        ar_v5 = get_aortic_regurgitation_v5(secs)

        v5_ok = (resolved['source'] != 'AV' or
                 (a_s['label_strict'] == as_v5 and a_r['label_strict'] == ar_v5))
        all_flags = resolved['flags'] + a_s['flags'] + a_r['flags']
        flags_ok = all(f in all_flags for f in e_flags)

        ok = (a_s['label_strict'] == e_ass and a_s['label_incl'] == e_asi and a_s['grade'] == e_asg and
              a_r['label_strict'] == e_ars and a_r['label_incl'] == e_ari and a_r['grade'] == e_arg and
              resolved['source'] == e_src and v5_ok and flags_ok and
              a_s['label_incl'] >= a_s['label_strict'] and a_r['label_incl'] >= a_r['label_strict'])
        n_pass += ok
        if not ok:
            ok_all = False

        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
        logger.info(
            f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
            f"          → [{resolved['source']}] "
            f"AS {a_s['label_strict']}/{a_s['label_incl']} ({a_s['grade']})   "
            f"AR {a_r['label_strict']}/{a_r['label_incl']} ({a_r['grade']})"
            f"{'  flags=' + ';'.join(all_flags) if all_flags else ''}"
            f"{'' if ok else f'  (αναμενόταν [{e_src}] AS {e_ass}/{e_asi} {e_asg}, AR {e_ars}/{e_ari} {e_arg}, flags⊇{e_flags}, v5 AS={as_v5} AR={ar_v5})'}")

    logger.info(f"SELF-TEST: {n_pass + int(same)}/{len(cases) + 1} — {'ΟΚ' if ok_all else 'ΑΠΕΤΥΧΕ'}")
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
            label_rows.append({'exam_id': e['exam_id'], 'status': 'read_failed',
                               'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        resolved = resolve_aortic_text(sections)
        a_s = grade_aortic_stenosis(sections, resolved)
        a_r = grade_aortic_regurgitation(sections, resolved)
        as_v5 = get_aortic_stenosis_v5(sections)
        ar_v5 = get_aortic_regurgitation_v5(sections)

        src = resolved['source']
        flags = list(resolved['flags']) + a_s['flags'] + a_r['flags']

        if src == 'AV':
            if a_s['label_strict'] != as_v5 or a_r['label_strict'] != ar_v5:
                flags.append('strict_vs_v5_mismatch')
        else:
            if a_s['label_strict'] > as_v5 or a_r['label_strict'] > ar_v5:
                flags.append('fallback_gain')

        if a_s['label_incl'] < a_s['label_strict'] or a_r['label_incl'] < a_r['label_strict']:
            flags.append('non_monotonic')

        if src == 'AV':
            status = 'ok'
        elif src == 'none':
            status = 'no_aortic_text'
        else:
            status = 'fallback'

        label_rows.append({
            'exam_id':                        e['exam_id'],
            'source':                         src,
            'aortic_stenosis':                a_s['label_strict'],
            'aortic_stenosis_incl_mild':      a_s['label_incl'],
            'as_delta':                       a_s['label_incl'] - a_s['label_strict'],
            'as_grade':                       a_s['grade'],
            'as_rule_incl':                   a_s['rule_incl'],
            'as_phrase_incl':                 original_phrase(a_s['raw_incl'], a_s['phrase_incl']),
            'as_v5':                          as_v5,
            'aortic_regurgitation':           a_r['label_strict'],
            'aortic_regurgitation_incl_mild': a_r['label_incl'],
            'ar_delta':                       a_r['label_incl'] - a_r['label_strict'],
            'ar_grade':                       a_r['grade'],
            'ar_rule_incl':                   a_r['rule_incl'],
            'ar_phrase_incl':                 original_phrase(a_r['raw_incl'], a_r['phrase_incl']),
            'ar_v5':                          ar_v5,
            'flags':                          ';'.join(flags),
            'status':                         status,
            'aortic_text':                    resolved['raw'],
            'av_text':                        get_sec(sections, 'AV'),
            'conclusions_text':               get_sec(sections, 'CONCLUSIONS'),
            'comments_text':                  get_sec(sections, 'COMMENTS'),
            'imported_text':                  get_sec(sections, 'IMPORTED'),
            'report_path':                    e['report_path'],
        })

        for res in (a_s, a_r):
            for m in res['matches']:
                evidence_rows.append({
                    'exam_id':         e['exam_id'],
                    'finding':         res['finding'],
                    'rule':            m['rule'],
                    'matched_phrase':  original_phrase(m['raw'], m['match']),
                    'decisive_strict': m['decisive_strict'],
                    'decisive_incl':   m['decisive_incl'],
                    'context':         m['context'],
                })

    out = Path(output_xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_excel(out, label_rows, evidence_rows)
    except PermissionError:
        logger.error(f"Το {out} είναι ανοιχτό στο Excel — κλείσ' το και ξανατρέξε.")
        return

    # ── Στατιστικά ──────────────────────────────────────────────────────────
    ok_rows = [r for r in label_rows if r.get('status') != 'read_failed']
    logger.info("=" * 60)
    logger.info(f"Εξετάσεις: {len(label_rows)} | αναγνώστηκαν: {len(ok_rows)} | "
                f"αποτυχίες: {len(label_rows) - len(ok_rows)}")

    if ok_rows:
        n = len(ok_rows)
        logger.info(f"\n  {'Finding':<34} {'Pos':>5} {'Total':>7} {'%':>6}")
        logger.info(f"  {'-'*54}")
        for col in ('aortic_stenosis', 'aortic_stenosis_incl_mild',
                    'aortic_regurgitation', 'aortic_regurgitation_incl_mild'):
            pos_n = sum(r[col] == 1 for r in ok_rows)
            logger.info(f"  {col:<34} {pos_n:>5} {n:>7} {100 * pos_n / n:>5.1f}%")

        d_as = sum(r['as_delta'] == 1 for r in ok_rows)
        d_ar = sum(r['ar_delta'] == 1 for r in ok_rows)
        logger.info(f"\nΕπιπλέον θετικές λόγω mild:")
        logger.info(f"  aortic_stenosis        +{d_as} ({100 * d_as / n:.1f}%)")
        logger.info(f"  aortic_regurgitation   +{d_ar} ({100 * d_ar / n:.1f}%)")

        src_dist = {}
        for r in ok_rows:
            src_dist[r['source']] = src_dist.get(r['source'], 0) + 1
        logger.info("\nΠηγή κειμένου:")
        for s, c in sorted(src_dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {s:<24} {c:>6} ({100 * c / n:.1f}%)")

        n_fb = sum(r['source'] not in ('AV', 'none') for r in ok_rows)
        if n_fb:
            g_as = sum(r['source'] not in ('AV', 'none') and r['aortic_stenosis'] == 1 for r in ok_rows)
            g_ar = sum(r['source'] not in ('AV', 'none') and r['aortic_regurgitation'] == 1 for r in ok_rows)
            gi_as = sum(r['source'] not in ('AV', 'none') and r['aortic_stenosis_incl_mild'] == 1 for r in ok_rows)
            gi_ar = sum(r['source'] not in ('AV', 'none') and r['aortic_regurgitation_incl_mild'] == 1 for r in ok_rows)
            logger.info(f"\nFallback (χωρίς AV section): {n_fb} εξετάσεις")
            logger.info(f"  νέες θετικές AS: {g_as} strict / {gi_as} incl_mild")
            logger.info(f"  νέες θετικές AR: {g_ar} strict / {gi_ar} incl_mild")

        n_av  = sum(r['source'] == 'AV' for r in ok_rows)
        n_mis = sum('strict_vs_v5_mismatch' in r['flags'] for r in ok_rows)
        n_mon = sum('non_monotonic' in r['flags'] for r in ok_rows)
        if n_mis:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mis} εξετάσεις όπου η STRICT διαφέρει από το v5!")
        else:
            logger.info(f"\nSanity check: η STRICT ταυτίζεται με το v5 και στις {n_av} "
                        f"εξετάσεις με AV section ✓")
        if n_mon:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mon} εξετάσεις με STRICT=1 αλλά INCLUSIVE=0!")
        else:
            logger.info("Sanity check: INCLUSIVE >= STRICT παντού ✓")

        for key in ('as_grade', 'ar_grade'):
            dist = {}
            for r in ok_rows:
                dist[r[key]] = dist.get(r[key], 0) + 1
            logger.info(f"\nΚατανομή {key}:")
            for g, c in sorted(dist.items(), key=lambda x: -x[1]):
                logger.info(f"  {g:<24} {c:>6}")

        flag_counts = {}
        for r in ok_rows:
            for f in filter(None, r['flags'].split(';')):
                flag_counts[f] = flag_counts.get(f, 0) + 1
        if flag_counts:
            logger.info("\nFlags:")
            for f, c in sorted(flag_counts.items(), key=lambda x: -x[1]):
                mark = '  ← ΕΛΕΓΧΟΣ' if f in REVIEW_FLAGS else ''
                logger.info(f"  {f:<24} {c:>6}{mark}")

    logger.info(f"\nExcel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/aortic_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
