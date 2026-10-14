# Model layer contracts and ownership

Read before running, changing or reviewing models, audio inference, loaders,
jobs, caches, output storage/readiness, text/seed search, ranking, classifier
signals or their shared backend/frontend contracts.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and paths are
relative to the repository root, except shortened Python module paths, which
are relative to `src/dj_track_similarity/`. Markdown links are relative to this
file. Read related guides only for the matching task.

## MODEL LAYER OWNERSHIP

- scikit-learn is a required project-wide dependency managed in the root
  `pyproject.toml`. Prefer its existing tools for feature analysis, clustering,
  evaluation and classical ML when they fit the task.

### Native inference and assets

- For MAEST integration changes and reviews, use `models/maest/contract.json`
  as the active native-inference reference. Contracts are tracked in Git; the
  weights beside them are local and untracked. The package itself is the pinned
  `maest-infer` release, a required dependency in the root `pyproject.toml`,
  and `embedding/loading.py` resolves every family's assets under
  `models/<family>` inside the checkout. Ground contract updates in the
  `maest-infer` source identified there and verify the installed package when
  assessing runtime behavior. Keep `MAEST_MODEL_NAME` in `analysis_models.py`
  aligned with the contract's `settings.adapter.model`. Use native
  `predict_labels()` for genre activation and block averaging; obtain
  embeddings from the same pass.
  Decoder/device choices, top-k, track-level embedding pooling and L2
  normalization are caller policies, separate from native model outputs.
  Every family keeps its own `models/<family>/contract.json`; none of these
  files is read at runtime.

### Stored outputs and readiness

- `analysis_models.py::CURRENT_EMBEDDING_SPECS` and `EMBEDDING_LAYERS` own
  embedding dimensions and layers;
  `db/embeddings.py::_EMBEDDING_TABLES` owns the family/table mapping. Use those
  sources for the current family set, dimensions, layer counts and defaults.
  Layered families store float32 L2-normalized vectors keyed `(track_id, layer)`;
  unlayered families store one per `track_id`. Reads/joins select a layer,
  defaulting to the family's primary layer; counters count tracks.
- For ordinary layered-embedding readiness in
  `db/analysis_candidates.py::ready_target_keys_by_output`, a default-layer row with the
  current track UUID represents the set: one write replaces all layers under
  one UUID and `analyzed_at`. A track migrated with only the default layer is
  ready too; its other layers stay empty until reset and reanalysis. Write and
  reset whole layer sets atomically (`EmbeddingOutput` rejects a partial set);
  do not split tables or average layers in storage.
- SheetSage2 analysis readiness has a stronger bundle contract in
  `db/sheetsage2.py::SHEETSAGE2_READY_FROM`: the current, nonmissing track must
  have timeline, feature and default-layer embedding rows with matching
  `track_uuid` and `analyzed_at`. A default-layer embedding alone is insufficient.
  The shared readiness query does not count all stored layers; preserve the
  complete-layer validation on writes instead of inventing another readiness rule.

### Construction and lifetime

- `embedding/registry.py` owns the single `adapter_factories()` map and typed
  `create_embedding_adapter()` factory; `embedding/contracts.py` defines the
  capabilities used by callers. Use the factory for shared analysis/text API
  construction. Family-specific callers import concrete classes from their
  family modules. SONARA keeps its dedicated runner in `analysis/model_runners.py`.
- Keep heavy imports and weight loading lazy. Each embedding adapter serializes
  construction per instance, checks readiness again after acquiring its lock,
  and publishes ready state only after all family preparation succeeds. Preserve
  shared MuQ/MuLan and CLAP construction locks, verified asset lifetimes and
  restoration of temporary loader bindings through `finally`.
- Loaded analysis runners belong to `AnalysisJobManager`; text adapters belong
  to the application's `TextEmbeddingAdapterCache`. Preserve their separate
  caches, leases and runtime keys. Database switching releases old analysis
  owners while retaining the application text cache.
- Owners drain `AnalysisStageQueue` before closing `AnalysisJobManager`, so
  accepted pipeline callbacks can finish their child stages. A closing queue
  rejects further submissions; release runners only after admitted work unwinds.
  Perform joins and final resource release outside locks needed by callbacks,
  and reject self-close. Replacement construction failure preserves the previously
  published state.
  App teardown closes these analysis owners and the text cache; analysis CLI
  closes its queue/manager. CLI cleanup must await actual worker completion even
  when progress reporting or a thread join is interrupted.

### Search scope and evidence

- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/embedding/text_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/TextSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT-v2, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; keep production
  logic in its owning layer. Ask before extending the task to a model layer
  the user has not authorized; already requested cross-layer work is delegated
  and integrated under [AGENT LAYER](agent-layer.md#agent-layer).
- Shared surfaces such as `search/engine.py`, `analysis_models.py`, `frontend/src/TrackRows.tsx`,
  and family unions in `frontend/src/api.ts` take changes within the requested
  scope. Preserve unaffected contracts; update affected consumers together when
  the requested behavior changes a shared contract.
- Keep CLAP text scores separate from audio-to-audio CLAP signals. Never
  substitute MuQ, MERT-v2, MAEST, CLAP, MuQ-MuLan, or SONARA evidence
  for another.
- Zero-shot text tags are additional evidence, not replacements for MAEST or
  classifier scores; never write them to `classifier_scores` or audio files.
- Browser search tabs are rank-only: use `Limit`, preserve descending scores,
  and do not add a minimum-similarity threshold. API/CLI thresholds and Audio
  Dedup fingerprint thresholds are separate workflows.
- Use the `text-music-search` skill for text-search/model-choice work.
  Reliability claims require a reproducible result from
  `scripts/text_prompt_benchmark.py`, including the run parameters and a
  results table or JSON. Commit or publish it only at the user's explicit request.

## SONARA AND ML RUN CONTRACTS

- SONARA and ML never share a run on any entry point: a pipeline job has one
  `stage` (`sonara` or `ml`), `dj-sim analyze --models` takes `sonara` alone or
  ML models only, and a job rejects the other layer's settings (SONARA BPM
  range, ML staged mode).
- The first SONARA job locks the library's BPM range; only a SONARA reset or a
  library clear releases it. ML refuses to start without any current SONARA
  track and skips tracks lacking it.
- A SONARA write needs all four outputs and stores them together: core,
  timeline, embedding, fingerprint. Readiness is a stored current-track row,
  not a payload check; payloads are validated on write (SONARA Core and stored
  embeddings also on read). `dj-sim validate-database` checks SONARA Core,
  embedding and fingerprint rows but not timeline rows.
- A library without the `sonara_timeline` table gets an explicit error and is
  never migrated automatically.

## REFERENCE MAP

- The REFERENCE map (`cluster_map.py` and `sonara_descriptors.py` in
  `src/dj_track_similarity/search/`) judges a ranking by SONARA alone. The
  model or layer supplies only the candidates, their order (the `/api/search`
  ranking) and its pool, the tracks it could have returned, as a second
  percentile background by membership alone; neither it nor its similarity
  scores enter the distance or any scale.
- The pool sample (`POOL_SAMPLE`) depends only on the library and the model,
  never on a search; the references leave it before comparison.
- Read SONARA Core and stored Timeline rows, never the heuristic Perceptual,
  Mood, Aggression or Vocalness outputs; facet weights are fixed before any
  search, with tempo and pitch class reduced. Fit every scale and within-facet weight on the fixed library sample
  (`BACKGROUND_SIZE`), never on the returned tracks or the pool, and center on
  the per-descriptor median of the references.
- The distance, its exact per-descriptor split and the map radius are one
  calculation; band curves, decoded read-only from source audio on request,
  never enter it. Mood is only a labeled reading of measured descriptors,
  never a measurement.
- Persist nothing and produce no standalone or local HTML map files: the map
  lives in browser memory until the library, model, layer, references or limit
  change, and library scales and pool samples live only in server memory until SONARA
  data or the pool changes.
