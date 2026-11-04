r"""
tavr_v6x_v2.py
==============
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για το finding
tavr (προσθετική αορτική βαλβίδα). Παράγει ΔΥΟ αναλύσεις:

  ΑΝΑΛΥΣΗ Α — tavr_incl_mech  (ΠΕΡΙΛΑΜΒΑΝΕΙ μηχανική/μεταλλική)
      Τα 5 patterns του v5 (αυτούσια): οποιοδήποτε ταιριάζει σε ΟΠΟΙΑΔΗΠΟΤΕ πηγή → 1.

  ΑΝΑΛΥΣΗ Β — tavr_excl_mech  (ΔΕΝ περιλαμβάνει μηχανική/μεταλλική)
      label = 1 : βιοπροσθετική βαλβίδα ή TAVR/TAVI
      label = 0 : μηχανική/μεταλλική βαλβίδα
      label = 0 : σκέτο «προσθετική βαλβίδα» χωρίς τύπο        → FLAG generic_prosthetic
      label = MECH_AND_BIO_LABEL_B (default 0) : μηχανική ΚΑΙ βιοπροσθετική/TAVR
                                                 → FLAG mech_and_bio
      label = 0 : καμία αναφορά

ΠΗΓΕΣ ΤΟΥ REPORT (ΝΕΟ στο v2)
  AV           section «Αορτική βαλβίδα» — ολόκληρο, ακριβώς όπως στο v5
  CONCLUSIONS  Συμπεράσματα
  COMMENTS     Σχόλια / Διάγνωση / Echo summary

  Στα CONCLUSIONS/COMMENTS εξετάζεται κάθε πρόταση ξεχωριστά:
    - Κρατιέται μόνο αν ταιριάζει κάποιο από τα patterns.
    - Απορρίπτεται αν αναφέρει ΑΛΛΗ βαλβίδα (μιτροειδής/τριγλώχινα/πνευμονική)
      χωρίς αναφορά σε αορτή/TAVR/TAVI  (π.χ. «μηχανική μιτροειδής βαλβίδα»).
    - Αν αναφέρει ΚΑΙ αορτή ΚΑΙ άλλη βαλβίδα → κρατιέται + FLAG multi_valve_sentence.
    - Αν το TAVR/TAVI είναι σχεδιαζόμενο («παραπέμπεται για TAVI», «υποψήφιος
      για TAVR» κ.λπ.) → το TAVR/TAVI ΔΕΝ μετράει + FLAG tavr_planned.

  Συνδυασμός: τα ευρήματα όλων των πηγών ενώνονται (ο ασθενής έχει μία αορτική
  βαλβίδα). Έτσι, π.χ., σκέτο «προσθετική» στο AV + «TAVI» στα Συμπεράσματα → 1
  χωρίς flag· «βιοπροσθετική» στο AV + «μηχανική αορτική» στα Σχόλια → mixed + flag.

  Sanity check: όπου το v5 έδινε 1, η Ανάλυση Α ΠΡΕΠΕΙ να δίνει 1 (μπορεί μόνο
  να κερδίσει θετικά από τις νέες πηγές, ποτέ να χάσει).

FLAGS (στήλη flags) — οι γραμμές με flag χρωματίζονται έντονο πορτοκαλί στο Excel:
  generic_prosthetic, mech_and_bio      → αφορούν το label της Ανάλυσης Β
  multi_valve_sentence, tavr_planned    → αφορούν την ανάγνωση των Συμπερασμάτων/Σχολίων

PATTERNS
  Τα 5 regex του v5 είναι ΑΥΤΟΥΣΙΑ (V5_PATTERNS). Μόνο για την Ανάλυση Β:
    - B_PROS_GENERIC : v5 «προσθετική» + \b (δεν πιάνει «βιοπροσθετική»)·
      αγνοείται όταν προηγείται «μηχανική/μεταλλική»
    - B_MECH_EXT     : «μηχανική προσθετική (αορτική) βαλβίδα»
    - B_METAL        : «μεταλλική (προσθετική/αορτική) βαλβίδα»
  Στο AV δεν εφαρμόζεται κανένα φίλτρο (ίδια συμπεριφορά με v5). Δεν χειρίζεται
  αρνήσεις (όπως και το v5).

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά pattern που ταίριαξε (πηγή, ανάλυση, αν καθόρισε το label)

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
logger = logging.getLogger("tavr")


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

def get_tavr_v5(sections: dict) -> int:
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


# =============================================================================
# PATTERNS — ΑΥΤΟΥΣΙΑ από v5 (μην τα επεξεργαστείς εδώ)
# =============================================================================

V5_BIO  = r'βιοπροσθετικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*'
V5_MECH = r'μηχανικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*'
V5_PROS = r'προσθετικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*'
V5_TAVR = r'\btavr\b'
V5_TAVI = r'\btavi\b'

# Ίδια σειρά με το v5. Το 3ο στοιχείο = ποιες αναλύσεις χρησιμοποιούν το pattern.
V5_PATTERNS = [
    ('v5_bioprosthetic', V5_BIO,  'A+B'),
    ('v5_mechanical',    V5_MECH, 'A+B'),
    ('v5_prosthetic',    V5_PROS, 'A'),     # στη Β αντικαθίσταται από B_PROS_GENERIC
    ('v5_tavr',          V5_TAVR, 'A+B'),
    ('v5_tavi',          V5_TAVI, 'A+B'),
]


# =============================================================================
# PATTERNS — ΜΟΝΟ ΓΙΑ ΤΗΝ ΑΝΑΛΥΣΗ Β
# =============================================================================

# Γενικό «προσθετική βαλβίδα»: το v5 pattern με \b στην αρχή → ΔΕΝ πιάνει «βιοπροσθετική».
B_PROS_GENERIC = r'\bπροσθετικ\w*\s+(?:αορτικ\w*\s+)?βαλβ[ίι]δ\w*'
# Το match του γενικού αγνοείται αν η ΑΜΕΣΩΣ προηγούμενη λέξη είναι μηχανική/μεταλλική
# (π.χ. «μηχανική προσθετική βαλβίδα» → είναι μηχανική, όχι αδιευκρίνιστη).
B_PROS_MECH_LOOKBACK = r'(?:μηχανικ|μεταλλικ)\w*\s+$'
B_PROS_LOOKBACK_CHARS = 30

# Μηχανική με ενδιάμεσο «προσθετική»/«αορτική» (το v5 V5_MECH επιτρέπει μόνο «αορτική»)
B_MECH_EXT = r'μηχανικ\w*\s+(?:(?:προσθετικ|αορτικ)\w*\s+){0,2}βαλβ[ίι]δ\w*'
# Μεταλλική βαλβίδα (νέο, μόνο Β)
B_METAL    = r'μεταλλικ\w*\s+(?:(?:προσθετικ|αορτικ)\w*\s+){0,2}βαλβ[ίι]δ\w*'

# Μηχανική ΚΑΙ βιοπροσθετική/TAVR στο ίδιο section → ποιο label στην Ανάλυση Β.
# 0 = υπερισχύει η μηχανική (default)  |  1 = υπερισχύει η βιοπροσθετική/TAVR
MECH_AND_BIO_LABEL_B = 0

POSITIVE_GRADES_B = {'bioprosthetic', 'tavr', 'bioprosthetic+tavr'}



# =============================================================================
# ΠΗΓΕΣ: Συμπεράσματα / Σχόλια / Διάγνωση  (ΝΕΟ στο v2)
# =============================================================================

SOURCE_ORDER = ['AV', 'CONCLUSIONS', 'COMMENTS']

# Διαχωρισμός σε προτάσεις: τελεία (όχι δεκαδική), ερωτηματικό, αλλαγή γραμμής
TAVR_SENT_SPLIT = r'\.(?!\d)|;|\n'

# Πρόταση που αφορά αορτή
TAVR_AORTIC_CTX = r'αορτ|\btavr\b|\btavi\b|\bavr\b'
# Πρόταση που αφορά άλλη βαλβίδα
TAVR_OTHER_VALVE = r'μιτροειδ|τριγλωχ|πνευμονικ'

# Οποιοδήποτε pattern (για να κρατηθεί μια πρόταση)
TAVR_ANY = '|'.join(f'(?:{p})' for p in (V5_BIO, V5_MECH, V5_PROS, V5_TAVR, V5_TAVI,
                                         B_MECH_EXT, B_METAL))

# Σχεδιαζόμενο TAVR/TAVI (δεν σημαίνει ότι υπάρχει βαλβίδα)
TAVR_PLANNED = (
    r'(?:για|προς|υποψηφι\w*|παραπ[εο]μπ\w*|προγραμματ\w*|αξιολογ\w*|συζητ\w*|'
    r'ενδειξ\w*|συστηνε\w*|πιθαν\w*|ενδεχομεν\w*|candidate|referr\w*|planned)'
    r'\s+(?:\w+\s+){0,3}(?:tavr|tavi)\b'
)


def _sentences(t: str) -> list:
    return [s.strip() for s in re.split(TAVR_SENT_SPLIT, t) if s.strip()]


def build_sources(sections: dict) -> dict:
    """
    {source: {'text': normalized κείμενο, 'raw': αρχικό κείμενο, 'flags': [...]}}
    AV: ολόκληρο (όπως v5). CONCLUSIONS/COMMENTS: μόνο οι σχετικές προτάσεις.
    """
    out = {}
    raw = get_sec(sections, 'AV')
    t = normalize(raw)
    if t:
        out['AV'] = {'text': t, 'raw': raw, 'flags': []}

    for key in ('CONCLUSIONS', 'COMMENTS'):
        raw = get_sec(sections, key)
        t = normalize(raw)
        if not t:
            continue
        kept, flags = [], []
        for s in _sentences(t):
            if not re.search(TAVR_ANY, s):
                continue
            aortic = re.search(TAVR_AORTIC_CTX, s)
            other = re.search(TAVR_OTHER_VALVE, s)
            if other and not aortic:
                continue                                  # άλλη βαλβίδα → εκτός
            if re.search(TAVR_PLANNED, s):
                flags.append('tavr_planned')
                s = re.sub(r'\b(tavr|tavi)\b', r'[\1_planned]', s)   # δεν ξαναπιάνεται
            if aortic and other:
                flags.append('multi_valve_sentence')
            kept.append(s)
        if kept:
            out[key] = {'text': '. '.join(kept), 'raw': raw, 'flags': flags}
    return out


# =============================================================================
# CORE LOGIC
# =============================================================================

def _context(text: str, m, before=40, after=30) -> str:
    return text[max(0, m.start() - before): m.end() + after]


def _probe(t: str, source: str, raw: str, matches: list) -> dict:
    """Τρέχει όλα τα patterns σε ΕΝΑ κείμενο. Επιστρέφει {rule: record}."""
    found = {}

    def add(rule, used_by, m):
        rec = {'source': source, 'raw': raw, 'rule': rule, 'used_by': used_by,
               'match': m.group(), 'context': _context(t, m),
               'decisive_A': 0, 'decisive_B': 0}
        matches.append(rec)
        found[rule] = rec

    # v5 patterns (αυτούσια)
    for name, pat, used_by in V5_PATTERNS:
        m = re.search(pat, t)
        if m:
            add(name, used_by, m)

    # μόνο Β
    m = re.search(B_MECH_EXT, t)
    if m:
        add('B_mechanical_ext', 'B', m)
    m = re.search(B_METAL, t)
    if m:
        add('B_metallic', 'B', m)
    for m in re.finditer(B_PROS_GENERIC, t):
        before = t[max(0, m.start() - B_PROS_LOOKBACK_CHARS): m.start()]
        if re.search(B_PROS_MECH_LOOKBACK, before):
            continue
        add('B_prosthetic_generic', 'B', m)
        break
    return found


def grade_tavr(sections: dict) -> dict:
    """
    Συνδυάζει AV + Συμπεράσματα + Σχόλια και αποφασίζει ΚΑΙ τις δύο αναλύσεις.
    Επιστρέφει dict με: label_A, label_B, grade_B, flags, sources_A, rule_A,
    match_A, raw_A, source_B, rule_B, match_B, raw_B, matches.
    """
    out = {'label_A': 0, 'label_B': 0, 'grade_B': 'none', 'flags': '',
           'sources_A': '', 'rule_A': '', 'match_A': '', 'raw_A': '',
           'source_B': '', 'rule_B': '', 'match_B': '', 'raw_B': '', 'matches': []}

    srcs = build_sources(sections)
    matches, per = [], {}
    for src in SOURCE_ORDER:
        if src in srcs:
            per[src] = _probe(srcs[src]['text'], src, srcs[src]['raw'], matches)

    def first(*rules):
        """Πρώτο record κατά σειρά πηγής (AV → CONCLUSIONS → COMMENTS)."""
        for src in SOURCE_ORDER:
            for r in rules:
                if r in per.get(src, {}):
                    return per[src][r]
        return None

    v5_names = [n for n, _, _ in V5_PATTERNS]

    # ── ΑΝΑΛΥΣΗ Α ────────────────────────────────────────────────────────
    sources_A = [s for s in SOURCE_ORDER if any(n in per.get(s, {}) for n in v5_names)]
    dec_A = None
    if sources_A:
        s0 = sources_A[0]
        dec_A = next(per[s0][n] for n in v5_names if n in per[s0])
    label_A = 1 if dec_A else 0

    # ── ΑΝΑΛΥΣΗ Β ────────────────────────────────────────────────────────
    bio     = first('v5_bioprosthetic')
    tavr    = first('v5_tavr', 'v5_tavi')
    mech    = first('v5_mechanical', 'B_mechanical_ext', 'B_metallic')
    generic = first('B_prosthetic_generic')
    pos     = bio or tavr

    flags = []
    if mech and pos:
        grade_B, label_B = 'mixed', MECH_AND_BIO_LABEL_B
        dec_B = mech if label_B == 0 else pos
        flags.append('mech_and_bio')
    elif mech:
        grade_B, label_B, dec_B = 'mechanical', 0, mech
    elif pos:
        grade_B = 'bioprosthetic+tavr' if (bio and tavr) else ('bioprosthetic' if bio else 'tavr')
        label_B, dec_B = 1, pos
    elif generic:
        grade_B, label_B, dec_B = 'generic_prosthetic', 0, generic
        flags.append('generic_prosthetic')
    else:
        grade_B, label_B, dec_B = 'none', 0, None

    for src in SOURCE_ORDER:
        for f in srcs.get(src, {}).get('flags', []):
            if f not in flags:
                flags.append(f)

    if dec_A:
        dec_A['decisive_A'] = 1
    if dec_B:
        dec_B['decisive_B'] = 1

    out.update({
        'label_A':   label_A,
        'label_B':   label_B,
        'grade_B':   grade_B,
        'flags':     ';'.join(flags),
        'sources_A': ';'.join(sources_A),
        'rule_A':    dec_A['rule'] if dec_A else '',
        'match_A':   dec_A['match'] if dec_A else '',
        'raw_A':     dec_A['raw'] if dec_A else '',
        'source_B':  dec_B['source'] if dec_B else '',
        'rule_B':    dec_B['rule'] if dec_B else '',
        'match_B':   dec_B['match'] if dec_B else '',
        'raw_B':     dec_B['raw'] if dec_B else '',
        'matches':   matches,
    })
    return out


def get_tavr_incl_mech(sections: dict) -> int:
    """Ανάλυση Α — drop-in (ίδιο signature με get_tavr)."""
    return grade_tavr(sections)['label_A']


def get_tavr_excl_mech(sections: dict) -> int:
    """Ανάλυση Β — drop-in (ίδιο signature με get_tavr)."""
    return grade_tavr(sections)['label_B']


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
# ΑΝΑΓΝΩΣΗ REPORTS (HTML ή CHM)  — ίδιο με pericardial_effusion_v6x2
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

FLAG_FILL = PatternFill('solid', fgColor='FFC000')   # έντονο πορτοκαλί για γραμμές με flag


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
    cols1 = ['exam_id', 'tavr_incl_mech', 'tavr_excl_mech', 'grade_B', 'flags',
             'sources_A', 'rule_A', 'phrase_A', 'source_B', 'rule_B', 'phrase_B',
             'label_v5', 'changed_vs_v5_A', 'changed_vs_v5_B', 'status',
             'av_text', 'conclusions_text', 'comments_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 14, 14, 20, 30, 22, 18, 34, 14, 22, 34, 9, 15, 15, 18, 60, 60, 60, 60],
               wrap_cols=('av_text', 'conclusions_text', 'comments_text'))
    i_flag = cols1.index('flags')
    i_chg_a, i_chg_b = cols1.index('changed_vs_v5_A'), cols1.index('changed_vs_v5_B')
    for row in ws1.iter_rows(min_row=2):
        if row[i_flag].value:
            for c in row:
                c.fill = FLAG_FILL
        for j in (i_chg_a, i_chg_b):
            if row[j].value == 1:
                row[j].font = chg_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'source', 'rule', 'used_by', 'matched_phrase',
             'decisive_A', 'decisive_B', 'context']
    fill_sheet(ws2, cols2, evidence_rows, [18, 14, 22, 9, 40, 11, 11, 80], wrap_cols=('context',))

    wb.save(path)


# =============================================================================
# SELF-TEST (synthetic περιπτώσεις — τρέχει πριν το batch)
# =============================================================================

SELF_TESTS = [
    # (sections, label_A, label_B, grade_B, flags, source_B)
    # ── Μόνο AV (ίδια συμπεριφορά με v1) ─────────────────────────────────
    ({'AV': 'Βιοπροσθετική αορτική βαλβίδα με καλή λειτουργία.'},   1, 1, 'bioprosthetic',      '', 'AV'),
    ({'AV': 'Βιοπροσθετικής βαλβίδας με φυσιολογικές κλίσεις.'},    1, 1, 'bioprosthetic',      '', 'AV'),
    ({'AV': 'Status post TAVI. Καλή λειτουργία.'},                  1, 1, 'tavr',               '', 'AV'),
    ({'AV': 'TAVR 26 mm χωρίς παραβαλβιδική διαφυγή.'},             1, 1, 'tavr',               '', 'AV'),
    ({'AV': 'Βιοπροσθετική βαλβίδα (TAVI).'},                       1, 1, 'bioprosthetic+tavr', '', 'AV'),
    ({'AV': 'Μηχανική βαλβίδα σε αορτική θέση.'},                   1, 0, 'mechanical',         '', 'AV'),
    ({'AV': 'Μηχανική προσθετική αορτική βαλβίδα.'},                1, 0, 'mechanical',         '', 'AV'),
    ({'AV': 'Δίφυλλη μηχανική βαλβίδα.'},                           1, 0, 'mechanical',         '', 'AV'),
    ({'AV': 'Μεταλλική προσθετική βαλβίδα.'},                       1, 0, 'mechanical',         '', 'AV'),
    ({'AV': 'Μεταλλική βαλβίδα.'},                                  0, 0, 'mechanical',         '', 'AV'),
    ({'AV': 'Προσθετική βαλβίδα με φυσιολογικές κλίσεις.'},         1, 0, 'generic_prosthetic', 'generic_prosthetic', 'AV'),
    ({'AV': 'Προσθετική αορτική βαλβίδα (βιοπροσθετική βαλβίδα).'}, 1, 1, 'bioprosthetic',      '', 'AV'),
    ({'AV': 'Μηχανική βαλβίδα. Εντός αυτής TAVI (valve-in-valve).'}, 1, 0, 'mixed',             'mech_and_bio', 'AV'),
    ({'AV': 'Τριγλώχινη, με φυσιολογική διάνοιξη.'},                0, 0, 'none',               '', ''),
    ({},                                                            0, 0, 'none',               '', ''),

    # ── Συμπεράσματα / Σχόλια ────────────────────────────────────────────
    # Εύρημα μόνο στα Συμπεράσματα
    ({'AV': 'Τριγλώχινη.', 'CONCLUSIONS': 'Βιοπροσθετική αορτική βαλβίδα με καλή λειτουργία.'},
     1, 1, 'bioprosthetic', '', 'CONCLUSIONS'),
    # Χωρίς AV section, εύρημα στη Διάγνωση
    ({'COMMENTS': 'Διάγνωση: Κατάσταση μετά από TAVI.'},
     1, 1, 'tavr', '', 'COMMENTS'),
    # Σκέτο «προσθετική» στο AV διευκρινίζεται από τα Συμπεράσματα → 1, χωρίς flag
    ({'AV': 'Προσθετική βαλβίδα.', 'CONCLUSIONS': 'Κατάσταση μετά από TAVI.'},
     1, 1, 'tavr', '', 'CONCLUSIONS'),
    # Μηχανική ΜΙΤΡΟΕΙΔΗΣ στα Συμπεράσματα → απορρίπτεται
    ({'AV': 'Τριγλώχινη.', 'CONCLUSIONS': 'Μηχανική μιτροειδής βαλβίδα με καλή λειτουργία.'},
     0, 0, 'none', '', ''),
    ({'CONCLUSIONS': 'Μηχανική βαλβίδα σε μιτροειδή θέση.'},
     0, 0, 'none', '', ''),
    # Σχεδιαζόμενο TAVI → δεν μετράει + flag
    ({'CONCLUSIONS': 'Σοβαρή αορτική στένωση. Παραπέμπεται για TAVI.'},
     0, 0, 'none', 'tavr_planned', ''),
    ({'COMMENTS': 'Υποψήφιος για TAVR.'},
     0, 0, 'none', 'tavr_planned', ''),
    # Βιοπροσθετική στο AV + μηχανική αορτική στα Σχόλια → mixed
    ({'AV': 'Βιοπροσθετική βαλβίδα.', 'COMMENTS': 'Μηχανική αορτική βαλβίδα.'},
     1, 0, 'mixed', 'mech_and_bio', 'COMMENTS'),
    # Αορτή + μιτροειδής στην ίδια πρόταση → κρατιέται + flag
    ({'CONCLUSIONS': 'Βιοπροσθετική αορτική βαλβίδα, μηχανική βαλβίδα σε μιτροειδή θέση.'},
     1, 0, 'mixed', 'mech_and_bio;multi_valve_sentence', 'CONCLUSIONS'),
    # Άσχετα Συμπεράσματα
    ({'AV': 'Τριγλώχινη.', 'CONCLUSIONS': 'Μέτρια ανεπάρκεια μιτροειδούς. Ρίζα αορτής 40 mm.'},
     0, 0, 'none', '', ''),
]


def run_self_test() -> bool:
    ok_all = True
    logger.info("SELF-TEST")
    for secs, exp_a, exp_b, exp_grade, exp_flags, exp_src in SELF_TESTS:
        res = grade_tavr(secs)
        v5 = get_tavr_v5(secs)
        ok = (res['label_A'] == exp_a and res['label_B'] == exp_b and
              res['grade_B'] == exp_grade and res['flags'] == exp_flags and
              res['source_B'] == exp_src and not (v5 == 1 and res['label_A'] == 0))
        if not ok:
            ok_all = False
        desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
        logger.info(f"  [{'PASS' if ok else 'FAIL':5}] {desc}\n"
                    f"          → A={res['label_A']} B={res['label_B']} grade_B={res['grade_B']} "
                    f"source_B={res['source_B'] or '-'}"
                    f"{'  flags=' + res['flags'] if res['flags'] else ''}"
                    f"{'' if ok else f'  (αναμενόταν A={exp_a} B={exp_b} {exp_grade} [{exp_flags}] {exp_src or chr(45)}, v5={v5})'}")
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
            label_rows.append({'exam_id': e['exam_id'], 'tavr_incl_mech': '', 'tavr_excl_mech': '',
                               'status': 'read_failed', 'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        res = grade_tavr(sections)
        v5 = get_tavr_v5(sections)
        status = 'ok' if get_sec(sections, 'AV') else 'no_AV_section'

        label_rows.append({'exam_id':          e['exam_id'],
                           'tavr_incl_mech':   res['label_A'],
                           'tavr_excl_mech':   res['label_B'],
                           'grade_B':          res['grade_B'],
                           'flags':            res['flags'],
                           'sources_A':        res['sources_A'],
                           'rule_A':           res['rule_A'],
                           'phrase_A':         original_phrase(res['raw_A'], res['match_A']),
                           'source_B':         res['source_B'],
                           'rule_B':           res['rule_B'],
                           'phrase_B':         original_phrase(res['raw_B'], res['match_B']),
                           'label_v5':         v5,
                           'changed_vs_v5_A':  int(v5 != res['label_A']),
                           'changed_vs_v5_B':  int(v5 != res['label_B']),
                           'status':           status,
                           'av_text':          get_sec(sections, 'AV'),
                           'conclusions_text': get_sec(sections, 'CONCLUSIONS'),
                           'comments_text':    get_sec(sections, 'COMMENTS'),
                           'report_path':      e['report_path']})

        for m in res['matches']:
            evidence_rows.append({
                'exam_id':        e['exam_id'],
                'source':         m['source'],
                'rule':           m['rule'],
                'used_by':        m['used_by'],
                'matched_phrase': original_phrase(m['raw'], m['match']),
                'decisive_A':     m['decisive_A'],
                'decisive_B':     m['decisive_B'],
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
    logger.info("=" * 60)
    logger.info(f"Εξετάσεις: {len(label_rows)} | αναγνώστηκαν: {len(ok_rows)} | "
                f"αποτυχίες: {len(label_rows) - len(ok_rows)}")
    if ok_rows:
        n = len(ok_rows)
        n_a    = sum(r['tavr_incl_mech'] == 1 for r in ok_rows)
        n_b    = sum(r['tavr_excl_mech'] == 1 for r in ok_rows)
        n_v5   = sum(r['label_v5'] == 1 for r in ok_rows)
        n_lost = sum(r['label_v5'] == 1 and r['tavr_incl_mech'] == 0 for r in ok_rows)
        n_new  = sum(r['label_v5'] == 0 and r['tavr_incl_mech'] == 1 for r in ok_rows)
        n_fl   = sum(bool(r['flags']) for r in ok_rows)
        logger.info(f"Θετικές v5: {n_v5} ({100 * n_v5 / n:.1f}%)")
        logger.info(f"Ανάλυση Α (incl mech): {n_a} ({100 * n_a / n:.1f}%) | "
                    f"νέες θετικές από Συμπεράσματα/Σχόλια: {n_new}")
        logger.info(f"Ανάλυση Β (excl mech): {n_b} ({100 * n_b / n:.1f}%)")
        if n_lost:
            logger.warning(f"SANITY CHECK ΑΠΕΤΥΧΕ: {n_lost} εξετάσεις με v5=1 αλλά Α=0 — έλεγξε τον κώδικα!")
        else:
            logger.info("Sanity check: καμία θετική του v5 δεν χάθηκε στην Ανάλυση Α ✓")
        logger.info(f"Γραμμές με flag: {n_fl}")
        flag_counts = {}
        for r in ok_rows:
            for f in filter(None, r['flags'].split(';')):
                flag_counts[f] = flag_counts.get(f, 0) + 1
        for f, c in sorted(flag_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {f:<24} {c:>6}")
        grades = {}
        for r in ok_rows:
            grades[r['grade_B']] = grades.get(r['grade_B'], 0) + 1
        logger.info("Κατανομή grade_B:")
        for g, c in sorted(grades.items(), key=lambda x: -x[1]):
            logger.info(f"  {g:<24} {c:>6}")
        srcs = {}
        for r in ok_rows:
            if r.get('source_B'):
                srcs[r['source_B']] = srcs.get(r['source_B'], 0) + 1
        logger.info("Αποφασιστική πηγή (Ανάλυση Β):")
        for s, c in sorted(srcs.items(), key=lambda x: -x[1]):
            logger.info(f"  {s:<24} {c:>6}")
    logger.info(f"Excel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/tavr_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
