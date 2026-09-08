# Prompt banks and retrieval evidence

## Contents

- [Edit the vocabulary](#edit-the-vocabulary)
- [Six lines per model](#six-lines-per-model)
- [Draft JSON and validation](#draft-json-and-validation)
- [Production scoring](#production-scoring)
- [Preserve a search](#preserve-a-search)
- [Compare models reproducibly](#compare-models-reproducibly)

## Edit the vocabulary

`frontend/src/textPromptPresets.ts` owns categories, axes, labels, hints, model
banks, and negative weights. Read the requested entry, its neighbors, and
`composePromptBanks` before editing. Keep `positive.shared` empty when providing
complete separate `clap` and `mulan` arrays. Do not merge model banks or maintain
a second preset registry in this skill.

Own the edit here; no separate curator skill is required. Preserve a preset key
for wording or display changes that retain its meaning. A different concept
needs a distinct key so existing feedback is not silently reinterpreted. Inspect
the current feedback contract before changing identity or persisted behavior.

Check `frontend/src/textSearchExecution.ts`, `frontend/src/api.ts`, and
`src/dj_track_similarity/api/schemas.py` for the affected request boundary. The
current backend accepts generic preset keys and prompt arrays; it does not need
a duplicate vocabulary entry for every new label. Change both sides together
only when an actual payload or behavior contract changes.

Review each line against the axis definition and neighboring labels. For
example, **Introspective** describes an inward, reflective mood; it does not
require slow tempo, quiet dynamics, sparse texture, sadness, or romance.
Rhythm describes beat placement; Groove describes timing and motion. A valid
JSON bank can still blur these boundaries. State any unresolved semantic overlap.

## Six lines per model

For each preset and each model, keep exactly six English positive strings in
this order. This is the curation format, not evidence that six prompts outperform
other counts. Each full string is one prompt; commas remain inside that string.

| Lines | CLAP writing form | MuQ-MuLan writing form |
|---|---|---|
| 1-2 | Two short track-centered anchors | Two compact anchors or label templates |
| 3-4 | Two concise keyword lists with a track frame | Two lowercase bare keyword lists, without a final period |
| 5-6 | Two concrete descriptions of the target property in the track | Two short descriptions of the same property |

Use musical terms precisely and vary wording without adding another axis. Avoid
whole-line duplicates, competing concepts in positives, and negated descriptions
such as "without vocals". Name a real unwanted class in the negative bank when
needed. Do not invent negatives merely to populate a field or choose a high
weight without comparison. Current weights and composition rules come from code.

An illustrative Introspective draft follows; review the live preset rather than
treating this example as another source of truth.

```text
CLAP
The track has an introspective mood.
A contemplative track.
This track evokes introspection, contemplation, self-reflection.
This track feels reflective, inward-looking, thoughtful.
This track invites reflection on personal thoughts and feelings.
The track conveys a sense of looking inward and examining one's inner life.

MuQ-MuLan
Introspective mood.
A contemplative track.
introspective, contemplative, reflective
self-reflection, inner thoughts, contemplation
The music invites reflection on personal thoughts and feelings.
An inward-looking mood encourages awareness of one's inner life.
```

Keep lines concise. The validator's punctuation/word count is an approximation,
not either model's tokenizer. Exact truncation depends on the actual adapter and
tokenizer configuration; do not apply a universal token ceiling or load a model
just to validate the bank's structure.

## Draft JSON and validation

The standalone scripts keep this interchange shape, separate from the TypeScript
preset registry and the benchmark's concept/form JSON:

```json
{
  "labels": {
    "Introspective": {
      "prompts": [
        "The track has an introspective mood.",
        "A contemplative track.",
        "This track evokes introspection, contemplation, self-reflection.",
        "This track feels reflective, inward-looking, thoughtful.",
        "This track invites reflection on personal thoughts and feelings.",
        "The track conveys a sense of looking inward and examining one's inner life."
      ],
      "hard_negatives": []
    }
  },
  "global_hard_negatives": []
}
```

Save the reviewed draft to a task-specific JSON file; use a separate file for
each model. In the commands below, `$clapDraftPath` and `$mulanDraftPath` are those
existing files, verified with `Resolve-Path -LiteralPath`. Run from the repo root:

```powershell
& .\.venv\Scripts\python.exe .djts/skills/text-music-search/scripts/validate_prompt_bank.py $clapDraftPath --model clap
& .\.venv\Scripts\python.exe .djts/skills/text-music-search/scripts/validate_prompt_bank.py $mulanDraftPath --model mulan
```

Structural errors include a non-object root, empty label/prompt banks, and
non-string or blank positive/negative entries, including global negatives.
`--model` adds writing advice. Warnings about approximate length, duplication, or
style are review prompts; passing validation does not prove six-line balance,
axis separation, or retrieval quality.

## Production scoring

Read `src/dj_track_similarity/search/engine.py:_contrast_vector_scores` and
`src/dj_track_similarity/api/routes_search.py` for current execution. The default
contrast path normalizes each positive vector, averages them, and normalizes
the mean. For each eligible stored audio vector, it subtracts the weighted mean
of the **two highest** negative similarities. A single negative supplies that
one value; an empty negative bank contributes zero.

The request's preset composition and any applied feedback can affect the query.
Use the response's `execution.query_context` and `execution.feedback` to identify
what ran. Scores are ranking evidence, not calibrated probabilities, and scales
do not transfer between families. The separate CLAP audio experiment uses
**maximum** negative similarity and newly computed windows, so its scores cannot
be presented as production results.

## Preserve a search

The API helper accepts repeated `--positive` / `--negative`, line-based
`--positive-file` / `--negative-file`, and additional positive text via `--query`.
Multiline values become separate non-empty prompts; commas do not split a line.
JSON label banks must first be exported to positive/negative text lines, not
passed as a line-based input file. For a chosen label, concatenate its negatives
with global negatives deliberately; do not combine unrelated positive labels.

Resolve the user-confirmed library and existing line files before running. The
following variables represent those paths, and `$mulanRunPath` / `$clapRunPath`
are distinct new JSON output paths in the task's working output directory:

```powershell
& .\.venv\Scripts\python.exe .djts/skills/text-music-search/scripts/project_text_search.py `
  --model mulan --expected-db $libraryPath --positive-file $mulanPositivePath --limit 25 --json |
  Set-Content -LiteralPath $mulanRunPath -Encoding utf8
& .\.venv\Scripts\python.exe .djts/skills/text-music-search/scripts/project_text_search.py `
  --model clap --expected-db $libraryPath --positive-file $clapPositivePath --limit 25 --json |
  Set-Content -LiteralPath $clapRunPath -Encoding utf8
```

When negatives are intended, add the corresponding `--negative-file` and the
reviewed `--negative-weight`. Omit `--min-similarity` for rank-only comparisons.
Check each process exit code and parse both saved JSON objects. Retain their
complete `{results, execution}` envelopes, not just track lists. Plain output
also identifies the run, query, model, and feedback status.

The expected database comes from `--expected-db`, then `DJ_SIM_DB` or
`DJ_TRACK_SIMILARITY_DB`. Missing or nonexistent targets fail before HTTP. The
helper checks the selected database and catalog, then rejects a response from a
different catalog. `--no-db-check` explicitly skips that guard; do not use it to
work around an unknown target. Do not switch the server's database automatically.

Manual banks use the custom request mode. These runs do not imply preset
attribution, paired product A/B, or feedback application. The existing UI sends
preset banks and comparison metadata through `frontend/src/textSearchExecution.ts`.
No automatic feedback writes are part of this helper.

## Compare models reproducibly

First choose the comparison: the same prompts test a wording-controlled model
comparison; separate curated banks compare two model-plus-prompt configurations.
Record the distinction. Preserve each bank and full search response, including
catalog, family/output identity, code revision, eligible count/digest, composition,
feedback state, and run/query identifiers. Unequal eligible track coverage or
changed feedback makes a ranking comparison confounded; disclose it or define
a common evaluation pool. A pair of searches alone does not establish a winner.

For labeled measurements, inspect `scripts/text_prompt_benchmark.py` and the
existing `scripts/text_prompt_benchmark_prompts.json` schema. It uses concepts
with `classifier_key`, positive/negative label names, and named forms containing
`positive` / `negative` arrays. Confirm both label classes resolve in the named
library; never repurpose unrelated judgments for a new Mood concept.

With an explicitly confirmed library and labels database, this evaluates the
existing benchmark definitions without inventing a missing starter asset:

```powershell
& .\.venv\Scripts\python.exe scripts/text_prompt_benchmark.py `
  --db $libraryPath --labels $labelsPath `
  --prompts scripts/text_prompt_benchmark_prompts.json --models mulan,clap --out $benchmarkOutputPath
```

Those existing definitions do not automatically include a new preset. To
evaluate different banks per model, prepare two JSON files in the benchmark's
actual schema and run them separately with `--models clap` and `--models mulan`.
Use matching concepts, judgments, vector identities, and candidate pools; retain
the commands, input hashes, parameters, and output tables. The benchmark loads
text models, so run it only within an authorized real-model task.

The current report marks its reused training-library judgments
`exploration_in_sample`. They support exploratory measurements, not held-out
generalization. Missing judgments mean the new preset can be structurally and
semantically reviewed, but its quality is unmeasured. Do not repeat historical
model superiority or loading-time claims without current reproducible evidence.
Project reliability claims require a committed benchmark table under the
project's delivery rules; do not commit or publish unless authorized.
