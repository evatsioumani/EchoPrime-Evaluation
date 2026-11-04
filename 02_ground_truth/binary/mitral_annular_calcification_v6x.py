r"""
mitral_annular_calcification_v6x.py
===================================
Αυτοτελές script (δεν κάνει import από άλλο αρχείο του project) για το finding

  mitral_annular_calcification   (επασβέστωση μιτροειδικού δακτυλίου — MAC)

ΟΔΗΓΙΑ ΕΠΙΒΛΕΠΟΝΤΑ
  "Include cases of mild mitral annular calcification and run this once,
   including mild, moderate, and severe cases."

  → ΕΝΑ μόνο label:  mitral_annular_calcification_incl_mild
      Θετικά: mild + borderline + moderate/severe + αναφορές χωρίς βαθμό (unqualified).
      Δεν υπάρχει STRICT ανάλυση και δεν υπάρχει στήλη v5.

ΔΕΥΤΕΡΟ LABEL (v6x2) — label_mod_severe  (στήλη mitral_annular_calcification)
  Ίδια εξαγωγή, ίδιο grade (ο υψηλότερος βαθμός σε όλες τις πηγές)· αλλάζει
  ΜΟΝΟ ποια grades μετράνε θετικά. Κανένα νέο regex.
      1 : moderate_severe, unqualified (θετικό χωρίς δηλωμένο βαθμό)
      0 : mild, borderline, none
  Επειδή GRADE_RANK: mild > unqualified, ένα unqualified μετράει ΜΟΝΟ αν δεν
  δηλώνεται βαθμός πουθενά στο report (π.χ. MV «Επασβέστωση οπίσθιου δακτυλίου»
  + Συμπεράσματα «Ήπια επασβέστωση μιτροειδικού δακτυλίου» → mild → 0).
  Εγγυάται label_mod_severe ≤ label (υποσύνολο του incl_mild).

ΣΧΕΣΗ ΜΕ ΤΟ v5 (get_mitral_annular_calcification)
  Τα positive patterns του v5 διατηρούνται ως λογική, με τις εξής ΣΥΜΦΩΝΗΜΕΝΕΣ αλλαγές:

  1. Ουσιαστικό «επασβέστωση» → ενιαίο CALC = επα[σς]{1,2}βεσ\w+
     Καλύπτει όλες τις καταλήξεις και τον πληθυντικό (επασβεστώσεις/-ώσεων),
     τη μετοχή (επασβεστωμένη/-ος/-ο) και το typo «επασσβέστωση».
     Στο v5 ο πληθυντικός δεν ταίριαζε σε ΚΑΝΕΝΑ pattern.
  2. Mild: το v5 έπιανε μόνο «μικρού βαθμού» / «ήπια». Τώρα και
     μικρή/μικρές, ελαφρ-, ήπιου βαθμού, ελάχιστη, εστιακή/-ές, και αντίστροφη
     σειρά («επασβέστωση δακτυλίου μικρού βαθμού»). Αυτό αλλάζει κυρίως το GRADE:
     στο v5 το «μικρή επασβέστωση οπίσθιου μιτροειδικού δακτυλίου» έβγαινε θετικό
     χωρίς βαθμό.
  3. Borderline: εκτός από «μικρού προς μετρίου» και «ήπια έως/-/ μέτρια».
     (Το «έως» γράφεται ΧΩΡΙΣ τόνο — το κείμενο είναι normalize()-αρισμένο.)
  4. Negation guard (νέο — δεν υπήρχε στο v5): «χωρίς / δεν παρατηρείται /
     απουσία … επασβέστωση» → η φράση έως το τέλος του clause ΑΓΝΟΕΙΤΑΙ.
     Στο v5 το «Χωρίς επασβέστωση του μιτροειδικού δακτυλίου» έδινε 1.
     Η άρνηση ΔΕΝ μηδενίζει θετική αναφορά σε άλλο clause/πρόταση.
  5. Στο MV section, «επασβέστωση (οπίσθιου) δακτυλίου» χωρίς τη λέξη
     «μιτροειδικού» = MAC (rule annulus_implicit). Στο v5 δεν πιανόταν.
  6. Γλωχίνες / υπομιτροειδική συσκευή: ΚΑΜΙΑ αλλαγή (απόφαση χρήστη) — ό,τι
     έπιανε το v5 πιάνεται και εδώ, χωρίς flag.

ΠΗΓΗ ΚΕΙΜΕΝΟΥ — UNION (όχι fallback)
  1. MV section — αυτούσιο.
  2. Συμπεράσματα + Σχόλια/Διάγνωση — ΠΑΝΤΑ, ανά πρόταση. Κρατιούνται μόνο
     προτάσεις με όρο επασβέστωσης ΚΑΙ αναφορά στη μιτροειδή (ή «MAC»).
     Στο MAC το MV section σχεδόν πάντα υπάρχει (περιγράφει MR/MS), οπότε
     ένα αυστηρό fallback δεν θα διάβαζε σχεδόν ποτέ τα Συμπεράσματα.
  3. Imported Findings — ΜΟΝΟ αν ούτε το MV ούτε τα Συμπεράσματα/Σχόλια
     αναφέρουν καθόλου επασβέστωση (ούτε θετικά ούτε αρνητικά).

  label = OR σε όλες τις πηγές.
  grade = ο υψηλότερος βαθμός: moderate_severe > borderline > mild > unqualified.

  Multi-valve προτάσεις στα Συμπεράσματα: clause φιλτράρισμα όπως στη μιτροειδή.
  Επειδή το ουσιαστικό μπορεί να είναι ΚΟΙΝΟ («Επασβέστωση αορτικής βαλβίδας
  και μιτροειδικού δακτυλίου»), αν τα clauses της μιτροειδούς δεν δώσουν
  αποτέλεσμα, ελέγχεται ο κανόνας εγγύτητας ctx_proximity στην πλήρη πρόταση
  (επασβέστωση … ≤6 λέξεις … μιτροειδικού δακτυλίου) → grade unqualified.

GRADE
  none | mild | borderline | moderate_severe | unqualified
  unqualified = θετικό χωρίς δηλωμένο βαθμό (π.χ. «Επασβέστωση οπίσθιου
  μιτροειδικού δακτυλίου»).

FLAGS (στήλη flags) — όσα σημειώνονται [ΕΛΕΓΧΟΣ] χρωματίζουν τη γραμμή πορτοκαλί:
  conclusions_gain           θετικό ΜΟΝΟ από Συμπεράσματα/Σχόλια (MV = 0)
  imported_findings          χρησιμοποιήθηκε η παράγραφος Imported Findings
  mac_negated                ενεργοποιήθηκε negation guard
  mac_mixed_severity         συνυπάρχουν mild και moderate/severe αναφορές
  multi_valve_sentence       πρόταση με >1 βαλβίδα → clause φιλτράρισμα   [ΕΛΕΓΧΟΣ]
  mac_negated_and_positive   άρνηση ΚΑΙ θετική αναφορά στο ίδιο report     [ΕΛΕΓΧΟΣ]
  source_conflict            MV αρνητικό (άρνηση) αλλά Συμπεράσματα θετικά  [ΕΛΕΓΧΟΣ]
  mac_annulus_unspecified    «επασβέστωση δακτυλίου» στα Συμπεράσματα χωρίς
                             να ονομάζεται βαλβίδα                         [ΕΛΕΓΧΟΣ]
  mac_uncovered              υπάρχει όρος επασβέστωσης αλλά label = 0
                             (π.χ. σκέτο «Επασβέστωση.» ή γλωχίνες)        [ΕΛΕΓΧΟΣ]
  mac_mentioned_elsewhere    MAC γραμμένο σε άλλο ανατομικό section
                             (π.χ. AV) ενώ label = 0                       [ΕΛΕΓΧΟΣ]

Εκτέλεση: F5. Ρυθμίσεις (paths) στο block MAIN στο τέλος του αρχείου.

Output: Excel με 2 sheets
  Labels   : μία γραμμή ανά εξέταση
  Evidence : μία γραμμή ανά pattern που ταίριαξε (πηγή, κανόνας, αν καθόρισε το label)

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
logger = logging.getLogger("mac")


# =============================================================================
# REPORT → SECTIONS  (αυτούσιο από mitral_valve_v6x.py)
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
}


def parse_sections(html: str) -> dict:
    """
    Διαβάζει το report HTML και επιστρέφει dict { 'LV': 'κείμενο...', ... }.
      - Underlined headers → αναγνώριση μέσω SECTION_KEYS
      - Orphan paragraphs: startswith check για Συμπεράσματα/Σχόλια/Διάγνωση,
        αλλιώς προσθήκη στο τρέχον section.
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
# PATTERNS
# Όλα εφαρμόζονται σε normalize()-αρισμένο κείμενο → γράφονται ΧΩΡΙΣ τόνους
# και σε πεζά.
# =============================================================================

# Ουσιαστικό / μετοχή επασβέστωσης — όλες οι καταλήξεις, ενικός και πληθυντικός.
# επασβεστωση, επασβεστωσης, επασβεστωσεις, επασβεστωσεων, επασβεστωμενη/-ος/-ο,
# και το typo επασσβεστωση.
CALC = r'επα[σς]{1,2}βεσ\w+'

# Οποιοσδήποτε όρος επασβέστωσης — για επιλογή προτάσεων και για mac_uncovered
CALC_ANY = r'επα[σς]{1,2}βεσ|ασβεσ|ασβεστοποιητ|calcif|\bmac\b'

# ── Negation guard ───────────────────────────────────────────────────────────
# Η φράση από την άρνηση μέχρι το τέλος του clause (, ; . ·) αγνοείται.
# Όριο 3 λέξεων ανάμεσα — «χωρίς στένωση ή επασβέστωση» πιάνεται,
# ενώ το κόμμα σταματά το match («Χωρίς στένωση, με επασβέστωση» → ΔΕΝ πιάνεται).
NEGATION = (
    r'(?:\bχωρις|\bδεν\s+(?:παρατηρ\w+|εντοπιζ\w+|υπαρχ\w+|απεικονιζ\w+|εμφανιζ\w+|ανευρισκ\w+|διαπιστων\w+)'
    r'|\bαπουσια|\bμη)'
    r'\s+(?:\w+\s+){0,3}?(?:' + CALC + r'|ασβεσ\w+)'
)
CLAUSE_END = r'[,;.·]'

# ── Borderline (μικρού/ήπιου προς/έως μετρίου) ───────────────────────────────
MAC_BORDERLINE = [
    ('borderline_fwd',
     r'(?:μικρ\w*|ηπι\w*)(?:\s+βαθμου)?\s*(?:\s(?:προς|εως)\s|[-–/])\s*μετρι\w*(?:\s+βαθμου)?\s+' + CALC),
    ('borderline_rev',
     CALC + r'\s+(?:\w+\s+){0,4}?(?:μικρ\w*|ηπι\w*)\s*(?:\s(?:προς|εως)\s|[-–/])\s*μετρι\w*'),
]

# ── Moderate / severe ────────────────────────────────────────────────────────
# Η αντίστροφη μορφή αποκλείει «… μετρίου βαθμού ανεπάρκεια/στένωση», ώστε ο
# βαθμός άλλου finding να μη χρεώνεται στην επασβέστωση.
OTHER_FINDING_NOUN = r'(?!\s+(?:ανεπαρκ|στενωσ|διαφυγ|διαταση|υπερτροφ|παχυνση|πεχυνση))'
MAC_SEVERE = [
    ('severe_fwd',
     r'(?:μετρι\w*|σοβαρ\w*|σημαντικ\w*|εκτεταμεν\w*|εντον\w*)(?:\s+βαθμου)?\s+' + CALC),
    ('severe_rev',
     CALC + r'\s+(?:\w+\s+){0,4}?(?:μετριου|σοβαρου|σημαντικου)\s+βαθμου' + OTHER_FINDING_NOUN),
]

# ── Mild ─────────────────────────────────────────────────────────────────────
MAC_MILD = [
    ('mild_fwd',
     r'(?:μικρ\w*|ηπι\w*|ελαφρ\w*|ελαχιστ\w*|εστιακ\w*)(?:\s+βαθμου)?\s+' + CALC),
    ('mild_rev',
     CALC + r'\s+(?:\w+\s+){0,4}?(?:μικρου|ηπιου|ελαχιστου)\s+βαθμου' + OTHER_FINDING_NOUN),
]

# ── Θετικά χωρίς βαθμό (unqualified) — η λογική των positive patterns του v5,
#    με το ενιαίο CALC στη θέση του ουσιαστικού ─────────────────────────────
MAC_BARE = [
    # v5: επασβέστωση (του) (οπίσθιου) μιτροειδικού δακτυλίου  [+ πρόσθιου]
    ('annulus',            CALC + r'\s+(?:(?:του|των)\s+)?(?:(?:οπισθι|προσθι)\w*\s+)?μιτροειδικ\w*\s+δακτυλ\w*'),
    # v5: επασβέστωση στον οπίσθιο μιτροειδικό δακτύλιο
    ('annulus_sto',        CALC + r'\s+στο[νυ]?\s+(?:\w+\s+){0,2}δακτυλι\w*'),
    # v5: επασβέστωση (της) οπίσθιας/πρόσθιας γλωχίνας
    ('leaflet',            CALC + r'\s+(?:(?:της|των)\s+)?(?:οπισθι|προσθι)\w*\s+γλωχιν\w*'),
    # v5: εμφανίζει επασβέστωση / εμφανίζεται επασβεστωμένη
    ('emfanizei',          r'εμφανιζ\w*\s+' + CALC),
    # v5: επασβεστωμένη/ος οπίσθια/ος, πρόσθια/ος
    ('calc_ant_post',      CALC + r'\s+(?:οπισθι|προσθι)\w*'),
    # v5: επασβέστωση και ακινησία / ακινησία … επασβέστωση
    ('akinisia_1',         CALC + r'\s+και\s+ακινησια'),
    ('akinisia_2',         r'ακινησια\s+(?:\w+\s+){0,3}?' + CALC),
    # v5: μερικώς επασβεστωμένο
    ('merikos',            r'μερικως\s+' + CALC),
    # v5: ασβέστωση (του) (οπίσθιου) μιτροειδικού δακτυλίου
    ('asbestosi_annulus',  r'ασβεσ\w+\s+(?:του\s+)?(?:οπισθιου\s+)?μιτροειδικ\w*\s+δακτυλ\w*'),
    # v5: επασβέστωση (του) (υπο)μιτροειδικής συσκευής / δακτυλίου
    ('apparatus',          CALC + r'\s+(?:(?:του|της)\s+)?(?:υπο)?μιτροειδ\w+\s+(?:συσκευ\w*|δακτυλ\w*)'),
    # v5: ασβεστοποιητική μεταβολή (του) δακτυλίου
    ('asbestopoiitiki',    r'ασβεστοποιητικ\w*\s+μεταβολ\w*\s+(?:του\s+)?δακτυλ\w*'),
    # v5: caseous MAC  (+ ο αγγλικός όρος MAC)
    ('caseous',            r'caseous\s+mitral\s+(?:valve\s+)?calcification'),
    ('english',            r'mitral\s+annul\w*\s+calcif\w*'),
    # v5: επασβεστωμένο μόρφωμα
    ('morfoma',            CALC + r'\s+μορφωμα'),
    # v5: λόγω επασβέστωσης
    ('logo',               r'λογω\s+(?:\w+\s+)?' + CALC),
    # v5 typo pattern (επασσβέστωση + ανατομικό context) — κρατιέται ΜΟΝΟ για το typo
    ('typo_ss',            r'επασσβεσ\w+\s+(?:\w+\s+){0,2}(?:οπισθι|προσθι|μιτροειδ|γλωχιν|δακτυλ)'),
    # Συντομογραφία
    ('mac_abbrev',         r'\bmac\b'),
]

# ΝΕΟ — μόνο για το MV section: «επασβέστωση (του) (οπίσθιου) δακτυλίου»
# χωρίς «μιτροειδικού». Μέσα στην ενότητα της μιτροειδούς ο δακτύλιος είναι ο
# μιτροειδικός. Στα Συμπεράσματα το ίδιο κείμενο είναι αμφίσημο → flag.
MAC_ANNULUS_IMPLICIT = ('annulus_implicit',
                        CALC + r'\s+(?:(?:του|των)\s+)?(?:(?:οπισθι|προσθι)\w*\s+)?δακτυλ\w*')

# Κανόνας εγγύτητας για προτάσεις Συμπερασμάτων με κοινό ουσιαστικό:
# «Επασβέστωση αορτικής βαλβίδας και μιτροειδικού δακτυλίου»
MAC_PROXIMITY = ('ctx_proximity',
                 CALC + r'\s+(?:[\w,]+\s+){0,6}?(?:του\s+)?μιτροειδικ\w*\s+δακτυλ\w*')

GRADE_RANK = {'none': 0, 'unqualified': 1, 'mild': 2, 'borderline': 3, 'moderate_severe': 4}

# Moderate or severe (label_mod_severe). unqualified → 1, borderline → 0 (απόφαση χρήστη).
MOD_SEVERE_GRADES = {'moderate_severe', 'unqualified'}


# =============================================================================
# EVIDENCE HELPERS
# =============================================================================

def _context(text: str, m, before=40, after=30) -> str:
    return text[max(0, m.start() - before): m.end() + after]


def _rec(matches: list, source: str, rule: str, m, text: str, raw: str) -> dict:
    rec = {'source': source, 'rule': rule, 'match': m.group(), 'context': _context(text, m),
           'raw': raw, 'end': m.end(), 'decisive': 0}
    matches.append(rec)
    return rec


def _mask(text: str, start: int, end: int) -> str:
    """Αντικαθιστά [start:end] με '#' ίδιου μήκους (θέσεις μένουν ίδιες,
    και κανένα pattern δεν μπορεί να ταιριάξει μέσα ή διαμέσου του masked τμήματος)."""
    return text[:start] + '#' * (end - start) + text[end:]


# =============================================================================
# GRADING ΕΝΟΣ ΚΕΙΜΕΝΟΥ
# =============================================================================

def grade_text(raw: str, source: str, allow_implicit_annulus: bool,
               proximity_text: str = '') -> dict:
    """
    Βαθμολογεί ένα κείμενο (MV section ή μία πρόταση Συμπερασμάτων).

    Σειρά:
      1. Negation guard   → masking του clause
      2. Borderline       → καταγραφή + masking (ώστε το «μετρίου» μέσα στο
                            «μικρού προς μετρίου» να μη μετρήσει ως severe)
      3. Severe, mild, bare positives στο υπόλοιπο κείμενο
      4. (μόνο Συμπεράσματα) ctx_proximity στην πλήρη πρόταση, αν δεν βρέθηκε τίποτα

    Επιστρέφει dict με label, grade, decisive record, matches και ενδείξεις.
    """
    res = {'label': 0, 'grade': 'none', 'decisive': None, 'matches': [],
           'negated': False, 'has_mild': False, 'has_severe': False,
           'mention': False, 'uncovered': False}
    t = normalize(raw)
    if not t:
        return res
    M = res['matches']

    # ── 1. NEGATION ─────────────────────────────────────────────────────
    for m in list(re.finditer(NEGATION, t)):
        end_m = re.compile(CLAUSE_END).search(t, m.end())
        end = end_m.start() if end_m else len(t)
        _rec(M, source, 'negation_guard', m, t, raw)
        t = _mask(t, m.start(), end)
        res['negated'] = True

    # ── 2. BORDERLINE ───────────────────────────────────────────────────
    found = []   # (grade, record)
    for name, pat in MAC_BORDERLINE:
        for m in list(re.finditer(pat, t)):
            found.append(('borderline', _rec(M, source, name, m, t, raw)))
            t = _mask(t, m.start(), m.end())

    # ── 3. SEVERE / MILD / BARE ─────────────────────────────────────────
    for grade, rules in (('moderate_severe', MAC_SEVERE), ('mild', MAC_MILD)):
        for name, pat in rules:
            m = re.search(pat, t)
            if m:
                found.append((grade, _rec(M, source, name, m, t, raw)))

    bare_rules = list(MAC_BARE) + ([MAC_ANNULUS_IMPLICIT] if allow_implicit_annulus else [])
    for name, pat in bare_rules:
        m = re.search(pat, t)
        if m:
            found.append(('unqualified', _rec(M, source, name, m, t, raw)))
            break   # ένα bare αρκεί ως evidence

    # ── 4. ctx_proximity (μόνο για προτάσεις Συμπερασμάτων) ─────────────
    if not found and proximity_text:
        tp = normalize(proximity_text)
        for m in re.finditer(NEGATION, tp):
            end_m = re.compile(CLAUSE_END).search(tp, m.end())
            tp = _mask(tp, m.start(), end_m.start() if end_m else len(tp))
        m = re.search(MAC_PROXIMITY[1], tp)
        if m:
            found.append(('unqualified', _rec(M, source, MAC_PROXIMITY[0], m, tp, proximity_text)))

    res['has_mild'] = any(g == 'mild' for g, _ in found)
    res['has_severe'] = any(g == 'moderate_severe' for g, _ in found)

    if found:
        grade, rec = max(found, key=lambda x: GRADE_RANK[x[0]])
        res['label'], res['grade'], res['decisive'] = 1, grade, rec
    elif re.search(CALC_ANY, t):
        res['uncovered'] = True

    res['mention'] = bool(M) or res['uncovered']
    return res


# =============================================================================
# ΕΠΙΛΟΓΗ ΠΡΟΤΑΣΕΩΝ ΑΠΟ ΣΥΜΠΕΡΑΣΜΑΤΑ / ΣΧΟΛΙΑ / IMPORTED
# =============================================================================

# Αναφορά στη μιτροειδή. Χωρίς \bav\b / \btv\b (αμφίσημα).
MITRAL_CTX = r'μιτροειδ|\bmitral\b|\bmv\b|\bmac\b'
# Άλλη βαλβίδα. «πνευμονική» μόνο ως βαλβίδα — όχι «πνευμονική υπέρταση».
OTHER_VALVE_CTX = r'αορτικ|αορτ[ηή]|τριγλωχ|πνευμονικ\w*\s+βαλβιδ|\baortic\b|\btricuspid\b'
ANNULUS_CTX = r'δακτυλ'
SENT_SPLIT = r'\.(?!\d)|;|\n'
CLAUSE_SPLIT = r',|·|\sκαι\s|\sκαθ[ωώ]ς\s|/'

FALLBACK_KEYS = ('CONCLUSIONS', 'COMMENTS')
IMPORTED_KEYS = ('IMPORTED',)


def _mitral_clauses(sent: str) -> str:
    """
    Από πρόταση με >1 βαλβίδα κρατά μόνο τα clauses της μιτροειδούς
    (ίδια λογική ανάθεσης με το mitral_valve_v6x.py):
      1. clause που ονομάζει βαλβίδα ανήκει σε αυτήν
      2. clause χωρίς όνομα κληρονομεί το ΠΡΟΗΓΟΥΜΕΝΟ όργανο
      3. αρχικά clauses χωρίς προηγούμενο κληρονομούν το ΕΠΟΜΕΝΟ
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

    return ', '.join(p for p, o in zip(parts, owners) if o == 'MITRAL')


def scan_sentences(sections: dict, keys: tuple) -> list:
    """
    Επιστρέφει λίστα από dicts, ένα ανά πρόταση που αφορά MAC:
      {'key', 'text' (μετά από clause φιλτράρισμα), 'full' (πλήρης πρόταση),
       'flags'}

    Κρατιέται πρόταση που περιέχει όρο επασβέστωσης ΚΑΙ
      (α) αναφορά στη μιτροειδή, ή
      (β) «δακτύλιο» χωρίς καμία βαλβίδα → flag mac_annulus_unspecified.
    Πρόταση μόνο για άλλη βαλβίδα → απορρίπτεται.
    """
    out = []
    for key in keys:
        raw_k = get_sec(sections, key)
        if not raw_k.strip():
            continue
        for sent in re.split(SENT_SPLIT, raw_k):
            sent = sent.strip()
            if not sent:
                continue
            sn = normalize(sent)
            if not re.search(CALC_ANY, sn):
                continue
            has_mitral = bool(re.search(MITRAL_CTX, sn))
            has_other = bool(re.search(OTHER_VALVE_CTX, sn))
            flags = []
            if has_mitral and has_other:
                flags.append('multi_valve_sentence')
                text = _mitral_clauses(sent)
            elif has_mitral:
                text = sent
            elif not has_other and re.search(ANNULUS_CTX, sn):
                flags.append('mac_annulus_unspecified')
                text = sent
            else:
                continue
            out.append({'key': key, 'text': text, 'full': sent, 'flags': flags})
    return out


# Ανατομικά sections (εκτός MV) όπου ελέγχεται αν γράφτηκε MAC «σε λάθος θέση»
ELSEWHERE_EXCLUDE = {'MV', 'CONCLUSIONS', 'COMMENTS', 'IMPORTED'}
ELSEWHERE_PAT = CALC + r'\s+(?:\w+\s+){0,6}?μιτροειδικ\w*\s+δακτυλ\w*|\bmac\b|mitral\s+annul\w*\s+calcif'


# =============================================================================
# CORE: grade_mac
# =============================================================================

def grade_mac(sections: dict) -> dict:
    """
    MAC — ένα label (mild + moderate + severe), union πηγών.

    Επιστρέφει:
      label, label_mod_severe, grade, source, rule, phrase, raw (για original_phrase), flags,
      matches (Evidence), used_text (το κείμενο που αξιολογήθηκε ανά πηγή)
    """
    out = {'label': 0, 'label_mod_severe': 0, 'grade': 'none', 'source': 'none', 'rule': '',
           'phrase': '', 'raw': '', 'flags': [], 'matches': [], 'used_text': ''}
    results = []          # (source_key, result)
    used = []

    # ── 1. MV section ───────────────────────────────────────────────────
    mv_raw = get_sec(sections, 'MV')
    r_mv = None
    if mv_raw.strip():
        r_mv = grade_text(mv_raw, 'MV', allow_implicit_annulus=True)
        results.append(('MV', r_mv))
        used.append(f'[MV] {mv_raw.strip()}')

    # ── 2. Συμπεράσματα / Σχόλια / Διάγνωση (ΠΑΝΤΑ) ──────────────────────
    fb_sents = scan_sentences(sections, FALLBACK_KEYS)

    # ── 3. Imported Findings — μόνο αν ΚΑΜΙΑ αναφορά επασβέστωσης αλλού ──
    mv_mention = bool(r_mv and r_mv['mention'])
    if not mv_mention and not fb_sents:
        imp = scan_sentences(sections, IMPORTED_KEYS)
        if imp:
            fb_sents = imp
            out['flags'].append('imported_findings')

    for s in fb_sents:
        prox = s['full'] if 'multi_valve_sentence' in s['flags'] else ''
        r = grade_text(s['text'], s['key'], allow_implicit_annulus=False, proximity_text=prox)
        results.append((s['key'], r))
        used.append(f"[{s['key']}] {s['text']}")
        for f in s['flags']:
            if f not in out['flags']:
                out['flags'].append(f)

    out['used_text'] = '\n'.join(used)

    # ── Συνένωση ─────────────────────────────────────────────────────────
    for _, r in results:
        out['matches'].extend(r['matches'])

    positives = [(k, r) for k, r in results if r['label'] == 1]
    if positives:
        best_k, best = max(positives, key=lambda kr: GRADE_RANK[kr[1]['grade']])
        best['decisive']['decisive'] = 1
        out['label'] = 1
        out['grade'] = best['grade']
        out['label_mod_severe'] = 1 if best['grade'] in MOD_SEVERE_GRADES else 0
        out['rule'] = best['decisive']['rule']
        out['phrase'] = best['decisive']['match']
        out['raw'] = best['decisive']['raw']
        src_keys = []
        for k, _ in positives:
            if k not in src_keys:
                src_keys.append(k)
        out['source'] = '+'.join(src_keys)

    # ── Flags ────────────────────────────────────────────────────────────
    F = out['flags']
    any_neg = any(r['negated'] for _, r in results)
    fb_positive = any(r['label'] for k, r in results if k != 'MV')
    mv_positive = bool(r_mv and r_mv['label'])

    if any_neg:
        F.append('mac_negated')
        if out['label'] == 1:
            F.append('mac_negated_and_positive')
    if r_mv and r_mv['negated'] and not mv_positive and fb_positive:
        F.append('source_conflict')
    if fb_positive and not mv_positive:
        F.append('conclusions_gain')
    if any(r['has_mild'] for _, r in results) and any(r['has_severe'] for _, r in results):
        F.append('mac_mixed_severity')
    if out['label'] == 0 and any(r['uncovered'] for _, r in results):
        F.append('mac_uncovered')
    if out['label'] == 0:
        for key, text in sections.items():
            if key in ELSEWHERE_EXCLUDE or not text.strip():
                continue
            if re.search(ELSEWHERE_PAT, normalize(text)):
                F.append('mac_mentioned_elsewhere')
                break

    # mac_annulus_unspecified μένει μόνο αν το label προήλθε / σχετίζεται με τέτοια πρόταση
    # (κρατιέται πάντα — είναι για έλεγχο της πηγής)
    return out


def get_mitral_annular_calcification_incl_mild(sections: dict) -> int:
    """Drop-in wrapper — ίδιο signature με τις v5 συναρτήσεις."""
    return grade_mac(sections)['label']


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
# ΑΝΑΓΝΩΣΗ REPORTS (HTML ή CHM)  (αυτούσιο από mitral_valve_v6x.py)
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

FLAG_FILL = PatternFill('solid', fgColor='FFC000')

REVIEW_FLAGS = {'multi_valve_sentence', 'mac_negated_and_positive', 'source_conflict',
                'mac_annulus_unspecified', 'mac_uncovered', 'mac_mentioned_elsewhere'}

LABEL_COL = 'mitral_annular_calcification_incl_mild'
LABEL_COL_MOD = 'mitral_annular_calcification'          # moderate or severe (strict)


def write_excel(path: Path, label_rows: list, evidence_rows: list):
    wb = Workbook()
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='305496')
    pos_font    = Font(bold=True, color='C00000')

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
    cols1 = ['exam_id', 'source', LABEL_COL, LABEL_COL_MOD, 'mac_grade', 'mac_rule', 'mac_phrase',
             'flags', 'status', 'mac_text', 'mv_text', 'conclusions_text',
             'comments_text', 'imported_text', 'report_path']
    fill_sheet(ws1, cols1, label_rows,
               [18, 22, 22, 22, 18, 20, 40, 40, 14, 70, 70, 60, 60, 60, 60],
               wrap_cols=('mac_text', 'mv_text', 'conclusions_text',
                          'comments_text', 'imported_text'))
    i_flag = cols1.index('flags')
    i_lab = cols1.index(LABEL_COL)
    for row in ws1.iter_rows(min_row=2):
        flags = row[i_flag].value or ''
        if any(f in REVIEW_FLAGS for f in flags.split(';') if f):
            for c in row:
                c.fill = FLAG_FILL
        if row[i_lab].value == 1:
            row[i_lab].font = pos_font

    ws2 = wb.create_sheet('Evidence')
    cols2 = ['exam_id', 'source', 'rule', 'matched_phrase', 'decisive', 'context']
    fill_sheet(ws2, cols2, evidence_rows, [18, 14, 22, 46, 10, 80], wrap_cols=('context',))

    wb.save(path)


# =============================================================================
# SELF-TEST
# =============================================================================

def MV(text: str) -> dict:
    return {'MV': text} if text else {}


# (sections, label, grade, source, required_flags, forbidden_flags)
SELF_TESTS = [
    # ── MV: unqualified (v5 positives) ───────────────────────────────────
    (MV('Επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση του μιτροειδικού δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση στον οπίσθιο μιτροειδικό δακτύλιο.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση της οπίσθιας γλωχίνας.'), 1, 'unqualified', 'MV', [], []),
    (MV('Εμφανίζει επασβέστωση.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβεστωμένη οπίσθια γλωχίνα με περιορισμένη κινητικότητα.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση και ακινησία της οπίσθιας γλωχίνας.'), 1, 'unqualified', 'MV', [], []),
    (MV('Ασβεστοποιητική μεταβολή του δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    (MV('Caseous mitral calcification.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβεστωμένο μόρφωμα στον οπίσθιο δακτύλιο.'), 1, 'unqualified', 'MV', [], []),
    (MV('Περιορισμός διάνοιξης λόγω επασβέστωσης.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασσβέστωση οπίσθιου δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση υπομιτροειδικής συσκευής.'), 1, 'unqualified', 'MV', [], []),
    # Νέο: δακτύλιος χωρίς «μιτροειδικού» μέσα στο MV section
    (MV('Επασβέστωση οπίσθιου δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    # Νέο: πληθυντικός
    (MV('Επασβεστώσεις του μιτροειδικού δακτυλίου.'), 1, 'unqualified', 'MV', [], []),
    (MV('MAC.'), 1, 'unqualified', 'MV', [], []),

    # ── MV: mild ─────────────────────────────────────────────────────────
    (MV('Μικρού βαθμού επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'), 1, 'mild', 'MV', [], []),
    (MV('Ήπια επασβέστωση του δακτυλίου.'), 1, 'mild', 'MV', [], []),
    (MV('Ήπιας επασβέστωσης δακτύλιος.'), 1, 'mild', 'MV', [], []),
    (MV('Μικρή επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'), 1, 'mild', 'MV', [], []),
    (MV('Ελαφρά επασβέστωση δακτυλίου.'), 1, 'mild', 'MV', [], []),
    (MV('Ελαφριά επασβέστωση.'), 1, 'mild', 'MV', [], []),
    (MV('Ήπιου βαθμού επασβέστωση.'), 1, 'mild', 'MV', [], []),
    (MV('Μικρές εστιακές επασβεστώσεις στον δακτύλιο.'), 1, 'mild', 'MV', [], []),
    (MV('Επασβέστωση οπίσθιου μιτροειδικού δακτυλίου μικρού βαθμού.'), 1, 'mild', 'MV', [], []),
    # Γλωχίνες: ό,τι πιάνει το mild χωρίς ανατομία → 1 (απόφαση: καμία ειδική λογική)
    (MV('Ήπια επασβέστωση των γλωχίνων.'), 1, 'mild', 'MV', [], []),

    # ── MV: borderline ───────────────────────────────────────────────────
    (MV('Μικρού προς μετρίου βαθμού επασβέστωση δακτυλίου.'), 1, 'borderline', 'MV', [], ['mac_mixed_severity']),
    (MV('Ήπια έως μέτρια επασβέστωση οπίσθιου δακτυλίου.'), 1, 'borderline', 'MV', [], []),
    (MV('Ήπια/μέτρια επασβέστωση.'), 1, 'borderline', 'MV', [], []),

    # ── MV: moderate / severe ────────────────────────────────────────────
    (MV('Μετρίου βαθμού επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'), 1, 'moderate_severe', 'MV', [], []),
    (MV('Σοβαρή επασβέστωση του μιτροειδικού δακτυλίου.'), 1, 'moderate_severe', 'MV', [], []),
    (MV('Σημαντική επασβέστωση.'), 1, 'moderate_severe', 'MV', [], []),
    (MV('Σημαντικά επασβεστωμένη οπίσθια γλωχίνα.'), 1, 'moderate_severe', 'MV', [], []),
    (MV('Εκτεταμένη επασβέστωση του δακτυλίου.'), 1, 'moderate_severe', 'MV', [], []),
    (MV('Επασβέστωση δακτυλίου σοβαρού βαθμού.'), 1, 'moderate_severe', 'MV', [], []),
    # Μικτό: ήπια γλωχίνες + σοβαρός δακτύλιος → υψηλότερος βαθμός
    (MV('Ήπια επασβέστωση γλωχίνων. Σοβαρή επασβέστωση οπίσθιου δακτυλίου.'),
     1, 'moderate_severe', 'MV', ['mac_mixed_severity'], []),

    # ── Ο βαθμός άλλου finding ΔΕΝ χρεώνεται στην επασβέστωση ────────────
    (MV('Επασβέστωση οπίσθιου δακτυλίου, μετρίου βαθμού ανεπάρκεια.'), 1, 'unqualified', 'MV', [], []),
    (MV('Επασβέστωση οπίσθιου δακτυλίου, μικρού βαθμού ανεπάρκεια.'), 1, 'unqualified', 'MV', [], []),
    # Μέτρια ανεπάρκεια, χωρίς επασβέστωση → 0
    (MV('Μέτρια ανεπάρκεια μιτροειδούς.'), 0, 'none', 'none', [], ['mac_uncovered']),

    # ── MV: άρνηση ───────────────────────────────────────────────────────
    (MV('Χωρίς επασβέστωση του μιτροειδικού δακτυλίου.'), 0, 'none', 'none', ['mac_negated'], ['mac_uncovered']),
    (MV('Δεν παρατηρείται επασβέστωση του δακτυλίου.'), 0, 'none', 'none', ['mac_negated'], []),
    (MV('Χωρίς στένωση ή επασβέστωση.'), 0, 'none', 'none', ['mac_negated'], []),
    (MV('Απουσία επασβεστώσεων.'), 0, 'none', 'none', ['mac_negated'], []),
    # Η άρνηση σταματά στο κόμμα
    (MV('Χωρίς στένωση, επασβέστωση οπίσθιου δακτυλίου.'), 1, 'unqualified', 'MV', [], ['mac_negated']),
    # Άρνηση σε άλλο clause δεν μηδενίζει το θετικό
    (MV('Επασβέστωση οπίσθιου μιτροειδικού δακτυλίου, χωρίς επασβέστωση γλωχίνων.'),
     1, 'unqualified', 'MV', ['mac_negated', 'mac_negated_and_positive'], []),

    # ── MV: uncovered ────────────────────────────────────────────────────
    (MV('Επασβέστωση.'), 0, 'none', 'none', ['mac_uncovered'], []),
    (MV('Επασβέστωση γλωχίνων.'), 0, 'none', 'none', ['mac_uncovered'], []),
    (MV('Καλή σύγκλειση των γλωχίνων.'), 0, 'none', 'none', [], ['mac_uncovered']),
    (MV(''), 0, 'none', 'none', [], []),

    # ── MAC σε άλλο section ──────────────────────────────────────────────
    ({'MV': 'Καλή σύγκλειση.', 'AV': 'Επασβέστωση αορτικής βαλβίδας και μιτροειδικού δακτυλίου.'},
     0, 'none', 'none', ['mac_mentioned_elsewhere'], []),
]

SELF_TESTS_FALLBACK = [
    # Μόνο στα Συμπεράσματα
    ({'CONCLUSIONS': 'Επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'unqualified', 'CONCLUSIONS', ['conclusions_gain'], []),
    # Μόνο στη Διάγνωση (→ COMMENTS)
    ({'COMMENTS': 'Διάγνωση: Ήπια επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'mild', 'COMMENTS', ['conclusions_gain'], []),
    # UNION: MV υπάρχει χωρίς επασβέστωση, Συμπεράσματα θετικά
    ({'MV': 'Μέτρια ανεπάρκεια.', 'CONCLUSIONS': 'Σοβαρή επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'moderate_severe', 'CONCLUSIONS', ['conclusions_gain'], []),
    # UNION: και τα δύο θετικά → υψηλότερος βαθμός, source και τα δύο
    ({'MV': 'Ήπια επασβέστωση δακτυλίου.', 'CONCLUSIONS': 'Σοβαρή επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'moderate_severe', 'MV+CONCLUSIONS', ['mac_mixed_severity'], ['conclusions_gain']),
    # Άλλη βαλβίδα μόνο → αγνοείται
    ({'CONCLUSIONS': 'Επασβέστωση αορτικής βαλβίδας.'}, 0, 'none', 'none', [], []),
    # Επασβέστωση χωρίς όργανο → αγνοείται
    ({'CONCLUSIONS': 'Σοβαρή επασβέστωση.'}, 0, 'none', 'none', [], []),
    # Multi-valve με ΚΟΙΝΟ ουσιαστικό → ctx_proximity
    ({'CONCLUSIONS': 'Επασβέστωση αορτικής βαλβίδας και μιτροειδικού δακτυλίου.'},
     1, 'unqualified', 'CONCLUSIONS', ['multi_valve_sentence'], []),
    # Multi-valve, μιτροειδής πρώτη
    ({'CONCLUSIONS': 'Επασβέστωση μιτροειδικού δακτυλίου και σοβαρή στένωση αορτικής.'},
     1, 'unqualified', 'CONCLUSIONS', ['multi_valve_sentence'], []),
    # Multi-valve, μιτροειδής δεύτερη — ο βαθμός της αορτικής δεν περνά
    ({'CONCLUSIONS': 'Σοβαρή επασβέστωση αορτικής βαλβίδας, ήπια επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'mild', 'CONCLUSIONS', ['multi_valve_sentence'], []),
    # «πνευμονική υπέρταση» ΔΕΝ είναι άλλη βαλβίδα
    ({'CONCLUSIONS': 'Επασβέστωση μιτροειδικού δακτυλίου, πνευμονική υπέρταση.'},
     1, 'unqualified', 'CONCLUSIONS', [], ['multi_valve_sentence']),
    # Δακτύλιος χωρίς βαλβίδα στα Συμπεράσματα → flag, όχι annulus_implicit
    ({'CONCLUSIONS': 'Ήπια επασβέστωση δακτυλίου.'},
     1, 'mild', 'CONCLUSIONS', ['mac_annulus_unspecified'], []),
    ({'CONCLUSIONS': 'Επασβέστωση δακτυλίου.'},
     0, 'none', 'none', ['mac_annulus_unspecified', 'mac_uncovered'], []),
    # Συντομογραφία MAC στα Σχόλια
    ({'COMMENTS': 'Σχόλια: MAC.'}, 1, 'unqualified', 'COMMENTS', [], []),
    # Επιλογή μίας πρότασης από πολλές
    ({'CONCLUSIONS': 'Φυσιολογική αορτική βαλβίδα. Μικρή επασβέστωση μιτροειδικού δακτυλίου. '
                     'Καλή συστολική λειτουργία.'},
     1, 'mild', 'CONCLUSIONS', [], []),
    # Άρνηση στα Συμπεράσματα
    ({'CONCLUSIONS': 'Χωρίς επασβέστωση μιτροειδικού δακτυλίου.'},
     0, 'none', 'none', ['mac_negated'], []),
    # Σύγκρουση: MV αρνητικό, Συμπεράσματα θετικά
    ({'MV': 'Χωρίς επασβέστωση δακτυλίου.', 'CONCLUSIONS': 'Επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'unqualified', 'CONCLUSIONS', ['source_conflict', 'mac_negated_and_positive'], []),
    # ── IMPORTED ─────────────────────────────────────────────────────────
    ({'IMPORTED': 'Μέτρια επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'moderate_severe', 'IMPORTED', ['imported_findings'], []),
    # MV χωρίς αναφορά επασβέστωσης → IMPORTED εξετάζεται
    ({'MV': 'Καλή σύγκλειση.', 'IMPORTED': 'Επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'unqualified', 'IMPORTED', ['imported_findings'], []),
    # MV ΑΝΑΦΕΡΕΙ επασβέστωση (άρνηση) → IMPORTED ΔΕΝ εξετάζεται
    ({'MV': 'Χωρίς επασβέστωση.', 'IMPORTED': 'Επασβέστωση μιτροειδικού δακτυλίου.'},
     0, 'none', 'none', ['mac_negated'], ['imported_findings']),
    # Συμπεράσματα με αναφορά → IMPORTED ΔΕΝ εξετάζεται
    ({'CONCLUSIONS': 'Ήπια επασβέστωση μιτροειδικού δακτυλίου.',
      'IMPORTED': 'Σοβαρή επασβέστωση μιτροειδικού δακτυλίου.'},
     1, 'mild', 'CONCLUSIONS', [], ['imported_findings']),
    # Τίποτα πουθενά
    ({'CONCLUSIONS': 'Τυπική μελέτη.'}, 0, 'none', 'none', [], []),
]


# Moderate or severe: (sections, label incl_mild, label_mod_severe, grade)
SELF_TESTS_MOD = [
    (MV('Επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'),               1, 1, 'unqualified'),
    (MV('MAC.'),                                                        1, 1, 'unqualified'),
    (MV('Μικρού βαθμού επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'),  1, 0, 'mild'),
    (MV('Ήπια επασβέστωση του δακτυλίου.'),                             1, 0, 'mild'),
    (MV('Μικρού προς μετρίου βαθμού επασβέστωση δακτυλίου.'),          1, 0, 'borderline'),
    (MV('Μετρίου βαθμού επασβέστωση οπίσθιου μιτροειδικού δακτυλίου.'), 1, 1, 'moderate_severe'),
    (MV('Σοβαρή επασβέστωση του μιτροειδικού δακτυλίου.'),             1, 1, 'moderate_severe'),
    (MV('Σημαντικά επασβεστωμένη οπίσθια γλωχίνα.'),                    1, 1, 'moderate_severe'),
    (MV('Χωρίς επασβέστωση του μιτροειδικού δακτυλίου.'),              0, 0, 'none'),
    (MV('Επασβέστωση.'),                                                0, 0, 'none'),
    # Ο δηλωμένος βαθμός σε άλλη πηγή υπερισχύει του unqualified
    ({'MV': 'Επασβέστωση οπίσθιου δακτυλίου.',
      'CONCLUSIONS': 'Ήπια επασβέστωση μιτροειδικού δακτυλίου.'},       1, 0, 'mild'),
    ({'MV': 'Ήπια επασβέστωση δακτυλίου.',
      'CONCLUSIONS': 'Σοβαρή επασβέστωση μιτροειδικού δακτυλίου.'},     1, 1, 'moderate_severe'),
    ({'CONCLUSIONS': 'Επασβέστωση αορτικής βαλβίδας και μιτροειδικού δακτυλίου.'},
                                                                        1, 1, 'unqualified'),
]


def run_self_test() -> bool:
    ok_all = True
    n_pass = 0
    for secs, e_lab, e_mod, e_grade in SELF_TESTS_MOD:
        r = grade_mac(secs)
        ok = (r['label'] == e_lab and r['label_mod_severe'] == e_mod and r['grade'] == e_grade
              and r['label_mod_severe'] <= r['label'])
        ok_all &= ok
        if not ok:
            desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
            logger.info(f"  [FAIL ] (mod_severe) {desc}\n"
                        f"          → {r['label']}/{r['label_mod_severe']} ({r['grade']})\n"
                        f"          αναμενόταν {e_lab}/{e_mod} ({e_grade})")
    logger.info(f"SELF-TEST mod_severe: {'ΟΚ' if ok_all else 'ΑΠΕΤΥΧΕ'} ({len(SELF_TESTS_MOD)} cases)")
    cases = SELF_TESTS + SELF_TESTS_FALLBACK
    logger.info("SELF-TEST")
    for secs, e_lab, e_grade, e_src, req, forb in cases:
        r = grade_mac(secs)
        missing = [f for f in req if f not in r['flags']]
        present = [f for f in forb if f in r['flags']]
        ok = (r['label'] == e_lab and r['grade'] == e_grade and r['source'] == e_src
              and not missing and not present)
        ok_all &= ok
        n_pass += ok
        if not ok:
            desc = ' + '.join(f"{k}:'{v}'" for k, v in secs.items()) or '<κενό>'
            logger.info(
                f"  [FAIL ] {desc}\n"
                f"          → {r['label']} ({r['grade']}) [{r['source']}] rule={r['rule']} "
                f"flags={';'.join(r['flags'])}\n"
                f"          αναμενόταν {e_lab} ({e_grade}) [{e_src}]"
                f"{'  λείπουν=' + str(missing) if missing else ''}"
                f"{'  δεν έπρεπε=' + str(present) if present else ''}")
    logger.info(f"SELF-TEST: {n_pass}/{len(cases)} PASS — {'ΟΚ' if ok_all else 'ΑΠΕΤΥΧΕ'}")
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
        r = grade_mac(sections)

        label_rows.append({
            'exam_id':          e['exam_id'],
            'source':           r['source'],
            LABEL_COL:          r['label'],
            LABEL_COL_MOD:      r['label_mod_severe'],
            'mac_grade':        r['grade'],
            'mac_rule':         r['rule'],
            'mac_phrase':       original_phrase(r['raw'], r['phrase']),
            'flags':            ';'.join(r['flags']),
            'status':           'ok' if get_sec(sections, 'MV').strip() else 'no_mv_section',
            'mac_text':         r['used_text'],
            'mv_text':          get_sec(sections, 'MV'),
            'conclusions_text': get_sec(sections, 'CONCLUSIONS'),
            'comments_text':    get_sec(sections, 'COMMENTS'),
            'imported_text':    get_sec(sections, 'IMPORTED'),
            'report_path':      e['report_path'],
        })

        for m in r['matches']:
            evidence_rows.append({
                'exam_id':        e['exam_id'],
                'source':         m['source'],
                'rule':           m['rule'],
                'matched_phrase': original_phrase(m['raw'], m['match']),
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

    # ── Στατιστικά ──────────────────────────────────────────────────────────
    ok_rows = [r for r in label_rows if r.get('status') != 'read_failed']
    logger.info("=" * 60)
    logger.info(f"Εξετάσεις: {len(label_rows)} | αναγνώστηκαν: {len(ok_rows)} | "
                f"αποτυχίες: {len(label_rows) - len(ok_rows)}")
    if not ok_rows:
        return

    n = len(ok_rows)
    pos_n = sum(r[LABEL_COL] == 1 for r in ok_rows)
    logger.info(f"\n{LABEL_COL}: {pos_n}/{n} ({100 * pos_n / n:.1f}%)")
    mod_n = sum(r[LABEL_COL_MOD] == 1 for r in ok_rows)
    logger.info(f"{LABEL_COL_MOD} (moderate or severe): {mod_n}/{n} ({100 * mod_n / n:.1f}%)")

    for title, key in (('mac_grade', 'mac_grade'), ('source', 'source'), ('status', 'status')):
        dist = {}
        for r in ok_rows:
            dist[r[key]] = dist.get(r[key], 0) + 1
        logger.info(f"\nΚατανομή {title}:")
        for g, c in sorted(dist.items(), key=lambda x: -x[1]):
            logger.info(f"  {g:<28} {c:>6} ({100 * c / n:.1f}%)")

    flag_counts = {}
    for r in ok_rows:
        for f in filter(None, r['flags'].split(';')):
            flag_counts[f] = flag_counts.get(f, 0) + 1
    if flag_counts:
        logger.info("\nFlags:")
        for f, c in sorted(flag_counts.items(), key=lambda x: -x[1]):
            mark = '  ← ΕΛΕΓΧΟΣ' if f in REVIEW_FLAGS else ''
            logger.info(f"  {f:<28} {c:>6}{mark}")

    logger.info(f"\nExcel: {out}")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_XLSX         = r"outputs/ground_truth/per_finding/mac_labels.xlsx"
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    RUN_SELF_TEST       = True

    if RUN_SELF_TEST:
        run_self_test()
    run(DATASET_DIR, OUTPUT_XLSX, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, MAX_FILES)
