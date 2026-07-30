# Rhythm Lab Notes

Standalone classifier labeling / training / promotion UI + CLI. Independent safety domain — see root `AGENTS.md`.

## Boundaries

- Not part of the main Python package: no shared `pyproject.toml`, script tree.
- CLI entry: `tools/rhythm-lab/rhythm_lab_cli.py` → `rhythm_lab.cli.main()`. Subcommands: `serve`, `train`, `predict`, `promote`, calibration/report, queue/collection management, profile delete.
- Package: `tools/rhythm-lab/rhythm_lab/` — `cli.py`, `web_app.py` (FastAPI at `127.0.0.1:8777`), `training.py`, `predictions.py`, `features.py`, `artifact_io.py`, `label_transfer.py`, `lab_db.py`, `source_db.py`, `ablation.py`, `static/`.
- Bridge from main app: `src/dj_track_similarity/rhythm_lab_launcher.py` (launch/status/stop) and `src/dj_track_similarity/rhythm_lab_collections.py` (save current set as a Lab collection).

## Source Database Boundary

- The main library SQLite is opened via `source_db.py` MOSTLY READ-ONLY. The one exception is the explicit liked-track toggle, which updates `likes` on the source DB. No other write path to the main DB.
- Labels, predictions, training queue rows, checkpoints, metrics, and
  calibration data live in the configured lab database under
  `tools/rhythm-lab/data/`. Storage layout and migrations may evolve when
  requested; test changes with temporary databases.
- Do not add other main-DB write paths from any Rhythm Lab code.

## Feature Sources

- Canonical embedding feature sources are MERT, MAEST, CLAP, and MuQ. Feature
  names use `<family>:<index>` and dimensions come from the active runtime data.
- `combined` remains the compatibility alias for `sonara+mert+maest`. Do not silently redefine it to mean every available source.
- Generic `source+source` combinations are supported. The default ablation list preserves its legacy matrix and adds representative MuQ sets (`muq`, `sonara+muq`, `mert+muq`, and the full MuQ combination); use explicit `--feature-set` values for other expensive combinations.
- Readiness follows the selected feature set's available sources. MuQ is needed
  only for a MuQ-containing recipe; missing inputs should not block unrelated
  recipes.

## Artifacts and Promotion

- Training artifacts stay under `tools/rhythm-lab/artifacts/<profile>/` (gitignored). Never commit.
- Promotion publishes an immutable generation under `models/classifiers/<classifier_key>/generations/<generation_id>/` with a bound `model.joblib` + `model.json`, then atomically updates `current.json`. Never expose a mixed model/manifest pair or bypass staged validation. Promoted generations are read by `src/dj_track_similarity/classifier_scoring.py`.
- Promoted classifier scoring in the main app is scoped by `classifier_key` and writes only that classifier's rows in `classifier_scores`. Rhythm Lab must not touch other classifiers' scores.

## Profile Delete

- `Delete` is destructive and profile-scoped: removes labels, predictions, queue, checkpoints, metrics, and local artifacts for that profile. Promoted runtime generations under `models/classifiers/` are left in place (delete them manually if desired).
- UI/CLI asks for exact profile name or key confirmation; keep that gate.

## Static UI

- `static/index.html`, `static/app.js`, and `static/styles.css` are a separate frontend surface. Keep visible feature-source copy and selectors aligned with `features.py`.
- Do not use a global hardcoded SONARA/MERT/MAEST readiness check. Compute readiness from the selected recipe and show per-source missing/stale reasons without blocking unrelated recipes.
- UI changes do not authorize training, promotion, prediction, or source-DB writes automatically.

## Testing

- `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=` (root pytest does not collect this).
- Include `tools\rhythm-lab\tests\test_consumers.py` when changing feature-source handling.
- Include `tests\test_break_energy.py` from the main suite when touching promoted-classifier scoring boundaries (per root `AGENTS.md`).
