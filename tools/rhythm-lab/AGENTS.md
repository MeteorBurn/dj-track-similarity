# Rhythm Lab Notes

Standalone classifier labeling / training / promotion UI + CLI. Independent safety domain — see root `AGENTS.md`.

## Active Development

- The root evolution policy applies. Feature families, recipes, aliases,
  storage layout, artifact formats, UI structure, CLI commands, and promotion
  flow are current implementation rather than permanent contracts.
- Requested changes may replace or reorganize them. Prefer shared registries
  and data-driven recipes over duplicated family lists and hard-coded readiness
  checks; coordinate Lab storage, runtime consumers, tests, and docs.
- The source-database and destructive-action rules below are the default safety
  baseline. An owner-directed redesign is allowed only when the new write
  scope, confirmation, recovery, and verification behavior are explicit.

## Current Boundaries

- Not part of the main Python package: no shared `pyproject.toml`, script tree.
- CLI entry: `tools/rhythm-lab/rhythm_lab_cli.py` → `rhythm_lab.cli.main()`. Subcommands: `serve`, `train`, `predict`, `promote`, calibration/report, queue/collection management, profile delete.
- Package: `tools/rhythm-lab/rhythm_lab/` — `cli.py`, `web_app.py` (FastAPI at `127.0.0.1:8777`), `training.py`, `predictions.py`, `features.py`, `artifact_io.py`, `label_transfer.py`, `lab_db.py`, `source_db.py`, `ablation.py`, `static/`.
- Bridge from main app: `src/dj_track_similarity/rhythm_lab_launcher.py` (launch/status/stop) and `src/dj_track_similarity/rhythm_lab_collections.py` (save current set as a Lab collection).

## Current Source Database Boundary

- The main library SQLite is opened via `source_db.py` MOSTLY READ-ONLY. The one exception is the explicit liked-track toggle, which updates `likes` on the source DB. No other write path to the main DB.
- Labels, predictions, training queue rows, checkpoints, metrics, and
  calibration data live in the configured lab database under
  `tools/rhythm-lab/data/`. Storage layout and migrations may evolve when
  requested; test changes with temporary databases.
- Do not add other main-DB write paths from any Rhythm Lab code.

## Current Feature Sources

- Active embedding families and feature-name rules live in `features.py` and
  current runtime data. Extend or replace them through the shared source rather
  than duplicating a permanent family list.
- `combined` currently aliases `sonara+mert+maest`. It may be renamed or
  redefined through an explicit migration, but do not silently change existing
  profile meaning.
- Generic `source+source` combinations and the default ablation matrix are
  current tunable behavior. Use explicit recipes for expensive combinations
  and update source-driven selectors/tests when defaults change.
- Readiness follows the selected feature set's available sources. MuQ is needed
  only for a MuQ-containing recipe; missing inputs should not block unrelated
  recipes.

## Current Artifacts and Promotion

- Training artifacts stay under `tools/rhythm-lab/artifacts/<profile>/` (gitignored). Never commit.
- Promotion currently publishes a generation under
  `models/classifiers/<classifier_key>/generations/<generation_id>/` and
  atomically updates `current.json`. Artifact layout and format may evolve, but
  runtime readers must never observe a mixed model/manifest pair; preserve
  atomicity or provide a verified equivalent.
- Promoted classifier scoring in the main app is scoped by `classifier_key` and writes only that classifier's rows in `classifier_scores`. Rhythm Lab must not touch other classifiers' scores.

## Profile Delete

- `Delete` is destructive and profile-scoped: removes labels, predictions, queue, checkpoints, metrics, and local artifacts for that profile. Promoted runtime generations under `models/classifiers/` are left in place (delete them manually if desired).
- UI/CLI currently require explicit profile-scoped confirmation. Keep the
  owning definition centralized; a requested redesign must retain unambiguous
  destructive intent and update both entry points together.

## Current Static UI

- `static/index.html`, `static/app.js`, and `static/styles.css` are a separate frontend surface. Keep visible feature-source copy and selectors aligned with `features.py`.
- Do not use a global hardcoded SONARA/MERT/MAEST readiness check. Compute readiness from the selected recipe and show per-source missing/stale reasons without blocking unrelated recipes.
- UI changes do not authorize training, promotion, prediction, or source-DB writes automatically.

## Testing

- `python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=` (root pytest does not collect this).
- Include `tools\rhythm-lab\tests\test_consumers.py` when changing feature-source handling.
- Include `tests\test_break_energy.py` from the main suite when touching promoted-classifier scoring boundaries (per root `AGENTS.md`).
