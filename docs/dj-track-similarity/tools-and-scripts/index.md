# Tools and scripts

The repository includes helper tools for classifier labeling, metadata enrichment, duplicate review,
audio repair, and database maintenance, plus a set of read-only diagnostic and benchmark scripts.
Use them deliberately. Most are report-only by default, and three have real apply modes.

## Tools

| Page | What it does | Can it write? |
| --- | --- | --- |
| [Rhythm Lab](./rhythm-lab.md) | Label, train, promote, and queue classifier review work | its own labels database, plus the liked-track toggle |
| [Audio Dedup](./audio-dedup.md) | Find duplicate audio candidates and delete confirmed copies | deletes audio files after confirmation |
| [Audio Doctor](./audio-doctor.md) | Inspect and repair known container and tag faults | rewrites audio files in apply mode |
| [Audio Online](./audio-online.md) | Collect online metadata into one XLSX workbook | no, it is read-only |
| [Optimize database](./optimize-database.md) | Back up, integrity-check, and vacuum SQLite | rewrites the database after backing it up |

## Scripts

[Scripts](./scripts.md) covers the nine read-only helpers:

- `qa_database.py` for library integrity QA.
- `benchmark_search.py` for synthetic vector-search timing.
- `text_prompt_benchmark.py` for prompt-form reliability, the committed evidence base every
  text-search claim in this project has to cite.
- `text_fusion_benchmark.py`, `text_tag_crosscheck.py`, and `prompt_preset_tune.py` for the rest of
  the text layer.
- `clap_checkpoint_embed.py` for evaluating a candidate CLAP checkpoint.
- `spectral_check_cli.py` and `benchmark_fingerprint_candidates.py` under `tools/audio-dedup/`.

Two further files in `scripts/` are not read-only and are documented elsewhere:
`optimize_database.py` has [its own page](./optimize-database.md), and `run_server_launcher.py` is
the launcher behind `run_server.cmd`.

## Which tool touches audio

Audio Doctor and Audio Dedup are the only two here that reach an audio file. Audio Doctor rewrites
one, Audio Dedup deletes one. Rhythm Lab, Audio Online, the database optimizer, and every script
leave source audio alone.
[Local-first safety](../concepts/local-first-safety.md) is the full list of write paths in the
project.

## Generated output

Tool output is local state. Each directory below keeps a tracked `.gitkeep` placeholder while its
contents are ignored by Git:

- `tools/audio-doctor/data/`
- `tools/audio-dedup/data/reports/`
- `tools/audio-online/data/` and `tools/audio-online/config.toml`
- `tools/rhythm-lab/database/`
- `tools/rhythm-lab/profiles/<profile-key>/`
- `models/classifiers/`

Review before sharing, because reports and model metadata can expose local paths and library
contents. The Audio Online configuration file holds API credentials.
