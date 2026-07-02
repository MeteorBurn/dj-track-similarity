# Find compatible tracks around a reference

> Audience: Users who have one track and want candidates nearby.
> Goal: Use seed and feature search with clear fallback steps.
> Type: workflow

## Steps

1. Search the library for the reference track.
2. Add it as a seed.
3. Run **MERT search** for embedding-near candidates.
4. Run **SONARA search** when you want more control over rhythm, timbre, dynamics, harmonic color, or tempo.
5. Lower similarity thresholds if results are too narrow.
6. Preview candidates before adding them to the current set.
7. Add good candidates to the set or save them into a crate/export.

## When one seed is too narrow

Add a second or third seed that represents the intended direction. Do not add unrelated seeds just to get more results. That makes the target less clear.

## Tempo note

SONARA tempo weighting uses compatibility logic that can handle half/double relationships. SET BPM trajectory is separate: use it only when you want the actual order to move toward a BPM target.

## Output

For a reusable list, export CSV. For a player or DJ app, export M3U and verify the paths work on the target machine.
