# MAEST structure-aware window selection design

## Goal

MAEST genre analysis must sample up to three representative 30-second windows
without wasting inference on near-duplicate positions or routinely sampling
leading silence, DJ intros, outros, or trailing silence.

The selection should combine:

- the existing SONARA Core structure fields when a current SONARA row exists;
- evenly distributed window centers at 20%, 50%, and 80% of the selected
  content range;
- deterministic fallback behavior when the stored structure boundaries are
  absent or too close together.

Genre score aggregation, checkpoint selection, embedding extraction, audio-file
safety, and source precision remain unchanged.

## Scope

This change affects only the MAEST per-track audio-window selection and the
read-only data passed to that selector.

It uses these already-persisted SONARA Core fields:

- `leading_silence_seconds`
- `trailing_silence_seconds`
- `intro_end_seconds`
- `outro_start_seconds`

It does not:

- persist or consume SONARA `energy_curve` samples or `segments`;
- add or migrate database columns;
- change MAEST top-K selection or mean score aggregation;
- round model scores or embeddings;
- modify source audio or tags.

## Window context

Add a small immutable MAEST window-context value carrying optional leading
silence, trailing silence, intro end, and outro start values.

`AnalysisCandidate` carries this optional context. Candidate collection obtains
it with a left join to the current-generation SONARA row. A stale SONARA row
must never supply window context.

The context remains optional at the adapter boundary so:

- tests and non-MAEST callers can construct candidates without structure data;
- a current SONARA row whose structure values are absent can still use the
  full-duration window fallback.

No model other than MAEST consumes the context.

Project ML jobs have a stronger eligibility rule than the adapter boundary.
MAEST, MERT, MuQ, and CLAP select only tracks with a valid SONARA Core result
for the same current `content_generation`. A stale, missing, or invalid SONARA
row excludes the track from every ML job.

No ML or promoted-classifier job can start until the current catalog contains
at least one valid current-generation SONARA result. A pipeline that includes
the SONARA stage may bootstrap an empty catalog because the gate is checked
when each later stage starts.

## Range selection

For decoded duration `D` and MAEST window duration `W = 30 seconds`, sanitize
all optional boundary values as finite seconds clamped to `0..D`.

The hard content range removes edge silence:

```text
hard_start = leading_silence, otherwise 0
hard_end   = D - trailing_silence, otherwise D
```

The preferred main range additionally excludes the detected intro and outro:

```text
main_start = max(hard_start, intro_end when present)
main_end   = min(hard_end, outro_start when present)
```

Choose the first range in this order whose duration is at least `W`:

1. preferred main range;
2. hard non-silent range;
3. full decoded range.

This makes silence the stronger signal while treating SONARA intro/outro
boundaries as soft heuristics. Invalid, reversed, non-finite, or insufficient
ranges are ignored rather than failing the track.

If the decoded track is shorter than `W`, keep the existing behavior: analyze
one window from zero and right-pad it to 30 seconds.

## Start calculation

Within the selected range `[range_start, range_end]`, use fractional center
positions `(0.2, 0.5, 0.8)`.

For each position:

```text
center = range_start + position * (range_end - range_start)
start  = clamp(center - W / 2, range_start, range_end - W)
```

Keep starts in chronological order. Remove a start when it is within one second
of an already selected start, matching the current clamped-window
deduplication tolerance. The result therefore contains one to three windows.

When a current valid SONARA row has no structure boundaries, or when the
adapter is called directly outside a project ML job, this becomes ordinary
centered 20%/50%/80% sampling over the full decoded duration. It replaces the
current `60 seconds / 38% / 72%` start policy, whose first two windows overlap
heavily on common three-minute tracks.

## Data flow

1. Candidate collection excludes tracks without current-generation SONARA and
   reads optional structure boundaries from the matching row.
2. Shared audio decoding remains unchanged and still occurs once per ML batch
   item.
3. `MaestModelRunner` passes the per-item optional contexts alongside decoded
   audio to `MaestGenreAdapter`.
4. The adapter calculates starts independently for each decoded track,
   resamples to 16 kHz, slices or pads the 30-second windows, and batches the
   resulting tensors as it does today.
5. Per-label sigmoid scores are averaged across that track's selected windows
   before top-K selection.
6. The 768-dimensional MAEST embeddings are averaged across the same selected
   windows and L2-normalized as they are today.

SONARA and ML remain separate analysis stages. The fixed pipeline order
SONARA → ML lets a full pipeline establish the prerequisite before ML starts.
An explicit MAEST-only project job is rejected while the catalog has no
current SONARA results and skips individual tracks without current SONARA.

## Runtime metadata

MAEST runtime parameters should describe the new policy with:

- `analysis_window_positions = (0.2, 0.5, 0.8)`
- `window_selection = structure-aware-main-range-centered-20-50-80`
- `window_context = sonara-current-generation-optional`
- `window_fallback = main-range->non-silent-range->full-duration`
- `window_dedup_tolerance_seconds = 1.0`

Legacy parameter names that describe `60 seconds / 38% / 72%` must not remain
as the reported active policy.

Per-track offsets are deterministic from decoded duration and the stored
SONARA values. Persisting a second copy of those offsets would require a schema
change and is outside this initial scope.

## Error handling

- Missing or stale SONARA excludes a track from project ML jobs.
- Zero current SONARA coverage rejects ML and classifier job creation.
- Missing structure fields on an otherwise current SONARA row select the
  full-duration fallback.
- Non-finite, negative, out-of-duration, or reversed boundaries are ignored or
  clamped without failing MAEST.
- If the preferred range is shorter than 30 seconds, relax intro/outro first.
- If the non-silent range is also shorter than 30 seconds, use the full track.
- Existing model, decode, resample, inference, and repository errors retain
  their current per-track handling.

## Compatibility

The current project database has zero MAEST analysis rows and zero MAEST
embeddings, so adopting this policy does not require clearing existing MAEST
results in that database.

Other databases may already contain MAEST results. The current contract-free
readiness model does not invalidate them based on window policy. This change
does not automatically delete or recompute those rows.

## Verification

Focused tests must prove:

1. centered 20%/50%/80% starts for representative durations;
2. a current SONARA row supplies window context to the MAEST candidate;
3. a stale SONARA generation supplies no context;
4. leading and trailing silence constrain the hard range;
5. valid intro/outro values constrain the preferred range;
6. a short preferred range falls back to the non-silent range;
7. a short non-silent range falls back to the full duration;
8. missing and invalid hints do not fail analysis;
9. clamped starts within one second are deduplicated;
10. tracks no longer than 30 seconds still produce one padded window;
11. multi-track batches may use different starts without mixing their scores
    or embeddings;
12. score aggregation still averages all label scores before top-K selection;
13. MAEST embeddings remain finite, 768-dimensional, and L2-normalized;
14. every ML job filters out tracks without current-generation SONARA;
15. ML and classifier job creation is rejected at zero current SONARA
    coverage;
16. a pipeline with SONARA first can establish the prerequisite for later
    stages.

Run the smallest focused backend tests covering candidate collection, MAEST
window preparation, and MAEST model-runner persistence. No real project
database or source audio is used for automated verification.
