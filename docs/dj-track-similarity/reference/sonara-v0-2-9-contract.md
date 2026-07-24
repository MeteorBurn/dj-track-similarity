# SONARA v0.2.9 project contract

> Audience: Maintainers validating stored SONARA results.
> Goal: Define the exact decode, signature, output, and storage boundaries.
> Type: reference

## Pinned analysis contract

| Setting | Value |
| --- | --- |
| SONARA package | `0.2.9` |
| Upstream result schema | `4` |
| Project feature revision | `6` |
| Mode | `playlist` |
| Decoder backend | `sonara-symphonia` |
| Execution path | `analyze_batch` |
| Requested sample rate | `22050 Hz` |
| Analysis hop | `512` samples |
| BPM range | `70..180` |
| Core vocalness model | bundled `sonara-vocalness-v2` selector |

The SONARA job passes ordered path chunks directly to `sonara.analyze_batch()`. SONARA's Symphonia
path owns file decoding. The production job does not call the project's FFmpeg loader,
`DecodedAudio`, `analyze_signal`, or `analyze_file`, and it has no fallback to those paths. ML,
preview, and other non-SONARA functions retain their FFmpeg dependency.

## Four independent outputs

| Output kind | Contents | Storage |
| --- | --- | --- |
| `core` | scalar and compact fixed-vector features, including full Contrast, MFCC, and Chroma vectors | Core `sonara` |
| `timeline` | complete beats, onsets, chord sequence/events, tempo, energy, and loudness curves, downbeats, and structure segments | Artifacts `sonara_timeline` |
| `embedding` | 48-dimensional float32 little-endian vector, version `2`, no normalization | Artifacts `sonara_similarity_embeddings` |
| `fingerprint` | version `1` uint32 little-endian fingerprint | Artifacts `sonara_fingerprints` |

`core` is always included. Selecting several output kinds performs one SONARA call; persistence
splits the returned object into contract-owned tables without repeating decode or Rust analysis.

The Full-only `time_signature` metrogram is excluded from `core`. It is not a production ranking or
classifier input, and Beatgrid uses SONARA's normal 4/4 fallback rather than an untrusted meter
estimate.

## Contract and release identity

All four `ContractIdentity` values are derived from the loaded package. Callers cannot supply a
release hash. Common parameters include:

- package version and build identity;
- schema, mode, sample rate, hop size, and BPM bounds;
- project feature revision `6`;
- decoder and execution path;
- unit-interval clamp policy and affected fields;
- selected vocalness model identity;
- the sorted, output-specific requested feature set.

Embedding and fingerprint contracts also include their encoding and version details. Canonical
contract JSON is hashed into a `contract_hash`; the complete runtime identity produces one
`release_hash` shared by all four output contracts. Analyzer provenance is validated during
ingestion, but the runtime does not promise to preserve the raw provenance payload for round-trip
display.

## Storage boundary

A fresh catalog is schema-v7 Core plus mandatory Artifacts, bound by one `catalog_uuid`. Evaluation
is an optional third database created only by evaluation workflows. Missing, mismatched, or
cross-catalog sidecars fail closed.

Normal track reads expose v7 analysis coverage and compact summaries. The explicit timeline route
loads only the current signed `timeline` row. The React frontend has not yet been ported to these v7
responses, so this contract does not claim that the current browser UI can display them.

## Release preparation

Run this before analysis under a new or unprepared SONARA runtime:

```powershell
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backup --confirm "PREPARE SONARA RELEASE"
```

The command derives exactly `core`, `timeline`, `embedding`, and `fingerprint`; verifies a Core plus
Artifacts backup pair; and advances an ordered, receipt-backed activation. An interrupted operation
can resume, while mismatched receipt, backup, catalog, or runtime identity is rejected. Prior SONARA
rows and SONARA-dependent classifier scores are removed before the new contracts become active.

This is not schema migration. The runtime accepts only clean v7 bundles, and the removed
`migrate-v7` and `migrate-schema-v7` commands are unavailable.

## Scoring boundary

Current search, SET, Hybrid, and classifiers use signed `core` features. The `timeline`, SONARA
embedding, and fingerprint remain stored evidence for narrower or future workflows. MERT and CLAP
remain active similarity/search embeddings. Every result is a ranking or diagnostic signal, not an
automatic DJ decision.
