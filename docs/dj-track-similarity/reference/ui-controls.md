# Browser controls reference

The browser works with one library database. The database picker selects the library SQLite file;
the optional `*.evaluation.sqlite` companion is opened only by Evaluation workflows. There are no
separate Timeline or Representations database controls.

## Database and library

- **Choose database** selects or creates the library SQLite file. An older or incomplete catalog is
  rejected instead of being migrated in place.
- **Load tracks into the database** opens an import dialog. Its server-side folder picker selects
  the root, and its format badges select the formats to scan. Scan and **Refresh Tags** update
  catalog rows without rewriting source audio.
- Library pages contain up to `200` tracks. **Prev**, **Next**, and the page-number field request one
  `/api/tracks` page at a time.
- All rows from the current page render in one scrollable list. There is no second row-window
  paginator.
- Library text search can use **LIKE** or **FTS**. Preset, liked-only, classifier-score, and sort
  controls remain server-backed filters.
- Preview streams `/media/{track_id}`. Metadata is fetched on demand from
  `/api/tracks/{track_id}`. A liked-track write carries `catalog_uuid` and `track_uuid`.

Changing the database cancels or invalidates older library and search requests. Track rows are
deduplicated by `catalog_uuid` plus `track_uuid`.

## Analysis

The initial analysis values are:

| Control | Default | Range or meaning |
| --- | ---: | --- |
| **Analyze limit** | `0` | `0..100000`; `0` means the whole eligible library |
| **Track batch** | `8` | `1..64` |
| **Inference batch** | `16` | `1..128` |
| **SONARA Mode** | `Direct` | `Direct` or `Staged` |
| **Direct BatchSize** | `8` | `1..16` source paths per native batch |
| **Staged Folder** | empty | Existing temporary folder selected with **Choose Folder** |
| **Staged Processes** | `4` | `1..16` |
| **Staged Threads** | `4` | `1..64` Rayon threads per process |
| **Staged BatchSize** | `4` | `1..16` ready staging paths per native mini-batch |
| **Staged StageSize** | `32` | `1..512` files in the staging window |
| **Device** | `auto` | `auto`, `cpu`, or `cuda` |

The stage controls keep **SONARA**, **ML**, and **CLASSIFIERS** distinct. **FULL** runs the ordered
pipeline. SONARA is selected at startup and always runs Core plus its dedicated embedding as one
fixed output set. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ, MuQ-MuLan, and CLAP only;
SONARA and CLASSIFIERS remain separate stages. The UI also shows queued/running progress, per-file
failures, blockers, cancellation, and reset actions from the typed job responses.

The staging-folder field is read-only. It and **Choose Folder** stay visible but disabled in Direct
Mode, and both become active in Staged Mode. No staging path or placeholder is supplied on first
use, so Staged Mode cannot start until the user selects a folder. Mode, both BatchSize values, the
folder, and the other Staged settings persist together in browser `localStorage`. These controls
affect SONARA only, so GPU model analysis does not use the staging folder.

## Track import

Each opening of **Load tracks into the database** starts a new modal dialog; it does not retain a
previous folder or settings. The default selected formats are **MP3**, **FLAC**, **ALAC**, **WAV**,
**WAVE**, **AIFF**, **AIF**, **M4A**, **OGG**, and **OPUS**. **Scan limit** is `0..100000` and
starts at `0`; `0` scans every eligible track. The default duration range is `120..1200` seconds.
Clear either duration field to disable that bound independently. **Workers** starts at `8` and
allows `1..16`.

The app first collects a list of paths that match the selected formats, then submits the raw paths
to the configured `ProcessPoolExecutor` in bounded batches of up to `64`. It keeps at most twice as
many metadata batches in flight as the configured worker count. As each batch finishes, the parent
scan coordinator consumes its results and writes eligible records to SQLite immediately instead of
waiting for metadata reads across the whole library. All SQLite writes stay on the parent job
thread. Worker processes only read metadata and apply the duration bound. There is no separate
duration pass.

Duration uses Mutagen metadata first and then a lightweight PyAV container-duration fallback that
does not decode audio frames. When a duration filter is active, files whose duration cannot be
determined are skipped. **Scan limit** caps tracks that meet the selected filters.
The final scan total includes only tracks accepted after the duration bounds and scan limit. The
scan status shows `skip N` for tracks rejected by those filters plus supported audio files excluded
by the selected format badges.

## ML analysis availability

The ML checkboxes for MAEST, MERT, MuQ, MuQ-MuLan, and CLAP are unavailable until the library has
at least one SONARA result. Until then, the analysis selection is limited to SONARA. Run SONARA
first, then select the ML families to analyze.

## Search tabs

The primary tab list is **LAB**, **SONARA**, **MERT**, **MUQ**, **MULAN**, **TEXT**, and **CLASS**.
Use `ArrowLeft` and `ArrowRight` to move between tabs; `Home` and `End` jump to the first and last
tab.

MERT, MUQ, and MULAN use the same generic seed-search shape. All accept a `1..500` result limit and
selected seed tracks. A tab with zero current embeddings is disabled with a source-specific reason.
Request failures stay visible in that tab instead of being replaced by an empty successful result.

## CLASS, LAB, and Rhythm Lab

The **CLASS** tab filters the library by stored classifier scores. Its per-profile action resets and
rescans only that `classifier_key` from stored data, without decoding audio; the main analysis panel
does not run classifier scoring.

The **LAB** tab compares a reference track across six separate default groups: CLAP, MERT, MuQ,
MuQ-MuLan, MAEST, and SONARA. Unavailable models show a model-specific reason. Verdict writes
include `catalog_uuid` and `track_uuid`.

The **TEXT** tab has a **Model** control for CLAP and MuQ-MuLan text-to-track search. It requires
current stored audio embeddings for the selected family. Results from either selection stay in that
family’s score space and appear on the TEXT tab.

The top-bar Rhythm Lab action calls `/api/rhythm-lab/launch` and opens the returned local URL. The
current set can be saved as a Lab review collection. Standalone Rhythm Lab shows current, missing,
or stale state for SONARA, MERT, MAEST, CLAP, and MuQ; its page sizes are `50`, `100`, `200`, and
`500`. For a binary profile, a configured training label appears immediately after **TRAINED** with
its display name: positive is green and negative is red. The **Training recipe** selector supports
MuQ and explicit source combinations.

For analysis semantics, see [Analyze a library](../user-guide/analyze-library.md). For
source-file boundaries, see [Local-first safety](../concepts/local-first-safety.md).
