r"""
run_ground_truth.py
===================
Ενιαίο τρέξιμο ground truth για ΟΛΑ τα binary findings, με ΟΛΕΣ τις εκδοχές τους.

ΑΡΧΙΤΕΚΤΟΝΙΚΗ
  Το script ΔΕΝ περιέχει κανένα regex. Φορτώνει τα επικυρωμένα scripts ως
  modules (από τον ίδιο φάκελο) και καλεί τις grade_* συναρτήσεις τους:

    Βάση (findings χωρίς νέα έκδοση)  →  ground_truth_extractor_full_dataset_v5.py
    pacemaker                          →  pacemaker_v6x.py
    rv_systolic_function_depressed     →  rv_systolic_v6x.py
    mitral stenosis / regurgitation    →  mitral_valve_v6x.py
    mitral annular calcification       →  mitral_annular_calcification_v6x.py
                                          (strict = moderate/severe + incl_mild)
    tavr                               →  tavr_v6x.py
    aortic stenosis / regurgitation    →  aortic_valve_v6x.py
    tricuspid regurgitation            →  tricuspid_valve_v6x.py
    pericardial effusion               →  pericardial_effusion_v6x.py
                                          (strict = mod_severe + any_size)

  Κάθε finding βλέπει ΑΚΡΙΒΩΣ τα sections που θα έβλεπε στο δικό του script:
  ο κώδικας parse_sections() είναι ίδιος σε όλα, αλλά τα SECTION_KEYS διαφέρουν
  (v5 / +IMPORTED / +IMPORTED+REFERRAL+RHYTHM). Γι' αυτό κάθε report γίνεται
  parse μία φορά ανά διαφορετικό SECTION_KEYS (3 φορές), με το parser του
  αντίστοιχου module.

  Αλλαγή σε regex γίνεται ΜΟΝΟ στο script του finding. Εδώ δεν αλλάζει τίποτα.

ΑΝΑΓΝΩΣΗ REPORTS
  Ίδια με τα v6x scripts (find_report_files / read_report / exclusion list).
  Τα CHM εξάγονται παράλληλα (threads) και το HTML αποθηκεύεται σε cache·
  στο επόμενο τρέξιμο δεν ξανατρέχει το 7-Zip.

OUTPUT (στο OUTPUT_DIR)
  ground_truth_labels.csv   wide: μία γραμμή ανά εξέταση, μία στήλη ανά εκδοχή
                            (κενό = δεν υπολογίστηκε, π.χ. read_failed)
  ground_truth_long.csv     long: εξέταση × εκδοχή, με grade, πηγή, κανόνα,
                            φράση και flags — για evaluation ανά (finding, variant)
  ground_truth_summary.csv  θετικά / prevalence ανά στήλη
  manifest.json             ρυθμίσεις, εκδοχές, hash κάθε script, self-tests

Εκτέλεση: F5. Ρυθμίσεις στο block MAIN στο τέλος.
Εξαρτήσεις: ίδιες με τα επιμέρους scripts (beautifulsoup4, openpyxl, 7-Zip).
"""

import csv
import json
import sys
import time
import hashlib
import logging
import traceback
import importlib.util
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("run_gt")


# =============================================================================
# MODULES
# =============================================================================

MODULE_FILES = {
    'v5':        'ground_truth_extractor_full_dataset_v5.py',
    'pacemaker': 'pacemaker_v6x.py',
    'rv_sys':    'rv_systolic_v6x.py',
    'mitral':    'mitral_valve_v6x.py',
    'mac':       'mitral_annular_calcification_v6x.py',
    'tavr':      'tavr_v6x.py',
    'aortic':    'aortic_valve_v6x.py',
    'tricuspid': 'tricuspid_valve_v6x.py',
    'pericard':  'pericardial_effusion_v6x.py',
}

M = {}   # key → module


def load_modules(scripts_dir: Path) -> dict:
    hashes = {}
    for key, fname in MODULE_FILES.items():
        path = scripts_dir / fname
        if not path.is_file():
            raise FileNotFoundError(f"Δεν βρέθηκε το script: {path}")
        name = f"gt_{key}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        M[key] = mod
        hashes[fname] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return hashes


# =============================================================================
# CONTEXT ΑΝΑ ΕΞΕΤΑΣΗ — parse μία φορά ανά διαφορετικό SECTION_KEYS
# =============================================================================

class ExamContext:
    def __init__(self, html: str):
        self.html = html
        self._cache = {}

    def sections(self, mod) -> dict:
        k = repr(mod.SECTION_KEYS)
        if k not in self._cache:
            self._cache[k] = mod.parse_sections(self.html)
        return self._cache[k]


def _row(finding, variant, column, label, grade='', source='', rule='', phrase='', flags=()):
    return {'finding': finding, 'variant': variant, 'column': column,
            'label': label, 'grade': grade, 'source': source, 'rule': rule,
            'phrase': phrase, 'flags': ';'.join(f for f in flags if f)}


def _phrase(mod, raw, match):
    try:
        return mod.original_phrase(raw or '', match or '')
    except Exception:
        return match or ''


# =============================================================================
# ADAPTERS — ένας ανά script, μετατρέπουν το output σε κοινές γραμμές
# =============================================================================

def ad_v5(func_name, finding, column):
    def adapter(ctx):
        m = M['v5']
        lab = getattr(m, func_name)(ctx.sections(m))
        return [_row(finding, 'v5', column, lab)]
    return adapter


def ad_pacemaker(ctx):
    m = M['pacemaker']
    r = m.grade_pacemaker(ctx.sections(m))
    flags = list(r['flags'])
    if not r['mentions']:
        import re
        full = m.normalize(m.html_plain_text(ctx.html))
        if any(re.search(p, full) for _, p in m.DEVICE_GROUPS):
            flags.append('pacemaker_outside_sections')
    return [
        _row('pacemaker', 'strict', 'pacemaker', r['label_strict'], r['device_type'],
             r['source_sections'], r['rule_strict'], r['phrase_strict'], flags),
        _row('pacemaker', 'incl_icd', 'pacemaker_incl_icd', r['label_incl'], r['device_type'],
             r['source_sections'], r['rule_incl'], r['phrase_incl'], flags),
    ]


def ad_rv_systolic(ctx):
    m = M['rv_sys']
    s = ctx.sections(m)
    rows = []
    for variant, column, mild in (('strict', 'rv_systolic_function_depressed', False),
                                  ('incl_mild', 'rv_systolic_function_depressed_incl_mild', True)):
        r = m.grade_rv_systolic_v6x(s, mild_positive=mild, borderline_positive=False)
        rows.append(_row('rv_systolic_function_depressed', variant, column, r['label'],
                         r['grade'], r['source'], r['rule'],
                         _phrase(m, r['evidence'], r['match'])))
    return rows


def _dual(mod, finding, column, res, extra_flags):
    flags = list(extra_flags) + list(res['flags'])
    if res['label_incl'] < res['label_strict']:
        flags.append('non_monotonic')
    return [
        _row(finding, 'strict', column, res['label_strict'], res['grade'], res['source'],
             res['rule_strict'], _phrase(mod, res['raw_strict'], res['phrase_strict']), flags),
        _row(finding, 'incl_mild', column + '_incl_mild', res['label_incl'], res['grade'],
             res['source'], res['rule_incl'], _phrase(mod, res['raw_incl'], res['phrase_incl']), flags),
    ]


def ad_mitral(ctx):
    m = M['mitral']
    s = ctx.sections(m)
    rv = m.resolve_mitral_text(s)
    return (_dual(m, 'mitral_stenosis', 'mitral_stenosis', m.grade_mitral_stenosis(s, rv), rv['flags'])
            + _dual(m, 'mitral_regurgitation', 'mitral_regurgitation',
                    m.grade_mitral_regurgitation(s, rv), rv['flags']))


def ad_aortic(ctx):
    m = M['aortic']
    s = ctx.sections(m)
    rv = m.resolve_aortic_text(s)
    return (_dual(m, 'aortic_stenosis', 'aortic_stenosis', m.grade_aortic_stenosis(s, rv), rv['flags'])
            + _dual(m, 'aortic_regurgitation', 'aortic_regurgitation',
                    m.grade_aortic_regurgitation(s, rv), rv['flags']))


def ad_tricuspid(ctx):
    m = M['tricuspid']
    s = ctx.sections(m)
    rv = m.resolve_tricuspid_text(s)
    return _dual(m, 'tricuspid_valve_regurgitation', 'tricuspid_valve_regurgitation',
                 m.grade_tricuspid_regurgitation(s, rv), rv['flags'])


def _mod_flags(flags, mod, broad):
    flags = list(flags)
    if mod > broad:
        flags.append('non_monotonic')
    return flags


def ad_mac(ctx):
    m = M['mac']
    r = m.grade_mac(ctx.sections(m))
    phrase = _phrase(m, r['raw'], r['phrase'])
    flags = _mod_flags(r['flags'], r['label_mod_severe'], r['label'])
    return [
        _row('mitral_annular_calcification', 'strict', 'mitral_annular_calcification',
             r['label_mod_severe'], r['grade'], r['source'], r['rule'], phrase, flags),
        _row('mitral_annular_calcification', 'incl_mild', 'mitral_annular_calcification_incl_mild',
             r['label'], r['grade'], r['source'], r['rule'], phrase, flags),
    ]


def ad_tavr(ctx):
    m = M['tavr']
    r = m.grade_tavr(ctx.sections(m))
    flags = [f for f in r['flags'].split(';') if f]
    return [
        _row('tavr', 'incl_mech', 'tavr_incl_mech', r['label_A'],
             'prosthetic' if r['label_A'] else 'none', r['sources_A'], r['rule_A'],
             _phrase(m, r['raw_A'], r['match_A']), flags),
        _row('tavr', 'excl_mech', 'tavr_excl_mech', r['label_B'], r['grade_B'], r['source_B'],
             r['rule_B'], _phrase(m, r['raw_B'], r['match_B']), flags),
    ]


def ad_pericardial(ctx):
    m = M['pericard']
    r = m.grade_pericardial_effusion(ctx.sections(m))
    phrase = _phrase(m, r['raw'], r['match'])
    flags = _mod_flags([f for f in r['flags'].split(';') if f], r['label_mod_severe'], r['label'])
    return [
        _row('pericardial_effusion', 'strict', 'pericardial_effusion_mod_severe',
             r['label_mod_severe'], r['grade'], r['decisive_source'], r['rule'], phrase, flags),
        _row('pericardial_effusion', 'any_size', 'pericardial_effusion', r['label'],
             r['grade'], r['decisive_source'], r['rule'], phrase, flags),
    ]


# =============================================================================
# REGISTRY — finding → εκδοχές (στήλες) → adapter
# Σειρά = σειρά στηλών στο wide CSV (ίδια με BINARY_FEATURES του v5).
# Για νέα εκδοχή: προσθήκη στο script του finding + μία γραμμή εδώ.
# =============================================================================

REGISTRY = [
    # (finding, [(variant, column, ορισμός)], adapter, script)
    ('pacemaker',
     [('strict',   'pacemaker',          'Βηματοδότης'),
      ('incl_icd', 'pacemaker_incl_icd', 'Βηματοδότης ή απινιδωτής ή καλώδιο')],
     ad_pacemaker, 'pacemaker'),
    ('rv_systolic_function_depressed',
     [('strict',    'rv_systolic_function_depressed',           'Μέτρια/σοβαρή (= v5)'),
      ('incl_mild', 'rv_systolic_function_depressed_incl_mild', 'Ήπια/μέτρια/σοβαρή· οριακή = 0')],
     ad_rv_systolic, 'rv_sys'),
    ('right_ventricle_dilation',
     [('v5', 'right_ventricle_dilation', 'v5 αυτούσιο')],
     ad_v5('get_rv_dilation', 'right_ventricle_dilation', 'right_ventricle_dilation'), 'v5'),
    ('right_atrium_dilation',
     [('v5', 'right_atrium_dilation', 'v5 αυτούσιο')],
     ad_v5('get_ra_dilation', 'right_atrium_dilation', 'right_atrium_dilation'), 'v5'),
    ('left_atrium_dilation',
     [('v5', 'left_atrium_dilation', 'v5 αυτούσιο')],
     ad_v5('get_la_dilation', 'left_atrium_dilation', 'left_atrium_dilation'), 'v5'),
    ('mitraclip',
     [('v5', 'mitraclip', 'v5 αυτούσιο')],
     ad_v5('get_mitraclip', 'mitraclip', 'mitraclip'), 'v5'),
    ('mitral_annular_calcification',
     [('strict',    'mitral_annular_calcification',
       'Μέτρια/σοβαρή ή χωρίς δηλωμένο βαθμό σε καμία πηγή· ήπια/οριακή = 0'),
      ('incl_mild', 'mitral_annular_calcification_incl_mild', 'Ήπια/μέτρια/σοβαρή/χωρίς βαθμό')],
     ad_mac, 'mac'),
    ('mitral_stenosis + mitral_regurgitation',
     [('strict',    'mitral_stenosis',                'Μέτρια/σοβαρή (= v5 όταν υπάρχει MV)'),
      ('incl_mild', 'mitral_stenosis_incl_mild',      'Ήπια/μέτρια/σοβαρή'),
      ('strict',    'mitral_regurgitation',           'Μέτρια/σοβαρή (= v5 όταν υπάρχει MV)'),
      ('incl_mild', 'mitral_regurgitation_incl_mild', 'Ήπια/μέτρια/σοβαρή· ίχνος = 0')],
     ad_mitral, 'mitral'),
    ('tavr',
     [('incl_mech', 'tavr_incl_mech', 'Κάθε προσθετική (v5 patterns + Συμπεράσματα/Σχόλια)'),
      ('excl_mech', 'tavr_excl_mech', 'Βιοπροσθετική/TAVR· μηχανική = 0')],
     ad_tavr, 'tavr'),
    ('bicuspid_aov',
     [('v5', 'bicuspid_aov', 'v5 αυτούσιο')],
     ad_v5('get_bicuspid_aov', 'bicuspid_aov', 'bicuspid_aov'), 'v5'),
    ('aortic_stenosis + aortic_regurgitation',
     [('strict',    'aortic_stenosis',                'Μέτρια/σοβαρή (= v5 όταν υπάρχει AV)'),
      ('incl_mild', 'aortic_stenosis_incl_mild',      'Ήπια/μέτρια/σοβαρή'),
      ('strict',    'aortic_regurgitation',           'Μέτρια/σοβαρή (= v5 όταν υπάρχει AV)'),
      ('incl_mild', 'aortic_regurgitation_incl_mild', 'Ήπια/μέτρια/σοβαρή· ίχνος = 0')],
     ad_aortic, 'aortic'),
    ('aortic_root_dilation',
     [('v5', 'aortic_root_dilation', 'v5 αυτούσιο')],
     ad_v5('get_aortic_root_dilation', 'aortic_root_dilation', 'aortic_root_dilation'), 'v5'),
    ('tricuspid_valve_regurgitation',
     [('strict',    'tricuspid_valve_regurgitation',           'Μέτρια/σοβαρή (= v5 όταν υπάρχει TV)'),
      ('incl_mild', 'tricuspid_valve_regurgitation_incl_mild', 'Ήπια/μέτρια/σοβαρή· ίχνος = 0')],
     ad_tricuspid, 'tricuspid'),
    ('pericardial_effusion',
     [('strict',   'pericardial_effusion_mod_severe',
       'Μέτρια/μεγάλη: ≥10 mm ή φράση μέτρια/μεγάλη/σοβαρή. '
       '«<X» ή «ως/έως/μέχρι X» μετράει μόνο αν X > 10 mm. '
       'Ρητό «μικρή/ελάχιστη» στην ίδια πηγή = 0 όποιος κι αν είναι ο αριθμός. '
       'Οριακή/slash/χωρίς χαρακτηρισμό = 0'),
      ('any_size', 'pericardial_effusion', 'Συλλογή οποιουδήποτε μεγέθους· ίχνος/0 mm = 0')],
     ad_pericardial, 'pericard'),
    ('dilated_ivc',
     [('v5', 'dilated_ivc', 'v5 αυτούσιο')],
     ad_v5('get_dilated_ivc', 'dilated_ivc', 'dilated_ivc'), 'v5'),
]

LABEL_COLUMNS = [col for _, variants, _, _ in REGISTRY for _, col, _ in variants]


# =============================================================================
# SELF-TESTS των επιμέρους scripts
# =============================================================================

def run_module_self_tests() -> dict:
    results = {}
    for key, mod in M.items():
        if not hasattr(mod, 'run_self_test'):
            continue
        lg = getattr(mod, 'logger', None)
        old = lg.level if lg else None
        if lg:
            lg.setLevel(logging.WARNING)       # σιωπηλά· λεπτομέρειες μόνο αν αποτύχει
        try:
            ok = bool(mod.run_self_test())
        except Exception as exc:
            ok = False
            logger.error(f"Self-test {MODULE_FILES[key]} έσκασε: {exc}")
        finally:
            if lg:
                lg.setLevel(old)
        if not ok:
            logger.warning(f"Self-test ΑΠΕΤΥΧΕ: {MODULE_FILES[key]} — τρέξε το script "
                           f"μόνο του για λεπτομέρειες")
        results[MODULE_FILES[key]] = 'PASS' if ok else 'FAIL'
    return results


# =============================================================================
# ΑΝΑΓΝΩΣΗ + CACHE
# =============================================================================

def make_fetcher(seven_zip: str, cache_dir):
    reader = M['mitral']    # ίδια υλοποίηση ανάγνωσης σε όλα τα v6x

    def fetch(entry):
        rp = Path(entry['report_path'])
        cp = Path(cache_dir) / f"{entry['exam_id']}.html" if cache_dir else None
        try:
            if cp and cp.is_file() and cp.stat().st_mtime >= rp.stat().st_mtime:
                return entry, cp.read_text(encoding='utf-8'), True
        except OSError:
            pass
        try:
            html = reader.read_report(entry, seven_zip)
        except Exception as exc:
            logger.warning(f"Ανάγνωση απέτυχε {entry['exam_id']}: {exc}")
            html = None
        if html and cp:
            try:
                cp.write_text(html, encoding='utf-8')
            except OSError:
                pass
        return entry, html, False
    return fetch


# =============================================================================
# RUN
# =============================================================================

def run(dataset_dir, output_dir, exclusion_list=None, seven_zip='', cache_dir=None,
        max_files=None, n_workers=8, run_self_tests=True, scripts_dir=None):
    t0 = time.time()
    scripts_dir = Path(scripts_dir or Path(__file__).resolve().parent)
    hashes = load_modules(scripts_dir)
    logger.info(f"Φορτώθηκαν {len(M)} scripts από {scripts_dir}")

    self_tests = run_module_self_tests() if run_self_tests else {}
    if self_tests:
        logger.info("Self-tests: " + ', '.join(f"{k}={v}" for k, v in self_tests.items()))

    reader = M['mitral']
    entries = reader.find_report_files(dataset_dir)
    n_found = len(entries)
    logger.info(f"Reports που βρέθηκαν: {n_found}")
    excluded = reader.load_exclusion_list(exclusion_list)
    if excluded:
        entries = [e for e in entries if e['exam_id'] not in excluded]
        logger.info(f"Εξαιρέθηκαν (exclusion list): {n_found - len(entries)}")
    n_excluded = n_found - len(entries)

    if any(e['report_type'] == 'chm' for e in entries):
        import shutil
        if not (seven_zip and Path(seven_zip).is_file()):
            seven_zip = shutil.which('7z') or shutil.which('7za') or ''
        if not seven_zip:
            logger.error("Υπάρχουν .CHM reports αλλά δεν βρέθηκε 7-Zip (SEVEN_ZIP_PATH).")
            return
    if max_files:
        entries = entries[:max_files]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

    fetch = make_fetcher(seven_zip, cache_dir)
    wide_rows, long_rows = [], []
    n_cache = n_err = 0
    err_examples = []
    CHUNK = 256

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        for start in range(0, len(entries), CHUNK):
            chunk = entries[start:start + CHUNK]
            logger.info(f"  [{start + 1}-{start + len(chunk)}/{len(entries)}]")
            for entry, html, from_cache in pool.map(fetch, chunk):
                n_cache += from_cache
                wide = {'exam_id': entry['exam_id'], 'report_path': entry['report_path']}
                if not html:
                    wide['status'] = 'read_failed'
                    wide_rows.append(wide)
                    continue

                ctx = ExamContext(html)
                status = 'ok'
                for finding, variants, adapter, _ in REGISTRY:
                    try:
                        rows = adapter(ctx)
                    except Exception as exc:
                        n_err += 1
                        status = 'partial_error'
                        if len(err_examples) < 5:
                            err_examples.append(f"{entry['exam_id']} / {finding}: "
                                                f"{traceback.format_exc(limit=3)}")
                        rows = [_row(finding, v, c, None, flags=[f'error:{type(exc).__name__}'])
                                for v, c, _ in variants]
                    for r in rows:
                        wide[r['column']] = r['label']
                        long_rows.append({'exam_id': entry['exam_id'], **r})
                wide['status'] = status
                wide_rows.append(wide)

    # ── Αρχεία ─────────────────────────────────────────────────────────────
    wide_cols = ['exam_id', 'status'] + LABEL_COLUMNS + ['report_path']
    long_cols = ['exam_id', 'finding', 'variant', 'column', 'label', 'grade',
                 'source', 'rule', 'phrase', 'flags']

    def write_csv(path, cols, rows, enc):
        try:
            with open(path, 'w', newline='', encoding=enc) as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
                w.writeheader()
                for r in rows:
                    w.writerow({c: ('' if r.get(c) is None else r.get(c, '')) for c in cols})
        except PermissionError:
            logger.error(f"Το {path} είναι ανοιχτό (Excel;) — κλείσ' το και ξανατρέξε.")
            raise

    write_csv(out / 'ground_truth_labels.csv', wide_cols, wide_rows, 'utf-8')
    write_csv(out / 'ground_truth_long.csv', long_cols, long_rows, 'utf-8-sig')

    ok_rows = [r for r in wide_rows if r['status'] != 'read_failed']
    summary = []
    for col in LABEL_COLUMNS:
        vals = [r.get(col) for r in ok_rows if r.get(col) is not None]
        pos = sum(v == 1 for v in vals)
        summary.append({'column': col, 'n_labeled': len(vals), 'n_positive': pos,
                        'n_negative': len(vals) - pos,
                        'prevalence_%': round(100 * pos / len(vals), 2) if vals else '',
                        'n_missing': len(ok_rows) - len(vals)})
    write_csv(out / 'ground_truth_summary.csv',
              ['column', 'n_labeled', 'n_positive', 'n_negative', 'prevalence_%', 'n_missing'],
              summary, 'utf-8')

    manifest = {
        'created': datetime.now().isoformat(timespec='seconds'),
        'dataset_dir': str(dataset_dir),
        'exclusion_list': str(exclusion_list) if exclusion_list else None,
        'n_reports_found': n_found,
        'n_excluded': n_excluded,
        'n_processed': len(wide_rows),
        'n_read_failed': len(wide_rows) - len(ok_rows),
        'n_from_cache': n_cache,
        'n_adapter_errors': n_err,
        'max_files': max_files,
        'scripts_sha256_16': hashes,
        'self_tests': self_tests,
        'variants': [{'finding': f, 'variant': v, 'column': c, 'definition': d,
                      'script': MODULE_FILES[s]}
                     for f, vs, _, s in REGISTRY for v, c, d in vs],
        'runtime_sec': round(time.time() - t0, 1),
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding='utf-8')

    # ── Log ────────────────────────────────────────────────────────────────
    logger.info("=" * 70)
    logger.info(f"Εξετάσεις: {len(wide_rows)} | αναγνώστηκαν: {len(ok_rows)} | "
                f"read_failed: {len(wide_rows) - len(ok_rows)} | από cache: {n_cache}")
    logger.info(f"\n  {'Στήλη':<44} {'Pos':>6} {'N':>7} {'%':>6}")
    for s in summary:
        logger.info(f"  {s['column']:<44} {s['n_positive']:>6} {s['n_labeled']:>7} "
                    f"{s['prevalence_%']:>6}")
    if n_err:
        logger.warning(f"{n_err} σφάλματα σε adapters (στήλες κενές, flag error:*). Παραδείγματα:")
        for e in err_examples:
            logger.warning(e)
    logger.info(f"\nOutput: {out}  ({manifest['runtime_sec']} s)")


# =============================================================================
# MAIN (F5) — ΑΛΛΑΖΕΙΣ ΜΟΝΟ ΑΥΤΟ ΤΟ BLOCK
# =============================================================================

if __name__ == "__main__":
    DATASET_DIR         = r"data/reports"                                   # <root>\<exam_id>\report\<αρχείο>
    OUTPUT_DIR          = r"outputs/ground_truth/binary"
    CACHE_DIR           = r"outputs/ground_truth/binary/html_cache" # None = χωρίς cache
    EXCLUSION_LIST_PATH = r"data/lists/exclusion_ids.txt"  # ή None
    SEVEN_ZIP_PATH      = r"C:/Program Files/7-Zip/7z.exe"               # χρειάζεται μόνο για .CHM
    MAX_FILES           = None                                              # π.χ. 300 για γρήγορη δοκιμή
    N_WORKERS           = 8                                                 # παράλληλες εξαγωγές CHM
    RUN_SELF_TESTS      = True
    SCRIPTS_DIR         = None    # None = ο φάκελος αυτού του αρχείου (εκεί πρέπει να είναι τα 9 scripts)

    run(DATASET_DIR, OUTPUT_DIR, EXCLUSION_LIST_PATH, SEVEN_ZIP_PATH, CACHE_DIR,
        MAX_FILES, N_WORKERS, RUN_SELF_TESTS, SCRIPTS_DIR)
