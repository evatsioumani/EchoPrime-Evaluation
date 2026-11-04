r"""
pacemaker_v6x.py
================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για την
ανίχνευση εμφυτευμένης συσκευής (βηματοδότης / απινιδωτής) στα reports.

Παράγονται ΔΥΟ labels:

  ΑΝΑΛΥΣΗ STRICT    — pacemaker
      Θετικό ΜΟΝΟ όταν υπάρχει αναφορά σε βηματοδότη / βηματοδότηση
      (pattern του v5: βηματοδοτ\w+ → βηματοδότης, βηματοδότη, βηματοδοτικός,
      βηματοδοτικού ρυθμού, βηματοδότηση, βηματοδότησης ...).

  ΑΝΑΛΥΣΗ INCLUSIVE — pacemaker_incl_icd
      Θετικό όταν υπάρχει αναφορά σε βηματοδότη Ή απινιδωτή Ή καλώδιο.
      Οι όροι «απινιδωτικό» και «καλώδιο» είναι ΑΝΕΞΑΡΤΗΤΟΙ: αρκεί ο καθένας
      μόνος του (δεν απαιτείται να εμφανίζονται μαζί).

  Εξ ορισμού INCLUSIVE >= STRICT.

ΠΗΓΗ ΚΕΙΜΕΝΟΥ — ΟΛΟ το report
  Σε αντίθεση με τις βαλβίδες, ΔΕΝ υπάρχει ιεραρχία / fallback. Σαρώνονται ΟΛΑ
  τα sections του parse_sections() ταυτόχρονα: ανατομικά (LV, RV, TV ...),
  Αιτιολογία παραπομπής (REFERRAL), Υποκείμενος καρδιακός ρυθμός (RHYTHM),
  Ευρήματα, Συμπεράσματα, Σχόλια/Διάγνωση, Imported Findings και κάθε
  αναγνωρισμένο header (UNKNOWN:*). Αρκεί ΜΙΑ μη αρνητική αναφορά οπουδήποτε.

ΛΟΓΙΚΗ ΑΞΙΟΛΟΓΗΣΗΣ
  1. Κάθε section χωρίζεται σε προτάσεις (τελεία που δεν είναι δεκαδική, ';', '\n').
  2. Σε κάθε πρόταση αναζητούνται τρεις ομάδες όρων (σε normalize()-αρισμένο
     κείμενο, χωρίς τόνους):
        pacemaker : βηματοδοτ\w+                     (αυτούσιο από v5)
        icd       : α?πινιδωτ\w*                     (και «πινιδωτικών» χωρίς α)
        lead      : κ(αλ|α|λ)[ωο]δι\w*               (καλώδιο / καώδιων / κλώδιο / καλόδιο)
     ΣΗΜΕΙΩΣΗ: το «απινίδωση» (καρδιοανάταξη) ΔΕΝ ταιριάζει — διαφέρει στο τ/σ.
     ΣΗΜΕΙΩΣΗ: στο lead τουλάχιστον ένα από α / λ είναι υποχρεωτικό, ώστε να μην
     πιάνεται το «κωδικός».
  3. Άρνηση: ίδιο regex με το _has_negation του v5 (χωρίς / δεν εντοπίζεται /
     δεν παρατηρείται / δεν υπάρχει) σε παράθυρο 60 χαρακτήρων ΠΡΙΝ τον όρο,
     αλλά ΠΕΡΙΟΡΙΣΜΕΝΟ ΜΕΣΑ ΣΤΗΝ ΙΔΙΑ ΠΡΟΤΑΣΗ (στο v5 διέσχιζε προτάσεις).
  4. STRICT    = 1 αν υπάρχει μη αρνητική αναφορά pacemaker.
     INCLUSIVE = 1 αν υπάρχει μη αρνητική αναφορά pacemaker / icd / lead.

FLAGS (στήλη flags) — οι γραμμές με flag ΕΛΕΓΧΟΥ χρωματίζονται πορτοκαλί:
  pacemaker_icd_only          INCLUSIVE=1, STRICT=0 (αναμενόμενο delta — χωρίς χρώμα)
  typo_match                  ταίριαξε ορθογραφική παραλλαγή (π.χ. πινιδωτ-, καώδιο) (χωρίς χρώμα)
  lead_only                   θετικό INCLUSIVE ΜΟΝΟ από τη λέξη «καλώδιο»          [ΕΛΕΓΧΟΣ]
  device_negated              υπάρχει αναφορά που ακυρώθηκε από άρνηση            [ΕΛΕΓΧΟΣ]
  pacemaker_outside_sections  όρος υπάρχει στο HTML αλλά σε κανένα section
                              (π.χ. κείμενο εκτός <p>, σε πίνακα)                [ΕΛΕΓΧΟΣ]
  non_monotonic               STRICT=1 αλλά INCLUSIVE=0 — ΣΦΑΛΜΑ                  [ΕΛΕΓΧΟΣ]

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: ένα Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά αναφορά συσκευής (section, ομάδα, φράση, άρνηση, πρόταση)

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
logger = logging.getLogger("pacemaker")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από v6x, + REFERRAL / RHYTHM)
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
    # ΠΡΟΣΟΧΗ ΣΤΗ ΣΕΙΡΑ: το IMPORTED ΠΡΕΠΕΙ να προηγείται του FINDINGS
    # (το 'findings' ταιριάζει και στο 'imported findings').
    'IMPORTED':    ['imported findings', 'imported finding', 'imported'],
    'FINDINGS':    ['ευρήματα', 'ευρηματα', 'findings'],
    'CONCLUSIONS': ['συμπεράσματα', 'συμπερασματα', 'conclusions', 'συμπέρασμα', 'συμπερασμα'],
    'COMMENTS':    ['σχόλια', 'σχολια', 'διάγνωση', 'διαγνωση', 'echo summary'],
    # ΝΕΑ keys — μπαίνουν ΤΕΛΕΥΤΑΙΑ, ώστε να μην «κλέβουν» headers που ήδη
    # αναγνωρίζονται. Χωρίς αυτά οι ενότητες γίνονται UNKNOWN:* — θα σαρώνονταν
    # ούτως ή άλλως· τα keys υπάρχουν μόνο για καθαρή στήλη source_sections.
    'REFERRAL':    ['αιτιολογία παραπομπής', 'αιτιολογια παραπομπης',
                    'αιτιολογία εξέτασης', 'αιτιολογια εξετασης'],
    'RHYTHM':      ['υποκείμενος καρδιακός ρυθμός', 'υποκειμενος καρδιακος ρυθμος',
                    'καρδιακός ρυθμός', 'καρδιακος ρυθμος'],
}


def parse_sections(html: str) -> dict:
    """
    Διαβάζει το report HTML και επιστρέφει dict:
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


def html_plain_text(html: str) -> str:
    """Όλο το ορατό κείμενο του HTML (για το δίχτυ ασφαλείας pacemaker_outside_sections)."""
    if not html:
        return ''
    if BS4_AVAILABLE:
        return BeautifulSoup(html, 'html.parser').get_text(separator=' ')
    return re.sub(r'<[^>]+>', ' ', html)


# =============================================================================
# TEXT HELPERS  (αυτούσια από ground_truth_extractor)
# =============================================================================

def normalize(text: str) -> str:
    text = text.lower().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', text)


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
# PATTERNS
# =============================================================================
# Όλα εφαρμόζονται σε normalize()-αρισμένο κείμενο (πεζά, χωρίς τόνους).

# Βηματοδότης — ΑΥΤΟΥΣΙΟ από v5
PM_PAT = r'βηματοδοτ\w+'

# Απινιδωτής — αρχικό α προαιρετικό (ορθογραφικό «πινιδωτικών»).
# Πιάνει: απινιδωτής, απινιδωτή, απινιδωτικό, απινιδωτικών, πινιδωτικών ...
# ΔΕΝ πιάνει: απινίδωση (καρδιοανάταξη) — διαφέρει στο τ/σ.
ICD_PAT = r'\bα?πινιδωτ\w*'

# Καλώδιο — ανεκτικό σε ορθογραφικά: καλώδιο, καλωδίων, καώδιων, κλώδιο, καλόδιο.
# Τουλάχιστον ένα από α / λ είναι υποχρεωτικό (αλλιώς θα έπιανε το «κωδικός»).
LEAD_PAT = r'\bκ(?:αλ|α|λ)[ωο]δι\w*'

# Σειρά = προτεραιότητα για το decisive της INCLUSIVE (το πιο ειδικό πρώτα)
DEVICE_GROUPS = (
    ('pacemaker', PM_PAT),
    ('icd',       ICD_PAT),
    ('lead',      LEAD_PAT),
)

# Κανονική ορθογραφία ανά ομάδα — ό,τι άλλο ταιριάζει σημειώνεται ως typo
CANONICAL = {
    'pacemaker': r'βηματοδοτ',
    'icd':       r'απινιδωτ',
    'lead':      r'καλωδι',
}

# Άρνηση — ΑΥΤΟΥΣΙΟ regex του _has_negation του v5
NEG_PAT = r'(?:δεν\s+(?:εντοπ[ίι]ζεται|παρατηρε[ίι]ται|υπ[άα]ρχει)|χωρ[ίι][σς])'
NEG_WINDOW = 60

# Διαχωρισμός σε προτάσεις: τελεία (όχι δεκαδική), άνω τελεία, αλλαγή γραμμής
SENT_SPLIT = r'\.(?!\d)|;|\n'


# =============================================================================
# CORE LOGIC
# =============================================================================

def find_device_mentions(sections: dict) -> list:
    """
    Σαρώνει ΟΛΑ τα sections, ανά πρόταση, και επιστρέφει κάθε αναφορά συσκευής:
      {section, group, match, raw_sentence, negated, negation, typo}

    Η άρνηση ελέγχεται μόνο μέσα στην ίδια πρόταση, σε παράθυρο NEG_WINDOW
    χαρακτήρων πριν τον όρο.
    """
    mentions = []
    for key, raw in sections.items():
        if not raw or not raw.strip():
            continue
        for sent in re.split(SENT_SPLIT, raw):
            sent = sent.strip()
            if not sent:
                continue
            s = normalize(sent)
            for group, pat in DEVICE_GROUPS:
                for m in re.finditer(pat, s):
                    preceding = s[max(0, m.start() - NEG_WINDOW): m.start()]
                    neg = re.search(NEG_PAT, preceding)
                    mentions.append({
                        'section':      key,
                        'group':        group,
                        'match':        m.group(),
                        'raw_sentence': sent,
                        'negated':      1 if neg else 0,
                        'negation':     neg.group() if neg else '',
                        'typo':         0 if re.match(CANONICAL[group], m.group()) else 1,
                        'decisive_strict': 0,
                        'decisive_incl':   0,
                    })
    return mentions


def grade_pacemaker(sections: dict) -> dict:
    """
    STRICT    : 1 αν υπάρχει μη αρνητική αναφορά βηματοδότη.
    INCLUSIVE : 1 αν υπάρχει μη αρνητική αναφορά βηματοδότη / απινιδωτή / καλωδίου.
    """
    out = {'label_strict': 0, 'label_incl': 0, 'device_type': 'none',
           'rule_strict': '', 'phrase_strict': '', 'rule_incl': '', 'phrase_incl': '',
           'source_sections': '', 'flags': [], 'mentions': []}

    mentions = find_device_mentions(sections)
    out['mentions'] = mentions
    if not mentions:
        return out

    valid = [m for m in mentions if not m['negated']]
    groups_present = [g for g, _ in DEVICE_GROUPS if any(m['group'] == g for m in valid)]

    # ── STRICT ───────────────────────────────────────────────────────────
    pm = [m for m in valid if m['group'] == 'pacemaker']
    if pm:
        dec = pm[0]
        dec['decisive_strict'] = 1
        out['label_strict'] = 1
        out['rule_strict'] = 'pacemaker_term'
        out['phrase_strict'] = original_phrase(dec['raw_sentence'], dec['match'])

    # ── INCLUSIVE (προτεραιότητα decisive: pacemaker > icd > lead) ───────
    if groups_present:
        first_group = groups_present[0]
        dec = next(m for m in valid if m['group'] == first_group)
        dec['decisive_incl'] = 1
        out['label_incl'] = 1
        out['rule_incl'] = f'{first_group}_term'
        out['phrase_incl'] = original_phrase(dec['raw_sentence'], dec['match'])

    out['device_type'] = '+'.join(groups_present) if groups_present else 'none'

    seen = []
    for m in valid:
        if m['section'] not in seen:
            seen.append(m['section'])
    out['source_sections'] = ';'.join(seen)

    # ── FLAGS ────────────────────────────────────────────────────────────
    if out['label_incl'] == 1 and out['label_strict'] == 0:
        out['flags'].append('pacemaker_icd_only')
        if groups_present == ['lead']:
            out['flags'].append('lead_only')
    if any(m['negated'] for m in mentions):
        out['flags'].append('device_negated')
    if any(m['typo'] for m in valid):
        out['flags'].append('typo_match')
    if out['label_incl'] < out['label_strict']:
        out['flags'].append('non_monotonic')

    return out


# ── Drop-in wrappers ─────────────────────────────────────────────────────────

def get_pacemaker(sections: dict) -> int:
    return grade_pacemaker(sections)['label_strict']


def get_pacemaker_incl_icd(sections: dict) -> int:
    return grade_pacemaker(sections)['label_incl']


# =============================================================================
# ΑΝΑΓΝΩΣΗ REPORTS (HTML ή CHM)  (αυτούσιο από v6x)
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

# Μόνο αυτά τα flags χρωματίζουν τη γραμμή
REVIEW_FLAGS = {'lead_only', 'device_negated', 'pacemaker_outside_sections', 'non_monotonic'}


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
    cols1 = ['exam_id', 'pacemaker', 'pacemaker_incl_icd', 'delta', 'device_type',
             'rule_strict', 'phrase_strict', 'rule_incl', 'phrase_incl',
             'source_sections', 'n_mentions', 'n_negated',
             'flags', 'status', 'device_sentences', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 11, 18, 8, 22,
                16, 26, 16, 26,
                28, 11, 10,
                40, 14, 90, 60],
               wrap_cols=('device_sentences',))
    i_flag  = cols1.index('flags')
    i_delta = cols1.index('delta')
    for row in ws1.iter_rows(min_row=2):
        flags = row[i_flag].value or ''
        if any(f in REVIEW_FLAGS for f in flags.split(';') if f):
            for c in row:
                c.fill = FLAG_FILL
        if row[i_delta].value == 1:
            row[i_delta].font = chg_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'section', 'group', 'matched_phrase', 'typo',
             'negated', 'negation', 'decisive_strict', 'decisive_incl', 'sentence']
    fill_sheet(ws2, cols2, evidence_rows,
               [18, 22, 12, 26, 7, 9, 16, 15, 14, 90], wrap_cols=('sentence',))

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
            label_rows.append({'exam_id': e['exam_id'], 'status': 'read_failed',
                               'report_path': e['report_path']})
            continue

        sections = parse_sections(html)
        res = grade_pacemaker(sections)
        flags = list(res['flags'])

        # Δίχτυ ασφαλείας: όρος στο HTML που δεν πέρασε σε κανένα section
        if not res['mentions']:
            full = normalize(html_plain_text(html))
            if any(re.search(pat, full) for _, pat in DEVICE_GROUPS):
                flags.append('pacemaker_outside_sections')

        if not sections:
            status = 'no_sections'
        else:
            status = 'ok'

        sent_seen, sent_list = set(), []
        for m in res['mentions']:
            tag = f"[{m['section']}] {m['raw_sentence']}"
            if tag not in sent_seen:
                sent_seen.add(tag)
                sent_list.append(tag)

        label_rows.append({
            'exam_id':            e['exam_id'],
            'pacemaker':          res['label_strict'],
            'pacemaker_incl_icd': res['label_incl'],
            'delta':              res['label_incl'] - res['label_strict'],
            'device_type':        res['device_type'],
            'rule_strict':        res['rule_strict'],
            'phrase_strict':      res['phrase_strict'],
            'rule_incl':          res['rule_incl'],
            'phrase_incl':        res['phrase_incl'],
            'source_sections':    res['source_sections'],
            'n_mentions':         len(res['mentions']),
            'n_negated':          sum(m['negated'] for m in res['mentions']),
            'flags':              ';'.join(flags),
            'status':             status,
            'device_sentences':   ' | '.join(sent_list),
            'report_path':        e['report_path'],
        })

        for m in res['mentions']:
            evidence_rows.append({
                'exam_id':         e['exam_id'],
                'section':         m['section'],
                'group':           m['group'],
                'matched_phrase':  original_phrase(m['raw_sentence'], m['match']),
                'typo':            m['typo'],
                'negated':         m['negated'],
                'negation':        m['negation'],
                'decisive_strict': m['decisive_strict'],
                'decisive_incl':   m['decisive_incl'],
                'sentence':        m['raw_sentence'],
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
        logger.info(f"\n  {'Label':<24} {'Pos':>5} {'Total':>7} {'%':>6}")
        logger.info(f"  {'-'*44}")
        for col in ('pacemaker', 'pacemaker_incl_icd'):
            pos_n = sum(r[col] == 1 for r in ok_rows)
            logger.info(f"  {col:<24} {pos_n:>5} {n:>7} {100 * pos_n / n:>5.1f}%")

        d = sum(r['delta'] == 1 for r in ok_rows)
        logger.info(f"\nΕπιπλέον θετικές στην INCLUSIVE (απινιδωτής/καλώδιο): +{d} ({100 * d / n:.1f}%)")

        dist = {}
        for r in ok_rows:
            dist[r['device_type']] = dist.get(r['device_type'], 0) + 1
        logger.info("\nΚατανομή device_type:")
        for g, c in sorted(dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {g:<28} {c:>6}")

        sec_dist = {}
        for r in ok_rows:
            for s in filter(None, (r['source_sections'] or '').split(';')):
                sec_dist[s] = sec_dist.get(s, 0) + 1
        if sec_dist:
            logger.info("\nSections με μη αρνητική αναφορά συσκευής:")
            for s, c in sorted(sec_dist.items(), key=lambda x: -x[1]):
                logger.info(f"  {s:<36} {c:>6}")

        flag_counts = {}
        for r in ok_rows:
            for f in filter(None, r['flags'].split(';')):
                flag_counts[f] = flag_counts.get(f, 0) + 1
        if flag_counts:
            logger.info("\nFlags:")
            for f, c in sorted(flag_counts.items(), key=lambda x: -x[1]):
                mark = '  ← ΕΛΕΓΧΟΣ' if f in REVIEW_FLAGS else ''
                logger.info(f"  {f:<28} {c:>6}{mark}")

        n_mon = flag_counts.get('non_monotonic', 0)
        if n_mon:
            logger.warning(f"ΣΦΑΛΜΑ: {n_mon} εξετάσεις με STRICT=1 αλλά INCLUSIVE=0!")

    logger.info(f"\nExcel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/pacemaker_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή

    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
