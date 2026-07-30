# SONARA Model Output Group Order Design

## Scope

Change only the grouping and ordering of SONARA Core fields in the track
metadata dialog. Do not change SONARA analysis, stored values, database
columns, API fields, or value formatting.

## Grouping

Keep `Mood` exclusively for SONARA's four heuristic mood affinities:

- `Happy`
- `Aggressive`
- `Relaxed`
- `Sad`

Remove `Vocal Probability` from `Mood`. Add a separate `Vocalness` group
containing only `Vocal Probability`, which is backed by the bundled
`sonara-vocalness-v2` model in the application's current SONARA configuration.

Keep the existing `Aggression` group and its fields unchanged:

- `Score`
- `Evidence support`
- `Forcefulness`
- `Harshness`
- `Tension`
- `Rhythm`

## Order

Place the two model-backed groups immediately before `Vector summaries`:

1. `Spectral`
2. `Vocalness`
3. `Aggression`
4. `Vector summaries`

All other SONARA Core groups retain their existing relative order.

## Verification

Update the focused metadata-reference test first and confirm it fails under
the current grouping. The test must prove that:

- `Mood` does not contain `vocal_probability`;
- the mood heuristic keeps the UI label `Aggressive`;
- `Vocalness` contains `vocal_probability`;
- `Vocalness` and `Aggression` immediately precede `Vector summaries` in that
  order;
- existing vocal-probability and aggression formatting remains unchanged.

Then make the smallest corresponding change in `TrackMetadataDialog.tsx` and
run the focused frontend test plus TypeScript type checking.
