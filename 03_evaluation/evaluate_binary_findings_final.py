r"""
evaluate_binary_findings.py
===========================
Binary evaluation του EchoPrime για ΟΛΑ τα findings και ΟΛΕΣ τις εκδοχές GT,
σε ένα τρέξιμο. Είσοδος: το ground_truth_labels.csv του run_ground_truth.py.

ΤΙ ΥΠΟΛΟΓΙΖΕΙ
  Ανά (finding, εκδοχή):
    N εξετάσεων / ασθενών, N θετικά / αρνητικά, prevalence,
    AUROC, AUPRC, Sensitivity, Specificity, PPV, NPV, Accuracy, F1 (όριο 0.5),
    TP / FP / FN / TN — με 95% CI από patient-level cluster bootstrap.
  Exploratory: όριο Youden (επιλέγεται και αξιολογείται στα ίδια δεδομένα).
  Table S2: για την κύρια εκδοχή κάθε finding (TABLE_S2_VARIANT), όριο που
    δίνει specificity ≥ SPEC_TARGET με τη μέγιστη sensitivity. Το όριο
    επιλέγεται ΜΙΑ φορά στο πλήρες δείγμα και μένει σταθερό στο bootstrap
    (CI = δειγματοληπτική αβεβαιότητα στο συγκεκριμένο σημείο λειτουργίας).
  Για findings με >1 εκδοχή (π.χ. strict vs incl_mild):
    ΔAUROC και ΔAUPRC (εκδοχή B − εκδοχή A) με 95% CI και bootstrap p-value,
    Holm–Bonferroni σε όλη την οικογένεια συγκρίσεων εκδοχών.

ΣΧΕΔΙΑΣΜΟΣ
  - Ίδιο σύνολο εξετάσεων για όλες τις εκδοχές ενός finding (εξετάσεις με
    πρόβλεψη ΚΑΙ label σε κάθε εκδοχή) → η σύγκριση είναι paired: αλλάζει μόνο
    το GT, όχι ο denominator.
  - Ίδια bootstrap resamples (ίδιο seed, ίδιοι ασθενείς) για όλες τις εκδοχές
    ενός finding.
  - Bootstrap με βάρη: κάθε resample = πόσες φορές επιλέχθηκε κάθε ασθενής.
    Οι μετρικές υπολογίζονται με βάρη ανά εξέταση — μαθηματικά ίδιο με την
    αντιγραφή γραμμών, αλλά πολύ γρηγορότερο (10.000 × 25 εκδοχές σε λεπτά).
  - Resamples με μία μόνο κλάση παραλείπονται (καταγράφονται).
  - p-value: δίπλευρο, Phipson–Smyth (b+1)/(m+1), b = 2·min(#Δ≤0, #Δ≥0).

OUTPUT (στο OUTPUT_DIR)
  binary_evaluation.xlsx
     Summary              μία γραμμή ανά (finding, εκδοχή), όριο 0.5
     Youden_Exploratory   ίδιες μετρικές στο όριο Youden
     TableS2_Spec90       17 findings, κύρια εκδοχή, όριο για specificity ≥ 90%
     Variant_Comparison   ΔAUROC / ΔAUPRC ανά finding, Holm
     Cohort               εξετάσεις που μπήκαν / έμειναν εκτός ανά finding
     Missing_or_Unmatched γραμμές GT χωρίς πρόβλεψη και αντίστροφα
     Excluded_IDs         από το exclusion list
     Methods              ορισμοί εκδοχών (από manifest.json) + ρυθμίσεις
  per_exam_predictions.csv  exam_id, patient_id, GT όλων των εκδοχών, scores

Εκτέλεση: F5. Ρυθμίσεις στο block CONFIGURATION.
Εξαρτήσεις: numpy, pandas, openpyxl
"""

import sys
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("binary_eval")

# =============================================================================
# CONFIGURATION
# =============================================================================

GT_CSV                = r"outputs/ground_truth/binary/ground_truth_labels.csv"
GT_MANIFEST           = r"outputs/ground_truth/binary/manifest.json"   # None αν δεν υπάρχει
MODEL_PREDICTIONS_CSV = r"outputs/predictions/predictions_raw_.csv"
OUTPUT_DIR            = r"outputs/evaluation/binary"
OUTPUT_XLSX_NAME      = "binary_evaluation.xlsx"

EXCLUSION_FILE = r"data/lists/exclusion_ids.txt"  # ή None

PATIENT_MAP_FILE        = r"data/metadata/study_patient_mapping.csv"  # ή None
PATIENT_MAP_SHEET       = 0
PATIENT_MAP_EXAM_COL    = "exam_id"
PATIENT_MAP_PATIENT_COL = "patient_id"

GT_ID_COL   = "exam_id"
PRED_ID_COL = "study_id"

THRESHOLD   = 0.5
N_BOOTSTRAP = 10_000
SEED        = 42
CI_ALPHA    = 0.05

# ── TASKS ────────────────────────────────────────────────────────────────────
# finding → (στήλη πρόβλεψης EchoPrime, [(εκδοχή, στήλη GT), ...])
# Η ΠΡΩΤΗ εκδοχή είναι η αναφορά στη Variant_Comparison (Δ = άλλη − πρώτη).
# Αν μια στήλη πρόβλεψης έχει άλλο όνομα στο MODEL_PREDICTIONS_CSV, άλλαξέ
# την εδώ. Findings που λείπουν από τα predictions καταγράφονται και
# παραλείπονται.
TASKS = {
    'pacemaker':                      ('pacemaker',
                                       [('strict', 'pacemaker'),
                                        ('incl_icd', 'pacemaker_incl_icd')]),
    'rv_systolic_function_depressed': ('rv_systolic_function_depressed',
                                       [('strict', 'rv_systolic_function_depressed'),
                                        ('incl_mild', 'rv_systolic_function_depressed_incl_mild')]),
    'right_ventricle_dilation':       ('right_ventricle_dilation',
                                       [('v5', 'right_ventricle_dilation')]),
    'right_atrium_dilation':          ('right_atrium_dilation',
                                       [('v5', 'right_atrium_dilation')]),
    'left_atrium_dilation':           ('left_atrium_dilation',
                                       [('v5', 'left_atrium_dilation')]),
    'mitraclip':                      ('mitraclip',
                                       [('v5', 'mitraclip')]),
    'mitral_annular_calcification':   ('mitral_annular_calcification',
                                       [('strict', 'mitral_annular_calcification'),
                                        ('incl_mild', 'mitral_annular_calcification_incl_mild')]),
    'mitral_stenosis':                ('mitral_stenosis',
                                       [('strict', 'mitral_stenosis'),
                                        ('incl_mild', 'mitral_stenosis_incl_mild')]),
    'mitral_regurgitation':           ('mitral_regurgitation',
                                       [('strict', 'mitral_regurgitation'),
                                        ('incl_mild', 'mitral_regurgitation_incl_mild')]),
    'tavr':                           ('tavr',
                                       [('incl_mech', 'tavr_incl_mech'),
                                        ('excl_mech', 'tavr_excl_mech')]),
    'bicuspid_aov':                   ('bicuspid_aov_morphology',
                                       [('v5', 'bicuspid_aov')]),
    'aortic_stenosis':                ('aortic_stenosis',
                                       [('strict', 'aortic_stenosis'),
                                        ('incl_mild', 'aortic_stenosis_incl_mild')]),
    'aortic_regurgitation':           ('aortic_regurgitation',
                                       [('strict', 'aortic_regurgitation'),
                                        ('incl_mild', 'aortic_regurgitation_incl_mild')]),
    'aortic_root_dilation':           ('aortic_root_dilation',
                                       [('v5', 'aortic_root_dilation')]),
    'tricuspid_valve_regurgitation':  ('tricuspid_valve_regurgitation',
                                       [('strict', 'tricuspid_valve_regurgitation'),
                                        ('incl_mild', 'tricuspid_valve_regurgitation_incl_mild')]),
    'pericardial_effusion':           ('pericardial_effusion',
                                       [('strict', 'pericardial_effusion_mod_severe'),
                                        ('any_size', 'pericardial_effusion')]),
    'dilated_ivc':                    ('dilated_ivc',
                                       [('v5', 'dilated_ivc')]),
}

# ── TABLE S2 ─────────────────────────────────────────────────────────────────
# Όριο λειτουργίας: specificity ≥ SPEC_TARGET, με τη μέγιστη sensitivity.
SPEC_TARGET = 0.90
EXPECTED_N  = 2359      # έλεγχος: N εξετάσεων ανά finding στον Table S2 (None = χωρίς έλεγχο)

# finding → (εκδοχή που μπαίνει στον Table S2, όνομα γραμμής στον πίνακα)
TABLE_S2_VARIANT = {
    'pacemaker':                      ('incl_icd',  'Pacemaker'),
    'rv_systolic_function_depressed': ('strict',    'RV systolic dysfunction'),
    'right_ventricle_dilation':       ('v5',        'RV dilation'),
    'right_atrium_dilation':          ('v5',        'RA dilation'),
    'left_atrium_dilation':           ('v5',        'LA dilation'),
    'mitraclip':                      ('v5',        'MitraClip'),
    'mitral_annular_calcification':   ('strict',    'Mitral annular calcification'),
    'mitral_stenosis':                ('strict',    'Mitral stenosis'),
    'mitral_regurgitation':           ('strict',    'Mitral regurgitation'),
    'tavr':                           ('excl_mech', 'TAVR'),
    'bicuspid_aov':                   ('v5',        'Bicuspid AV'),
    'aortic_stenosis':                ('strict',    'Aortic stenosis'),
    'aortic_regurgitation':           ('strict',    'Aortic regurgitation'),
    'aortic_root_dilation':           ('v5',        'Aortic root dilation'),
    'tricuspid_valve_regurgitation':  ('strict',    'Tricuspid regurgitation'),
    'pericardial_effusion':           ('strict',    'Pericardial effusion'),
    'dilated_ivc':                    ('v5',        'Dilated IVC'),
}
DASH = "–"   # CI που δεν μπορεί να εκτιμηθεί (λεζάντα Table S2)

THR_KEYS = ["sensitivity", "specificity", "ppv", "npv", "accuracy", "f1"]
THR_LABELS = {"sensitivity": "Sensitivity", "specificity": "Specificity", "ppv": "PPV",
              "npv": "NPV", "accuracy": "Accuracy", "f1": "F1 Score"}


# =============================================================================
# HELPERS
# =============================================================================

def normalize_id(x):
    if pd.isna(x):
        return np.nan
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s if s else np.nan


def read_table(path, sheet=0):
    path = Path(path)
    if not path.exists():
        logger.error(f"Δεν βρέθηκε το αρχείο: {path}")
        sys.exit(1)
    if path.suffix.lower() in (".xlsx", ".xls", ".xlsm"):
        return pd.read_excel(path, sheet_name=sheet, dtype=str)
    return pd.read_csv(path, dtype=str)


def load_exclusion_list(filepath):
    if not filepath or not Path(filepath).exists():
        if filepath:
            logger.warning(f"Exclusion file δεν βρέθηκε: {filepath} — χωρίς exclusions")
        return set()
    ids = set()
    for line in Path(filepath).read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.add(normalize_id(line))
    logger.info(f"Exclusion list: {len(ids):,} IDs")
    return ids


def fmt_ci(point, ci, d=4):
    if point is None or pd.isna(point):
        return "N/A"
    lo, hi = ci
    if pd.isna(lo):
        return f"{point:.{d}f}"
    return f"{point:.{d}f} ({lo:.{d}f}-{hi:.{d}f})"


def fmt_ci_dash(point, ci, d=4):
    """Όπως fmt_ci, αλλά με παύλα: '–' αν η μετρική δεν ορίζεται,
    'x.xxxx (–)' αν ορίζεται αλλά το CI δεν μπορεί να εκτιμηθεί."""
    if point is None or pd.isna(point):
        return DASH
    lo, hi = ci
    if pd.isna(lo):
        return f"{point:.{d}f} ({DASH})"
    return f"{point:.{d}f} ({lo:.{d}f}-{hi:.{d}f})"


def fmt_p(p):
    if p is None or pd.isna(p):
        return "N/A"
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"


# =============================================================================
# WEIGHTED METRICS (w = πόσες φορές μετράει κάθε εξέταση στο resample)
# =============================================================================

class ScoreIndex:
    """Ταξινόμηση των scores μία φορά, με ομαδοποίηση ισοβαθμιών."""

    def __init__(self, scores):
        self.order = np.argsort(-scores, kind="mergesort")          # φθίνουσα
        s_sorted = scores[self.order]
        new_grp = np.r_[True, s_sorted[1:] != s_sorted[:-1]]
        self.group = np.cumsum(new_grp) - 1                          # ομάδα ανά θέση
        self.n_groups = int(self.group[-1]) + 1 if len(scores) else 0


def weighted_auc_ap(y, w, idx: ScoreIndex):
    """AUROC (Mann–Whitney με ισοβαθμίες = 0.5) και AUPRC (average precision,
    ίδιος ορισμός με sklearn) με βάρη."""
    yo, wo = y[idx.order], w[idx.order]
    pos_g = np.bincount(idx.group, weights=wo * (yo == 1), minlength=idx.n_groups)
    neg_g = np.bincount(idx.group, weights=wo * (yo == 0), minlength=idx.n_groups)
    P, N = pos_g.sum(), neg_g.sum()
    if P == 0 or N == 0:
        return np.nan, np.nan
    # AUROC: για κάθε ομάδα (φθίνουσα), θετικά × (αρνητικά με χαμηλότερο score + ½ ισοβαθμία)
    neg_below = N - np.cumsum(neg_g)
    auc = float(np.sum(pos_g * (neg_below + 0.5 * neg_g)) / (P * N))
    # AUPRC: Σ (ΔRecall × Precision) σε κάθε κατώφλι
    tp, fp = np.cumsum(pos_g), np.cumsum(neg_g)
    precision = tp / np.maximum(tp + fp, 1e-12)
    ap = float(np.sum(pos_g / P * precision))
    return auc, ap


def weighted_thr_metrics(y, pred, w):
    tp = float(np.sum(w * ((y == 1) & (pred == 1))))
    tn = float(np.sum(w * ((y == 0) & (pred == 0))))
    fp = float(np.sum(w * ((y == 0) & (pred == 1))))
    fn = float(np.sum(w * ((y == 1) & (pred == 0))))
    tot = tp + tn + fp + fn
    div = lambda a, b: a / b if b else np.nan
    return {"sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
            "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn),
            "accuracy": div(tp + tn, tot), "f1": div(2 * tp, 2 * tp + fp + fn),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def youden_threshold(y, scores):
    """Όριο που μεγιστοποιεί Sens + Spec − 1 (σε μοναδικές τιμές score)."""
    idx = ScoreIndex(scores)
    yo = y[idx.order]
    pos_g = np.bincount(idx.group, weights=(yo == 1).astype(float), minlength=idx.n_groups)
    neg_g = np.bincount(idx.group, weights=(yo == 0).astype(float), minlength=idx.n_groups)
    tpr = np.cumsum(pos_g) / pos_g.sum()
    fpr = np.cumsum(neg_g) / neg_g.sum()
    best = int(np.argmax(tpr - fpr))
    thr_vals = scores[idx.order][np.searchsorted(idx.group, np.arange(idx.n_groups))]
    return float(thr_vals[best])


def spec_threshold(y, scores, target=SPEC_TARGET):
    """Χαμηλότερο όριο (σε μοναδικές τιμές score) με specificity ≥ target,
    δηλ. FPR ≤ 1 − target → μέγιστη sensitivity υπό τον περιορισμό.
    Κανόνας θετικού: score ≥ όριο (ισοβαθμίες μπαίνουν ολόκληρες).
    Επιστρέφει np.inf αν ούτε η ομάδα με το υψηλότερο score δεν χωράει
    (τότε όλες οι προβλέψεις είναι αρνητικές)."""
    idx = ScoreIndex(scores)
    yo = y[idx.order]
    neg_g = np.bincount(idx.group, weights=(yo == 0).astype(float), minlength=idx.n_groups)
    fpr = np.cumsum(neg_g) / neg_g.sum()
    ok = np.where(fpr <= (1 - target) + 1e-12)[0]
    if not len(ok):
        return np.inf
    thr_vals = scores[idx.order][np.searchsorted(idx.group, np.arange(idx.n_groups))]
    return float(thr_vals[ok[-1]])


# =============================================================================
# CLUSTER BOOTSTRAP
# =============================================================================

def bootstrap_weights(patient_codes, n_patients, n_iter, seed):
    """Generator: βάρη ανά εξέταση = πόσες φορές επιλέχθηκε ο ασθενής της."""
    rng = np.random.default_rng(seed)
    for _ in range(n_iter):
        counts = np.bincount(rng.integers(0, n_patients, size=n_patients), minlength=n_patients)
        yield counts[patient_codes].astype(float)


def ci_of(vals):
    vals = np.asarray([v for v in vals if not np.isnan(v)])
    if not len(vals):
        return (np.nan, np.nan)
    return (float(np.percentile(vals, 100 * CI_ALPHA / 2)),
            float(np.percentile(vals, 100 * (1 - CI_ALPHA / 2))))


def boot_p(deltas):
    d = np.asarray([v for v in deltas if not np.isnan(v)])
    m = len(d)
    if not m:
        return np.nan
    b = 2 * min(np.sum(d <= 0), np.sum(d >= 0))
    return min(1.0, (b + 1) / (m + 1))


def holm(pvals):
    p = np.asarray(pvals, dtype=float)
    out = np.full(len(p), np.nan)
    ok = ~np.isnan(p)
    idx = np.where(ok)[0][np.argsort(p[ok])]
    m, running = len(idx), 0.0
    for rank, i in enumerate(idx):
        running = max(running, min(1.0, (m - rank) * p[i]))
        out[i] = running
    return out


# =============================================================================
# EVALUATION ΕΝΟΣ FINDING (όλες οι εκδοχές μαζί, paired)
# =============================================================================

def evaluate_finding(finding, pred_col, variants, df, s2_variant=None, s2_label=None):
    """
    df: εξετάσεις του finding (κοινό σύνολο), με στήλες patient_id, score,
        και μία στήλη GT ανά εκδοχή.
    s2_variant: εκδοχή για τον Table S2 (None = δεν μπαίνει στον πίνακα).
    Επιστρέφει: (summary_rows, youden_rows, comparison_rows, s2_rows, n_skipped)
    """
    scores = df["score"].to_numpy(float)
    idx = ScoreIndex(scores)
    codes, uniq = pd.factorize(df["patient_id"])
    Y = {v: df[col].to_numpy(int) for v, col in variants}

    # Σημειακές εκτιμήσεις + Youden
    point, yth = {}, {}
    ones = np.ones(len(df))
    for v, _ in variants:
        y = Y[v]
        auc, ap = weighted_auc_ap(y, ones, idx)
        m05 = weighted_thr_metrics(y, (scores >= THRESHOLD).astype(int), ones)
        point[v] = {"auroc": auc, "auprc": ap, **m05}
        if 0 < y.sum() < len(y):
            t = youden_threshold(y, scores)
            yth[v] = (t, weighted_thr_metrics(y, (scores >= t).astype(int), ones))
        else:
            yth[v] = (np.nan, None)

    # Table S2: όριο για specificity ≥ SPEC_TARGET (επιλογή μία φορά, σταθερό στο bootstrap)
    s2 = None
    if s2_variant is not None:
        y = Y[s2_variant]
        if 0 < y.sum() < len(y):
            t = spec_threshold(y, scores)
            s2_pred = (scores >= t).astype(int)
            s2 = (t, s2_pred, weighted_thr_metrics(y, s2_pred, ones))

    # Bootstrap — ίδια βάρη για όλες τις εκδοχές
    boot = {v: {k: [] for k in ["auroc", "auprc"] + THR_KEYS
                + ["y_" + k for k in THR_KEYS] + ["s_" + k for k in THR_KEYS]}
            for v, _ in variants}
    deltas = {v: {"auroc": [], "auprc": []} for v, _ in variants[1:]}
    pred05 = (scores >= THRESHOLD).astype(int)
    predY = {v: (scores >= yth[v][0]).astype(int) for v, _ in variants if not np.isnan(yth[v][0])}
    ref = variants[0][0]
    skipped = 0
    for w in bootstrap_weights(codes, len(uniq), N_BOOTSTRAP, SEED):
        res = {}
        for v, _ in variants:
            auc, ap = weighted_auc_ap(Y[v], w, idx)
            res[v] = (auc, ap)
            if np.isnan(auc):
                continue
            boot[v]["auroc"].append(auc)
            boot[v]["auprc"].append(ap)
            m = weighted_thr_metrics(Y[v], pred05, w)
            for k in THR_KEYS:
                boot[v][k].append(m[k])
            if v in predY:
                my = weighted_thr_metrics(Y[v], predY[v], w)
                for k in THR_KEYS:
                    boot[v]["y_" + k].append(my[k])
            if s2 is not None and v == s2_variant:
                ms = weighted_thr_metrics(Y[v], s2[1], w)
                for k in THR_KEYS:
                    boot[v]["s_" + k].append(ms[k])
        if any(np.isnan(res[v][0]) for v, _ in variants):
            skipped += 1
            continue
        for v, _ in variants[1:]:
            deltas[v]["auroc"].append(res[v][0] - res[ref][0])
            deltas[v]["auprc"].append(res[v][1] - res[ref][1])

    n_pat = len(uniq)
    summary, youden, comp = [], [], []
    for v, col in variants:
        y, pt = Y[v], point[v]
        n_pos = int(y.sum())
        row = {"Finding": finding, "Variant": v, "GT Column": col, "Pred Column": pred_col,
               "N (Exams)": len(y), "N (Patients)": n_pat,
               "N Positive": n_pos, "N Negative": len(y) - n_pos,
               "Prevalence (%)": round(100 * n_pos / len(y), 2) if len(y) else np.nan,
               "AUROC (95% CI)": fmt_ci(pt["auroc"], ci_of(boot[v]["auroc"])),
               "AUPRC (95% CI)": fmt_ci(pt["auprc"], ci_of(boot[v]["auprc"]))}
        for k in THR_KEYS:
            row[f"{THR_LABELS[k]} (95% CI)"] = fmt_ci(pt[k], ci_of(boot[v][k]))
        for k in ("tp", "fp", "fn", "tn"):
            row[k.upper()] = int(pt[k])
        row["Bootstrap resamples used"] = len(boot[v]["auroc"])
        summary.append(row)

        t, my = yth[v]
        yrow = {"Finding": finding, "Variant": v, "GT Column": col,
                "Youden Threshold": round(t, 4) if not np.isnan(t) else "N/A"}
        for k in THR_KEYS:
            yrow[f"{THR_LABELS[k]} (95% CI)"] = (fmt_ci(my[k], ci_of(boot[v]["y_" + k]))
                                                  if my else "N/A")
        for k in ("tp", "fp", "fn", "tn"):
            yrow[k.upper()] = int(my[k]) if my else "N/A"
        youden.append(yrow)

    for v, col in variants[1:]:
        da, dp = deltas[v]["auroc"], deltas[v]["auprc"]
        comp.append({
            "Finding": finding, "Reference": ref, "Variant": v,
            "N (Exams)": len(df), "N (Patients)": n_pat,
            f"Prevalence {ref} (%)": round(100 * Y[ref].mean(), 2),
            f"Prevalence variant (%)": round(100 * Y[v].mean(), 2),
            "AUROC reference": round(point[ref]["auroc"], 4),
            "AUROC variant": round(point[v]["auroc"], 4),
            "ΔAUROC (95% CI)": fmt_ci(point[v]["auroc"] - point[ref]["auroc"], ci_of(da)),
            "p ΔAUROC": boot_p(da),
            "AUPRC reference": round(point[ref]["auprc"], 4),
            "AUPRC variant": round(point[v]["auprc"], 4),
            "ΔAUPRC (95% CI)": fmt_ci(point[v]["auprc"] - point[ref]["auprc"], ci_of(dp)),
            "p ΔAUPRC": boot_p(dp),
            "Paired resamples": len(da),
            "Note": "" if len(da) else "Μία εκδοχή έχει μία μόνο κλάση — σύγκριση μη εφικτή",
        })

    # ── Table S2 γραμμή ─────────────────────────────────────────────────────
    s2_rows = []
    if s2_variant is not None:
        col = dict(variants)[s2_variant]
        y, pt = Y[s2_variant], point[s2_variant]
        n_pos = int(y.sum())
        srow = {"Feature": s2_label or finding, "Finding": finding, "Variant": s2_variant,
                "GT Column": col, "N (Exams)": len(y), "N (Patients)": n_pat,
                "N Positive": n_pos, "N Negative": len(y) - n_pos,
                "Prevalence (%)": round(100 * n_pos / len(y), 2) if len(y) else np.nan}
        if s2 is None:
            srow["Threshold"] = DASH
            srow["AUROC (95% CI)"] = fmt_ci_dash(pt["auroc"], ci_of(boot[s2_variant]["auroc"]))
            srow["AUPRC (95% CI)"] = fmt_ci_dash(pt["auprc"], ci_of(boot[s2_variant]["auprc"]))
            for k in THR_KEYS:
                srow[f"{THR_LABELS[k]} (95% CI)"] = DASH
            for k in ("tp", "fp", "fn", "tn"):
                srow[k.upper()] = DASH
            srow["Note"] = "Μία μόνο κλάση — όριο μη εφικτό"
        else:
            t, _, ms = s2
            srow["Threshold"] = (f"> max score ({scores.max():.6f})" if np.isinf(t) else round(t, 6))
            srow["AUROC (95% CI)"] = fmt_ci_dash(pt["auroc"], ci_of(boot[s2_variant]["auroc"]))
            srow["AUPRC (95% CI)"] = fmt_ci_dash(pt["auprc"], ci_of(boot[s2_variant]["auprc"]))
            notes = []
            if np.isinf(t):
                notes.append(f"Καμία τιμή score δεν δίνει specificity ≥ {SPEC_TARGET:.0%} "
                             f"(ισοβαθμία στο υψηλότερο score) — όλες οι προβλέψεις αρνητικές")
            n_used = len(boot[s2_variant]["s_sensitivity"])
            for k in THR_KEYS:
                vals = np.asarray(boot[s2_variant]["s_" + k], dtype=float)
                srow[f"{THR_LABELS[k]} (95% CI)"] = fmt_ci_dash(ms[k], ci_of(vals))
                n_nan = int(np.isnan(vals).sum())
                if n_nan and not pd.isna(ms[k]):
                    notes.append(f"{THR_LABELS[k]} μη ορισμένο σε {n_nan:,}/{n_used:,} resamples "
                                 f"(εκτός CI)")
            for k in ("tp", "fp", "fn", "tn"):
                srow[k.upper()] = int(ms[k])
            srow["Note"] = "; ".join(notes)
        srow["Bootstrap resamples used"] = len(boot[s2_variant]["auroc"])
        s2_rows.append(srow)

    return summary, youden, comp, s2_rows, skipped


# =============================================================================
# LOAD
# =============================================================================

def load_patient_map():
    if PATIENT_MAP_FILE is None:
        logger.warning("PATIENT_MAP_FILE=None → exam-level bootstrap")
        return None
    df = read_table(PATIENT_MAP_FILE, PATIENT_MAP_SHEET)
    for c in (PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL):
        if c not in df.columns:
            logger.error(f"Στήλη '{c}' δεν βρέθηκε στο patient map. Διαθέσιμες: {list(df.columns)}")
            sys.exit(1)
    df = df[[PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL]].copy()
    for c in df.columns:
        df[c] = df[c].apply(normalize_id)
    df = df.dropna().drop_duplicates(subset=PATIENT_MAP_EXAM_COL)
    logger.info(f"Patient map: {len(df)} εξετάσεις → {df[PATIENT_MAP_PATIENT_COL].nunique()} ασθενείς")
    return dict(zip(df[PATIENT_MAP_EXAM_COL], df[PATIENT_MAP_PATIENT_COL]))


def dedupe(df, col, source, issues):
    dup = df[col].duplicated(keep="first")
    for sid in df.loc[dup, col].unique():
        issues.append({"Finding": "ALL", "Study_ID": sid,
                       "Issue": f"Duplicate ID in {source}", "Detail": "Kept first"})
    if dup.any():
        logger.warning(f"{source}: {dup.sum()} διπλές γραμμές — κρατιέται η πρώτη")
    return df[~dup].copy()


# =============================================================================
# MAIN
# =============================================================================

def main():
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    issues, excluded_log, cohort = [], [], []

    # Έλεγχος ρυθμίσεων Table S2 πριν από οτιδήποτε άλλο
    for f, (v, _) in TABLE_S2_VARIANT.items():
        if f not in TASKS:
            logger.error(f"TABLE_S2_VARIANT: finding '{f}' δεν υπάρχει στα TASKS")
            sys.exit(1)
        if v not in [vv for vv, _ in TASKS[f][1]]:
            logger.error(f"TABLE_S2_VARIANT: εκδοχή '{v}' δεν υπάρχει για '{f}'. "
                         f"Διαθέσιμες: {[vv for vv, _ in TASKS[f][1]]}")
            sys.exit(1)

    excluded = load_exclusion_list(EXCLUSION_FILE)

    # ── GT ──────────────────────────────────────────────────────────────────
    gt = read_table(GT_CSV)
    gt[GT_ID_COL] = gt[GT_ID_COL].apply(normalize_id)
    gt = gt.dropna(subset=[GT_ID_COL]).rename(columns={GT_ID_COL: "exam_id"})
    gt = dedupe(gt, "exam_id", "GT", issues)
    if "status" in gt.columns:
        bad = gt["status"] == "read_failed"
        for sid in gt.loc[bad, "exam_id"]:
            issues.append({"Finding": "ALL", "Study_ID": sid, "Issue": "GT read_failed", "Detail": ""})
        gt = gt[~bad]
    if excluded:
        m = gt["exam_id"].isin(excluded)
        excluded_log += [{"Study_ID": s, "Source": "GT"} for s in gt.loc[m, "exam_id"]]
        gt = gt[~m]
    logger.info(f"GT: {len(gt)} εξετάσεις")

    # ── Predictions ─────────────────────────────────────────────────────────
    pred = read_table(MODEL_PREDICTIONS_CSV)
    if PRED_ID_COL not in pred.columns:
        logger.error(f"Λείπει η στήλη '{PRED_ID_COL}' στα predictions. Διαθέσιμες: {list(pred.columns)}")
        sys.exit(1)
    pred[PRED_ID_COL] = pred[PRED_ID_COL].apply(normalize_id)
    pred = pred.dropna(subset=[PRED_ID_COL]).rename(columns={PRED_ID_COL: "exam_id"})
    pred = dedupe(pred, "exam_id", "Predictions", issues)
    if excluded:
        m = pred["exam_id"].isin(excluded)
        excluded_log += [{"Study_ID": s, "Source": "Predictions"} for s in pred.loc[m, "exam_id"]]
        pred = pred[~m]
    logger.info(f"Predictions: {len(pred)} εξετάσεις")

    for sid in sorted(set(pred["exam_id"]) - set(gt["exam_id"])):
        issues.append({"Finding": "ALL", "Study_ID": sid, "Issue": "Prediction without GT row", "Detail": ""})
    for sid in sorted(set(gt["exam_id"]) - set(pred["exam_id"])):
        issues.append({"Finding": "ALL", "Study_ID": sid, "Issue": "GT without prediction", "Detail": ""})

    # Οι στήλες GT και πρόβλεψης έχουν ΙΔΙΑ ονόματα (π.χ. 'pacemaker') →
    # ρητό prefix στις προβλέψεις, ώστε να μη γίνει ποτέ σύγχυση.
    pred = pred.rename(columns={c: f"pred__{c}" for c in pred.columns if c != "exam_id"})
    merged = gt.merge(pred, on="exam_id", how="inner")

    patient_map = load_patient_map()
    if patient_map is not None:
        merged["patient_id"] = merged["exam_id"].map(patient_map)
        unm = merged["patient_id"].isna()
        for sid in merged.loc[unm, "exam_id"]:
            issues.append({"Finding": "ALL", "Study_ID": sid, "Issue": "No patient mapping",
                           "Detail": "Treated as its own cluster"})
        if unm.any():
            logger.warning(f"{unm.sum()} εξετάσεις χωρίς patient mapping — ξεχωριστοί ασθενείς")
        merged.loc[unm, "patient_id"] = "EXAM_" + merged.loc[unm, "exam_id"]
        boot_type = "Patient-level cluster bootstrap"
    else:
        merged["patient_id"] = merged["exam_id"]
        boot_type = "Exam-level bootstrap (no patient map)"

    # ── Ανά finding ─────────────────────────────────────────────────────────
    summary, youden, comp, table_s2 = [], [], [], []
    per_exam = merged[["exam_id", "patient_id"]].copy()
    for finding, (pred_col, variants) in TASKS.items():
        pc = f"pred__{pred_col}"
        if pc not in merged.columns:
            logger.warning(f"[{finding}] στήλη πρόβλεψης '{pred_col}' δεν υπάρχει — παράλειψη")
            issues.append({"Finding": finding, "Study_ID": "", "Issue": "Prediction column missing",
                           "Detail": pred_col})
            continue
        missing_gt = [c for _, c in variants if c not in merged.columns]
        if missing_gt:
            logger.warning(f"[{finding}] στήλες GT λείπουν: {missing_gt} — παράλειψη")
            issues.append({"Finding": finding, "Study_ID": "", "Issue": "GT column missing",
                           "Detail": ", ".join(missing_gt)})
            continue

        d = merged[["exam_id", "patient_id"]].copy()
        d["score"] = pd.to_numeric(merged[pc], errors="coerce")
        for _, c in variants:
            d[c] = pd.to_numeric(merged[c], errors="coerce")
            per_exam[c] = d[c]
        per_exam[f"score__{pred_col}"] = d["score"]

        gt_cols = [c for _, c in variants]
        bad_label = d[gt_cols].notna() & ~d[gt_cols].isin([0, 1])
        d[gt_cols] = d[gt_cols].mask(bad_label)
        nan_score = d["score"].isna()
        nan_gt = d[gt_cols].isna().any(axis=1)
        for sid in d.loc[nan_score, "exam_id"]:
            issues.append({"Finding": finding, "Study_ID": sid, "Issue": "Prediction is NaN", "Detail": pred_col})
        for sid in d.loc[~nan_score & nan_gt, "exam_id"]:
            issues.append({"Finding": finding, "Study_ID": sid, "Issue": "GT label missing",
                           "Detail": "Excluded from all variants (paired set)"})
        d = d[~nan_score & ~nan_gt].reset_index(drop=True)

        cohort.append({"Finding": finding, "Pred Column": pred_col,
                       "Merged exams": len(merged), "NaN prediction": int(nan_score.sum()),
                       "Missing GT label": int((~nan_score & nan_gt).sum()),
                       "Evaluated exams": len(d), "Evaluated patients": d["patient_id"].nunique()})

        sc = d["score"]
        if len(sc) and (sc.min() < 0 or sc.max() > 1):
            logger.warning(f"[{finding}] scores εκτός [0,1] ({sc.min():.3f}–{sc.max():.3f}) — "
                           f"το όριο {THRESHOLD} μπορεί να μην έχει νόημα")
        if len(d) == 0 or all(d[c].nunique() < 2 for c in gt_cols):
            logger.warning(f"[{finding}] μία μόνο κλάση ή κενό σύνολο — παράλειψη")
            issues.append({"Finding": finding, "Study_ID": "", "Issue": "Single class or empty",
                           "Detail": f"N={len(d)}"})
            continue

        logger.info(f"[{finding}] N={len(d)} | εκδοχές: {', '.join(v for v, _ in variants)} | bootstrap…")
        s2_variant, s2_label = TABLE_S2_VARIANT.get(finding, (None, None))
        s, y, c, s2, skipped = evaluate_finding(finding, pred_col, variants, d,
                                                s2_variant, s2_label)
        summary += s
        youden += y
        comp += c
        table_s2 += s2
        for r in s2:
            logger.info(f"   Table S2 [{r['Variant']}] thr={r['Threshold']}  "
                        f"Sens={r['Sensitivity (95% CI)']}  Spec={r['Specificity (95% CI)']}")
            if EXPECTED_N is not None and r["N (Exams)"] != EXPECTED_N:
                logger.warning(f"[{finding}] Table S2: N={r['N (Exams)']} ≠ EXPECTED_N={EXPECTED_N}")
                issues.append({"Finding": finding, "Study_ID": "", "Issue": "Table S2 N mismatch",
                               "Detail": f"N={r['N (Exams)']}, expected {EXPECTED_N}"})
        cohort[-1]["Skipped resamples (single class)"] = skipped
        for r in s:
            logger.info(f"   {r['Variant']:<10} prev={r['Prevalence (%)']:>6}%  AUROC={r['AUROC (95% CI)']}")

    if comp:
        hp = holm([r["p ΔAUROC"] for r in comp])
        hq = holm([r["p ΔAUPRC"] for r in comp])
        for r, a, b in zip(comp, hp, hq):
            r["Holm p ΔAUROC"] = fmt_p(a)
            r["Holm p ΔAUPRC"] = fmt_p(b)
            r["p ΔAUROC"] = fmt_p(r["p ΔAUROC"])
            r["p ΔAUPRC"] = fmt_p(r["p ΔAUPRC"])

    # ── Methods ─────────────────────────────────────────────────────────────
    methods = [("Ground truth", GT_CSV), ("Predictions", MODEL_PREDICTIONS_CSV),
               ("Threshold", THRESHOLD), ("Bootstrap", boot_type),
               ("N iterations", N_BOOTSTRAP), ("Seed", SEED),
               ("CI", f"{100 * (1 - CI_ALPHA):.0f}% percentile"),
               ("Paired design", "Ίδιο σύνολο εξετάσεων και ίδια resamples για όλες τις εκδοχές ενός finding"),
               ("p-value", "Δίπλευρο bootstrap, Phipson–Smyth (b+1)/(m+1), b = 2·min(#Δ≤0, #Δ≥0)"),
               ("Multiple comparisons", "Holm–Bonferroni σε όλες τις συγκρίσεις εκδοχών (οικογένεια)"),
               ("Youden", "Exploratory: επιλέγεται και αξιολογείται στα ίδια δεδομένα (αισιόδοξο)"),
               ("Table S2 threshold",
                f"Χαμηλότερο όριο με specificity ≥ {SPEC_TARGET:.0%} (μέγιστη sensitivity υπό τον "
                f"περιορισμό), κανόνας θετικού score ≥ όριο. Επιλέγεται μία φορά στο πλήρες δείγμα "
                f"και μένει σταθερό σε όλα τα resamples (fixed-threshold CI). In-sample επιλογή → "
                f"η απόδοση μπορεί να είναι αισιόδοξη σε νέο δείγμα."),
               ("Table S2 dashes",
                f"'{DASH}' = μετρική μη ορισμένη στο πλήρες δείγμα· 'x ({DASH})' = CI μη εκτιμήσιμο "
                f"(καμία έγκυρη bootstrap τιμή). Resamples όπου η μετρική δεν ορίζεται εξαιρούνται "
                f"από το CI και καταγράφονται στη στήλη Note.")]
    for f, (v, lab) in TABLE_S2_VARIANT.items():
        methods.append((f"Table S2 variant: {lab}", f"{f} → {v} ({dict(TASKS[f][1])[v]})"))
    if GT_MANIFEST and Path(GT_MANIFEST).exists():
        mf = json.loads(Path(GT_MANIFEST).read_text(encoding="utf-8"))
        methods.append(("GT created", mf.get("created", "")))
        for k, h in mf.get("scripts_sha256_16", {}).items():
            methods.append((f"GT script {k}", h))
        for v in mf.get("variants", []):
            methods.append((f"Definition: {v['column']}", f"{v['definition']} [{v['script']}]"))

    # ── Αρχεία ──────────────────────────────────────────────────────────────
    path = out_dir / OUTPUT_XLSX_NAME
    excl_df = pd.DataFrame(excluded_log, columns=["Study_ID", "Source"])
    if len(excl_df):
        excl_df = excl_df.groupby("Study_ID")["Source"].apply(lambda s: ", ".join(sorted(set(s)))).reset_index()
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            pd.DataFrame(summary).to_excel(w, sheet_name="Summary", index=False)
            pd.DataFrame(youden).to_excel(w, sheet_name="Youden_Exploratory", index=False)
            pd.DataFrame(table_s2).to_excel(w, sheet_name="TableS2_Spec90", index=False)
            pd.DataFrame(comp).to_excel(w, sheet_name="Variant_Comparison", index=False)
            pd.DataFrame(cohort).to_excel(w, sheet_name="Cohort", index=False)
            pd.DataFrame(issues, columns=["Finding", "Study_ID", "Issue", "Detail"]).to_excel(
                w, sheet_name="Missing_or_Unmatched", index=False)
            excl_df.to_excel(w, sheet_name="Excluded_IDs", index=False)
            pd.DataFrame(methods, columns=["Item", "Value"]).to_excel(w, sheet_name="Methods", index=False)
    except PermissionError:
        logger.error(f"Το {path} είναι ανοιχτό στο Excel — κλείσ' το και ξανατρέξε.")
        sys.exit(1)

    wb = load_workbook(path)
    hdr_fill = PatternFill("solid", fgColor="2C3E50")
    hdr_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    alt_fill = PatternFill("solid", fgColor="EEF2F7")
    for ws in wb.worksheets:
        for c in ws[1]:
            c.fill, c.font = hdr_fill, hdr_font
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for col in ws.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(width + 2, 10), 60)
        ws.freeze_panes = "B2" if ws.title in ("Summary", "Youden_Exploratory", "TableS2_Spec90",
                                                "Variant_Comparison") else "A2"
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions
    # Εναλλασσόμενο χρώμα ανά finding στο Summary
    ws = wb["Summary"]
    prev, shade = None, False
    for row in ws.iter_rows(min_row=2):
        if row[0].value != prev:
            shade, prev = not shade, row[0].value
        if shade:
            for c in row:
                c.fill = alt_fill
    wb.save(path)

    per_exam.to_csv(out_dir / "per_exam_predictions.csv", index=False)
    logger.info(f"Excel: {path}")
    logger.info(f"Per-exam CSV: {out_dir / 'per_exam_predictions.csv'}")
    logger.info("DONE")


if __name__ == "__main__":
    main()
