r"""
mitral_valve_v6x.py
===================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για τα findings
της ΜΙΤΡΟΕΙΔΟΥΣ βαλβίδας:

  mitral_stenosis        (στένωση μιτροειδούς)
  mitral_regurgitation   (ανεπάρκεια μιτροειδούς)

Για ΚΑΘΕ finding παράγονται ΔΥΟ labels:

  ΑΝΑΛΥΣΗ STRICT   — <finding>
      Θετικά ΜΟΝΟ μέτριου/σοβαρού βαθμού. Ακριβώς η συμπεριφορά του v5.

  ΑΝΑΛΥΣΗ INCLUSIVE — <finding>_incl_mild
      Θετικά ΚΑΙ τα ήπια/μικρού βαθμού (mild + moderate + severe).
      Το ΙΧΝΟΣ δεν είναι ποτέ θετικό — ούτε εδώ.

ΒΑΣΙΚΗ ΑΡΧΗ ΥΛΟΠΟΙΗΣΗΣ
  Κανένα επιβεβαιωμένο regex του v5 δεν τροποποιήθηκε. Τα patterns αντιγράφηκαν
  ΑΥΤΟΥΣΙΑ ως σταθερές. Η μόνη δομική αλλαγή είναι ότι το mild guard της
  ανεπάρκειας, που στο v5 ήταν ΕΝΑ regex με τρία alternations
  (mild-forward | mild-reverse | ίχνος), σπάει σε τρεις σταθερές:

      MR_MILD_FWD | MR_MILD_REV | MR_TRACE   ==  το αρχικό mild_pat του v5

  Η ένωσή τους με '|' δίνει χαρακτήρα-προς-χαρακτήρα το αρχικό string, οπότε η
  STRICT ανάλυση παραμένει ταυτόσημη. Ο διαχωρισμός χρειάζεται μόνο ώστε στην
  INCLUSIVE να γίνεται θετικό το mild ΧΩΡΙΣ να γίνεται θετικό το ίχνος.

ΣΕΙΡΑ ΕΛΕΓΧΟΥ

  mitral_stenosis
    1. Prosthetic guard (μηχανική/προσθετική) → 0 και στις δύο αναλύσεις,
       εκτός ρητής αναφοράς μέτριας/σοβαρής  [ΑΜΕΤΑΒΛΗΤΟ κατ' απαίτηση]
    2. Borderline «μικρού προς μετρίου»      → 1 / 1
    3. Mild                                   → 0 / 1
    4. Positive (μέτρια/σοβαρή)               → 1 / 1

  mitral_regurgitation
    STRICT    : borderline → 1 | (mild Ή ίχνος) → 0 | positive → 1
    INCLUSIVE : borderline → 1 | mild → 1 | positive → 1 | ίχνος → 0

    Η σειρά της INCLUSIVE βάζει το ίχνος ΤΕΛΕΥΤΑΙΟ, ώστε report που αναφέρει
    «ίχνος διαφυγής» μαζί με «σοβαρή ανεπάρκεια» να μη μηδενίζεται.
    Έτσι εξασφαλίζεται INCLUSIVE >= STRICT πάντα (ελέγχεται ανά εξέταση).

ΠΗΓΗ ΚΕΙΜΕΝΟΥ — MV με fallback
  1. Αν υπάρχει (μη κενό) section MV → χρησιμοποιείται αυτούσιο, όπως στο v5.
     Τα Συμπεράσματα/Σχόλια ΑΓΝΟΟΥΝΤΑΙ σε αυτή την περίπτωση.
  2. Αν ΛΕΙΠΕΙ ή είναι κενό → FALLBACK σε Συμπεράσματα + Σχόλια/Διάγνωση:
     - σάρωση ανά πρόταση
     - κρατιούνται ΜΟΝΟ προτάσεις με ρητή αναφορά σε μιτροειδή — είτε ολογράφως
       (μιτροειδής / μιτροειδικός / mitral) είτε με συντομογραφία (MV, MVA, MVR)
       (σκέτο «μέτρια ανεπάρκεια» χωρίς όργανο αγνοείται ως αμφίσημο)
     - πρόταση που αναφέρει ΚΑΙ άλλη βαλβίδα → clause-level φιλτράρισμα,
       κρατιούνται μόνο τα clauses της μιτροειδούς + flag multi_valve_sentence
  3. Αν ΟΥΤΕ εκεί βρεθεί τίποτα → ΤΡΙΤΟ ΕΠΙΠΕΔΟ: η παράγραφος «Imported Findings»
     (υπογραμμισμένος header, ίδιο format με τις ανατομικές ενότητες), με το ΙΔΙΟ
     per-sentence φιλτράρισμα — το περιεχόμενό της μπορεί να καλύπτει πολλά
     όργανα μαζί, οπότε δεν λαμβάνεται αυτούσια. Flag: imported_findings.

  Τα τρία επίπεδα είναι αυστηρά ιεραρχικά: το πρώτο που δίνει αποτέλεσμα κερδίζει
  και τα επόμενα δεν εξετάζονται.

  Η στήλη `source` δείχνει την πηγή ανά εξέταση: MV | CONCLUSIONS | COMMENTS |
  CONCLUSIONS+COMMENTS | IMPORTED | none.

  ΣΥΝΕΠΕΙΑ ΓΙΑ ΤΟ SANITY CHECK: η ταύτιση STRICT ↔ v5 απαιτείται ΜΟΝΟ στις
  εξετάσεις με source == 'MV'. Στα fallback rows το v5 δεν είχε καθόλου πηγή,
  οπότε κάθε διαφορά είναι κέρδος (flag `fallback_gain`), όχι σφάλμα.

ΣΚΟΠΟΣ
  Πρόχειρο check ορθότητας των ground truth labels, ΟΧΙ το τελικό CSV του
  evaluation.

FLAGS (στήλη flags) — οι γραμμές με flag ΕΛΕΓΧΟΥ χρωματίζονται πορτοκαλί:
  ms_incl_only / mr_incl_only      μόνο στην INCLUSIVE θετικό (αναμενόμενο delta — χωρίς χρώμα)
  mr_trace                         εντοπίστηκε ίχνος (χωρίς χρώμα)
  fallback_source                  λείπει MV section → χρήση εναλλακτικής πηγής
  imported_findings                η πηγή ήταν η παράγραφος «Imported Findings»
  fallback_gain                    το fallback έδωσε θετικό που το v5 έχανε
  multi_valve_sentence             πρόταση με >1 βαλβίδα → clause φιλτράρισμα [ΕΛΕΓΧΟΣ]
  ms_prosthetic_guard              ενεργοποιήθηκε ο prosthetic guard         [ΕΛΕΓΧΟΣ]
  mr_strict_blocked                INCLUSIVE moderate/severe αλλά STRICT=0   [ΕΛΕΓΧΟΣ]
  strict_vs_v5_mismatch            η STRICT διαφέρει από το v5 — ΣΦΑΛΜΑ      [ΕΛΕΓΧΟΣ]
  non_monotonic                    STRICT=1 αλλά INCLUSIVE=0 — ΣΦΑΛΜΑ        [ΕΛΕΓΧΟΣ]

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά pattern που ταίριαξε (finding, κανόνας, αν καθόρισε το label)

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
logger = logging.getLogger("mitral")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από ground_truth_extractor)
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
    # ταιριάζει και στο 'imported findings'. Επειδή τα dicts της Python είναι
    # insertion-ordered και το πρώτο match κερδίζει, αν το IMPORTED μπει μετά
    # το FINDINGS δεν θα χρησιμοποιηθεί ΠΟΤΕ.
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

def get_mitral_stenosis_v5(sections: dict) -> int:
    """
    Στένωση μιτροειδούς. Μόνο μέτριου/σοβαρού → 1. Μικρή/ήπια → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.
    """
    t = normalize(get_sec(sections, 'MV'))
    if not t:
        return 0

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

    if re.search(
        r'μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου\s+(?:βαθμο[ύυ]\s+)?στ[έε]νωσ'
        r'|στ[έε]νωσ\w*\s+(?:ρευματικ[ήη][σς]?\s+αιτιολογ[ίι]α[σς]\s+)?'
        r'(?:\([^)]*\)\s*)?μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου', t
    ):
        return 1

    if re.search(r'μικρ[ήη]\s+προ[σς]\s+μ[έε]τρια\s+στ[έε]νωσ', t):
        return 1

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

    pos_patterns = [
        r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?στ[έε]νωσ',
        r'στ[έε]νωσ.*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]',
        r'(?:μ[έε]τρια|σοβαρ[ήη])\s+στ[έε]νωσ',
        r'στ[έε]νωσ.*?(?:μ[έε]τρια|σοβαρ[ήη])',
    ]
    for pat in pos_patterns:
        if re.search(pat, t):
            return 1

    return 0


def get_mitral_regurgitation_v5(sections: dict) -> int:
    """
    Ανεπάρκεια μιτροειδούς. ΜΟΝΟ μετρίου/σοβαρού → 1. Μικρή/ήπια/ίχνος → 0.
    Αξιολογεί ΜΟΝΟ λεκτικά patterns — χωρίς numeric path.
    """
    t = normalize(get_sec(sections, 'MV'))
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
        r'|(?:ανεπ[εάα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    if re.search(mild_pat, t):
        return 0

    pos_pat = (
        r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
    )
    if re.search(pos_pat, t):
        return 1

    return 0


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v5 (μην τα επεξεργαστείς εδώ)
# =============================================================================

# ── ΣΤΕΝΩΣΗ ΜΙΤΡΟΕΙΔΟΥΣ ──────────────────────────────────────────────────────
MS_PROSTHETIC = (
    r'(?:μηχανικ[ήη]|προσθετικ[ήη][σς]?|μεταλλικ[ήη]|βιοπροσθετικ[ήη][σς]?)\s+'
    r'(?:βαλβ[ίι]δ|μιτροειδ)'
)
MS_PROSTHETIC_EXPLICIT = (
    r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?στ[έε]νωσ'
    r'|στ[έε]νωσ.*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]'
    r'|(?:μ[έε]τρια|σοβαρ[ήη])\s+στ[έε]νωσ'
)
MS_BORDERLINE_1 = (
    r'μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου\s+(?:βαθμο[ύυ]\s+)?στ[έε]νωσ'
    r'|στ[έε]νωσ\w*\s+(?:ρευματικ[ήη][σς]?\s+αιτιολογ[ίι]α[σς]\s+)?'
    r'(?:\([^)]*\)\s*)?μικρο[ύυ]\s+προ[σς]\s+μετρ[ίι]ου'
)
MS_BORDERLINE_2 = r'μικρ[ήη]\s+προ[σς]\s+μ[έε]τρια\s+στ[έε]νωσ'
MS_MILD_1 = (
    r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?)\s+'
    r'(?:βαθμο[ύυ]\s+)?(?:περιορισμ[οό][σς]?\s+στη\s+δι[αά]νοιξη|στ[έε]νωσ)'
)
MS_MILD_2 = (
    r'στ[έε]νωσ\w*\s+(?:\([^)]*\)\s+)?(?:ρευματικ[ήη][σς]?\s+αιτιολογ[ίι]α[σς]\s+)?'
    r'(?:μικρο[ύυ]\s+βαθμο[ύυ]|μικρ[ήη](?!\s+προ[σς]))'
)
MS_POSITIVE = [
    r'(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ].*?στ[έε]νωσ',
    r'στ[έε]νωσ.*?(?:μετρ[ίι]ου|σοβαρο[ύυ])\s+βαθμο[ύυ]',
    r'(?:μ[έε]τρια|σοβαρ[ήη])\s+στ[έε]νωσ',
    r'στ[έε]νωσ.*?(?:μ[έε]τρια|σοβαρ[ήη])',
]

# ── ΑΝΕΠΑΡΚΕΙΑ ΜΙΤΡΟΕΙΔΟΥΣ ───────────────────────────────────────────────────
MR_BORDERLINE = (
    r'(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
    r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[οόύηή]\w*|[ήη]πι\w*)\s+(?:προ[σς]|έως|[-–/])\s+(?:μετρ[ίι]\w*|μ[έε]τρι\w*)(?:\s+βαθμο[ύυ])?'
)

# Τα τρία alternations του v5 mild_pat, σπασμένα ώστε το ΙΧΝΟΣ να μένει χωριστά.
# MR_MILD_FWD + '|' + MR_MILD_REV + '|' + MR_TRACE  ==  το αρχικό mild_pat.
MR_MILD_FWD = r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
MR_MILD_REV = r'(?:ανεπ[εάα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
MR_TRACE    = r'[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'

MR_POSITIVE = (
    r'(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
    r'|(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)[,\s]+(?:\w+[,\s]+){0,3}(?:μετρ[ίι]\w*|μ[έε]τρι\w*|σοβαρ\w*|σημαντικ\w*)(?:\s+(?:προ[σς]|έως|[-–/])\s+(?:σοβαρ\w*|σημαντικ\w*))?(?:\s+βαθμο[ύυ])?'
)

# Ανασύνθεση του v5 mild_pat από τα τρία κομμάτια — ελέγχεται στο self-test.
MR_MILD_PAT_V5 = MR_MILD_FWD + '|' + MR_MILD_REV + '|' + MR_TRACE


# =============================================================================
# CORE LOGIC
# =============================================================================

def _context(text: str, m, before=40, after=30) -> str:
    return text[max(0, m.start() - before): m.end() + after]


def _rec(matches: list, rule: str, m, text: str, raw: str) -> dict:
    rec = {'rule': rule, 'match': m.group(), 'context': _context(text, m),
           'raw': raw, 'decisive_strict': 0, 'decisive_incl': 0}
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
# ΕΠΙΛΟΓΗ ΠΗΓΗΣ ΚΕΙΜΕΝΟΥ — MV, με fallback σε Συμπεράσματα / Σχόλια / Διάγνωση
# =============================================================================

# Πρόταση που αφορά τη ΜΙΤΡΟΕΙΔΗ.
# - μιτροειδ  : μιτροειδής / μιτροειδούς / μιτροειδικός / μιτροειδικού κ.λπ.
# - mitral    : αγγλικός όρος
# - mv        : η συντομογραφία, όπως εμφανίζεται συχνά στα Σχόλια
# - mva / mvr : mitral valve area / mitral valve replacement — επίσης μιτροειδή
# Τα \b εμποδίζουν false positives: το \bmv\b ΔΕΝ πιάνει το "mva", και κανένα
# από αυτά δεν πιάνεται μέσα σε μεγαλύτερη λέξη.
# ΣΗΜΕΙΩΣΗ: το normalize() έχει ήδη κάνει lowercase, γι' αυτό τα patterns είναι πεζά.
MITRAL_CTX = r'μιτροειδ|\bmitral\b|\bmv\b|\bmva\b|\bmvr\b'
# Πρόταση που αφορά ΑΛΛΗ βαλβίδα → multi-valve, χρειάζεται manual review.
# ΔΕΝ προστίθενται εδώ οι συντομογραφίες AV / TV / PV: στην καρδιολογία το "AV"
# σημαίνει συνήθως atrioventricular (AV block, AV node), όχι aortic valve. Ένα
# λανθασμένο match εδώ θα απέρριπτε clause της μιτροειδούς → false negative.
OTHER_VALVE_CTX = r'αορτικ|αορτ[ηή]|τριγλωχ|πνευμονικ|\baortic\b|\btricuspid\b'
# Διαχωρισμός σε προτάσεις: τελεία (όχι δεκαδική), άνω τελεία, αλλαγή γραμμής
MV_SENT_SPLIT = r'\.(?!\d)|;|\n'

# Επίπεδο 2 του fallback
FALLBACK_KEYS = ('CONCLUSIONS', 'COMMENTS')
# Επίπεδο 3 του fallback — εξετάζεται ΜΟΝΟ αν το επίπεδο 2 δεν έδωσε τίποτα
IMPORTED_KEYS = ('IMPORTED',)

# Διαχωρισμός πρότασης σε clauses — μόνο για multi-valve προτάσεις
CLAUSE_SPLIT = r',|·|\sκαι\s|\sκαθ[ωώ]ς\s|/'


def _mitral_clauses(sent: str) -> str:
    """
    Από πρόταση που αναφέρει ΠΑΝΩ ΑΠΟ ΜΙΑ βαλβίδα, κρατά μόνο τα clauses που
    αφορούν τη μιτροειδή.

    Απαραίτητο γιατί τα bidirectional patterns ανεπάρκειας/στένωσης ταιριάζουν
    severity με όργανο σε απόσταση έως 3 λέξεων. Χωρίς αυτό, το
    «Μέτρια ανεπάρκεια μιτροειδούς και ήπια αορτικής» μηδενίζεται: το «ήπια»
    της αορτικής πιάνεται από το mild guard της μιτροειδούς.

    Ανάθεση clause → όργανο:
      1. Clause που ονομάζει βαλβίδα ανήκει σε αυτήν.
      2. Clause χωρίς όνομα βαλβίδας κληρονομεί το ΠΡΟΗΓΟΥΜΕΝΟ όργανο
         («Ανεπάρκεια μιτροειδούς, μετρίου βαθμού» → και τα δύο clauses μιτροειδής).
      3. Αρχικά clauses χωρίς προηγούμενο όργανο κληρονομούν το ΕΠΟΜΕΝΟ.
    """
    parts = [p.strip() for p in re.split(CLAUSE_SPLIT, sent, flags=re.IGNORECASE) if p.strip()]
    if len(parts) < 2:
        return sent

    owners = []
    for p in parts:
        pn = normalize(p)
        if re.search(MITRAL_CTX, pn):
            owners.append('MITRAL')
        elif re.search(OTHER_VALVE_CTX, pn):
            owners.append('OTHER')
        else:
            owners.append(None)

    # Forward carry
    cur = None
    for i, o in enumerate(owners):
        if o:
            cur = o
        elif cur:
            owners[i] = cur
    # Backward fill για τα αρχικά clauses
    nxt = None
    for i in range(len(owners) - 1, -1, -1):
        if owners[i]:
            nxt = owners[i]
        elif nxt:
            owners[i] = nxt

    kept = [p for p, o in zip(parts, owners) if o == 'MITRAL']
    return ', '.join(kept)


def _scan_sections(sections: dict, keys: tuple) -> tuple:
    """
    Σαρώνει τα δοσμένα sections ανά πρόταση και κρατά ΜΟΝΟ όσες αναφέρουν ρητά
    τη μιτροειδή (MITRAL_CTX).

    - Πρόταση χωρίς ρητή αναφορά σε μιτροειδή ΔΕΝ κρατιέται: σκέτο
      «μέτρια ανεπάρκεια» είναι αμφίσημο.
    - Πρόταση που αναφέρει ΚΑΙ άλλη βαλβίδα → clause-level φιλτράρισμα
      (_mitral_clauses) + flag multi_valve_sentence.

    Επιστρέφει: (kept_sentences, used_keys, flags)
    """
    kept, used_keys, flags = [], [], []
    for key in keys:
        raw_k = get_sec(sections, key)
        if not raw_k.strip():
            continue
        for sent in re.split(MV_SENT_SPLIT, raw_k):
            sent = sent.strip()
            if not sent:
                continue
            sent_norm = normalize(sent)
            if not re.search(MITRAL_CTX, sent_norm):
                continue
            if re.search(OTHER_VALVE_CTX, sent_norm):
                if 'multi_valve_sentence' not in flags:
                    flags.append('multi_valve_sentence')
                sent = _mitral_clauses(sent)
                if not sent.strip():
                    continue
            kept.append(sent)
            if key not in used_keys:
                used_keys.append(key)
    return kept, used_keys, flags


def resolve_mitral_text(sections: dict) -> dict:
    """
    Επιλέγει το κείμενο πάνω στο οποίο θα τρέξουν οι extractors.
    Τρία επίπεδα, με αυστηρή σειρά προτεραιότητας — το πρώτο που δίνει
    αποτέλεσμα κερδίζει και τα επόμενα ΔΕΝ εξετάζονται:

    1. MV — αν υπάρχει (μη κενό) section «Μιτροειδής βαλβίδα».
       Συμπεριφορά ταυτόσημη με v5.
    2. CONCLUSIONS + COMMENTS — Συμπεράσματα / Σχόλια / Διάγνωση, per-sentence.
    3. IMPORTED — η παράγραφος «Imported Findings», per-sentence.
       Είναι υπογραμμισμένος header με το ίδιο format όπως οι ανατομικές
       ενότητες, αλλά το περιεχόμενό της μπορεί να καλύπτει πολλά όργανα
       μαζί — γι' αυτό περνάει από το ΙΔΙΟ per-sentence φιλτράρισμα και δεν
       λαμβάνεται αυτούσια.

    Επιστρέφει: {'raw': κείμενο, 'source': ετικέτα πηγής, 'flags': [...]}
    source ∈ {'MV', 'CONCLUSIONS', 'COMMENTS', 'CONCLUSIONS+COMMENTS',
              'IMPORTED', 'none'}

    ΓΙΑΤΙ CLAUSE ΦΙΛΤΡΑΡΙΣΜΑ ΣΤΑ MULTI-VALVE: βλ. _mitral_clauses().
    """
    raw_mv = get_sec(sections, 'MV')
    if raw_mv.strip():
        return {'raw': raw_mv, 'source': 'MV', 'flags': []}

    # ── Επίπεδο 2: Συμπεράσματα / Σχόλια / Διάγνωση ──────────────────────
    kept, used_keys, flags = _scan_sections(sections, FALLBACK_KEYS)
    if kept:
        return {'raw': '. '.join(kept),
                'source': '+'.join(used_keys),
                'flags': ['fallback_source'] + flags}

    # ── Επίπεδο 3: Imported Findings ─────────────────────────────────────
    kept, used_keys, flags = _scan_sections(sections, IMPORTED_KEYS)
    if kept:
        return {'raw': '. '.join(kept),
                'source': '+'.join(used_keys),
                'flags': ['fallback_source', 'imported_findings'] + flags}

    return {'raw': '', 'source': 'none', 'flags': []}


def grade_mitral_stenosis(sections: dict, resolved: dict = None) -> dict:
    """
    Στένωση μιτροειδούς — STRICT + INCLUSIVE σε ένα πέρασμα.

    STRICT    : prosthetic guard → borderline(1) → mild(0) → positive(1)
    INCLUSIVE : prosthetic guard → borderline(1) → mild(1) → positive(1)

    Ο prosthetic guard είναι ΙΔΙΟΣ και στις δύο αναλύσεις (καμία αλλαγή).

    Πηγή: MV, με fallback σε Συμπεράσματα/Σχόλια (βλ. resolve_mitral_text).
    """
    out = _blank('mitral_stenosis')
    resolved = resolved or resolve_mitral_text(sections)
    raw = resolved['raw']
    out['source'] = resolved['source']
    t = normalize(raw)
    if not t:
        return out
    M = out['matches']

    # ── 1. PROSTHETIC / MECHANICAL VALVE GUARD ───────────────────────────
    m_pros = re.search(MS_PROSTHETIC, t)
    m_expl = re.search(MS_PROSTHETIC_EXPLICIT, t) if m_pros else None
    if m_pros:
        rec_pros = _rec(M, 'prosthetic_guard', m_pros, t, raw)
        if m_expl:
            _rec(M, 'prosthetic_explicit_stenosis', m_expl, t, raw)
        else:
            out['grade'] = 'prosthetic_no_stenosis'
            out['flags'].append('ms_prosthetic_guard')
            return _finish(out, rec_pros, rec_pros)

    # ── 2. BORDERLINE: μικρού προς μετρίου ───────────────────────────────
    for name, pat in (('borderline_1', MS_BORDERLINE_1), ('borderline_2', MS_BORDERLINE_2)):
        m = re.search(pat, t)
        if m:
            rec = _rec(M, name, m, t, raw)
            out['label_strict'] = 1
            out['label_incl'] = 1
            out['grade'] = 'borderline'
            return _finish(out, rec, rec)

    # ── 3. MILD: 0 στη STRICT, 1 στην INCLUSIVE ──────────────────────────
    for name, pat in (('mild_1', MS_MILD_1), ('mild_2', MS_MILD_2)):
        m = re.search(pat, t)
        if m:
            rec = _rec(M, name, m, t, raw)
            out['label_strict'] = 0
            out['label_incl'] = 1
            out['grade'] = 'mild'
            out['flags'].append('ms_incl_only')
            return _finish(out, rec, rec)

    # ── 4. POSITIVE: μέτρια / σοβαρή ─────────────────────────────────────
    for i, pat in enumerate(MS_POSITIVE, 1):
        m = re.search(pat, t)
        if m:
            rec = _rec(M, f'positive_{i}', m, t, raw)
            out['label_strict'] = 1
            out['label_incl'] = 1
            out['grade'] = 'moderate_severe'
            return _finish(out, rec, rec)

    return out


def grade_mitral_regurgitation(sections: dict, resolved: dict = None) -> dict:
    """
    Ανεπάρκεια μιτροειδούς — STRICT + INCLUSIVE σε ένα πέρασμα.

    STRICT    : borderline(1) → [mild Ή ίχνος](0) → positive(1)
                (ισοδύναμο με το ενιαίο mild_pat του v5)
    INCLUSIVE : borderline(1) → mild(1) → positive(1) → ίχνος(0)

    Το ίχνος ελέγχεται ΤΕΛΕΥΤΑΙΟ στην INCLUSIVE ώστε report με «ίχνος διαφυγής»
    δίπλα σε «σοβαρή ανεπάρκεια» να μη μηδενίζεται.

    Πηγή: MV, με fallback σε Συμπεράσματα/Σχόλια (βλ. resolve_mitral_text).
    """
    out = _blank('mitral_regurgitation')
    resolved = resolved or resolve_mitral_text(sections)
    raw = resolved['raw']
    out['source'] = resolved['source']
    t = normalize(raw)
    if not t:
        return out
    M = out['matches']

    m_border  = re.search(MR_BORDERLINE, t)
    m_mild_f  = re.search(MR_MILD_FWD, t)
    m_mild_r  = re.search(MR_MILD_REV, t)
    m_trace   = re.search(MR_TRACE, t)
    m_pos     = re.search(MR_POSITIVE, t)

    rec_border = _rec(M, 'borderline', m_border, t, raw) if m_border else None
    rec_mild_f = _rec(M, 'mild_forward', m_mild_f, t, raw) if m_mild_f else None
    rec_mild_r = _rec(M, 'mild_reverse', m_mild_r, t, raw) if m_mild_r else None
    rec_trace  = _rec(M, 'trace', m_trace, t, raw) if m_trace else None
    rec_pos    = _rec(M, 'positive', m_pos, t, raw) if m_pos else None

    rec_mild = rec_mild_f or rec_mild_r

    # ── STRICT (ταυτόσημο με v5) ─────────────────────────────────────────
    if rec_border:
        out['label_strict'], dec_strict = 1, rec_border
    elif rec_mild or rec_trace:
        out['label_strict'], dec_strict = 0, (rec_mild or rec_trace)
    elif rec_pos:
        out['label_strict'], dec_strict = 1, rec_pos
    else:
        out['label_strict'], dec_strict = 0, None

    # ── INCLUSIVE ────────────────────────────────────────────────────────
    if rec_border:
        out['label_incl'], out['grade'], dec_incl = 1, 'borderline', rec_border
    elif rec_mild:
        out['label_incl'], out['grade'], dec_incl = 1, 'mild', rec_mild
    elif rec_pos:
        out['label_incl'], out['grade'], dec_incl = 1, 'moderate_severe', rec_pos
    elif rec_trace:
        out['label_incl'], out['grade'], dec_incl = 0, 'trace', rec_trace
    else:
        out['label_incl'], out['grade'], dec_incl = 0, 'none', None

    # ── FLAGS ────────────────────────────────────────────────────────────
    if rec_trace:
        out['flags'].append('mr_trace')
    if out['label_incl'] == 1 and out['label_strict'] == 0:
        out['flags'].append('mr_incl_only')
        if out['grade'] in ('moderate_severe', 'borderline'):
            # Η STRICT το μηδένισε λόγω ίχνους παρότι υπάρχει moderate+ αναφορά
            out['flags'].append('mr_strict_blocked')

    return _finish(out, dec_strict, dec_incl)


# ── Drop-in wrappers (ίδιο signature με τις v5 συναρτήσεις) ──────────────────

def get_mitral_stenosis(sections: dict) -> int:
    return grade_mitral_stenosis(sections)['label_strict']


def get_mitral_stenosis_incl_mild(sections: dict) -> int:
    return grade_mitral_stenosis(sections)['label_incl']


def get_mitral_regurgitation(sections: dict) -> int:
    return grade_mitral_regurgitation(sections)['label_strict']


def get_mitral_regurgitation_incl_mild(sections: dict) -> int:
    return grade_mitral_regurgitation(sections)['label_incl']


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
REVIEW_FLAGS = {'ms_prosthetic_guard', 'mr_strict_blocked', 'multi_valve_sentence',
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
             'mitral_stenosis', 'mitral_stenosis_incl_mild', 'ms_delta', 'ms_grade',
             'ms_rule_incl', 'ms_phrase_incl', 'ms_v5',
             'mitral_regurgitation', 'mitral_regurgitation_incl_mild', 'mr_delta', 'mr_grade',
             'mr_rule_incl', 'mr_phrase_incl', 'mr_v5',
             'flags', 'status', 'mitral_text', 'mv_text',
             'conclusions_text', 'comments_text', 'imported_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 20,
                16, 20, 10, 20, 18, 36, 8,
                20, 24, 10, 20, 18, 36, 8,
                36, 18, 70, 70, 60, 60, 60, 60],
               wrap_cols=('mitral_text', 'mv_text', 'conclusions_text',
                          'comments_text', 'imported_text'))
    i_flag = cols1.index('flags')
    i_dms, i_dmr = cols1.index('ms_delta'), cols1.index('mr_delta')
    for row in ws1.iter_rows(min_row=2):
        flags = row[i_flag].value or ''
        if any(f in REVIEW_FLAGS for f in flags.split(';') if f):
            for c in row:
                c.fill = FLAG_FILL
        for j in (i_dms, i_dmr):
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

def MV(text: str) -> dict:
    """Helper: sections dict με μόνο το MV section."""
    return {'MV': text} if text else {}


# (sections, ms_strict, ms_incl, ms_grade, mr_strict, mr_incl, mr_grade, source)
SELF_TESTS_FALLBACK = [
    # Χωρίς MV section — εύρημα στα Συμπεράσματα
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Χωρίς MV section — εύρημα στη Διάγνωση (→ COMMENTS)
    ({'COMMENTS': 'Διάγνωση: Ήπια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 0, 1, 'mild', 'COMMENTS'),
    # Στένωση στα Συμπεράσματα
    ({'CONCLUSIONS': 'Σοβαρή στένωση μιτροειδούς.'},
     1, 1, 'moderate_severe', 0, 0, 'none', 'CONCLUSIONS'),
    # Πρόταση για ΑΛΛΗ βαλβίδα → αγνοείται εντελώς
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής βαλβίδας.'},
     0, 0, 'none', 0, 0, 'none', 'none'),
    # Σκέτο «μέτρια ανεπάρκεια» χωρίς όργανο → αμφίσημο, αγνοείται
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια.'},
     0, 0, 'none', 0, 0, 'none', 'none'),
    # Μεικτή πρόταση → κρατιέται ΜΟΝΟ το clause της μιτροειδούς + flag
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς και ήπια αορτικής.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Αντίστροφη σειρά — το clause της αορτικής απορρίπτεται, MS μένει 0
    ({'CONCLUSIONS': 'Σοβαρή στένωση αορτικής βαλβίδας και μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Clause χωρίς όνομα βαλβίδας κληρονομεί το προηγούμενο όργανο
    ({'CONCLUSIONS': 'Ανεπάρκεια μιτροειδούς, μετρίου βαθμού, και σοβαρή αορτική στένωση.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Επιλογή μόνο της σχετικής πρότασης μέσα από πολλές
    ({'CONCLUSIONS': 'Φυσιολογική αορτική βαλβίδα. Ήπια ανεπάρκεια μιτροειδούς. '
                     'Φυσιολογική συστολική λειτουργία.'},
     0, 0, 'none', 0, 1, 'mild', 'CONCLUSIONS'),
    # Ίχνος στα Συμπεράσματα → 0 και στις δύο
    ({'CONCLUSIONS': 'Ίχνος ανεπάρκειας μιτροειδούς.'},
     0, 0, 'none', 0, 0, 'trace', 'CONCLUSIONS'),
    # Συντομογραφία MV στα Συμπεράσματα
    ({'CONCLUSIONS': 'Μέτρια ανεπάρκεια MV.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Συντομογραφία MV σε multi-valve πρόταση → κρατιέται μόνο το clause της MV
    ({'COMMENTS': 'Σχόλια: Ήπια στένωση MV και σοβαρή ανεπάρκεια αορτικής.'},
     0, 1, 'mild', 0, 0, 'none', 'COMMENTS'),
    # ΥΠΑΡΧΕΙ MV section → ΔΕΝ ενεργοποιείται fallback, τα Συμπεράσματα αγνοούνται
    ({'MV': 'Καλή σύγκλειση των γλωχίνων.',
      'CONCLUSIONS': 'Σοβαρή ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 0, 0, 'none', 'MV'),
    # Κενό MV section → ενεργοποιείται fallback
    ({'MV': '   ', 'CONCLUSIONS': 'Σοβαρή ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # ── ΕΠΙΠΕΔΟ 3: Imported Findings ─────────────────────────────────────
    # Μόνη πηγή το Imported Findings
    ({'IMPORTED': 'Μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'IMPORTED'),
    # Συμπεράσματα υπάρχουν αλλά χωρίς αναφορά σε μιτροειδή → πέφτει στο IMPORTED
    ({'CONCLUSIONS': 'Τυπική μελέτη.', 'IMPORTED': 'Ήπια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 0, 1, 'mild', 'IMPORTED'),
    # Τα Συμπεράσματα ΕΧΟΥΝ αναφορά → κερδίζουν, το IMPORTED αγνοείται
    ({'CONCLUSIONS': 'Σοβαρή ανεπάρκεια μιτροειδούς.',
      'IMPORTED': 'Ήπια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'CONCLUSIONS'),
    # Το MV section κερδίζει και από τα δύο επίπεδα fallback
    ({'MV': 'Καλή σύγκλειση των γλωχίνων.',
      'IMPORTED': 'Σοβαρή ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 0, 0, 'none', 'MV'),
    # Imported Findings με αναφορά σε άλλη βαλβίδα → clause φιλτράρισμα
    ({'IMPORTED': 'Σοβαρή στένωση αορτικής βαλβίδας και μέτρια ανεπάρκεια μιτροειδούς.'},
     0, 0, 'none', 1, 1, 'moderate_severe', 'IMPORTED'),
    # Imported Findings χωρίς καμία αναφορά σε μιτροειδή
    ({'IMPORTED': 'Φυσιολογική συστολική λειτουργία αριστερής κοιλίας.'},
     0, 0, 'none', 0, 0, 'none', 'none'),

    # Τίποτα πουθενά
    ({'CONCLUSIONS': 'Τυπική μελέτη.'},
     0, 0, 'none', 0, 0, 'none', 'none'),
]

# (MV text, ms_strict, ms_incl, ms_grade, mr_strict, mr_incl, mr_grade)
SELF_TESTS = [
    # ── ΣΤΕΝΩΣΗ ──────────────────────────────────────────────────────────
    ('Μετρίου βαθμού στένωση μιτροειδούς.',
     1, 1, 'moderate_severe', 0, 0, 'none'),
    ('Σοβαρή στένωση μιτροειδούς.',
     1, 1, 'moderate_severe', 0, 0, 'none'),
    ('Μικρού βαθμού στένωση.',
     0, 1, 'mild', 0, 0, 'none'),
    ('Ήπια στένωση μιτροειδούς.',
     0, 1, 'mild', 0, 0, 'none'),
    ('Στένωση ρευματικής αιτιολογίας μικρού βαθμού.',
     0, 1, 'mild', 0, 0, 'none'),
    ('Μικρού βαθμού περιορισμός στη διάνοιξη.',
     0, 1, 'mild', 0, 0, 'none'),
    ('Μικρού προς μετρίου βαθμού στένωση.',
     1, 1, 'borderline', 0, 0, 'none'),
    ('Φυσιολογική διάνοιξη των γλωχίνων.',
     0, 0, 'none', 0, 0, 'none'),
    # Prosthetic guard — αμετάβλητος, 0 και στις δύο αναλύσεις
    ('Μηχανική βαλβίδα σε μιτροειδή θέση, φυσιολογική λειτουργία.',
     0, 0, 'prosthetic_no_stenosis', 0, 0, 'none'),
    ('Βιοπροσθετική μιτροειδής βαλβίδα με ήπια στένωση.',
     0, 0, 'prosthetic_no_stenosis', 0, 0, 'none'),
    # Prosthetic + ρητή σοβαρή → περνά τον guard
    ('Μηχανική βαλβίδα. Σοβαρή στένωση.',
     1, 1, 'moderate_severe', 0, 0, 'none'),

    # ── ΑΝΕΠΑΡΚΕΙΑ ───────────────────────────────────────────────────────
    ('Μέτρια ανεπάρκεια μιτροειδούς.',
     0, 0, 'none', 1, 1, 'moderate_severe'),
    ('Ανεπάρκεια μετρίου βαθμού.',
     0, 0, 'none', 1, 1, 'moderate_severe'),
    ('Σοβαρή ανεπάρκεια μιτροειδούς.',
     0, 0, 'none', 1, 1, 'moderate_severe'),
    ('Σημαντική διαφυγή.',
     0, 0, 'none', 1, 1, 'moderate_severe'),
    ('Ήπια ανεπάρκεια μιτροειδούς.',
     0, 0, 'none', 0, 1, 'mild'),
    ('Μικρού βαθμού ανεπάρκεια.',
     0, 0, 'none', 0, 1, 'mild'),
    ('Ελαφρά ανεπάρκεια.',
     0, 0, 'none', 0, 1, 'mild'),
    ('Ελάχιστη διαφυγή.',
     0, 0, 'none', 0, 1, 'mild'),
    ('Ανεπάρκεια μικρού βαθμού.',
     0, 0, 'none', 0, 1, 'mild'),
    # ΙΧΝΟΣ — 0 και στις δύο αναλύσεις
    ('Ίχνος διαφυγής.',
     0, 0, 'none', 0, 0, 'trace'),
    ('Ίχνος ανεπάρκειας μιτροειδούς.',
     0, 0, 'none', 0, 0, 'trace'),
    # Borderline
    ('Μικρού προς μετρίου βαθμού ανεπάρκεια.',
     0, 0, 'none', 1, 1, 'borderline'),
    # Ίχνος + σοβαρή: STRICT=0 (v5 behaviour), INCLUSIVE=1 → flag mr_strict_blocked
    ('Σοβαρή ανεπάρκεια μιτροειδούς. Ίχνος διαφυγής περιβαλβιδικά.',
     0, 0, 'none', 0, 1, 'moderate_severe'),
    ('Καλή σύγκλειση των γλωχίνων.',
     0, 0, 'none', 0, 0, 'none'),

    # ── ΣΥΝΔΥΑΣΜΟΙ ───────────────────────────────────────────────────────
    ('Μικρού βαθμού στένωση μιτροειδούς και ήπια ανεπάρκεια.',
     0, 1, 'mild', 0, 1, 'mild'),
    ('Σοβαρού βαθμού στένωση μιτροειδούς με μέτρια ανεπάρκεια.',
     1, 1, 'moderate_severe', 1, 1, 'moderate_severe'),
    ('',
     0, 0, 'none', 0, 0, 'none'),
]


def run_self_test() -> bool:
    ok_all = True
    logger.info("SELF-TEST")

    # 0. Η ανασύνθεση του v5 mild_pat πρέπει να είναι χαρακτήρα-προς-χαρακτήρα ίδια
    expected_mild_v5 = (
        r'(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?\s+(?:\w+\s+){0,3}(?:ανεπ[άα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)'
        r'|(?:ανεπ[εάα]ρκεια[ςσ]?|διαφυγ[ήη][ςσ]?)\s+(?:\w+\s+){0,3}(?:μικρ[ήη]|μικρο[ύυ]\s+βαθμο[ύυ]|[ήη]πι[οα][σς]?|ελαφρ[άα]|ελ[άα]χιστ[ηο])(?:\s+βαθμο[ύυ])?'
        r'|[ίι]χνο[σς]\s+(?:ανεπ[άα]ρκειας?|διαφυγ[ήη]ς?)'
    )
    same = (MR_MILD_PAT_V5 == expected_mild_v5)
    ok_all &= same
    logger.info(f"  [{'PASS' if same else 'FAIL':5}] ανασύνθεση v5 mild_pat από MR_MILD_FWD|MR_MILD_REV|MR_TRACE")

    # 1. Synthetic περιπτώσεις — MV section (source πάντα 'MV' ή 'none' αν κενό)
    cases = [(MV(mv), a, b, c, d, e, f, 'MV' if mv else 'none')
             for mv, a, b, c, d, e, f in SELF_TESTS]

    # 2. Synthetic περιπτώσεις — fallback σε Συμπεράσματα / Σχόλια
    cases += SELF_TESTS_FALLBACK

    for secs, e_mss, e_msi, e_msg, e_mrs, e_mri, e_mrg, e_src in cases:
        resolved = resolve_mitral_text(secs)
        ms = grade_mitral_stenosis(secs, resolved)
        mr = grade_mitral_regurgitation(secs, resolved)
        ms_v5 = get_mitral_stenosis_v5(secs)
        mr_v5 = get_mitral_regurgitation_v5(secs)

        # Η ταύτιση με v5 απαιτείται ΜΟΝΟ όταν η πηγή είναι το MV section.
        v5_ok = (resolved['source'] != 'MV' or
                 (ms['label_strict'] == ms_v5 and mr['label_strict'] == mr_v5))

        ok = (ms['label_strict'] == e_mss and ms['label_incl'] == e_msi and ms['grade'] == e_msg and
              mr['label_strict'] == e_mrs and mr['label_incl'] == e_mri and mr['grade'] == e_mrg and
              resolved['source'] == e_src and v5_ok and
              ms['label_incl'] >= ms['label_strict'] and mr['label_incl'] >= mr['label_strict'])
        if not ok:
            ok_all = False

        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
        all_flags = resolved['flags'] + ms['flags'] + mr['flags']
        logger.info(
            f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
            f"          → [{resolved['source']}] "
            f"MS {ms['label_strict']}/{ms['label_incl']} ({ms['grade']})   "
            f"MR {mr['label_strict']}/{mr['label_incl']} ({mr['grade']})"
            f"{'  flags=' + ';'.join(all_flags) if all_flags else ''}"
            f"{'' if ok else f'  (αναμενόταν [{e_src}] MS {e_mss}/{e_msi} {e_msg}, MR {e_mrs}/{e_mri} {e_mrg}, v5 MS={ms_v5} MR={mr_v5})'}")

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
            label_rows.append({'exam_id': e['exam_id'], 'status': 'read_failed',
                               'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        resolved = resolve_mitral_text(sections)
        ms = grade_mitral_stenosis(sections, resolved)
        mr = grade_mitral_regurgitation(sections, resolved)
        ms_v5 = get_mitral_stenosis_v5(sections)
        mr_v5 = get_mitral_regurgitation_v5(sections)

        src = resolved['source']
        flags = list(resolved['flags']) + ms['flags'] + mr['flags']

        if src == 'MV':
            # Πηγή ίδια με v5 → η STRICT ΠΡΕΠΕΙ να ταυτίζεται
            if ms['label_strict'] != ms_v5 or mr['label_strict'] != mr_v5:
                flags.append('strict_vs_v5_mismatch')
        else:
            # Fallback: το v5 δεν είχε πηγή, άρα διαφορά = κέρδος, όχι σφάλμα
            if ms['label_strict'] > ms_v5 or mr['label_strict'] > mr_v5:
                flags.append('fallback_gain')

        if ms['label_incl'] < ms['label_strict'] or mr['label_incl'] < mr['label_strict']:
            flags.append('non_monotonic')

        if src == 'MV':
            status = 'ok'
        elif src == 'none':
            status = 'no_mitral_text'
        else:
            status = 'fallback'

        label_rows.append({
            'exam_id':                        e['exam_id'],
            'source':                         src,
            'mitral_stenosis':                ms['label_strict'],
            'mitral_stenosis_incl_mild':      ms['label_incl'],
            'ms_delta':                       ms['label_incl'] - ms['label_strict'],
            'ms_grade':                       ms['grade'],
            'ms_rule_incl':                   ms['rule_incl'],
            'ms_phrase_incl':                 original_phrase(ms['raw_incl'], ms['phrase_incl']),
            'ms_v5':                          ms_v5,
            'mitral_regurgitation':           mr['label_strict'],
            'mitral_regurgitation_incl_mild': mr['label_incl'],
            'mr_delta':                       mr['label_incl'] - mr['label_strict'],
            'mr_grade':                       mr['grade'],
            'mr_rule_incl':                   mr['rule_incl'],
            'mr_phrase_incl':                 original_phrase(mr['raw_incl'], mr['phrase_incl']),
            'mr_v5':                          mr_v5,
            'flags':                          ';'.join(flags),
            'status':                         status,
            'mitral_text':                    resolved['raw'],
            'mv_text':                        get_sec(sections, 'MV'),
            'conclusions_text':               get_sec(sections, 'CONCLUSIONS'),
            'comments_text':                  get_sec(sections, 'COMMENTS'),
            'imported_text':                  get_sec(sections, 'IMPORTED'),
            'report_path':                    e['report_path'],
        })

        for res in (ms, mr):
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
        for col in ('mitral_stenosis', 'mitral_stenosis_incl_mild',
                    'mitral_regurgitation', 'mitral_regurgitation_incl_mild'):
            pos_n = sum(r[col] == 1 for r in ok_rows)
            logger.info(f"  {col:<34} {pos_n:>5} {n:>7} {100 * pos_n / n:>5.1f}%")

        d_ms = sum(r['ms_delta'] == 1 for r in ok_rows)
        d_mr = sum(r['mr_delta'] == 1 for r in ok_rows)
        logger.info(f"\nΕπιπλέον θετικές λόγω mild:")
        logger.info(f"  mitral_stenosis        +{d_ms} ({100 * d_ms / n:.1f}%)")
        logger.info(f"  mitral_regurgitation   +{d_mr} ({100 * d_mr / n:.1f}%)")

        # ── Πηγή κειμένου ───────────────────────────────────────────────────
        src_dist = {}
        for r in ok_rows:
            src_dist[r['source']] = src_dist.get(r['source'], 0) + 1
        logger.info("\nΠηγή κειμένου:")
        for s, c in sorted(src_dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {s:<24} {c:>6} ({100 * c / n:.1f}%)")

        n_fb = sum(r['source'] not in ('MV', 'none') for r in ok_rows)
        if n_fb:
            g_ms = sum(r['source'] not in ('MV', 'none') and r['mitral_stenosis'] == 1 for r in ok_rows)
            g_mr = sum(r['source'] not in ('MV', 'none') and r['mitral_regurgitation'] == 1 for r in ok_rows)
            gi_ms = sum(r['source'] not in ('MV', 'none') and r['mitral_stenosis_incl_mild'] == 1 for r in ok_rows)
            gi_mr = sum(r['source'] not in ('MV', 'none') and r['mitral_regurgitation_incl_mild'] == 1 for r in ok_rows)
            logger.info(f"\nFallback (χωρίς MV section): {n_fb} εξετάσεις")
            logger.info(f"  νέες θετικές MS: {g_ms} strict / {gi_ms} incl_mild")
            logger.info(f"  νέες θετικές MR: {g_mr} strict / {gi_mr} incl_mild")

        n_mv  = sum(r['source'] == 'MV' for r in ok_rows)
        n_mis = sum('strict_vs_v5_mismatch' in r['flags'] for r in ok_rows)
        n_mon = sum('non_monotonic' in r['flags'] for r in ok_rows)
        if n_mis:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mis} εξετάσεις όπου η STRICT διαφέρει από το v5!")
        else:
            logger.info(f"\nSanity check: η STRICT ταυτίζεται με το v5 και στις {n_mv} "
                        f"εξετάσεις με MV section ✓")
        if n_mon:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_mon} εξετάσεις με STRICT=1 αλλά INCLUSIVE=0!")
        else:
            logger.info("Sanity check: INCLUSIVE >= STRICT παντού ✓")

        for name, key in (('ms_grade', 'ms_grade'), ('mr_grade', 'mr_grade')):
            dist = {}
            for r in ok_rows:
                dist[r[key]] = dist.get(r[key], 0) + 1
            logger.info(f"\nΚατανομή {name}:")
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
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/mitral_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
