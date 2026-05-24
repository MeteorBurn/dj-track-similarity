# dj-track-similarity

A personal experiment in building a local music-library tool for finding tracks
that feel close enough to work together in DJ sets.

This repository started as something useful for my own workflow. I collect
music, tag it in my own way, and spend a lot of time thinking about which
tracks can sit next to each other in a set. I am not a professional researcher
or audio engineer; this is an enthusiast project where I am trying ideas,
testing models on a real library, and slowly turning the useful parts into a
tool.

The repository is public because the problem is interesting, and maybe someone
else who collects, tags, or plays music will find the approach useful too.

![dj-track-similarity web UI](https://i.ibb.co/FkKt31n3/Q3n-Az-F6u7-T.png)

## What It Does

- Scans a local music folder and stores track metadata in SQLite.
- Reads a fixed, human-sized set of file tags through Mutagen and shows those
  tags separately from model-derived values.
- Refreshes Mutagen tags for already indexed tracks without rescanning paths or
  deleting analysis results.
- Can relocate stored track paths after moving the same music folder to another
  drive, without repeating completed analysis.
- Extracts a focused Sonara playlist feature set, including analyzed BPM,
  raw Sonara key data, rhythm/loudness values, perceptual scores, tonal
  descriptors, and compact spectral summaries, then stores those summaries in SQLite.
- Uses a native-first audio loader with standard decoders: torchaudio when
  available, Python's WAV reader for WAV files, and ffmpeg fallback.
- Keeps analyzed Sonara key data in its original form for display and storage.
- Builds audio embeddings with MERT for audio-to-audio similarity search.
- Builds CLAP audio embeddings for text-to-audio search.
- Extracts top genre labels with MAEST using a three-window consensus and
  stores the final top 3 labels in the local SQLite database.
- Can explicitly save stored MAEST labels into standard audio genre tags for
  players such as AIMP.
- Shows compact per-track analysis status (`sonara`, `maest`, `mert`, `clap`)
  and header counters for how many tracks have each analysis family.
- Loads the library view in server-side pages so large local databases stay
  usable without sending every track and every metadata blob to the browser.
- Shows a metadata popup with source-separated Mutagen file metadata, grouped
  Sonara playlist features, and MAEST genre confidence scores.
- Lets you choose seed tracks, search for similar tracks with SONARA mixer
  controls or embedding/text models, preview results, and assemble a small set
  for export.
- Streams AIFF/AIF previews as browser-playable WAV audio through ffmpeg while
  leaving the original audio files untouched.
- Exports the current set as M3U or CSV without storing playlists in SQLite.
- Can reset one analysis family at a time, or clear the local SQLite database
  after confirmation. These actions do not delete audio files.

The current focus is simple and practical: check whether modern audio embedding
models can help find tracks that sound related, without relying on BPM, key, or
manually curated genre tags as the main signal.

## Current Status

The project is usable, but still experimental.

SONARA seed search is now the primary explainable search path in the UI. The
current UI uses a custom mixer instead of preset mode buttons. The mixer exposes
weights for timbre, rhythm, dynamics, harmonic color, and tempo compatibility;
optional modifiers can bias the result toward higher or lower energy, valence,
acousticness, brightness, rhythm density, dynamic range, or loudness. It still
deliberately uses raw SONARA tonal fields and does not derive Camelot notation.

MERT is still available as a separate seed-search tab. It already gives
promising results on my own library: aggressive broken tracks tend to pull
similar aggressive material, and deeper kick-focused tracks tend to find
related tracks. CLAP remains separate for text-to-audio search.

The UI keeps the search controls separated by model:

- `Mixer` appears for SONARA and weights timbre, rhythm, dynamics, harmonic,
  and tempo similarity.
- `Modifiers` appear for SONARA and bias the custom ranking relative to the
  current seed/lookback context.
- `Similarity` sets a minimum score.
- `Lookback` adds the last N tracks from the current set into the search
  context.
- `Limit` caps the number of returned results.
- `Text query` appears only on the CLAP tab.

The older SONARA preset modes still exist in the backend for compatibility, but
the active UI path sends the custom mixer and modifiers to `/api/search/sonara`.
Other controls such as randomization are either disabled in the UI or treated as
future work until they are calibrated properly. I do not want uncalibrated knobs
to make the model look better or worse than it really is.

Large libraries are handled as a paged server-side list. The browser requests
the current library page from `/api/tracks` with optional query, preset, limit,
and offset parameters. Header counters come from `/api/library/summary`, and
the full metadata payload for a single track is loaded only when the metadata
dialog opens through `/api/tracks/{id}`. Search and analysis still run against
the SQLite database on the backend; the paged library view is only a UI loading
strategy.

Sonara is currently used in `playlist` mode as a fast, practical feature pass.
It writes a focused set of analyzed playlist features into SQLite metadata:
core rhythm/loudness fields, perceptual scores, musical key, tonal analysis,
and compact spectral summaries. The UI displays Sonara values in those groups,
starting with analyzed BPM and raw Sonara key data. Database keys keep Sonara's
canonical names such as `spectral_centroid_mean`, `mfcc_mean`, and
`chroma_mean`; the metadata dialog uses shorter display labels such as
Spectral Centroid, MFCC, and Chroma. Large unavailable or non-playlist fields
are not represented as placeholder rows; the current goal is inspection and
calibration, not a final data format. In the UI, `Embedding batch size` controls
how many Sonara track workers run concurrently.

The metadata popup is intentionally split by source:

- the top unnamed table starts with always-present local track/file facts:
  title, audio length, audio format, file size, and file path;
- the same top table then shows Mutagen file tags only when present: artist,
  album, genre, year, country, label, catalog, track number, disc number, BPM
  tag, key tag, comment, and ISRC;
- `SONARA features` are computed playlist analysis values grouped as Core
  features, Perceptual features, Musical key, Tonal analysis, and Spectral
  features;
- `MAEST genres` are model genre labels and confidence scores.

This separation is important because file tags and model-derived values can
disagree. In particular, BPM and key shown as Sonara values are analyzed, not
copied from tags.

MAEST genres can be saved explicitly from the UI. The global `Save genres`
button writes genres for all tracks with MAEST labels; the compact `Save`
button in the metadata popup writes genres for one track. It overwrites only
the standard genre field and keeps existing title, artist, album, BPM, key, and
other tags. MAEST genre extraction uses inference batching through direct model
logits, not the convenience `predict_labels()` helper, so each track in a batch
keeps its own genre scores. Each track is represented by three 30-second
windows, and the final stored top 3 labels are ranked after averaging per-label
activation scores across those windows.

## Run The App

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

Then open:

```text
http://127.0.0.1:8765/
```

There is also a Windows helper script in this workspace:

```powershell
scripts\run_server.cmd
```

### Startup Options

| Setting | Default | Notes |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address for the local FastAPI server. |
| `--port` | `8765` | Local HTTP port. |
| `--db` | none | Optional SQLite database path. Without it, choose or create a `.sqlite` database in the UI. |
| `--log-level` | `info` | File log level: `debug`, `info`, `warning`, `error`, or `critical`. |
| `--log-track-events` | off | Also write successful per-track job events to the file log. |
| `DJ_TRACK_SIMILARITY_LOG` | `dj-track-similarity.log` | File log path. |
| `DJ_TRACK_SIMILARITY_LOG_LEVEL` | `info` | Alternative way to set the file log level. |
| `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS` | off | Set to `1`, `true`, `yes`, or `on` to write successful per-track job events. |
| `DJ_TRACK_SIMILARITY_FFMPEG` | auto-detected from `PATH` | Full path to `ffmpeg.exe` when ffmpeg is not on `PATH`. |

`ffmpeg` is required for robust audio decoding. The server checks it on startup
and exits with a clear error if it is missing. MERT, CLAP, MAEST, and Sonara
fallback decoding use the shared audio loader: it tries the native library path
first and then falls back to `ffmpeg` without writing decoded temporary audio
into the project. File logging defaults to `info`, but successful per-track job
events are aggregated out by default so large jobs do not write one success line
per file. Use `--log-track-events` when debugging detailed track behavior. The
file log rotates daily at midnight and keeps one rotated day.

### Multiple Databases

The web app can start without a selected database. Use the database picker in
the first panel to open an existing `.sqlite` file or create a new one. If you
already know which database to use, start the server with `--db` and the UI will
open that database immediately:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765 --db "D:\DJDatabases\breaks.sqlite"
```

You can switch databases from the UI later as long as no scan, analysis, or tag
write job is active. CLI commands that read or write a database should still use
the matching `--db` path:

```powershell
dj-sim scan "D:\Music\Breaks" --db "D:\DJDatabases\breaks.sqlite"
dj-sim analyze-sonara --batch-size 4 --limit 25 --db "D:\DJDatabases\breaks.sqlite"
dj-sim analyze-genres --device cuda --batch-size 4 --limit 25 --db "D:\DJDatabases\breaks.sqlite"
dj-sim analyze --adapter clap --device cuda --batch-size 4 --db "D:\DJDatabases\breaks.sqlite"
```

Each database keeps its own tracks, analysis results, and stored paths.

## CLI Examples

```powershell
dj-sim scan "D:\Music"

dj-sim analyze-sonara --batch-size 4 --limit 25

dj-sim analyze
dj-sim analyze --device cpu --batch-size 2
dj-sim analyze --device cuda --batch-size 8

dj-sim analyze --adapter clap --device cuda --batch-size 4
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" --limit 50

dj-sim analyze-genres --device cuda --batch-size 4 --limit 25

dj-sim doctor

dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive"
dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive" --apply

python scripts\migrate_sonara_brightness.py --db "C:\db\abstracted.sqlite"
python scripts\migrate_sonara_brightness.py --db "C:\db\abstracted.sqlite" --apply
```

`scripts\migrate_sonara_brightness.py` is a small dry-run-first migration
helper for old databases that may still contain
`metadata_json.sonara_features.brightness`. It renames that legacy key to the
canonical `spectral_centroid_mean` key without touching audio files and without
overwriting rows where `spectral_centroid_mean` already exists.

## Audio Metadata Repair Script

`scripts\repair_audio_metadata.py` is a standalone diagnostic and repair helper
for audio files whose container or tag metadata cannot be read reliably after a
Mutagen tag write. It is separate from the main app because it can inspect real
audio files directly and, only with `--apply`, write repaired copies back.

Folder checks are dry-run by default:

```powershell
python scripts\repair_audio_metadata.py --folder "M:\Volumes\Abstracted" --workers 4
```

Dry-run does not write audio files and does not copy each track. It recursively
checks supported audio extensions, reports `OK`, `NOTICE`, `SUSPICIOUS`,
`TAG-ERROR`, `REPAIRABLE`, or `FAILED`, and stores progress so repeated runs of
the same folder continue from already checked files. Each state entry also
stores a short machine-friendly `reason`, for example `OVERSIZED_DATA`,
`DUPLICATE_ID3`, `EMPTY_ID3`, `CONTAINER_NORMALIZATION`,
`EXTENSION_MISMATCH`, or `CODEC_MISMATCH`, so repair can later be limited to
one exact problem type. The default state file is derived from the resolved
`--folder` path and stored under:

```text
scripts/audio_repair/state.<folder_name>.<folder_hash>.json
```

The default file log is overwritten on every run:

```text
scripts/audio_repair/repair_audio_metadata.log
```

Use `--apply` only after reviewing the dry-run report and only when there are
real `REPAIRABLE` entries:

```powershell
python scripts\repair_audio_metadata.py --folder "M:\Volumes\Abstracted" --apply
```

Apply mode is intentionally sequential even if `--workers` is provided. Before
rewriting a repaired file, the script creates a full-file backup under:

```text
scripts/audio_repair/backups/
```

To apply only one repair reason from a previous dry-run state file, pass the
exact `reason` value:

```powershell
python scripts\repair_audio_metadata.py --folder "M:\Volumes\Abstracted" --apply --reason oversized_data
```

`OK` files are not changed. `NOTICE` entries are non-required cleanup such as
cosmetic trailing padding. `SUSPICIOUS` reports format/container or codec
mismatches and is not auto-repaired. `TAG-ERROR` reports tag-read failures for
formats where there is not yet a safe repair path.

`dj-sim analyze` uses `m-a-p/MERT-v1-95M` by default through
PyTorch/Hugging Face and may download model weights on first run.

`analyze-sonara` uses `sonara.analyze_file(..., mode="playlist")` and stores
only the focused playlist feature set in SQLite metadata. Its `--batch-size`
controls parallel track workers, not a neural-network batch. If Sonara's
default decoder cannot read a WAV-like file, the app falls back to the shared
tolerant audio loader before calling Sonara signal analysis. BPM and key from
this pass are analyzed values, not file tags. The UI displays the raw Sonara
key fields rather than deriving another notation.

`--adapter clap` builds separate LAION-CLAP audio embeddings for text search.
The active CLAP path uses LAION's music-focused
`lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt` checkpoint through
the `laion-clap` package. If you previously analyzed CLAP with the older
general `laion/clap-htsat-fused` model, reset CLAP and reanalyze it so text and
audio vectors come from the same model.

`analyze-genres` uses MAEST through `maest-infer` with
`discogs-maest-30s-pw-129e-519l` to store the top 3 genre labels and confidence
scores in SQLite track metadata. Its `--batch-size` controls MAEST inference
batching on the selected device. For each track, MAEST analyzes up to three
30-second windows: the section starting at 60 seconds, then windows near 38% and
72% of track duration. For short tracks, duplicate or impossible windows are
clamped/deduplicated, and very short audio is padded as needed for batching. The
stored genre scores are averaged per-label activation scores across the windows,
then ranked into the final top 3 labels. If one track in a MAEST batch fails to
decode, the job retries that batch one track at a time so the bad file is
reported directly and the other tracks can still be analyzed. It does not modify
audio files by itself.

`doctor` reports the Python executable, installed PyTorch build, CUDA build,
whether `torch.cuda.is_available()` is true, and the device that `auto` will
choose. Use it when CUDA behavior looks suspicious.

`relocate-library` is for a practical two-drive workflow: scan and analyze a
folder on a fast SSD, move that same folder to another drive, then update the
stored track paths in SQLite. The command is a dry run by default:

```powershell
dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive"
```

It reports how many tracks match the old root, which target files are missing,
and whether any target paths would conflict with tracks already in the database.
When the preview looks right and the files exist at the new location, apply the
change:

```powershell
dj-sim relocate-library "E:\MusicFast" "D:\MusicArchive" --apply
```

This updates only `tracks.path` in SQLite. It keeps track IDs, Sonara features,
MAEST genres, MERT/CLAP embeddings, and other analysis results. It
does not move, edit, or delete audio files.

In the UI, `Analyze limit = 0` means the whole library. If you only want to test
a few tracks, set a specific integer limit yourself. Limits count missing
results for the selected analysis family, so later runs continue from tracks
without that analysis data.

## Embedding Spaces

The database can store multiple embedding spaces for the same track:

- `mert`: the main audio-to-audio similarity space.
- `clap`: the music-focused LAION-CLAP audio/text space for text search.

These spaces are intentionally not mixed into one matrix. SONARA search uses
stored SONARA playlist features from SQLite. MERT seed search uses MERT vectors
only. CLAP text search compares a CLAP text vector with CLAP audio vectors only.
The text query and analyzed audio embeddings must be produced by the same CLAP
checkpoint.

That means text search requires a separate CLAP analysis pass before it can
return useful results.

## Analysis Counters

The header shows the total library size and four analysis counters, for example:

```text
3016 треков | sonara 3016 | maest 742 | mert 3016 | clap 900
```

These counters are based on the same per-track analysis markers shown in the
track list. Sonara and MAEST are counted from stored metadata, while MERT and
CLAP are counted from their separate embedding spaces.

## Tag And Analysis Data

The app keeps a deliberately plain separation between local file metadata and
computed analysis data.

Mutagen file tags are read from a fixed whitelist instead of importing every
possible tag blob:

- title, audio length, audio format, file size, and file path are always shown
  in the metadata popup's top table;
- artist, album, genre, year, country, label, catalog number, track number,
  disc number, BPM tag, key tag, comment, and ISRC are shown there when Mutagen
  has those values.

Values are normalized before writing to SQLite metadata so odd Mutagen objects
such as ID3 timestamps can still be stored as JSON-safe strings.

`RefreshTags` in the UI rereads only these Mutagen fields for already indexed
tracks. It preserves paths and model analysis data, including Sonara, MAEST,
MERT, and CLAP results.

When explicitly saved from the UI, MAEST labels are written as one
semicolon-separated genre string, for example `Tech House; Minimal; Techno`.
The writer uses `TCON` for MP3/WAV/AIFF, `GENRE` for FLAC/Vorbis-style tags,
and `©gen` for MP4/M4A/ALAC. MAEST prefixes such as `Electronic---` are removed
before writing. WAV genre updates use Mutagen's WAVE writer, validate the
saved genre by reading the file back, and do not repair malformed RIFF/WAVE
chunk structures automatically.

Runtime logs are written to `dj-track-similarity.log` in the current working
directory by default. Set `DJ_TRACK_SIMILARITY_LOG` to choose another path.
The log rotates daily at midnight and keeps one rotated day. INFO-level startup,
completion, warning, and error messages are written by default; successful
per-track job events are skipped unless `--log-track-events` or
`DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS` is enabled.

The Sonara feature table is deliberately limited to fields produced by the
playlist workflow. It currently keeps these groups in order:

- Core features: BPM, beat frames, onset frames, onset density
  (value/sec), beat count, RMS mean/max, LUFS loudness, dynamic range, spectral
  centroid, zero crossing rate, and duration.
- Perceptual features: energy, danceability, valence, and acousticness.
- Musical key: original Sonara key and key confidence.
- Tonal analysis: chord sequence, predominant chord, chord change rate, and
  dissonance.
- Spectral features: spectral bandwidth, rolloff, flatness, contrast, MFCC
  mean, and chroma mean.

The small trash buttons next to analysis names reset only that analysis family:

- Sonara reset removes `sonara_features` and restores BPM/key/duration from
  file tags where possible.
- MAEST reset removes stored genre labels.
- MERT and CLAP reset remove only their embedding rows.

The database clear button removes local SQLite records after confirmation. It
does not remove or edit audio files.

## Text Search

CLAP text search is not metadata filtering. It is an embedding query: the
music-focused LAION-CLAP model tries to place your phrase near audio that
matches the description.

Short, concrete English prompts usually make the most sense. Prefer a compact
caption that names audible musical details:

```text
Melancholic minimal house with broken drums, warm chords, no vocals
Dark hypnotic rominimal with sparse clicks, wooden percussion, deep rolling bass
Organic microhouse with guitar-like plucks, soft pads, spacious sunset mood
```

Good query ingredients:

- broad genre or scene words;
- mood and intensity;
- rhythm or drum feel;
- sound texture;
- vocal presence, for example `no vocals` or `female vocal`.

## Performance Notes

MERT, CLAP, and MAEST analysis are accelerated mostly by device selection and
inference batching, not by running many model workers in parallel.

- `auto` uses CUDA when PyTorch can see a GPU, otherwise CPU.
- `cpu` is slower, but useful for compatibility checks.
- `cuda` is usually faster. Start with `batch size 4-8` and raise it carefully.
- `batch size` affects speed and memory use, but should not change the produced
  embeddings or genre scores because mixed precision is not currently enabled.
- If CUDA is explicitly requested but unavailable, the analysis fails instead
  of silently falling back to CPU. Use `auto` when fallback is desired.

MAEST genre extraction uses the same `auto`, `cpu`, and `cuda` device behavior.
Internally, the app sends a `[batch, time]` audio tensor to `maest-infer` and
reads per-track logits from `model(...)`. It intentionally avoids
`predict_labels()` for batch analysis because that helper averages activations
into one label vector. The active MAEST model expects 30-second inputs, so the
app creates up to three 30-second windows per track and averages per-label
activation scores before ranking the final labels. Some current `torchaudio`
builds delegate audio loading to TorchCodec; if that native path is unavailable
or fails, the shared loader uses the existing `ffmpeg` executable from `PATH` or
`DJ_TRACK_SIMILARITY_FFMPEG` as a fallback.

The three-window MAEST path multiplies model inputs by up to three windows per
track, so it is expected to be roughly 2.5-3x slower than the previous
single-window genre path on the same hardware. On one local CUDA benchmark, 125
tracks / 374 windows took about 75 seconds, but that number depends heavily on
GPU, disk, and file decode behavior.

Sonara playlist analysis is usually much lighter than MERT/CLAP/MAEST model
inference. It still reads and decodes audio, so the full-library pass is not
free, but it is intended to be a fast feature inspection step. Its batch size
means parallel track workers rather than model inference batching. The current
implementation summarizes large arrays instead of storing full arrays in the
database.

PyTorch CUDA wheels should be installed explicitly for the local machine before
running real MERT, CLAP, or MAEST analysis. For example, choose the matching
command from the official PyTorch installer, such as:

```powershell
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
```

Then install the remaining ML packages without replacing the selected torch
stack:

```powershell
python -m pip install transformers maest-infer --no-deps
```

## Safety

- Scanning, analysis, search, preview, and export do not modify audio files.
- `RefreshTags` rereads file metadata and updates SQLite only.
- Analysis reset buttons delete only local SQLite analysis outputs.
- Database clear deletes local SQLite records only; it does not delete music
  files.
- The UI genre save action is the explicit exception: it writes MAEST genres
  into the standard audio genre tag and should overwrite only that genre field.

## Roadmap

These are the directions that currently seem most useful, roughly in priority
order:

1. `Search calibration` - inspect real score distributions and choose practical
   defaults for `Similarity`, `Epsilon`, and controlled randomization.
2. `Auto chain` - build a set gradually: seed, find a few close tracks, move the
   context forward, and repeat until the desired limit is reached.
3. `Sonara calibration` - inspect real result sets for the custom mixer,
   modifier controls, score breakdowns, and default thresholds.
4. `Mel/CNN similarity` - use mel-spectrogram or CNN-style embeddings to capture
   pattern, structure, groove, density, and spectral shape.
5. `Music feature similarity` - improve the explainable DSP layer with
   additional calibrated features such as PLP, Mel Spectrogram, Constant-Q
   Transform, waveform envelope, and autocorrelation.
6. `Hybrid ranking` - combine MERT audio similarity and CLAP text/audio
   similarity in a controlled way after both score ranges are understood.
7. `DJ transition features` - beatgrid, downbeat, phrase structure, loudness,
   real energy, intro/outro spectral balance, vocalness, groove/percussion
   density, and other features that matter specifically for mixing.
8. `MERT model upgrade` - add `m-a-p/MERT-v1-330M` as an optional heavier model
   after the current pipeline is stable.
9. `Scale improvements` - add an ANN index or cached embedding matrix for larger
   libraries.

## Development

Install for development:

```powershell
python -m pip install -e ".[dev]"
```

Install optional ML dependencies:

```powershell
python -m pip install -e ".[ml,dev]"
```

Install Sonara support:

```powershell
python -m pip install -e ".[sonara,dev]"
```

Install everything used by the full local lab:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

For CUDA work, prefer installing PyTorch separately with the official CUDA wheel
index first. A plain `.[ml]` install can only express generic Python
dependencies; it cannot know which CUDA wheel your machine needs.

Run backend tests:

```powershell
pytest
```

Build the frontend:

```powershell
cd frontend
npm run build
```
