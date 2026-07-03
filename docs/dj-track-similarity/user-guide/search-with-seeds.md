# Search with seed tracks

> Audience: Users who have one or more reference tracks and want nearby candidates.
> Goal: Use MERT and SONARA search without confusing their scores.
> Type: guide

Seed search starts from tracks you select in the library. Use one seed for a close neighborhood or several seeds for a blended target.

## Choose seeds

In the library list, add tracks to the seed strip. The search panel uses the selected seed IDs for MERT, SONARA, SET, and Hybrid preview.

Hybrid and feedback endpoints accept one to five unique seeds. SET manual mode also expects one to five practical anchors because the artist guard and waypoint placement are built around a small seed set.

## MERT tab

MERT search calls `/api/search` with selected seed IDs. It compares stored MERT embeddings and returns scored candidates.

Use MERT when you want audio-to-audio similarity from learned embedding space. It is useful for timbral and musical neighborhood discovery, but it does not know your exact DJ intention.

Common controls:

- **Similarity**: minimum score threshold from `0.00` to `1.00`.
- **Limit**: maximum result count, `1..500`.

When BPM filtering is applied, MERT search resolves BPM from stored SONARA analysis first. It falls
back to the Mutagen BPM tag only when SONARA BPM is missing.

## SONARA tab

SONARA search calls `/api/search/sonara` and uses stored SONARA feature rows. It is useful when you want more explainable control over rhythm, timbre, level and energy, harmonic color, and tempo compatibility.

The mixer weights are:

- **Timbre**: spectral texture and MFCC-related features.
- **Rhythm**: onset density, danceability, and related rhythm signals.
- **Dynamics**: energy, RMS, loudness, and level range.
- **Harmonic**: chroma, dissonance, chord movement, and key confidence.
- **Tempo**: BPM compatibility, including half/double tempo logic.

Modifiers bias the result direction relative to the seed context: energy, valence, acousticness, brightness, rhythm density, level range, and loudness. A modifier value of `0` does not pull in either direction.

## Review results

Result rows support preview, likes, metadata, seed actions, and current-set actions. Treat the score as a ranking hint. A candidate with a lower score can still be the better mix.

## When results are empty

- Confirm the selected model family was analyzed.
- Lower the similarity threshold.
- Use fewer or clearer seeds.
- Check that the database path in the UI is the database you analyzed.
