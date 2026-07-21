# SONARA v0.2.9 project contract

> Audience: Maintainers validating stored SONARA results.
> Goal: Define the exact decode, signature, output, and storage boundaries.
> Type: reference

## Pinned analysis contract

| Setting | Value |
| --- | --- |
| SONARA package | `0.2.9` |
| Upstream result schema | `4` |
| Project feature revision | `3` |
| Mode | `playlist` |
| Sample rate | `22050 Hz` mono `float32`, arithmetic mean of all source channels |
| BPM range | `70..180` |
| Core vocalness model | bundled `sonara-vocalness-v2` |

The project FFmpeg decoder uses a normalized `pan` mix so each source channel contributes exactly
`1 / channel_count`; unlike FFmpeg's default equal-power stereo downmix, correlated material is not
raised by about 3 dB. It produces one decoded buffer per track. A SONARA-only job passes that
buffer directly to `sonara.analyze_signal`; Python orchestrates the job and persistence but does not
decode the file a second time.

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
  "project_feature_revision": 3,
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

Project feature revision `3` also invalidates revision `2` rows produced with FFmpeg's equal-power
mono matrix. Reanalysis replaces those rows without resetting the database or touching source audio.

## Scoring boundary

Current search, SET, Hybrid, and classifiers use signed Core features only. Timeline and SONARA
Representations are retained for future functions. MERT and CLAP remain the active similarity/search
embeddings.
