# Computational environment

All analyses were run on a single Windows workstation, in one conda environment.

## Hardware

| Component | Version |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 (12 GB) |
| CUDA (PyTorch build) | 12.1 |

## EchoPrime

| Item | Version |
|---|---|
| Repository | https://github.com/echonet/EchoPrime |
| Code version | commit `03874a5` (merged 9 Feb 2026, PR #14, single-DICOM inference fix) |
| Pretrained weights | release `v1.0.0` (`model_data.zip`, `candidate_embeddings_p1.pt`, `candidate_embeddings_p2.pt`) |
| Modifications | none |

The local copy was downloaded on 13 Nov 2025 (commit `6c14cbe`), and
`echo_prime/model.py` was later replaced with the version from commit `03874a5`.
These two commits differ only in that file, so the code used is identical to
`03874a5`. It is also identical to the current `main` branch, since later commits
change only `README.md`.

## Core software

| Package | Version | Used for |
|---|---|---|
| Python | 3.10.19 | all |
| torch | 2.5.1+cu121 | EchoPrime inference |
| torchvision | 0.20.1+cu121 | EchoPrime inference |
| transformers | 4.57.0 | EchoPrime inference |
| pydicom | 2.3.1 | DICOM reading |
| opencv-python-headless | 4.8.1.78 | video preprocessing |
| numpy | 1.26.4 | all (incl. AUROC/AUPRC and the cluster bootstrap) |
| pandas | 2.3.3 | all |
| scikit-learn | 1.7.2 | regression metrics; ROC thresholds (RVSP) |
| beautifulsoup4 | 4.13.5 | report HTML parsing (`html.parser`) |
| openpyxl | 3.1.5 | Excel output |
| matplotlib | 3.10.7 | confusion-matrix figures (RVSP, optional) |
| seaborn | 0.13.2 | confusion-matrix figures (RVSP, optional) |
| tqdm | 4.67.1 | progress bars |
| 7-Zip | any | only for reports stored as `.CHM` |

EchoPrime's own `requirements.txt` pins `opencv-python-headless==4.5.5.64`.
Version 4.8.1.78 was used here instead.

The minimal pinned set is in `requirements.txt`. The full environment export
(`pip freeze`, `conda list --export`) is kept in `environment/` for completeness.
