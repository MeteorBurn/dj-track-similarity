# Audio Dedup Tool

Local duplicate-audio report and cleanup helper for `dj-track-similarity`.

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\audio_dedup_cli.py --help
```

Runs are report-only by default and write JSON, XLSX, and log files under
`tools\audio-dedup\data\reports`. Apply mode remains explicit and destructive:
it requires `--apply` plus the `APPLY DELETE` confirmation prompt.

Two search modes exist:

- `--fingerprint` (primary, also the default): search exclusively over stored
  SONARA fingerprints. No embeddings are loaded, candidates come from
  fingerprint LSH only, every candidate is verified with the exact native
  matcher, and only that exact score forms groups. Every reported candidate
  stays manual-review.
- `--embedding` (secondary): duplicates are scored from the enabled embedding
  families (`--source`/`--weight`) with the preset gates; exact fingerprint
  checks of embedding-shortlisted pairs still add manual-review pairs. This is
  the only mode that can produce safe delete candidates for `--apply`.
