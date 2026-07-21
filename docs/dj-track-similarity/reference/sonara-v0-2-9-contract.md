# SONARA v0.2.9 project contract

> Audience: Maintainers validating stored SONARA results.
> Goal: Define the exact decode, signature, output, and storage boundaries.
> Type: reference

## Pinned analysis contract

| Setting | Value |
| --- | --- |
| SONARA package | `0.2.9` |
| Upstream result schema | `4` |
| Project feature revision | `4` |
| Mode | `playlist` |
| Decoder backend | `sonara-symphonia` |
| Execution path | `analyze_batch` |
| Requested sample rate | `22050 Hz` |
| BPM range | `70..180` |
| Core vocalness model | bundled `sonara-vocalness-v2` |

The SONARA job passes ordered path chunks directly to `sonara.analyze_batch()`. SONARA's Symphonia
path owns file decoding. The production job does not call the project's FFmpeg loader,
`DecodedAudio`, `analyze_signal`, or `analyze_file`, and it has no fallback to those paths. ML,
preview, and other non-SONARA functions retain their existing FFmpeg dependency.

## Independent outputs

- **Core** requests the complete lightweight feature profile and stores scalar or compact fixed-vector
  results in the main database. Contrast, MFCC, and Chroma retain all 7, 13, and 12 components.
- **Timeline** stores complete beats, onsets, chord sequence/events, tempo and energy curves,
  downbeats, structure segments, and loudness curve in `*.timeline.sqlite`.
- **Representations** stores the SONARA 48-dimensional embedding and fingerprint in
  `*.representations.sqlite`.

Selecting multiple outputs still performs one SONARA call. Persistence splits the returned object;
it does not duplicate the decode or Rust analysis.

## Signature

Every output signature hashes these fields:

```json
{
  "sonara_version": "0.2.9",
  "schema_version": 4,
  "mode": "playlist",
  "sample_rate": 22050,
  "bpm_range": [70, 180],
  "requested_features": ["output-specific", "sorted", "feature", "names"],
  "project_feature_revision": 4,
  "decoder_backend": "sonara-symphonia",
  "execution_path": "analyze_batch",
  "signature_id": "sha256:..."
}
```

Core keeps the signature in `tracks.metadata_json`. Timeline stores both signature JSON and digest
with its row. The SONARA embedding and fingerprint each store the Representations digest. Scheduling
requires all selected rows to match their expected digest.

## Storage and UI boundary

The three files share `storage.catalog_id`; mixing side databases from different catalogs is an
error. Normal track reads expose `timeline_fields` and `representation_fields` only. The metadata
dialog displays full Core values, then a presence marker and exact field names for Timeline and
Representations. It never loads their payload values.

## Compatibility policy

Schema v6 does not preserve old SONARA analysis results. Its v5 migration retains catalog metadata,
MAEST metadata, MAEST/MERT/MuQ/CLAP embeddings, likes, feedback, evaluation rows, and classifier
scores that do not depend on SONARA. It clears old SONARA features and curves and invalidates only
SONARA-dependent classifier scores. Schema v4 and older databases are rejected. Reanalyze SONARA
tracks with the current contract.

Project feature revision `4` invalidates every earlier project decode contract. Before the first
native job, any old Core, Timeline, or Representations signature is a blocker. The application never
adapts, mixes, or automatically deletes old results. Back up the catalog before the explicit SONARA
reset, then reanalyze. Reset also removes SONARA-dependent classifier scores while preserving
labels, feedback, and ML-only results.

## Scoring boundary

Current search, SET, Hybrid, and classifiers use signed Core features only. Timeline and SONARA
Representations are retained for future functions. MERT and CLAP remain the active similarity/search
embeddings.
