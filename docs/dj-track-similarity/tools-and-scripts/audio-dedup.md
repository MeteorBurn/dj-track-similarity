# Audio Dedup

Audio Dedup reads an existing SQLite library and writes JSON/XLSX/log reports by default. It uses stored analysis data and local paths. It does not scan unknown folders outside the selected root.

## Requirements

Audio Dedup needs stored audio-to-audio evidence. The available embedding sources are `mert`,
`maest`, `muq`, and `clap`. The reader accepts vectors whose dimensions, encoding, and track
identity match the current structural requirements.

When the library has saved SONARA fingerprints, Audio Dedup also uses them as an independent
candidate-retrieval signal. It reads only fingerprints whose stored `track_uuid`, positive
version, timestamp, and Base64 payload validate against the current track. It does not analyse
audio again or keep full fingerprint payloads on track records.

The `min_similarity` value is an audio-to-audio content gate. It is not the CLAP text-search score scale, and none of these values are probabilities.

## Sources and weights

The default CLI profile enables all four embedding sources:

| Source | Raw weight |
| --- | ---: |
| MERT | 0.43 |
| MAEST | 0.32 |
| MuQ | 0.12 |
| CLAP | 0.04 |

Raw weights are configuration coefficients, not percentages. The scorer divides by the total weight of the enabled evidence that is available for a pair. The duplicate score can also include stored SONARA and duration evidence.

The CLI accepts repeatable `--source` and `--weight FAMILY=VALUE` options.

Validation is fail-closed:

- `sources` must be nonempty, unique, and limited to the four supported families.
- When `weights` is supplied, its keys must exactly match the enabled sources.
- Every weight must be finite and nonnegative, and at least one must be positive.

## Candidate retrieval and fingerprint review

Candidate construction takes a set union rather than applying one signal after another.

| Signal | Candidate-retrieval role |
| --- | --- |
| MERT/MAEST LSH | Used for suitable high-dimensional embeddings. |
| Duration window | Used when embedding LSH produces no candidate pairs. |
| SONARA fingerprint LSH | Uses compact descriptors from valid stored fingerprints. A pair must share one 24-bit key made from two adjacent 12-bit bands. Comparisons stay inside one fingerprint version. |

The native SONARA matcher then verifies pairs retrieved by either fingerprint LSH or MERT/MAEST
LSH. Pairs found only by the duration window do not trigger native fingerprint matching. This
keeps the expensive comparison out of the broad duration fallback. The 24-bit fingerprint key
also filters accidental LSH collisions before native verification, while either LSH signal can
still contribute fingerprint evidence.

An exact native fingerprint score of at least `0.45` can create a **manual-review** candidate,
even when embeddings or duration data are absent. A pair retrieved only by `fingerprint_lsh`
never becomes an automatic delete candidate: it carries an explicit manual-review blocker. The
normal MERT/MAEST, content-similarity, duration, identity, and confirmation requirements for
safe deletion remain in force.

The order in which the two independent LSH paths are scheduled changes latency only, not their
union of candidate pairs. A synthetic comparison is available for recall and cost checks:

```powershell
python tools\audio-dedup\benchmark_fingerprint_candidates.py --groups 32 --distractors 128
```

It uses known synthetic duplicate groups, reports retrieval recall, candidate-pair counts, and
timing for fingerprint LSH, embedding LSH, and their union. It does not estimate precision on a
real music library. Run Audio Dedup in report-only mode and listen to the fingerprint-review pairs
before changing the review threshold.

To disable MuQ and reproduce the exact legacy source profile, select only MERT, MAEST, and CLAP. Omitting explicit weights gives those sources their legacy raw weights:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music `
  --source mert --source maest --source clap
```

This exact profile uses MERT 0.43, MAEST 0.32, and CLAP 0.04. Any other source or weight configuration uses the non-legacy deletion-safety rules below.

## CLI report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

The CLI updates one console line while it runs. It loads track records and only
the selected embedding families in SQLite chunks of 200 tracks, showing the
phase, percentage, and processed items as `N/M`. During pair scoring, `N/M`
refers to candidate pairs.

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

The tool deletes only safe duplicate candidates inside the selected `--root`. Before deletion it rechecks the report identity fields `catalog_uuid` and `track_uuid`, the stored path, and the reported `size` and `file_modified_ns`. Stale or mismatched candidates are skipped.

SQLite rows are removed only for tracks whose files were deleted.

Do not run apply mode during routine tests. Review the report first and keep backups when the library matters.

## Output

Reports default under `tools/audio-dedup/data/reports/` and include JSON, XLSX, and log output. The JSON payload records `sources`, `weights`, and `fingerprint_retrieval` metrics: validated and rejected stored fingerprints, LSH/exact candidate counts, the review-pair count, and the threshold. Pair evidence records `fingerprint_similarity` and `candidate_sources`; the XLSX Pair Evidence sheet exposes the same provenance, while its Summary sheet lists valid fingerprints and fingerprint-review pairs. Safety failures appear in `blocked_reasons`.

Reports are local private artifacts.
