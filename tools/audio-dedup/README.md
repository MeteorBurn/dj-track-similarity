# Audio Dedup Tool

Local duplicate-audio report and cleanup helper for `dj-track-similarity`.

```powershell
.\.venv\Scripts\python.exe tools\audio-dedup\audio_dedup_cli.py --help
```

The default mode is report-only and writes JSON, XLSX, and log files under
`tools\audio-dedup\data\reports`. Apply mode remains explicit and destructive:
it requires `--apply` plus the `APPLY DELETE` confirmation prompt.
