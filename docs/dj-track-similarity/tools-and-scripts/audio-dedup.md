# Audio Dedup

> Audience: Users looking for duplicate audio candidates.
> Goal: Run report mode safely and understand apply mode.
> Type: guide

Audio Dedup reads an existing SQLite library and writes JSON/XLSX/log reports by default. It uses stored analysis data and local paths. It does not scan unknown folders outside the selected root.

## Requirements

Audio Dedup needs stored current-contract audio-to-audio evidence. The available embedding sources are `mert`, `maest`, `muq`, and `clap`. The reader ignores stale or mismatched artifacts and accepts only vectors that match the active current analysis contract and the current track identity.

The `min_similarity` value is an audio-to-audio content gate. It is not the CLAP text-search score scale, and none of these values are probabilities.

## Sources and weights

The default CLI and API profile enables all four embedding sources:

| Source | Raw weight |
| --- | ---: |
| MERT | 0.43 |
| MAEST | 0.32 |
| MuQ | 0.12 |
| CLAP | 0.04 |

Raw weights are configuration coefficients, not percentages. The scorer divides by the total weight of the enabled evidence that is available for a pair. The duplicate score can also include stored SONARA and duration evidence.

The CLI accepts repeatable `--source` and `--weight FAMILY=VALUE` options. The `POST /api/audio-dedup/jobs` API accepts equivalent `sources` and `weights` fields.

Validation is fail-closed:

- `sources` must be nonempty, unique, and limited to the four supported families.
- When `weights` is supplied, its keys must exactly match the enabled sources.
- Every weight must be finite and nonnegative, and at least one must be positive.

To disable MuQ and reproduce the exact legacy source profile, select only MERT, MAEST, and CLAP. Omitting explicit weights gives those sources their legacy raw weights:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music `
  --source mert --source maest --source clap
```

This exact profile uses MERT 0.43, MAEST 0.32, and CLAP 0.04. Any other source or weight configuration uses the non-legacy deletion-safety rules below.

## UI flow

Open Audio Dedup from the copy icon in the top bar.

The current React dialog does not expose `sources` or `weights`. Jobs started there use the backend default profile. Use the CLI or API to select sources or change weights. The frontend source/weight controls are deferred.

Controls:

- **Root**: only DB tracks inside this stored path root are considered.
- **Path contains**: optional case-insensitive path filters, split by line, comma, or semicolon.
- **Preset**: safe, balanced, or aggressive.
- **Min score**: optional `0..1` override.
- **Min similarity**: optional `0..1` audio-to-audio gate over the enabled embedding sources.
- **Limit groups**: optional maximum number of groups.
- **Output dir**: report directory.

Click **Start** for report mode. The UI shows progress and opens the XLSX report when complete.

## CLI report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Optional examples:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --path-contains wav --limit-groups 50
```

An explicit default source profile looks like this:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music `
  --source mert --source maest --source muq --source clap `
  --weight mert=0.43 --weight maest=0.32 --weight muq=0.12 --weight clap=0.04
```

## Safe-delete corroboration

MuQ and CLAP can affect ranking and report candidates, but they cannot replace MERT plus MAEST evidence for automatic deletion.

The exact legacy profile keeps its previous aggregate gate. Every non-legacy source or weight configuration requires:

- current MERT and MAEST evidence for the pair;
- a positive MERT weight and a positive MAEST weight;
- an independent MERT-plus-MAEST weighted similarity that meets the preset `min_similarity`;
- the existing duration compatibility gate.

A high MuQ or CLAP similarity by itself can produce a review candidate, but never a safe delete candidate.

## Apply mode

Apply mode is destructive. It requires exact confirmation:

```text
APPLY DELETE
```

The tool deletes only safe duplicate candidates inside the selected `--root`. Before deletion it rechecks the report identity fields `catalog_uuid`, `track_uuid`, and `content_generation`, the stored path, and the reported `size` and `file_modified_ns`. Stale or mismatched candidates are skipped.

SQLite rows are removed only for tracks whose files were deleted.

Do not run apply mode during routine tests. Review the report first and keep backups when the library matters.

## Output

Reports default under `tools/audio-dedup/data/reports/` and include JSON, XLSX, and log output. The JSON payload records `sources` and `weights`. Pair evidence and the XLSX candidate/evidence sheets include `muq_similarity`. Safety failures appear in `blocked_reasons`.

Reports are local private artifacts.
