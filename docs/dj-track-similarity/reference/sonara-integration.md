# SONARA integration

> Audience: Maintainers working with stored SONARA results.
> Goal: Describe the current decode, output, storage, and update boundaries.
> Type: reference

## Current path

The current project uses SONARA in `playlist` mode with a `70..180` BPM range. Direct Mode is the
default and passes source paths to native `analyze_batch()`. Staged Mode instead copies selected
source files read-only to a per-job directory below a user-selected folder. It never moves or
modifies the source files. In Staged Mode, SONARA and any fallback FFmpeg decoder receive only
staging-copy paths, while job status, errors, and stored outputs continue to use the original
candidate identity.

The browser stores independent Direct and Staged settings in `localStorage`. Direct BatchSize
defaults to `8`. Staged settings start with an empty folder, Processes `4`, Threads `4`, BatchSize
`4`, and StageSize `32`. The API accepts Processes `1..16`, Threads `1..64`, BatchSize `1..16`, and
StageSize `1..512`. The selected folder must already exist.

In Staged Mode, StageSize bounds files being copied, waiting in the shared ready queue, and being
analyzed. Each persistent worker process sets `RAYON_NUM_THREADS` from Threads and takes up to
BatchSize ready paths for `sonara.analyze_batch()` without cross-process batch barriers. SONARA's
Symphonia path is the normal decoder. A decode or codec failure for one result does not fail its
mini-batch: FFmpeg decodes that same input to mono `float32` PCM, resamples it to SONARA's sample
rate when needed, and retries through `analyze_signal()`. If that fallback fails, the error belongs
only to the original track. Direct Mode uses the same per-file fallback rule, but its input remains
the source path rather than a staging copy.

Each staging copy is removed after its analysis, including any fallback, completes. The job directory
is removed on success, failure, or cancellation. Every Staged session creates a new unique job
directory. Before doing so, it removes an owner-marked staging directory only if its recorded owner
process is gone, and also removes an empty `sonara-stage-*` residue that has no valid owner marker.
It preserves a directory with a live owner and a nonempty directory without a valid marker. Staged
Mode is SONARA-only. Generic ML reads original source paths and uses a separate tolerant full-track
FFmpeg fallback after a full TorchCodec failure. Preview and other non-SONARA functions keep their
own decode paths.

The application requests a fixed output set. It contains scalar and compact fixed-vector Core data
together with the SONARA embedding and acoustic fingerprint. It stores Core in `sonara_features`, the unnormalized
48-dimensional `float32` embedding in the dedicated `sonara_embeddings` table, and SONARA's native
base64 fingerprint in `sonara_fingerprints`. Timeline is not requested, converted, stored, read, or
exposed.

The Full-only `time_signature` metrogram is excluded from current SONARA storage. It is not a ranking
or classifier input, and Beatgrid uses SONARA's normal fallback when a meter estimate is unavailable.

## Storage boundary

A selected catalog uses one library database with `catalog_uuid`. Evaluation is an optional sidecar
created only by Evaluation workflows. Each `sonara_embeddings` row is bound to `track_id` and
`track_uuid`, stores exactly 48 little-endian `float32` values with `normalization = 'none'`, and
records `analyzed_at`. Each `sonara_fingerprints` row is bound to `track_id` and `track_uuid` and
stores `fingerprint_version`, native `fingerprint_base64`, and `analyzed_at`. Normal track reads
expose SONARA Core coverage and compact summaries. There is no Timeline route or optional SONARA
output selector.

Normal SONARA candidate selection checks all three current outputs and skips a track only when its
Core, embedding, and fingerprint rows are present for the current track identity. If any is missing,
one successful SONARA rerun writes all three rows together. The repository opens one transaction and
uses a savepoint per track, so that track's Core, embedding, and fingerprint are atomic while another
track's failure can be retained separately. Job diagnostics report staging, FFmpeg fallback,
copy/analyze/store timing, and per-track errors.

After a successful per-track store, or after a track failure is finalized, the staged runner updates
job status immediately instead of waiting for the whole queue. The existing UI Process Log receives
the normal track event with the original source path and track ID. A normal SONARA Direct or Staged
success is `Track analyzed`; its FFmpeg recovery is `[ffmpeg] Track analyzed`. A final failure
affects only that track. This behavior reuses the current analysis-event UI rather than adding a
separate staging component.

## Updating SONARA or stored fields

The project does not require a versioned schema or release contract before adopting a new SONARA
release. Adapt the source and database structure to the fields that the project should use, then run
focused compatibility checks.

Normal startup never changes an incompatible legacy layout. The explicit `dj-sim migrate-database`
command is the one-time conversion path after all SQLite users stop. It does not start analysis.
Reset or reanalyze only the outputs you choose to rebuild. Rhythm Lab profiles and labels remain
separate.

## Scoring boundary

Search, Evaluation diagnostics, Audio Dedup, and classifiers continue to use stored SONARA Core
values. The dedicated SONARA embedding and acoustic fingerprint are persisted but are not current
similarity, search, classifier, or Audio Dedup inputs. MERT, MuQ, MuQ-MuLan, MAEST, and CLAP remain
separate analysis sources. Every result is a ranking or diagnostic signal, not an automatic DJ decision.
