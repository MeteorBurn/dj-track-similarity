# MODEL & SIGNAL LAYER — EXPLORER REPORT

---

## 1. Model family matrix

Source of truth: `C:\projects\dj-track-similarity\src\dj_track_similarity\analysis_models.py` (constants + `CURRENT_EMBEDDING_SPECS`), `C:\projects\dj-track-similarity\src\dj_track_similarity\embedding.py` (adapters), `C:\projects\dj-track-similarity\src\dj_track_similarity\db_embeddings.py:16-23` (tables).

| Family | Checkpoint / revision | Input prep | Dim | Normalization | Storage table(s) | Consumers | Reset semantics |
|---|---|---|---|---|---|---|---|
| **SONARA** | PyPI `sonara==0.3.5` (`pyproject.toml:24`, `uv.lock:2579`). Native Rust/CPU. `mode="playlist"`, `sr=22050`, `vocalness_model="bundled"` (`sonara_runtime.py:5-12`) | Native decode (Symphonia) of source path (Direct) or staging copy (Staged). Per-file recovery: tolerant PyAV → `analyze_signal()` (`sonara_features.py:203-269`) | Core row (74+ scalar/vector cols) + **48D** embedding + fingerprint | Core: n/a. Embedding: **`none`** (unnormalized, `analysis_models.py:186`) | `sonara_features`, `sonara_embeddings`, `sonara_fingerprints` | Core → `SonaraSimilaritySearch`, tempo resolution, transition diagnostics, classifiers, MAEST window context, Audio Dedup. Embedding → **nothing**. Fingerprint → **Audio Dedup only** | Reset family = **Core only** (`api_routes_analysis.py:337`). Embedding + fingerprint rows survive; next run rewrites all three. Classifier scores are **NOT** deleted (`db_analysis.py:1408`) |
| **MAEST** | `discogs-maest-30s-pw-129e-519l`, release `v0.0.0-beta`, file `discogs-maest-30s-pw-129e-519l-swa.ckpt`, sha256 `d6044e64…8cdb` (`embedding.py:96-104`) | Shared TorchCodec mono decode → torchaudio resample to **16 kHz** → up to **3 × 30 s** windows centred at 20/50/80 % of the best content range (`maest_windows.py:7,19-40`); short audio right-zero-padded to 30 s | 768 | `l2` | `maest_genres` + `maest_embeddings` | Genre display, genre tag apply, `/api/search` seed, LAB, Audio Dedup, classifiers | Reset family deletes **both** `maest_genres` and `maest_embeddings` (`api_routes_analysis.py:338`) |
| **MERT** | `m-a-p/MERT-v1-95M` @ `12af15fef9…4f5`, `pytorch_model.bin` sha256 `a2b8b747…3fcd`; 5-file snapshot digest set (`analysis_models.py:74-92`) | 24 kHz; **5 s** windows, max **5**, interior 10–90 % evenly spaced; `pad="none"` → variable-length window, `Wav2Vec2FeatureExtractor` pads right with attention mask | 768 | `l2` (single final L2 only) | `mert_embeddings` | Seed search, LAB, Audio Dedup, classifiers | Reset deletes `mert_embeddings` |
| **MuQ** | `OpenMuQ/MuQ-large-msd-iter` @ `0562a578…841a`, `model.safetensors` sha256 `273febab…b7a6` | 24 kHz; **10 s** windows, max **5**, interior 10–90 %; `pad="zero"` | **1024** | `l2` (per-window L2 → mean → L2) | `muq_embeddings` | Seed search, LAB, Audio Dedup, classifiers | Reset deletes `muq_embeddings` |
| **MuQ-MuLan** | `OpenMuQ/MuQ-MuLan-large` @ `57b8af8e…c918`, sha256 `5fe234bb…1d59`. Text tower `xlm-roberta-base` @ `e73636d4…089`, audio tower pinned to the MuQ snapshot (`embedding.py:849-904`) | Same as MuQ: 24 kHz, 10 s × 5, interior, `pad="zero"` | **512** | `l2` (per-window L2 → mean → L2) | `mulan_embeddings` | Seed search (SIMILARITY tab), **text-to-track**, LAB group, classifiers, explicit Evaluation source | Reset deletes `mulan_embeddings` |
| **CLAP** | `lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt` @ `b3708341…651`, sha256 `fae3e9c0…dedd`. `amodel=HTSAT-base`, `tmodel=roberta`, `enable_fusion=False`. Text tower `roberta-base` @ `e2da8e2f…c7b` | 48 kHz; **10 s** windows, max **5**, interior; `pad="repeat"` (tile then zero-pad, `embedding.py:1731-1743`) | 512 | `l2` (per-window L2 → mean → L2) | `clap_embeddings` | **Text-to-track**, `/api/search` seed (API/LAB only, not the browser SIMILARITY selector), Audio Dedup, classifiers | Reset deletes `clap_embeddings` |

Cross-cutting facts:

- `OUTPUT_KINDS_BY_FAMILY` (`analysis_models.py:25-34`) is the canonical contract: sonara = {core, embedding, fingerprint}; maest = {analysis, embedding}; mert/muq/mulan/clap = {embedding}.
- Every checkpoint is SHA-256 pinned and bound into a private verified copy before deserialization (`embedding.py:1279-1307`, `1510-1560`). CLAP's RoBERTa and MuLan's XLM-R/MuQ towers are monkey-patched to `local_files_only` proxies during construction so they cannot reach the Hub (`embedding.py:1310-1507`).
- Runner cache key = `(model, device_requested, inference_batch_size, top_k)` (`analysis_jobs.py:105-110`), reused for the life of the server process.
- Decode: `AudioDecoder(path, num_channels=1).get_all_samples()`, dtype must be `torch.float32` (`audio_loader.py:51-74`). Fallback is in-process PyAV with `fflags=+discardcorrupt+genpts` / `err_detect=ignore_err`, arithmetic channel mean to mono (`shared_ffmpeg_decoder.py:13-14,75-87`). No `ffmpeg.exe` process.
- **Per-family pooling difference worth documenting:** MERT alone does *not* L2-normalize each window before averaging (`embedding.py:454-470`); MuQ, MuQ-MuLan, and CLAP do.
- **Text-embedding asymmetry:** CLAP embeds the whole prompt bank in one forward pass (`embedding.py:1049-1065`); MuQ-MuLan deliberately embeds **one prompt per forward pass** because its text tower mean-pools over padding, making a batched vector depend on its neighbours (measured cosine 0.9952 vs. unbatched) — `embedding.py:772-800`.
- ML jobs require ≥1 track with current SONARA Core before they may start (`analysis_config.py:150-152`, `analysis_jobs.py:271-275`). SONARA cannot be combined with ML models in one job (`analysis_config.py:65-68`).

---

## 2. SONARA in depth

### Direct vs Staged

| | Direct | Staged |
|---|---|---|
| Config | none (`SonaraModelRunner(staging_config=None)`) | `SonaraStagingConfig(root, stage_size=32, copy_workers=16, processes=4, rayon_threads=4, max_native_batch_size=4)` — `sonara_staging.py:32-56` |
| Input to `analyze_batch()` | original source paths | staging-copy paths under `<root>/sonara-stage-<uuid4hex>/` |
| Batch call | one `analyze_batch(paths, sr=22050, mode="playlist", bpm_min, bpm_max, features=[...], vocalness_model="bundled", progress=…)` (`sonara_features.py:115-124`) | per-process mini-batches from a shared ready queue; `RAYON_NUM_THREADS` from `rayon_threads` |
| Result emission | one batch, then bulk store | incremental per track (`incremental_results_emitted=True`, `analysis_model_runners.py:175`) |
| Ownership | n/a | `.owner` marker file holding the PID; `cleanup_orphaned_sonara_staging()` runs on session entry and removes owner-marked dirs whose PID is gone plus empty `sonara-stage-*` residue (`sonara_staging.py:96-101`) |
| API bounds | BatchSize 1..16 | Processes 1..16, Threads 1..64, BatchSize 1..16, StageSize 1..512 (`api_schemas.py:198`, `SonaraStagedSettings`) |

### Requested Core feature inventory

`SONARA_CORE_REQUESTED_FEATURES` (`sonara_runtime.py:40-70`) — 29 names: bpm, beats, rms, dynamic_range, centroid, zcr, onset_density, bandwidth, rolloff, flatness, contrast, mfcc, chroma, chords, dissonance, energy, danceability, key, valence, acousticness, tempo_curve, beatgrid, structure, loudness, silence, key_candidates, vocalness, aggression, mood. `sonara_requested_features()` appends `embedding` and `fingerprint`. **`time_signature` is deliberately not requested.** Timeline is never requested.

Stored Core columns (`sonara_storage.py:185-395`, validated by `sonara_core_validation.py`):
- Tempo: `detected_bpm` (bounded by the run's own `bpm_min`/`bpm_max`), `raw_bpm`, `bpm_confidence`, `onset_density_per_second`, `beat_count`, `tempo_variability`, `beat_grid_offset_seconds`, `beat_grid_stability`, `bpm_candidates_json` (≤5, descending score, canonical JSON).
- Key/harmony: `detected_key_name`, `detected_key_camelot`, `key_confidence`, `predominant_chord`, `chord_changes_per_second`, `key_candidates_json` (≤3, first entry must match the detected key).
- Perceptual: `energy_score`, `energy_level` (1..10), `danceability_score`, `valence_score`, `acousticness_score`, `dissonance_score`.
- Spectral/timbral: `spectral_centroid_hz`, `spectral_bandwidth_hz`, `spectral_rolloff_hz`, `spectral_flatness`, `zero_crossing_rate`, `rms_mean`, `rms_max`.
- Loudness: `integrated_loudness_lufs`, `dynamic_range_db`, `true_peak_dbtp`, `replay_gain_db`, `max_momentary_loudness_lufs`, `loudness_range_lu`.
- Structure/silence: `analyzed_duration_seconds`, `intro_end_seconds`, `outro_start_seconds`, `leading_silence_seconds`, `trailing_silence_seconds`; energy-curve **summary only** (`hop_seconds`, `sample_count`, `min`, `max`, `mean`, `stddev`) — the raw curve is reduced, never stored (`sonara_storage.py:135-166`). All six summary fields are all-NULL or all-present (`sonara_core_validation.py:224-229`).
- Learned/bundled: `vocal_probability`, `mood_happy_score`, `mood_aggressive_score`, `mood_relaxed_score`, `mood_sad_score`, `aggression_score`, `aggression_confidence`, `aggression_forcefulness`, `aggression_harshness`, `aggression_tension`, `aggression_rhythm`.
- Fixed vectors as float32-LE BLOBs: `mfcc_mean_blob` (13), `chroma_mean_blob` (12), `spectral_contrast_mean_blob` (7).
- Provenance: `analysis_schema_version`, `bpm_min`, `bpm_max`, `analyzed_at`.

Unit-interval fields are clamped with `epsilon=0.001` evaluated in float32 precision (`sonara_storage.py:536-556`).

### Fingerprint

`FingerprintOutput(value, version, analyzed_at)` — `value` must be valid base64 decoding to a whole number of uint32s; `version` a positive int (`analysis_models.py:569-593`). Row columns: `track_id`, `track_uuid`, `fingerprint_version`, `fingerprint_base64`, `analyzed_at`. **Single consumer:** `tools/audio-dedup/audio_dedup/` via `audio_dedup_reports.py` / `audio_dedup_jobs.py`. `FINGERPRINT_REVIEW_MIN_SIMILARITY = 0.45` (`tools/audio-dedup/audio_dedup/core.py:47`) creates manual-review candidates only and never authorizes deletion.

### BPM-range-is-library-scoped

Enforced at `analysis_jobs.py:194-230`:
- `db.sonara_analysis_ranges()` returns the distinct `(bpm_min, bpm_max)` pairs already stored.
- More than one distinct pair → hard error "Reset SONARA analysis before analysing again."
- No rows → the requested (or default 70/180) pair is used.
- Rows exist → any requested pair other than the stored one is refused with an explicit reset instruction.
- Independently, `normalize_sonara_bpm_range` requires `bpm_max >= 2 × bpm_min` (`analysis_config.py:102-106`) and bounds both to 20..400 (`MIN_SONARA_BPM`/`MAX_SONARA_BPM`); the stored Core row re-checks the octave rule (`sonara_storage.py:110-114`, `sonara_core_validation.py:144-154`).
- UI presets: Rekordbox 70-180, VirtualDJ 80-240, Mixed In Key 79-192 (`frontend/src/sonaraAnalysisSettings.ts:104-106`).

### Stored-but-unused

| Signal | Written | Read by | Status |
|---|---|---|---|
| `sonara_embeddings` (48D, unnormalized) | every successful SONARA pass (`sonara_storage.py:71-79`) | only `db_embeddings.py` (table map), `db_analysis_candidates.py` (missing-output check), `db_ddl.py` (schema). **No search, classifier, dedup, or API reader.** | Deliberate WIP. `SimilaritySearch` rejects `"sonara"` outright (`search.py:30,112-117`); `SonaraSimilaritySearch` docstring states the 48D space is "data-only and intentionally not exposed as a public search mode" (`sonara_similarity.py:76-79`) |
| `mood_happy/aggressive/relaxed/sad_score` | yes | nothing in `sonara_similarity_scoring.py`, `transition_diagnostics.py`, or Rhythm Lab's `SONARA_SCALAR_FIELDS` — wait, mood **is** in Rhythm Lab's scalar set (`tools/rhythm-lab/rhythm_lab/features.py:80-91`) | Not a similarity input; **is** an optional Rhythm Lab classifier input |
| `true_peak_dbtp`, `replay_gain_db` | yes | not in any mixer group, modifier, or risk component; **are** in Rhythm Lab's `_SONARA_CURRENT_EXTRA_SCALAR_FIELDS` | Not a similarity input; is a classifier input |
| `vocal_probability` | yes | Custom-search `vocalness` modifier (`sonara_similarity_scoring.py:115`). **Excluded from Rhythm Lab training features by design** (`features.py:86-92`) | Search modifier only |
| `aggression_*` components (forcefulness/harshness/tension/rhythm) | yes | only `aggression_score` + `aggression_confidence` are read (`score_modifier`, `sonara_similarity_scoring.py:424-453`). The four component values are unread everywhere, and Rhythm Lab excludes the whole family | Data-only |

---

## 3. Search and ranking

### 3.1 ML embedding search — `search.py` / `SimilaritySearch`

Families: `maest | mert | muq | mulan | clap` (`search.py:28-30`). SONARA is structurally excluded.

Three entry points:

| Method | Query construction | Scoring |
|---|---|---|
| `search(seed_targets, …)` | L2-normalized **mean of the seed rows** (centroid), seeds excluded from results (`search.py:270-284`) | cosine via `ExactVectorSearchBackend` |
| `search_vector(vector, …)` | caller vector, dimension-checked against the family spec then L2-normalized (`_query_for_output`) | cosine |
| `search_contrast_vectors(positive_vectors, negative_vectors, negative_weight)` | positive bank = L2-normalized **mean of L2-normalized positives**; negatives kept as a matrix | `score = positive − w · mean(top-2 negative cosines)` (`search.py:796-841`) |

**Contrast scoring detail that documentation gets wrong today:** negatives are combined as `np.sort(matrix @ negative_bank.T, axis=1)[:, -2:].mean(axis=1)` — the **mean of the two highest** negative similarities, not the single maximum. The in-code rationale: "Averaging the two closest negatives asks a second prompt to agree before a track is pushed down… Measured on the labelled pool it beats the maximum at every weight for both text models. A bank of one negative keeps the old behaviour" (`search.py:819-827`). Default weight `CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT = 0.5` (`search.py:29`). Score breakdown returned: `{positive, negative, contrast, negative_weight}`.

`SearchFilters` (`search.py:62-88`): `min_similarity` (score floor), `epsilon` (keep only candidates within ε of the best score), `noise` 0..1 (deterministic SHA-256 jitter over `catalog_uuid\0track_uuid`, amplitude ±noise/2, applied to the *ranking* score only — the returned `score` is untouched; `search.py:1044-1057`).

Ranking is progressive-depth: request `limit + |excluded|` hits, double until `_ranking_is_settled` (`search.py:470-530, 992-1022`). Every row set is validated once and memoized by object identity in `_PreparedRows` (4 entries) and `_CheckedTargets` (4 entries) — both keyed on `id()` while holding a strong reference.

Backend: `ExactVectorSearchBackend` (`vector_index.py:47-75`) — exact NumPy cosine, `argsort(-scores, kind="stable")`. It re-verifies that every matrix row and the query are unit-norm within `rtol=1e-4, atol=1e-5`. **There is no ANN backend in the repository.**

### 3.2 SONARA Core search — `sonara_similarity.py` + `sonara_similarity_scoring.py`

Five modes (`SonaraSearchMode`): `balanced | vibe | sound | dj_transition | custom`.

Weights (`sonara_similarity_scoring.py:25-99`):

| Mode | Numeric fields | Tonal text |
|---|---|---|
| `vibe` | energy 3.0, danceability 3.0, valence 1.4, acousticness 1.0, LUFS 0.8, dynamic_range 0.8, onset_density 0.8, rms_mean 0.6 | none |
| `sound` | mfcc 1.8, centroid/bandwidth/rolloff 1.0, flatness 0.9, contrast 0.9, zcr 0.8, rms_mean 0.8, rms_max 0.5 | none |
| `dj_transition` | detected_bpm 3.0, onset_density 2.0, energy 1.3, danceability 1.3, chord_change_rate 1.0, dissonance 1.0 | key_name 4.0, camelot 3.0, predominant_chord 3.0 |
| `balanced` | 0.9 × VIBE ∪ 0.7 × SOUND, plus bpm 1.0, chord_change_rate 0.7, dissonance 0.7 | key_name 4.0, camelot 3.0, predominant_chord 3.0 |
| `custom` | five mixer groups (below) | lighter harmonic-group tonal weights 0.9/0.9/0.6 |

Normalization is a **library-scoped robust 2nd–98th percentile band** per dimension, computed over the candidate set of the request, with fall-back to raw min/max when degenerate (`_robust_range`, `sonara_similarity_scoring.py:180-190`); values outside the band clamp to the edges. Vector fields (mfcc 13, chroma 12, contrast 7) split their field weight across components so a vector cannot dominate its group (`numeric_dimensions`, lines 166-177; `score_custom_group`, lines 376-406).

`score_candidate` returns `None` (candidate dropped) when fewer than 2 numeric dimensions overlap or total weight is 0.

**Custom mixer groups** (`CUSTOM_GROUP_WEIGHTS`, defaults in `DEFAULT_CUSTOM_MIXER_WEIGHTS`): `timbre 1.0`, `rhythm 1.0`, `dynamics 0.8`, `harmonic 0.8`, `tempo 0.35`. API bounds 0..5 (`api_schemas.py:316-322`).

**Custom modifiers** (`CUSTOM_MODIFIER_FIELDS`, 9 knobs, API bounds −1..1): energy→`energy_score`, valence→`valence_score`, acousticness→`acousticness_score`, brightness→`spectral_centroid_hz`, rhythm_density→`onset_density_per_second`, dynamic_range→`dynamic_range_db`, loudness→`integrated_loudness_lufs`, vocalness→`vocal_probability`, aggression→`aggression_score`.
- A field driven by an active modifier is **excluded from group similarity** so the two do not cancel (`score_custom_candidate`, lines 308-313).
- Modifier weight = `|direction| × MODIFIER_GAIN` with `MODIFIER_GAIN = 2.5`.
- Modifier score = `clamp01(0.5 + desired_delta/2)`, where `desired_delta = ±(value − centroid)`.
- **Aggression is the only confidence-attenuated modifier**: `0.5 + confidence × (score − 0.5)`, and returns `None` when `aggression_confidence` is missing (`score_modifier`, lines 444-453). Breakdown emits `modifier_aggression` and `modifier_aggression_confidence`.

**DJ transition mode** additionally blends a directional structural fit: `score = 0.8 × similarity + 0.2 × transition_fit` (`DJ_TRANSITION_FIT_BLEND = 0.2`, `sonara_similarity.py:308-316`), with breakdown `{dj_similarity, transition_fit}`. `transition_fit` = mean over seeds of `structure_transition_fit_from_values(seed, candidate)` — seed **outro** vs candidate **intro** overlap / 16 s, energy-level closeness / 10, and the four energy-curve summary values; missing parts are omitted, not zeroed (`transition_diagnostics.py:162-208`).

**Harmonic scoring** uses Camelot compatibility attenuated by key confidence — key confidence is a reliability weight, never a similarity dimension (`_tonal_similarity`, lines 520-535).

### 3.3 Tempo evidence — `tempo_resolution.py`

- `LOW_BPM_CONFIDENCE = 0.45`, `NEUTRAL_TEMPO_SCORE = 0.5`, `TEMPO_MATCH_WINDOW_BPM = 16.0`, `TAG_CANDIDATE_TOLERANCE_BPM = 4.0`.
- `reliability = bpm_confidence`, then `sqrt(reliability × grid_stability)` if grid stability exists. **A NULL `bpm_confidence` yields reliability 0.0** and therefore the neutral 0.5 score; the Mutagen tag BPM is *not* promoted in that case (`tempo_resolution.py:250-272`, pinned by `tests/test_scoring_invariants.py:74-96`).
- Below 0.45 confidence, ranked `bpm_candidates_json` entries join the alternatives, and a tag BPM within 4 BPM of any SONARA option is promoted with source `tag_confirmed_by_sonara_candidate`.
- `best_tempo_distance` scales **at most one** side of the pair (×½, ×1, ×2) so a 60-vs-240 quarter/quadruple ratio does not look like a match (`tempo_resolution.py:130-141`).
- `confidence_aware_tempo_score = reliability·measured + (1−reliability)·0.5`, with pair reliability `sqrt(a·b)`.
- Multi-seed tempo is **pairwise, not an arithmetic BPM centroid** (`_tempo_similarity`, `sonara_similarity_scoring.py:598-611`; pinned by `tests/test_sonara_similarity.py:504`).

### 3.4 Transition diagnostics — `transition_diagnostics.py`

Two versions. v1 = 4 components (bpm, key, energy jump, source disagreement), unweighted mean; kept so recorded evaluations stay reproducible. v2 (default) = 11 components with `V2_COMPONENT_WEIGHTS`: bpm/key/energy/source 1.0; density/texture/mood 0.75; vocal_conflict 0.6; grid_instability 0.6; structure_transition 0.65; confidence_missingness 0.4. Missing components are omitted from the weighted mean, never zeroed. `confidence_missingness_risk` = `(missing/3) × 0.35` over the three optional feature groups. Vocal conflict reads `classifier_scores` whose key contains "voice" or "vocal".

### 3.5 LAB Reference Compare — `reference_compare.py`

Six default groups: `clap, mert, muq, mulan, maest, sonara` (`DEFAULT_REFERENCE_COMPARE_MODELS`, line 42). Each family is searched independently for the first seed; SONARA uses `mode="balanced", min_similarity=0.0`. An unavailable family stays in the response with `available=False` and a reason. Verdicts (`mood | palette | instruments | groove | genre | transition | miss`) are written as pair feedback with source `reference_compare:<model>` and rating 2 (or 0 for `miss`). API limit 1..100.

### 3.6 Rank-only rule for browser tabs

- Browser tabs: `lab | sonara | similarity | text | class` (`frontend/src/searchSurfaceState.ts:1-14`). Displayed labels are `LAB, SONARA, SIMILARITY, **PROMPT**, CLASS` (`frontend/src/SearchPlaylistPanel.tsx:95-99`).
- SIMILARITY seed families are exactly `maest, mert, muq, mulan` — **CLAP has no browser seed-search entry** (`searchSurfaceState.ts:2,14`), although `/api/search` accepts it and LAB shows it.
- `min_similarity` appears only in frontend *type declarations* (`api.ts:209`, `apiClient.ts:70,83`); no UI code sets it. Browser search is Limit-only, descending score.
- API/CLI thresholds exist and are separate: `SearchRequest.min_similarity`, `SonaraSearchRequest.min_similarity`, `TextSearchRequest.min_similarity` (0..1), `dj-sim text-search --min-similarity`.
- Audio Dedup content gates are a third, unrelated surface (`min_similarity` over MERT/MAEST/MuQ/CLAP; `fingerprint_similarity ≥ 0.45` for manual review only).

---

## 4. Text-to-track layer

### Paths

`POST /api/search/text` (`api_routes_search.py:191-219`). `analysis_family: Literal["clap","mulan"]`, default `"clap"` (`api_schemas.py:378`). The browser default preset model is `"mulan"` (`textPromptPresets.ts:2741`); the CLI default is `--model clap` (`cli.py:1120`).

Dispatch (`_search_clap_text_prompts`, `api_routes_search.py:292-308`):
- 1 positive prompt and no negatives → `search_vector`.
- Otherwise → `search_contrast_vectors` over the whole bank.

`POST /api/search/text/warmup` loads the family and embeds the literal prompt `"warmup"`, touching no database (`api_routes_search.py:221-248`).
`POST /api/search/text/feedback` writes one verdict per `(track_uuid, preset_key, analysis_family)` with `verdict ∈ {-1, 0, +1}`; `0` withdraws (`api_routes_search.py:250-270`, table `text_preset_feedback` in `db_ddl.py:334-348`, `verdict IN (-1,1)`, PK `(track_id, preset_key, analysis_family)`).

### Prompt presets

`frontend/src/textPromptPresets.ts`: **21 axes** (`textPromptAxes`, lines 64-86) and **153 presets** (verified by count of `^    key: "`). Axis order is deliberate: rhythm, groove, percussion, bass, synths, instruments, voice, harmony, movement, timbre, texture, organic, space, density, complexity, energy, tension, mood, abstract, function, style (labelled "Genres").

Per-preset fields: `positive: PromptVariants` (shared + optional per-model override), optional `negative`, `negativeWeight` (scalar or `{clap, mulan}`), optional `measured: {clap?, mulan?}` ROC-AUC, optional `model` pin overriding the axis model.

Measured model pins: axis-level `rhythm → mulan`, `texture → clap`, `style → mulan`; other axes carry no `model`. `modelAdvice(keys)` returns `single | conflict | unmeasured` and never fuses — "Rank fusion was measured and rejected" (lines 2775-2808).

`composePromptBanks` merges the selected presets: positives de-duplicated in order; a preset with `negativeWeight <= 0` or no negatives contributes nothing to the negative bank; the merged weight is the **minimum** contributing weight (lines 2836-2864).

`defaultNegativeWeight = 0.5` explicitly mirrors `CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT`; `negativeWeightRange = {min:0, max:2, step:0.05}` mirrors the API bound.

### Caching

`TextEmbeddingAdapterCache` (`text_embedding_cache.py`): one adapter per `(family, device)`, `DEFAULT_IDLE_TTL_SECONDS = 600`, serialized per-entry `RLock` so two threadpool requests never share one forward pass, background sweeper at `max(5, ttl/2)` seconds, `gc.collect()` + `torch.cuda.empty_cache()` on eviction.

### Benchmark / research tooling (all read-only, report-first)

| Script | Purpose | Key constants |
|---|---|---|
| `scripts/text_prompt_benchmark.py` | Ranks a labelled pool with each prompt form × model × negative weight; reports ROC-AUC, AP, P@K, median rank | `DEFAULT_WEIGHTS = (0.0,0.15,0.35,0.5,0.75,1.0)`, `PRODUCTION_WEIGHT = 0.35`, `TOP_K = 20`; spec `scripts/text_prompt_benchmark_prompts.json` |
| `scripts/text_tag_crosscheck.py` | Cross-checks each preset against SONARA/MAEST signals | `TOP_K = 100`, `BINARY_STRONG = 0.70`, `BINARY_WEAK = 0.55`, `EXTREME_QUANTILE = 0.9`; parses `textPromptPresets.ts` directly |
| `scripts/text_fusion_benchmark.py` | Tests CLAP+MuLan rank fusion vs the better single model and a per-label oracle | `RRF_K_GRID = (10,60,200)`, `MULAN_WEIGHTS = (0.5..0.8)`, `CASCADE_DEPTH = 500` |
| `scripts/prompt_preset_tune.py` | Turns accumulated `text_preset_feedback` verdicts into wording/weight proposals; leave-one-out marginal value per line | `WEIGHT_GRID = (0.0,0.25,0.5,0.75,1.0)`; writes nothing |
| `scripts/clap_checkpoint_embed.py` | Embeds only the labelled pool with a candidate CLAP checkpoint into an `.npz` sidecar | two pinned checkpoints, incl. `music_speech_audioset_epoch_15_esc_89.98.pt`; explicitly never writes the library DB, `classifier_scores`, or audio |

All five reuse the *production* adapters and `search._contrast_vector_scores`, so a benchmark number is produced by the same math as a live search.

---

## 5. Evaluation package

**What it is:** an optional, CLI-and-HTTP-only diagnostics layer. There is **no Evaluation UI** — `evaluation` appears in `frontend/src` only inside `api.ts` type declarations.

### Sidecar database

`library.sqlite` → `library.evaluation.sqlite` (`db_storage.py:19-26`). Created lazily, only when an Evaluation workflow writes (`db_evaluation_sidecar.py:1-6,105-137`). WAL enforced; an existing file is never migrated. Tables: `evaluation_profiles`, `search_sessions`, `search_session_seeds`, `search_result_events`, `calibration_runs`.

**Feedback lives in the main library database, not the sidecar:** `pair_feedback` (`db_ddl.py:296+`) and `transition_feedback` (`db_ddl.py:314-325`).

### Modules (17)

| Module | Role |
|---|---|
| `candidates.py` | Blind candidate pools per seed. `ALLOWED = (mert,maest,muq,mulan,sonara,clap)`, `DEFAULT = (mert,maest,muq,sonara,clap)` — **`mulan` is allowed but not default**. Randomized blind order, per-source `(rank, score)` recorded, optional `search_sessions` write |
| `weighted_candidates.py` | Weighted RRF over a score profile, optional `transition_risk_weight` penalty; own CSV columns |
| `seed_sampling.py` | Stratified or random seed sampling; `require_complete_analysis` defaults to the 5-source default set |
| `source_profile.py` | Unsupervised source-agreement profile: coverage, reciprocal support, pairwise overlap/Jaccard/rank correlation, RRF consensus (`DEFAULT_RRF_K = 60`), recommended weights = normalized `coverage × consensus × stability`. `WEIGHT_KIND = "unsupervised_internal_profile"` with four explicit `LIMITATIONS` strings |
| `score_profiles.py` | Score-profile artifact: `SCORE_PROFILE_VERSION = 1`, `DEFAULT_K_VALUES = (5,10,20)`, `LABEL_POLICY = "unjudged_as_non_relevant_preserve_rank_positions"` |
| `score_profile_optimizer.py` | Bounded grid search over source weights with a seed-split train/validation, NDCG@10 guardrail, deterministic bootstrap (`BOOTSTRAP_PASS_RATE = 0.60`), `DEFAULT_MIN_JUDGED_PAIRS = 200` |
| `ablation.py` | Per-source and fusion ablation, incl. `fusion:rrf_all` vs `fusion:rrf_without_classifiers` |
| `calibration.py` | Reliability bins, Brier, log loss, ECE. `SCORE_KINDS = {event-total-score, rank-percentile, rrf}`; four `DIAGNOSTIC_NOTES` insisting these are ordering scores, not production probabilities |
| `risk_sweep.py` | Sweeps `transition_risk_weight` ∈ `(0.0, 0.25, 0.5, 1.0)` over v1/v2 diagnostics |
| `judged.py` | Label gates: `INSUFFICIENT_JUDGED_PAIRS = 50`, `CANDIDATE_PROFILE_JUDGED_PAIRS = 200`, `DEFAULT_UPDATE_JUDGED_PAIRS = 500`, `default_update_policy = "manual_review_only_never_automatic"` |
| `metrics.py` | P@K, R@K, DCG/NDCG, AP@K, MRR; plus `EXPLANATION_REASON_TAG_AXES` mapping reason tags to axis/direction with 0.55/0.45 thresholds |
| `reports.py`, `labels.py`, `csv_io.py`, `track_views.py`, `recorded_sessions.py` | Report assembly, CSV/JSONL label import, CSV writer, `TransitionTrack` view loading, current-session filtering |

### CLI surface (`dj-sim eval …`)

`export-candidates`, `export-weighted-candidates`, `export-seed-sample`, `import-pair-feedback`, `import-transition-feedback`, `report`, `run-ablation`, `build-score-profile`, `run-calibration`, `optimize-score-profile`, `profile-sources`, `apply-score-profile`, `sweep-risk-penalty`. Plus `dj-sim classifier calibration-report` and `dj-sim classifier suggest-labels`.

### Outputs

- CSV: candidate pools, weighted candidate pools, seed samples (paths chosen by `--output`).
- JSON reports written by `_write_json_report` (sorted keys, indent 2) — never auto-persisted; `/api/evaluation/reports/latest` explicitly states "CLI JSON report directories are not scanned by the API".
- Sidecar rows: `search_sessions` + `search_session_seeds` + `search_result_events` (only with `--record-session`), `calibration_runs` (only with `--record` and `status == "ok"`), `evaluation_profiles` (only with `--save-profile` and ≥500 judged pairs).
- Main-DB rows: `pair_feedback`, `transition_feedback` via the import commands and `/api/evaluation/feedback/*`.

### HTTP surface

`GET /api/evaluation/summary`, `POST /api/evaluation/feedback/pair`, `POST /api/evaluation/feedback/transition`, `POST /api/evaluation/run/source-profile`, `POST /api/evaluation/run/apply-score-profile`, `POST /api/evaluation/run/weighted-candidates`, `GET /api/evaluation/reports/latest`. Ablation, calibration, the optimizer and the risk sweep are **CLI-only**.

---

## 6. Classifiers and Rhythm Lab

### Manifest contract — `classifier_manifest.py`

`model.json` beside `model.joblib`. Required, else `status="invalid"`:
`classifier_key` (must equal the requested key), `artifact_hash` matching `sha256:[0-9a-f]{64}`, `feature_set`, `feature_names` (non-empty, no duplicates, no surrounding whitespace), `feature_count` == `len(feature_names)`, `label_order` (≥2 labels), `positive_label` ∈ `label_order`, `production.score_semantics == "positive_label_probability"`. `publication_status`, when present, must be `"ready"`. Optional: `negative_label` (must differ from positive), `production.calibration` (missing → warning "scores are not calibrated probabilities"), `trained_label_counts`.

Feature-name grammar: `<sonara|mert|maest|clap|muq|mulan>:<key>`. Embedding indices must be canonical non-negative integers strictly below `current_embedding_spec(family).dimension` — so a manifest becomes invalid if a family's dimension changes. SONARA keys resolve through `sonara_classifier_features.resolve_sonara_classifier_feature`, which supports Rhythm Lab's short aliases (`bpm`, `mfcc_mean:0`, …) and direct column names, and returns `None` for anything not a numeric `SonaraRow` scalar or a valid vector index.

`required_inputs` is derived as the **first-occurrence order** of feature sources (`classifier_manifest.py:77-85`), and `classifier_scoring._validate_feature_inputs` enforces `feature_families == required_families` exactly (`classifier_scoring.py:478-484`).

### Validation and artifact-hash gates

Three independent SHA-256 checks:
1. Discovery: `promoted_classifiers()` verifies `model.joblib` against `manifest.artifact_hash` and downgrades the row to `invalid` on mismatch (`classifier_scoring.py:106-113`).
2. `load_classifier_requirements()` re-verifies the file — deliberately read-only, never loads joblib, never deletes scores (`classifier_scoring.py:190-218`).
3. `_load_payload()` hashes the exact bytes it hands to `joblib.load` (`classifier_scoring.py:515-539`).

Then `_validate_payload_identity` compares the joblib payload's `classifier_key`, `feature_set`, `feature_names`, `label_order`, `positive_label`, `feature_count` against `model.json`, and `_validate_model` checks `n_features_in_` and `classes_`.

`_predict_probabilities` requires finite probabilities in [0,1] summing to 1 within 1e-6 and requires `classes_` to match `label_order` as a set. `predicted_class` uses `_argmax_with_tiebreak`, which resolves exact ties by manifest `label_order` position. `score_bucket`: `≥0.7 high`, `≥0.3 medium`, else `low`.

### Database-only scoring rule

`analyze_classifier` / `ClassifierJobManager` read `db.load_classifier_work_batch(specification, after_track_id, limit)`, which builds the query from **INNER JOINs** on each required table plus `LEFT JOIN classifier_scores … WHERE scored.track_id IS NULL` (`db_analysis.py:1266-1329`, `_classifier_input_query_parts` at `78-119`). No audio path is opened. Batch size `CLASSIFIER_SCORE_BATCH_SIZE = 200`. Writes go only to `classifier_scores`, scoped by `classifier_key` (PK `(track_id, classifier_key)`).

**Not-ready vs failure:** a track missing any required input is dropped by the INNER JOIN before the job total is computed, so it is neither counted nor failed. A failure is a scoring exception or a write error, recorded per track in `status.errors`. Note: `ClassifierJobStatus.not_ready` and `readiness[key]["not_ready"]` are **hard-coded to 0** (`classifier_jobs.py:148-157`) and `analyze_classifier` returns `"not_ready": 0, "skipped": 0, "already_scored": 0, "deleted_stale": 0` unconditionally (`classifier_scoring.py:281-290`). The not-ready concept exists in the payload shape but carries no computed value today.

**Incremental, never re-scoring:** because the candidate query excludes tracks that already have a row for that `classifier_key`, rescoring after a retrain requires an explicit `POST /api/classifiers/reset` (or the CLASS-tab play button) first.

### The label → train → promote → score loop

1. **Label** in Rhythm Lab (`tools/rhythm-lab/`), a separate FastAPI app on `127.0.0.1:8777` started by `rhythm_lab_launcher.launch_rhythm_lab()` with list-based `subprocess.Popen`, `shell=False`, a PID file and a `rhythm_lab.source.json` catalog binding that must match before reuse.
2. **Train** — `rhythm_lab_cli train --profile <key> [--feature-set <recipe>] [--calibrate]`. Pipeline = `StandardScaler → ColumnTransformer(per-source passthrough with weight sqrt(total/(groups·group_size))) → LogisticRegression(class_weight="balanced", max_iter=1000)` (`training.py:351-400`). Holdout split `test_size = 0.5` under 8 rows else `0.25`, stratified. Minimum 4 labelled rows and ≥2 per label. Metrics written next to the artifact as `<prefix>-<feature_set>-<stamp>.metrics.json`: classification report, confusion matrix, positive-discovery threshold and top-N tables, StratifiedKFold cross-validation (≤5 folds), production calibration report.
3. **Calibration gate**: `MIN_CALIBRATION_LABELS = 100`, `MIN_CALIBRATION_POSITIVE = 20`, `MIN_CALIBRATION_NEGATIVE = 20`, binary only. Method `sigmoid` via `CalibratedClassifierCV`. Reports Brier, ECE@10, ROC-AUC, AP, F1@0.5, and precision-80/recall-80 thresholds.
4. **Benchmark** — `benchmark-ablation` over `FEATURE_RECIPE_OPTIONS` = the default recipe plus every other non-empty combination of the six sources (2⁶−1 = **63**), optional `--calibrate-finalists`.
5. **Promote** — `rhythm_lab_cli promote --profile … --source <library.sqlite>`. Two hard gates that documentation must state: the artifact's `source_catalog_uuid` **must equal the active library's `catalog_uuid`** (`cli.py:296-317`), and **calibration is required by default** — `require_calibration = args.require_calibration or not args.allow_uncalibrated` (`cli.py:379-381`). Publication is atomic: staged pair written and fsynced under `.staging-<uuid>/`, both hashes fenced, the staged classifier is actually *exercised* through the production `ClassifierScorer` on a zero vector, then `model.json` is flipped to `publication_status="publishing"`, `model.joblib` replaced, and `model.json` replaced with the `"ready"` manifest (`artifact_io.py:69-181`).
6. **Score** — `dj-sim analyze-classifier <key> --db …` or `POST /api/classifiers/{key}/analyze`.

### Feature sources (`tools/rhythm-lab/rhythm_lab/features.py`)

`BASE_FEATURE_SOURCES = ("sonara","mert","maest","clap","muq","mulan")`; `MODERN_FULL_FEATURE_SET = DEFAULT_TRAINING_FEATURE_SET = "sonara+mert+maest+clap+muq+mulan"`.

SONARA block = **74 features**: 19 core scalars + 19 current extras (incl. `true_peak_db`, `replaygain_db`, `loudness_range_lu`, `grid_stability`, silence and energy-curve summaries) + 4 mood scalars + mfcc(13) + chroma(12) + spectral_contrast(7). **`vocalness` and the entire aggression family are deliberately excluded**, with the in-code reason "Keep the baseline independent of SONARA's bundled learned outputs" (`features.py:86-92`). Default recipe dimensionality = 74 + 768 + 768 + 512 + 1024 + 512 = **3658**.

Feature order is always `BASE_FEATURE_SOURCES` order, SONARA first (`_feature_names`, lines 385-401). A track missing **any** requested value is skipped entirely — never zero-imputed (`_track_features` / `_sonara_features` return `None`).

### Rhythm Lab state separation

Labels, queues, predictions, checkpoints and review collections live in `tools/rhythm-lab/database/rhythm_lab.sqlite`. `rhythm_lab_collections.py` validates every Lab classifier table against an exact column set and refuses a legacy `classifier_labels` schema without `catalog_uuid`/`track_uuid`/`selected_path`. **The only write into the source library is `SourceDatabase.set_track_liked()`** — "the sole narrow Core write after checking exact current identity" (`tools/rhythm-lab/rhythm_lab/source_db.py:585-592`).

---

## 7. Invariants the documentation MUST state correctly

1. **Score spaces never mix.** One search = one embedding family = one score space. `SimilaritySearch` binds a single `AnalysisOutput` and refuses any output whose key does not match (`search.py:120-129`). SONARA Core scores, each ML family's cosine, CLAP text contrast, MuQ-MuLan text contrast, Audio Dedup `min_similarity`, `fingerprint_similarity`, transition risk, and classifier probability are **eight distinct scales**. Comparing across them is not defined.
2. **CLAP text ≠ CLAP audio-to-audio.** The same `clap_embeddings` table serves both, but a text score is `prompt · audio` and a seed score is `audio · audio`. `search_contrast_vectors` returns `contrast = positive − w·mean(top-2 negatives)`, which can be negative and is not a probability.
3. **Rank fusion between CLAP and MuQ-MuLan was measured and rejected.** The code never fuses; `modelAdvice` returns `conflict` rather than a blend (`textPromptPresets.ts:2775-2808`). Documentation must not suggest combining them.
4. **Never substitute one model's evidence for another.** MuQ-MuLan vectors are produced by its own tower, never derived from `muq_embeddings` (`embedding.py:802-847`). Each family has its own table, its own reset, and its own coverage count.
5. **Zero-shot text tags are not classifier scores.** `/api/search/text` writes only `text_preset_feedback` (verdicts ±1) — never `classifier_scores`, never file tags. `prompt_preset_tune.py` is report-first and states "Trained classifier outputs play no part here." Conversely `text_tag_crosscheck.py` refuses to use promoted classifiers as references.
6. **Audio is read-only in this layer.** Analysis, search, text search, classifier scoring, evaluation, and every `scripts/` benchmark open audio read-only or not at all. The only script that reads audio is `clap_checkpoint_embed.py`, and it writes exactly one `.npz`.
7. **The SONARA 48D embedding and the fingerprint are not similarity inputs.** The embedding has zero readers; the fingerprint has exactly one (Audio Dedup). SONARA similarity always uses Core fields.
8. **Browser tabs are rank-only.** Limit only, descending score, no minimum-similarity control. API/CLI thresholds and Audio Dedup gates are separate workflows.
9. **The SONARA BPM range belongs to the library, not the run**, and the upper bound must be ≥ 2× the lower.
10. **Missing classifier inputs skip a track; they are never imputed as 0.0** — in both Rhythm Lab feature assembly and the scoring query.
11. **A promoted classifier is bound to one source catalog UUID and (by default) must be calibrated.**

---

## 8. DOCUMENTATION FINDINGS

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\reference\analysis-families.md` — **WRONG**

| Claim | Line | Correct fact |
|---|---|---|
| MuQ-MuLan unlocks "optional ANN" | 41 | **There is no ANN anywhere in the repository.** `vector_index.py` contains only `ExactVectorSearchBackend`; `rg '\bANN\b'` over all `*.py` returns nothing; there is no `ann` extra in `pyproject.toml:22-46` |
| "A per-file native decode or codec failure falls back to a **direct TorchCodec** shared-library decode" | 97 | SONARA's fallback is `load_audio_mono_with_ffmpeg` → `shared_ffmpeg_decoder.load_tolerant_mono_audio` (PyAV). `sonara_features.py:225`. TorchCodec is never used by SONARA. The same page says PyAV correctly at line 32 — self-contradictory |
| "Staged Mode does not apply to the GPU model families" | 137-138 | ML Staged Mode exists and is reachable: `MLStagingConfig` (`ml_staging.py:27-61`), `AnalysisPipelineRequest.ml.mode="staged"` (`api_schemas.py:261-262`), `api_routes_analysis.py:169-189`, `dj-sim analyze --ml-staged --ml-staging-path` (`cli.py:908-939`), and browser settings in `frontend/src/mlAnalysisSettings.ts` |
| "The current `sonara` classifier source includes those loudness scalars **and vocalness**" | 161-163 | Loudness scalars yes; **vocalness no**. `tools/rhythm-lab/rhythm_lab/features.py:86-92` excludes `vocal_probability` and the aggression family from `SONARA_SCALAR_FIELDS` by explicit design |
| "Classifier scoring remains unavailable until the catalog has at least one current SONARA result" | 222-224 | Not enforced. `LibraryDatabase.active_analysis_output` is now a **pure structural check that always returns an `AnalysisOutput`** (`db_analysis.py:677-691`), so `_require_available_outputs` (`classifier_scoring.py:426-434`) can never fail. A classifier job on an empty library simply finds zero work |
| `--inference-batch-size` default `16`, `top_k` default `3`, `track_batch_size` default `8` | 203-207 | Correct (`analysis_config.py:15-17`) |
| MAEST windows 20/50/80 %, silence hard / intro-outro soft, fallback main→non-silent→full, dedup 1.0 s | 176-182 | Correct (`maest_windows.py`) |
| Runner cache per model/device/inference batch/top_k | 64-66 | Correct (`analysis_jobs.py:105-110`) |

**Missing:** the per-family pooling differences (MERT has no per-window L2); MuQ-MuLan's one-prompt-per-forward text policy; the fact that `register_analysis_outputs` registers nothing.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\reference\sonara-integration.md` — **OUTDATED**

- Line 7: "uses SONARA in `playlist` mode **with a `70..180` BPM range**" — 70/180 is only the *default* (`sonara_runtime.py:10-11`); the page itself contradicts this at 55-59. Delete the range from the opening sentence.
- Line 50: "For **SONARA 0.3.6** Core results" — the pinned and tested version is **0.3.5** (`pyproject.toml:24`, `uv.lock:2579-2580`). Either 0.3.6 or the pin is wrong; the lockfile wins.
- Everything else verified accurate: `sr=22050`, `mode="playlist"`, bundled vocalness, unnormalized 48D in `sonara_embeddings`, native base64 fingerprint, `analysis_schema_version`/`bpm_min`/`bpm_max` provenance, three-output atomic per-track savepoint, library-scoped range read back from the data, no Timeline, no output selector.
- **Missing:** that resetting SONARA does not delete dependent classifier scores, and that already-scored tracks are skipped by the classifier candidate query.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\reference\model-citations.md` — **ACCURATE**

`sonara==0.3.5` matches `pyproject.toml`/`uv.lock`. All six upstream sources and their license notes match the adapter constants. Only gap: it does not mention the CLAP text tower (`roberta-base`) or the MuQ-MuLan text tower (`xlm-roberta-base`), both of which are downloaded, SHA-pinned, and loaded (`analysis_models.py:40,42,107-154`). Those are separate upstream assets with their own licenses and should be listed.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\concepts\features-embeddings-tags.md` — **OUTDATED**

- Line 43-44: "The current `sonara` classifier source includes those loudness scalars **and vocalness**" — same error as `analysis-families.md`; Rhythm Lab excludes vocalness.
- Line 79: "The **MERT tab** searches from selected seed tracks" — there is no MERT tab. Seed search is the **SIMILARITY** tab with a model selector (`searchSurfaceState.ts:1-14`).
- Line 91-92: "Use the **MULAN tab** … In the **TEXT tab**" — there is no MULAN tab; the text tab is labelled **PROMPT** (`SearchPlaylistPanel.tsx:97`).
- Line 13 attributes text search to CLAP alone in the "start with the question" table while line 16 gives MuQ-MuLan text retrieval — inconsistent within the page.
- Everything about storage tables, dimensions, normalization, the unused embedding, and the single fingerprint consumer is correct.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\concepts\similarity-scores.md` — **INCOMPLETE**

- Section headings "MERT seed search" / "CLAP text search" describe families accurately but reinforce the phantom per-model tabs.
- Line 20: "Useful matches can appear around `0.35..0.55`" — NOT VERIFIED; no constant or test anchors this.
- Line 22 and 247-equivalent: with negatives the score is contrast evidence — correct in spirit, but the page never says the negative term is the **mean of the two highest** negative similarities scaled by `negative_weight` (`search.py:824-827`).
- `fingerprint_similarity ≥ 0.45` → manual review only: **correct** (`tools/audio-dedup/audio_dedup/core.py:47`).
- Audio Dedup sources "MERT, MAEST, MuQ, and CLAP": **correct** — `SUPPORTED_EMBEDDINGS` excludes `mulan` (`core.py:44`).
- **Missing:** SONARA Custom-search score anatomy (mixer groups + `MODIFIER_GAIN = 2.5` + aggression confidence attenuation), the DJ-transition 0.8/0.2 blend, the deterministic `noise` jitter, and `epsilon`.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\concepts\classifiers-and-rhythm-lab.md` — **WRONG**

- Line 62: "Promotion publishes the selected artifact through the main app's **immutable-generation layout**" — there is no generation layout. `publish_promoted_artifact` writes `models/classifiers/<artifact-prefix>/model.joblib` and `model.json` directly via a `.staging-<uuid>` temp dir (`artifact_io.py:106-181`), and discovery globs exactly `*/model.joblib` and `*/model.json` (`classifier_scoring.py:66-72`).
- Line 74: "Existing scores are candidates again when their stored **`model_id`** differs from the current promoted manifest" — `classifier_scores` has **no `model_id` column** (`db_ddl.py:270-284`), and the candidate query re-scores nothing that already has a row (`db_analysis.py:1300-1305`). An explicit reset is mandatory.
- Line 78: "A full SONARA reset invalidates all such scores" — `reset_analysis_outputs` sets `classifier_deleted = 0` and never touches `classifier_scores` (`db_analysis.py:1408`). The scores survive and go stale silently.
- Line 73: "Missing manifest inputs make a track not ready, not failed" — true in effect, but `not_ready` is always reported as 0 (`classifier_jobs.py:148-157`).
- Correct: profile types, label/prediction/queue locations, six feature sources, default six-source recipe, no zero-imputation, database-only scoring, per-key scoping.
- **Missing:** the promotion catalog-UUID binding and the calibration-required-by-default rule.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\concepts\project-idea.md` — **ACCURATE**

Framing only; no verifiable technical claims that conflict with code. The signal list at 15-20 matches. Line 56 correctly marks automatic set generation as direction, not shipped.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\user-guide\text-search.md` — **OUTDATED (otherwise the strongest page in the set)**

- "The **TEXT** tab" (15, 17, 23) — the UI label is **PROMPT** (`SearchPlaylistPanel.tsx:97`); the internal key is still `text`.
- Line 247: "positive prompt match minus part of the **strongest** negative match" — **wrong**. It is `positive − w · mean(two highest negative cosines)` (`search.py:824-827`). With a one-line negative bank the two collapse to the same value, which is presumably why the error survived.
- Line 91: 153 presets / 21 axes — **verified exactly**.
- Line 253: "roughly 40 seconds"; line 256: "about `0.8` GB (CLAP) or `2.5` GB (MuQ-MuLan)" — NOT VERIFIED, no anchor in code.
- Line 256: "released after 10 idle minutes" — correct (`DEFAULT_IDLE_TTL_SECONDS = 600`).
- Lines 235-245 (request-field list, "no `query`, `preset`, or `adaptive_contrast` field") — correct against `TextSearchRequest` (`api_schemas.py:367-386`).
- Lines 137-152 (feedback table, per `(track, preset, model)`, click-again withdraws) — correct against `db_ddl.py:334-342` and `TextSearchFeedbackRequest` (`verdict ∈ {-1,0,1}`).
- Line 262-263 (MuQ-MuLan XLM-R loaded from a verified pinned snapshot) — correct (`embedding.py:872-882`, `1428-1439`).
- **Missing:** the browser default model is MuQ-MuLan (`defaultTextPromptModel`) while the API and CLI default to CLAP; and MuQ-MuLan embeds one prompt per forward pass while CLAP batches the bank, which is why a MuLan bank of N prompts costs N forwards.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\user-guide\search-with-seeds.md` — **ACCURATE**

SIMILARITY = MAEST/MERT/MuQ/MuQ-MuLan (correct, CLAP is API/LAB-only), `/api/search` accepting `clap` (correct), limit 1..500 (correct), "no browser similarity threshold" (correct), SONARA modes and mixer/modifier lists (correct), LAB six groups and limit 1..100 and verdict vocabulary (correct), `reference_compare:<model>` feedback source (correct). Only gap: it does not say that the harmonic *group* in Custom mode uses lighter tonal weights (0.9/0.9/0.6) than Balanced/DJ mode (4.0/3.0/3.0), which is the whole point of `CUSTOM_HARMONIC_TONAL_WEIGHTS`.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\user-guide\class-tab.md` — **WRONG**

- Lines 29-42: the entire `current.json` + `generations/<generation-id>/` storage description is fictional. Real layout: `models/classifiers/<artifact-prefix>/{model.joblib,model.json}` (`artifact_io.py:120-121`, `classifier_scoring.py:44-51`). "Promotion verifies and syncs both generation files before atomically switching `current.json`" must be replaced with the real staged-pair-then-`os.replace` sequence and the `publication_status` interlock.
- Line 74-76: "Missing inputs exclude a track before the job total is formed and do not create a partial score" — correct. But the surrounding claim that the UI shows "manifest-specific ready/not-ready counts" is undercut by `not_ready` being hard-coded to 0.
- Line 61-63 (database-only, exact declared inputs, `classifier_scores`, never decodes audio, never inside a SONARA/ML job) — correct.
- **Missing:** that scoring is incremental and skips already-scored tracks, so a retrain-then-rescore requires a reset first.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\user-guide\analyze-library.md` — **ACCURATE**

Batch defaults 8/16/8 and device `auto` correct; stage separation correct; ML default order MAEST→MERT→MuQ→MuQ-MuLan→CLAP correct (`ML_ANALYSIS_MODEL_ORDER`); SONARA storage paragraph correct; reset boundaries correct as stated ("Resets affect SQLite data only") because this page — unlike `first-analysis.md` — does not claim classifier scores are deleted.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\workflows\train-personal-classifier.md` — **WRONG**

- Line 52: "The single current `sonara` source includes the current Core fields, **including `vocalness`**" — false (`features.py:86-92`).
- Lines 177-179: "Promotion copies the selected runtime artifact into an **immutable generation** under `models/classifiers/<artifact-prefix>/`, then atomically switches **`current.json`**" — false, same as `class-tab.md`.
- Line 96: calibration gate 100/20/20 — correct (`training.py:24-26`).
- Line 119: 63 ablation combinations — correct (2⁶−1, `features.py:27-35`).
- Lines 158-163: promotion requires calibration by default — correct (`cli.py:379-381`).
- **Missing:** step 8 must say to reset the classifier key before rescoring, because `load_classifier_work_batch` will otherwise return zero rows for already-scored tracks. It also omits that promotion refuses an artifact whose `source_catalog_uuid` differs from the active library.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\workflows\reanalyze-sonara-split-storage.md` — **INCOMPLETE**

Everything stated is accurate (three-output candidate selection, backfill without reset, SQLite-only reset, storage description, embedding/fingerprint consumers). Missing the two consequences a reader hits immediately: SONARA reset does not delete `classifier_scores`, and step 6's `analyze-classifier` will score **nothing** unless the classifier key is reset first.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\workflows\find-compatible-tracks.md` — **OUTDATED**

Step 3 "Run **MERT search**" names a tab that does not exist; the action is SIMILARITY with the MERT model selected. Tempo note (0.45 confidence, ranked candidates, tag BPM, grid stability, neutral) is correct.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\workflows\build-crates.md` — **ACCURATE**

Step 4 "Use MERT or SONARA" is loose but not wrong. Steps 5-7 correct. Filter list at step 2 (syncopated rhythm, classifier filters) matches the backend.

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\tools-and-scripts\rhythm-lab.md` — **ACCURATE**

Six sources, six-source default recipe, 63 ablation combinations, `muq:<index>`/`mulan:<index>` dimension check, liked-track toggle as the only main-catalog write, legacy schema rejection, label-transfer bundle version 3 and its report-first `--apply` contract — all verified. Only gap: it does not mention the promotion gates (catalog-UUID binding, calibration-by-default, staged-scorer smoke test).

### `C:\projects\dj-track-similarity\docs\dj-track-similarity\getting-started\first-analysis.md` — **WRONG**

- Line 32: MuQ-MuLan "optional ANN" — phantom feature.
- Line 173: "Staged Mode applies only to SONARA" — false; ML Staged Mode exists in CLI, pipeline API, and browser localStorage settings.
- Line 200: "**Reset SONARA removes Core rows plus dependent classifier scores**" — false. `reset_analysis_outputs` deletes `sonara_features` only and returns `classifier_rows_deleted=0` (`db_analysis.py:1382-1419`). There are no triggers on `classifier_scores`.
- Line 37: "Incomplete tracks are counted as not ready rather than failed" — true in effect, but the reported `not_ready` counter is always 0.
- Correct: BPM-range explanation, presets, CLI options and ranges, model warm-up, Direct/Staged tables and bounds, the decode-recovery description (this page describes SONARA's PyAV fallback correctly, unlike `analysis-families.md:97`), and reset boundaries for MAEST/MERT/MuQ/MuQ-MuLan/CLAP/CLASSIFIERS.

### Bonus — `C:\projects\dj-track-similarity\README.md`

- Line 167 and 214: "SONARA **0.3.6** Core rows" — the pin is 0.3.5.
- Line 462: "**Persistent ANN indexes** … See [Persistent ANN indexes](docs/dj-track-similarity/tools-and-scripts/persistent-ann-indexes.md)" — the feature does not exist and **the linked file does not exist** (`docs/dj-track-similarity/tools-and-scripts/` contains only `index.md`, `rhythm-lab.md`, `audio-dedup.md`, `audio-doctor.md`, `optimize-database.md`). Broken link plus phantom feature.
- Line 113 "Search from seed tracks with MAEST, MERT, MuQ, MuQ-MuLan, CLAP, and SONARA" — true only if "search" includes the HTTP API and LAB; the browser SIMILARITY selector has no CLAP option.
- Line 448-450 "Its main search tabs are LAB, SONARA, SIMILARITY, **TEXT**, and CLASS" — the visible label is PROMPT.
- Verified correct: 48D `sonara_embeddings`, `sonara_fingerprints` column list, 512D L2-normalized `mulan_embeddings`, TorchCodec 0.16 with `AudioDecoder(path, num_channels=1).get_all_samples()` and `data[0]` staying a 1-D CPU float32 tensor, PyAV 17.1.0 tolerant recovery with no `ffmpeg.exe`, BPM presets and the ≥2× rule, mood/true-peak/ReplayGain stored-but-unscored, aggression as a confidence-attenuated Custom modifier, DJ transition structural blend, batch ranges and defaults, and the CLAP-vs-MuLan score-space separation warning.

Also broken beyond my page list: `docs/.../getting-started/install.md:114` "For optional ANN support:" and `docs/.../reference/configuration.md:41` "Persistent ANN sidecars | `.dj-track-similarity-indexes/`" and `docs/.../concepts/local-first-safety.md:14` "Optional ANN sidecar indexes" — all phantom.

---

## 9. UNDOCUMENTED SURFACE (ranked)

1. **`active_analysis_output` / `register_analysis_outputs` are vestigial.** Both are now pure structural helpers that always succeed (`db_analysis.py:677-691`, `728-736`). Consequences no page states: a search on a family with zero embeddings returns `[]` (HTTP 200) rather than a 409; the classifier "input is not active" error path is unreachable; "registering analysis outputs" writes nothing.
2. **Classifier scoring is incremental and never re-scores.** `scored.track_id IS NULL` in both the count and batch queries means a promoted-model change is invisible until the key is reset. Nothing in the docs states this as the reason for the reset step.
3. **SONARA reset leaves classifier scores in place**, so a library can carry classifier scores computed from Core rows that no longer exist.
4. **The `not_ready` counter is always 0** across `ClassifierJobStatus`, `readiness`, and `analyze_classifier`'s return payload — as are `skipped`, `already_scored`, and `deleted_stale`.
5. **ML Staged Mode** — reachable through `POST /api/analysis/pipeline` (`ml.mode="staged"`, folder + `copy_workers` 1..16 + `decode_workers` + `stage_size` + `inference_batch_size` + `preflight_copy_*`), `dj-sim analyze --ml-staged`, and the browser (`mlAnalysisSettings.ts`, defaults workers 4 / stageSize 64, folder never restored from storage). Two docs pages actively deny it exists.
6. **Contrast-negative aggregation = mean of the two highest**, with the measured rationale in-code. Only `text-search.md` touches this and gets it wrong.
7. **Deterministic `noise` jitter and `epsilon` filter** in `/api/search` (`SearchRequest.noise` 0..1, `epsilon` ≥0). No user-facing page explains either; `noise` perturbs ranking only, never the reported score, and is deterministic per `(catalog_uuid, track_uuid)`.
8. **The full SONARA Custom score anatomy** — five mixer groups with their per-field weights, robust 2–98 percentile normalization, vector-weight splitting, modifier-field exclusion from group similarity, `MODIFIER_GAIN = 2.5`, and the aggression confidence attenuation formula.
9. **Rhythm Lab's feature-group balancing** — the `ColumnTransformer` weights each source by `sqrt(total_features / (group_count × group_size))` so a 1024-D MuQ block does not swamp 74 SONARA features (`training.py:393-400`). This is a substantive modelling decision with no documentation.
10. **Promotion runs the production scorer on the staged artifact** before activation (`artifact_io.py:193-228`), plus the `publication_status` `publishing`→`ready` interlock that makes a half-published pair refuse to deserialize.
11. **Checkpoint pinning and Hub isolation** — every family verifies a SHA-256, binds a private verified copy, and (for CLAP and MuQ-MuLan) monkey-patches the upstream loaders to `local_files_only` proxies that reject an unexpected source string. `model-citations.md` never mentions the pinned text towers.
12. **`transition_diagnostics` v1 vs v2** — the 11 v2 components, their weights, `confidence_missingness_risk`, and the fact that v1 is preserved for reproducibility of recorded evaluations.
13. **MAEST `syncopated_rhythm`** — derived from a fixed 13-label list (`maest_analysis_validation.py:20-37`) and exposed as a library filter; `recompute_maest_syncopated_rhythm()` exists as an explicit repair path.
14. **Text-preset feedback loop** — `text_preset_feedback` → `prompt_preset_tune.py` leave-one-out marginal analysis → hand edit of `textPromptPresets.ts`. `text-search.md` covers it; nothing else does.
15. **`text_prompt_benchmark_prompts.json` is the frozen spec** that makes every published number reproducible, including deliberately retained losing forms.

---

## 10. WORK-IN-PROGRESS vs SHIPPED

### Shipped and reachable from the UI

- SONARA analysis, Direct and Staged, with library-scoped BPM range and browser presets.
- ML analysis for MAEST, MERT, MuQ, MuQ-MuLan, CLAP; Direct and (via localStorage settings) Staged.
- SONARA search: all five modes, mixer weights, nine modifiers, DJ-transition structural blend.
- SIMILARITY seed search over MAEST, MERT, MuQ, MuQ-MuLan.
- PROMPT (text) search over CLAP or MuQ-MuLan, with the 153-preset / 21-axis picker, merged banks, per-preset negative weights, model advice, and ±1 relevance verdicts.
- LAB Reference Compare across six families with listening verdicts.
- CLASS filters over promoted classifier scores, per-key reset + rescore.
- Rhythm Lab launch/reuse, review-collection save, liked-track toggle.

### Shipped, CLI/API only (no browser surface)

- CLAP **seed** search (`POST /api/search` with `analysis_family: "clap"`).
- `dj-sim text-search` with `--min-similarity`.
- The whole Evaluation package. Seven HTTP routes exist; ablation, calibration, the score-profile optimizer, and the risk sweep are CLI-only. The `*.evaluation.sqlite` sidecar is created only on first write.
- `dj-sim classifier calibration-report` / `suggest-labels`.
- Rhythm Lab `benchmark-ablation`, `predict`, `export-predictions`, `queue*`, `delete-profile`, `label_transfer`.
- `scripts/text_prompt_benchmark.py`, `text_tag_crosscheck.py`, `text_fusion_benchmark.py`, `prompt_preset_tune.py`, `clap_checkpoint_embed.py`.

### Exists in code, no consumer yet

- **`sonara_embeddings` (48D)** — written on every SONARA pass, read by nothing outside candidate selection and schema validation. Deliberate WIP, explicitly documented as such in `sonara_similarity.py:76-79`. Do not describe it as dead code and do not describe it as a search input.
- **SONARA `mood_*`, `true_peak_dbtp`, `replay_gain_db`** — stored, available to Rhythm Lab recipes, absent from every similarity path.
- **Aggression component values** (`forcefulness`, `harshness`, `tension`, `rhythm`) — stored, read by nothing.
- **`not_ready` / `skipped` / `already_scored` / `deleted_stale`** counters — present in the payload shape, always 0.
- **`_require_available_outputs` / `_require_active_outputs`** error paths — unreachable given the current `active_analysis_output`.
- **`VectorIndexUnavailable` from `SimilaritySearch.active_output()`** — unreachable for the five ML families; only `random_target` can still raise it.

### Aspiration in the README / docs, NOT implemented

- **Persistent ANN indexes.** No code, no extra, no `.dj-track-similarity-indexes/` writer, and the linked doc page does not exist. Documented in README §Maintenance tools, `reference/configuration.md:41`, `getting-started/install.md:114`, `concepts/local-first-safety.md:14`, `reference/analysis-families.md:41`, and `getting-started/first-analysis.md:32`. **Remove all six.**
- **Immutable classifier generations / `current.json`.** No code. Documented in `class-tab.md:29-42`, `train-personal-classifier.md:177-179`, `classifiers-and-rhythm-lab.md:62`. **Remove all three.**
- **`classifier_scores.model_id` staleness detection.** No column, no query. `classifiers-and-rhythm-lab.md:74`.
- **Automatic set dramaturgy / narrative generation.** Correctly framed as direction, not shipped, in README §"The long-term direction" and `concepts/project-idea.md:56`. Keep it framed that way.agentId: ad0a0613013f0646f (use SendMessage with to: 'ad0a0613013f0646f', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 555215
tool_uses: 154
duration_ms: 894992</usage>