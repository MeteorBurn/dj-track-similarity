# Rhythm Lab

Rhythm Lab is an auxiliary classifier labeling and training UI for
`dj-track-similarity`. It runs separately from the main app, opens a main
project SQLite database read-only, and stores only lab labels, predictions, and
training checkpoints in its own writable SQLite file.

Rhythm Lab is profile-based. A classifier profile defines:

- a stable `classifier_key`
- a display name and description
- a profile type:
  - `binary`: exactly one positive training label, exactly one negative
    training label, and optional review-only labels that are stored but
    excluded from fitting
  - `multiclass`: two or more user-defined class labels; every label is a
    trainable class
- a profile-specific artifact folder and artifact filename prefix
- a train-refresh threshold for how many new labels per training class are
  required after the last training checkpoint before the UI enables training

Profiles can be binary or multiclass. A binary profile might use:

- `live_instrument`: positive class for tracks with live/acoustic instrument
  material
- `no_instrument`: negative/reference class
- `uncertain`: review-only label, excluded from fitting

Track labels are current-state annotations. If a track was labeled incorrectly
or your judgment changes, select another label or Clear in the UI; the old value
is replaced and only the current label is used by the next training run.
This applies to both binary and multiclass profiles: one track can have only one
current label for the active profile.

## Storage Layout

Lab state:

```text
tools/rhythm-lab/data/rhythm_lab.sqlite
```

Training artifacts for a profile:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

New profiles can use their own folder, for example:

```text
tools/rhythm-lab/artifacts/vocal-presence/
```

Promoted runtime model used by the main app:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

The lab database uses classifier-scoped tables:

```text
classifier_profiles
classifier_profile_labels
classifier_labels
classifier_predictions
classifier_training_checkpoints
```

Rows for different profiles are isolated by `classifier_key`, so labels,
predictions, and training checkpoints do not mix.

## Quick Start

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

No source database is loaded at startup unless `--source` is provided. The UI
has a source database path field, file picker, and Load database button. The
selected source DB is opened read-only. No classifier profile is selected at
startup; choose an existing profile or create one before loading tracks.

## Labeling UI

The UI includes:

- profile creation, editing, archiving, and switching
- profile type selection in the New classifier profile dialog
- multiclass label creation with custom keys, display names, and descriptions
- explicit profile selection on startup
- profile-scoped Library, Candidates, Training, and Profile Settings views
- text search by path/title/artist
- source database picker and load control
- syncopated rhythm filter
- dynamic manual label and predicted-label filters
- pagination
- audio preview from source paths
- MAEST genres and SONARA/MERT/MAEST feature availability from the source DB
- compact app-shell coverage badges for Tracks, SONARA, MAEST, and MERT
- compact label-count badges for the active profile
- training readiness and guidance cards
- per-profile train-refresh threshold editing in Profile Settings

Keyboard shortcuts on a focused row use the active profile's label order:

- `1`..`9` = profile labels in display order
- `0` = clear label

AIFF/AIF previews are transcoded to temporary WAV files for browser playback.
This is read-only for the source audio file and lets the browser load a
seekable codec with duration and scrubbing support.

## Training

After labeling enough examples:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Train a custom profile:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --profile vocal_presence --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

The training command benchmarks these feature sets:

- `sonara`
- `mert`
- `maest`
- `combined`

`combined` requires all three families: SONARA features from
`metadata_json.sonara_features`, MERT embeddings, and MAEST embeddings. Tracks
missing any of those inputs are skipped for the combined model.

The UI train-refresh button is controlled by the active profile's threshold for
new labels per training class. The default is 50. Changing that value in Profile
Settings immediately changes the readiness calculation and the "required new
labels" display for the active profile.

Artifacts and metrics are written to the active profile's artifact folder:

```text
tools/rhythm-lab/artifacts/live-instrumentation/
```

Artifact names use the profile artifact prefix, for example:

```text
live-instrumentation-combined-20260525T010203Z.joblib
live-instrumentation-combined-20260525T010203Z.metrics.json
```

Metrics use profile-neutral names such as `positive_discovery`,
`positive_precision`, `positive_recall`, `negative_candidates`, and
`label_order`. Profiles should not write classifier-specific legacy metric
fields.

Apply a trained model and export candidates:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\live-instrumentation\<model>.joblib --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py export-predictions --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

For custom profiles, pass `--profile <classifier_key>` when the artifact does
not already contain profile metadata or when exporting profile-scoped
predictions.

Promote the latest combined model for any profile into the main project:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

This copies the latest `<artifact-prefix>-combined-*.joblib` artifact to
`models/classifiers/<artifact-prefix>/model.joblib` and writes local metadata to
`models/classifiers/<artifact-prefix>/model.json`. The metadata is written from
the selected profile and artifact payload (`classifier_key`, profile name,
labels, feature set, and label counts). Those promoted files are local runtime
artifacts and are ignored by git.

## Useful Checks

Count labels for a profile:

```powershell
@'
from pathlib import Path
import sqlite3
path = Path(r"E:\Projects\dj-track-similarity\tools\rhythm-lab\data\rhythm_lab.sqlite")
conn = sqlite3.connect(path)
try:
    print(conn.execute("""
        SELECT label, COUNT(*)
        FROM classifier_labels
        WHERE classifier_key = 'live_instrumentation'
        GROUP BY label
        ORDER BY label
    """).fetchall())
finally:
    conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```
