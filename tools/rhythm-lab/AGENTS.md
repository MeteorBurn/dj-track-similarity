# Rhythm Lab Notes

Standalone classifier labeling / training / promotion UI + CLI. Independent safety domain — see root `AGENTS.md`.

## Boundaries

- Not part of the main Python package: no shared `pyproject.toml`, script tree.
- CLI entry: `tools/rhythm-lab/rhythm_lab_cli.py` → `rhythm_lab.cli.main()`. Subcommands: `serve`, `train`, `predict`, `promote`, calibration/report, queue/collection management, profile delete.
- Package: `tools/rhythm-lab/rhythm_lab/` — `cli.py`, `web_app.py` (FastAPI at `127.0.0.1:8777`), `training.py`, `predictions.py`, `features.py`, `lab_db.py`, `source_db.py`, `ablation.py`, `static/`.
- Bridge from main app: `src/dj_track_similarity/rhythm_lab_launcher.py` (launch/status/stop) and `src/dj_track_similarity/rhythm_lab_collections.py` (save current set as a Lab collection).

## Source Database Boundary

- The main library SQLite is opened via `source_db.py` MOSTLY READ-ONLY. The one exception is the explicit liked-track toggle, which updates `likes` on the source DB. No other write path to the main DB.
- All labels, predictions, training queue rows, checkpoints, metrics, and calibration data live in the lab DB at `tools/rhythm-lab/data/rhythm_lab.sqlite`.
- Do not add other main-DB write paths from any Rhythm Lab code.

## SONARA Contract Guard

- `lab_db.py` deletes stale SONARA-dependent predictions when the SONARA feature revision changes; labels and feedback are preserved.
- `training.py` refuses to train SONARA-dependent classifiers when the current SONARA signature does not match the labeled data.
- `cli.py` blocks `promote` on stale artifacts until they are retrained (and optionally recalibrated) against the current SONARA signature.
- MERT-, MAEST-, MuQ-, or CLAP-only profiles are independent of SONARA and are not invalidated by a SONARA revision.

## Artifacts and Promotion

- Training artifacts stay under `tools/rhythm-lab/artifacts/<profile>/` (gitignored). Never commit.
- Promotion copies `model.joblib` + `model.json` to `models/classifiers/<profile>/` (also gitignored). These are read by `src/dj_track_similarity/classifier_scoring.py`.
- Promoted classifier scoring in the main app is scoped by `classifier_key` and writes only that classifier's rows in `classifier_scores`. Rhythm Lab must not touch other classifiers' scores.

## Profile Delete

- `Delete` is destructive and profile-scoped: removes labels, predictions, queue, checkpoints, metrics, and local artifacts for that profile. Promoted runtime models under `models/classifiers/` are left in place (delete them manually if desired).
- UI/CLI asks for exact profile name or key confirmation; keep that gate.

## Testing

- `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=` (root pytest does not collect this).
- Include `tests\test_break_energy.py` from the main suite when touching promoted-classifier scoring boundaries (per root `AGENTS.md`).
