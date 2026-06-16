# Rhythm Lab

Rhythm Lab is an auxiliary classifier labeling and training UI for
`dj-track-similarity`. It runs separately from the main app, opens a main
project SQLite database read-only for track browsing, analysis metadata,
training inputs, and audio preview. The only source-database write path is the
explicit liked-track toggle, which updates the shared `track_likes` table used
by the main app. Lab labels, predictions, and training checkpoints stay in
Rhythm Lab's own writable SQLite file.

Use Rhythm Lab when generic similarity or genre labels are not enough and you
want a personal reusable classifier, for example "has live instrumentation",
"vocal presence", "peak-time tool", or any other library-specific concept you
can label consistently.

Rhythm Lab is profile-based. A classifier profile defines:

- a stable `classifier_key`
- a unique display name and description
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

A good workflow is: create one focused profile, label clear examples first,
train a few benchmark models, inspect predictions, add more labels for mistakes
or uncertain areas, then promote the best combined model for use in the main
app.

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

Profile display names are unique case-insensitively inside one lab database.
For example, `Electronic Mood` and `electronic mood` cannot exist together.
If an older lab database already contains duplicate profile names, Rhythm Lab
will refuse to open it until the duplicate names are resolved.

## Quick Start

From the main `dj-track-similarity` UI, use the Rhythm Lab flask button in the
top toolbar. It starts the Rhythm Lab server on port `8777`, passes the current
selected SQLite database as the read-only source database when one is selected,
and opens:

```text
http://127.0.0.1:8777/
```

If Rhythm Lab is already listening on that port, the button reuses the running
server and opens the same URL.

Use the adjacent Rhythm Lab power button in the same toolbar to stop the
managed hidden Rhythm Lab server. The stop button terminates the process that
was started by the main app through its stored PID. If port `8777` is occupied
by a manually started or otherwise unmanaged server, the main app reports that
state instead of killing an unrelated process.

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
selected source DB is opened read-only except for explicit liked-track
changes. No classifier profile is selected at startup; choose an existing
profile or create one before loading tracks.

Use the UI for labeling, review, train-refresh, and promoting a trained combined
model. Use the CLI for repeatable batch training, prediction export, promotion,
and permanent profile deletion.

## Labeling UI

The UI includes:

- profile creation, editing, archiving, and switching
- profile type selection in the New classifier profile dialog
- multiclass label creation with custom keys, display names, and descriptions
- explicit profile selection on startup
- profile-scoped Library, Candidates, Liked, Training, and Profile Settings
  views
- text search by path/title/artist
- source database picker and load control
- syncopated rhythm filter
- liked-track buttons that update the main app's shared `track_likes` table
- a Liked tab for the shared liked-track list
- dynamic manual label and predicted-label filters
- Candidate filters for predicted label, probability focus, and minimum
  probability; text search remains in the shared path/title/artist field
- server-side pagination and filtering for both Library and Candidates
- pagination
- audio preview from source paths
- MAEST genres and SONARA/MERT/MAEST feature availability from the source DB
- compact app-shell coverage badges for Tracks, SONARA, MAEST, MERT, and
  Liked tracks
- compact label-count badges for the active profile
- training readiness and guidance cards
- per-profile train-refresh threshold editing in Profile Settings

Archiving a profile hides it from the normal active profile list but keeps its
labels, predictions, and training checkpoints in the lab database.
Permanent deletion is intentionally exposed through the CLI instead of the UI.

Keyboard shortcuts on a focused row use the active profile's label order:

- `1`..`9` = profile labels in display order
- `0` = clear label

AIFF/AIF previews are transcoded to temporary WAV files for browser playback.
This is read-only for the source audio file and lets the browser load a
seekable codec with duration and scrubbing support.

Label only the current profile's concept. Mixing several concepts into one
profile makes the model harder to interpret and usually produces less useful
CLASS filters in the main app.

## Training

Training and prediction use scikit-learn. Install the optional Rhythm Lab
dependency group in the project environment before running training commands:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[rhythm-lab]"
```

For a single environment that also runs the main app analysis passes, install
`.[sonara,ml,rhythm-lab,dev]`.

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

The Training tab keeps the readiness cards inside the existing training panel
and adds one `Training Stats` card at the bottom with the latest training run, artifact
counts, latest artifact details per feature set, current combined-model metrics,
and a short combined-model metrics history. Dates are displayed in a
human-readable local browser format.

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

The Rhythm Lab toolbar also exposes a promote button next to the train-refresh
button. It is enabled only after the active profile has an existing trained
combined model artifact. The button uses the same promotion path as the CLI.

Promotion copies the latest `<artifact-prefix>-combined-*.joblib` artifact to
`models/classifiers/<artifact-prefix>/model.joblib` and writes local metadata to
`models/classifiers/<artifact-prefix>/model.json`. The metadata is written from
the selected profile and artifact payload (`classifier_key`, profile name,
labels, feature set, and label counts). Those promoted files are local runtime
artifacts and are ignored by git.

## Profile Deletion

Delete is a destructive operation. It permanently removes the profile row and
all profile-scoped lab data from `rhythm_lab.sqlite`: profile labels, manual
track labels, saved predictions, and training checkpoints. It does not
delete source audio files, source database rows, or training/model artifact
files on disk.

Delete by unique profile name:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "Electronic Mood" --confirm "Electronic Mood"
```

Delete by `classifier_key`:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile electronic_mood --confirm electronic_mood
```

The `--confirm` value must exactly match the selected `--name` or `--profile`
value. This prevents accidental deletion when shell history or copy/paste is
used.

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

## Main App Integration

Promoted classifiers are local classifier profiles, not audio-analysis models
that decode files themselves. They score tracks from already stored analysis
outputs:

- SONARA playlist features from `metadata_json.sonara_features`;
- MERT embeddings from `embeddings.embedding_key = "mert"`;
- MAEST embeddings from `embeddings.embedding_key = "maest"`.

Tracks missing any of those inputs are skipped by the classifier job. Scores
are stored in `track_classifier_scores` under the profile classifier key.

Stable model locations use the profile artifact prefix:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

The promoted files are local runtime artifacts and are ignored by git. The main
app can score a promoted profile with:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

The user-facing score is the classifier probability for the profile's positive
training label. Because UI displays can round probabilities, a value shown as
`1.0000` may be slightly below mathematical `1.0`. Use thresholds such as
`0.99`, `0.95`, or `0.90` for practical filtering instead of relying on exact
`1.0`.
