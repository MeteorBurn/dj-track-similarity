---
name: clap-query-workflow
description: Project-specific CLAP query workflow for dj-track-similarity. Use when the user asks Codex to find tracks directly from the local music library with CLAP text search, search from one or more source audio files using stored SQLite CLAP embeddings or temporary direct CLAP analysis, optimize Russian or English music descriptions into CLAP prompt banks, work with CLAP prompt presets/profiles, positive_queries, negative_queries, /api/search/text, TextSearchRequest, SimilaritySearch.search_contrast_vectors, or LAION-CLAP music checkpoints such as music_audioset_epoch_15_esc_90.14.pt with HTSAT-base and enable_fusion=False.
---

# CLAP Query Workflow

Use this skill as the project operator for CLAP search in `dj-track-similarity`: convert the user's natural-language request into a compact English prompt bank, or use one or more existing library files as audio seeds, then search against stored CLAP audio embeddings, inspect the results, and iterate when needed.

## Project Defaults

- Project: the user's current `dj-track-similarity` checkout. Helper scripts discover the repo root from their own location.
- Library DB: user-local. Pass it with `--db` / `--expected-db`, or set `DJ_SIM_DB` or `DJ_TRACK_SIMILARITY_DB`.
- Running app/API: prefer `http://localhost:8765` or `http://127.0.0.1:8765` when available.
- API endpoint for text prompts: `POST /api/search/text`
- Text API helper checks `/api/database/current` only when `--expected-db`, `DJ_SIM_DB`, or `DJ_TRACK_SIMILARITY_DB` provides the expected DB path.
- Source-file DB search: use stored SQLite `embeddings.embedding_key = 'clap'`; do not decode source audio and do not compute new audio embeddings.
- Source-file analyze search: decode only the user-provided source files, compute temporary CLAP audio embeddings, compare them to stored DB CLAP embeddings, and do not save anything.
- Main contract files: `src/dj_track_similarity/api_schemas.py`, `src/dj_track_similarity/api_routes_search.py`, `src/dj_track_similarity/search.py`, `frontend/src/api.ts`, `frontend/src/clapPrompt.ts`.
- Current scoring: normalized positive text embeddings are mean-pooled, normalized, compared to stored CLAP audio embeddings, then hard negatives are subtracted with `alpha = 0.35`.
- CLAP text-search scores are text-to-audio cosine or contrast scores, not probabilities and not equivalent to MERT/SONARA seed similarity.

## Direct Search Workflow

Use two different search modes.

### Text Request

When the user writes a request such as "найди сухие ломаные барабаны без вокала":

1. Translate the intent into audible English concepts. Keep genre/style, rhythm/groove, instrumentation, timbre, vocal presence, mood, and production texture.
2. Build a positive prompt bank with 4-5 short lines. Use one label-only prompt, two template prompts, one audio-centric description, and optionally one close synonym.
3. Build hard negatives only for real exclusions or likely confusions. Prefer per-query/per-label hard negatives; avoid broad global negatives because they can conflict with vocal or acoustic profiles. Do not make `no`, `not`, or `without` the main semantics.
4. Run the local API with `scripts/project_clap_search.py` when the app is up. If the app is unavailable and a live search is required, start the project server only after checking existing listeners/processes.
5. Start broad: normally omit `min_similarity` or use a low value. Do not apply high seed-search thresholds to CLAP text search.
6. Inspect top results. If they are too vocal, too acoustic, too straight, too aggressive, or otherwise off-target, refine the positive bank or hard negatives and run one more pass.
7. Report the prompt bank used plus the best matches with score, track id, artist/title when available, and path.

Use Russian in explanations when the user writes in Russian. Keep CLAP prompt strings in English unless the user explicitly asks otherwise.

### Source Files

When the user provides one or more source audio files and asks for similar tracks:

Choose the mode from the user's wording:

- `--source-mode db`: use when the source files are already in the selected library DB and the user wants to use existing analysis. Resolve source paths to `tracks`, require stored `clap` embeddings, build a centroid through `SimilaritySearch(..., embedding_key="clap").search(source_track_ids, ...)`, and exclude source tracks.
- `--source-mode analyze`: use when the user says to analyze the provided files directly, provides files that may be outside the DB, or asks for a clean audio-derived query. Compute temporary CLAP audio embeddings for the provided files, mean-pool and normalize them, search the stored DB CLAP matrix with `SimilaritySearch(...).search_vector(...)`, and do not save source embeddings.

Use multiple source files together as one CLAP audio-to-audio query by averaging their CLAP embeddings. In `db` mode, missing DB rows or missing stored CLAP embeddings are a coverage error. In `analyze` mode, missing source files are an input error, but files do not need to be present in the DB.

## Running Project Search

Set the user's local library DB once per shell, or pass the same path through `--db` / `--expected-db` in each command:

```powershell
$env:DJ_SIM_DB = "<path-to-library.sqlite>"
```

Text prompt search through the running API:

```powershell
python .agents\skills\clap-query-workflow\scripts\project_clap_search.py `
  --query "broken beat electronic music" `
  --positive "broken beat electronic music." `
  --positive "This audio is a broken beat electronic track." `
  --positive "This audio is a syncopated drum track." `
  --positive "A club electronic track with syncopated drums, broken rhythm, dry percussion, and tight low-end." `
  --negative "This audio contains prominent singing vocals." `
  --negative "This audio is a straight four-on-the-floor house track." `
  --limit 25
```

Source-file CLAP search using already computed SQLite embeddings:

```powershell
python .agents\skills\clap-query-workflow\scripts\project_clap_search.py `
  --source-mode db `
  --source-file "<path-to-seed-one.flac>" `
  --source-file "<path-to-seed-two.flac>" `
  --limit 25
```

Source-file CLAP search by temporarily analyzing input files, without writing to the DB:

```powershell
python .agents\skills\clap-query-workflow\scripts\project_clap_search.py `
  --source-mode analyze `
  --source-file "<path-to-reference-one.flac>" `
  --source-file "<path-to-reference-two.flac>" `
  --device auto `
  --limit 25
```

If using the project CLI, remember `dj-sim text-search` currently accepts one text query and does not expose the multi-positive/hard-negative API contract. Use it as a fallback for simple single-prompt searches only.

## CLAP Prompt Rules

- Treat a prompt as a text embedding anchor, not as an instruction.
- Prefer several compact prompts over one long prompt.
- Keep most prompts under 35 words and comfortably below 50 tokens; 77 tokens is a ceiling, not a target.
- Include label-only prompts with a final period as real candidates: `broken beat.`, `ambient drone.`
- Use templates:

```text
{label}.
This audio is a {label} song.
This audio is a {label} track.
This is an audio clip of {label}.
A sound recording of {label}.
```

- Avoid social metadata and subjective claims: release year, label mythology, "rare vinyl bomb", "underground", "non-commercial", "like artist X".
- Use hard-negative candidates instead of negation prose:

```text
POS: This audio is an instrumental electronic dance track.
NEG: This audio contains prominent singing vocals.
NEG: This audio is speech or spoken word.
NEG: This audio is a vocal pop song.
```

## Prompt Ensemble Scoring

Use this mental model:

```python
text = normalize(each_prompt_embedding)
positive_bank = normalize(mean(text))
final_score = sim(audio, positive_bank) - 0.35 * max(sim(audio, hard_negative_i))
```

Vector subtraction can be tried experimentally for retrieval, but the project default should be margin/gating through `/api/search/text`.

## Current Project Profiles

The current CLAP profiles are:

- `breaks_broken`: Breaks / Syncopated drums
- `deep_warmup`: Deep Warm-up
- `vocals_speech`: Vocals / Speech
- `vocals_music`: Vocals with Music
- `instrumental`: Instrumental
- `acoustic_organic`: Acoustic / Organic
- `ambient_drone`: Ambient / Drone

Adaptive is intentionally excluded unless the user explicitly reintroduces it.

Use `assets/project_prompt_bank.json` for the project starter bank. Keep each comparable profile at the same prompt count unless the search is a one-off user query.

## Bundled Resources

- `assets/project_prompt_bank.json`: project-aligned prompt bank for the current CLAP profiles.
- `references/clap_prompting_reference.md`: detailed LAION-CLAP prompt engineering rules from the merged external skill.
- `scripts/project_clap_search.py`: posts optimized prompt banks to the running local project API, searches from source files via stored SQLite CLAP embeddings, or temporarily analyzes source files and searches against stored DB embeddings.
- `scripts/validate_prompt_bank.py`: validates prompt bank structure and length.
- `scripts/score_prompt_bank.py`: standalone audio-file scorer for experiments outside the project DB; do not use it as the normal path for searching the user's stored library. It must load PyTorch checkpoints in `weights_only=True` mode.

## Implementation Changes

When changing project CLAP code:

- Verify the current code path first.
- Model multiline text as one prompt per non-empty line.
- Keep `positive_queries` and `negative_queries` as arrays through frontend/API/backend.
- Preserve `TextSearchRequest` and `frontend/src/api.ts` alignment.
- Mean-pool normalized positive prompt embeddings before scoring.
- Keep `negativeQueries` visible unless the user explicitly asks to hide it.
- Do not imply text-search scores are calibrated probabilities.
- Preserve audio read-only behavior; CLAP search must not modify audio files.

## Verification

- Skill validation: `python "$env:CODEX_HOME\skills\.system\skill-creator\scripts\quick_validate.py" .agents\skills\clap-query-workflow`
- Prompt bank validation: `python .agents\skills\clap-query-workflow\scripts\validate_prompt_bank.py .agents\skills\clap-query-workflow\assets\project_prompt_bank.json`
- API helper smoke: `python .agents\skills\clap-query-workflow\scripts\project_clap_search.py --help`
- Standalone scorer safety test: `.\.venv\Scripts\python.exe -m pytest tests\test_clap_query_workflow_scripts.py --override-ini addopts=`
- Frontend prompt changes: `cd frontend; npm test -- tests/clapPrompt.test.mjs tests/clapSimilaritySemantics.test.mjs`
- Backend scoring/API changes: `.\.venv\Scripts\python.exe -m pytest tests\test_api_text_search.py --override-ini addopts=`
