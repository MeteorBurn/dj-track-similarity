# Tools and scripts

> Audience: Users running helper workflows outside the main search panel.
> Goal: Explain what each helper writes and when to use it.
> Type: guide index

The repository includes helper tools for classifier labeling, reports, maintenance, and faster repeated lookup. Use them deliberately. Some are report-only by default, and some have real apply modes.

## Pages

- [Rhythm Lab](./rhythm-lab.md): label, train, promote, and queue classifier review work.
- [Audio Dedup](./audio-dedup.md): find likely duplicate audio candidates and optionally delete safe candidates after confirmation.
- [Audio Doctor](./audio-doctor.md): inspect and repair known safe audio container/tag issues after dry-run state exists.
- [Persistent ANN indexes](./persistent-ann-indexes.md): build optional vector sidecars for faster repeated lookup.
- [Optimize database](./optimize-database.md): backup, integrity-check, vacuum, analyze, and checkpoint SQLite.

## Generated output

Tool output directories are local state and are ignored by Git by default:

- `tools/audio-doctor/data/`
- `tools/audio-dedup/data/reports/`
- `tools/rhythm-lab/data/`
- `tools/rhythm-lab/artifacts/`
- `models/classifiers/`
- `.dj-track-similarity-indexes/`

Review before sharing because reports and model metadata can expose local paths and library contents.
