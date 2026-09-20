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

`--detect-fake-bitrate` adds a spectral check to the report step of both modes.
It is off by default because it decodes every file in every duplicate group.
With the flag it decodes each duplicate-group file with FFmpeg and
measures its spectral cutoff. A brickwall below ~19.5 kHz marks the copy as a
suspected transcode (fake bitrate): keeper choice then prefers full-band copies
over any format rank, and the verdict lands in the report columns. Thresholds
are calibrated against a 1000-file Fakin' The Funk reference (10 false alarms,
5 misses, all misses in the ~224-256 kbps class); a transcode buried under
dense vinyl crackle can still evade the check. Unreachable files are skipped.
Without the flag nothing is decoded: the report carries no spectral columns or
verdicts, and keeper choice falls back to the declared file facts.

The same detector also runs standalone over arbitrary files, directories, or a
`--list` of paths — no library database needed, file facts come from ffprobe —
and can write every verdict to `--csv`:

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\spectral_check_cli.py --list files.txt --csv verdicts.csv
```
