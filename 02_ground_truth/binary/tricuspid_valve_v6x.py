r"""
tricuspid_valve_v6x.py
======================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για το finding
της ΤΡΙΓΛΩΧΙΝΑΣ βαλβίδας:

  tricuspid_valve_regurgitation   (ανεπάρκεια τριγλώχινας — TR)

Το όνομα της στήλης είναι ΙΔΙΟ με το CSV του v5 (`tricuspid_valve_regurgitation`),
ώστε να γίνεται απευθείας merge.

Πρότυπο: aortic_valve_v6x.py. Η infrastructure (parsing, ανάγνωση reports,
Excel, run) είναι αυτούσια· αλλάζουν μόνο το finding και η πηγή κειμένου.

Παράγονται ΔΥΟ labels:

  ΑΝΑΛΥΣΗ STRICT   — tricuspid_valve_regurgitation
      Θετικά ΜΟΝΟ μέτριου/σοβαρού βαθμού. Ακριβώς η συμπεριφορά του v5.

  ΑΝΑΛΥΣΗ INCLUSIVE — tricuspid_valve_regurgitation_incl_mild
      Θετικά ΚΑΙ τα ήπια/μικρού βαθμού (mild + moderate + severe).
      Το ΙΧΝΟΣ και η ΦΥΣΙΟΛΟΓΙΚΗ ΔΙΑΦΥΓΗ δεν είναι ποτέ θετικά από μόνα τους.

ΒΑΣΙΚΗ ΑΡΧΗ ΥΛΟΠΟΙΗΣΗΣ
  Κανένα regex του v5 δεν τροποποιήθηκε. Όλα αντιγράφηκαν ΑΥΤΟΥΣΙΑ ως σταθερές
  (TR_*). Το self-test #0 το επιβεβαιώνει αυτόματα: διαβάζει τον κώδικα της
  αυτούσιας v5 συνάρτησης και ελέγχει ότι κάθε σταθερά υπάρχει εκεί
  χαρακτήρα-προς-χαρακτήρα.

  Το ίχνος είναι ήδη ξεχωριστό βήμα στο v5 → ΔΕΝ χρειάζεται split.
  Το competing-moderate check είναι ΙΔΙΟ στα βήματα 1 και 2 του v5 → μία σταθερά
  (TR_COMPETING_MOD), που χρησιμοποιείται και στα δύο.

  ΜΟΝΗ ΠΡΟΣΘΗΚΗ (απόφαση χρήστη): το v5 mild του TR ΔΕΝ περιέχει «ελαφρά» /
  «ελάχιστη». Για να είναι 1 στην INCLUSIVE, όπως στη MR/AR, προστέθηκαν τα
  TR_MILD_EXTRA_FWD / TR_MILD_EXTRA_REV. Είναι οι όροι και η φραγμένη δομή
  {0,3} των MR_MILD_FWD / MR_MILD_REV, αυτούσιοι. Χρησιμοποιούνται ΜΟΝΟ στην
  INCLUSIVE — η STRICT δεν τα βλέπει. Στο Evidence: rule = mild_extra_*.

ΣΕΙΡΑ ΕΛΕΓΧΟΥ

  STRICT — πιστή αναπαραγωγή των 5 βημάτων του v5:
    1. Negation guard (χωρίς/δεν/απουσία … ανεπάρκεια), εκτός competing moderate → 0
    2. Mild (has_mild, χωρίς mild→moderate, χωρίς competing moderate)          → 0
    3. Ίχνος (εκτός αν υπάρχει μετρ/σοβαρ οπουδήποτε)                         → 0
       Φυσιολογική διαφυγή/ανεπάρκεια                                          → 0
    4. Mild→moderate («μικρού προς μετρίου») + λέξη ανεπάρκεια/διαφυγή         → 1
    5. Positive patterns, εκτός αν υπάρχει global negation                    → 1

  INCLUSIVE:
    αν STRICT == 1                                  → 1  (borderline / moderate_severe)
    αλλιώς αν αποφάσισε το negation βήμα 1          → 0  (none)
    αλλιώς αν mild match (v5 ή extra) που ΔΕΝ
           επικαλύπτει το ίχνος / τη φυσιολογική   → 1  (mild)
    αλλιώς αν ίχνος                                 → 0  (trace)
    αλλιώς αν φυσιολογική διαφυγή                   → 0  (physiologic)
    αλλιώς                                          → 0  (none)

  ΓΙΑΤΙ Ο ΕΛΕΓΧΟΣ ΕΠΙΚΑΛΥΨΗΣ: τα patterns του TR είναι `.*?` χωρίς όριο, οπότε
  περνούν από πρόταση σε πρόταση. Στο «Μικρή διάταση δακτυλίου. Ίχνος
  ανεπάρκειας.» το mild match τελειώνει ΜΕΣΑ στη φράση του ίχνους → κερδίζει το
  ίχνος (0). Στο «Ήπια ανεπάρκεια. Ίχνος διαφυγής.» τα δύο match δεν
  επικαλύπτονται → mild (1). Αν το πρώτο mild match επικαλύπτεται, εξετάζονται
  και τα επόμενα (finditer).

  Η INCLUSIVE ≥ STRICT ισχύει δομικά (κάθε STRICT=1 περνά αυτούσιο) και
  ελέγχεται ανά εξέταση.

ΠΗΓΗ ΚΕΙΜΕΝΟΥ — TV με fallback
  1. Αν υπάρχει (μη κενό) section TV → χρησιμοποιείται αυτούσιο, όπως στο v5.
  2. Αλλιώς Συμπεράσματα + Σχόλια/Διάγνωση, ανά πρόταση, μόνο προτάσεις με ρητή
     αναφορά στην τριγλώχινα (TRICUSPID_CTX), με clause φιλτράρισμα στις
     multi-valve.
  3. Αλλιώς «Imported Findings», με το ίδιο φιλτράρισμα.

  Η συντομογραφία TV ΠΕΡΙΛΑΜΒΑΝΕΤΑΙ στο TRICUSPID_CTX (απόφαση χρήστη: στα
  reports η τριγλώχινα γράφεται και ως TV). Το TR ΔΕΝ περιλαμβάνεται (αμφίσημο).
  Το OTHER_VALVE_CTX καλύπτει μόνο μιτροειδή και αορτική (απόφαση χρήστη: η
  πνευμονική δεν λαμβάνεται υπόψη — έτσι και η «πνευμονική υπέρταση» δεν
  δημιουργεί ψευδές multi_valve_sentence).

  ΣΥΝΕΠΕΙΑ ΓΙΑ ΤΟ SANITY CHECK: η ταύτιση STRICT ↔ v5 απαιτείται ΜΟΝΟ στις
  εξετάσεις με source == 'TV'. Στα fallback rows κάθε διαφορά = fallback_gain.

ΣΚΟΠΟΣ
  Πρόχειρο check ορθότητας των ground truth labels, ΟΧΙ το τελικό CSV.

FLAGS (στήλη flags) — οι γραμμές με flag ΕΛΕΓΧΟΥ χρωματίζονται πορτοκαλί:
  tr_incl_only               μόνο στην INCLUSIVE θετικό (χωρίς χρώμα)
  tr_trace                   εντοπίστηκε ίχνος (χωρίς χρώμα)
  fallback_source            λείπει TV section → εναλλακτική πηγή
  imported_findings          η πηγή ήταν το «Imported Findings»
  fallback_gain              το fallback έδωσε θετικό που το v5 έχανε
  multi_valve_sentence       πρόταση με >1 βαλβίδα → clause φιλτράρισμα     [ΕΛΕΓΧΟΣ]
  tr_trace_positive          STRICT=1 με positive match που ξεκινά/περνά από
                             φράση ίχνους («Ίχνος ανεπάρκειας. Μέτρια διάταση
                             δακτυλίου.») — ΓΝΩΣΤΟ FP του v5               [ΕΛΕΓΧΟΣ]
  tr_negation_blocked        υπήρχε positive αλλά το απέκλεισε το global
                             negation («Χωρίς διάταση. Σοβαρή ανεπάρκεια.»)
                             — ΓΝΩΣΤΟ FN του v5                             [ΕΛΕΓΧΟΣ]
  tr_negation_vs_mild        το negation βήματος 1 μηδένισε report που έχει
                             και mild («Χωρίς διάταση. Ήπια ανεπάρκεια.»)    [ΕΛΕΓΧΟΣ]
  tr_cross_sentence          το match που έδωσε θετικό περιέχει τελεία      [ΕΛΕΓΧΟΣ]
  tr_borderline_unanchored   το «μικρού προς μετρίου» δεν συνοδεύεται από
                             ανεπάρκεια/διαφυγή (π.χ. αφορά διάταση)        [ΕΛΕΓΧΟΣ]
  tr_mild_suspect            το mild που έδωσε INCLUSIVE=1 περιέχει άρνηση ή
                             ουσιαστικό άλλης δομής (διάταση, δακτύλιος,
                             στένωση, υπέρταση), ακολουθείται αμέσως από
                             τέτοιο, ή στο κείμενο υπάρχει και ίχνος /
                             φυσιολογική διαφυγή                            [ΕΛΕΓΧΟΣ]
  tr_positive_suspect        ίδιος έλεγχος για το positive που έδωσε STRICT=1
                             («Σοβαρή διάταση δακτυλίου με ανεπάρκεια»)     [ΕΛΕΓΧΟΣ]
  tr_mild_uncovered          INCLUSIVE=0 αλλά υπάρχει mild όρος που δεν
                             καλύπτεται (ελαφριά, ελαφρώς, αμελητέα)        [ΕΛΕΓΧΟΣ]
  strict_vs_v5_mismatch      η STRICT διαφέρει από το v5 — ΣΦΑΛΜΑ           [ΕΛΕΓΧΟΣ]
  non_monotonic              STRICT=1 αλλά INCLUSIVE=0 — ΣΦΑΛΜΑ             [ΕΛΕΓΧΟΣ]

  Όλα τα flags είναι ΕΝΗΜΕΡΩΤΙΚΑ — κανένα δεν αλλάζει label.

GRADE (από τον κανόνα που αποφάσισε την INCLUSIVE):
  none | mild | borderline | moderate_severe | trace | physiologic

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά pattern που ταίριαξε

Εξαρτήσεις: pip install beautifulsoup4 openpyxl
            7-Zip μόνο αν υπάρχουν reports σε .CHM
"""

import re
import ast
import random
import shutil
import inspect
import logging
import subprocess
import tempfile
import textwrap
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
logger = logging.getLogger("tricuspid")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από aortic_valve_v6x)
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
# v5 — ΑΥΤΟΥΣΙΑ η αρχική συνάρτηση (μόνο για σύγκριση / sanity check)
# =============================================================================

def get_tricuspid_regurgitation_v5(sections: dict) -> int:
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


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v5 (μην τα επεξεργαστείς εδώ)
# Κάθε σταθερά ελέγχεται στο self-test #0 απέναντι στον κώδικα της v5.
# =============================================================================

# ── Βήμα 1: negation guard ──────────────────────────────────────────────────
TR_NEGATION = (
    r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[άα]ζει|παρατηρε[ίι]ται)|απουσ[ίι]α)\s+'
    r'.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
)
# Competing moderate+ — ΙΔΙΟ regex στα βήματα 1 και 2 του v5
TR_COMPETING_MOD = (
    r'(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])[,\s]+.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
    r'|(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μετρ[ίι]ου|σοβαρο[ύυ]|μ[εέ]τρια|σοβαρ[ήη])'
)

# ── Βήμα 2: mild guard ──────────────────────────────────────────────────────
TR_MILD = (
    r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πια?).*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
    r'|(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μικρο[ύυ]\s+βαθμο[ύυ]|μικρ[ήη]|[ήη]πια?)'
)
TR_MILD_TO_MOD = (
    r'μικρο[ύυ]\s+προ[σς]\s+μ[εέ]τρ[ίι]?[οωυ]?'
    r'|μικρ[ήη]\s+προ[σς]\s+μ[εέ]τρια'
    r'|[ήη]πι\w*\s+προ[σς]\s+μ[εέ]τρ'
)

# ── Βήμα 3: trace / physiologic guard ───────────────────────────────────────
TR_TRACE        = r'[ίι]χνο[σς]?\s+(?:ανεπ[αά]ρκεια[σς]?|διαφυγ[ήη][σς]?)'
TR_TRACE_EXCEPT = r'(?:μετρ|σοβαρ|μ[εέ]τρια)'
TR_PHYSIOLOGIC  = r'φυσιολογικ\w+\s+(?:διαφυγ[ήη]|ανεπ[αά]ρκεια)'

# ── Βήμα 4: mild→moderate χρειάζεται και λέξη ανεπάρκεια/διαφυγή ────────────
TR_ANY_REGURG = r'ανεπ[αά]ρκεια|διαφυγ[ήη]'

# ── Βήμα 5: positive + global negation ──────────────────────────────────────
TR_POSITIVE = [
    r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
    r'(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]',
    r'(?:μ[εέ]τρια|σοβαρ[ήη]).*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
    r'(?:ανεπ[αά]ρκεια|διαφυγ[ήη]).*?(?:μ[εέ]τρια|σοβαρ[ήη])',
    r'σοβαρη\s+ανεπαρκεια',
    r'μετρ[ίι]ου\s+προ[σς]\s+σοβαρ\w*\s+.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])',
    r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?τριγλωχινικ[ήη]\s+ανεπ[αά]ρκεια',
]
TR_NEGATION_GLOBAL = (
    r'(?:χωρ[ίι][σς]|δεν\s+(?:εμφαν[ίι]ζει|παρουσι[αά]ζει|παρατηρε[ίι]ται)|απουσ[ίι]α)\s+'
    r'.*?(?:ανεπ[αά]ρκεια|διαφυγ[ήη])'
)

# Οι σταθερές που πρέπει να υπάρχουν αυτούσιες στη v5 (self-test #0)
V5_CONSTANTS = {
    'TR_NEGATION': TR_NEGATION, 'TR_COMPETING_MOD': TR_COMPETING_MOD,
    'TR_MILD': TR_MILD, 'TR_MILD_TO_MOD': TR_MILD_TO_MOD,
    'TR_TRACE': TR_TRACE, 'TR_TRACE_EXCEPT': TR_TRACE_EXCEPT,
    'TR_PHYSIOLOGIC': TR_PHYSIOLOGIC, 'TR_ANY_REGURG': TR_ANY_REGURG,
    'TR_NEGATION_GLOBAL': TR_NEGATION_GLOBAL,
    **{f'TR_POSITIVE[{i}]': p for i, p in enumerate(TR_POSITIVE)},
}


# =============================================================================
# ΠΡΟΣΘΗΚΗ — ΜΟΝΟ για την INCLUSIVE (απόφαση χρήστη)
# «ελαφρά» / «ελάχιστη»: ΔΕΝ υπάρχουν στο v5 mild του TR. Όροι και δομή
# αυτούσια από τα MR_MILD_FWD / MR_MILD_REV (φραγμένο {0,3}, όχι .*?).
# =============================================================================

TR_MILD_EXTRA_FWD = r'(?:ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
TR_MILD_EXTRA_REV = r'(?:ανεπ[εάα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'


# =============================================================================
# ΕΝΗΜΕΡΩΤΙΚΑ PATTERNS — ΝΕΑ, μόνο για flags (δεν επηρεάζουν κανένα label)
# Γράφονται ΧΩΡΙΣ τόνους, γιατί εφαρμόζονται σε normalize()-αρισμένο κείμενο.
# =============================================================================

# Μέσα στο match: άρνηση
SUSPECT_NEGATION = r'\b(?:χωρις|δεν|απουσια|ουτε)\b'
# Μέσα στο match ή αμέσως μετά: ουσιαστικό ΑΛΛΗΣ δομής → η βαρύτητα
# πιθανότατα αφορά αυτήν και όχι την ανεπάρκεια
SUSPECT_OTHER_NOUN_TR = r'στενωσ|διατασ|διατεταμ|δακτυλ|υπερτασ'
# «Αμέσως μετά»: επιτρέπεται μόνο το υπόλοιπο της λέξης και ένα «βαθμού»
# (π.χ. «ανεπάρκεια, ήπια διάταση» / «…ήπιου βαθμού διάταση»)
_FOLLOWED_BY = r'\w*\s*(?:βαθμ\w*\s+)?(?:' + SUSPECT_OTHER_NOUN_TR + ')'

# Mild όροι που ΔΕΝ καλύπτονται (ούτε από το v5 ούτε από το mild_extra).
# Το «ήπιου» ΔΕΝ είναι εδώ: το `[ήη]πια?` του v5 TR το πιάνει ήδη (χωρίς \b).
_UNCOVERED_MILD = r'(?:ελαφρι\w*|ελαφρως|αμελητ\w*)'
TR_UNCOVERED = (
    _UNCOVERED_MILD + r'(?:\s+βαθμου)?\s+(?:\w+\s+){0,3}(?:ανεπαρκ|διαφυγ)'
    r'|(?:ανεπαρκ|διαφυγ)\w*\s+(?:\w+\s+){0,3}' + _UNCOVERED_MILD
)

# Τελεία πρότασης μέσα σε match (όχι δεκαδική)
SENTENCE_BREAK = r'\.(?!\d)'


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
# ΕΠΙΛΟΓΗ ΠΗΓΗΣ ΚΕΙΜΕΝΟΥ — TV, με fallback σε Συμπεράσματα / Σχόλια / Imported
# =============================================================================

# Πρόταση που αφορά την ΤΡΙΓΛΩΧΙΝΑ.
# - τριγλωχ   : τριγλώχινα, τριγλώχινας, τριγλωχινική, τριγλωχινικής
# - tricuspid : αγγλικός όρος
# - tv        : η συντομογραφία, όπως γράφεται στα reports (απόφαση χρήστη).
#               Το \b εμποδίζει match μέσα σε μεγαλύτερη λέξη.
# ΔΕΝ περιλαμβάνεται το \btr\b (αμφίσημο).
TRICUSPID_CTX = r'τριγλωχ|\btricuspid\b|\btv\b'
# Πρόταση που αφορά ΑΛΛΗ βαλβίδα → multi-valve, clause φιλτράρισμα.
# Μόνο μιτροειδής και αορτική (με τις μη αμφίσημες συντομογραφίες τους).
# Η πνευμονική ΔΕΝ περιλαμβάνεται (απόφαση χρήστη).
OTHER_VALVE_CTX = (r'μιτροειδ|αορτικ|αορτ[ηή]|\bmitral\b|\baortic\b'
                   r'|\bmv\b|\bmva\b|\bmvr\b|\bavr\b|\bava\b')

# Διαχωρισμός σε προτάσεις: τελεία (όχι δεκαδική), άνω τελεία, αλλαγή γραμμής
TV_SENT_SPLIT = r'\.(?!\d)|;|\n'

# Επίπεδο 2 του fallback
FALLBACK_KEYS = ('CONCLUSIONS', 'COMMENTS')
# Επίπεδο 3 του fallback — εξετάζεται ΜΟΝΟ αν το επίπεδο 2 δεν έδωσε τίποτα
IMPORTED_KEYS = ('IMPORTED',)

# Διαχωρισμός πρότασης σε clauses — μόνο για multi-valve προτάσεις
CLAUSE_SPLIT = r',|·|\sκαι\s|\sκαθ[ωώ]ς\s|/'


def _tricuspid_clauses(sent: str) -> str:
    """
    Από πρόταση που αναφέρει ΠΑΝΩ ΑΠΟ ΜΙΑ βαλβίδα, κρατά μόνο τα clauses που
    αφορούν την τριγλώχινα. Ίδιος αλγόριθμος με το _aortic_clauses():
      1. Clause που ονομάζει βαλβίδα ανήκει σε αυτήν.
      2. Clause χωρίς όνομα βαλβίδας κληρονομεί το ΠΡΟΗΓΟΥΜΕΝΟ όργανο.
      3. Αρχικά clauses χωρίς προηγούμενο όργανο κληρονομούν το ΕΠΟΜΕΝΟ.

    Εδώ είναι ακόμα πιο απαραίτητο απ' ό,τι στις άλλες βαλβίδες: τα patterns του
    TR είναι `.*?` χωρίς όριο, οπότε χωρίς φιλτράρισμα το «σοβαρή» μιας άλλης
    βαλβίδας θα έδινε TR=1.
    """
    parts = [p.strip() for p in re.split(CLAUSE_SPLIT, sent, flags=re.IGNORECASE) if p.strip()]
    if len(parts) < 2:
        return sent

    owners = []
    for p in parts:
        pn = normalize(p)
        if re.search(TRICUSPID_CTX, pn):
            owners.append('TRICUSPID')
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

    kept = [p for p, o in zip(parts, owners) if o == 'TRICUSPID']
    return ', '.join(kept)


def _scan_sections(sections: dict, keys: tuple) -> tuple:
    """
    Σαρώνει τα δοσμένα sections ανά πρόταση και κρατά ΜΟΝΟ όσες αναφέρουν ρητά
    την τριγλώχινα (TRICUSPID_CTX).

    - Σκέτο «μέτρια ανεπάρκεια» χωρίς όργανο → αγνοείται (αμφίσημο).
    - Πρόταση που αναφέρει ΚΑΙ άλλη βαλβίδα → clause φιλτράρισμα
      + flag multi_valve_sentence.

    Επιστρέφει: (kept_sentences, used_keys, flags)
    """
    kept, used_keys, flags = [], [], []
    for key in keys:
        raw_k = get_sec(sections, key)
        if not raw_k.strip():
            continue
        for sent in re.split(TV_SENT_SPLIT, raw_k):
            sent = sent.strip()
            if not sent:
                continue
            sent_norm = normalize(sent)
            if not re.search(TRICUSPID_CTX, sent_norm):
                continue
            if re.search(OTHER_VALVE_CTX, sent_norm):
                if 'multi_valve_sentence' not in flags:
                    flags.append('multi_valve_sentence')
                sent = _tricuspid_clauses(sent)
                if not sent.strip():
                    continue
            kept.append(sent)
            if key not in used_keys:
                used_keys.append(key)
    return kept, used_keys, flags


def resolve_tricuspid_text(sections: dict) -> dict:
    """
    Επιλέγει το κείμενο πάνω στο οποίο θα τρέξει ο extractor.
    Τρία επίπεδα, αυστηρά ιεραρχικά — το πρώτο που δίνει αποτέλεσμα κερδίζει:

    1. TV — αν υπάρχει (μη κενό) section «Τριγλώχινα βαλβίδα». Ταυτόσημο με v5.
    2. CONCLUSIONS + COMMENTS — per-sentence.
    3. IMPORTED — «Imported Findings», per-sentence.

    Επιστρέφει: {'raw': κείμενο, 'source': ετικέτα πηγής, 'flags': [...]}
    source ∈ {'TV', 'CONCLUSIONS', 'COMMENTS', 'CONCLUSIONS+COMMENTS',
              'IMPORTED', 'none'}
    """
    raw_tv = get_sec(sections, 'TV')
    if raw_tv.strip():
        return {'raw': raw_tv, 'source': 'TV', 'flags': []}

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


# ── Βοηθητικά για την INCLUSIVE ─────────────────────────────────────────────

def _overlap(a, b) -> bool:
    """True αν τα δύο regex matches επικαλύπτονται στο κείμενο."""
    return bool(a and b and a.start() < b.end() and b.start() < a.end())


def _first_free(pat: str, t: str, blockers: list):
    """Το πρώτο match του pat που ΔΕΝ επικαλύπτει κανένα από τα blockers."""
    for m in re.finditer(pat, t):
        if not any(_overlap(m, b) for b in blockers):
            return m
    return None


def _suspect(m, t: str) -> bool:
    """Άρνηση ή ουσιαστικό άλλης δομής μέσα στο match, ή αμέσως μετά από αυτό."""
    return bool(re.search(SUSPECT_NEGATION, m.group())
                or re.search(SUSPECT_OTHER_NOUN_TR, m.group())
                or re.match(_FOLLOWED_BY, t[m.end():]))


def _anchored_m2m(m, t: str) -> bool:
    """Το «μικρού προς μετρίου» συνοδεύεται από ανεπάρκεια/διαφυγή (≤3 λέξεις);"""
    after = t[m.end():]
    before = t[:m.start()]
    return bool(re.match(r'\w*\s+(?:βαθμ\w*\s+)?(?:\w+\s+){0,3}(?:ανεπαρκ|διαφυγ)', after)
                or re.search(r'(?:ανεπαρκ|διαφυγ)\w*\s+(?:\w+\s+){0,3}$', before))


def grade_tricuspid_regurgitation(sections: dict, resolved: dict = None) -> dict:
    """
    Ανεπάρκεια τριγλώχινας — STRICT + INCLUSIVE σε ένα πέρασμα.
    Βλ. docstring του module για τη σειρά ελέγχου.
    """
    out = _blank('tricuspid_valve_regurgitation')
    resolved = resolved or resolve_tricuspid_text(sections)
    raw = resolved['raw']
    out['source'] = resolved['source']
    t = normalize(raw)
    if not t:
        return out
    M = out['matches']

    # ── Όλα τα component matches ─────────────────────────────────────────
    m_neg   = re.search(TR_NEGATION, t)
    m_comp  = re.search(TR_COMPETING_MOD, t)
    m_mild  = re.search(TR_MILD, t)
    m_m2m   = re.search(TR_MILD_TO_MOD, t)
    m_trace = re.search(TR_TRACE, t)
    m_texc  = re.search(TR_TRACE_EXCEPT, t) if m_trace else None
    m_phys  = re.search(TR_PHYSIOLOGIC, t)
    m_any   = re.search(TR_ANY_REGURG, t)
    m_pos, pos_i = None, 0
    for i, pat in enumerate(TR_POSITIVE, 1):
        m_pos = re.search(pat, t)
        if m_pos:
            pos_i = i
            break
    m_negg  = re.search(TR_NEGATION_GLOBAL, t) if m_pos else None
    m_xf    = re.search(TR_MILD_EXTRA_FWD, t)
    m_xr    = re.search(TR_MILD_EXTRA_REV, t)

    rec_neg   = _rec(M, 'negation_guard', m_neg, t, raw) if m_neg else None
    rec_comp  = _rec(M, 'competing_moderate', m_comp, t, raw) if m_comp else None
    rec_mild  = _rec(M, 'mild', m_mild, t, raw) if m_mild else None
    rec_xf    = _rec(M, 'mild_extra_forward', m_xf, t, raw) if m_xf else None
    rec_xr    = _rec(M, 'mild_extra_reverse', m_xr, t, raw) if m_xr else None
    rec_m2m   = _rec(M, 'mild_to_moderate', m_m2m, t, raw) if m_m2m else None
    rec_trace = _rec(M, 'trace', m_trace, t, raw) if m_trace else None
    if m_texc:
        _rec(M, 'trace_exception', m_texc, t, raw)
    rec_phys  = _rec(M, 'physiologic', m_phys, t, raw) if m_phys else None
    rec_pos   = _rec(M, f'positive_{pos_i}', m_pos, t, raw) if m_pos else None
    rec_negg  = _rec(M, 'negation_guard_global', m_negg, t, raw) if m_negg else None
    _ = rec_comp  # καταγράφεται μόνο για το Evidence

    # ── STRICT (ταυτόσημο με v5, βήμα-βήμα) ──────────────────────────────
    neg_fires   = bool(m_neg and not m_comp)                       # βήμα 1
    mild_fires  = bool(m_mild and not m_m2m and not m_comp)        # βήμα 2
    trace_fires = bool(m_trace and not m_texc)                     # βήμα 3α

    if neg_fires:
        out['label_strict'], dec_strict, dec_m = 0, rec_neg, m_neg
    elif mild_fires:
        out['label_strict'], dec_strict, dec_m = 0, rec_mild, m_mild
    elif trace_fires:
        out['label_strict'], dec_strict, dec_m = 0, rec_trace, m_trace
    elif m_phys:                                                   # βήμα 3β
        out['label_strict'], dec_strict, dec_m = 0, rec_phys, m_phys
    elif m_m2m and m_any:                                          # βήμα 4
        out['label_strict'], dec_strict, dec_m = 1, rec_m2m, m_m2m
    elif m_pos and not m_negg:                                     # βήμα 5
        out['label_strict'], dec_strict, dec_m = 1, rec_pos, m_pos
    elif m_pos:
        out['label_strict'], dec_strict, dec_m = 0, rec_negg, m_negg
    else:
        out['label_strict'], dec_strict, dec_m = 0, None, None

    # ── INCLUSIVE ────────────────────────────────────────────────────────
    dec_incl_m = None
    if out['label_strict'] == 1:
        out['label_incl'] = 1
        out['grade'] = 'borderline' if dec_strict is rec_m2m else 'moderate_severe'
        dec_incl, dec_incl_m = dec_strict, dec_m
    elif neg_fires:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', rec_neg
    else:
        blockers = [b for b in (m_trace, m_phys) if b]
        mi, rec_mi = None, None
        for pat, first_m, first_rec, alt_rule in (
                (TR_MILD, m_mild, rec_mild, 'mild_alt'),
                (TR_MILD_EXTRA_FWD, m_xf, rec_xf, 'mild_extra_forward_alt'),
                (TR_MILD_EXTRA_REV, m_xr, rec_xr, 'mild_extra_reverse_alt')):
            if not first_m:
                continue
            mi = _first_free(pat, t, blockers)
            if mi:
                rec_mi = (first_rec if mi.span() == first_m.span()
                          else _rec(M, alt_rule, mi, t, raw))
                break
        if mi:
            out['label_incl'], out['grade'], dec_incl, dec_incl_m = 1, 'mild', rec_mi, mi
        elif m_trace:
            out['label_incl'], out['grade'], dec_incl = 0, 'trace', rec_trace
        elif m_phys:
            out['label_incl'], out['grade'], dec_incl = 0, 'physiologic', rec_phys
        elif m_pos and m_negg:
            out['label_incl'], out['grade'], dec_incl = 0, 'none', rec_negg
        else:
            out['label_incl'], out['grade'], dec_incl = 0, 'none', None

    _finish(out, dec_strict, dec_incl)

    # ── FLAGS (ενημερωτικά — δεν αλλάζουν label) ─────────────────────────
    F = out['flags']
    if m_trace:
        F.append('tr_trace')
    if out['label_incl'] == 1 and out['label_strict'] == 0:
        F.append('tr_incl_only')
    if out['label_strict'] == 1 and _overlap(dec_m, m_trace):
        F.append('tr_trace_positive')
    if m_pos and m_negg and dec_strict is rec_negg:
        F.append('tr_negation_blocked')
    if neg_fires and (m_mild or m_xf or m_xr):
        F.append('tr_negation_vs_mild')
    if out['label_incl'] == 1 and dec_incl_m and re.search(SENTENCE_BREAK, dec_incl_m.group()):
        F.append('tr_cross_sentence')
    if dec_strict is rec_m2m and m_m2m and not _anchored_m2m(m_m2m, t):
        F.append('tr_borderline_unanchored')
    if out['grade'] == 'mild' and dec_incl_m and (_suspect(dec_incl_m, t) or m_trace or m_phys):
        F.append('tr_mild_suspect')
    if out['label_strict'] == 1 and dec_strict is rec_pos and _suspect(m_pos, t):
        F.append('tr_positive_suspect')
    if out['label_incl'] == 0 and re.search(TR_UNCOVERED, t):
        F.append('tr_mild_uncovered')
    return out


# ── Drop-in wrappers (ίδιο signature με τη v5 συνάρτηση) ─────────────────────

def get_tricuspid_regurgitation(sections: dict) -> int:
    return grade_tricuspid_regurgitation(sections)['label_strict']


def get_tricuspid_regurgitation_incl_mild(sections: dict) -> int:
    return grade_tricuspid_regurgitation(sections)['label_incl']


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
REVIEW_FLAGS = {'multi_valve_sentence',
                'tr_trace_positive', 'tr_negation_blocked', 'tr_negation_vs_mild',
                'tr_cross_sentence', 'tr_borderline_unanchored',
                'tr_mild_suspect', 'tr_positive_suspect', 'tr_mild_uncovered',
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
             'tricuspid_valve_regurgitation', 'tricuspid_valve_regurgitation_incl_mild',
             'tr_delta', 'tr_grade', 'tr_rule_strict', 'tr_rule_incl', 'tr_phrase_incl', 'tr_v5',
             'flags', 'status', 'tricuspid_text', 'tv_text',
             'conclusions_text', 'comments_text', 'imported_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 20,
                28, 36, 10, 18, 22, 22, 40, 8,
                40, 18, 70, 70, 60, 60, 60, 60],
               wrap_cols=('tricuspid_text', 'tv_text', 'conclusions_text',
                          'comments_text', 'imported_text'))
    i_flag = cols1.index('flags')
    i_dtr = cols1.index('tr_delta')
    for row in ws1.iter_rows(min_row=2):
        flags = row[i_flag].value or ''
        if any(f in REVIEW_FLAGS for f in flags.split(';') if f):
            for c in row:
                c.fill = FLAG_FILL
        if row[i_dtr].value == 1:
            row[i_dtr].font = chg_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'finding', 'rule', 'matched_phrase',
             'decisive_strict', 'decisive_incl', 'context']
    fill_sheet(ws2, cols2, evidence_rows, [18, 30, 26, 42, 15, 14, 80], wrap_cols=('context',))

    wb.save(path)


# =============================================================================
# SELF-TEST (synthetic περιπτώσεις — τρέχει πριν το batch)
# =============================================================================

def TV(text: str) -> dict:
    """Helper: sections dict με μόνο το TV section."""
    return {'TV': text} if text else {}


# (TV text, strict, incl, grade, required_flags)
SELF_TESTS = [
    # ── MODERATE / SEVERE ────────────────────────────────────────────────
    ('Μέτρια ανεπάρκεια τριγλώχινας.',            1, 1, 'moderate_severe', []),
    ('Ανεπάρκεια μετρίου βαθμού.',                1, 1, 'moderate_severe', []),
    ('Σοβαρή ανεπάρκεια τριγλώχινας.',            1, 1, 'moderate_severe', []),
    ('Ανεπάρκεια τριγλώχινας, σοβαρή.',           1, 1, 'moderate_severe', []),
    ('Σοβαρού βαθμού τριγλωχινική ανεπάρκεια.',   1, 1, 'moderate_severe', []),
    ('Μετρίου προς σοβαρού βαθμού ανεπάρκεια.',   1, 1, 'moderate_severe', []),
    # Το «ήπια» ΚΑΙ το «μέτρια» υπάρχουν → το competing check παρακάμπτει το mild
    ('Μέτρια ανεπάρκεια. Μικρή διάταση δακτυλίου.', 1, 1, 'moderate_severe', []),

    # ── MILD (v5 regex) ──────────────────────────────────────────────────
    ('Ήπια ανεπάρκεια.',                          0, 1, 'mild', ['tr_incl_only']),
    ('Μικρή ανεπάρκεια τριγλώχινας.',             0, 1, 'mild', []),
    ('Μικρού βαθμού ανεπάρκεια.',                 0, 1, 'mild', []),
    ('Ανεπάρκεια μικρού βαθμού.',                 0, 1, 'mild', []),
    ('Διαφυγή ήπια.',                             0, 1, 'mild', []),
    # «ήπιου» καλύπτεται ήδη από το `[ήη]πια?` του v5 (χωρίς όριο λέξης)
    ('Ήπιου βαθμού ανεπάρκεια.',                  0, 1, 'mild', []),
    # ── MILD (προσθήκη: ελαφρά / ελάχιστη) ───────────────────────────────
    ('Ελαφρά ανεπάρκεια.',                        0, 1, 'mild', ['tr_incl_only']),
    ('Ελάχιστη διαφυγή.',                         0, 1, 'mild', []),
    ('Διαφυγή ελάχιστη.',                         0, 1, 'mild', []),
    # Φραγμένο {0,3}: δεν περνά την τελεία → μένει το ίχνος
    ('Ελάχιστη διάταση. Ίχνος ανεπάρκειας.',      0, 0, 'trace', ['tr_trace']),

    # ── ΙΧΝΟΣ / ΦΥΣΙΟΛΟΓΙΚΗ ──────────────────────────────────────────────
    ('Ίχνος ανεπάρκειας.',                        0, 0, 'trace', ['tr_trace']),
    ('Ίχνος διαφυγής.',                           0, 0, 'trace', ['tr_trace']),
    ('Φυσιολογική διαφυγή.',                      0, 0, 'physiologic', []),
    # Το unbounded mild του v5 περνά την τελεία και καταλήγει ΜΕΣΑ στο ίχνος
    # → επικάλυψη → κερδίζει το ίχνος
    ('Μικρή διάταση δακτυλίου. Ίχνος ανεπάρκειας.', 0, 0, 'trace', ['tr_trace']),
    ('Μικρή διάταση δακτυλίου, φυσιολογική διαφυγή.', 0, 0, 'physiologic', []),
    # Mild και ίχνος σε ΧΩΡΙΣΤΕΣ φράσεις → mild, με flag
    ('Ήπια ανεπάρκεια. Ίχνος διαφυγής.',          0, 1, 'mild', ['tr_trace', 'tr_mild_suspect']),
    # Ίχνος + σοβαρή: ο trace guard του v5 παρακάμπτεται (σοβαρ) → 1/1
    ('Σοβαρή ανεπάρκεια. Ίχνος διαφυγής.',        1, 1, 'moderate_severe', ['tr_trace']),

    # ── BORDERLINE ───────────────────────────────────────────────────────
    ('Μικρού προς μετρίου βαθμού ανεπάρκεια.',    1, 1, 'borderline', []),
    ('Ήπια προς μέτρια ανεπάρκεια.',              1, 1, 'borderline', []),
    # Στο TR το «έως» δίνει 1 (μέσω competing check + positive) — σε αντίθεση με MR/AR
    ('Ήπια έως μέτρια ανεπάρκεια.',               1, 1, 'moderate_severe', []),

    # ── ΡΗΤΗ ΑΡΝΗΣΗ ──────────────────────────────────────────────────────
    ('Χωρίς ανεπάρκεια.',                         0, 0, 'none', []),
    ('Δεν παρατηρείται διαφυγή.',                 0, 0, 'none', []),
    ('Ήπια διάταση δακτυλίου χωρίς ανεπάρκεια.',  0, 0, 'none', ['tr_negation_vs_mild']),
    # Η άρνηση του βήματος 1 περνά την τελεία → μηδενίζει και το mild (απόφαση: 0)
    ('Χωρίς διάταση δακτυλίου. Ήπια ανεπάρκεια.', 0, 0, 'none', ['tr_negation_vs_mild']),

    # ── ΓΝΩΣΤΑ ΠΡΟΒΛΗΜΑΤΑ v5 (πραγματική συμπεριφορά + flag) ─────────────
    # ΓΝΩΣΤΟ FN: το global negation του βήματος 5 περνά την τελεία
    ('Χωρίς διάταση δακτυλίου. Σοβαρή ανεπάρκεια.', 0, 0, 'none', ['tr_negation_blocked']),
    # ΓΝΩΣΤΟ FP: ο trace guard παρακάμπτεται από ΟΠΟΙΟΔΗΠΟΤΕ «μετρ», και το
    # positive 4 συνδέει «ανεπάρκειας. μέτρια» → 1
    ('Ίχνος ανεπάρκειας. Μέτρια διάταση δακτυλίου.', 1, 1, 'moderate_severe',
     ['tr_trace_positive', 'tr_cross_sentence', 'tr_positive_suspect']),
    # ΓΝΩΣΤΟ FP: το «μέτρια» της διάτασης δίνει competing + positive 4
    ('Ήπια ανεπάρκεια. Μέτρια διάταση δακτυλίου.', 1, 1, 'moderate_severe',
     ['tr_cross_sentence', 'tr_positive_suspect']),
    # ΓΝΩΣΤΟ FP: το «μικρού προς μετρίου» αφορά τη διάταση, όχι την ανεπάρκεια
    ('Μικρού προς μετρίου βαθμού διάταση δακτυλίου. Ήπια ανεπάρκεια.', 1, 1, 'borderline',
     ['tr_borderline_unanchored']),
    # ΓΝΩΣΤΟ FP: η βαρύτητα αφορά τη διάταση
    ('Σοβαρή διάταση δακτυλίου με ανεπάρκεια.',   1, 1, 'moderate_severe', ['tr_positive_suspect']),

    # ── SUSPECT ──────────────────────────────────────────────────────────
    # Το «ήπια» αφορά τη διάταση, το v5 mild το πιάνει → INCLUSIVE=1, flag
    ('Ήπια διάταση δακτυλίου με ανεπάρκεια.',     0, 1, 'mild', ['tr_mild_suspect']),
    ('Ανεπάρκεια, ήπια διάταση δακτυλίου.',       0, 1, 'mild', ['tr_mild_suspect']),

    # ── ΑΚΑΛΥΠΤΟΙ ΟΡΟΙ ───────────────────────────────────────────────────
    ('Ελαφριά ανεπάρκεια.',                       0, 0, 'none', ['tr_mild_uncovered']),
    ('Αμελητέα ανεπάρκεια.',                      0, 0, 'none', ['tr_mild_uncovered']),

    # ── ΧΩΡΙΣ ΕΥΡΗΜΑ / ΚΕΝΟ ──────────────────────────────────────────────
    ('Καλή σύγκλειση των γλωχίνων.',              0, 0, 'none', []),
    ('',                                          0, 0, 'none', []),
]

# (sections, strict, incl, grade, source, required_flags)
SELF_TESTS_FALLBACK = [
    # Εύρημα μόνο στα Συμπεράσματα
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια τριγλώχινας.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', ['fallback_source']),
    # Εύρημα μόνο στη Διάγνωση (→ COMMENTS)
    ({'COMMENTS': 'Διάγνωση: Ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'COMMENTS', ['fallback_source']),
    # Άλλη βαλβίδα → αγνοείται
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 'none', []),
    # Σκέτο εύρημα χωρίς όργανο → αμφίσημο
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια.'},
     0, 0, 'none', 'none', []),
    # Multi-valve, σειρά 1: τριγλώχινα πρώτα
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια τριγλώχινας και ήπια ανεπάρκεια μιτροειδούς.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Multi-valve, σειρά 2: χωρίς φιλτράρισμα το «σοβαρή» της μιτροειδούς θα έδινε TR=1
    ({'CONCLUSIONS': 'Σοβαρή ανεπάρκεια μιτροειδούς και ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'CONCLUSIONS', ['multi_valve_sentence']),
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής και ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Clause χωρίς βαλβίδα κληρονομεί το προηγούμενο όργανο
    ({'CONCLUSIONS': 'Ανεπάρκεια τριγλώχινας, μετρίου βαθμού, και ήπια ανεπάρκεια μιτροειδούς.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', ['multi_valve_sentence']),
    # Επιλογή της σχετικής πρότασης μέσα από πολλές
    ({'CONCLUSIONS': 'Φυσιολογική μιτροειδής βαλβίδα. Ήπια ανεπάρκεια τριγλώχινας. '
                     'Φυσιολογική συστολική λειτουργία.'},
     0, 1, 'mild', 'CONCLUSIONS', []),
    # Ίχνος στα Συμπεράσματα
    ({'CONCLUSIONS': 'Ίχνος ανεπάρκειας τριγλώχινας.'},
     0, 0, 'trace', 'CONCLUSIONS', ['tr_trace']),
    # Αγγλικός όρος οργάνου
    ({'CONCLUSIONS': 'Σοβαρή ανεπάρκεια (tricuspid).'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', []),
    # Συντομογραφία άλλης βαλβίδας (MV) μέσα σε multi-valve
    ({'COMMENTS': 'Σοβαρή ανεπάρκεια MV και ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'COMMENTS', ['multi_valve_sentence']),
    # Συντομογραφία TV → θεωρείται τριγλώχινα
    ({'CONCLUSIONS': 'Σοβαρή ανεπάρκεια TV.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', ['fallback_source']),
    # Αμφίσημη συντομογραφία TR → ΔΕΝ θεωρείται τριγλώχινα
    ({'CONCLUSIONS': 'Μέτρια TR.'},
     0, 0, 'none', 'none', []),
    # ΥΠΑΡΧΕΙ TV section → ΔΕΝ ενεργοποιείται fallback
    ({'TV': 'Καλή σύγκλειση των γλωχίνων.', 'CONCLUSIONS': 'Σοβαρή ανεπάρκεια τριγλώχινας.'},
     0, 0, 'none', 'TV', []),
    # Κενό / whitespace TV section → fallback
    ({'TV': '   ', 'CONCLUSIONS': 'Σοβαρή ανεπάρκεια τριγλώχινας.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', ['fallback_source']),
    # ── ΕΠΙΠΕΔΟ 3: Imported Findings ─────────────────────────────────────
    ({'IMPORTED': 'Μέτρια ανεπάρκεια τριγλώχινας.'},
     1, 1, 'moderate_severe', 'IMPORTED', ['fallback_source', 'imported_findings']),
    ({'CONCLUSIONS': 'Τυπική μελέτη.', 'IMPORTED': 'Ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'IMPORTED', ['imported_findings']),
    ({'CONCLUSIONS': 'Σοβαρή ανεπάρκεια τριγλώχινας.', 'IMPORTED': 'Ήπια ανεπάρκεια τριγλώχινας.'},
     1, 1, 'moderate_severe', 'CONCLUSIONS', []),
    ({'TV': 'Καλή σύγκλειση.', 'IMPORTED': 'Σοβαρή ανεπάρκεια τριγλώχινας.'},
     0, 0, 'none', 'TV', []),
    ({'IMPORTED': 'Σοβαρή ανεπάρκεια μιτροειδούς και ήπια ανεπάρκεια τριγλώχινας.'},
     0, 1, 'mild', 'IMPORTED', ['multi_valve_sentence']),
    ({'IMPORTED': 'Φυσιολογική συστολική λειτουργία αριστερής κοιλίας.'},
     0, 0, 'none', 'none', []),
    # Τίποτα πουθενά
    ({'CONCLUSIONS': 'Τυπική μελέτη.'},
     0, 0, 'none', 'none', []),
]

# Θραύσματα για το fuzz test (#2): τυχαίοι συνδυασμοί τους πρέπει πάντα να δίνουν
# STRICT == v5 και INCLUSIVE >= STRICT
FUZZ_FRAGMENTS = [t for t, *_ in SELF_TESTS if t] + [
    'Διάταση δακτυλίου.', 'Μέτρια διάταση.', 'Σοβαρή πνευμονική υπέρταση.',
    'Χωρίς στένωση.', 'Φυσιολογική κινητικότητα των γλωχίνων.',
    'PASP 45 mmHg.', 'Διάμετρος δακτυλίου 3.8 cm.', 'Καλώδιο βηματοδότη.',
]


def _v5_constants_in_source() -> set:
    """Όλα τα string literals της αυτούσιας v5 συνάρτησης (με implicit concatenation)."""
    src = textwrap.dedent(inspect.getsource(get_tricuspid_regurgitation_v5))
    return [n.value for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def run_self_test() -> bool:
    ok_all = True
    logger.info("SELF-TEST")

    # ── 0. Κάθε σταθερά TR_* υπάρχει αυτούσια στον κώδικα της v5 ──────────
    v5_literals = _v5_constants_in_source()
    for name, pat in V5_CONSTANTS.items():
        same = pat in v5_literals
        ok_all &= same
        if not same:
            logger.info(f"  [FAIL ] #0 η σταθερά {name} ΔΕΝ υπάρχει αυτούσια στη v5")
    n_comp = v5_literals.count(TR_COMPETING_MOD)
    ok_all &= (n_comp == 2)
    logger.info(f"  [{'PASS' if ok_all else 'FAIL':5}] #0 όλες οι {len(V5_CONSTANTS)} σταθερές "
                f"αυτούσιες στη v5 (competing check ×{n_comp}, αναμένεται ×2)")

    # ── 1. Synthetic περιπτώσεις ─────────────────────────────────────────
    cases = [(TV(tv), a, b, c, 'TV' if tv else 'none', fl) for tv, a, b, c, fl in SELF_TESTS]
    cases += SELF_TESTS_FALLBACK

    n_pass = 0
    for secs, e_s, e_i, e_g, e_src, e_flags in cases:
        resolved = resolve_tricuspid_text(secs)
        tr = grade_tricuspid_regurgitation(secs, resolved)
        tr_v5 = get_tricuspid_regurgitation_v5(secs)

        v5_ok = resolved['source'] != 'TV' or tr['label_strict'] == tr_v5
        all_flags = resolved['flags'] + tr['flags']
        flags_ok = all(f in all_flags for f in e_flags)

        ok = (tr['label_strict'] == e_s and tr['label_incl'] == e_i and tr['grade'] == e_g and
              resolved['source'] == e_src and v5_ok and flags_ok and
              tr['label_incl'] >= tr['label_strict'])
        n_pass += ok
        ok_all &= ok

        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
        logger.info(
            f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
            f"          → [{resolved['source']}] "
            f"TR {tr['label_strict']}/{tr['label_incl']} ({tr['grade']})"
            f"{'  flags=' + ';'.join(all_flags) if all_flags else ''}"
            f"{'' if ok else f'  (αναμενόταν [{e_src}] TR {e_s}/{e_i} {e_g}, flags⊇{e_flags}, v5={tr_v5})'}")

    # ── 2. Fuzz: τυχαίοι συνδυασμοί προτάσεων — STRICT == v5, INCL >= STRICT ─
    rng = random.Random(12345)
    n_fuzz, bad = 3000, []
    for _ in range(n_fuzz):
        text = ' '.join(rng.sample(FUZZ_FRAGMENTS, rng.randint(1, 4)))
        secs = {'TV': text}
        tr = grade_tricuspid_regurgitation(secs)
        if tr['label_strict'] != get_tricuspid_regurgitation_v5(secs) or \
                tr['label_incl'] < tr['label_strict']:
            bad.append(text)
    fuzz_ok = not bad
    ok_all &= fuzz_ok
    logger.info(f"  [{'PASS' if fuzz_ok else 'FAIL':5}] #2 fuzz: {n_fuzz} τυχαίοι συνδυασμοί, "
                f"STRICT == v5 και INCLUSIVE >= STRICT"
                f"{'' if fuzz_ok else f' — {len(bad)} αποτυχίες, π.χ. {bad[0]!r}'}")

    total = len(cases) + 2
    passed = n_pass + int(n_comp == 2 and all(p in v5_literals for p in V5_CONSTANTS.values())) + int(fuzz_ok)
    logger.info(f"SELF-TEST: {passed}/{total} — {'ΟΚ' if ok_all else 'ΑΠΕΤΥΧΕ'}")
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
        resolved = resolve_tricuspid_text(sections)
        tr = grade_tricuspid_regurgitation(sections, resolved)
        tr_v5 = get_tricuspid_regurgitation_v5(sections)

        src = resolved['source']
        flags = list(resolved['flags']) + tr['flags']

        if src == 'TV':
            if tr['label_strict'] != tr_v5:
                flags.append('strict_vs_v5_mismatch')
        else:
            if tr['label_strict'] > tr_v5:
                flags.append('fallback_gain')

        if tr['label_incl'] < tr['label_strict']:
            flags.append('non_monotonic')

        if src == 'TV':
            status = 'ok'
        elif src == 'none':
            status = 'no_tricuspid_text'
        else:
            status = 'fallback'

        label_rows.append({
            'exam_id':                                 e['exam_id'],
            'source':                                  src,
            'tricuspid_valve_regurgitation':           tr['label_strict'],
            'tricuspid_valve_regurgitation_incl_mild': tr['label_incl'],
            'tr_delta':                                tr['label_incl'] - tr['label_strict'],
            'tr_grade':                                tr['grade'],
            'tr_rule_strict':                          tr['rule_strict'],
            'tr_rule_incl':                            tr['rule_incl'],
            'tr_phrase_incl':                          original_phrase(tr['raw_incl'], tr['phrase_incl']),
            'tr_v5':                                   tr_v5,
            'flags':                                   ';'.join(flags),
            'status':                                  status,
            'tricuspid_text':                          resolved['raw'],
            'tv_text':                                 get_sec(sections, 'TV'),
            'conclusions_text':                        get_sec(sections, 'CONCLUSIONS'),
            'comments_text':                           get_sec(sections, 'COMMENTS'),
            'imported_text':                           get_sec(sections, 'IMPORTED'),
            'report_path':                             e['report_path'],
        })

        for m in tr['matches']:
            evidence_rows.append({
                'exam_id':         e['exam_id'],
                'finding':         tr['finding'],
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
        logger.info(f"\n  {'Finding':<42} {'Pos':>5} {'Total':>7} {'%':>6}")
        logger.info(f"  {'-'*62}")
        for col in ('tricuspid_valve_regurgitation', 'tricuspid_valve_regurgitation_incl_mild'):
            pos_n = sum(r[col] == 1 for r in ok_rows)
            logger.info(f"  {col:<42} {pos_n:>5} {n:>7} {100 * pos_n / n:>5.1f}%")

        d_tr = sum(r['tr_delta'] == 1 for r in ok_rows)
        logger.info(f"\nΕπιπλέον θετικές λόγω mild: +{d_tr} ({100 * d_tr / n:.1f}%)")
        n_extra = sum(r['tr_rule_incl'].startswith('mild_extra') for r in ok_rows)
        logger.info(f"  από αυτές λόγω «ελαφρά/ελάχιστη» (mild_extra): {n_extra}")

        src_dist = {}
        for r in ok_rows:
            src_dist[r['source']] = src_dist.get(r['source'], 0) + 1
        logger.info("\nΠηγή κειμένου:")
        for s, c in sorted(src_dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {s:<24} {c:>6} ({100 * c / n:.1f}%)")

        n_fb = sum(r['source'] not in ('TV', 'none') for r in ok_rows)
        if n_fb:
            g_s = sum(r['source'] not in ('TV', 'none') and r['tricuspid_valve_regurgitation'] == 1
                      for r in ok_rows)
            g_i = sum(r['source'] not in ('TV', 'none') and r['tricuspid_valve_regurgitation_incl_mild'] == 1
                      for r in ok_rows)
            logger.info(f"\nFallback (χωρίς TV section): {n_fb} εξετάσεις")
            logger.info(f"  νέες θετικές TR: {g_s} strict / {g_i} incl_mild")

        n_tv  = sum(r['source'] == 'TV' for r in ok_rows)
        n_mis = sum('strict_vs_v5_mismatch' in r['flags'] for r in ok_rows)
        n_mon = sum('non_monotonic' in r['flags'] for r in ok_rows)
        if n_mis:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mis} εξετάσεις όπου η STRICT διαφέρει από το v5!")
        else:
            logger.info(f"\nSanity check: η STRICT ταυτίζεται με το v5 και στις {n_tv} "
                        f"εξετάσεις με TV section ✓")
        if n_mon:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mon} εξετάσεις με STRICT=1 αλλά INCLUSIVE=0!")
        else:
            logger.info("Sanity check: INCLUSIVE >= STRICT παντού ✓")

        dist = {}
        for r in ok_rows:
            dist[r['tr_grade']] = dist.get(r['tr_grade'], 0) + 1
        logger.info("\nΚατανομή tr_grade:")
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
                logger.info(f"  {f:<26} {c:>6}{mark}")

    logger.info(f"\nExcel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/tricuspid_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
