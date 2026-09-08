# Model layer contracts and ownership

Read before changing or reviewing models, audio inference, loaders, jobs, caches, text/seed search, ranking, classifier signals, or their shared backend/frontend contracts.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## MODEL LAYER OWNERSHIP

- State the model layer before changing shared files.
- For MAEST integration changes and reviews, use `models/maest/contract.json`
  as the active native-inference reference. It is machine-local, like the rest
  of the untracked model store, and sits next to the staged `maest-infer`
  source it describes; ground contract updates in that source and verify the
  installed package when assessing runtime behavior. Keep `MAEST_MODEL_NAME`
  in `analysis_models.py` aligned with the variant the contract marks
  `default_application_model`. Use native `predict_labels()` for genre
  activation and block averaging; obtain embeddings from the same pass.
  Decoder/device choices, top-k, track-level embedding pooling and L2
  normalization are caller policies, separate from native model outputs.
  Every family keeps its own `models/<family>/contract.json`; none of these
  files is read at runtime.
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
- Text-to-track/tagging owns CLAP and MuQ-MuLan text paths, `/api/search/text`,
  `src/dj_track_similarity/embedding/text_cache.py`,
  `frontend/src/textPromptPresets.ts`, `frontend/src/TextSearchTab.tsx`, and
  `scripts/text_prompt_benchmark.py`.
- SONARA, MERT, MAEST, MuQ seed search, their analysis jobs, and Rhythm Lab
  training are separate layers. Signals may cross boundaries; keep production
  logic in its owning layer. Ask before extending the task to a model layer
  the user has not authorized; already requested cross-layer work is delegated
  and integrated under [AGENT LAYER](agent-layer.md#agent-layer).
- Shared surfaces such as `search/engine.py`, `analysis_models.py`, `TrackRows.tsx`,
  and family unions in `frontend/src/api.ts` take changes within the requested
  scope. Preserve unaffected contracts; update affected consumers together when
  the requested behavior changes a shared contract.
- Do not expand, redesign, or remove Model Listening Lab without a new request.
- Keep CLAP text scores separate from audio-to-audio CLAP signals. Never
  substitute MuQ, MERT, MAEST, CLAP, MuQ-MuLan, or SONARA evidence for another.
- Zero-shot text tags are additional evidence, not replacements for MAEST or
  classifier scores; never write them to `classifier_scores` or audio files.
- Browser search tabs are rank-only: use `Limit`, preserve descending scores,
  and do not add a minimum-similarity threshold. API/CLI thresholds and Audio
  Dedup content gates are separate workflows.
- Delegate text-search/model-choice work with `text-music-search`. Reliability claims
  require a committed `scripts/text_prompt_benchmark.py` table.
