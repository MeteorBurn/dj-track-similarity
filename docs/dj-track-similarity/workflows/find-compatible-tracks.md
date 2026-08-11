# Find compatible tracks around a reference

> Audience: Users who have one track and want candidates nearby.
> Goal: Use seed and feature search with clear fallback steps.
> Type: workflow

Here, "compatible" means worth auditioning next to the reference under the search question you
choose. It does not mean guaranteed harmonic, rhythmic, or stylistic compatibility.

The useful result is a manageable list of alternatives and adjacent ideas. Export the list as a
crate, reuse useful tracks as new seeds, or add the strongest candidates to the current set.

## Steps

1. Search the library for the reference track.
2. Add it as a seed.
3. Run **MERT search** for embedding-near candidates.
4. Run **SONARA search** when you want more control over rhythm, timbre, dynamics, harmonic color, or tempo.
5. Increase **Limit** if you want to hear more lower-ranked candidates.
6. Preview candidates before adding them to the current set.
7. Add good candidates to the set or save them into a crate/export.

## When one seed is too narrow

Add a second or third seed that represents the intended direction. Do not add unrelated seeds just to get more results. That makes the target less clear.

## Tempo note

Tempo-aware search starts with current SONARA evidence. Below `0.45` confidence, it inspects
ranked SONARA candidates and the Mutagen BPM tag. Grid stability can weaken the evidence, and low
reliability moves the score toward neutral rather than creating a bonus or automatic rejection.

## Output

Keep a small result in the current set while you compare by ear. For a reusable review list, export
CSV. For a player or DJ app, export M3U and verify that the paths work on the target machine.
