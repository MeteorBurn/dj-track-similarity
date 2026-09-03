---
name: clap-query-workflow
description: Text-to-track search operator for dj-track-similarity. Use when the user wants to find tracks in the local library from a text description with CLAP or MuQ-MuLan, to turn a Russian or English request into an English prompt bank with hard negatives, to pick between the two text models, to tune negative weight, or to work with textPromptPresets, positive_queries, negative_queries, /api/search/text, TextSearchRequest, or SimilaritySearch.search_contrast_vectors.
context: fork
background: false
---

# Text Search Operator

Turn a listening intent into a prompt bank, search the local library with CLAP or
MuQ-MuLan, read the results honestly, and iterate.

## Layer Boundary

This skill owns the text-to-track and tagging layer built on **CLAP and MuQ-MuLan**.
The **SONARA, MERT, MAEST** layers, their analysis jobs, their seed search, and the
Rhythm Lab training pipeline belong to other agents.

Signals from those layers are inputs here. Use SONARA tempo, key, energy and feature
values, MAEST genre labels, MERT/MuQ/MuQ-MuLan embeddings, and promoted classifier
scores freely as evidence, filters, or expansion vectors, and never change how they are
produced. Their adapters, feature computation, scoring formulas, thresholds, schemas,
promoted artifacts, and UI surfaces stay untouched; route a needed change there back to
the user.

Audio-to-audio seed search is out of scope here. It lives in the SIMILARITY tab and
`POST /api/search`.

## Project Defaults

- Library DB: user-local. Pass `--expected-db`, or set `DJ_SIM_DB` / `DJ_TRACK_SIMILARITY_DB`.
- Running app/API: `http://127.0.0.1:8765`.
- Text endpoint: `POST /api/search/text`, families `clap` and `mulan`.
- Contract files: `src/dj_track_similarity/api_schemas.py`, `src/dj_track_similarity/api_routes_search.py`,
  `src/dj_track_similarity/search.py`, `frontend/src/api.ts`, `frontend/src/textPromptPresets.ts`.
- Preset and tag vocabulary source of truth: `frontend/src/textPromptPresets.ts` (8 axes, 32 presets).
  Changing that vocabulary is the `prompt-bank-curator` skill's job, not this one.
- Current scoring: normalized positive text embeddings are mean-pooled, normalized, compared to
  stored audio embeddings, then hard negatives are subtracted with the preset's `negative_weight`
  (`CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT = 0.5` applies only when the request omits one).
- Text-search scores are text-to-audio cosine or contrast scores, not probabilities, and not
  comparable to MERT/SONARA seed similarity or to the other text model's scores.
- The server keeps one loaded text adapter per family and device, so the first search of a process
  costs about 40 s and later searches are milliseconds. Iterate freely once it is warm.

## Choosing The Model

Measured on the user's own library against 4590 Rhythm Lab labels (ROC-AUC):

| Concept | MuQ-MuLan | CLAP |
|---|---:|---:|
| broken / syncopated drums | **0.955** | 0.840 |
| minimal / deep tech | **0.880** | 0.691 |
| voice presence | 0.879 | **0.910** |
| live instrumentation | 0.778 | **0.792** |

Default to MuQ-MuLan for groove, style, energy and texture. Prefer CLAP for voice and
instrument questions. When unsure, run both and compare the top lists.

## Prompt Rules

These come from measurement on this library, not from taste:

1. **A bank beats one long sentence.** A single caption scored between 0.955 and 0.495 depending on
   wording; a bank of four short prompts stayed stable. Use 4-5 lines: one label-only anchor plus
   three or four short descriptive variants.
2. **Never name the competing class in a positive prompt.** A positive caption containing
   "over the instrumental" dropped voice retrieval from 0.873 to 0.640.
3. **Never write `no`, `not` or `without`.** The text encoders do not model negation; the negated
   word attracts the thing it negates. Name the unwanted class in the negative bank instead.
4. **Hard negatives only when they name a real competing class.** Then a high weight helps: ROC rose
   with weight up to 0.75-1.0 on broken drums and voice. An invented negative bank hurt monotonically,
   so omit negatives rather than inventing them.
5. Keep every line short. The CLAP text tower truncates at 77 tokens; current presets peak at 19.
6. Write prompts in English. MuQ-MuLan's text tower is multilingual, but its contrastive training was
   English and Chinese, and Russian is unmeasured here. Explain in Russian, prompt in English.

Templates that work:

```text
{label}.
A {label} track.
A track with {audible detail} and {audible detail}.
```

## Running A Search

```powershell
$env:DJ_SIM_DB = "<path-to-library.sqlite>"

python .djts\skills\clap-query-workflow\scripts\project_text_search.py `
  --model mulan `
  --query "broken drums" `
  --positive "A breakbeat track." `
  --positive "A track with broken drums and syncopated percussion." `
  --positive "An electronic club track built on chopped drum breaks and uneven accents." `
  --negative "A four-on-the-floor house track." `
  --negative-weight 0.75 `
  --limit 25
```

Useful flags: `--model clap|mulan`, `--negative-weight 0..2`, `--no-negatives` to drop the negative
bank, `--json` for raw output, `--no-db-check` to skip the database guard. `--query` is shorthand for
one more positive prompt, not a separate field.

Start broad: omit `min_similarity`, or keep it low. Seed-search thresholds do not transfer here.

The CLI `dj-sim text-search` currently accepts one query and no negatives. Use it only for a quick
single-prompt check.

## Reading Results

- Report the prompt bank you used, then score, track id, artist/title, and path.
- With negatives the score is contrast evidence: positive match minus a weighted share of the
  strongest negative match. Show `positive` and `negative` separately when they explain a result.
- If the list is too vocal, too straight, too acoustic, or otherwise off, change one thing at a time:
  first the positives, then the negatives, then the weight. Re-run and compare.

## Measuring A Change

Any claim that one bank beats another is checkable:

```powershell
python scripts\text_prompt_benchmark.py --db database\volumes.sqlite --models mulan,clap
```

It scores prompt forms against the Rhythm Lab labels and reports ROC-AUC, average precision and the
median library rank. Those labels belong to the catalog of `database\volumes.sqlite`; the
currently selected library has a different catalog and does not join to them.

## Bundled Resources

These ship with this skill and live under `.djts/skills/clap-query-workflow/`.
Every other path in this file is relative to the repository root.

- `.djts/skills/clap-query-workflow/scripts/project_text_search.py`: posts a prompt bank to the
  running API for either text model.
- `.djts/skills/clap-query-workflow/scripts/validate_prompt_bank.py`: model-free structural check
  for a bank you are drafting, before it becomes a preset.
- `.djts/skills/clap-query-workflow/scripts/score_prompt_bank.py`: standalone audio-file scorer for
  experiments outside the project DB. It must load PyTorch checkpoints with `weights_only=True`.
- `.djts/skills/clap-query-workflow/references/clap_prompting_reference.md`: LAION-CLAP prompt
  engineering background.

## Implementation Changes

When changing text-layer code:

- Verify the current code path first; this project rewrites its own structure often.
- Model a multiline field as one prompt per non-empty line.
- Keep `positive_queries` and `negative_queries` as arrays through frontend, API and backend, and keep
  `TextSearchRequest` aligned with `frontend/src/apiClient.ts`.
- `positive_queries` is the only prompt field and is required. There is no `query` string beside it,
  no `preset`, and no switch that reduces the bank to its first line.
- Mean-pool normalized positive embeddings before scoring.
- Never imply that text-search scores are calibrated probabilities.
- Text search must not modify audio files or write into `classifier_scores`.

## Verification

- Skill scripts: `.\.venv\Scripts\python.exe -m pytest tests\test_clap_query_workflow_scripts.py --override-ini addopts=`
- API helper smoke: `python .djts\skills\clap-query-workflow\scripts\project_text_search.py --help`
- Frontend prompt changes: `cd frontend; node --test tests/textPromptPresets.test.mjs`
- Backend scoring/API changes: `.\.venv\Scripts\python.exe -m pytest tests\test_api_text_search.py --override-ini addopts=`
