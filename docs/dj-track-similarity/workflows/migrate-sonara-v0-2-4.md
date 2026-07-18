# Migrate and reanalyze SONARA v0.2.4

> Audience: Users upgrading an existing analyzed library to the current SONARA contract.
> Goal: Reanalyze safely, preserve review data, and rebuild only dependent classifiers.
> Type: workflow

Use this workflow for a database that contains SONARA output from an older package, schema, BPM
range, requested-feature profile, or project feature revision. The current signature detects those
rows automatically. You do not need to delete the database or reset SONARA before reanalysis.

## What changes and what stays

Reanalysis replaces SONARA-derived track fields, provenance, signature, and out-of-band curves. It
also invalidates dependent classifier scores for each rewritten track.

The migration preserves:

- audio files and file tags;
- track rows, likes, and non-SONARA embeddings;
- Rhythm Lab profiles, labels, queues, collections, and feedback;
- pair and transition feedback;
- embedding-only classifier scores and predictions.

Old SONARA-dependent model files remain on disk for recovery, but signature checks block them from
scoring current tracks.

## 1. Back up local state

Stop writers before copying a live database. Back up the main library and, if you use Rhythm Lab,
its labels database:

```powershell
Copy-Item .\data\library.sqlite .\data\library.before-sonara-0.2.4.sqlite
Copy-Item tools\rhythm-lab\data\rhythm_lab.sqlite tools\rhythm-lab\data\rhythm_lab.before-sonara-0.2.4.sqlite
```

If either database uses WAL and is open, use a SQLite-aware backup instead of copying only the main
file. The repository's database optimization tool creates a checked backup before maintenance.

## 2. Install and verify the pinned version

Update the environment from the current project metadata:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
python -c "import sonara; print(sonara.__version__)"
```

The version check must print `0.2.4`. Windows x64 uses the pinned wheel named in `pyproject.toml`;
other platforms install the same version from PyPI.

## 3. Choose one analysis profile

For the normal archival migration, use the default full profile. It captures structure, loudness,
beat grid, key candidates, vocalness, mood, instrumentalness, silence, and complete archival
sequences.

Do not add `--sonara-minimal` to the command below unless a plain-playlist database is intentional.
Minimal, subset, and full results have different signatures. Alternating between them causes the
other profile to be queued again.

## 4. Reanalyze SONARA

An optional pilot confirms decoding and storage before the full run:

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Then omit `--limit` to finish the library:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

The job queues unsigned, legacy, and mismatched rows even if
`has_sonara_analysis = 1`. Tracks that already have the exact requested signature are skipped.
MAEST, MERT, MuQ, and CLAP do not need reanalysis for this migration.

Do not reset SONARA first. A reset is useful only when you intentionally want to purge stored
SONARA data before a fresh run; it also removes all SONARA curves and dependent main-library
classifier scores.

## 5. Verify current coverage

The library summary counts only current signed SONARA rows. During migration, its SONARA count can
temporarily be lower than the raw presence-flag count. In the UI, compare SONARA coverage with the
track count and review job failures.

With the server running, the same check is available through the API:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/library/summary
```

Inspect several tracks from different formats and durations in the metadata dialog. Confirm:

- package version `0.2.4`, schema `3`, playlist mode, and sample rate `22050`;
- BPM range `79..192` and the expected requested-feature list;
- a `signature_id`, `bpm_confidence`, tempo candidates, and Camelot key;
- mood, instrumentalness, loudness, structure, beat-grid, and silence fields;
- lazy summaries for stored beats, onsets, chords, curves, downbeats, embedding, and fingerprint.

The lazy curves endpoint returns `{}` for a stale or unsigned SONARA row even when an old
`sonara_curves` record still exists. This prevents stale arrays from appearing current.

## 6. Rebuild SONARA-dependent classifiers

Do this after SONARA coverage is complete. Reusing an old artifact is blocked because v0.2.4
changed acousticness, danceability, vocalness, and instrumentalness semantics.

Affected feature sets include `sonara`, `sonara2`, `sonara2vocal`, `combined`, and any `+` feature
set containing a SONARA source. MERT-, MAEST-, or CLAP-only artifacts are unaffected.

For each affected profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set combined --labels tools\rhythm-lab\data\rhythm_lab.sqlite
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

Use the feature set that won your current benchmark instead of `combined` when appropriate. A new
benchmark is recommended because the input scales changed:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --output tools\rhythm-lab\artifacts\ablation-sonara-0.2.4.json
```

Opening the main database applies the project-revision guard to stored classifier scores. Opening
the Rhythm Lab labels database applies the same guard to predictions. Neither operation deletes
labels or feedback.

## 7. Validate behavior by listening

Run small, repeatable checks before trusting whole-library rankings:

1. Compare steady dance tracks with ambient or rubato tracks and inspect BPM confidence.
2. Check a low-confidence case where tag BPM or a ranked candidate corroborates the tempo.
3. Review same, relative, adjacent, and clashing Camelot transitions.
4. Compare structure-rich SET transitions with transition-risk v2 enabled.
5. Recheck classifier thresholds and top candidates instead of reusing pre-v0.2.4 cutoffs.

The expected tempo score moves unreliable evidence toward neutral `0.5`; low confidence should not
create a similarity bonus. Key confidence also weakens harmonic evidence toward neutral rather
than acting as a distance feature.

## Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| Old rows are analyzed again | Their signature differs from the requested profile | Let the job finish; a reset is not required |
| The next run queues most tracks again | The requested profile changed, often full versus minimal | Pick one intended profile and rerun consistently |
| SONARA coverage drops after the update | Summary counts only current signed rows | Reanalyze and inspect failed job entries |
| Classifier scoring reports an incompatible manifest or signature | The promoted artifact predates the current contract or used another profile | Retrain, promote, and then rescore |
| Some training rows are skipped | Rows do not share one current signature, or a requested opt-in value is absent | Complete one consistent SONARA profile; do not zero-impute |
| Curves endpoint returns `{}` | No out-of-band row exists, or the track's SONARA signature is not current | Reanalyze that track with the intended profile |

For exact fields and formulas, see the
[SONARA v0.2.4 project contract](../reference/sonara-v0-2-4-contract.md).
