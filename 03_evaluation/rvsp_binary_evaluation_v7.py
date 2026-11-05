"""
RVSP Binary Evaluation Script (v7)
==================================
Binary αξιολόγηση της πρόβλεψης RVSP του EchoPrime: elevated (≥35 mmHg, label=1)
vs normal (<35 mmHg, label=0) — ΟΛΕΣ οι εκδοχές GT σε ένα τρέξιμο, όπως το
evaluate_binary_findings.py για τα binary findings.

ΕΚΔΟΧΕΣ GT (από το rvsp_ground_truth.csv του rvsp_binary_extractor.py)
  all_methods  : κάθε εξέταση με rvsp_label (exact, modifier, range, qualitative)
                 — ο ορισμός του v6
  exact_only   : μόνο εξετάσεις με rvsp_method == 'exact' (αριθμητική τιμή RVSP)
                 — ο ορισμός του v5
  Νέα εκδοχή = μία γραμμή στο VARIANTS (π.χ. exact + modifier).

v7 ΑΛΛΑΓΕΣ (vs v6)
  - Όλες οι εκδοχές σε ένα τρέξιμο, με κοινό Excel.
  - Variant_Comparison: ΔAUROC / ΔAUPRC (εκδοχή − αναφορά) με 95% CI και
    bootstrap p-value. Οι εκδοχές έχουν ΔΙΑΦΟΡΕΤΙΚΟ σύνολο εξετάσεων
    (το exact_only είναι υποσύνολο), οπότε η σύγκριση γίνεται με ΚΟΙΝΑ
    resamples ασθενών: σε κάθε επανάληψη επιλέγονται ασθενείς από την ένωση
    και κάθε εκδοχή υπολογίζεται στις δικές της εξετάσεις αυτών των ασθενών.
    Έτσι η συσχέτιση λόγω κοινών εξετάσεων λαμβάνεται υπόψη στο CI του Δ.
  - Bootstrap με βάρη ανά εξέταση (ίδιο αποτέλεσμα με την αντιγραφή γραμμών,
    πολύ γρηγορότερο). Τα CI κάθε εκδοχής προκύπτουν από resampling των
    ασθενών της ΙΔΙΑΣ της εκδοχής, με seed 42 — για την all_methods τα
    αποτελέσματα ταυτίζονται με του v6.
  - Threshold optimization, confusion matrix PNG και GT source breakdown
    ανά εκδοχή.

  Ίδια με το v6: exclusion list, patient map, label consistency check (exact),
  implausible flag (exact, 10–120 mmHg — flagged, όχι excluded), όριο 35 mmHg
  στο continuous output του μοντέλου.

ΣΗΜΕΙΩΣΗ: τα βέλτιστα όρια του Threshold_Optimization επιλέγονται και
αξιολογούνται στα ίδια δεδομένα → exploratory, όχι validated operating points.

Output (στο OUTPUT_DIR):
  - rvsp_binary_evaluation_v7.xlsx
  - rvsp_confusion_matrix_<εκδοχή>.png
  - rvsp_binary_labels_v7.csv
"""

import sys
import logging
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from sklearn.metrics import roc_curve

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import seaborn as sns
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False
    print("[WARNING] matplotlib/seaborn not installed — confusion matrix PNG unavailable")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

GT_CSV = r"outputs/ground_truth/rvsp_ground_truth.csv"
MODEL_PREDICTIONS_CSV = r"outputs/predictions/predictions_raw_.csv"
OUTPUT_DIR = r"outputs/evaluation/rvsp_binary"
OUTPUT_XLSX_NAME = "rvsp_binary_evaluation_v7.xlsx"

# Exclusion list: TXT με 1 exam_id ανά γραμμή (# = σχόλιο). None = χωρίς exclusion.
EXCLUSION_FILE = r"data/lists/exclusion_ids.txt"

# Αντιστοίχιση εξέτασης → ασθενή (Excel ή CSV). None = exam-level bootstrap.
PATIENT_MAP_FILE = r"data/metadata/study_patient_mapping.csv"
PATIENT_MAP_SHEET = 0                 # μόνο για Excel
PATIENT_MAP_EXAM_COL = "exam_id"
PATIENT_MAP_PATIENT_COL = "patient_id"

# Στήλες
GT_ID_COL = "exam_id"
PRED_ID_COL = "study_id"
PRED_SCORE_COL = "pulmonary_artery_pressure_continuous"

THRESHOLD = 35.0          # ≥35 mmHg → label=1
CLINICAL_MIN = 10.0       # sanity filter (μόνο exact)
CLINICAL_MAX = 120.0

N_BOOTSTRAP = 10_000
SEED = 42
CI_ALPHA = 0.05

# ── ΕΚΔΟΧΕΣ GT ──────────────────────────────────────────────────────────────
# (όνομα, rvsp_method που περιλαμβάνονται — None = όλα, περιγραφή)
# Η ΠΡΩΤΗ εκδοχή είναι η αναφορά στη Variant_Comparison (Δ = άλλη − πρώτη).
VARIANTS = [
    ("all_methods", None,      "Κάθε εξέταση με rvsp_label (exact, modifier, range, qualitative) — ορισμός v6"),
    ("exact_only",  {"exact"}, "Μόνο εξετάσεις με αριθμητική τιμή RVSP (rvsp_method = exact) — ορισμός v5"),
]

THRESHOLD_STRATEGIES = [
    {"name": "Youden's J Index", "method": "youden",
     "description": "Maximizes (Sensitivity + Specificity − 1)"},
    {"name": "Sensitivity ≥ 90%", "method": "sensitivity_ge", "target": 0.90,
     "description": "Highest threshold maintaining Sensitivity ≥ 90%"},
    {"name": "Sensitivity ≥ 95%", "method": "sensitivity_ge", "target": 0.95,
     "description": "Highest threshold maintaining Sensitivity ≥ 95%"},
    {"name": "Specificity ≥ 90%", "method": "specificity_ge", "target": 0.90,
     "description": "Lowest threshold maintaining Specificity ≥ 90%"},
    {"name": "Specificity ≥ 95%", "method": "specificity_ge", "target": 0.95,
     "description": "Lowest threshold maintaining Specificity ≥ 95%"},
]

METRIC_KEYS = ["sensitivity", "specificity", "ppv", "npv", "accuracy", "f1"]
METRIC_LABELS = ["Sensitivity", "Specificity", "PPV", "NPV", "Accuracy", "F1 Score"]


# =============================================================================
# HELPERS
# =============================================================================

def normalize_id(x):
    """ID ως καθαρό string (χωρίς κενά και χωρίς '.0' από Excel/float)."""
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
    if filepath is None:
        return set()
    path = Path(filepath)
    if not path.exists():
        logger.warning(f"Exclusion file not found: {filepath} — proceeding without exclusions")
        return set()
    excluded = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                excluded.add(normalize_id(line))
    logger.info(f"Exclusion list: {len(excluded):,} IDs")
    return excluded


def dedupe(df, id_col, source, issues):
    dup_mask = df[id_col].duplicated(keep="first")
    if dup_mask.any():
        for sid in df.loc[dup_mask, id_col].unique():
            issues.append({"Task": "RVSP_binary", "Study_ID": sid,
                           "Issue": f"Duplicate ID in {source}",
                           "Detail": "Kept first occurrence"})
        logger.warning(f"{source}: {dup_mask.sum()} διπλές γραμμές — κρατιέται η πρώτη")
        df = df[~dup_mask].copy()
    return df


def fmt_ci(point, ci, d=4):
    if point is None or pd.isna(point):
        return "N/A"
    lo, hi = ci
    if pd.isna(lo):
        return f"{point:.{d}f}"
    return f"{point:.{d}f} ({lo:.{d}f}-{hi:.{d}f})"


def fmt_p(p):
    if p is None or pd.isna(p):
        return "N/A"
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"


# =============================================================================
# STEP 1 — LOAD  (ίδιο με v6)
# =============================================================================

def load_ground_truth(excluded, issues, excluded_log):
    df = read_table(GT_CSV)
    required = [GT_ID_COL, "rvsp_label", "rvsp_method", "rvsp_raw", "rvsp_numeric"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.error(f"Λείπουν στήλες στο GT: {missing}. Διαθέσιμες: {list(df.columns)}")
        sys.exit(1)

    df = df[required].copy()
    df[GT_ID_COL] = df[GT_ID_COL].apply(normalize_id)
    df = df.dropna(subset=[GT_ID_COL])
    df["rvsp_label"] = pd.to_numeric(df["rvsp_label"], errors="coerce")
    df["rvsp_numeric"] = pd.to_numeric(df["rvsp_numeric"], errors="coerce")
    df["rvsp_method"] = df["rvsp_method"].fillna("").str.strip()
    logger.info(f"GT: {len(df)} γραμμές από {Path(GT_CSV).name}")

    df = dedupe(df, GT_ID_COL, "GT", issues)

    if excluded:
        mask = df[GT_ID_COL].isin(excluded)
        for sid in df.loc[mask, GT_ID_COL]:
            excluded_log.append({"Study_ID": sid, "Source": "GT"})
        df = df[~mask].copy()
        logger.info(f"GT: {mask.sum()} εξαιρέθηκαν (exclusion list), {len(df)} απομένουν")

    bad = df["rvsp_label"].notna() & ~df["rvsp_label"].isin([0, 1])
    if bad.any():
        logger.warning(f"GT: {bad.sum()} labels εκτός {{0,1}} — αντιμετωπίζονται ως κενά")
        df.loc[bad, "rvsp_label"] = np.nan

    return df.rename(columns={GT_ID_COL: "exam_id"})


def load_predictions(excluded, issues, excluded_log):
    df = read_table(MODEL_PREDICTIONS_CSV)
    missing = [c for c in (PRED_ID_COL, PRED_SCORE_COL) if c not in df.columns]
    if missing:
        logger.error(f"Λείπουν στήλες στα predictions: {missing}. Διαθέσιμες: {list(df.columns)}")
        sys.exit(1)

    df = df[[PRED_ID_COL, PRED_SCORE_COL]].copy()
    df[PRED_ID_COL] = df[PRED_ID_COL].apply(normalize_id)
    df = df.dropna(subset=[PRED_ID_COL])
    df["rvsp_predicted"] = pd.to_numeric(df[PRED_SCORE_COL], errors="coerce")
    df = df.drop(columns=[PRED_SCORE_COL])
    logger.info(f"Predictions: {len(df)} γραμμές")

    df = dedupe(df, PRED_ID_COL, "Predictions", issues)

    if excluded:
        mask = df[PRED_ID_COL].isin(excluded)
        for sid in df.loc[mask, PRED_ID_COL]:
            excluded_log.append({"Study_ID": sid, "Source": "Predictions"})
        df = df[~mask].copy()

    return df.rename(columns={PRED_ID_COL: "exam_id"})


def load_patient_map():
    if PATIENT_MAP_FILE is None:
        logger.warning("PATIENT_MAP_FILE=None → fallback σε exam-level bootstrap")
        return None
    df = read_table(PATIENT_MAP_FILE, PATIENT_MAP_SHEET)
    for c in (PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL):
        if c not in df.columns:
            logger.error(f"Στήλη '{c}' δεν βρέθηκε στο patient map. Διαθέσιμες: {list(df.columns)}")
            sys.exit(1)
    df = df[[PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL]].copy()
    df[PATIENT_MAP_EXAM_COL] = df[PATIENT_MAP_EXAM_COL].apply(normalize_id)
    df[PATIENT_MAP_PATIENT_COL] = df[PATIENT_MAP_PATIENT_COL].apply(normalize_id)
    df = df.dropna().drop_duplicates(subset=PATIENT_MAP_EXAM_COL)
    logger.info(f"Patient map: {len(df)} εξετάσεις → {df[PATIENT_MAP_PATIENT_COL].nunique()} ασθενείς")
    return dict(zip(df[PATIENT_MAP_EXAM_COL], df[PATIENT_MAP_PATIENT_COL]))


# =============================================================================
# STEP 2 — MERGE & CHECKS  (ίδιο με v6 + στήλες εκδοχών)
# =============================================================================

def build_evaluation_set(gt, pred, patient_map, issues):
    labeled = gt[gt["rvsp_label"].notna()].copy()
    unlabeled = gt[gt["rvsp_label"].isna()]
    pred_ids = set(pred["exam_id"])
    gt_ids = set(gt["exam_id"])

    for _, r in unlabeled[unlabeled["exam_id"].isin(pred_ids)].iterrows():
        issues.append({"Task": "RVSP_binary", "Study_ID": r["exam_id"],
                       "Issue": "No GT label",
                       "Detail": f"rvsp_method={r['rvsp_method'] or 'empty'}"})
    for sid in sorted(pred_ids - gt_ids):
        issues.append({"Task": "RVSP_binary", "Study_ID": sid,
                       "Issue": "Prediction without GT row", "Detail": ""})

    merged = labeled.merge(pred, on="exam_id", how="left", indicator=True)

    no_pred = merged["_merge"] == "left_only"
    for sid in merged.loc[no_pred, "exam_id"]:
        issues.append({"Task": "RVSP_binary", "Study_ID": sid,
                       "Issue": "No prediction", "Detail": "GT label exists"})
    nan_pred = (~no_pred) & merged["rvsp_predicted"].isna()
    for sid in merged.loc[nan_pred, "exam_id"]:
        issues.append({"Task": "RVSP_binary", "Study_ID": sid,
                       "Issue": "Prediction is NaN", "Detail": PRED_SCORE_COL})

    ev = merged[~no_pred & ~nan_pred].drop(columns="_merge").copy().reset_index(drop=True)
    ev["rvsp_label"] = ev["rvsp_label"].astype(int)

    if patient_map is not None:
        ev["patient_id"] = ev["exam_id"].map(patient_map)
        unmapped = ev["patient_id"].isna()
        for sid in ev.loc[unmapped, "exam_id"]:
            issues.append({"Task": "RVSP_binary", "Study_ID": sid,
                           "Issue": "No patient mapping",
                           "Detail": "Treated as its own cluster"})
        if unmapped.any():
            logger.warning(f"{unmapped.sum()} εξετάσεις χωρίς patient mapping — "
                           f"θεωρούνται ξεχωριστοί ασθενείς")
        ev.loc[unmapped, "patient_id"] = "EXAM_" + ev.loc[unmapped, "exam_id"]
    else:
        ev["patient_id"] = ev["exam_id"]

    is_exact = ev["rvsp_method"] == "exact"
    ev["rvsp_implausible"] = (
        is_exact & ev["rvsp_numeric"].notna()
        & ((ev["rvsp_numeric"] < CLINICAL_MIN) | (ev["rvsp_numeric"] > CLINICAL_MAX))
    ).astype(int)
    if ev["rvsp_implausible"].sum():
        logger.warning(f"{ev['rvsp_implausible'].sum()} exact τιμές εκτός "
                       f"[{CLINICAL_MIN}-{CLINICAL_MAX}] mmHg — flagged, NOT excluded")

    ev["pred_label"] = (ev["rvsp_predicted"] >= THRESHOLD).astype(int)
    ev["correct"] = (ev["pred_label"] == ev["rvsp_label"]).astype(int)

    # Σε ποιες εκδοχές ανήκει κάθε εξέταση
    for name, methods, _ in VARIANTS:
        ev[f"in_{name}"] = (1 if methods is None else ev["rvsp_method"].isin(methods).astype(int))

    logger.info(f"Evaluation set (ένωση εκδοχών): {len(ev)} εξετάσεις, "
                f"{ev['patient_id'].nunique()} ασθενείς")
    return ev


def label_consistency_check(gt):
    """Για τα exact: rvsp_label πρέπει να ισούται με (rvsp_numeric ≥ THRESHOLD)."""
    ex = gt[(gt["rvsp_method"] == "exact") & gt["rvsp_numeric"].notna()
            & gt["rvsp_label"].notna()].copy()
    ex["expected_label"] = (ex["rvsp_numeric"] >= THRESHOLD).astype(int)
    bad = ex[ex["rvsp_label"].astype(int) != ex["expected_label"]]
    if len(bad):
        logger.warning(f"⚠ {len(bad)} exact εξετάσεις με label ασυνεπές με το "
                       f"rvsp_numeric (όριο ≥{THRESHOLD})")
    else:
        logger.info(f"Label consistency check: OK ({len(ex)} exact εξετάσεις)")
    out = bad[["exam_id", "rvsp_raw", "rvsp_numeric", "rvsp_label", "expected_label"]]
    return out.rename(columns={"exam_id": "Study_ID", "rvsp_label": "GT_label"}), len(ex)


# =============================================================================
# STEP 3 — WEIGHTED METRICS & BOOTSTRAP
# w = πόσες φορές μετράει κάθε εξέταση στο resample (0, 1, 2, …)
# =============================================================================

class ScoreIndex:
    """Ταξινόμηση των scores μία φορά, με ομαδοποίηση ισοβαθμιών."""

    def __init__(self, scores):
        self.order = np.argsort(-scores, kind="mergesort")
        s_sorted = scores[self.order]
        new_grp = np.r_[True, s_sorted[1:] != s_sorted[:-1]] if len(scores) else np.array([], bool)
        self.group = np.cumsum(new_grp) - 1
        self.n_groups = int(self.group[-1]) + 1 if len(scores) else 0


def weighted_auc_ap(y, w, idx):
    """AUROC (ισοβαθμίες = 0.5) και AUPRC (average precision, ορισμός sklearn) με βάρη."""
    yo, wo = y[idx.order], w[idx.order]
    pos_g = np.bincount(idx.group, weights=wo * (yo == 1), minlength=idx.n_groups)
    neg_g = np.bincount(idx.group, weights=wo * (yo == 0), minlength=idx.n_groups)
    P, N = pos_g.sum(), neg_g.sum()
    if P == 0 or N == 0:
        return np.nan, np.nan
    neg_below = N - np.cumsum(neg_g)
    auc = float(np.sum(pos_g * (neg_below + 0.5 * neg_g)) / (P * N))
    tp, fp = np.cumsum(pos_g), np.cumsum(neg_g)
    ap = float(np.sum(pos_g / P * (tp / np.maximum(tp + fp, 1e-12))))
    return auc, ap


def weighted_thr_metrics(y, pred, w):
    tp = float(np.sum(w * ((y == 1) & (pred == 1))))
    tn = float(np.sum(w * ((y == 0) & (pred == 0))))
    fp = float(np.sum(w * ((y == 0) & (pred == 1))))
    fn = float(np.sum(w * ((y == 1) & (pred == 0))))
    div = lambda a, b: a / b if b else np.nan
    return {"sensitivity": div(tp, tp + fn), "specificity": div(tn, tn + fp),
            "ppv": div(tp, tp + fp), "npv": div(tn, tn + fn),
            "accuracy": div(tp + tn, tp + tn + fp + fn), "f1": div(2 * tp, 2 * tp + fp + fn),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def bootstrap_weights(groups, n_iter=N_BOOTSTRAP, seed=SEED):
    """
    Generator: patient-level cluster bootstrap ως βάρη ανά εξέταση
    (= πόσες φορές επιλέχθηκε ο ασθενής της). Ίδια ακολουθία τυχαίων
    αριθμών με το bootstrap_indices του v6.
    """
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(groups)
    n = len(uniq)
    for _ in range(n_iter):
        counts = np.bincount(rng.integers(0, n, size=n), minlength=n)
        yield counts[codes].astype(float)


def ci_of(vals):
    vals = np.asarray([v for v in vals if not np.isnan(v)])
    if not len(vals):
        return (np.nan, np.nan)
    return (float(np.percentile(vals, 100 * CI_ALPHA / 2)),
            float(np.percentile(vals, 100 * (1 - CI_ALPHA / 2))))


def boot_p(deltas):
    """Δίπλευρο bootstrap p, Phipson–Smyth: (b+1)/(m+1), b = 2·min(#Δ≤0, #Δ≥0)."""
    d = np.asarray([v for v in deltas if not np.isnan(v)])
    if not len(d):
        return np.nan
    b = 2 * min(np.sum(d <= 0), np.sum(d >= 0))
    return min(1.0, (b + 1) / (len(d) + 1))


def bootstrap_ci(y, scores, groups, thresholds, with_auc=False):
    """
    CI για μετρικές σε ΣΤΑΘΕΡΑ όρια (λίστα) + προαιρετικά AUROC/AUPRC.
    Resamples που έχουν μία μόνο κλάση παραλείπονται (όπως στο v6).
    """
    idx = ScoreIndex(scores)
    preds = [(scores >= t).astype(int) for t in thresholds]
    boot = [{k: [] for k in METRIC_KEYS} for _ in thresholds]
    auc_b, ap_b, skipped = [], [], 0
    for w in bootstrap_weights(groups):
        wp = float(np.sum(w * (y == 1)))
        if wp == 0 or wp == float(np.sum(w)):
            skipped += 1
            continue
        for b, p in zip(boot, preds):
            m = weighted_thr_metrics(y, p, w)
            for k in METRIC_KEYS:
                if not np.isnan(m[k]):
                    b[k].append(m[k])
        if with_auc:
            a, ap = weighted_auc_ap(y, w, idx)
            auc_b.append(a)
            ap_b.append(ap)
    cis = [{k: ci_of(b[k]) for k in METRIC_KEYS} for b in boot]
    auc_ci = (ci_of(auc_b), ci_of(ap_b)) if with_auc else None
    return cis, auc_ci, skipped


# =============================================================================
# STEP 4 — THRESHOLD OPTIMIZATION (ίδιο με v6)
# =============================================================================

def find_optimal_threshold(y_true, y_score, strategy):
    fpr, tpr, thresholds = roc_curve(y_true, y_score)
    spec = 1 - fpr
    best = None
    if strategy["method"] == "youden":
        best = int(np.argmax(tpr - fpr))
    elif strategy["method"] == "sensitivity_ge":
        valid = np.where(tpr >= strategy["target"])[0]
        best = int(valid[0]) if len(valid) else None        # υψηλότερο threshold
    elif strategy["method"] == "specificity_ge":
        valid = np.where(spec >= strategy["target"])[0]
        best = int(valid[-1]) if len(valid) else None       # χαμηλότερο threshold
    if best is not None and np.isfinite(thresholds[best]):
        return float(thresholds[best])
    return np.nan


# =============================================================================
# STEP 5 — ΑΞΙΟΛΟΓΗΣΗ ΕΚΔΟΧΗΣ
# =============================================================================

def evaluate_variant(name, desc, sub):
    """Όλες οι μετρικές μίας εκδοχής στις δικές της εξετάσεις."""
    y = sub["rvsp_label"].to_numpy(int)
    s = sub["rvsp_predicted"].to_numpy(float)
    g = sub["patient_id"].to_numpy()
    if len(y) == 0 or y.min() == y.max():
        logger.warning(f"[{name}] κενό σύνολο ή μία μόνο κλάση — παράλειψη")
        return None

    ones = np.ones(len(y))
    auc, ap = weighted_auc_ap(y, ones, ScoreIndex(s))

    # Όρια: κλινικό + στρατηγικές
    strategies = [{"name": f"Clinical Baseline ({THRESHOLD:.0f} mmHg)", "method": "fixed",
                   "description": f"Fixed clinical threshold: RVSP ≥ {THRESHOLD:.0f} mmHg"}]
    strategies += THRESHOLD_STRATEGIES
    thr = [THRESHOLD if st["method"] == "fixed" else find_optimal_threshold(y, s, st)
           for st in strategies]
    feasible = [not np.isnan(t) for t in thr]
    thr_ok = [t for t, f in zip(thr, feasible) if f]

    logger.info(f"[{name}] N={len(y)} | bootstrap {N_BOOTSTRAP:,}…")
    cis, (auc_ci, ap_ci), skipped = bootstrap_ci(y, s, g, thr_ok, with_auc=True)

    opt_rows, it = [], iter(cis)
    for st, t, f in zip(strategies, thr, feasible):
        row = {"Variant": name, "Strategy": st["name"], "Description": st["description"],
               "Optimal Threshold (mmHg)": round(t, 2) if f else "N/A",
               "Calibration Shift (mmHg)": round(t - THRESHOLD, 2) if f else "N/A",
               "Feasible": "Yes" if f else "No"}
        if f:
            ci = next(it)
            m = weighted_thr_metrics(y, (s >= t).astype(int), ones)
            for k, lbl in zip(METRIC_KEYS, METRIC_LABELS):
                row[f"{lbl} (95% CI)"] = fmt_ci(m[k], ci[k])
            for k in ("tp", "fp", "fn", "tn"):
                row[k.upper()] = int(m[k])
        else:
            for lbl in METRIC_LABELS:
                row[f"{lbl} (95% CI)"] = "N/A"
            for k in ("tp", "fp", "fn", "tn"):
                row[k.upper()] = "N/A"
        opt_rows.append(row)
        if st["method"] == "fixed":
            m35, ci35 = weighted_thr_metrics(y, (s >= THRESHOLD).astype(int), ones), ci

    n_pos = int(y.sum())
    summary = OrderedDict()
    summary["Variant"] = name
    summary["Definition"] = desc
    summary["N (Exams)"] = len(y)
    summary["N (Patients)"] = int(pd.Series(g).nunique())
    summary["N Positive (Elevated)"] = n_pos
    summary["N Negative (Normal)"] = len(y) - n_pos
    summary["Prevalence (%)"] = round(n_pos / len(y) * 100, 1)
    summary["Threshold (mmHg)"] = THRESHOLD
    summary["AUROC (95% CI)"] = fmt_ci(auc, auc_ci)
    summary["AUPRC (95% CI)"] = fmt_ci(ap, ap_ci)
    for k, lbl in zip(METRIC_KEYS, METRIC_LABELS):
        summary[f"{lbl} (95% CI)"] = fmt_ci(m35[k], ci35[k])
    for k in ("tp", "fp", "fn", "tn"):
        summary[k.upper()] = int(m35[k])
    summary["Skipped resamples (single class)"] = skipped

    for k in ("N (Exams)", "Prevalence (%)", "AUROC (95% CI)", "Sensitivity (95% CI)",
              "Specificity (95% CI)"):
        logger.info(f"   {k:22s}: {summary[k]}")
    return {"summary": summary, "opt": opt_rows, "auc": auc, "ap": ap,
            "y": y, "pred": (s >= THRESHOLD).astype(int)}


def compare_variants(ev, results):
    """
    Δ (εκδοχή − αναφορά) για AUROC, AUPRC, Sensitivity, Specificity στο 35 mmHg.
    Κοινά resamples ασθενών από την ΕΝΩΣΗ· κάθε εκδοχή στις δικές της εξετάσεις.
    """
    names = [n for n, _, _ in VARIANTS if n in results]
    if len(names) < 2:
        return []
    ref = names[0]
    y = ev["rvsp_label"].to_numpy(int)
    s = ev["rvsp_predicted"].to_numpy(float)
    pred = (s >= THRESHOLD).astype(int)
    masks = {n: ev[f"in_{n}"].to_numpy(bool) for n in names}
    idx = {n: ScoreIndex(s[masks[n]]) for n in names}

    deltas = {n: {"auroc": [], "auprc": [], "sensitivity": [], "specificity": []}
              for n in names[1:]}
    for w in bootstrap_weights(ev["patient_id"].to_numpy(), seed=SEED + 1):
        vals = {}
        for n in names:
            m = masks[n]
            a, ap = weighted_auc_ap(y[m], w[m], idx[n])
            tm = weighted_thr_metrics(y[m], pred[m], w[m])
            vals[n] = {"auroc": a, "auprc": ap,
                       "sensitivity": tm["sensitivity"], "specificity": tm["specificity"]}
        for n in names[1:]:
            for k in deltas[n]:
                deltas[n][k].append(vals[n][k] - vals[ref][k])

    rows = []
    for n in names[1:]:
        r_ref, r_var = results[ref], results[n]
        ones_r, ones_v = np.ones(len(r_ref["y"])), np.ones(len(r_var["y"]))
        pt_r = weighted_thr_metrics(r_ref["y"], r_ref["pred"], ones_r)
        pt_v = weighted_thr_metrics(r_var["y"], r_var["pred"], ones_v)
        point = {"auroc": r_var["auc"] - r_ref["auc"], "auprc": r_var["ap"] - r_ref["ap"],
                 "sensitivity": pt_v["sensitivity"] - pt_r["sensitivity"],
                 "specificity": pt_v["specificity"] - pt_r["specificity"]}
        row = {"Reference": ref, "Variant": n,
               "N reference": len(r_ref["y"]), "N variant": len(r_var["y"]),
               "N common exams": int((masks[ref] & masks[n]).sum())}
        for k, lbl in (("auroc", "ΔAUROC"), ("auprc", "ΔAUPRC"),
                       ("sensitivity", "ΔSensitivity @35"), ("specificity", "ΔSpecificity @35")):
            row[f"{lbl} (95% CI)"] = fmt_ci(point[k], ci_of(deltas[n][k]))
            row[f"p {lbl}"] = fmt_p(boot_p(deltas[n][k]))
        row["Resamples"] = len(deltas[n]["auroc"])
        rows.append(row)
    return rows


# =============================================================================
# STEP 6 — DESCRIPTIVE STATS
# =============================================================================

def descriptive_stats(gt, ev, n_exact_checked, n_inconsistent, bootstrap_type):
    s = OrderedDict()
    s["GT rows (after exclusion)"] = len(gt)
    s["GT rows with label"] = int(gt["rvsp_label"].notna().sum())
    s["Evaluated exams (union of variants)"] = len(ev)
    s["Evaluated patients (union)"] = int(ev["patient_id"].nunique())

    exact_vals = ev.loc[(ev["rvsp_method"] == "exact"), "rvsp_numeric"].dropna()
    s["— Exact RVSP values (evaluated set) —"] = ""
    s["N exact with numeric value"] = len(exact_vals)
    if len(exact_vals):
        q25, q75 = exact_vals.quantile([0.25, 0.75])
        s["Mean ± Std (mmHg)"] = f"{exact_vals.mean():.1f} ± {exact_vals.std():.1f}"
        s["Median [IQR] (mmHg)"] = f"{exact_vals.median():.1f} [{q25:.1f}-{q75:.1f}]"
        s["Min - Max (mmHg)"] = f"{exact_vals.min():.1f} - {exact_vals.max():.1f}"
    s["Implausible exact values (flagged)"] = int(ev["rvsp_implausible"].sum())
    s["Label consistency (exact)"] = f"{n_inconsistent} inconsistent / {n_exact_checked} checked"
    s["— Bootstrap Method —"] = ""
    s["Type"] = bootstrap_type
    s["N iterations"] = N_BOOTSTRAP
    s["Seed (per-variant CIs)"] = SEED
    s["Seed (variant comparison)"] = SEED + 1
    s["Variant comparison"] = ("Κοινά resamples ασθενών από την ένωση· κάθε εκδοχή στις "
                               "δικές της εξετάσεις· p δίπλευρο Phipson–Smyth")
    return s


def method_breakdown(ev):
    rows = []
    for name, _, _ in VARIANTS:
        sub = ev[ev[f"in_{name}"] == 1]
        if not len(sub):
            continue
        tab = sub.groupby("rvsp_method")["rvsp_label"].agg(N="size", Label_1="sum").reset_index()
        for _, r in tab.iterrows():
            rows.append({"Variant": name, "GT Source (rvsp_method)": r["rvsp_method"],
                         "N": int(r["N"]), "Label_1": int(r["Label_1"]),
                         "Label_0": int(r["N"] - r["Label_1"]),
                         "% of variant": round(r["N"] / len(sub) * 100, 1)})
        rows.append({"Variant": name, "GT Source (rvsp_method)": "TOTAL", "N": len(sub),
                     "Label_1": int(sub["rvsp_label"].sum()),
                     "Label_0": int(len(sub) - sub["rvsp_label"].sum()), "% of variant": 100.0})
    return pd.DataFrame(rows)


# =============================================================================
# STEP 7 — CONFUSION MATRIX PNG (ίδιο με v6, ανά εκδοχή)
# =============================================================================

def plot_confusion_matrix_png(y_true, y_pred, output_dir, variant, dpi=300):
    if not MPL_AVAILABLE:
        return ""
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    cm = np.array([[tn, fp], [fn, tp]])
    cm_norm = cm.astype(float) / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    labels = [f"Normal\n(<{int(THRESHOLD)})", f"Elevated\n(≥{int(THRESHOLD)})"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=labels,
                yticklabels=labels, linewidths=1.5, linecolor="white",
                annot_kws={"size": 18, "weight": "bold"},
                cbar_kws={"shrink": 0.75, "label": "Count"}, ax=axes[0])
    axes[0].set_xlabel("Predicted Label", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("True Label (Ground Truth)", fontsize=11, fontweight="bold")
    axes[0].set_title("Counts", fontsize=13, fontweight="bold")
    for i, row in enumerate([["TN", "FP"], ["FN", "TP"]]):
        for j, t in enumerate(row):
            axes[0].text(j + 0.5, i + 0.78, t, ha="center", va="center",
                         fontsize=9, color="#555555", style="italic")

    sns.heatmap(cm_norm, annot=True, fmt=".1%", cmap="Oranges", xticklabels=labels,
                yticklabels=labels, linewidths=1.5, linecolor="white", vmin=0, vmax=1,
                annot_kws={"size": 18, "weight": "bold"},
                cbar_kws={"shrink": 0.75, "label": "Proportion",
                          "format": mticker.PercentFormatter(1.0)}, ax=axes[1])
    axes[1].set_xlabel("Predicted Label", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("")
    axes[1].set_title("Row-Normalized (Specificity / Sensitivity)", fontsize=13, fontweight="bold")

    n, n_pos = len(y_true), int(y_true.sum())
    fig.suptitle(f"RVSP Binary Classification — {variant}\n"
                 f"N={n}  |  Elevated={n_pos} ({n_pos / n * 100:.1f}%)  |  "
                 f"Threshold={int(THRESHOLD)} mmHg",
                 fontsize=12, fontweight="bold", y=0.98)
    fig.subplots_adjust(top=0.85, wspace=0.35)
    out_path = str(Path(output_dir) / f"rvsp_confusion_matrix_{variant}.png")
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info(f"Confusion matrix PNG: {out_path}")
    return out_path


# =============================================================================
# STEP 8 — EXCEL OUTPUT
# =============================================================================

HEADER_FILL = PatternFill("solid", fgColor="2C3E50")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Arial", size=10)
NOTE_FONT = Font(name="Arial", size=9, italic=True, color="555555")
SECTION_FONT = Font(name="Arial", size=10, bold=True, italic=True)
LABEL1_FILL = PatternFill("solid", fgColor="FADBD8")
LABEL0_FILL = PatternFill("solid", fgColor="D5F5E3")
IMPLAUS_FILL = PatternFill("solid", fgColor="F9E79F")


def style_sheet(ws, header_row=1, max_width=45):
    for cell in ws[header_row]:
        if cell.value is not None:
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.font = BODY_FONT
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(width + 2, 10), max_width)
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)


def write_excel(path, results, comparison, desc, breakdown, ev, issues, excluded_log, consistency):
    summary_df = pd.DataFrame([r["summary"] for r in results.values()])
    opt_df = pd.DataFrame([row for r in results.values() for row in r["opt"]])
    comp_df = pd.DataFrame(comparison)

    in_cols = [f"in_{n}" for n, _, _ in VARIANTS]
    per_exam = ev[["exam_id", "patient_id", "rvsp_method", "rvsp_raw", "rvsp_numeric",
                   "rvsp_label", "rvsp_predicted", "pred_label", "correct",
                   "rvsp_implausible"] + in_cols].copy()
    per_exam["rvsp_predicted"] = per_exam["rvsp_predicted"].round(2)
    per_exam.columns = (["Study_ID", "Patient_ID", "GT_Method", "GT_Raw", "GT_Numeric",
                         "GT_Label", "Pred_RVSP", "Pred_Label", "Correct", "Implausible"]
                        + [c.replace("in_", "In_") for c in in_cols])
    per_exam = per_exam.sort_values(["GT_Label", "Pred_RVSP"], ascending=[False, False])

    issues_df = pd.DataFrame(issues, columns=["Task", "Study_ID", "Issue", "Detail"])
    excl_df = pd.DataFrame(excluded_log, columns=["Study_ID", "Source"])
    if len(excl_df):
        excl_df = (excl_df.groupby("Study_ID")["Source"]
                   .apply(lambda s: ", ".join(sorted(set(s)))).reset_index())

    rules = pd.DataFrame(
        [("Εκδοχή: " + n, d, "όλα" if m is None else ", ".join(sorted(m))) for n, m, d in VARIANTS]
        + [
            ("Πηγή label", "rvsp_label από το rvsp_binary_extractor.py, χωρίς τροποποίηση.", "—"),
            ("Όριο", f"label=1 αν RVSP ≥ {THRESHOLD:.0f} mmHg, label=0 αν < {THRESHOLD:.0f}", "—"),
            ("exact", f"Αριθμητική τιμή συγκρίνεται με το όριο {THRESHOLD:.0f}", "40 → 1  |  30 → 0"),
            ("modifier", "Label όπως το ορίζει ο extractor (το rvsp_numeric είναι το όριο του modifier)", "<35 → 0"),
            ("range", "Label όπως το ορίζει ο extractor", "—"),
            ("qualitative", "Label από περιγραφικό κείμενο, χωρίς αριθμητική τιμή", "—"),
            ("not_found / not_estimable / ambiguous", "Χωρίς label → εκτός ανάλυσης "
             "(καταγράφονται στο Missing_or_Unmatched αν υπάρχει πρόβλεψη)", "—"),
            ("Model output", f"pred_label = 1 αν {PRED_SCORE_COL} ≥ {THRESHOLD:.0f}", "—"),
        ], columns=["Type", "Rule", "Methods / Example"])

    desc_df = pd.DataFrame(list(desc.items()), columns=["Item", "Value"])

    with pd.ExcelWriter(path, engine="openpyxl") as w:
        summary_df.to_excel(w, sheet_name="Summary", index=False)
        comp_df.to_excel(w, sheet_name="Variant_Comparison", index=False)
        opt_df.to_excel(w, sheet_name="Threshold Optimization", index=False)
        breakdown.to_excel(w, sheet_name="GT Source Breakdown", index=False)
        desc_df.to_excel(w, sheet_name="Descriptive & Bootstrap", index=False)
        per_exam.to_excel(w, sheet_name="Per-Exam Labels", index=False)
        issues_df.to_excel(w, sheet_name="Missing_or_Unmatched", index=False)
        excl_df.to_excel(w, sheet_name="Excluded_IDs", index=False)
        consistency.to_excel(w, sheet_name="Label_Consistency_Check", index=False)
        rules.to_excel(w, sheet_name="Binarization Rules", index=False)

    wb = load_workbook(path)
    for ws in wb.worksheets:
        style_sheet(ws, max_width=70 if ws.title in ("Binarization Rules", "Descriptive & Bootstrap",
                                                     "Missing_or_Unmatched") else 40)
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions

    ws = wb["Per-Exam Labels"]
    cols = {c.value: c.column for c in ws[1]}
    for r in range(2, ws.max_row + 1):
        lab = ws.cell(row=r, column=cols["GT_Label"])
        lab.fill = LABEL1_FILL if lab.value == 1 else LABEL0_FILL
        imp = ws.cell(row=r, column=cols["Implausible"])
        if imp.value == 1:
            imp.fill = IMPLAUS_FILL

    ws = wb["Descriptive & Bootstrap"]
    for r in range(2, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.startswith("—"):
            ws.cell(row=r, column=1).font = SECTION_FONT

    ws = wb["Threshold Optimization"]
    note_row = ws.max_row + 2
    notes = [
        "INTERPRETATION:",
        f"• GT labels are fixed at the clinical threshold ({THRESHOLD:.0f} mmHg); "
        "only the model output threshold is optimized.",
        "• Calibration Shift = Optimal Threshold − Clinical Threshold. Negative = the model "
        "underestimates RVSP; positive = it overestimates.",
        "• Optimal thresholds are selected and evaluated on the same data, so their metrics "
        "are optimistic. They are exploratory, not validated operating points.",
        "• CIs do not include the uncertainty of threshold selection itself.",
    ]
    for i, n in enumerate(notes):
        ws.cell(row=note_row + i, column=1, value=n).font = SECTION_FONT if i == 0 else NOTE_FONT

    ws = wb["Variant_Comparison"]
    note_row = ws.max_row + 2
    for i, n in enumerate([
        "INTERPRETATION:",
        "• Δ = εκδοχή − αναφορά (πρώτη εκδοχή στο VARIANTS). Το μοντέλο είναι ίδιο· αλλάζει μόνο ο ορισμός του GT.",
        "• Οι εκδοχές δεν έχουν το ίδιο σύνολο εξετάσεων: διαφορά μπορεί να οφείλεται και στον "
        "πληθυσμό (π.χ. οι εξετάσεις με αριθμητική τιμή), όχι μόνο στο label.",
        "• CI και p από κοινά resamples ασθενών (ένωση), ώστε να λαμβάνεται υπόψη η επικάλυψη.",
    ]):
        ws.cell(row=note_row + i, column=1, value=n).font = SECTION_FONT if i == 0 else NOTE_FONT

    ws = wb["Label_Consistency_Check"]
    if ws.max_row == 1:
        ws["A3"] = "No inconsistencies: every exact label matches rvsp_numeric ≥ threshold."
        ws["A3"].font = NOTE_FONT
    for row in wb["Binarization Rules"].iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(path)
    logger.info(f"Excel output: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    logger.info("=" * 60)
    logger.info(f"RVSP BINARY EVALUATION (v7) — threshold ≥{THRESHOLD} mmHg — "
                f"{len(VARIANTS)} εκδοχές GT")
    logger.info("=" * 60)

    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    issues, excluded_log = [], []
    excluded = load_exclusion_list(EXCLUSION_FILE)

    gt = load_ground_truth(excluded, issues, excluded_log)
    pred = load_predictions(excluded, issues, excluded_log)
    patient_map = load_patient_map()
    bootstrap_type = ("Patient-level cluster bootstrap" if patient_map is not None
                      else "Exam-level bootstrap (fallback: no patient map)")

    consistency, n_checked = label_consistency_check(gt)
    ev = build_evaluation_set(gt, pred, patient_map, issues)

    results = OrderedDict()
    for name, _, desc in VARIANTS:
        sub = ev[ev[f"in_{name}"] == 1]
        r = evaluate_variant(name, desc, sub)
        if r is not None:
            results[name] = r
            plot_confusion_matrix_png(r["y"], r["pred"], out_dir, name)
    if not results:
        logger.error("Καμία εκδοχή δεν αξιολογήθηκε")
        sys.exit(1)

    logger.info("Σύγκριση εκδοχών (κοινά resamples)…")
    comparison = compare_variants(ev, results)
    for c in comparison:
        logger.info(f"   {c['Variant']} − {c['Reference']}: ΔAUROC {c['ΔAUROC (95% CI)']} "
                    f"(p={c['p ΔAUROC']})")

    desc = descriptive_stats(gt, ev, n_checked, len(consistency), bootstrap_type)
    breakdown = method_breakdown(ev)

    try:
        write_excel(str(out_dir / OUTPUT_XLSX_NAME), results, comparison, desc, breakdown,
                    ev, issues, excluded_log, consistency)
    except PermissionError:
        logger.error(f"Το {out_dir / OUTPUT_XLSX_NAME} είναι ανοιχτό στο Excel — κλείσ' το και ξανατρέξε.")
        sys.exit(1)

    csv_path = out_dir / "rvsp_binary_labels_v7.csv"
    ev[["exam_id", "patient_id", "rvsp_method", "rvsp_numeric", "rvsp_label",
        "rvsp_predicted", "pred_label", "rvsp_implausible"]
       + [f"in_{n}" for n, _, _ in VARIANTS]].to_csv(csv_path, index=False)
    logger.info(f"Binary labels CSV: {csv_path}")
    logger.info("DONE")


if __name__ == "__main__":
    main()
