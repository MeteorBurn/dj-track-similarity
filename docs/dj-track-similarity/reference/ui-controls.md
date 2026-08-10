# Browser controls reference

> Audience: Users looking for current browser control ranges and defaults.
> Goal: Describe the current UI that is backed by the active API.
> Type: reference

The browser works with one catalog bundle. The database picker selects the Core SQLite
file; the runtime resolves the mandatory `*.artifacts.sqlite` companion and validates the shared
`catalog_uuid`. The optional `*.evaluation.sqlite` companion is opened only by evaluation
workflows. There are no separate Timeline or Representations database controls.

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
  `/api/tracks/{track_id}`. A liked-track write carries `catalog_uuid`, `track_uuid`, and
  `expected_content_generation`.

Changing the database cancels or invalidates older library and search requests. Track rows are
deduplicated by `catalog_uuid` plus `track_uuid`; when duplicate responses race, the greatest
`content_generation` wins.

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
pipeline. SONARA is selected at startup and always runs Core only. There are no output checkboxes.
The ML selection contains MAEST, MERT, MuQ, and CLAP only;
SONARA and CLASSIFIERS remain separate stages. The UI also shows queued/running progress, per-file
failures, blockers, cancellation, and reset actions from the typed job responses.

## Search tabs

The primary tab list is **LAB**, **SONARA**, **MERT**, **MUQ**, **CLAP**, and **CLASS**.
Use `ArrowLeft` and `ArrowRight` to move between tabs; `Home` and `End` jump to the first and last
tab.

MERT and MUQ use the same generic seed-search shape. Both accept a `1..500` result limit and
selected seed tracks. A tab with zero current embeddings is disabled with a source-specific reason.
Request failures stay visible in that tab instead of being replaced by an empty successful result.

## CLASS, LAB, and Rhythm Lab

The **CLASS** tab filters the library by stored classifier scores. Its per-profile action resets and
rescans only that `classifier_key`. It does not decode audio. The main analysis panel also exposes
the separate **CLASSIFIERS** stage and the ordered **FULL** pipeline.

The **LAB** tab compares a reference track across CLAP, MERT, MuQ, MAEST, and SONARA. Unavailable
models show a model-specific reason. Verdict writes include `catalog_uuid`, `track_uuid`, and
`content_generation`, and the MuQ action sends `model="muq"`.

The top-bar Rhythm Lab action calls `/api/rhythm-lab/launch` and opens the returned local URL. The
current set can be saved as a Lab review collection. Standalone Rhythm Lab shows current, missing,
or stale state for SONARA, MERT, MAEST, CLAP, and MuQ; its page sizes are `50`, `100`, `200`, and
`500`. The **Training recipe** selector supports MuQ and explicit source combinations. The legacy
`combined` recipe remains `sonara+mert+maest`.

## Audio Dedup

The Audio Dedup dialog exposes `mert`, `maest`, `muq`, and audio-to-audio `clap` source checkboxes.
It shows raw defaults `0.43`, `0.32`, `0.12`, and `0.04`, supports **Custom raw weights**, and
provides **Reset defaults** and **Pre-MuQ legacy** actions. The legacy action selects `mert`,
`maest`, and `clap` with raw weights `0.43`, `0.32`, and `0.04`.

Report mode is the default. Apply mode still requires the exact `APPLY DELETE` confirmation. MuQ or
CLAP evidence alone never authorizes deletion.

For analysis semantics, see [Analyze a library](../user-guide/analyze-library.md). For
source-file boundaries, see [Local-first safety](../concepts/local-first-safety.md).
