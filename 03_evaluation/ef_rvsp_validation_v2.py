import os
import re
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from tqdm import tqdm

# =============================================================================
# ΠΑΡΑΜΕΤΡΟΙ ΕΚΤΕΛΕΣΗΣ
# =============================================================================

GT_EF_FILE        = r"outputs/ground_truth/ef_ground_truth.csv"
GT_RVSP_FILE      = r"outputs/ground_truth/rvsp_ground_truth.csv"
PREDICTIONS_FILE  = r"outputs/predictions/predictions_raw_.csv"
OUTPUT_RESULTS    = r"outputs/evaluation/regression_results.xlsx"

# Αρχείο εξαιρέσεων (.txt: ένα ID ανά γραμμή | .csv: στήλη με IDs). None = χωρίς εξαιρέσεις
EXCLUSION_FILE    = r"data/lists/exclusion_ids.txt"
EXCLUSION_ID_COL  = None

# Στήλες ID εξέτασης
ID_COL_GT   = "exam_id"
ID_COL_PRED = "study_id"

# --- Patient IDs (για patient-level cluster bootstrap) ---
# Επιλογή 1: ξεχωριστό CSV αντιστοίχισης εξέτασης → ασθενή
PATIENT_MAP_FILE     = r"data/metadata/study_patient_mapping.csv"           # π.χ. r"data/metadata/study_patient_mapping.csv"
PATIENT_MAP_EXAM_COL = "exam_id"      # στήλη εξέτασης στο αρχείο αντιστοίχισης
# Επιλογή 2: αν PATIENT_MAP_FILE = None, η στήλη αναζητείται στα Predictions ή στα GT
PATIENT_ID_COL       = "patient_id"

# --- Ground Truth EF (output του ef_extractor.py) ---
GT_EF_COL       = "ef_exact"
GT_EF_RANGE_COL = "ef_range"      # π.χ. "55-60"
GT_EF_MOD_COL   = "ef_modifier"   # π.χ. ">55", "<60", "~50"

# 'with_fallback' : exact > range (μέσος όρος) > modifier (ο αριθμός)  ← κύρια ανάλυση
# 'exact_only'    : μόνο ακριβείς τιμές (sensitivity analysis)
EF_MODE = 'with_fallback'

# --- Ground Truth RVSP (output του rvsp_binary_extractor.py) ---
GT_RVSP_METHOD_COL = "rvsp_method"
GT_RVSP_RAW_COL    = "rvsp_raw"
GT_RVSP_NUM_COL    = "rvsp_numeric"

# Modifiers με τιμή ίση με το threshold (π.χ. "<35") εξαιρούνται από τη regression
RVSP_THRESHOLD = 35   # mmHg — ίδιο με το THRESHOLD του rvsp_binary_extractor.py

# 'exact_plus_modifiers' : exact + modifiers, εκτός από modifiers = threshold  ← κύρια ανάλυση
# 'exact_only'           : μόνο exact
RVSP_REG_MODE = 'exact_plus_modifiers'

# --- Predictions ---
PRED_EF_COL   = "ejection_fraction"
PRED_RVSP_COL = "pulmonary_artery_pressure_continuous"

N_BOOTSTRAPS = 10000
RANDOM_SEED  = 42


# =============================================================================
# ΦΟΡΤΩΣΗ & ΠΡΟΕΤΟΙΜΑΣΙΑ
# =============================================================================

def load_exclusion_list(filepath, id_col=None):
    """Φορτώνει λίστα εξαιρέσεων από .txt ή .csv. Επιστρέφει set από string IDs."""
    if filepath is None or not os.path.exists(filepath):
        return set()

    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.csv':
        df_excl = pd.read_csv(filepath, dtype=str)
        col = id_col if id_col and id_col in df_excl.columns else df_excl.columns[0]
        ids = df_excl[col].dropna().str.strip().tolist()
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            ids = [line.strip() for line in f
                   if line.strip() and not line.strip().startswith('#')]
    return set(ids)


def load_csv_with_str_id(filepath, id_col, label, extra_str_cols=()):
    """Διαβάζει CSV με τα IDs ως string (χωρίς απώλεια μηδενικών στην αρχή)."""
    header = pd.read_csv(filepath, nrows=0).columns
    dtypes = {c: str for c in (id_col, *extra_str_cols) if c in header}
    df = pd.read_csv(filepath, dtype=dtypes)
    if id_col not in df.columns:
        raise KeyError(f"Η στήλη '{id_col}' δεν υπάρχει στο αρχείο {label} ({filepath}).")
    df[id_col] = df[id_col].str.strip()
    return df[df[id_col].notna() & (df[id_col] != '')]


def apply_exclusions(df, id_col, exclusion_ids):
    if not exclusion_ids:
        return df, 0
    mask = df[id_col].isin(exclusion_ids)
    return df[~mask].copy(), int(mask.sum())


def build_patient_map(df_pred, df_gt_list):
    """Επιστρέφει (dict exam_id → patient_id, περιγραφή πηγής) ή ({}, None)."""
    if PATIENT_MAP_FILE:
        df_map = load_csv_with_str_id(PATIENT_MAP_FILE, PATIENT_MAP_EXAM_COL,
                                      "Patient map", extra_str_cols=(PATIENT_ID_COL,))
        if PATIENT_ID_COL not in df_map.columns:
            raise KeyError(f"Η στήλη '{PATIENT_ID_COL}' δεν υπάρχει στο {PATIENT_MAP_FILE}.")
        df_map = df_map.dropna(subset=[PATIENT_ID_COL])
        return dict(zip(df_map[PATIENT_MAP_EXAM_COL], df_map[PATIENT_ID_COL].str.strip())), PATIENT_MAP_FILE

    for df, id_col, name in [(df_pred, ID_COL_PRED, "Predictions"),
                             *[(g, ID_COL_GT, "Ground Truth") for g in df_gt_list]]:
        if PATIENT_ID_COL in df.columns:
            d = df.dropna(subset=[PATIENT_ID_COL])
            return dict(zip(d[id_col], d[PATIENT_ID_COL].astype(str).str.strip())), f"στήλη '{PATIENT_ID_COL}' ({name})"

    return {}, None


def merge_gt_pred(df_gt, df_pred, task, missing_issues):
    """Outer merge GT–Predictions. Καταγράφει τα unmatched και επιστρέφει τα κοινά."""
    gt = df_gt.rename(columns={ID_COL_GT: 'unified_id'})
    pr = df_pred.rename(columns={ID_COL_PRED: 'unified_id'})
    df_all = pd.merge(gt, pr, on='unified_id', how='outer', indicator=True)

    for _, row in df_all[df_all['_merge'] != 'both'].iterrows():
        issue = ("Υπάρχει μόνο στο Ground Truth" if row['_merge'] == 'left_only'
                 else "Υπάρχει μόνο στα Predictions")
        missing_issues.append({'Task': task, 'Study_ID': row['unified_id'],
                               'Issue': issue, 'Detail': ''})

    return df_all[df_all['_merge'] == 'both'].drop(columns='_merge').copy()


# =============================================================================
# EF — ΕΠΙΛΥΣΗ ΤΙΜΗΣ GT
# =============================================================================

def try_parse_float(value):
    if value is None or pd.isna(value):
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_ef_range(value):
    """'55-60' → 57.5"""
    if value is None or pd.isna(value):
        return None
    m = re.match(r'(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)', str(value).strip())
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2.0
    return None


def parse_ef_modifier(value):
    """'>55' / '<60' / '~50' → ο αριθμός"""
    if value is None or pd.isna(value):
        return None
    m = re.match(r'[^\d]*(\d+(?:\.\d+)?)', str(value).strip())
    return float(m.group(1)) if m else None


def resolve_ef_value(row):
    """Επιστρέφει (τιμή, πηγή). Σειρά: exact > range > modifier (ανάλογα με το EF_MODE)."""
    v = try_parse_float(row.get(GT_EF_COL))
    if v is not None:
        return v, 'exact'

    v_range = parse_ef_range(row.get(GT_EF_RANGE_COL))
    v_mod = parse_ef_modifier(row.get(GT_EF_MOD_COL))

    if EF_MODE == 'exact_only':
        if v_range is not None:
            return None, 'range_excluded'
        if v_mod is not None:
            return None, 'modifier_excluded'
        return None, 'not_found'

    if v_range is not None:
        return v_range, 'range'
    if v_mod is not None:
        return v_mod, 'modifier'
    return None, 'not_found'


# =============================================================================
# RVSP — ΕΠΙΛΟΓΗ ΤΙΜΗΣ ΓΙΑ REGRESSION
# =============================================================================

def resolve_rvsp_reg_source(method, numeric):
    """Επιστρέφει (τιμή ή None, πηγή/αιτία)."""
    if numeric is None or pd.isna(numeric):
        return None, f'no_numeric ({method})'

    if method == 'exact':
        return float(numeric), 'exact'

    if method == 'modifier':
        if RVSP_REG_MODE == 'exact_only':
            return None, 'modifier_excluded'
        if float(numeric) == RVSP_THRESHOLD:
            return None, 'modifier_at_threshold_excluded'   # π.χ. "<35": όριο, όχι μέτρηση
        return float(numeric), 'modifier'

    return None, f'no_numeric ({method})'


# =============================================================================
# ΜΕΤΡΙΚΕΣ — REGRESSION ΜΕ PATIENT-LEVEL CLUSTER BOOTSTRAP
# =============================================================================

def ci(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return (np.nan, np.nan)
    return (np.percentile(arr, 2.5), np.percentile(arr, 97.5))


def _reg_metrics(yt, yp):
    err = yt - yp
    mae = np.mean(np.abs(err))
    rmse = np.sqrt(np.mean(err ** 2))
    me = np.mean(yp - yt)          # Mean Error (bias): Pred − GT, θετικό = υπερεκτίμηση
    ss_tot = np.sum((yt - yt.mean()) ** 2)
    r2 = 1 - np.sum(err ** 2) / ss_tot if ss_tot > 0 else np.nan
    return mae, rmse, r2, me


def evaluate_regression(df, gt_col, pred_col, metric_name):
    """Point estimates + 95% CI με patient-level cluster bootstrap.
    Σε κάθε επανάληψη γίνεται δειγματοληψία ΑΣΘΕΝΩΝ με επανάθεση και
    συμπεριλαμβάνονται όλες οι εξετάσεις κάθε επιλεγμένου ασθενή."""
    df_valid = df[df[gt_col].notna() & df[pred_col].notna()].copy()
    if len(df_valid) < 2:
        return None, df_valid, "Ανεπαρκή δεδομένα για regression."

    y_true = df_valid[gt_col].astype(float).values
    y_pred = df_valid[pred_col].astype(float).values

    # Ομαδοποίηση εξετάσεων ανά ασθενή
    codes, uniques = pd.factorize(df_valid['patient_id'])
    n_patients = len(uniques)
    order = np.argsort(codes, kind='stable')
    counts = np.bincount(codes, minlength=n_patients)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    patient_rows = [order[s:s + c] for s, c in zip(starts, counts)]

    rng = np.random.RandomState(RANDOM_SEED)
    mae_l, rmse_l, r2_l, me_l = [], [], [], []
    for _ in tqdm(range(N_BOOTSTRAPS), desc=f"  Bootstrapping {metric_name}", leave=False):
        sampled = rng.randint(0, n_patients, n_patients)
        idx = np.concatenate([patient_rows[p] for p in sampled])
        mae, rmse, r2, me = _reg_metrics(y_true[idx], y_pred[idx])
        mae_l.append(mae)
        rmse_l.append(rmse)
        r2_l.append(r2)
        me_l.append(me)

    res = {
        "Metric_Name": metric_name,
        "N_Exams": len(df_valid),
        "N_Patients": n_patients,
        "MAE":  mean_absolute_error(y_true, y_pred),           "MAE_CI":  ci(mae_l),
        "ME":   np.mean(y_pred - y_true),                      "ME_CI":   ci(me_l),
        "RMSE": np.sqrt(mean_squared_error(y_true, y_pred)),   "RMSE_CI": ci(rmse_l),
        "R2":   r2_score(y_true, y_pred),                      "R2_CI":   ci(r2_l),
        "GT_Mean": y_true.mean(),   "GT_Std": y_true.std(),
        "Pred_Mean": y_pred.mean(), "Pred_Std": y_pred.std(),
    }
    return res, df_valid, None


def print_regression(res, err):
    if not res:
        print(f" ⚠ {err}")
        return
    print(f" Αξιολογήθηκαν : {res['N_Exams']} εξετάσεις από {res['N_Patients']} ασθενείς")
    for k, label in [("MAE", "MAE "), ("ME", "ME  "), ("RMSE", "RMSE"), ("R2", "R²  ")]:
        print(f" {label}          : {res[k]:.3f}  (95% CI: {res[k+'_CI'][0]:.3f} – {res[k+'_CI'][1]:.3f})")
    print("   (ME = Mean Error, Pred − GT· θετικό = υπερεκτίμηση)")


def fmt_ci(c):
    return f"[{c[0]:.3f}, {c[1]:.3f}]"


# =============================================================================
# MAIN
# =============================================================================

def run_evaluation():
    print("=" * 70)
    print(" EchoPrime — Combined Regression Evaluator v6 (EF & RVSP)")
    print("=" * 70)
    print(f" EF_MODE = {EF_MODE} | RVSP_REG_MODE = {RVSP_REG_MODE} | RVSP_THRESHOLD = {RVSP_THRESHOLD} mmHg")

    # ---------------------------------------------------------------- 1. Φόρτωση
    try:
        df_gt_ef   = load_csv_with_str_id(GT_EF_FILE, ID_COL_GT, "GT EF", (PATIENT_ID_COL,))
        df_gt_rvsp = load_csv_with_str_id(GT_RVSP_FILE, ID_COL_GT, "GT RVSP", (PATIENT_ID_COL,))
        df_pred    = load_csv_with_str_id(PREDICTIONS_FILE, ID_COL_PRED, "Predictions", (PATIENT_ID_COL,))
        patient_map, patient_src = build_patient_map(df_pred, [df_gt_ef, df_gt_rvsp])
    except FileNotFoundError as e:
        print(f"\n[ΣΦΑΛΜΑ] Το αρχείο δεν βρέθηκε: {e.filename}")
        return
    except KeyError as e:
        print(f"\n[ΣΦΑΛΜΑ] {e}")
        return

    for col in [PRED_EF_COL, PRED_RVSP_COL]:
        if col not in df_pred.columns:
            print(f"[ΣΦΑΛΜΑ] Η στήλη '{col}' δεν υπάρχει στα Predictions.")
            return
        df_pred[col] = pd.to_numeric(df_pred[col], errors='coerce')

    # Η στήλη patient_id προστίθεται μετά το merge από το map (αποφυγή διπλών στηλών)
    for df in (df_gt_ef, df_gt_rvsp, df_pred):
        if PATIENT_ID_COL in df.columns:
            df.drop(columns=PATIENT_ID_COL, inplace=True)

    print(f"\nΔιαβάστηκαν:")
    print(f"  GT EF        : {len(df_gt_ef)} εξετάσεις")
    print(f"  GT RVSP      : {len(df_gt_rvsp)} εξετάσεις")
    print(f"  Predictions  : {len(df_pred)} εξετάσεις")

    if patient_src:
        bootstrap_type = "Patient-level cluster bootstrap"
        print(f"  Patient IDs  : {len(set(patient_map.values()))} ασθενείς από {patient_src}")
    else:
        bootstrap_type = "Exam-level bootstrap (patient IDs not available)"
        print(f"  ⚠ Δεν βρέθηκαν patient IDs — κάθε εξέταση θεωρείται ξεχωριστός ασθενής.")

    # ---------------------------------------------------------------- 2. Exclusions
    exclusion_ids = load_exclusion_list(EXCLUSION_FILE, EXCLUSION_ID_COL)
    excl_presence = None
    if exclusion_ids:
        excl_presence = pd.DataFrame({'Excluded_Study_ID': sorted(exclusion_ids)})
        excl_presence['In_GT_EF']   = excl_presence['Excluded_Study_ID'].isin(set(df_gt_ef[ID_COL_GT]))
        excl_presence['In_GT_RVSP'] = excl_presence['Excluded_Study_ID'].isin(set(df_gt_rvsp[ID_COL_GT]))
        excl_presence['In_Pred']    = excl_presence['Excluded_Study_ID'].isin(set(df_pred[ID_COL_PRED]))

        df_gt_ef,   n_ef   = apply_exclusions(df_gt_ef,   ID_COL_GT,   exclusion_ids)
        df_gt_rvsp, n_rvsp = apply_exclusions(df_gt_rvsp, ID_COL_GT,   exclusion_ids)
        df_pred,    n_pred = apply_exclusions(df_pred,    ID_COL_PRED, exclusion_ids)
        print(f"  Exclusion list: {len(exclusion_ids)} IDs → εξαιρέθηκαν "
              f"{n_ef} (GT EF), {n_rvsp} (GT RVSP), {n_pred} (Pred)")
    elif EXCLUSION_FILE is not None:
        print("  Exclusion list: (κενό ή δεν βρέθηκε το αρχείο)")

    missing_issues = []

    def attach_patients(df, task):
        df['patient_id'] = df['unified_id'].map(patient_map)
        n_missing = int(df['patient_id'].isna().sum())
        if patient_src and n_missing:
            print(f"  ⚠ {task}: {n_missing} εξετάσεις χωρίς patient ID → θεωρούνται ξεχωριστοί ασθενείς")
        df['patient_id'] = df['patient_id'].fillna('exam_' + df['unified_id'])
        return df

    # ================================================================ EF
    df_ef = merge_gt_pred(df_gt_ef, df_pred, 'EF', missing_issues)
    df_ef = attach_patients(df_ef, 'EF')
    resolved = df_ef.apply(resolve_ef_value, axis=1, result_type='expand')
    df_ef['gt_ef'] = pd.to_numeric(resolved[0], errors='coerce')
    df_ef['ef_source'] = resolved[1]
    df_ef['pred_ef'] = df_ef[PRED_EF_COL]

    for _, row in df_ef[df_ef['gt_ef'].isna()].iterrows():
        missing_issues.append({'Task': 'EF', 'Study_ID': row['unified_id'],
                               'Issue': 'GT EF δεν χρησιμοποιήθηκε', 'Detail': row['ef_source']})
    for _, row in df_ef[df_ef['gt_ef'].notna() & df_ef['pred_ef'].isna()].iterrows():
        missing_issues.append({'Task': 'EF', 'Study_ID': row['unified_id'],
                               'Issue': 'Λείπει πρόβλεψη EF', 'Detail': ''})

    print(f"\n[{' EF (Κλάσμα Εξώθησης) ':^66}]")
    print("-" * 70)
    print(f" Κοινές (matched) εξετάσεις: {len(df_ef)}")
    res_ef, df_ef_valid, err_ef = evaluate_regression(df_ef, 'gt_ef', 'pred_ef', 'Ejection Fraction (%)')
    print_regression(res_ef, err_ef)

    # ================================================================ RVSP
    df_rv = merge_gt_pred(df_gt_rvsp, df_pred, 'RVSP', missing_issues)
    df_rv = attach_patients(df_rv, 'RVSP')
    df_rv['gt_rvsp_num'] = pd.to_numeric(df_rv[GT_RVSP_NUM_COL], errors='coerce')
    df_rv[GT_RVSP_METHOD_COL] = df_rv[GT_RVSP_METHOD_COL].fillna('not_found')
    df_rv['pred_rvsp'] = df_rv[PRED_RVSP_COL]

    reg = df_rv.apply(lambda r: resolve_rvsp_reg_source(r[GT_RVSP_METHOD_COL], r['gt_rvsp_num']),
                      axis=1, result_type='expand')
    df_rv['gt_rvsp'] = pd.to_numeric(reg[0], errors='coerce')
    df_rv['rvsp_source'] = reg[1]

    for _, row in df_rv[df_rv['gt_rvsp'].isna()].iterrows():
        raw = row.get(GT_RVSP_RAW_COL)
        missing_issues.append({'Task': 'RVSP', 'Study_ID': row['unified_id'],
                               'Issue': f"GT RVSP δεν χρησιμοποιήθηκε ({row['rvsp_source']})",
                               'Detail': '' if pd.isna(raw) else str(raw)})
    for _, row in df_rv[df_rv['gt_rvsp'].notna() & df_rv['pred_rvsp'].isna()].iterrows():
        missing_issues.append({'Task': 'RVSP', 'Study_ID': row['unified_id'],
                               'Issue': 'Λείπει πρόβλεψη RVSP', 'Detail': ''})

    print(f"\n[{' RVSP (Πίεση Δεξιάς Κοιλίας) ':^66}]")
    print("-" * 70)
    print(f" Κοινές (matched) εξετάσεις: {len(df_rv)}")
    res_rv, df_rv_valid, err_rv = evaluate_regression(df_rv, 'gt_rvsp', 'pred_rvsp', 'RVSP (mmHg)')
    print_regression(res_rv, err_rv)

    # ================================================================ EXCEL
    print("\n" + "=" * 70)
    print(" ΑΠΟΘΗΚΕΥΣΗ ΑΠΟΤΕΛΕΣΜΑΤΩΝ")
    print("=" * 70)

    rows = []

    def add(metric, stat, value, ci_str=""):
        rows.append({"Metric": metric, "Statistic": stat, "Value": value, "95% CI": ci_str})

    for res in [res_ef, res_rv]:
        if res:
            name = res['Metric_Name']
            add(name, "N (Exams)",    res['N_Exams'])
            add(name, "N (Patients)", res['N_Patients'])
            add(name, "MAE",  round(res['MAE'], 3),  fmt_ci(res['MAE_CI']))
            add(name, "Mean Error (Pred − GT)", round(res['ME'], 3), fmt_ci(res['ME_CI']))
            add(name, "RMSE", round(res['RMSE'], 3), fmt_ci(res['RMSE_CI']))
            add(name, "R²",   round(res['R2'], 3),   fmt_ci(res['R2_CI']))
            add(name, "GT Mean ± Std",   f"{res['GT_Mean']:.2f} ± {res['GT_Std']:.2f}")
            add(name, "Pred Mean ± Std", f"{res['Pred_Mean']:.2f} ± {res['Pred_Std']:.2f}")

    if res_ef:
        src_counts = df_ef_valid['ef_source'].value_counts()
        for src in ['exact', 'range', 'modifier']:
            if src_counts.get(src, 0) > 0:
                add("EF Source Breakdown", f"from_{src}", int(src_counts[src]))

    add("Bootstrap Method", "Type", bootstrap_type)
    add("Bootstrap Method", "N iterations", N_BOOTSTRAPS)
    add("Bootstrap Method", "Seed", RANDOM_SEED)

    df_summary = pd.DataFrame(rows)

    if res_ef:
        d_ef = df_ef_valid[['unified_id', 'patient_id', 'gt_ef', 'pred_ef', 'ef_source']].copy()
        d_ef.columns = ['Study_ID', 'Patient_ID', 'GT_EF', 'Pred_EF', 'EF_Source']
        d_ef['Signed_Error'] = (d_ef['Pred_EF'] - d_ef['GT_EF']).round(2)   # Pred − GT
        d_ef['Abs_Error'] = (d_ef['GT_EF'] - d_ef['Pred_EF']).abs().round(2)

    if res_rv:
        d_rv = df_rv_valid[['unified_id', 'patient_id', 'gt_rvsp', 'pred_rvsp',
                            'rvsp_source', GT_RVSP_RAW_COL]].copy()
        d_rv.columns = ['Study_ID', 'Patient_ID', 'GT_RVSP', 'Pred_RVSP', 'RVSP_Source', 'GT_Raw']
        d_rv['Signed_Error'] = (d_rv['Pred_RVSP'] - d_rv['GT_RVSP']).round(2)   # Pred − GT
        d_rv['Abs_Error'] = (d_rv['GT_RVSP'] - d_rv['Pred_RVSP']).abs().round(2)

    df_missing = pd.DataFrame(missing_issues, columns=['Task', 'Study_ID', 'Issue', 'Detail'])

    out_dir = os.path.dirname(OUTPUT_RESULTS)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_RESULTS, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name='Summary Metrics', index=False)
        if res_ef:
            d_ef.to_excel(writer, sheet_name='Details_EF', index=False)
        if res_rv:
            d_rv.to_excel(writer, sheet_name='Details_RVSP', index=False)
        if not df_missing.empty:
            df_missing.to_excel(writer, sheet_name='Missing_or_Unmatched', index=False)
        if excl_presence is not None:
            excl_presence.to_excel(writer, sheet_name='Excluded_IDs', index=False)

    print(f" ✓ Το Excel αποθηκεύτηκε επιτυχώς στο:\n   {OUTPUT_RESULTS}\n")


if __name__ == '__main__':
    run_evaluation()
