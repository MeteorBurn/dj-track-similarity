# SONARA v0.2.4 project contract

> Audience: Users and maintainers who need the exact SONARA compatibility boundary.
> Goal: Define what the project requests, stores, trusts, and deliberately leaves out.
> Type: reference

The project pins SONARA `0.2.4` and accepts persisted SONARA data only when its analysis signature
matches the current contract. The presence flag by itself is insufficient. This protects search,
SET, transition diagnostics, and classifiers from silently mixing old and current feature semantics.

## Why v0.2.4 requires reanalysis

Upstream v0.2.4 made three changes that affect downstream consumers:

- `bpm_confidence` became an always-present `0..1` trust signal for the tempo estimate.
- `acousticness` and `danceability` were recalibrated as absolute scales. Old cutoffs need to be
  derived again.
- `vocalness` changed to a contrast-based v2 heuristic. `instrumentalness` follows it as the
  clamped inverse, and the upstream analysis schema changed to `3`.

The upstream release also separated `tags.year` from `tags.original_year`. This project does not
request SONARA's `tags` family: file tags continue to come from the scanner and Mutagen. A separate
SONARA `original_year` value is not part of the stored SONARA payload.

See the [upstream v0.2.4 release](https://github.com/kkollsga/sonara/releases/tag/v0.2.4),
[v0.2.4 changelog](https://github.com/kkollsga/sonara/blob/main/CHANGELOG.md#024---2026-07-17),
and [merged calibration change](https://github.com/kkollsga/sonara/pull/4).

## Current signature

The default full project profile currently produces this compatibility record:

```json
{
  "sonara_version": "0.2.4",
  "schema_version": 3,
  "mode": "playlist",
  "sample_rate": 22050,
  "bpm_range": [79, 192],
  "requested_features": [
    "acousticness",
    "bandwidth",
    "beatgrid",
    "beats",
    "bpm",
    "centroid",
    "chords",
    "chroma",
    "contrast",
    "danceability",
    "dissonance",
    "dynamic_range",
    "embedding",
    "energy",
    "fingerprint",
    "flatness",
    "instrumentalness",
    "key",
    "key_candidates",
    "loudness",
    "mfcc",
    "mood",
    "onset_density",
    "onsets",
    "rms",
    "rolloff",
    "silence",
    "structure",
    "tempo_curve",
    "time_signature",
    "valence",
    "vocalness",
    "zcr"
  ],
  "project_feature_revision": 1,
  "signature_id": "sha256:f9e4a97e3c530ae3cddf7146719908cd140c841415a397fb34b5034fdd574ead"
}
```

`requested_features` is sorted and unique before hashing. The digest covers all fields above except
itself. Any change in the SONARA version, schema, mode, sample rate, BPM range, feature profile, or
project feature revision creates a different contract.

`sonara_provenance` is separate from this signature. Provenance preserves the values reported by
SONARA, such as sample rate, hop length, mode, and requested features, plus the installed package
version when available. The signature decides compatibility; provenance explains how the result was
produced.

The minimal profile has the same contract fields but uses an empty expanded request:

```json
{
  "sonara_version": "0.2.4",
  "schema_version": 3,
  "mode": "playlist",
  "sample_rate": 22050,
  "bpm_range": [79, 192],
  "requested_features": [],
  "project_feature_revision": 1,
  "signature_id": "sha256:900fef5efe88c270f0bdd3789d87ea484115e8b02980fc7c792a2364e1e6ae01"
}
```

Both are valid current contracts. Library summary counts either one as current, while analysis
scheduling requires an exact match with the requested profile. `sonara-playlist-lab` remains an
informational model label and is not part of either compatibility check. Hop length stays in
provenance and is not a signature field.

## Profile rules

The browser, an omitted API `sonara_features` field, and plain `dj-sim analyze` use all eight project
families:

```text
structure, loudness, beatgrid, key_candidates,
vocalness, mood, instrumentalness, silence
```

The adapter adds the playlist-equivalent base requests plus tempo curve, time signature, SONARA
embedding, and fingerprint. This is necessary because upstream `features=[...]` replaces the mode
preset instead of extending it.

"Full" means every audio-analysis family supported by this project adapter, not every possible
upstream extension. The adapter deliberately does not request SONARA file-tag passthrough or a genre
model because Mutagen and MAEST remain the corresponding project sources.

Use `--sonara-minimal` or an explicit empty API list only for an intentional plain-playlist profile.
Individual CLI flags or a non-empty API list create a signed subset. Switching profiles makes the
other profile incomplete by design and queues it on the next analysis run.

Saving a profile replaces the track's previous SONARA feature object and either replaces or deletes
its lazy curves row instead of merging subset results with a previous full result.

## Storage and use matrix

| Data | Storage | Current use |
| --- | --- | --- |
| Playlist scalars and vectors | `tracks.metadata_json` under `sonara_features` | SONARA search, SET, transition diagnostics, and classifier variants as configured |
| `bpm_confidence`, `bpm_candidates`, `bpm_raw` | hot SONARA metadata | Tempo trust and low-confidence resolution; `bpm_raw` is also available to `sonara2` classifiers |
| `key_camelot`, `key_confidence`, key candidates | hot SONARA metadata | Camelot resolution and confidence attenuation; confidence is not a similarity dimension |
| Structure scalars, segments, and `energy_curve_summary` | hot SONARA metadata | Transition-risk v2 and SET structure compatibility; `sonara2` classifier input |
| `grid_stability` and grid offset | hot SONARA metadata | Tempo reliability, transition-risk v2, SET, and `sonara2` classifier input |
| `vocalness` | hot SONARA metadata | Explicit SONARA search modifier and optional `sonara2vocal` classifier input |
| `mood_*` and `instrumentalness` | hot SONARA metadata | Display and future workflows only; no current similarity, SET, Hybrid, or classifier input |
| True peak and ReplayGain | hot SONARA metadata | No direct similarity score; retained for loudness work and available to `sonara2` experiments |
| Momentary loudness maximum and loudness range | hot SONARA metadata | SONARA dynamics comparison and `sonara2` classifier input |
| Silence offsets | hot SONARA metadata | Stored for inspection and `sonara2` experiments; no direct similarity dimension |
| Beats and onsets | hot descriptor plus complete lazy `sonara_curves` copy | Short values can remain hot; long values use a summary there; the full lazy copy is display/future data only |
| Chords, tempo/energy/loudness curves, and downbeats | lazy `sonara_curves` row | Metadata display and future workflows; no hot search or classifier read |
| SONARA embedding and fingerprint | lazy `sonara_curves` row | Archived only; MERT and CLAP remain search embeddings, and Audio Dedup ignores these values |
| Provenance and analysis signature | hot track metadata | Audit trail, current-coverage queries, reanalysis scheduling, and classifier compatibility |

Storage does not imply scoring. The transition component named `mood_clash_risk`
uses the existing `valence`, `acousticness`, `energy`, and brightness fields. It does not read the
four archived `mood_*` affinities.

The supported SONARA v0.2.4 runner returns fixed MFCC, chroma, and contrast vectors as short Python
lists, so all components are kept in hot metadata. The generic serializer keeps only summary data
when a custom or injected runner supplies those values as NumPy arrays. Such a runner should convert
fixed vectors to lists before storage if it needs component-level compatibility.

## Confidence-aware tempo

For each track, the resolver starts from SONARA BPM and calculates:

```text
track_reliability = bpm_confidence
track_reliability = sqrt(bpm_confidence * grid_stability)  # when grid stability exists
pair_reliability = sqrt(track_reliability_a * track_reliability_b)
tempo_score = pair_reliability * measured_match
            + (1 - pair_reliability) * 0.5
```

The measured match includes half/double-tempo comparisons. At `bpm_confidence < 0.45`, ranked
`bpm_candidates` are retained as alternatives. A Mutagen tag BPM can become the working value when
it agrees with a SONARA primary or candidate tempo within the project's four-BPM tolerance after
octave-aware comparison. An unreliable pair also avoids a hard BPM-filter rejection after all
alternatives have been checked.

Confidence controls how strongly tempo evidence matters. Equal confidence values do not make two
tracks similar, and `bpm_confidence` never adds a bonus of its own.

## Camelot and key confidence

The project resolves one Camelot code in this order:

1. A valid Camelot file tag.
2. SONARA `key_camelot` from a current signed analysis.
3. Conversion of a conventional key name, such as `A minor`.

Compatibility is graduated:

| Relation | Score |
| --- | ---: |
| same | `1.00` |
| relative major/minor | `0.90` |
| adjacent Camelot number | `0.95` |
| clash | `0.20` |
| unknown | `0.55` |

`key_confidence` does not enter the feature distance. Instead, confidence below `0.45` pulls the
measured harmonic score toward neutral `0.55`. Transition-risk v1 retains its legacy key behavior
for reproducible evaluations. Current v2 uses the graduated contract.

SONARA key confidence is applied only when the resolved key came from SONARA. An authoritative file
tag does not inherit confidence from a different analyzed key.

## Structure and beat-grid transitions

Transition-risk v2 uses the geometric mean of the two `grid_stability` values as beat-grid
reliability. Structure risk can combine:

- the shared outgoing-outro and incoming-intro window, normalized over 16 seconds;
- the energy difference at the last and first stored segment boundaries;
- the `energy_level` difference;
- similarity between compact energy-curve summaries.

The full arrays stay out of the hot path. Missing optional structure or grid data remains missing;
it is not converted to zero.

SET transition confidence uses `50%` tempo, `30%` harmonic compatibility, and `20%` structure when
structure is available. Without structure, the blend is `60%` tempo and `40%` harmonic
compatibility. Hybrid transition-risk v2 exposes grid and structure as separate diagnostic
components.

## Classifier compatibility

Any feature set named `combined` or containing a source that starts with `sonara` is SONARA
dependent. Training requires all accepted rows to share one current analysis signature. Promoted
manifest version `2` records that signature, and scoring requires an exact artifact-to-track match.
The manifest path is `production.sonara_analysis_signature`.

Missing opt-in values are not imputed as `0.0`. The row is skipped because zero is a valid measurement,
especially for vocalness and loudness fields.

When the project feature revision changes:

- the main database deletes SONARA-dependent classifier scores on open;
- Rhythm Lab deletes SONARA-dependent predictions on its labels-database open;
- labels, likes, pair feedback, transition feedback, and embedding-only results remain;
- old model files remain recoverable but cannot score until retrained and promoted.

Follow [Migrate and reanalyze SONARA v0.2.4](../workflows/migrate-sonara-v0-2-4.md) for the ordered
upgrade procedure.
