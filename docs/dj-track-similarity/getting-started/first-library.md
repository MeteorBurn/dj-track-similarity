# Build your first library

A library is the app's private map of your music collection. It lets you search one catalog even when
the files are spread across folders and their tags are incomplete. Your audio stays in its original
location.

Control names on this page are English. The browser shows most of them in Russian, so use the
[UI language glossary](../help/ui-language.md) to match a name to the string on screen.

## What you get after a scan

- one browsable list of supported audio files,
- searchable artist, title, album, genre, path, and other available tags,
- stable track rows that later analysis can attach results to,
- scan counts that show what was added, updated, unchanged, or skipped.

Scanning alone does not give you sound-based search. It builds the catalog first. The next step,
[analysis](./first-analysis.md), adds the audio evidence behind similarity search, text search, LAB
comparison, Audio Dedup, and classifiers.

## How the catalog is stored

The selected library file stores track identity, paths, tags, analysis rows, embeddings, likes, and
classifier scores. Its one `library` row carries the `catalog_uuid` and selected scan roots.

`*.evaluation.sqlite` is an optional adjacent database for evaluation data. Resolving its path does
not create it. Normal startup refuses a legacy split layout instead of adapting it.

## Choose or create a database

In panel 1, database and analysis, the read-only field at the top shows the current SQLite path,
with a placeholder asking you to choose a SQLite database when nothing is selected. Press the
database icon beside it, titled **Choose a SQLite database**, and pick the file. A new path creates
the current library schema. An existing path loads only after the runtime validates its `library`
identity. Switching the database also clears old library and search state, so a late response cannot
leak rows from the previous catalog.

From the CLI, pass `--db`:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

## The import dialog

In panel 1, database and analysis, a **DATABASE** stage card sits right below the database path row:
a checkbox, a description, a live count of tracks already loaded, and a **Clear the database** trash
button. Below that card, press **Track import settings** to open a dialog headed the same way,
subtitled with a line saying that formats and duration decide what enters the database. The button
stays disabled until a database is selected.

This dialog only edits settings. It no longer starts a scan itself. Its footer button is **OK**,
which just closes the dialog and keeps whatever is set, with no validation on close. Every setting
here except the source folder persists in browser storage, the same way the SONARA and ML staging
folders do: the folder itself is never restored, so every session asks for it again.

This dialog no longer sets the SONARA BPM range. That range now belongs to the SONARA analysis
settings dialog, covered in [First analysis](./first-analysis.md#choose-a-sonara-bpm-range-for-your-library).

### File formats

Fourteen format chips, all selected at first. A counter beside the section title reads how many of
the 14 are selected. Click a chip to exclude that format, and click it again to include it.

```text
AAC  AIF  AIFF  ALAC  APE  FLAC  M4A  MP3  OGG  OPUS  WAV  WAVE  WMA  WavPack
```

They map to these extensions:

```text
.aac .aif .aiff .alac .ape .flac .m4a .mp3 .ogg .opus .wav .wave .wma .wv
```

A supported audio file whose format chip is deselected is counted under `skip` in the activity
status rather than silently ignored.

### Selection bounds

| Control | Initial value | Range or behavior |
| --- | ---: | --- |
| **Minimum seconds** | `120` | positive integer; clearing the field disables only this bound |
| **Maximum seconds** | `1200` | positive integer; clearing the field disables only this bound |
| `Workers` | `8` | `1..16` metadata reader processes |

There is no `Scan limit` stepper in this dialog. The panel's shared **Track limit** stepper, below
all three stage cards, counts tracks added to the database instead, applied once DATABASE is checked
and **Start** is pressed.

### Music folder

The read-only path field reports that no folder is selected until you press the folder icon, titled
**Choose a folder on the server**. The picker runs on the machine hosting the backend. Scanning
descends into subfolders.

### Starting the import

Close the dialog once its settings are set up, with the footer **OK** button, the header **Close**
icon, or `Escape`. Closing does not start anything by itself.

Back in panel 1, check the **DATABASE** stage card. Its checkbox is deselected once you check
SONARA or an ML model, and vice versa, so only one of the three stage cards is ever checked. With
DATABASE checked, set the shared **Track limit** if you want fewer than every eligible track, then
press **Start**. **Start** stays disabled while DATABASE is checked and the dialog's folder is still
empty. A warning above the button asks you to set a source folder in the import settings.

Pressing **Start** closes the dialog if it is still open, and a centered toast reports that the
track list is being prepared. The main status reads that the directory is being scanned. After the
API returns the scan job, it changes to say that tracks are being loaded into the database, and the
normal scan-job status takes over with counts for added, updated, unchanged, skipped, and failed. The
browser refreshes the typed library summary when the job finishes.

## How the scan runs

The app first collects a list of paths that match the selected formats, then submits the raw paths
to the configured `ProcessPoolExecutor` in bounded batches of up to `64`. It keeps at most twice as
many metadata batches in flight as the configured worker count. As each batch finishes, the parent
scan coordinator consumes its results and writes eligible records to SQLite right away instead of
waiting for metadata reads across the whole library. All SQLite writes stay on the parent job
thread. Worker processes only read metadata and apply the duration bound. There is no separate
duration pass.

Duration comes from Mutagen metadata first, then from a lightweight PyAV container-duration fallback
that decodes no audio frames. Files with an unknown duration are skipped when a bound is active.

The directory walk is name-sorted and depth-first, it does not follow symlinked directories, and it
de-duplicates resolved paths. It skips AppleDouble-style files whose names start with `._`.

A file whose size or modification time changed between the metadata read and the write is failed
rather than written with stale values.

The equivalent CLI command is:

```powershell
dj-sim scan D:\Music --db .\data\library.sqlite
```

The CLI scans with the full extension set and no bounds, which is also the only configuration that
marks previously seen files as missing. Both surfaces create a fresh library database when the
selected file does not exist. A legacy split database stays unchanged until you explicitly stop its
users and run `dj-sim migrate-database`.

## What scan reads

Scan reads exactly eleven tag fields through Mutagen, plus duration and technical file facts:

```text
artist  title  album  genre  year  country  label  track_number  bpm  key  comment
```

Each name resolves through several tag aliases, so `artist` also accepts `albumartist`, `TPE1`,
`TPE2`, `©ART`, and `aART`. Catalog number, disc number, and ISRC are not read and have no column.

When a tag cannot be read, scan still creates a minimal metadata row with the file stem as title.

## What scan writes

Scan writes library track and tag rows. It does not write audio tags. A track is updated when its
file size or modification time changes. An unchanged size and modification time pair deliberately
skips tag decoding, so a tag-only edit needs Refresh Tags.

The CLI prints added, updated, unchanged, and skipped counts.

## Refresh Tags

The backend can reread file tags for existing tracks without rerunning SONARA, MAEST, MERT, MuQ,
MuQ-MuLan, or CLAP. Press the circular-arrows icon titled **Refresh tags** in panel 1, database and
analysis. It uses eight workers and reports progress through the same activity surface as scan.
Stored paths and every analysis row stay untouched.

## Browse after scan

The library panel reads one server-backed page of up to `200` tracks at a time. Use `Prev`, `Next`,
or the page-number field to move between pages. Each page maps to one `/api/tracks` request with
`limit=200`. The final page can hold fewer rows. Every row from the current page renders in one
scrollable list.

The browser deduplicates each loaded result by `catalog_uuid` and `track_uuid`. Metadata opens from
the detail endpoint only when requested. Preview and liked-track changes use the same exact track
identity.
