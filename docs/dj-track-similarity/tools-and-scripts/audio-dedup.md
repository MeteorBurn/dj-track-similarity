# Audio Dedup

> Audience: Users looking for duplicate audio candidates.
> Goal: Run report mode safely and understand apply mode.
> Type: guide

Audio Dedup reads an existing SQLite library and writes JSON/XLSX/log reports by default. It uses stored analysis data and local paths. It does not scan unknown folders outside the selected root.

## Requirements

Audio Dedup needs stored audio-to-audio evidence. The duplicate scoring uses stored MERT, MAEST, and CLAP audio embeddings plus other safe checks in the tool core. Its `min_similarity` is not the CLAP text-search score scale.

## UI flow

Open Audio Dedup from the copy icon in the top bar.

Controls:

- **Root**: only DB tracks inside this stored path root are considered.
- **Path contains**: optional case-insensitive path filters, split by line, comma, or semicolon.
- **Preset**: safe, balanced, or aggressive.
- **Min score**: optional `0..1` override.
- **Min similarity**: optional `0..1` audio-to-audio content gate.
- **Limit groups**: optional maximum number of groups.
- **Output dir**: report directory.

Click **Start** for report mode. The UI shows progress and opens the XLSX report when complete.

## CLI report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Optional examples:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --path-contains wav --limit-groups 50
```

## Apply mode

Apply mode is destructive. It requires exact confirmation:

```text
APPLY DELETE
```

The tool deletes only safe duplicate candidates inside the selected root and removes SQLite rows only for tracks whose files were deleted.

Do not run apply mode during routine tests. Review the report first and keep backups when the library matters.

## Output

Reports default under `tools/audio-dedup/data/reports/` and include JSON, XLSX, and log output. They are local private artifacts.
