# Scripts

The `scripts/` directory and two extra files under `tools/audio-dedup/` hold the diagnostic,
benchmark, and research helpers. They are separate from the `dj-sim` CLI and are run with `python`
directly.

Nine of them read and report. This page covers what each one answers, how to invoke it, and what it
leaves on disk. [CLI reference](../reference/commands.md) carries the full argument tables.

## Pick a script by the question

| Question | Script |
| --- | --- |
| Is my library database intact? | `qa_database.py` |
| How fast is vector search at N tracks? | `benchmark_search.py` |
| Which prompt wording finds a concept best? | `text_prompt_benchmark.py` |
| Would fusing CLAP and MuQ-MuLan help? | `text_fusion_benchmark.py` |
| Does a preset label agree with SONARA evidence? | `text_tag_crosscheck.py` |
| Which bank lines earn their place? | `prompt_preset_tune.py` |
| How would another CLAP checkpoint score? | `clap_checkpoint_embed.py` |
| Is this file a transcode wearing a lossless container? | `spectral_check_cli.py` |
| How well does duplicate candidate retrieval recall? | `benchmark_fingerprint_candidates.py` |

## What they write

None of the nine writes to your library database or to an audio file tag. `classifier_scores` stays
untouched as well. Every SQLite connection they open uses the `?mode=ro` URI, which SQLite
enforces.

The only files they produce are the reports you ask for, one `.npz` sidecar from
`clap_checkpoint_embed.py`, and the throwaway database `benchmark_search.py` builds for itself.

One caution. `scripts/` also holds `optimize_database.py`, which backs up and vacuums a real
database, and `run_server_launcher.py`, which starts processes. Neither is read-only, so the
guarantee above covers the nine scripts on this page rather than the directory.

## qa_database.py

Read-only integrity QA for one library database and its optional Evaluation sidecar.

```powershell
python scripts\qa_database.py --db .\data\library.sqlite
```

`--db` is required. `--evaluation-db` is optional, and without it the sidecar path is derived from
the library path. A missing sidecar is fine rather than an error.

The run executes `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, the library schema
validation, and a track count. Output goes to stdout only: `QA PASSED` with the catalog UUID and
track count, or `FAIL: <reason>`. Exit code `0` on pass, `1` on failure.

Unknown future tables in the library do not fail QA, which is pinned by
`scripts/tests/test_qa_database_script.py`.

## benchmark_search.py

Builds a synthetic library and measures MERT and MAEST vector-search timing on it. It never reads
your library.

```powershell
python scripts\benchmark_search.py --output .\reports\search-benchmark.json
```

`--output` is required. `--track-count` repeats, or `--track-counts 1000,10000` takes a list, and
the two are mutually exclusive. Defaults are one run at `1000` tracks, `--seed-count 20`,
`--per-source 30`, and `--random-seed 123`.

The synthetic database lives in a temporary directory that is deleted afterwards. `--keep-db PATH`
keeps it instead, and refuses to overwrite an existing file.

The JSON report records setup time, embedding-matrix load time per source, and exact-search timing
with p50 and p95 seconds, plus process resident memory. Embeddings are random 768-dimensional
vectors, so the numbers measure the search path rather than retrieval quality.

## text_prompt_benchmark.py

The evidence base for every text-search reliability claim in this project. `AGENTS.md` requires a
committed table from this script before any such claim is made.

```powershell
python scripts\text_prompt_benchmark.py --db .\data\library.sqlite
```

Only `--db` is required. The defaults that matter:

| Option | Default |
| --- | --- |
| `--labels` | `tools/rhythm-lab/database/rhythm_lab.sqlite` |
| `--prompts` | `scripts/text_prompt_benchmark_prompts.json` |
| `--models` | `mulan,clap` |
| `--device` | `auto` |
| `--concepts` | empty, meaning every concept in the prompt file |

The `--labels` default is a relative path, so run this from the repository root.

**Where the labels come from.** The Rhythm Lab labels database, table `classifier_labels`.
Resolution is UUID-first with a file-path fallback, because a rescan regenerates track UUIDs. A
concept whose positive or negative side resolves to zero rows is skipped with a note rather than
failing the run.

**The frozen spec.** `scripts/text_prompt_benchmark_prompts.json` holds five concepts and their
prompt forms. Each concept names a `classifier_key`, a positive label, a negative label, and a set
of forms, each with its own positive and negative prompt lists.

| Concept | Forms |
| --- | --- |
| `break_energy` | 11 |
| `minimal_deep_tech` | 10 |
| `abstract_edge` | 8 |
| `voice_presence` | 8 |
| `live_instrumentation` | 8 |

The file deliberately keeps wordings that measured badly, so a published comparison stays
reproducible.

**Metrics.** Four per row, with a scope difference worth knowing:

- `ROC-AUC` and `AP` are computed over the labelled pool.
- `P@20` is precision in the top 20 of the ranking **within the labelled pool**, not the top 20 of
  the library.
- `med.rank` is the median library-wide rank of the positive tracks.

**The weight sweep.** `0.0, 0.15, 0.35, 0.5, 0.75, 1.0`. A non-zero weight is skipped for a form
with no negative bank. Negative pooling is always evaluated as `max`, which is the production
behavior, plus `top2-mean` when the bank holds two or more negatives. `--centered` adds a second
scoring space with the library mean removed.

**Where the table goes.** Stdout only. `--out PATH` writes JSON containing the same measurements as
a flat array, not the rendered table. To satisfy the `AGENTS.md` requirement, copy the stdout table
into your commit by hand. Its columns:

```text
concept  model  form  space  pooling  w  ROC-AUC  AP  P@20  med.rank
```

Each concept group closes with a `best:` line naming the winning combination.

**What it needs.** Model weights for the selected families, so the `ml` extra, plus scikit-learn
from the `rhythm-lab` extra. It reads no audio.

To evaluate a non-production CLAP checkpoint, embed the pool first with `clap_checkpoint_embed.py`
and pass the sidecar through `--clap-vectors`. The script refuses a non-production
`--clap-checkpoint` without one.

## text_fusion_benchmark.py

Measures whether fusing CLAP and MuQ-MuLan rankings beats the better single model. This is the
measurement that rejected fusion.

```powershell
python scripts\text_fusion_benchmark.py --db .\data\library.sqlite
```

`--db` is required. `--references` defaults to `scripts/text_tag_crosscheck_references.json`. The
two families are fixed, so there is no model option.

Arms tested: reciprocal rank fusion at `k` of `10`, `60`, and `200`, MuQ-MuLan weights of `0.5`
through `0.8`, a z-score sum, and a cascade at depth `500`. Wins and losses use a `0.002` dead band.
Two report blocks are printed, one for global ordering by ROC-AUC and one for the share of the
reference inside the first 100 results, each against a per-label oracle.

`--out PATH` writes JSON with the single-model scores, the fusion arms, and the top-of-list variants
of both.

## text_tag_crosscheck.py

Cross-checks each text preset label against SONARA and MAEST evidence, without needing a labelled
pool.

```powershell
python scripts\text_tag_crosscheck.py --db .\data\library.sqlite
```

`--db` is required. `--references` defaults to `scripts/text_tag_crosscheck_references.json`, and
`--models` defaults to `mulan,clap`.

It reports one verdict per label and model: `ok`, `weak`, `suspect`, `consistent`, or `INVERTED`.
`INVERTED` means the label ranked the reference backwards. Key thresholds are `TOP_K = 100`, a
strong binary agreement at `0.70`, a weak one at `0.55`, and an extreme quantile of `0.9`. A
reference column covering under 90 percent of rows is dropped with a note.

The committed reference file currently holds 37 label entries, all backed by SONARA fields such as
`dissonance_score`, `onset_density_per_second`, and `acousticness_score`. It also records two
retirements in place: the vocal-probability reference and the MAEST genre-head references were both
withdrawn.

This script refuses to use promoted classifier outputs as references.

## prompt_preset_tune.py

Turns accumulated relevance verdicts into wording and weight proposals. Report-first, and it writes
no preset file.

```powershell
python scripts\prompt_preset_tune.py --db .\data\library.sqlite
```

`--db` is required. `--min-per-class` defaults to `5`, the number of relevant and irrelevant
verdicts a preset needs before it is tuned. `--presets` narrows the run to the keys you list.

Input is the `text_preset_feedback` table, which the thumbs-up and thumbs-down buttons in the
PROMPT tab write. For each qualifying preset the script scores the current bank, then one
leave-one-out variant per positive and per negative line, over a weight grid of
`0.0, 0.25, 0.5, 0.75, 1.0`. The output table shows the pool size, the current score, the best
score, and the gain.

Trained classifier outputs play no part here. The verdicts are your own listening decisions.

Run it from the repository root: it imports two sibling scripts by name and relies on `scripts/`
being on the path.

## clap_checkpoint_embed.py

Embeds the labelled pool with one pinned LAION-CLAP checkpoint into an `.npz` sidecar, so
`text_prompt_benchmark.py` can score a candidate checkpoint without touching the library.

```powershell
python scripts\clap_checkpoint_embed.py --db .\data\library.sqlite --checkpoint music_speech_audioset_epoch_15_esc_89.98.pt --out .\reports\candidate.npz
```

`--db`, `--checkpoint`, and `--out` are required. The checkpoint must be one of the two names the
script pins by SHA-256, and an unpinned name is refused. `--source` defaults to `audio` and decodes
files. The `stored` value reuses stored embeddings and is accepted only for the production
checkpoint. `--batch-size` defaults to `16` and `--device` to `auto`.

This is the one script on this page that reads audio. It writes exactly one file, the `.npz` holding
track IDs, vectors, and the checkpoint name.

## spectral_check_cli.py

A standalone transcode detector. It estimates each file's spectral cutoff and flags a file that
declares lossless or a high bitrate while its spectrum stops early.

```powershell
python tools\audio-dedup\spectral_check_cli.py --list files.txt --csv verdicts.csv
python tools\audio-dedup\spectral_check_cli.py "D:\Music\Folder" "D:\Music\one.mp3"
```

Positional targets are files or directories, and a directory is scanned recursively. `--list PATH`
reads one path per line. `--csv PATH` writes every verdict rather than only the suspects.

It needs `ffmpeg` and `ffprobe` on `PATH`, and exits `2` without them or with no files to analyze.
It opens no database. It reads audio and measures, and never rewrites a file.

Verdicts are `clean`, `suspected_transcode`, or `skipped`. The CSV columns are `path`, `verdict`,
`cutoff_hz`, `sharpness_db`, `sample_rate`, and `note`. The detection gates are a cutoff at or below
`19450` Hz combined with a rolloff sharpness of at least `14` dB.

The calibration is recorded in the source. It was measured against a commercial reference over 1000
library files holding 37 confirmed transcodes. The score was 10 false alarms and 5 misses, and every
miss fell in the 224 to 256 kbps class.

## benchmark_fingerprint_candidates.py

Compares fingerprint and embedding candidate retrieval for Audio Dedup on synthetic data.

```powershell
python tools\audio-dedup\benchmark_fingerprint_candidates.py --out .\reports\candidates.json
```

No argument is required. `--groups` defaults to `32`, `--distractors` to `128`, and `--seed` to
`20260826`. Without `--out` the JSON goes to stdout.

Everything is generated in memory, so it opens no database and reads no audio. The report compares
fingerprint LSH, embedding LSH, and their union on recall, a precision proxy, and retrieval time,
and it carries its own `limits` block stating that a synthetic fixture does not estimate real-library
precision.

## Requirements by group

| Scripts | Needs |
| --- | --- |
| `qa_database.py`, `benchmark_search.py`, `benchmark_fingerprint_candidates.py` | the base install |
| `spectral_check_cli.py` | `ffmpeg` and `ffprobe` on `PATH` |
| the four text scripts and `clap_checkpoint_embed.py` | the `ml` extra for weights, the `rhythm-lab` extra for scikit-learn |
| `text_tag_crosscheck.py`, `text_fusion_benchmark.py`, `prompt_preset_tune.py` | Node plus an installed `frontend/node_modules`, because they read the preset vocabulary out of `textPromptPresets.ts` through a Node subprocess |

That last row is easy to miss. Without `frontend/node_modules`, those three fail on a subprocess
error rather than a clear message.

## Tests

Root pytest configuration collects only `tests/`, so name the script suite explicitly:

```powershell
python -m pytest scripts/tests
python -m pytest tools/audio-dedup/tests
```

| Script | Covered by |
| --- | --- |
| `qa_database.py` | `scripts/tests/test_qa_database_script.py` |
| `benchmark_search.py` | `scripts/tests/test_benchmark_search.py` |
| `clap_checkpoint_embed.py` | `scripts/tests/test_clap_checkpoint_embed.py` |
| `text_prompt_benchmark.py` | partial, through the sidecar and guard paths in the same file |
| `spectral_check_cli.py` | `tools/audio-dedup/tests/test_spectral.py` |
| `benchmark_fingerprint_candidates.py` | `tools/audio-dedup/tests/test_fingerprint_benchmark.py` |

`text_fusion_benchmark.py`, `text_tag_crosscheck.py`, and `prompt_preset_tune.py` have no test file.

## Related pages

- [CLI reference](../reference/commands.md)
- [Text search](../user-guide/text-search.md)
- [Optimize database](./optimize-database.md)
- [Audio Dedup](./audio-dedup.md)
