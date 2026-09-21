# Audio Dedup Tool

Local duplicate-audio report and cleanup helper for `dj-track-similarity`.

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\audio_dedup_cli.py --help
```

Duplicates are found from stored SONARA fingerprints and nothing else. The CLI
is report-only: it writes JSON, XLSX, and log files under
`tools\audio-dedup\data\reports` and never touches audio. Copies are deleted
only in the browser, where a reviewer selects them and types `APPLY DELETE`.

Two search modes exist, both over the same stored fingerprints:

- `--fingerprint-scan` (primary, also the default): the upstream SONARA
  duplicate recipe. Each track is matched against the representatives seen so
  far and joins the first one scoring above 0.30, with candidates bucketed by
  rounded duration. A copy with a noticeably different duration is out of
  reach, and this is the slowest of the two.
- `--fingerprint-lsh`: the same exact native matcher, but candidates come from
  version-separated fingerprint LSH instead of duration buckets, so copies with
  different trims and padding pair up too. An exact match needs 0.45 to form a
  group.

`--detect-fake-bitrate` adds a spectral check to the report step.
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
`--list` of paths — no library database needed, file facts are read from the
files themselves —
and can write every verdict to `--csv`:

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\spectral_check_cli.py --list files.txt --csv verdicts.csv
```
