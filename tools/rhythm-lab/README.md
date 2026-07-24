# Rhythm Lab

Rhythm Lab is an auxiliary classifier labeling and training UI for
`dj-track-similarity`. It runs separately from the main app, opens a main
project SQLite database read-only for browsing and training inputs, and writes
only its own lab database and training artifacts. The exception is the explicit
liked-track toggle, which updates the main app's shared `likes` table.

Full documentation is in
[docs/dj-track-similarity/tools-and-scripts/rhythm-lab.md](../../docs/dj-track-similarity/tools-and-scripts/rhythm-lab.md).

## Quick Start

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

No source database is loaded at startup unless `--source` is provided. A new
labels database also starts without a built-in classifier profile. The UI has a
source database path field, file picker, Load database button, and profile
creation dialog. Choose or create a classifier profile before loading tracks.

The profile `Delete` action is permanent and asks you to type the profile name
or key. It removes Rhythm Lab labels, predictions, training queue rows,
checkpoints, metrics, and local training artifacts for that profile. Promoted
runtime models under `models/classifiers/` are left in place.

## Local Files

Lab state is stored at:

```text
tools/rhythm-lab/data/rhythm_lab.sqlite
```

Training artifacts stay under:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

Promoted runtime models for the main app use an immutable generation selected
by one small pointer:

```text
models/classifiers/<artifact-prefix>/current.json
models/classifiers/<artifact-prefix>/generations/<generation-id>/model.joblib
models/classifiers/<artifact-prefix>/generations/<generation-id>/model.json
```

Rhythm Lab writes and verifies both generation files before atomically
switching `current.json`. The main app checks the pointer, manifest, and exact
model SHA-256 before loading the artifact.

Generated lab databases, training artifacts, and promoted runtime models are
local state and are ignored by git.

## Recover labels from a preserved legacy database

The transfer tool accepts sealed bundle format version `3`. Keep the original
byte-for-byte legacy Lab database backup together with its matching `-wal` and
`-shm` files. That SQLite set remains the source recovery artifact; generated
JSON bundles and reports are derived working files, not replacements for it.

Run the workflow from `tools/rhythm-lab/`. Export reads one fixed read-only
SQLite snapshot, including committed WAL frames. It preserves SQL `NULL` values
and keeps labels with duplicate paths as separate records:

```powershell
python -m rhythm_lab.label_transfer export --lab-db <legacy-lab.sqlite> --output <export.json>
python -m rhythm_lab.label_transfer preview --bundle <export.json> --core-db <current-v7-core.sqlite> --output <preview.json>
python -m rhythm_lab.label_transfer rebound --bundle <export.json> --preview <preview.json> --output <rebound.json>
```

Restore is a preview by default:

```powershell
python -m rhythm_lab.label_transfer restore --bundle <rebound.json> --core-db <current-v7-core.sqlite> --lab-db <target-lab.sqlite> --report <report.json> [--accept-record-id sha256:...] [--apply] [--force]
```

Do not type the square brackets; they mark optional flags. Without `--apply`,
the command writes only the report and does not create or change the target Lab
database. Strong matches are eligible automatically. A reviewed weak match is
eligible only when its stable record ID is passed with `--accept-record-id`;
repeat the option for multiple records.

On every run, restore reopens the current v7 Core database read-only and checks
the exact catalog, track UUID, content generation, selected path, file size, and
mtime before binding. Changed bindings, unaccepted weak matches, unmatched or
ambiguous rows, and deterministic conflict losers remain losslessly available
in `classifier_label_recovery` after apply. For conflicts, the newest
`updated_at` wins; equal timestamps use the lexicographically smallest
`record_id`.

Before apply changes an existing target, it copies the target Lab database and
any existing `-wal` and `-shm` companions into a timestamped backup directory.
Applying the same rebound bundle again is data-idempotent: label and recovery
rows are upserted rather than duplicated. `--force` only permits replacing an
existing JSON report; it does not bypass matching, conflict, or Core
revalidation rules. The workflow never writes the v7 Core database, audio
files, or promoted model files.
