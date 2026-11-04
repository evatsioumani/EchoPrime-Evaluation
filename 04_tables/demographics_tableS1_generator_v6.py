"""
Demographics Table S1 Generator — 4 cohorts (v6)
════════════════════════════════════════════════
Βασίζεται στο demographics_multicohort_generator_v5.py.

Cohorts (στήλες του Table S1):
  1) Full cohort               — όλες οι εξετάσεις (metadata ∩ predictions)
  2) LVEF subset               — ef_exact ∪ ef_range ∪ ef_modifier
  3) RVSP Estimation subset    — rvsp_numeric έγκυρος ΚΑΙ (rvsp_method == "exact" Ή modifier με τιμή ≠ 35)
  4) RVSP Classification subset— rvsp_label έγκυρο (ταξινόμηση ως προς 35 mmHg)

Input:
  - metadata_processed.xlsx   (patient metadata)
  - binary GT csv             (exam_id, status, pacemaker, ...)
  - LVEF GT csv               (exam_id, ef_exact, ef_modifier, ef_range)
  - RVSP GT csv               (exam_id, rvsp_label, rvsp_method, rvsp_raw, rvsp_numeric)
  - predictions_merged.csv    (στήλη study_id)

Output: demographics_tableS1.xlsx
  Table_1, Per_Exam_<cohort> (x4), Missing_Data

Στο τέλος του run τυπώνεται έλεγχος έναντι των αναμενόμενων N του Table S1
(EXPECTED_COUNTS). Βάλε EXPECTED_COUNTS = None για να απενεργοποιηθεί.
"""

import re
import math
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════════════════════════════════════
# ΡΥΘΜΙΣΕΙΣ — ΑΛΛΑΞΕ ΜΟΝΟ ΑΥΤΑ
# ══════════════════════════════════════════════════════════════════════════════
INPUT_XLS       = r"data/metadata/metadata_processed.xlsx"

# ── Ground Truth: 3 ξεχωριστά αρχεία (ΒΑΛΕ ΤΑ ΝΕΑ PATHS) ──
GT_BINARY_CSV   = r"outputs/ground_truth/binary/ground_truth_labels.csv"  # exam_id, status, pacemaker, ...
GT_LVEF_CSV     = r"outputs/ground_truth/ef_ground_truth.csv"          # exam_id, ef_exact, ef_modifier, ef_range
GT_RVSP_CSV     = r"outputs/ground_truth/rvsp_ground_truth.csv"          # exam_id, rvsp_label, rvsp_method, rvsp_raw, rvsp_numeric

# ── Patient IDs: ίδιο mapping με τα evaluation scripts (patient-level bootstrap) ──
# None = fallback στο όνομα ασθενή (DICOM/Report), όπως στο v5.
PATIENT_MAP_FILE        = r"data/metadata/study_patient_mapping.csv"
PATIENT_MAP_EXAM_COL    = "exam_id"
PATIENT_MAP_PATIENT_COL = "patient_id"
# Τι γίνεται με exams που ΔΕΝ υπάρχουν στο mapping:
#   "exam": κάθε exam = ξεχωριστός ασθενής (EXAM_<id>) — ΙΔΙΟ με τα evaluation scripts → ίδια N ασθενών
#   "name": ομαδοποίηση με βάση το όνομα (DICOM → Report) — μπορεί να δώσει διαφορετικό N από το evaluation
UNMAPPED_POLICY = "exam"

# ── Full cohort ──
# False: Full = metadata ∩ predictions (όπως πριν). Το script τυπώνει πόσα exam_id του binary GT
#        ταιριάζουν, ώστε να δεις αν ο ορισμός συμφωνεί με το GT.
# True : Full = metadata ∩ predictions ∩ binary GT (προαιρετικά μόνο με status ∈ BINARY_STATUS_KEEP).
FULL_RESTRICT_TO_BINARY_GT = False
BINARY_STATUS_KEEP = None        # π.χ. ["ok"] — None = όλα τα status

# ── Prediction CSV (χρειάζεται μόνο η στήλη study_id) ──
PREDICTION_CSV  = r"outputs/predictions/predictions_raw_.csv"
PRED_ID_COL     = "exam_id"   # αν δεν υπάρχει, δοκιμάζεται αυτόματα και το "study_id"

# ── Output ──
OUTPUT_UNIFIED  = r"outputs/tables/demographics_tableS1.xlsx"

# ── Exclusion List ──
EXCLUSION_LIST = []
EXCLUSION_FILE = r"data/lists/exclusion_ids.txt"

# ── Ορισμός RVSP subsets (από το rvsp ground truth) ──
#   Estimation    = rvsp_numeric έγκυρος αριθμός
#   Classification= rvsp_label μη κενό και όχι ένα από τα RVSP_INVALID_LABELS
RVSP_INVALID_LABELS = {"", "nan", "none", "na", "n/a", "unknown", "missing", "unavailable"}
# Estimation: μόνο όσα έχουν rvsp_method == "exact" (ακριβής τιμή από το report) ΚΑΙ έγκυρο rvsp_numeric
RVSP_EST_METHOD = "exact"
# + modifiers (rvsp_method == "modifier") με rvsp_numeric ≠ RVSP_THRESHOLD — ίδιος κανόνας με το
#   ef_rvsp_validation (RVSP_REG_MODE = 'exact_plus_modifiers'). False = μόνο exact.
RVSP_EST_INCLUDE_MODIFIERS = True
RVSP_THRESHOLD = 35   # mmHg — modifiers με αυτή την τιμή (π.χ. "<35") εξαιρούνται

# ── Cohort labels (όπως στο Table S1) ──
COHORTS = [
    # (short_name, label)
    ("Full",     "Full cohort"),
    ("LVEF",     "LVEF Subset"),
    ("RVSP_Est", "RVSP Estimation Subset"),
    ("RVSP_Cls", "RVSP Classification Subset"),
]

# ── Αναμενόμενα N από το Table S1 (για sanity check) ──
EXPECTED_COUNTS = {
    "Full":     {"patients": 2336, "studies": 2359},
    "LVEF":     {"patients": 2212, "studies": 2228},
    "RVSP_Est": {"patients": 856,  "studies": 862},   # exact + modifiers ≠ 35 (όπως στο evaluation)
    "RVSP_Cls": {"patients": 1375, "studies": 1384},
}

# ── Data quality: adult-only dataset ──
MIN_VALID_AGE = 18


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DATA LOADING + FILTERING
# ══════════════════════════════════════════════════════════════════════════════

def _build_exclusion_set(exclusion_list: list, exclusion_file: str | None) -> set:
    excluded = set(str(x).strip() for x in exclusion_list if x)
    if exclusion_file and Path(exclusion_file).exists():
        with open(exclusion_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    excluded.add(line)
    return excluded


def load_patient_metadata(input_path: str, excluded: set) -> pd.DataFrame:
    df = pd.read_excel(input_path, sheet_name=0, dtype=str)
    total = len(df)
    if excluded:
        df = df[~df["ExamID"].astype(str).str.strip().isin(excluded)].reset_index(drop=True)
    print(f"  Loaded: {total:,} → after exclusion: {len(df):,} "
          f"(removed {total - len(df):,})")
    return df


def _valid_mask(series: pd.Series) -> pd.Series:
    """True όπου η τιμή δεν είναι NaN / κενό / 'nan'."""
    s = series.astype(str).str.strip()
    return series.notna() & (s != "") & (s.str.lower() != "nan")


def _read_table(path: str) -> pd.DataFrame:
    """Διαβάζει CSV ή Excel. Αναγνωρίζει xlsx/xls από τα πρώτα bytes (όχι μόνο από την κατάληξη)
    και δοκιμάζει διαδοχικά κωδικοποιήσεις για CSV."""
    with open(path, "rb") as f:
        head = f.read(4)
    is_excel = (head[:2] == b"PK" or head == b"\xd0\xcf\x11\xe0"
                or str(path).lower().endswith((".xlsx", ".xlsm", ".xls")))
    if is_excel:
        print(f"    [info] Excel αρχείο — διαβάζεται με read_excel")
        return pd.read_excel(path, dtype=str)
    last_err = None
    for enc in ("utf-8-sig", "cp1253", "latin-1"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            if enc != "utf-8-sig":
                print(f"    [info] CSV encoding: {enc}")
            return df
        except UnicodeDecodeError as e:
            last_err = e
    raise last_err


def _read_gt(csv_path: str, required: list[str]) -> pd.DataFrame:
    gt = _read_table(csv_path)
    gt.columns = gt.columns.str.strip()
    print(f"  Loaded: {csv_path}  ({len(gt):,} rows)")
    for col in required:
        if col not in gt.columns:
            raise ValueError(f"Δεν βρέθηκε στήλη '{col}' στο {csv_path}. "
                             f"Στήλες: {list(gt.columns)}")
    gt["exam_id"] = gt["exam_id"].astype(str).str.strip()
    dup = gt["exam_id"].duplicated().sum()
    if dup:
        print(f"    [warn] {dup:,} διπλότυπα exam_id στο αρχείο (μετράνε μία φορά)")
    return gt


def load_ground_truth(binary_csv: str, lvef_csv: str, rvsp_csv: str) -> dict:
    """Επιστρέφει dict με σύνολα exam_ids: binary, ef, rvsp_est, rvsp_cls."""

    # ── Binary findings ──
    print("  [binary]")
    gb = _read_gt(binary_csv, ["exam_id"])
    if "status" in gb.columns:
        print("    status counts:")
        for k, v in gb["status"].fillna("<NaN>").value_counts().items():
            print(f"      {k!s:25s} {v:>6,}")
        if BINARY_STATUS_KEEP is not None:
            gb = gb[gb["status"].isin(BINARY_STATUS_KEEP)]
            print(f"    κρατήθηκαν status ∈ {BINARY_STATUS_KEEP}: {len(gb):,} rows")
    binary_ids = set(gb["exam_id"])
    print(f"    unique exam_ids: {len(binary_ids):,}")

    # ── LVEF: exact ∪ range ∪ modifier ──
    print("  [LVEF]")
    ge = _read_gt(lvef_csv, ["exam_id", "ef_exact"])
    def _ef_ids(col):
        if col not in ge.columns:
            print(f"    [warn] στήλη '{col}' δεν υπάρχει — αγνοείται")
            return set()
        return set(ge.loc[_valid_mask(ge[col]), "exam_id"])
    ef_exact, ef_range, ef_mod = _ef_ids("ef_exact"), _ef_ids("ef_range"), _ef_ids("ef_modifier")
    ef_ids = ef_exact | ef_range | ef_mod
    print(f"    exact: {len(ef_exact):,} | range: {len(ef_range):,} | modifier: {len(ef_mod):,} "
          f"→ union: {len(ef_ids):,}")

    # ── RVSP ──
    print("  [RVSP]")
    gr = _read_gt(rvsp_csv, ["exam_id", "rvsp_label", "rvsp_method", "rvsp_numeric"])
    for col in ["rvsp_label", "rvsp_method"]:
        if col in gr.columns:
            print(f"    {col} counts (top 10):")
            for k, v in gr[col].fillna("<NaN>").value_counts().head(10).items():
                print(f"      {k!s:25s} {v:>6,}")

    num_val = pd.to_numeric(gr["rvsp_numeric"].astype(str).str.replace(",", ".").str.strip(),
                            errors="coerce")
    num_ok = num_val.notna()
    meth = gr["rvsp_method"].astype(str).str.strip().str.lower()
    method_ok = meth == str(RVSP_EST_METHOD).strip().lower()
    # modifiers με τιμή ≠ threshold (π.χ. ">50")· όσα ισούνται με το threshold (π.χ. "<35") είναι όριο, όχι μέτρηση
    modifier_ok = ((meth == "modifier") & (num_val != RVSP_THRESHOLD)
                   if RVSP_EST_INCLUDE_MODIFIERS else pd.Series(False, index=gr.index))
    est_mask = num_ok & (method_ok | modifier_ok)
    n_mod_at_thr = int((num_ok & (meth == "modifier") & (num_val == RVSP_THRESHOLD)).sum())
    print(f"    rvsp_numeric έγκυρο: {int(num_ok.sum()):,} | method == '{RVSP_EST_METHOD}': "
          f"{int((num_ok & method_ok).sum()):,} | modifier με τιμή ≠ {RVSP_THRESHOLD}: "
          f"{int((num_ok & modifier_ok).sum()):,} "
          f"({'ΕΝΕΡΓΟ' if RVSP_EST_INCLUDE_MODIFIERS else 'ΑΝΕΝΕΡΓΟ'}) "
          f"| modifier = {RVSP_THRESHOLD} (εξαιρούνται): {n_mod_at_thr:,}")
    if int(method_ok.sum()) == 0:
        print(f"    [warn] καμία γραμμή με rvsp_method == '{RVSP_EST_METHOD}' — "
              f"έλεγξε την ορθογραφία στα counts παραπάνω")
    rvsp_est = set(gr.loc[est_mask, "exam_id"])

    lab = gr["rvsp_label"].astype(str).str.strip().str.lower()
    lab_ok = gr["rvsp_label"].notna() & ~lab.isin(RVSP_INVALID_LABELS)
    rvsp_cls = set(gr.loc[lab_ok, "exam_id"])

    print(f"    Estimation (rvsp_numeric): {len(rvsp_est):,} | "
          f"Classification (rvsp_label): {len(rvsp_cls):,}")
    est_not_cls = rvsp_est - rvsp_cls
    if est_not_cls:
        print(f"    [warn] {len(est_not_cls):,} exam_ids έχουν rvsp_numeric αλλά όχι έγκυρο rvsp_label "
              f"(Estimation ⊄ Classification)")

    return {"binary": binary_ids, "ef": ef_ids, "rvsp_est": rvsp_est, "rvsp_cls": rvsp_cls}


def load_prediction_ids(csv_path: str, id_col: str = "study_id") -> set:
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = df.columns.str.strip()
    if id_col not in df.columns:
        fallback = next((c for c in ("exam_id", "study_id") if c in df.columns), None)
        if fallback is None:
            raise ValueError(f"Δεν βρέθηκε στήλη '{id_col}' (ούτε exam_id/study_id) στο {csv_path}. "
                             f"Στήλες: {list(df.columns)}")
        print(f"  [info] στήλη '{id_col}' δεν βρέθηκε — χρησιμοποιείται '{fallback}'")
        id_col = fallback
    pred_ids = set(df[id_col].astype(str).str.strip())
    pred_ids.discard("")
    pred_ids.discard("nan")
    print(f"  Prediction IDs loaded: {len(pred_ids):,} unique exam_ids")
    return pred_ids


def filter_by_prediction_intersection(df: pd.DataFrame, pred_ids: set) -> pd.DataFrame:
    before = len(df)
    filtered = df[df["ExamID"].astype(str).str.strip().isin(pred_ids)].reset_index(drop=True)
    print(f"  Intersection with predictions: {len(filtered):,}/{before:,} exams retained "
          f"({before - len(filtered):,} removed — no prediction)")
    return filtered


def filter_by_ground_truth(df: pd.DataFrame, valid_exam_ids: set, task_name: str) -> pd.DataFrame:
    filtered = df[df["ExamID"].astype(str).str.strip().isin(valid_exam_ids)].reset_index(drop=True)
    print(f"  {task_name}: {len(filtered):,}/{len(df):,} exams with ground truth "
          f"(GT ids: {len(valid_exam_ids):,})")
    return filtered


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: FIELD MERGING (DICOM → Report fallback) — αμετάβλητο από v5
# ══════════════════════════════════════════════════════════════════════════════

def normalize_id(x):
    """Ίδια κανονικοποίηση με τα evaluation scripts (strip, αφαίρεση τελικού '.0')."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    s = str(x).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s if s and s.lower() != "nan" else None


def load_patient_map(path: str | None) -> dict | None:
    """exam_id → patient_id από το study_patient_mapping (CSV ή Excel)."""
    if not path:
        print("  PATIENT_MAP_FILE=None → patient IDs από ονόματα ασθενών")
        return None
    if not Path(path).exists():
        raise FileNotFoundError(f"Δεν βρέθηκε το patient map: {path}")
    df = _read_table(path)
    df.columns = df.columns.str.strip()
    for c in (PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL):
        if c not in df.columns:
            raise ValueError(f"Στήλη '{c}' δεν βρέθηκε στο patient map. Διαθέσιμες: {list(df.columns)}")
    df = df[[PATIENT_MAP_EXAM_COL, PATIENT_MAP_PATIENT_COL]].copy()
    for c in df.columns:
        df[c] = df[c].apply(normalize_id)
    df = df.dropna().drop_duplicates(subset=PATIENT_MAP_EXAM_COL)
    print(f"  Patient map: {len(df):,} exams → {df[PATIENT_MAP_PATIENT_COL].nunique():,} patients")
    return dict(zip(df[PATIENT_MAP_EXAM_COL], df[PATIENT_MAP_PATIENT_COL]))


def _is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    return False

def _first_valid(*values):
    for v in values:
        if not _is_empty(v):
            return v
    return None

def _parse_age(val) -> float | None:
    if _is_empty(val): return None
    val = str(val).strip()
    m = re.match(r"^0*(\d+)\s*([YMW]?)$", val, re.IGNORECASE)
    if m:
        num = float(m.group(1))
        unit = m.group(2).upper()
        if unit == "M": return round(num / 12, 1)
        elif unit == "W": return round(num / 52, 1)
        return num
    try:
        res = float(val)
        return None if math.isnan(res) else res
    except ValueError:
        return None

def _parse_numeric(val) -> float | None:
    if _is_empty(val): return None
    val = str(val).strip().replace(",", ".")
    val = re.sub(r"[a-zA-Zα-ωΑ-Ω²/]+$", "", val).strip()
    try:
        num = float(val)
        return None if math.isnan(num) or num <= 0 else num
    except ValueError:
        return None

def _compute_age_from_dates(birth_str, study_str) -> float | None:
    if _is_empty(birth_str) or _is_empty(study_str): return None
    try:
        birth = datetime.strptime(str(birth_str).strip()[:8], "%Y%m%d")
        study = datetime.strptime(str(study_str).strip()[:8], "%Y%m%d")
        age = (study - birth).days / 365.25
        return round(age, 1) if 0 < age < 130 else None
    except (ValueError, TypeError):
        return None

def _normalize_height(val: float | None) -> float | None:
    if val is None: return None
    if val < 3: return round(val * 100, 1)
    if 50 <= val <= 250: return round(val, 1)
    return None

def _dubois_bsa(height_cm, weight_kg):
    if height_cm is None or weight_kg is None: return None
    if height_cm <= 0 or weight_kg <= 0: return None
    return round(0.007184 * (height_cm ** 0.725) * (weight_kg ** 0.425), 2)

def _bmi(height_cm, weight_kg):
    if height_cm is None or weight_kg is None: return None
    h_m = height_cm / 100
    if h_m <= 0: return None
    return round(weight_kg / (h_m ** 2), 1)

def merge_fields(df: pd.DataFrame, patient_map: dict | None = None) -> pd.DataFrame:
    out = pd.DataFrame()
    out["ExamID"] = df["ExamID"].values

    pids, pid_sources = [], []
    ages, age_sources = [], []
    sexes, sex_sources = [], []
    weights, weight_sources = [], []
    heights, height_sources = [], []
    bsas, bsa_sources = [], []
    bmis = []

    for _, r in df.iterrows():
        # ── Patient ID ──
        p_dicom = r.get("DICOM_PatientName")
        p_report = r.get("Report_PatientName")
        exam_key = normalize_id(r.get("ExamID"))
        mapped = patient_map.get(exam_key) if patient_map is not None else None
        name = _first_valid(p_dicom, p_report)
        if mapped is not None:
            pids.append(mapped)
            pid_sources.append("Mapping")
        elif patient_map is not None and UNMAPPED_POLICY == "exam":
            pids.append(f"EXAM_{exam_key}")
            pid_sources.append("Unmapped_own_cluster")
        elif not _is_empty(name):
            pids.append(("NAME_" if patient_map is not None else "") + str(name).strip())
            pid_sources.append(
                ("Name_DICOM" if not _is_empty(p_dicom) else "Name_Report")
                if patient_map is not None
                else ("DICOM" if not _is_empty(p_dicom) else "Report")
            )
        else:
            pids.append(f"Unknown_PID_{exam_key}")
            pid_sources.append("Missing_Data")

        # ── Age ──
        a_dicom    = _parse_age(r.get("DICOM_PatientAge"))
        a_report   = _parse_age(r.get("Report_Age"))
        a_computed = _compute_age_from_dates(r.get("DICOM_PatientBirthDate"), r.get("DICOM_StudyDate"))
        age = _first_valid(a_dicom, a_report, a_computed)
        if age is not None and age < MIN_VALID_AGE: age = None
        ages.append(age)
        age_sources.append(
            "DICOM" if a_dicom is not None and age is not None
            else "Report" if a_report is not None and age is not None
            else "Computed" if a_computed is not None and age is not None
            else "MISSING"
        )

        # ── Sex (from Predicted_PatientSex column) ──
        pred_sex = str(r.get("Predicted_PatientSex", "")).strip()
        if pred_sex == "M":
            sexes.append("M"); sex_sources.append("Predicted")
        elif pred_sex == "F":
            sexes.append("F"); sex_sources.append("Predicted")
        elif pred_sex in ("Conflict", "Unknown_Manual"):
            sexes.append("Unknown"); sex_sources.append("Predicted")
        else:
            sexes.append(None); sex_sources.append("MISSING")

        # ── Weight ──
        w_dicom  = _parse_numeric(r.get("DICOM_PatientWeight"))
        w_report = _parse_numeric(r.get("Report_Weight_kg"))
        wt = _first_valid(w_dicom, w_report)
        if wt is not None and (wt < 20 or wt > 300): wt = None
        weights.append(wt)
        weight_sources.append(
            "DICOM" if w_dicom is not None else "Report" if w_report is not None else "MISSING"
        )

        # ── Height ──
        h_dicom  = _normalize_height(_parse_numeric(r.get("DICOM_PatientSize")))
        h_report = _normalize_height(_parse_numeric(r.get("Report_Height")))
        ht = _first_valid(h_dicom, h_report)
        if ht is not None and (ht < 100 or ht > 250): ht = None
        heights.append(ht)
        height_sources.append(
            "DICOM" if h_dicom is not None else "Report" if h_report is not None else "MISSING"
        )

        # ── BSA & BMI ──
        bsa_dicom    = _parse_numeric(r.get("DICOM_PatientBodySurfaceArea"))
        bsa_report   = _parse_numeric(r.get("Report_BSA_m2"))
        bsa_computed = _dubois_bsa(ht, wt)
        bsa = _first_valid(bsa_dicom, bsa_report, bsa_computed)
        if bsa is not None and (bsa < 0.5 or bsa > 3.5): bsa = None
        bsas.append(bsa)
        bsa_sources.append(
            "DICOM" if bsa_dicom is not None
            else "Report" if bsa_report is not None
            else "Computed" if bsa_computed is not None
            else "MISSING"
        )

        bmi_dicom    = _parse_numeric(r.get("DICOM_PatientBodyMassIndex"))
        bmi_computed = _bmi(ht, wt)
        bmis.append(_first_valid(bmi_dicom, bmi_computed))

    out["PatientID"]       = pids
    out["PatientID_Source"] = pid_sources
    out["Age"]             = ages
    out["Age_Source"]       = age_sources
    out["Sex"]             = sexes
    out["Sex_Source"]       = sex_sources
    out["Weight_kg"]       = weights
    out["Weight_Source"]    = weight_sources
    out["Height_cm"]       = heights
    out["Height_Source"]    = height_sources
    out["BSA_m2"]          = bsas
    out["BSA_Source"]       = bsa_sources
    out["BMI"]             = bmis
    return out


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: TABLE S1 STATISTICS (μορφή Table S1)
#   mean (SD) | median (Q1–Q3) | n (%)
# ══════════════════════════════════════════════════════════════════════════════

def compute_table1_stats(merged: pd.DataFrame) -> list[dict]:
    N_studies = len(merged)
    N_patients = int(merged["PatientID"].nunique())
    rows = []

    rows.append({"Characteristic": "Patients (N)", "Value": str(N_patients), "N_available": N_patients})
    rows.append({"Characteristic": "Studies (N)",  "Value": str(N_studies),  "N_available": N_studies})

    # ── Age ──
    age = merged["Age"].dropna()
    if len(age) > 0:
        rows.append({"Characteristic": "Age (mean [SD])",
                     "Value": f"{age.mean():.1f} ({age.std():.1f})",
                     "N_available": len(age)})
        rows.append({"Characteristic": "Age (median [IQR])",
                     "Value": f"{age.median():.1f} ({age.quantile(0.25):.1f}\u2013{age.quantile(0.75):.1f})",
                     "N_available": len(age)})
    else:
        rows.append({"Characteristic": "Age (mean [SD])", "Value": "N/A", "N_available": 0})

    # ── Sex ──
    sex = merged["Sex"].dropna()
    if len(sex) > 0:
        male_n    = int((sex == "M").sum())
        female_n  = int((sex == "F").sum())
        other_n   = int((sex == "Other").sum())
        unknown_n = int((sex == "Unknown").sum())
        missing_n = N_studies - len(sex)
        rows.append({"Characteristic": "Sex", "Value": "", "N_available": len(sex)})
        rows.append({"Characteristic": "  Male (n (%))",
                     "Value": f"{male_n:,} ({male_n/N_studies*100:.1f})", "N_available": None})
        rows.append({"Characteristic": "  Female (n (%))",
                     "Value": f"{female_n:,} ({female_n/N_studies*100:.1f})", "N_available": None})
        if other_n > 0:
            rows.append({"Characteristic": "  Other (n (%))",
                         "Value": f"{other_n:,} ({other_n/N_studies*100:.1f})", "N_available": None})
        if unknown_n > 0:
            rows.append({"Characteristic": "  Unknown (n (%))",
                         "Value": f"{unknown_n:,} ({unknown_n/N_studies*100:.1f})", "N_available": None})
        if missing_n > 0:
            rows.append({"Characteristic": "  Missing (n (%))",
                         "Value": f"{missing_n:,} ({missing_n/N_studies*100:.1f})", "N_available": None})
    else:
        rows.append({"Characteristic": "Sex", "Value": "N/A", "N_available": 0})

    # ── Weight / Height / BMI / BSA ──
    def _cont(col, label, dec):
        s = merged[col].dropna()
        if len(s) > 0:
            rows.append({"Characteristic": label,
                         "Value": f"{s.mean():.{dec}f} ({s.std():.{dec}f})",
                         "N_available": len(s)})
        else:
            rows.append({"Characteristic": label, "Value": "N/A", "N_available": 0})

    _cont("Weight_kg", "Weight, kg (mean [SD])", 1)
    _cont("Height_cm", "Height, cm (mean [SD])", 1)
    _cont("BMI",       "BMI, kg/m\u00b2 (mean [SD])", 1)
    _cont("BSA_m2",    "BSA, m\u00b2 (mean [SD])", 2)

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: MISSING DATA DIAGNOSTIC
# ══════════════════════════════════════════════════════════════════════════════

def build_diagnostic(merged: pd.DataFrame) -> pd.DataFrame:
    fields = ["Age", "Sex", "Weight_kg", "Height_cm", "BSA_m2", "BMI"]
    diag_rows = []

    for _, row in merged.iterrows():
        missing_fields = []
        for f in fields:
            val = row[f]
            if val is None or (isinstance(val, float) and math.isnan(val)):
                missing_fields.append(f)
        if missing_fields:
            diag_rows.append({
                "ExamID": row["ExamID"],
                "PatientID": row.get("PatientID", ""),
                "N_Missing_Fields": len(missing_fields),
                "Missing_Fields": ", ".join(missing_fields),
                "Age_Source": row.get("Age_Source", ""),
                "Sex_Source": row.get("Sex_Source", ""),
                "Weight_Source": row.get("Weight_Source", ""),
                "Height_Source": row.get("Height_Source", ""),
                "BSA_Source": row.get("BSA_Source", ""),
            })

    if not diag_rows:
        diag_rows.append({
            "ExamID": "ALL COMPLETE",
            "N_Missing_Fields": 0,
            "Missing_Fields": "No missing data detected",
        })
    return pd.DataFrame(diag_rows)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: EXCEL OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def _align_stat_rows(stats_list: list[list[dict]]) -> list[str]:
    seen, ordered = set(), []
    for stats in stats_list:
        for row in stats:
            char = row["Characteristic"]
            if char not in seen:
                seen.add(char)
                ordered.append(char)
    return ordered


def save_unified_excel(cohort_data: list[dict], output_path: str):
    wb = Workbook()

    hdr_font     = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    hdr_fill     = PatternFill("solid", start_color="1F4E79")
    hdr_align    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_font    = Font(name="Arial", size=10)
    bold_font    = Font(name="Arial", size=10, bold=True)
    thin_border  = Border(bottom=Side(style="thin", color="BFBFBF"))
    thick_border = Border(bottom=Side(style="medium", color="000000"))
    alt_fill     = PatternFill("solid", start_color="F2F7FB")
    miss_fill    = PatternFill("solid", start_color="FFC7CE")
    warn_fill    = PatternFill("solid", start_color="FFEB9C")
    good_fill    = PatternFill("solid", start_color="C6EFCE")
    note_font    = Font(name="Arial", size=8, italic=True, color="666666")

    n_cohorts = len(cohort_data)
    last_col = 1 + (n_cohorts * 2)

    # ── Sheet 1: Table_1 (Table S1 layout) ──
    ws1 = wb.active
    ws1.title = "Table_1"

    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws1.cell(row=1, column=1,
             value="Table S1 | Baseline characteristics \u2014 Hippokration external validation cohort"
             ).font = Font(name="Arial", bold=True, size=12)

    ws1.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)
    char_hdr = ws1.cell(row=2, column=1, value="Characteristic")
    char_hdr.font = bold_font
    char_hdr.alignment = Alignment(vertical="center")
    ws1.cell(row=3, column=1).border = thick_border

    col_idx = 2
    for cd in cohort_data:
        ws1.merge_cells(start_row=2, start_column=col_idx, end_row=2, end_column=col_idx + 1)
        c_hdr = ws1.cell(row=2, column=col_idx, value=cd["label"])
        c_hdr.font = bold_font
        c_hdr.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for off, txt in ((0, "Value"), (1, "N")):
            h = ws1.cell(row=3, column=col_idx + off, value=txt)
            h.font = bold_font
            h.border = thick_border
            h.alignment = Alignment(horizontal="center", vertical="center")
        col_idx += 2

    all_stats = [cd["stats"] for cd in cohort_data]
    char_order = _align_stat_rows(all_stats)

    v_lookups, n_lookups = [], []
    for stats in all_stats:
        v_lookups.append({r["Characteristic"]: r["Value"] for r in stats})
        n_lookups.append({r["Characteristic"]: r.get("N_available") for r in stats})

    for r_idx, char_name in enumerate(char_order, start=4):
        char_cell = ws1.cell(row=r_idx, column=1, value=char_name)
        char_cell.font = body_font
        char_cell.border = thin_border
        if char_name.startswith("  "):
            char_cell.alignment = Alignment(indent=2)

        col_idx = 2
        for v_lookup, n_lookup in zip(v_lookups, n_lookups):
            val = v_lookup.get(char_name, "\u2013")
            n_val = n_lookup.get(char_name)
            if n_val is None: n_val = "\u2013"
            if char_name.startswith("  ") and val != "\u2013": n_val = ""

            vc = ws1.cell(row=r_idx, column=col_idx, value=val)
            vc.font = body_font
            vc.alignment = Alignment(horizontal="center")
            vc.border = thin_border

            nc = ws1.cell(row=r_idx, column=col_idx + 1, value=n_val)
            nc.font = body_font
            nc.alignment = Alignment(horizontal="center")
            nc.border = thin_border
            col_idx += 2

        if r_idx % 2 == 0:
            for c in range(1, last_col + 1):
                ws1.cell(row=r_idx, column=c).fill = alt_fill

    last_data_row = 3 + len(char_order)
    for c in range(1, last_col + 1):
        ws1.cell(row=last_data_row, column=c).border = thick_border

    fn_row = last_data_row + 2
    footnotes = [
        ("Table S1. Baseline characteristics of the full retrospective validation cohort, as well as the "
         "subsets of studies with available reference left ventricular ejection fraction, right ventricular "
         "systolic pressure value (estimation subset) and right ventricular systolic pressure classification "
         "relative to 35 mm Hg (classification subset). Values are reported as mean (SD), median (IQR), "
         "or n (%), as appropriate."),
        "N (right column of each pair) = number of non-missing records for the variable within the respective cohort.",
        ("Age, weight, height, BMI and BSA are summarised per study; Patients (N) counts unique patients "
         "(patient identifiers from the study-to-patient mapping used for the patient-level bootstrap)."),
        "BSA calculated using the DuBois formula where not directly available from DICOM or report.",
        "Sex derived from the Predicted_PatientSex column (gender inference pipeline).",
        ("LVEF subset: studies with any available LVEF ground truth (exact value, range or modifier). "
         "RVSP estimation subset: studies with a numeric RVSP value reported in the clinical report (rvsp_numeric; exact values plus modifier values other than the 35 mm Hg threshold). "
         "RVSP classification subset: studies with an RVSP class label relative to 35 mm Hg (rvsp_label)."),
        ("LVEF, left ventricular ejection fraction; RVSP, right ventricular systolic pressure; "
         "BMI, body mass index; BSA, body surface area; SD, standard deviation; IQR, interquartile range."),
    ]
    for i, fn in enumerate(footnotes):
        cell = ws1.cell(row=fn_row + i, column=1, value=fn)
        cell.font = note_font
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws1.merge_cells(start_row=fn_row + i, start_column=1,
                        end_row=fn_row + i, end_column=last_col)
        ws1.row_dimensions[fn_row + i].height = 36 if len(fn) > 160 else 14

    ws1.column_dimensions["A"].width = 32
    for c in range(2, last_col + 1, 2):
        ws1.column_dimensions[get_column_letter(c)].width = 18
        ws1.column_dimensions[get_column_letter(c + 1)].width = 9
    ws1.row_dimensions[2].height = 35
    ws1.row_dimensions[3].height = 20

    # ── Per-exam sheets ──
    detail_cols = [
        "PatientID", "ExamID", "Age", "Age_Source", "Sex", "Sex_Source",
        "Weight_kg", "Weight_Source", "Height_cm", "Height_Source",
        "BSA_m2", "BSA_Source", "BMI",
    ]
    for cd in cohort_data:
        ws = wb.create_sheet(f"Per_Exam_{cd['short_name']}")
        detail_df = cd["merged"][detail_cols].copy()

        for c_idx, col_name in enumerate(detail_cols, 1):
            cell = ws.cell(row=1, column=c_idx, value=col_name)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = hdr_align

        for r_idx, (_, row) in enumerate(detail_df.iterrows(), start=2):
            for c_idx, col_name in enumerate(detail_cols, 1):
                val = row[col_name]
                if isinstance(val, float) and math.isnan(val):
                    val = None
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = body_font
                if r_idx % 2 == 0:
                    cell.fill = alt_fill
                if isinstance(val, str) and val == "MISSING":
                    cell.fill = miss_fill
                    cell.font = Font(name="Arial", size=10, bold=True, color="9C0006")

        for c_idx, col_name in enumerate(detail_cols, 1):
            vals = [str(v) if v else "" for v in detail_df[col_name]]
            max_len = max(len(col_name), *(len(v) for v in vals)) if vals else len(col_name)
            ws.column_dimensions[get_column_letter(c_idx)].width = min(max_len + 3, 25)
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(detail_cols))}{len(detail_df)+1}"

    # ── Missing_Data (Full cohort — superset) ──
    ws_miss = wb.create_sheet("Missing_Data")
    merged_full = cohort_data[0]["merged"]
    diagnostic = cohort_data[0]["diagnostic"]
    total = len(merged_full)

    ws_miss.cell(row=1, column=1,
                 value="Missing Data Summary (Full cohort — superset)").font = Font(
        name="Arial", bold=True, size=12)

    fields_to_check = ["Age", "Sex", "Weight_kg", "Height_cm", "BSA_m2", "BMI"]
    summ_row = 3
    for c, h in enumerate(["Field", "Available", "Missing", "% Complete"], 1):
        cell = ws_miss.cell(row=summ_row, column=c, value=h)
        cell.font = bold_font
        cell.border = thick_border
        cell.alignment = Alignment(horizontal="center")

    for i, field in enumerate(fields_to_check, start=summ_row + 1):
        avail = merged_full[field].notna().sum()
        miss = total - avail
        pct = avail / total * 100 if total > 0 else 0
        ws_miss.cell(row=i, column=1, value=field).font = body_font
        ws_miss.cell(row=i, column=2, value=int(avail)).font = body_font
        ws_miss.cell(row=i, column=3, value=int(miss)).font = body_font
        pct_cell = ws_miss.cell(row=i, column=4, value=f"{pct:.1f}%")
        pct_cell.font = body_font
        pct_cell.alignment = Alignment(horizontal="center")
        pct_cell.fill = good_fill if pct >= 90 else warn_fill if pct >= 50 else miss_fill
        for c in range(1, 5):
            ws_miss.cell(row=i, column=c).border = thin_border

    src_row = summ_row + len(fields_to_check) + 3
    ws_miss.cell(row=src_row, column=1, value="Data Source Breakdown").font = Font(
        name="Arial", bold=True, size=11)
    src_row += 1
    for sf in ["PatientID_Source", "Age_Source", "Sex_Source", "Weight_Source", "Height_Source", "BSA_Source"]:
        if sf not in merged_full.columns:
            continue
        ws_miss.cell(row=src_row, column=1, value=sf.replace("_Source", "")).font = bold_font
        src_row += 1
        for src, cnt in merged_full[sf].value_counts().items():
            ws_miss.cell(row=src_row, column=1, value=f"  {src}").font = body_font
            ws_miss.cell(row=src_row, column=2, value=int(cnt)).font = body_font
            ws_miss.cell(row=src_row, column=3, value=f"{cnt/total*100:.1f}%").font = body_font
            if src == "MISSING":
                ws_miss.cell(row=src_row, column=1).fill = miss_fill
            src_row += 1
        src_row += 1

    detail_start = src_row + 1
    ws_miss.cell(row=detail_start, column=1, value="Per-Exam Missing Data Detail").font = Font(
        name="Arial", bold=True, size=11)
    detail_start += 1
    diag_cols = list(diagnostic.columns)
    for c_idx, col_name in enumerate(diag_cols, 1):
        cell = ws_miss.cell(row=detail_start, column=c_idx, value=col_name)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = hdr_align
    for r_idx, (_, row) in enumerate(diagnostic.iterrows(), start=detail_start + 1):
        for c_idx, col_name in enumerate(diag_cols, 1):
            val = row[col_name]
            if isinstance(val, float) and math.isnan(val):
                val = None
            cell = ws_miss.cell(row=r_idx, column=c_idx, value=val)
            cell.font = body_font
            if col_name == "N_Missing_Fields" and isinstance(val, (int, float)):
                cell.fill = miss_fill if val >= 4 else warn_fill if val >= 2 else alt_fill

    ws_miss.column_dimensions["A"].width = 22
    ws_miss.column_dimensions["B"].width = 18
    ws_miss.column_dimensions["C"].width = 45
    for col_letter in ["D", "E", "F", "G", "H"]:
        ws_miss.column_dimensions[col_letter].width = 14

    wb.save(output_path)


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def process_cohort(df_base: pd.DataFrame, label: str, short_name: str,
                   patient_map: dict | None = None) -> dict:
    print(f"\n  ┌─ Processing: {short_name}  ({len(df_base):,} exams)")
    merged = merge_fields(df_base, patient_map)
    src = merged["PatientID_Source"].value_counts().to_dict()
    print(f"  │  Patient ID sources: {src}")
    for field in ["Age", "Sex", "Weight_kg", "Height_cm"]:
        avail = merged[field].notna().sum()
        pct = avail / len(merged) * 100 if len(merged) else 0
        print(f"  │  {field:12s}: {avail:,}/{len(merged):,} ({pct:.1f}%)")
    stats = compute_table1_stats(merged)
    diagnostic = build_diagnostic(merged)
    print(f"  └─ Done: {short_name}")
    return {
        "label": label,
        "short_name": short_name,
        "stats": stats,
        "merged": merged,
        "diagnostic": diagnostic,
        "n_studies": len(merged),
        "n_patients": int(merged["PatientID"].nunique()),
    }


def check_expected(cohort_data: list[dict], expected: dict | None):
    if not expected:
        return
    print(f"\n  ── Έλεγχος έναντι Table S1 ──")
    print(f"  {'Cohort':10s} {'Studies exp/got':>18s} {'Patients exp/got':>20s}  Status")
    all_ok = True
    for cd in cohort_data:
        exp = expected.get(cd["short_name"])
        if not exp:
            continue
        s_ok = exp.get("studies") in (None, cd["n_studies"])      # None = δεν ελέγχεται
        p_ok = exp.get("patients") in (None, cd["n_patients"])
        all_ok &= (s_ok and p_ok)
        status = "OK" if (s_ok and p_ok) else ("DIFF studies" if not s_ok else "DIFF patients")
        es = "-" if exp.get("studies") is None else f"{exp['studies']:,}"
        ep = "-" if exp.get("patients") is None else f"{exp['patients']:,}"
        print(f"  {cd['short_name']:10s} {es:>8s} / {cd['n_studies']:<8,} "
              f"{ep:>9s} / {cd['n_patients']:<8,}  {status}")
    print("  → ΟΛΑ ΤΑΙΡΙΑΖΟΥΝ" if all_ok else "  → ΥΠΑΡΧΟΥΝ ΔΙΑΦΟΡΕΣ (δες παραπάνω)")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 65)
    print("  Demographics Table S1 Generator — 4 cohorts (v6)")
    print("=" * 65)

    print(f"\n[1/5] Loading patient metadata...")
    excluded = _build_exclusion_set(EXCLUSION_LIST, EXCLUSION_FILE)
    df_all = load_patient_metadata(INPUT_XLS, excluded)

    print(f"\n[2/5] Loading prediction file...")
    pred_ids = load_prediction_ids(PREDICTION_CSV, PRED_ID_COL)
    df_all = filter_by_prediction_intersection(df_all, pred_ids)

    print(f"\n[3/5] Loading ground truth file...")
    gt_ids = load_ground_truth(GT_BINARY_CSV, GT_LVEF_CSV, GT_RVSP_CSV)

    print(f"\n[4/5] Filtering cohorts...")
    meta_ids = set(df_all["ExamID"].astype(str).str.strip())
    in_both = len(meta_ids & gt_ids["binary"])
    print(f"  Binary GT ∩ (metadata ∩ predictions): {in_both:,} "
          f"| μόνο στο GT: {len(gt_ids['binary'] - meta_ids):,} "
          f"| μόνο στο metadata: {len(meta_ids - gt_ids['binary']):,}")
    if FULL_RESTRICT_TO_BINARY_GT:
        df_all = filter_by_ground_truth(df_all, gt_ids["binary"], "Full (binary GT)")
    subsets = {
        "Full":     df_all,
        "LVEF":     filter_by_ground_truth(df_all, gt_ids["ef"],       "LVEF"),
        "RVSP_Est": filter_by_ground_truth(df_all, gt_ids["rvsp_est"], "RVSP Estimation"),
        "RVSP_Cls": filter_by_ground_truth(df_all, gt_ids["rvsp_cls"], "RVSP Classification"),
    }

    print(f"\n[5/5] Processing cohorts + generating Table S1...")
    patient_map = load_patient_map(PATIENT_MAP_FILE)
    cohort_data = [process_cohort(subsets[short], label, short, patient_map) for short, label in COHORTS]

    Path(OUTPUT_UNIFIED).parent.mkdir(parents=True, exist_ok=True)
    save_unified_excel(cohort_data, OUTPUT_UNIFIED)

    check_expected(cohort_data, EXPECTED_COUNTS)

    print(f"\n{'=' * 65}")
    print(f"  DONE — Output: {OUTPUT_UNIFIED}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
