# Browser controls reference

> Audience: Users looking for current browser control ranges and defaults.
> Goal: Describe the current UI that is backed by the active API.
> Type: reference

The browser works with one library database. The database picker selects the library SQLite file;
the optional `*.evaluation.sqlite` companion is opened only by Evaluation workflows. There are no
separate Timeline or Representations database controls.

## Database and library

- **Choose database** selects or creates the Core file. An older or incomplete catalog is rejected
  instead of being migrated in place.
- **Music root** and **Scan workers** configure a scan. Scan and **Refresh Tags** update catalog
  rows without rewriting source audio.
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
| **Scan workers** | `8` | Clamped to the local worker limit |
| **Track batch** | `8` | `1..64` |
| **Inference batch** | `16` | `1..128` |
| **SONARA batch** | `8` | `1..16` |
| **Device** | `auto` | `auto`, `cpu`, or `cuda` |

The stage controls keep **SONARA**, **ML**, and **CLASSIFIERS** distinct. **FULL** runs the ordered
pipeline. SONARA is selected at startup and always runs Core plus its dedicated embedding as one
fixed output set. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ, MuQ-MuLan, and CLAP only;
SONARA and CLASSIFIERS remain separate stages. The UI also shows queued/running progress, per-file
failures, blockers, cancellation, and reset actions from the typed job responses.

## Search tabs

The primary tab list is **LAB**, **SONARA**, **MERT**, **MUQ**, **MULAN**, **CLAP**, and **CLASS**.
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

The **CLAP** tab has a **Model** control for CLAP and MuQ-MuLan text-to-track search. It requires
current stored audio embeddings for the selected family and keeps the result in that family’s score
space.

The top-bar Rhythm Lab action calls `/api/rhythm-lab/launch` and opens the returned local URL. The
current set can be saved as a Lab review collection. Standalone Rhythm Lab shows current, missing,
or stale state for SONARA, MERT, MAEST, CLAP, and MuQ; its page sizes are `50`, `100`, `200`, and
`500`. For a binary profile, a configured training label appears immediately after **TRAINED** with
its display name: positive is green and negative is red. The **Training recipe** selector supports
MuQ and explicit source combinations.

For analysis semantics, see [Analyze a library](../user-guide/analyze-library.md). For
source-file boundaries, see [Local-first safety](../concepts/local-first-safety.md).
