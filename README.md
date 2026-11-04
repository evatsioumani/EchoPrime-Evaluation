# EchoPrime external validation — Hippokration cohort

Code for the external validation of [EchoPrime](https://github.com/echonet/EchoPrime),
a multimodal echocardiography foundation model, on transthoracic echocardiograms
from the **3rd Cardiology Department, Hippokration General Hospital, Thessaloniki, Greece**.

EchoPrime is used as released (no fine-tuning, no code changes). This repository contains:

1. the batch inference wrapper used to run EchoPrime on the cohort,
2. the rule-based NLP pipeline that extracts ground-truth labels from the Greek clinical reports,
3. the evaluation scripts for the binary findings and the continuous measurements (LVEF, RVSP),
4. the generator for the cohort characteristics table.

> **No patient data is included.** DICOM studies, clinical reports, ID lists and every
> derived file (labels, predictions, results) stay at the hospital. `.gitignore`
> blocks `data/` and `outputs/`.

> **Status:** work in progress. Still to be added: the supplementary operating-point
> analysis (Table S2), the RVSP classification evaluation (35 mmHg), and the scripts
> that build the patient metadata used in Table S1.

---

## Repository structure

```
.
├── 01_inference/
│   └── batch_eval_determ_v3.py              EchoPrime batch inference → predictions_raw_.csv
├── 02_ground_truth/
│   ├── binary/                              binary findings (run all 10 files from this folder)
│   │   ├── run_ground_truth_final.py          ← entry point: unified run, all findings & variants
│   │   ├── ground_truth_extractor_full_dataset_v5.py   base extractor (findings without a v6x version)
│   │   ├── pacemaker_v6x.py
│   │   ├── rv_systolic_v6x.py
│   │   ├── mitral_valve_v6x.py                 mitral stenosis + regurgitation
│   │   ├── mitral_annular_calcification_v6x.py
│   │   ├── tavr_v6x.py
│   │   ├── aortic_valve_v6x.py                 aortic stenosis + regurgitation
│   │   ├── tricuspid_valve_v6x.py
│   │   └── pericardial_effusion_v6x.py
│   ├── lvef/ef_extractor.py                 LVEF: exact / range / modifier
│   └── rvsp/rvsp_binary_extractor.py        RVSP: numeric value + label at 35 mmHg
├── 03_evaluation/
│   ├── evaluate_binary_findings_final.py    binary findings (AUROC, AUPRC, Sens, Spec, …)
│   └── ef_rvsp_validation_v2.py             LVEF and RVSP regression (MAE, RMSE, R²)
├── 04_tables/
│   └── demographics_tableS1_generator_v6.py cohort characteristics (Table S1)
├── environment/                             full pip / conda exports
├── ENVIRONMENT.md                           software, hardware, EchoPrime version
├── requirements.txt
└── LICENSE
```

## Pipeline

```
DICOM studies ──► 01_inference ──────────────► predictions_raw_.csv ─┐
                                                                     ├─► 03_evaluation ──► results
Greek reports ──► 02_ground_truth/binary ────► ground_truth_labels.csv│
              ├─► 02_ground_truth/lvef ──────► ef_ground_truth.csv    │
              └─► 02_ground_truth/rvsp ──────► rvsp_ground_truth.csv ─┘
                                                         └─► 04_tables ──► Table S1
```

| Step | Script | Main output |
|---|---|---|
| 1 | `01_inference/batch_eval_determ_v3.py` | `predictions_raw_.csv` (one row per study) |
| 2a | `02_ground_truth/binary/run_ground_truth_final.py` | `ground_truth_labels.csv`, `ground_truth_long.csv`, `ground_truth_summary.csv`, `manifest.json` |
| 2b | `02_ground_truth/lvef/ef_extractor.py` | `ef_ground_truth.csv` |
| 2c | `02_ground_truth/rvsp/rvsp_binary_extractor.py` | `rvsp_ground_truth.csv` |
| 3a | `03_evaluation/evaluate_binary_findings_final.py` | `binary_evaluation.xlsx`, `per_exam_predictions.csv` |
| 3b | `03_evaluation/ef_rvsp_validation_v2.py` | `regression_results.xlsx` |
| 4 | `04_tables/demographics_tableS1_generator_v6.py` | `demographics_tableS1.xlsx` |

Steps 1 and 2 are independent; step 3 needs both; step 4 needs step 2 and the study list from step 1.

## Setup

```bash
conda create -n echoprime python=3.10
conda activate echoprime
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

EchoPrime is cloned separately (it is under its own academic license, see below):

```bash
git clone https://github.com/echonet/EchoPrime
cd EchoPrime && git checkout 03874a5
# download model_data.zip and candidate_embeddings_p1/p2.pt from release v1.0.0 (see EchoPrime README)
```

Reports stored as `.CHM` need [7-Zip](https://www.7-zip.org/); plain `.html` reports do not.

Exact versions and hardware: [`ENVIRONMENT.md`](ENVIRONMENT.md).

## Running

Every script has a configuration block (at the top, or under `if __name__ == "__main__":`)
with input/output paths. The defaults assume this layout, relative to the working directory:

```
data/
  dicom/<study_id>/echo/*.dcm
  reports/<exam_id>/report/<report>.CHM|.html
  lists/inclusion_ids.txt        studies to run inference on
  lists/exclusion_ids.txt        studies excluded from all analyses
  metadata/study_patient_mapping.csv   exam_id → patient_id
  metadata/metadata_processed.xlsx     demographics (Table S1 only)
outputs/                         everything the scripts write
```

The scripts were run in Spyder (F5); each one can also be run with `python <script>.py`.

Notes:
- **Inference** must run with the EchoPrime folder as the working directory, because
  EchoPrime loads `model_data/...` with relative paths. Set `ECHOPRIME_DIR` and use
  absolute paths for `DATASET_ROOT` / `OUTPUT_DIR`.
- **Binary ground truth**: `run_ground_truth_final.py` contains no regex. It loads the
  nine extractor scripts from its own folder and calls them, so keep the folder intact.
  Self-tests in the extractors run automatically; the SHA-256 of every script is
  written to `manifest.json` together with the variant definitions.

## Ground truth

Labels are extracted from the free-text Greek reports with section-aware regular
expressions, negation handling and explicit severity grading. No machine-learning
model is involved.

**Binary findings** (17). Where a severity threshold matters, two parallel labels
are produced so the effect of the definition can be measured:

| Finding | Column(s) | Definition |
|---|---|---|
| Pacemaker | `pacemaker` / `pacemaker_incl_icd` | pacemaker / pacemaker, ICD or device lead |
| RV systolic dysfunction | `rv_systolic_function_depressed` / `_incl_mild` | moderate–severe / mild–severe (borderline = 0) |
| RV, RA, LA dilation | `right_ventricle_dilation`, `right_atrium_dilation`, `left_atrium_dilation` | base extractor (v5) |
| MitraClip | `mitraclip` | base extractor (v5) |
| Mitral annular calcification | `mitral_annular_calcification` / `_incl_mild` | moderate–severe or ungraded / any |
| Mitral stenosis, regurgitation | `mitral_stenosis`, `mitral_regurgitation` (+ `_incl_mild`) | moderate–severe / mild–severe (trace = 0) |
| TAVR | `tavr_incl_mech` / `tavr_excl_mech` | any prosthetic valve / bioprosthetic or TAVR (mechanical = 0) |
| Bicuspid aortic valve | `bicuspid_aov` | base extractor (v5) |
| Aortic stenosis, regurgitation | `aortic_stenosis`, `aortic_regurgitation` (+ `_incl_mild`) | moderate–severe / mild–severe (trace = 0) |
| Aortic root dilation | `aortic_root_dilation` | base extractor (v5) |
| Tricuspid regurgitation | `tricuspid_valve_regurgitation` (+ `_incl_mild`) | moderate–severe / mild–severe (trace = 0) |
| Pericardial effusion | `pericardial_effusion_mod_severe` / `pericardial_effusion` | moderate–large (≥10 mm or stated) / any size |
| Dilated IVC | `dilated_ivc` | base extractor (v5) |

The full rule text for every variant is written to `manifest.json` at run time.

**LVEF** (`ef_extractor.py`) records the value as written: exact, range or modifier
(e.g. `>55`). Conversion to a single number happens in the evaluation script:
exact > range midpoint > modifier value.

**RVSP** (`rvsp_binary_extractor.py`) records the numeric value, how it was stated
(exact / modifier / qualitative / range) and a binary label at 35 mmHg. Regression
uses exact values plus modifiers whose value is not the 35 mmHg threshold.

## Evaluation

- EchoPrime's native outputs (`predict_metrics`) are evaluated directly; no model is trained here.
- Binary findings: AUROC, AUPRC, sensitivity, specificity, PPV, NPV, accuracy, F1 at the
  0.5 threshold, plus a Youden threshold reported as exploratory. Where a finding has two
  label variants, ΔAUROC and ΔAUPRC between them are tested on the same exams, with
  Holm–Bonferroni correction across the comparison family.
- LVEF and RVSP: MAE, RMSE, R².
- All 95% CIs come from a **patient-level cluster bootstrap** (10,000 resamples, seed 42),
  since some patients have more than one exam. Bootstrap p-values use the
  Phipson–Smyth correction, (b+1)/(m+1).

## Licence

Code in this repository: MIT (see `LICENSE`).
EchoPrime and its weights are distributed by Cedars-Sinai under their own
[academic software license](https://github.com/echonet/EchoPrime/blob/main/LICENSE)
and are not included here.

## Citation

If you use this code, please cite the accompanying paper (reference to be added) and EchoPrime:

> Vukadinovic M, et al. *Comprehensive echocardiogram evaluation with view primed vision language AI.* Nature 650, 970–977 (2026).
