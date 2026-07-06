# Agent Instructions

## Purpose And Source Of Truth

`dj-track-similarity` is a public personal/enthusiast project for local DJ music-library analysis,
similarity search, set preparation, and safe helper tools. Keep public claims practical and modest:
this is not a polished commercial product or research benchmark.

## Product North Star

The project north star is **local-first DJ set dramaturgy**, not generic recommendation or simple
nearest-neighbor search. Keep implementation, UI, and documentation oriented around helping a DJ
rediscover a large local library, choose reference tracks or text themes, and build playable sets that
move like a story: technically mixable, sonically coherent, and able to move gradually between moods,
chapters, tension, release, and a final destination.

Similarity search, CLAP text search, SONARA feature matching, Smart Set Builder, Hybrid preview, and
personal classifiers are means toward that narrative flow. Do not reduce the project to "find similar
tracks," and do not claim finished automatic DJ/story generation unless current source and UI behavior
support it. The practical goal is listening-led shortlisting and set preparation: the system proposes
candidates, explains signals, and leaves the final musical decision to the DJ.

Preserve the author's modest stance. The project is built by an enthusiast who does not claim expert
knowledge of ML models or music information retrieval. Make explanations inspectable, avoid inflated
ML claims, and treat model outputs as local ranking signals rather than objective truth.

Verify behavior from current source, tests, schemas, and runtime evidence. Docs are navigation aids,
not authority for logic, commands, API contracts, database fields, analysis outputs, UI workflows,
Rhythm Lab behavior, or maintenance scripts.

User-facing docs are English unless the user asks otherwise. The English entrypoint is
`docs/dj-track-similarity/project-guide.md`; follow linked topic pages instead of duplicating long
references here. The tracked documentation surface is `README.md` plus the VitePress tree under
`docs/dj-track-similarity/`; there is currently no tracked localized README or VitePress localization.
Treat documentation as maintained project surface: when behavior, commands, API contracts, UI workflows,
tools, safety rules, setup steps, or verification commands change, update the relevant README/docs pages
in the same implementation pass. `README.md` is the public repository landing page, not an exhaustive
reference: keep it clear, modest, workflow-oriented, and linked to the real docs tree.

For local manual checks against the real library, use `C:\db\abstracted.sqlite` unless the user gives
another path. This workspace may not always be a Git repo, so inspect before relying on branches,
history, or commits.

## Repo Map

- `src/dj_track_similarity/`: backend, CLI, FastAPI routes, SQLite access, scanning, analysis,
  embeddings, classifiers, search, exports, tags, media preview, logging, and runtime helpers.
- `frontend/`: React/Vite/TypeScript main UI. `frontend/src/api.ts` mirrors backend contracts;
  `frontend/dist` is the backend-served bundle.
- `tests/`: backend/API/search/jobs/tags/evaluation pytest coverage.
- `scripts/`: focused maintenance and benchmark scripts plus tests.
- `docs/dj-track-similarity/`: VitePress source; `npm run build` writes ignored `site/` output.
- `tools/rhythm-lab/`: standalone classifier labeling/training UI and CLI.
- `tools/audio-doctor/`: dry-run-first metadata/container diagnostic and repair helper plus UI jobs.
- `tools/audio-dedup/`: duplicate-audio candidate reporter plus explicit confirmed cleanup mode.
- `logs/`: runtime logs only; keep `.gitkeep`, never commit generated `*.log`.

Hot paths: `database.py`/`db_*` own SQLite; `api.py`, `api_schemas.py`, and `api_routes_*.py` own
HTTP contracts; `cli.py` owns Typer commands; `scanner.py`, `audio_loader.py`, `sonara_features.py`,
`genres.py`, `embedding.py`, `analysis_jobs.py`, `classifier_scoring.py`, `set_builder.py`,
`sonara_similarity.py`, `tags.py`, `wave_tags.py`, and `media_preview.py` own safety-sensitive logic.

## Generated And Local Artifacts

Do not commit generated local state: `*.sqlite`, `*.log`, `__pycache__/`, `.pytest_cache/`,
virtualenvs, `frontend/node_modules/`, temp folders, `frontend/dist` unless explicitly requested, or
`docs/dj-track-similarity/site/`.

Keep only source, README files, and `.gitkeep` placeholders under generated data areas. Audio Doctor
state/reports/backups under `tools/audio-doctor/data/`, duplicate reports under
`tools/audio-dedup/data/reports/`, Rhythm Lab data under `tools/rhythm-lab/data/`, Rhythm Lab
artifacts under `tools/rhythm-lab/artifacts/*/`, and promoted local classifier assets under
`models/classifiers/*/model.joblib` and `models/classifiers/*/model.json` stay out of git unless the
user explicitly changes that policy.

Runtime logs written by the main app or launched helpers live under `logs/`. `logs/dj-track-similarity.log`
owns startup-only daily rotation: if its first logged date is older than the current date at startup,
the active project `logs/*.log` files get the same dated suffix, sibling logs are truncated, and old
backups are pruned with the same retention rule. A server that runs through midnight keeps writing to
the active log until the next launch. Future app-started logs should use `logs/<name>.log`.

## Safety Invariants

### Audio Files And Tags

- Treat real audio as user data. Scanning, RefreshTags, analysis, search, preview, reset, clear,
  relocation preview, and export must not modify audio.
- Browser preview may transcode `.aif`/`.aiff` to a temporary WAV for `/media/{track_id}`; this is
  read-only streaming and must not rewrite or cache source audio.
- `/api/tags/genres/apply` is the explicit app-level standard-tag write path. It overwrites only the
  standard genre field from stored MAEST labels and preserves title, artist, album, BPM, key, and
  other normal tags.
- Genre writes are upserts to one normalized `;`-separated MAEST genre string: `TCON` for MP3/WAV/AIFF
  ID3, `GENRE` for FLAC/Vorbis-style tags, and `\xa9gen` for MP4/M4A/ALAC.
- WAV genre writing must use Mutagen WAVE/ID3 handling and read back `TCON`. Do not add custom RIFF
  repair/validation to the app tag-write path; failed WAV writes should fail that track and let the
  batch continue.

### SQLite And Destructive State

- Route SQLite writes through `LibraryDatabase`, with the shared path-scoped write lock, WAL, and busy
  timeout so scan, RefreshTags, SONARA, MAEST, MERT, MUQ, CLAP, reset, relocation, and classifier writes
  queue safely.
- Treat `dj-track-similarity.sqlite` as local user state. Tests must use temp DBs via `tmp_path` or
  explicit `--db`.
- Library relocation updates only stored `tracks.path` values. It must be previewable, reject missing
  target files and conflicts on apply, preserve track IDs plus analysis/tag metadata, and never
  move/copy/delete/retag audio.
- Reset controls are database-only per analysis family. Database clear deletes SQLite records only and
  must require explicit UI confirmation.
- Destructive SQLite maintenance on real DBs needs a backup or copied DB first, must rebuild affected
  FTS state such as `track_search_fts`, and should finish with integrity/orphan checks.

### Audio Doctor And Audio Dedup

- `tools/audio-doctor/audio_doctor_cli.py` is dry-run-first. `--apply` may rewrite only files
  previously reported as `REPAIRABLE`, runs sequentially, and creates full-file backups by default.
  UI/API apply mode must require exact `APPLY REPAIR` confirmation and should run from prior dry-run
  state.
- `tools/audio-doctor/audio_doctor_cli.py --db` opens the selected SQLite library read-only, reads
  existing `tracks.path`, may remap roots with `--db-root` plus `--file-root`, and skips missing
  remapped files.
- `tools/audio-dedup/audio_dedup_cli.py` is report-only by default. It opens SQLite read-only and writes
  JSON/XLSX/log reports under `tools/audio-dedup/data/reports/`.
- Audio Dedup `min_similarity` is an audio-to-audio content gate over stored MERT, MAEST, and CLAP
  audio embeddings. Do not weaken duplicate thresholds or safety decisions because CLAP text-search
  scores are lower; CLAP prompt scores are a different text-to-audio scoring surface. Do not add MuQ
  to Audio Dedup scoring unless that is an explicit future feature.
- Audio Dedup `--apply` must prompt for exact `APPLY DELETE`, delete only safe duplicate candidates
  inside selected `--root`, and remove SQLite rows only for tracks whose files were deleted. UI apply
  mode requires the same confirmation. Do not invoke apply mode in tests or routine checks.

### Classifiers And Rhythm Lab

- Promoted classifier scoring is database-only. It reads existing SONARA features plus MERT and MAEST
  embeddings, writes only `track_classifier_scores`, and must not decode or modify audio.
- Promoted classifier scoring is scoped by `classifier_key`. Adding or promoting one classifier scores
  only missing rows for that classifier and must not delete or recompute scores for other classifiers.
- After retraining and promoting a classifier, scores for that same `classifier_key` may be stale from
  an older `model_id`; reset only that classifier's `track_classifier_scores` rows before rescoring.
- Missing classifier scores stay neutral. Malformed manifests block scoring clearly. Production
  manifests should carry `model_id`, `artifact_hash`, `promoted_at`, `production.calibration`, and
  `production.required_inputs`.
- Rhythm Lab never writes source audio. It opens the main SQLite DB read-only for browsing, analysis
  metadata, training inputs, and preview. Its only source-DB write path is the explicit liked-track
  toggle via `LibraryDatabase`; labels, predictions, and checkpoints stay under `tools/rhythm-lab/data/`.
- Rhythm Lab uses `classifier_labels`, `classifier_predictions`, and `classifier_training_checkpoints`,
  all scoped by `classifier_key`. Do not reintroduce `rhythm_*` tables except in a one-way migration
  that removes them after copied data is verified.

### Runtime, Subprocesses, And Dependencies

- Server startup requires `ffmpeg` on `PATH` or `DJ_TRACK_SIMILARITY_FFMPEG`; keep missing-ffmpeg errors
  clear and actionable.
- Before starting local UI/server processes, check for existing listeners and matching project
  processes. Keep one instance per fixed port: main backend `8765`, Vite frontend `5173`, Rhythm Lab
  `8777`.
- When Codex needs to start the main backend/UI for this workspace and no matching process is already
  running, use the user's normal LAN launcher: `.\run_server.cmd lan --db C:\db\abstracted.sqlite`.
  If that server is already running, connect to it instead of launching another copy.
- TorchCodec-backed Torchaudio decoding on Windows requires an FFmpeg shared build with DLLs on `PATH`;
  the verified portable build is GyanD `ffmpeg 8.1.1-full_build-shared` under `C:\Utils\tools\ffmpeg\bin`.
- Verified Windows CUDA ML stack: PyTorch `2.11.0`, Torchaudio `2.11.0`, Torchvision `0.26.0`,
  TorchCodec `0.13.0`, nnaudio, CUDA wheel index `cu130`, and `numpy>=1.26,<2.0`. Keep PyTorch-family
  packages synchronized unless a dependency upgrade is deliberate.
- MuQ is an optional ML dependency through `muq==0.1.0`. The official package depends on `librosa`, but
  project code must not import or call `librosa` for MuQ analysis; use the shared decode path and
  `torchaudio` resampling.

## Runtime And UI Contracts

### Analysis

- Mutagen scan and RefreshTags read only the fixed human-relevant metadata whitelist and update SQLite
  only. Stored metadata must be JSON-safe.
- SONARA writes only SQLite metadata (`sonara_features`, `sonara_model`) plus derived working
  BPM/key/duration/energy fields. SONARA BPM/key are analyzed values, not copied file tags.
- Keep SONARA database keys canonical (`*_mean` stays in SQLite). Friendly UI labels may omit `mean`,
  but do not rename stored keys or derive Camelot data. Do not store placeholder `unavailable` rows,
  helper diagnostics, or `chord_sequence` in SONARA playlist storage.
- Shared audio loading is native-first: SONARA starts with `sonara.analyze_file`; SONARA fallback,
  MAEST, MERT, MUQ, and CLAP use the shared loader (`torchaudio` with TorchCodec when provided, Python
  `wave` for WAV, then `ffmpeg`).
- MAEST writes only SQLite metadata and uses the three-window 30-second policy with direct
  `model(audio_batch, melspectrogram_input=False)` logits, not `predict_labels()` for batch work.
- MERT, MUQ, CLAP, and MAEST use one selected device plus inference batching. `auto` picks CUDA when PyTorch
  sees a GPU; explicit `cuda` must error if unavailable.
- MuQ writes only stored `embedding_key='muq'` embeddings and the `tracks.has_muq_embedding` status flag.
  MuQ inference must stay `24_000 Hz` and `torch.float32` on CPU or CUDA: no `half()`, `bf16`, autocast,
  `torch.compile`, or project-level `librosa` decode. It is not a SET, Hybrid, search, classifier, ANN,
  or complete-analysis requirement unless a future task explicitly adds that behavior.
- In the UI, `Analyze limit = 0` means whole library. Positive limits count missing results for the
  selected analysis family.

### Search, SET, SONARA, And CLASS

- Search UI stays split into SET, SONARA, MERT, CLAP, and CLASS tabs; MuQ currently has no search tab.
- SET calls `/api/set-builder/generate` and is read-only preview generation. Manual mode uses `1-5`
  selected seeds and rejects manual seeds with the same known artist. Auto mode samples the first anchor
  from the full feature-complete library, then samples remaining waypoint anchors from related candidates.
  Preview enters the current set only through explicit user action.
- Smart Set Builder requires stored MERT, MAEST, and CLAP audio embeddings plus stored SONARA features.
  It may use MAEST embeddings, but must not use MAEST genre labels or MuQ embeddings for track selection.
- Smart Set Builder BPM/key are soft transition-ordering signals. BPM resolution prefers stored SONARA
  BPM when available, then falls back to file tag BPM. Default `bpm_mode=general` keeps normal
  transition rules only; `low_to_high` and `high_to_low` add actual-BPM trajectory with
  `bpm_change=slow|medium|fast` and optional `bpm_start` / `bpm_target`. Missing values are inferred
  from the first seed/anchor and library BPM range.
  Half/double tempo matching is for transition compatibility, not actual-BPM trajectory.
- Promoted classifiers are optional stored-score modifiers in SET. Missing scores stay neutral. Keep
  the artist guard strict: at most one track per known artist in one preview.
- SET controls must stay explicitly labeled with hover help for purpose, type/format, and range. Current
  controls include `Seed source`, `Set mode`, `Track limit`, `Auto anchors`, `Energy curve`, `Diversity`,
  `BPM mode`, `BPM change`, `Start BPM`, `Target BPM`, classifier `Target boost`, `Avoid cut`,
  `Curve start`, `Curve end`, and `Reset sliders`.
- SONARA custom search sends mixer/modifier payloads to `/api/search/sonara`. MERT seed search uses
  `/api/search`; CLAP text search uses `/api/search/text` and requires `clap` embeddings.
- CLAP text search scores are raw text-to-audio cosine or contrast evidence, usually lower than
  seed-based audio-to-audio scores. Keep CLAP text-search threshold state separate from MERT/SONARA
  similarity controls, keep the visible `Similarity` label if requested, and explain the scale in
  hover help/docs instead of renaming it casually.
- SET, Hybrid, and Audio Dedup use stored CLAP audio embeddings as audio-to-audio signals. Do not treat
  those values as interchangeable with CLAP prompt/text-search scores. MuQ embeddings are stored for
  future work and should not enter these ranking paths in the current contract.
- SONARA search should read analyzed tracks through `LibraryDatabase.load_sonara_feature_rows()` so
  repeated searches reuse parsed feature rows. Keep cache work behavior-preserving: do not change scoring math,
  feature ranges, or ordering. Invalidate the cache whenever track rows, metadata, SONARA features,
  resets, clears, or relocation updates can affect results.
- CLASS discovers promoted local profiles from `models/classifiers/*/model.json`. Per-classifier controls
  should call the single-classifier scoring path for that profile and preserve other classifier keys.

### Library, Metadata, And Rhythm Lab UI

- Keep library browsing scalable: `/api/tracks` stays server-side paginated/searchable with lightweight
  rows, `/api/library/summary` provides counters, and `/api/tracks/{id}` loads full metadata only on
  dialog open.
- Metadata dialog keeps Mutagen tags, SONARA features, MAEST genres, and classifier scores visually
  separate; preserve source boundaries and display order.
- Rhythm Lab profiles support `profile_type = "binary"` and `profile_type = "multiclass"`. Binary
  profiles use exactly one positive and one negative training label plus optional review labels.
  Multiclass profiles use `class` labels only, support arbitrary classes, and one track can hold only one
  current label for the active profile.
- Rhythm Lab artifacts are classifier-scoped under `tools/rhythm-lab/artifacts/<artifact-prefix>/`;
  promoted runtime models stay under `models/classifiers/<artifact-prefix>/`.
- Rhythm Lab training benchmarks `sonara`, `mert`, `maest`, and `combined`. `combined` requires existing
  SONARA features plus MERT and MAEST embeddings. Keep SONARA in this path, do not add MuQ to Rhythm Lab
  features without an explicit feature-contract change, and expose SONARA, MAEST, and MERT coverage
  counters.
- Rhythm Lab `train-refresh` is readiness-gated by newly added labels since the last training checkpoint.
  Use CLI `train` for forced retrain on the same label set instead of weakening the UI gate.
- Classifier calibration is opt-in. `--calibrate` may fit calibrated binary classifiers with enough data
  (currently at least 100 labels total, 20 positive, 20 negative). Otherwise training still produces an
  uncalibrated artifact with a diagnostic report. Use `promote --require-calibration` only intentionally.

## Development Workflow

- Keep Python compatible with 3.10+ and follow existing module patterns.
- Keep edits scoped. Inspect before editing when behavior, safety, or repo state matters. Preserve
  unrelated worktree changes.
- Prefer durable current behavior over legacy compatibility. Do not add fallback paths, compatibility
  shims, or parallel old/new behavior unless the user asks.
- Keep FastAPI request/response shapes aligned with `frontend/src/api.ts`.
- If changing scan/analysis job state, update backend tests plus frontend polling/display logic.
- If changing Mutagen tags, SONARA features, MAEST jobs, classifier jobs, audio decoding, search, library
  browsing, relocation, analysis controls, SQLite writes, UI controls, custom tags, or standard genre
  writes, update the focused tests, frontend/API surfaces, and `docs/dj-track-similarity/` pages.
- For user-facing behavior, CLI/API contracts, setup, verification, helper tools, safety invariants, and
  supported workflows, keep tracked `README.md` and `docs/dj-track-similarity/` Markdown current in the
  same implementation pass. If a source change does not require docs, the final response should make
  that no-docs-needed decision explicit. Do not build the static docs site just to satisfy this docs
  update requirement; build the site only when previewing, deploying, or explicitly asked.
- Documentation command examples in `README.md` and `docs/dj-track-similarity/` assume the Python
  environment is already activated. Do not write commands there with `.\.venv\Scripts\python.exe`;
  use `python ...` or the installed console script instead.
- Use deterministic test data and test-local stub adapters; automated tests should not depend on the real
  user music library.
- After frontend source changes, run `npm run build` from `frontend/`.
- When Markdown under `README.md` or `docs/dj-track-similarity/` changes, use Vale as the public docs
  style check. Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages change.
  Then run `npm run check` from `docs/dj-track-similarity/`; it checks `README.md` plus the VitePress
  Markdown tree with strict Vale failures and builds the static docs. Use `npm run lint:style` only when
  you want a non-failing style report while editing. If generated docs are absent, the backend should
  show a clear "documentation is not built" page.

## Plugin And External Tool Routing

- Superpowers: use workflow skills for non-trivial planning, TDD, debugging, implementation-plan
  execution, branch finishing, and verification discipline; do not let skill ceremony expand narrow work.
- Codex Security: use security-scan/review/fix skills when the user asks for security work. For normal
  edits, preserve invariants around audio mutation, SQLite writes, destructive apply modes, subprocesses,
  secrets, and generated artifacts.
- OpenAI Developers: use official OpenAI/Codex docs when changing OpenAI API, SDK, ChatGPT Apps, Codex,
  or `AGENTS.md` behavior. For OpenAI API-backed code or `OPENAI_API_KEY` work, use the secure Platform
  connector flow and never print plaintext secrets.
- GitHub: resolve local branch/upstream with `git` first for current-checkout work, then use GitHub tools
  or `gh` for PRs, issues, Actions, and remote metadata. For publish requests from a mixed tree, inspect
  status/diff first, stage only intended files, and keep push-only separate from commit+push. Current
  remote is `https://github.com/MeteorBurn/dj-track-similarity`.

## Common Commands

Use the project-local venv when present: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`,
`.\.venv\Scripts\python.exe -m pytest`, and the focused pytest commands in the verification matrix.

Common local runs: `dj-sim serve --host 127.0.0.1 --port 8765`, `run_server.cmd local`,
`cd frontend; npm run build; npm run dev`, and `cd docs\dj-track-similarity; npm run check`.

Focused CLI examples: `dj-sim scan <path-to-music> --db .\data\library.sqlite`,
`dj-sim analyze --models sonara,maest,mert,clap --limit 3 --db .\data\library.sqlite`,
`dj-sim analyze-classifier live_instrumentation --limit 3 --db .\data\library.sqlite`,
`dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 5 --db .\data\library.sqlite`,
`dj-sim relocate-library .\music-old .\music-new --apply --db .\data\library.sqlite`, and
`dj-sim doctor`.

Rhythm Lab examples: `.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite`,
`.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite`,
and `.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite`.

## Verification Matrix

- Instruction-only edits: inspect `git diff -- AGENTS.md`, run `git diff --check -- AGENTS.md`, and verify
  sentinel contracts with `rg`. Do not run backend/frontend tests unless source or docs behavior changed.
- Backend changes: run focused pytest for touched behavior; use full `.\.venv\Scripts\python.exe -m pytest`
  for broad/shared changes.
- Frontend changes: run `npm run build` in `frontend/`; add targeted `npm test` or `npm run typecheck`
  when the touched area needs it.
- API contract changes: exercise the affected endpoint through tests or a local server, and align
  `frontend/src/api.ts`.
- CLI changes: run the specific `dj-sim ...` command with a temp DB when practical.
- Docs changes: run `npm run check` from `docs/dj-track-similarity/` when touching public Markdown or
  docs config. It runs strict Vale style checking and the site build. For style-only
  exploration, `npm run lint:style` is enough because it reports findings without failing.
- Rhythm Lab changes: run `.\.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=`.
  For promoted classifier scoring boundaries, include `tests\test_break_energy.py`.
- Classifier train/promote hardening: copy source and labels DBs with the SQLite backup API, run
  `rhythm_lab_cli.py train --calibrate`, promote with `--require-calibration` into a temp target, reset
  only that copied classifier's scores, then run `dj-sim analyze-classifier --model <temp model> --limit 5`
  against the copied source DB.
- Audio Doctor changes: run `.\.venv\Scripts\python.exe -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=`.
- Audio Dedup changes: run `.\.venv\Scripts\python.exe -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=`.
- Relocation changes: verify dry-run does not modify paths, apply preserves IDs and analysis state, and
  conflicts/missing files block apply.
- SONARA changes: prefer stubbed helpers or small temp WAV fixtures; never rely on a real user music
  library in automated tests.
