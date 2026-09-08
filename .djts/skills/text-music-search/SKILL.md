---
name: text-music-search
description: Use when searching a local music library from text with CLAP or MuQ-MuLan, creating or editing prompt presets and axes, choosing a text model, evaluating retrieval results, or working with textPromptPresets and /api/search/text in dj-track-similarity.
---

# Text Music Search

Turn listening intent into English prompt banks, curate presets, and evaluate
CLAP and MuQ-MuLan retrieval. Invoke with `$text-music-search`.

## Scope and sources

Own the text-to-track layer, including vocabulary editing. Audio-to-audio search,
other model layers, classifier training, and Model Listening Lab remain separate.
Preserve source audio and library data; do not write text tags into classifier scores.

Work from the repository root and read its `AGENTS.md`. Code and command paths
below are repository-relative; inspect current source before relying on defaults:

- `frontend/src/textPromptPresets.ts`: presets, axes, categories, and model banks.
- `frontend/src/textSearchExecution.ts`: UI request composition and comparison.
- `src/dj_track_similarity/api/schemas.py` and `src/dj_track_similarity/api/routes_search.py`: payloads and execution context.
- `src/dj_track_similarity/search/engine.py`: production contrast scoring.
- `src/dj_track_similarity/embedding/registry.py` and `src/dj_track_similarity/embedding/text_cache.py`: adapter selection and lifetime.
- `scripts/text_prompt_benchmark.py`: reproducible measurements.

## Workflow

1. Identify the requested property and scope. For vocabulary edits, follow
   [prompt banks](references/prompt_banks.md) directly. Keep separate model banks,
   each with six English lines: two anchors, two keyword lists, two descriptions.
   Review axis meaning and competing labels, not just string counts.
2. Establish the explicitly named or confirmed library. Never choose a database
   from launcher defaults, filenames, or timestamps. Without a target, finish
   drafting and validation, then obtain it before searching.
3. Use `.djts/skills/text-music-search/scripts/project_text_search.py` for manual banks and explicit
   `--model clap|mulan`. Supply `--expected-db` or the confirmed `DJ_SIM_DB` /
   `DJ_TRACK_SIMILARITY_DB`. It verifies the selected path and catalog, including
   the response catalog. `--no-db-check` is an explicit bypass, never a fallback
   for an unknown database. `--query` adds positive lines; it is not a title.
4. Preserve the complete `--json` response: `results` **and** `execution`.
   Record model, prompts, run identifiers, catalog, output identity, eligibility,
   and feedback status. This helper sends custom banks; use the existing UI for
   preset attribution, product A/B, and feedback workflows.
5. Compare rankings and listening judgments. Change one variable at a time;
   never compare raw scores across families as probabilities or declare a
   universal winner. Follow the reference's measurement procedure and report
   missing labels, coverage, and exploratory evidence explicitly.

## Tools and verification

Use the existing root `.venv`; dependency maintenance follows the project's `uv`
workflow. No separate environment or pip installation recipe belongs here.

- `.djts/skills/text-music-search/scripts/validate_prompt_bank.py`: model-free JSON checks, optional `--model` advice.
- `.djts/skills/text-music-search/scripts/project_text_search.py`: manual library searches with execution provenance.
- `.djts/skills/text-music-search/scripts/score_prompt_bank.py`: separate [CLAP audio experiment](references/clap_audio_experiment.md).
  Its window scores and maximum-negative pooling do not reproduce production search.

Run script `--help` and the owning suite with the root interpreter:
`& .\.venv\Scripts\python.exe -m pytest tests/test_text_music_search_scripts.py --override-ini addopts=`.
For product edits, follow `AGENTS.md` verification routing. Use temporary fixtures
and model/HTTP stubs for automated checks; real model runs need task authorization.
