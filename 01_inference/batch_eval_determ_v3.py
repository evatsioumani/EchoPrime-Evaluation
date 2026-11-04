"""
EchoPrime — batch inference on the Hippokration cohort
======================================================
Runs the unmodified EchoPrime pipeline (github.com/echonet/EchoPrime,
commit 03874a5, weights release v1.0.0) on every study in DATASET_ROOT,
following the three steps of EchoPrimeDemo.ipynb:

    ep.process_dicoms(<study>/echo)  ->  ep.encode_study(...)  ->  ep.predict_metrics(...)

predict_metrics() is EchoPrime's native retrieval-augmented interpretation
(RAI); it returns the binary finding scores and the continuous measurements
(e.g. ejection_fraction, pulmonary_artery_pressure_continuous) for each study.

Expected layout:  DATASET_ROOT/<study_id>/echo/*.dcm
Study selection:  INCLUSION_LIST (.txt, one study_id per line; None = all)

Wrapper-level behaviour (EchoPrime itself is not modified):
  - set_deterministic(seed=42): Python/NumPy/PyTorch seeds, cuDNN
    deterministic mode, torch.use_deterministic_algorithms.
  - torch.no_grad() around inference and torch.cuda.empty_cache() after each
    step, to keep GPU memory stable over thousands of studies.
  - Incremental, crash-safe saving after every study; RESUME skips studies
    already present in predictions_raw_.csv.
  - MAX_STUDIES = N runs a pilot on the first N studies (written to
    OUTPUT_DIR/pilot/).

Output:  OUTPUT_DIR/predictions_raw_.csv   (one row per study, column study_id)
         OUTPUT_DIR/failed_studies.txt

Run: set the paths in the block at the bottom of this file and execute.
"""

import gc
import json
import logging
import os
import random
import traceback
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import torch
from tqdm import tqdm


# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("EchoPrimeBatch")


# ─── Determinism ──────────────────────────────────────────────────────────────
def set_deterministic(seed: int = 42) -> None:
    """
    Εγγυάται πλήρως reproducible inference.

    Καλύπτει:
      - Python / NumPy / PyTorch RNG seeds
      - cuDNN deterministic mode (απενεργοποιεί autotuner)
      - CUBLAS workspace για deterministic GEMM
      - torch.use_deterministic_algorithms (PyTorch >= 1.8)

    ΠΡΟΣΟΧΗ: torch.use_deterministic_algorithms(True) μπορεί να πετάξει
    RuntimeError αν κάποια op δεν έχει deterministic υλοποίηση.
    Σε αυτή την περίπτωση αλλαξε σε warn_only=True παρακάτω.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    try:
        torch.use_deterministic_algorithms(True)
    except AttributeError:
        # PyTorch < 1.8 — δεν υποστηρίζεται, συνεχίζουμε
        log.warning("torch.use_deterministic_algorithms μη διαθέσιμο "
                    "(PyTorch < 1.8) — μερική determinism")
    except RuntimeError as e:
        # Κάποια op δεν έχει deterministic implementation
        log.warning(f"use_deterministic_algorithms(True) απέτυχε: {e}\n"
                    "Δοκίμασε warn_only=True αν χρειάζεται.")
    log.info(f"Deterministic mode ενεργό (seed={seed})")


# ─── Inclusion list ──────────────────────────────────────────────────────────
def load_inclusion_list(inclusion_list_path) -> set:
    """
    Διαβάζει .txt αρχείο με ένα study_id ανά γραμμή.
    Γραμμές που ξεκινούν με # αγνοούνται (comments).
    Αν δεν δοθεί path, επιστρέφει κενό set (= επεξεργασία ΟΛΩΝ).

    [BUG-3 FIX]:
        - utf-8-sig αντί utf-8: αφαιρεί αυτόματα BOM (\ufeff) αν υπάρχει
        - Αν δοθεί path αλλά φορτωθούν 0 IDs → ΣΦΑΛΜΑ (fail-fast)
        - Debug logging: εμφανίζει τα πρώτα 5 IDs για επαλήθευση
    """
    if inclusion_list_path is None:
        log.info("Inclusion list: None — θα επεξεργαστούν ΟΛΑ τα studies")
        return set()

    path = Path(inclusion_list_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Inclusion list δεν βρέθηκε: {path}\n"
            f"Αν θες ΟΛΑ τα studies, βάλε INCLUSION_LIST = None"
        )

    # utf-8-sig: αφαιρεί BOM αυτόματα (κοινό σε Windows Notepad)
    raw_text = path.read_text(encoding="utf-8-sig")

    ids = set()
    for line in raw_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.add(line)

    if not ids:
        raise ValueError(
            f"Inclusion list υπάρχει αλλά δεν περιέχει IDs: {path}\n"
            f"Βεβαιώσου ότι έχει ένα study_id ανά γραμμή."
        )

    # Debug: δείξε τα πρώτα IDs για επαλήθευση
    sample = sorted(ids)[:5]
    log.info(
        f"Inclusion list: {len(ids)} studies φορτώθηκαν από {path.name}\n"
        f"  Δείγμα IDs: {sample}"
    )
    return ids


# ─── Study discovery ──────────────────────────────────────────────────────────
def discover_studies(dataset_root: Path, inclusion_ids: set) -> list:
    """
    Επιστρέφει sorted λίστα study folders που:
      - ΕΙΝΑΙ στην inclusion list (αν δόθηκε — αλλιώς όλα)
      - Έχουν τουλάχιστον ένα .dcm αρχείο στον echo/ υποφάκελο

    Η ταξινόμηση (sorted) εξασφαλίζει deterministic σειρά επεξεργασίας
    ανεξάρτητα από το filesystem.
    """
    studies          = []
    skipped_notinlist = 0
    skipped_novideo  = 0

    # sorted() εξασφαλίζει deterministic σειρά [DET-2 για folder discovery]
    for folder in sorted(dataset_root.iterdir()):
        if not folder.is_dir():
            continue

        study_id = folder.name

        # Έλεγχος inclusion list (αν υπάρχει)
        if inclusion_ids and study_id not in inclusion_ids:
            skipped_notinlist += 1
            continue

        # Έλεγχος ύπαρξης echo/ υποφακέλου και .dcm αρχείων μέσα σε αυτόν
        echo_dir = folder / "echo"
        if not echo_dir.is_dir():
            log.warning(f"  [ΠΑΡΑΛΕΙΨΗ — Δεν βρέθηκε echo/ υποφάκελος] {study_id}")
            skipped_novideo += 1
            continue

        dcm_files = list(echo_dir.glob("*.dcm"))
        if not dcm_files:
            log.warning(f"  [ΠΑΡΑΛΕΙΨΗ — Δεν βρέθηκαν .dcm αρχεία στο echo/] {study_id}")
            skipped_novideo += 1
            continue

        studies.append(folder)

    log.info(
        f"Ανακάλυψη: {len(studies)} studies προς επεξεργασία | "
        f"{skipped_notinlist} παραλείφθηκαν (εκτός inclusion list) | "
        f"{skipped_novideo} παραλείφθηκαν (χωρίς .dcm)"
    )

    # [BUG-3 FIX] Sanity check: αν δόθηκε inclusion list αλλά κανένα
    # folder δεν ταίριαξε, δείξε τι ακριβώς δεν ταιριάζει
    if inclusion_ids and not studies:
        all_folders = sorted(
            f.name for f in dataset_root.iterdir() if f.is_dir()
        )[:5]
        sample_ids = sorted(inclusion_ids)[:5]
        log.error(
            f"ΚΑΝΕΝΑ study δεν ταίριαξε!\n"
            f"  Δείγμα folder names : {all_folders}\n"
            f"  Δείγμα inclusion IDs: {sample_ids}\n"
            f"  Μήπως τα IDs δεν ταιριάζουν τα ονόματα φακέλων;"
        )

    return studies


# ─── Inference ενός study ─────────────────────────────────────────────────────
def run_single_study(ep, study_path: Path):
    """
    Εκτελεί τα 3 βήματα του EchoPrimeDemo.ipynb για ένα study.
    Επιστρέφει dict με τα phenotypes ή None αν αποτύχει.

    [MEM-1 FIX]:
        - torch.no_grad() αποτρέπει gradient tracking (δεν χρειάζεται στο inference)
        - torch.cuda.empty_cache() καλείται ΜΕΤΑ ΑΠΟ ΚΑΘΕ βήμα
    """
    study_id    = study_path.name
    echo_folder = str(study_path / "echo")

    with torch.no_grad():

        # ── Βήμα 1: Preprocessing ─────────────────────────────────────────
        try:
            stack_of_videos = ep.process_dicoms(echo_folder)
        except Exception:
            log.error(
                f"  [ΑΠΟΤΥΧΙΑ PREPROCESSING] {study_id}\n{traceback.format_exc()}"
            )
            return None

        if stack_of_videos is None or stack_of_videos.shape[0] == 0:
            log.warning(f"  [ΑΔΕΙΟ] {study_id} — κανένα έγκυρο video")
            return None

        log.debug(f"  {study_id}: {stack_of_videos.shape[0]} videos φορτώθηκαν")

        # ── Βήμα 2: Encoding ──────────────────────────────────────────────
        try:
            encoded_study = ep.encode_study(stack_of_videos)
        except Exception:
            log.error(
                f"  [ΑΠΟΤΥΧΙΑ ENCODING] {study_id}\n{traceback.format_exc()}"
            )
            return None
        finally:
            # Αποδέσμευση RAM/VRAM μετά το encoding
            del stack_of_videos
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # ── Βήμα 3: Prediction ────────────────────────────────────────────
        try:
            preds = ep.predict_metrics(encoded_study)
        except Exception:
            log.error(
                f"  [ΑΠΟΤΥΧΙΑ PREDICTION] {study_id}\n{traceback.format_exc()}"
            )
            return None
        finally:
            del encoded_study
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()            # [MEM-1 FIX] ΕΛΕΙΠΕ

    return preds


# ─── Batch loop ───────────────────────────────────────────────────────────────
def run_batch(
    ep,
    studies: list,
    output_dir: Path,
    existing_df: pd.DataFrame = None,   # [BUG-1 FIX] περνιέται από το main()
) -> pd.DataFrame:
    """
    Επεξεργάζεται όλα τα studies και αποθηκεύει τα αποτελέσματα
    incrementally στο CSV μετά από κάθε study (crash-safe).

    [BUG-1 FIX]:
        Το existing_df (αποτελέσματα από προηγούμενη εκτέλεση σε resume mode)
        συμπεριλαμβάνεται από την αρχή στο all_rows. Έτσι κάθε incremental
        save περιέχει ΚΑΙ τα παλιά ΚΑΙ τα νέα αποτελέσματα — ποτέ δεν
        αντικαθίστανται.
    """
    results_path = output_dir / "predictions_raw_.csv"
    failed_path  = output_dir / "failed_studies.txt"

    # Ξεκίνα από existing results αν υπάρχουν (resume mode)
    if existing_df is not None and not existing_df.empty:
        all_rows = existing_df.to_dict("records")
        log.info(f"  Φορτώθηκαν {len(all_rows)} existing αποτελέσματα στη μνήμη")
    else:
        all_rows = []

    failed = []

    for i, study_path in enumerate(tqdm(studies, desc="Επεξεργασία studies", unit="study")):
        study_id = study_path.name

        preds = run_single_study(ep, study_path)

        # [MEM-1] GPU memory monitoring κάθε 50 studies
        if torch.cuda.is_available() and i % 50 == 0:
            mem = torch.cuda.memory_allocated() / 1024**2
            log.info(f"  [GPU CHECK] Study {i}: {mem:.0f} MB allocated")

        if preds is None:
            failed.append(study_id)
            continue

        row = {"study_id": study_id, **preds}
        all_rows.append(row)

        # Incremental save — περιέχει ΠΑΝΤΑ existing + νέα (crash-safe)
        pd.DataFrame(all_rows).to_csv(results_path, index=False)

    if failed:
        failed_path.write_text("\n".join(failed), encoding="utf-8")
        log.warning(f"{len(failed)} studies απέτυχαν — δες {failed_path}")

    df = pd.DataFrame(all_rows)
    log.info(f"Predictions αποθηκεύτηκαν → {results_path}  ({len(df)} studies)")
    return df


# ─── Main ─────────────────────────────────────────────────────────────────────
def main(dataset_root, output_dir, inclusion_list, device, resume,
         max_studies=None):

    dataset_root = Path(dataset_root)
    output_dir   = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # [DET-1 FIX] Set deterministic mode ΠΡΙΝ από οτιδήποτε άλλο
    SEED = 42
    set_deterministic(seed=SEED)

    # Αποθήκευση config για reproducibility
    run_config = {
        "dataset_root":   str(dataset_root),
        "output_dir":     str(output_dir),
        "inclusion_list": str(inclusion_list),
        "device":         device,
        "resume":         resume,
        "max_studies":    max_studies,    # None = όλα, N = δοκιμαστική εκτέλεση
        "seed":           SEED,
        "timestamp":      datetime.now().isoformat(),
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(run_config, indent=2), encoding="utf-8"
    )

    # Φόρτωση inclusion list
    inclusion_ids = load_inclusion_list(inclusion_list)

    # Φόρτωση μοντέλου
    # Χειρίζεται και τις δύο εκδοχές του EchoPrime.__init__:
    #   - Νέα (διορθωμένη): δέχεται device=, lang= παραμέτρους
    #   - Παλιά (original): δεν δέχεται παραμέτρους (auto-detect device)
    log.info("Φόρτωση EchoPrime μοντέλου...")
    import sys
    ECHOPRIME_DIR = r"../EchoPrime"  
    if ECHOPRIME_DIR not in sys.path:
       sys.path.insert(0, ECHOPRIME_DIR)

    from echo_prime.model import EchoPrime
    try:
         ep = EchoPrime(device=device)
         log.info(f"Μοντέλο φορτώθηκε με device={device}.")
    except TypeError:
         log.warning("EchoPrime() δεν δέχεται παραμέτρους — χρήση auto-detect device.")
         ep = EchoPrime()
         log.info("Μοντέλο φορτώθηκε (auto-detect device).")  

    # Ανακάλυψη studies
    studies = discover_studies(dataset_root, inclusion_ids)

    # [BUG-1 FIX] Resume mode:
    # Φόρτωσε existing_df ΠΡΙΝ το discover ώστε να το περάσουμε στο run_batch
    existing_df = None
    if resume:
        done_path = output_dir / "predictions_raw_.csv"
        if done_path.exists():
            existing_df = pd.read_csv(done_path)
            done_ids    = set(existing_df["study_id"].astype(str))
            before      = len(studies)
            studies     = [s for s in studies if s.name not in done_ids]
            log.info(
                f"Resume: παράλειψη {before - len(studies)} "
                f"ήδη επεξεργασμένων studies "
                f"({len(existing_df)} rows φορτώθηκαν)"
            )

    if not studies:
        log.info("Δεν υπάρχουν studies προς επεξεργασία.")
        return

    # ── Δοκιμαστική εκτέλεση (pilot mode) ────────────────────────────────
    # Αν max_studies=N, επεξεργάζεται μόνο τα πρώτα N studies.
    # Τα αποτελέσματα αποθηκεύονται σε ξεχωριστό αρχείο (pilot_predictions.csv)
    # ώστε να μην αναμειχθούν με το κύριο predictions_raw_.csv.
    if max_studies is not None:
        studies = studies[:max_studies]
        log.info(
            f"[PILOT MODE] Εκτέλεση σε {len(studies)} studies "
            f"(max_studies={max_studies})"
        )
        pilot_output_dir = output_dir / "pilot"
        pilot_output_dir.mkdir(parents=True, exist_ok=True)
        active_output_dir = pilot_output_dir
        # Στο pilot mode δεν φορτώνουμε existing_df —
        # κάθε δοκιμή είναι ανεξάρτητη
        active_existing_df = None
    else:
        active_output_dir  = output_dir
        active_existing_df = existing_df

    # [BUG-1 FIX] Πέρνα existing_df ώστε το run_batch να μην το αντικαταστήσει
    predictions_df = run_batch(
        ep,
        studies,
        active_output_dir,
        existing_df=active_existing_df,
    )

    log.info(
        f"Ολοκληρώθηκε. "
        f"Σύνολο: {len(predictions_df)} studies → "
        f"{active_output_dir / 'predictions_raw_.csv'}"
    )


# =============================================================================
#  ΡΥΘΜΙΣΕΙΣ — συμπλήρωσε τα paths σου εδώ και πάτα F5
# =============================================================================
if __name__ == "__main__":

    DATASET_ROOT   = r"data/dicom"
    OUTPUT_DIR     = r"outputs/predictions"
    INCLUSION_LIST = r"data/lists/inclusion_ids.txt"
    # Αν θες ΟΛΑ τα studies βάλε: None

    DEVICE         = "cuda"   # "cuda" αν έχεις GPU, "cpu" αλλιώς
    RESUME         = True    # True για να συνεχίσει από όπου σταμάτησε

    # ── Pilot mode ───────────────────────────────────────────────────────────
    # MAX_STUDIES = 10   → επεξεργάζεται μόνο τα πρώτα 10 studies (δοκιμή)
    #                       αποτελέσματα → OUTPUT_DIR/pilot/predictions_raw_.csv
    # MAX_STUDIES = None → επεξεργάζεται ολόκληρο το dataset (κανονική εκτέλεση)
    #                       αποτελέσματα → OUTPUT_DIR/predictions_raw_.csv
    MAX_STUDIES    = None

    main(
        dataset_root   = DATASET_ROOT,
        output_dir     = OUTPUT_DIR,
        inclusion_list = INCLUSION_LIST,
        device         = DEVICE,
        resume         = RESUME,
        max_studies    = MAX_STUDIES,
    )