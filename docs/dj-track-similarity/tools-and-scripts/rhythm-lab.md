# Rhythm Lab

> Audience: Users creating local classifier profiles.
> Goal: Label, train, review, and promote without crossing source-audio boundaries.
> Type: guide

Rhythm Lab is a separate local labeling and training tool. Its labels, predictions, checkpoints, and
artifacts stay under `tools/rhythm-lab/`. It reads the main v7 library mostly read-only. The explicit
liked-track toggle is the narrow main-database write path. Rhythm Lab does not rewrite source audio.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab_v7.sqlite
```

The greenfield v7 writable default is `tools/rhythm-lab/data/rhythm_lab_v7.sqlite`. If
`tools/rhythm-lab/data/rhythm_lab.sqlite` exists from the legacy runtime, normal startup and
collection saves leave it untouched. Do not pass the legacy file to normal `serve`, training, or
collection commands. Use the recovery workflow below.

Create and label a profile, train it from its declared inputs, review its predictions, and promote a
chosen artifact. Promotion makes a database-only scoring artifact available to the main runtime.
Scoring does not decode audio and writes only its own `classifier_key` rows.

Only classifier manifest version `2` is scoring-compatible. Checked-in version `1` or unversioned
artifacts are blocked until retrained and promoted. SONARA-dependent profiles must match current
SONARA contracts and feature revision `6`. Missing inputs are incompatible rather than zero-filled.

Normal training now includes the `muq` feature set. MuQ can also participate in arbitrary
source combinations accepted by the backend and CLI. The legacy `combined` alias remains
`sonara+mert+maest`.

The default `benchmark-ablation` matrix preserves its previous combinations and adds four
representative MuQ cases: `muq`, `sonara+muq`, `mert+muq`, and
`sonara+mert+maest+clap+muq`. Repeat `--feature-set` to benchmark other explicit combinations.
Promoted manifest version `2` records the exact ordered contracts, and runtime scoring accepts
canonical `muq:<index>` features from the current MuQ embedding contract.

For a changed SONARA release, first run the ordered, crash-resumable `prepare-sonara-release` flow
for the main Core + Artifacts pair, then reanalyze, retrain, promote, and rescore affected profiles.
It is not a distributed atomic transaction.

## Open Rhythm Lab from the main app

Choose a v7 database in the main app, then click the Rhythm Lab flask in the top bar. The browser
calls `/api/rhythm-lab/launch`, reuses an existing matching process when possible, and opens the
returned local URL. The launch response is bound to the selected Core + Artifacts catalog rather
than to a numeric track ID alone.

The main set panel can also save its current ordered tracks as a Lab collection. That write carries
`catalog_uuid`, `track_uuid`, and `content_generation` for every item. It does not change labels or
source audio.

## MuQ-aware standalone UI

The standalone UI reports `current`, `missing`, or `stale` state for SONARA, MERT, MAEST, CLAP, and
MuQ. Coverage counts do not make a stale source trainable. The **Training recipe** selector exposes
MuQ alone and every supported source combination; readiness and blocker text are recalculated for
the selected recipe only. The legacy `combined` option still means `sonara+mert+maest`.

The training workflow uses the selected recipe to fit a model and refresh candidates. You can then
benchmark variants before promoting a current-contract artifact. Library, Candidates, and
Collection views use page sizes `50`, `100`, `200`, or `500`. The explicit liked-track toggle is
still the only narrow main-catalog write from standalone Rhythm Lab.

## Recover labels from a preserved legacy database

The transfer tool accepts sealed bundle format version `3`. Keep the original byte-for-byte legacy
Lab database backup together with its matching `-wal` and `-shm` files. That SQLite set remains the
source recovery artifact. Exported JSON bundles and reports are derived working files, not
replacements for the preserved database set.

Run the commands from `tools/rhythm-lab/`. Export uses one fixed read-only SQLite snapshot,
including committed WAL frames. SQL `NULL` values remain null, and labels that share a duplicate
path remain separate records:

```powershell
python -m rhythm_lab.label_transfer export --lab-db <legacy-lab.sqlite> --output <export.json>
python -m rhythm_lab.label_transfer preview --bundle <export.json> --core-db <current-v7-core.sqlite> --output <preview.json>
python -m rhythm_lab.label_transfer rebound --bundle <export.json> --preview <preview.json> --output <rebound.json>
```

Restore has this command shape:

```powershell
python -m rhythm_lab.label_transfer restore --bundle <rebound.json> --core-db <current-v7-core.sqlite> --lab-db <target-lab.sqlite> --report <report.json> [--accept-record-id sha256:...] [--apply] [--force]
```

The square brackets mark optional flags and are not literal command text. Run without `--apply`
first. That default writes a report only and does not create or modify the target Lab database.
Strong matches are eligible automatically. A weak match remains a recovery row unless you review it
and pass its stable ID through `--accept-record-id`. Repeat the option to accept more than one.

Immediately before planning either a preview or an apply, restore reopens the current v7 Core
database read-only. It requires the rebound target to still match the exact `catalog_uuid`,
`track_uuid`, `content_generation`, selected path, file size, and mtime. A changed binding becomes an
unresolved recovery record instead of being written as a label.

Apply writes unresolved rows to `classifier_label_recovery`, including unaccepted weak matches,
unmatched or ambiguous paths, changed file facts, stale bindings, and conflict losers. Conflict
resolution is deterministic: the latest source `updated_at` wins; equal timestamps use the
lexicographically smallest `record_id`. No source label record is silently discarded.

Before changing an existing target, apply copies the target Lab database and any existing `-wal`
and `-shm` companions into a timestamped backup directory. Applying the same rebound bundle again
is data-idempotent because bound labels and recovery rows are upserted. `--force` only allows the
JSON report to replace an existing file. It does not override matching, conflict, or Core
revalidation.

Export, preview, rebound, and restore do not write the v7 Core database, source audio, or promoted
model files. Only `--apply` writes the target Lab database; the commands also create their requested
JSON files and the apply-time target backup.
