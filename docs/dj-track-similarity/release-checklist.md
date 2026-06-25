# Release Readiness Checklist

This checklist is for deciding whether the current local build is ready for a
careful personal-library run. It is not a commercial release certification or a
research benchmark claim. Treat each item as a practical verification step before
using a current schema database for day-to-day DJ library work.

## Readiness Gate

Run the milestone gate from the repository root:

```powershell
.\scripts\verify_dev_milestone.ps1
```

Latest observed PR-19 gate result provided for PR-30:

- Backend non-ML pytest: `454 passed`, `3 skipped`.
- Evaluation/search regression: PASS.
- Frontend typecheck, tests, and build: PASS, including 83 frontend tests.
- Static documentation build: PASS.
- Search benchmark smoke: PASS.

The benchmark smoke report was written to a temporary path in that run. Do not
treat that exact path as a persistent artifact; rerun the gate or write a fresh
report when you need current benchmark evidence.

Use the PR-19 gate as the final broad check. For local iteration, the reduced
`-Smoke` path is useful, but it is not a substitute for the full gate before a
readiness decision.

## Migration and Schema Checks

- Confirm the target library database is schema version `4` before using
  evaluation, feedback, Hybrid judged reports, score-profile diagnostics, or ANN
  sidecar verification against it.
- For a v3 library, create a separate v4 copy instead of changing the original
  file in place:

  ```powershell
  .\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite
  .\.venv\Scripts\python.exe scripts\create_library_v4_from_v3.py --source .\data\library_v3.sqlite --dest .\data\library_v4.sqlite --apply
  ```

- Verify the dry run reports the intended source and destination before using
  `--apply`.
- Verify the source v3 file is opened read-only and kept as the rollback copy.
- Verify the destination v4 database sets `PRAGMA user_version = 4` and passes
  the script integrity check.
- Verify the v4 copy keeps existing track IDs, paths, metadata, embeddings,
  Sonara data, MAEST labels, classifier scores, likes, and other local library
  state expected from the v3 source.
- Verify v4 evaluation/calibration tables are additive local SQLite state and do
  not require audio-file inspection.
- Verify the current app reports a clear current-schema error or warning when an
  older database is selected for v4-only workflows. It should not silently
  runtime-migrate old databases.
- Use temporary databases, explicit copies, or disposable fixtures for migration
  checks. Do not test readiness on the only copy of a real library database.

## Audio Safety Invariants

- Scanning, RefreshTags, analysis, search, Hybrid preview, judged evaluation,
  benchmark smoke, reset, clear, export, and relocation preview must not modify
  audio files.
- Sonara, MAEST, MERT, CLAP, and promoted classifier scoring write SQLite data
  only. MAEST analysis stores labels and embeddings; it does not write tags by
  itself.
- Promoted classifier scoring reads existing SONARA, MERT, and MAEST data and
  writes only `track_classifier_scores` rows for the requested classifier key.
- Library relocation updates only stored SQLite `tracks.path` values after an
  explicit apply. It must preserve track IDs and analysis state, reject missing
  target files or conflicts, and never move, copy, delete, or retag audio.
- The only app-level audio tag write path is the explicit MAEST genre save
  workflow. It should overwrite only the standard genre field from reviewed
  stored MAEST labels.
- Audio Dedup report mode must remain report-only. Apply mode is outside normal
  readiness verification and should be exercised only with disposable files and
  the exact confirmation flow.
- Browser preview and media streaming must stay read-only, including any runtime
  `.aif` / `.aiff` transcoding done for playback compatibility.

## Classifier Productionization Checks

- Verify promoted classifier artifacts live under
  `models/classifiers/<artifact-prefix>/` and include both `model.joblib` and a
  valid `model.json` manifest.
- Verify invalid manifests are rejected and legacy artifacts without manifests
  produce a clear warning instead of silently mixing label definitions.
- Verify each promoted classifier is scoped by its `classifier_key`; scoring or
  resetting one classifier must not delete or recompute scores for another key.
- Verify classifier scoring requires stored SONARA, MERT, and MAEST inputs. Missing
  inputs should be skipped or rejected clearly, not decoded implicitly by the
  classifier-only path.
- Verify stored scores are presented as the promoted model's positive-label
  probability unless manifest calibration metadata explicitly says otherwise.
- Run classifier diagnostics when relevant:

  ```powershell
  dj-sim classifier calibration-report --classifier <classifier_key> --db .\data\library_v4.sqlite --output .\reports\classifier_calibration.json
  dj-sim classifier suggest-labels --classifier <classifier_key> --mode uncertainty --limit 25 --db .\data\library_v4.sqlite
  ```

- Treat `insufficient_data` diagnostics honestly. Stored classifier scores and a
  small amount of feedback are workflow hints, not validation that a classifier
  generalizes to other libraries.

## Hybrid, Risk, Feedback, and Judged Evaluation Checks

- Verify Hybrid preview remains an explicit preview path. It must not replace the
  SET, SONARA, MERT, CLAP, or CLASS workflows or change their default scoring.
- Verify Hybrid uses stored MERT, MAEST, SONARA, and CLAP analysis data only. CLAP
  in Hybrid is a stored audio-embedding source, not prompt-aware text search.
- Verify missing source coverage and missing classifier scores remain neutral or
  warned, not silently treated as negative evidence.
- Verify the default risk penalty remains `0.0`. Non-zero risk penalties should be
  chosen only after report evidence such as:

  ```powershell
  dj-sim eval sweep-risk-penalty --db .\data\library_v4.sqlite --profile .\reports\score_profile_auto.json --output .\reports\risk_penalty_sweep.json --weight 0 --weight 0.25 --weight 0.5 --weight 1.0 --k 5 --k 10 --rrf-k 60
  ```

- Verify Hybrid UI feedback writes schema-v4 pair feedback with the expected
  source and reason-tag allowlist, and that repeated ratings update existing rows
  rather than inflating counts.
- Verify judged-only reports count only feedback matched to recorded result
  events. Extra labels that cannot be tied back to a recorded result should remain
  audit data, not judged evidence.
- Use the PR-23 judged gates as guidance: fewer than 50 matched judged pairs is
  `insufficient_data`; 50-199 is diagnostics only; 200-499 may justify a candidate
  score-profile review; 500+ may justify explicit default-review consideration.
  No report updates defaults automatically.
- Verify `optimize-score-profile` is proposal-only unless `--record` or
  `--promote` is passed, and that `--promote` is guarded by the 500+ matched
  judged-pair gate and passing guardrails.

## ANN Sidecar Opt-In Checks

- Exact NumPy vector search remains the runtime default.
- Persistent ANN indexes are optional generated sidecar artifacts, not SQLite
  schema data and not required for normal search.
- Build sidecars only when explicitly needed:

  ```powershell
  dj-sim index build --adapter mert --db .\data\library_v4.sqlite
  dj-sim index verify --adapter mert --db .\data\library_v4.sqlite
  dj-sim index benchmark --adapter mert --compare exact --db .\data\library_v4.sqlite
  ```

- Verify sidecar manifests reject stale indexes after embedding reset,
  reanalysis, database changes, model changes, or track/vector mismatches.
- Verify ANN benchmark recall meets the local threshold before enabling any
  explicit ANN path for interactive use. The documented default Recall@K threshold
  is `0.97`.
- Verify `dj-sim text-search --use-ann-index` remains an explicit CLAP sidecar
  opt-in and falls back to exact search with a warning when the sidecar is
  missing, stale, or unsupported.
- Verify `dj-sim index clear` removes only generated sidecar files in the resolved
  sidecar directory and does not touch SQLite or audio files.

## Backend, Frontend, and Documentation Checks

- Run the full milestone gate before final readiness:

  ```powershell
  .\scripts\verify_dev_milestone.ps1
  ```

- Confirm the backend non-ML test suite, evaluation/search regression checks,
  frontend typecheck/tests/build, documentation build, and benchmark smoke all
  pass in the same run.
- Confirm frontend API contracts still match backend request and response shapes
  for analysis jobs, classifier jobs, Hybrid preview, feedback, judged reports,
  ANN commands surfaced through CLI documentation, and schema errors.
- Confirm docs are current for database schema, analysis families, classifier
  diagnostics, Hybrid/risk/evaluation workflows, ANN sidecars, CLI examples, and
  environment notes.
- Rebuild static HTML docs after Markdown changes under
  `docs/dj-track-similarity/`:

  ```powershell
  cd docs\dj-track-similarity
  npm run build
  ```

## Optional Dependencies and Environment Notes

- FFmpeg is required for server startup and robust audio decoding. It must be on
  `PATH` or set through `DJ_TRACK_SIMILARITY_FFMPEG`.
- On Windows, TorchCodec-backed Torchaudio decoding requires a shared FFmpeg build
  with DLLs on `PATH`; a standalone static `ffmpeg.exe` is not enough for that
  path.
- CUDA is optional. CPU remains valid for small or patient local analysis runs.
- The verified Windows CUDA stack is PyTorch `2.11.0`, Torchaudio `2.11.0`,
  Torchvision `0.26.0`, TorchCodec `0.13.0`, `numpy>=1.26,<2.0`, and the
  `cu130` PyTorch wheel index.
- The `ml` extra is required for MAEST, MERT, and CLAP analysis. The `sonara`
  extra is required for Sonara analysis. The `rhythm-lab` extra is required for
  local classifier training. The `ann` extra is required only when building HNSW
  sidecar indexes.
- `hnswlib` is optional. If it is absent, exact search still works and remains the
  default.

## Not Covered by the Gate

- Human DJ taste is not validated by the automated gate. Judged evaluation needs
  meaningful local feedback and enough matched judged pairs.
- Long real-library ML throughput, VRAM limits, and thermal behavior depend on the
  local machine and are not proven by the non-ML readiness gate.
- The gate does not prove every audio container/tag edge case. Keep tag writing
  limited to explicit reviewed genre saves and use disposable copies for unusual
  file-format checks.
- The gate does not verify destructive maintenance paths against real files. Keep
  Audio Dedup apply and repair-script apply checks on disposable fixtures unless a
  user explicitly chooses otherwise.
- Optional ANN sidecar quality is local to a database, embedding set, backend, and
  sidecar manifest. Rebuild and re-benchmark after analysis resets, reanalysis, or
  database changes.
