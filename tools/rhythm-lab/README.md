# Rhythm Lab

Rhythm Lab is an auxiliary classifier labeling and training UI for
`dj-track-similarity`. It runs separately from the main app, opens a main
project SQLite database read-only for browsing and training inputs, and writes
only its own lab database and training artifacts. The exception is the explicit
liked-track toggle, which updates the main app's shared `track_likes` table.

Full documentation is in
[docs/dj-track-similarity/rhythm-lab.md](../../docs/dj-track-similarity/rhythm-lab.md).

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
has a source database path field, file picker, and Load database button. Choose
or create a classifier profile before loading tracks.

## Local Files

Lab state is stored at:

```text
tools/rhythm-lab/data/rhythm_lab.sqlite
```

Training artifacts stay under:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

Promoted runtime models for the main app are copied to:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Generated lab databases, training artifacts, and promoted runtime models are
local state and are ignored by git.
