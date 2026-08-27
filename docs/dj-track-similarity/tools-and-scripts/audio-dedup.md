# Audio Dedup

Audio Dedup reads an existing SQLite library and writes JSON/XLSX/log reports by default. It uses stored analysis data, local paths, and a read-only FFmpeg decode of duplicate-group files for the spectral check below. It does not scan unknown folders outside the selected root and never modifies source audio.

## Requirements

Audio Dedup needs stored audio-to-audio evidence. The available embedding sources are `mert`,
`maest`, `muq`, and `clap`. The reader accepts vectors whose dimensions, encoding, and track
identity match the current structural requirements.

When the library has saved SONARA fingerprints, Audio Dedup also uses them as an independent
candidate-retrieval signal. It reads only fingerprints whose stored `track_uuid`, positive
version, timestamp, and Base64 payload validate against the current track. It does not analyse
audio again or keep full fingerprint payloads on track records.

The `min_similarity` value is an audio-to-audio content gate. It is not the CLAP text-search score scale, and none of these values are probabilities.

The spectral transcode check needs `ffmpeg` on `PATH`. Without it, that check is skipped with an
`ffmpeg unavailable` note while the duplicate search still runs.

## Search modes

The CLI has two mutually exclusive search modes:

- `--fingerprint` is the primary mode and the default, so a run without a mode flag behaves
  identically. Duplicates are decided from exact SONARA fingerprint matches alone, and every
  reported candidate stays manual-review.
- `--embedding` is the secondary mode and the previous default behavior. Duplicates are scored
  from the enabled embedding families with the preset gates, and exact fingerprint checks of
  embedding-shortlisted pairs still add manual-review pairs. It is the only mode that can produce
  safe delete candidates for `--apply`.

Passing both flags is a CLI argument error. `--source` and `--weight` require `--embedding`.
The JSON report records the selected mode as `search_mode`.

## Sources and weights

`--embedding` mode enables all four embedding sources by default:

| Source | Raw weight |
| --- | ---: |
| MERT | 0.43 |
| MAEST | 0.32 |
| MuQ | 0.12 |
| CLAP | 0.04 |

Raw weights are configuration coefficients, not percentages. The scorer divides by the total weight of the enabled evidence that is available for a pair. The duplicate score can also include stored SONARA and duration evidence.

In `--embedding` mode the CLI accepts repeatable `--source` and `--weight FAMILY=VALUE` options.

Validation is fail-closed:

- `--source` and `--weight` require `--embedding`.
- `sources` must be nonempty, unique, and limited to the four supported families.
- When `weights` is supplied, its keys must exactly match the enabled sources.
- Every weight must be finite and nonnegative, and at least one must be positive.

## Candidate retrieval and fingerprint review

In `--embedding` mode, candidate construction takes a set union rather than applying one signal
after another. Fingerprint mode instead retrieves from fingerprint LSH alone.

| Signal | Candidate-retrieval role |
| --- | --- |
| MERT/MAEST LSH | Used in `--embedding` mode for suitable high-dimensional embeddings. |
| Duration window | Used in `--embedding` mode when embedding LSH produces no candidate pairs. |
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
  --embedding --source mert --source maest --source clap
```

This exact profile uses MERT 0.43, MAEST 0.32, and CLAP 0.04. Any other source or weight configuration uses the non-legacy deletion-safety rules below.

## Fingerprint mode

`--fingerprint` decides duplicates from stored SONARA fingerprints alone. It is the default, so
this run selects it without a mode flag:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music
```

In this mode no embeddings are loaded. Candidate retrieval uses only the version-separated
fingerprint LSH, and neither embedding signature LSH nor the duration-window fallback runs. The
exact native SONARA matcher then verifies every shortlisted pair, and only exact scores at or
above the `0.45` review threshold form duplicate groups.

Every candidate in a fingerprint-mode report is `REVIEW MANUALLY`. The report carries no embedding
scoring evidence, and per-pair MERT, MAEST, and content similarities stay null. Fingerprint
evidence never authorizes deletion, so `--apply` on such a report finds no safe delete candidates.

`--source` or `--weight` in fingerprint mode fails before any database read, and the CLI exits
with code `2`. Fingerprint mode is the one report configuration without scoring sources. Its
report payload records `"search_mode": "fingerprint"` with `"sources": []` and `"weights": {}`,
while `fingerprint_retrieval` and the per-pair `candidate_sources` value `["fingerprint_lsh"]`
record the retrieval path.

## Spectral transcode check

In both search modes, the report step decodes every file that belongs to a duplicate group (only
those files, not the whole scope) and estimates its spectral cutoff. The read-only FFmpeg decode
covers three `24`-second windows centered at `15`%, `50`%, and `80`% of the track (short files
use a single window), first audio stream, mono, `f32` samples. Each window averages its loud
frames in linear power; the cutoff is the highest frequency still within `50` dB of the median of
the `1` to `8` kHz reference band. The window with the widest cutoff decides the file, so one
full-band window clears a copy while a true transcode stays walled in every window. The analysis
uses the stored `tracks.sample_rate_hz` value.

A lossless container whose widest window ends in a brickwall below `19.45` kHz, dropping at least
`14` dB across the cutoff, is marked `suspected_transcode`. That is fake-bitrate evidence, such
as an MP3-sourced rip stored as FLAC or WAV. A lossy container is instead measured against the
stored `tracks.bit_rate_bps` value and becomes suspect only when its wall sits below the cutoff
expected at that declared bitrate. The note then records a match or a shortfall. A gradual
roll-off is not a brickwall, so dark masters stay clean. Files that keep energy above `21` kHz
get a `full band` note; lower cutoffs are noted as a brickwall with an estimated bitrate class or
as a roll-off near the cutoff. Every verdict is evidence for review, never an automatic deletion
decision.

Keeper choice prefers copies that are not suspected transcodes ahead of every other ranking key:
format rank, size-per-second, metadata completeness, and modification time. So a full-band WAV
outranks a suspected-transcode FLAC. When even the chosen keeper is suspected, the
group gains the blocked reason `every remaining copy is a suspected transcode; verify spectra by
ear`.

Unreachable files, decode failures, and unknown sample rates are skipped with an explicit
per-file note, never guessed. When `ffmpeg` is not on `PATH`, the whole check is skipped with the
note `ffmpeg unavailable`. `--skip-spectral` disables the check.

## CLI report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Omitting `--db` selects `database\volumes.sqlite` under the repository root, the same default the
launcher suggests.

The CLI updates one console line while it runs. It loads track records and only
the embedding families the selected mode needs in SQLite chunks of 200 tracks, showing the
phase, percentage, and processed items as `N/M`. During pair scoring, `N/M`
refers to candidate pairs.

## Command examples

The two mode flags are mutually exclusive. `--source` and `--weight` require `--embedding` and
fail otherwise. Every run is report-only unless `--apply` is passed.

Default fingerprint report over one volume, with the default database:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes
```

The same run with the search mode spelled out:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --fingerprint --root M:/Volumes
```

Narrow the scope to one subfolder plus repeatable stored-path substrings:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes/Techno --path-contains vinyl --path-contains 2019
```

Select another database and another report directory:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db C:/db/library.sqlite --root D:/Music --out-dir C:/reports/audio-dedup
```

Write at most `50` duplicate groups:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes --limit-groups 50
```

Fast run without the FFmpeg spectral check:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes --skip-spectral
```

Embedding mode with the default four families and weights:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes
```

Embedding mode over an explicit family subset, where the weights must cover exactly the enabled
sources:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes `
  --source mert --source maest --weight mert=0.6 --weight maest=0.4
```

Embedding mode with the balanced preset and explicit threshold overrides:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes `
  --preset balanced --min-score 0.94 --min-similarity 0.96
```

Destructive apply run. It writes reports first and then prompts for the exact phrase
`APPLY DELETE`. Only safe delete candidates are deleted, and those exist only in embedding mode:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes --apply
```

Full flag reference:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --help
```

## Safe-delete corroboration

Safe deletion exists only in `--embedding` mode. MuQ and CLAP can affect ranking and report candidates, but they cannot replace MERT plus MAEST evidence for automatic deletion.

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

Reports default under `tools/audio-dedup/data/reports/` and include JSON, XLSX, and log output. The JSON payload records `search_mode`, `sources`, `weights`, and `fingerprint_retrieval` metrics: validated and rejected stored fingerprints, LSH/exact candidate counts, the review-pair count, and the threshold. Pair evidence records `fingerprint_similarity` and `candidate_sources`; the XLSX Pair Evidence sheet exposes the same provenance, while its Summary sheet lists the search mode, valid fingerprints, and fingerprint-review pairs. The text log carries a matching `search_mode=` line. Safety failures appear in `blocked_reasons`.

Spectral evidence has its own surfaces. Track rows carry `spectral_cutoff_hz`, `spectral_sharpness_db`, `suspected_transcode`, and `spectral_note`. Candidate rows repeat the cutoff, flag, and note, and the keeper and candidate explanations state when a spectrum looks transcoded. A top-level `spectral_analysis` block counts checked, analyzed, skipped, and suspected files. The XLSX Candidates sheet adds `suspected_transcode`, `spectral_note`, `keeper_suspected_transcode`, and `keeper_spectral_note` columns. The Summary sheet adds "Suspected transcodes in groups" and "Spectral checks" rows, and the text log carries a `suspected_transcodes=` line.

Reports are local private artifacts.
