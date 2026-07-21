# Troubleshooting by symptom

> Audience: Users fixing local setup, scan, analysis, and search problems.
> Goal: Give practical checks tied to current behavior.
> Type: help

## Server says FFmpeg is missing

The backend requires FFmpeg at startup. Install FFmpeg and add it to `PATH`, or set:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\Path\To\ffmpeg.exe"
```

Then restart `dj-sim serve`.

## The UI says to choose a database

The API has no selected SQLite database. Choose a `.sqlite` file in the UI or start the server with `--db`:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db .\data\library.sqlite
```

## Scan finds no files

Check that the selected folder exists and contains supported extensions:

```text
.aif .aiff .alac .flac .m4a .mp3 .ogg .opus .wav .wave
```

Files whose names start with `._` are skipped.

## Analysis job has zero tracks

The selected families may already be complete for all tracks, or the database may not be the one you scanned. Reset only if you intentionally want to recompute.

For classifiers, inspect the promoted manifest and the ready/not-ready counts. Run the missing SONARA
or ML stage first, then rerun the separate CLASSIFIERS job.

## SONARA is blocked after an update

The native decode migration intentionally blocks when any stored output has an older decoder or
execution contract. Back up the main and side databases together, then use the explicit SONARA
reset. Old and new SONARA results are never adapted or mixed.

Verify the installed package:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

Each Core, Timeline, and Representations output has its own signature. After reset, missing current
optional output rows do not invalidate Core and can resume normally. Follow
[Reanalyze with split SONARA storage](../workflows/reanalyze-sonara-split-storage.md).

## SONARA looks present but search or SET treats it as missing

The fast `has_sonara_analysis` flag can remain set on a legacy row. Search, SET, public analysis
lists, and the library summary require a valid current contract. Reanalyze the track and inspect its
provenance and signature in the metadata dialog.

## Timeline returns an empty object

`GET /api/tracks/{track_id}/sonara-timeline` returns `{}` when the Timeline checkbox was not analyzed
or its signature is stale. Because the metadata dialog shows only the field-name manifest, it does
not call this endpoint. Select Timeline and run SONARA again.

## A classifier reports an incompatible SONARA signature

The promoted artifact can be stale or trained with another profile. It may also request an opt-in
value that is missing from the track. The recovery order is fixed:

```text
reanalyze SONARA -> retrain -> promote -> rescore
```

Missing values are not converted to `0.0`. Labels and feedback remain available for retraining, and
embedding-only artifacts are unaffected.

## CUDA was requested but analysis fails

Use `dj-sim doctor` to inspect the PyTorch/CUDA runtime:

```powershell
dj-sim doctor
```

Try `--device cpu` or UI `CPU` to confirm the rest of the job works.

## CLAP text search is disabled or empty

Run CLAP analysis first:

```powershell
dj-sim analyze --models clap --db .\data\library.sqlite
```

If results are empty, lower the CLAP similarity threshold and rewrite the prompt around audible traits rather than metadata or artist names.

## SET eligible count is low

SET needs feature-complete tracks: SONARA, MERT, MAEST, and CLAP. Run missing families and check the SET coverage counts.

## Genre tag job has failures

Genre tag apply writes real audio tags. Failures are per track and the batch continues. Check the job log and file permissions. WAV writes use Mutagen WAVE/ID3 handling and should fail clearly rather than attempting custom RIFF repair in the app path.

## `/docs/` says documentation is not built

Build the docs site:

```powershell
cd docs\dj-track-similarity
npm run check
```

Then reload `/docs/`.
