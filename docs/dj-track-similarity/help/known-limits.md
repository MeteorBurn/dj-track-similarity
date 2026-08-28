# Known limits

Current boundaries that are working as intended, plus the local setup details that decide whether
the app works at all on your machine.

## The interface is Russian, the documentation is English

Every panel heading, button, tooltip, and notice in the browser is Russian. This documentation names
controls in English. [UI language](./ui-language.md) maps them, control by control.

Only technical tokens stay English on screen. Those are the model names, the five tab labels, the
SONARA mode names, and numeric field labels such as `Limit`, `Mode`, and `Device`.

There is no language switch. The in-product hover help is Russian as well, and it is a separate text
surface from these pages with its own small drifts.

## The app does not build sets automatically

The current set is a list you assemble by hand. You add candidates one at a time, preview them,
remove the ones that do not fit, and export the result.

Nothing turns anchors into an ordered sequence with a chosen energy, diversity, or tempo direction.
The set-dramaturgy framing in the project description is the goal that shapes what gets built, not a
feature you can run today.

## The local API has no authentication

`dj-sim serve --host 127.0.0.1` is the safe default. LAN mode binds `0.0.0.0` and prints a LAN URL,
and any device that reaches that port has the same reach as the browser, including database clear
and Audio Dedup deletion. Use LAN mode only on a network you trust.

## Audio Doctor has no in-app surface

Audio Doctor is a CLI tool with no route in the application. Nothing in the browser starts it,
stops it, or reports its state. Run it from a terminal, and read
[Audio Doctor](../tools-and-scripts/audio-doctor.md) before using `--apply`, which writes without a
confirmation prompt.

## Persistent ANN indexes do not exist

Vector search is exact NumPy cosine over the full embedding matrix for the selected family. The
repository holds one search backend and it is that one. Older documentation and the project README
describe optional approximate-nearest-neighbour sidecars and link to a page that was never written.
Ignore those references.

Search cost grows with library size and embedding dimension. Ranking is progressive-depth, so a
small `Limit` costs less than a large one.

## Model analysis is heavy

MAEST, MERT, MuQ, MuQ-MuLan, and CLAP need optional ML dependencies and downloaded checkpoints.
Weights download on first use rather than at install time, so the first job for a family waits in a
warm-up phase.

MuQ and MuQ-MuLan run on mono 24 kHz `float32` audio in 10-second windows. Large libraries take time
and memory. Use a small `--limit` first, then adjust device and batch sizes.

## Local-first means local setup matters

The app depends on your Python environment, a system-available shared FFmpeg runtime, optional ML
packages, GPU runtime, filesystem paths, and browser access to the backend. The repository does not
version or vendor the required FFmpeg `8.1.1` full shared runtime. An `ffmpeg.exe` installed for
another program is not a substitute, because TorchCodec loads the shared libraries directly. Run
`dj-sim doctor` to inspect the selected runtime and the PyAV installation.

## SONARA installs from a local wheel

The `sonara` extra pins `0.3.6` and resolves it through `[tool.uv.sources]` to a patched wheel on
the maintainer disk rather than to a package index. Anyone else has to build that wheel from the
SONARA sources and repoint the source entry. The published `0.3.5` release is no substitute, because
it does not return the BPM range provenance that storage requires. See
[Install](../getting-started/install.md).

## Scores are not probabilities

Search scores are ranking signals. The eight score spaces the app produces are separate scales, and
a threshold tuned on one means nothing on another. See
[Similarity scores](../concepts/similarity-scores.md).

## Classifier scoring never re-scores

Scoring skips every track that already holds a row for that classifier key. There is no staleness
detection and no `model_id` column. After a retrain and promotion, reset that key before scoring,
or the job finds zero work and reports success.

Resetting SONARA does not delete classifier scores either. They survive and go stale silently.

## Some analysis output has no consumer yet

The 48-dimensional SONARA embedding is written on every successful SONARA pass and is read by
nothing in search, classifiers, or Audio Dedup. SONARA mood values, true peak, and ReplayGain are
stored and available to Rhythm Lab recipes while staying out of every similarity path. The four
aggression component values are stored and unread.

None of this affects a ranking today. It is deliberate work in progress rather than dead code.

## Browser preview depends on files still existing

The database stores paths. If files move or disappear, preview fails until you rescan or relocate
stored paths. Relocation is a CLI workflow, with no browser surface.

## Native dialogs depend on local GUI support

The database and folder picker routes use local GUI support. If that is unavailable, type paths
manually or use CLI commands.

## Docs are built separately

The backend serves `/docs/` only when `docs/dj-track-similarity/site/` exists. Without it, `/docs/`
returns a 503 page telling you to build. Run `npm run check` from the docs folder.
