# Search with seed tracks

> Audience: Users who have one or more reference tracks and want nearby candidates.
> Goal: Use MERT, MuQ, SONARA, and Reference Compare search without confusing their scores.
> Type: guide

Seed search is useful when a real track communicates your intention better than tags or words. The
app compares stored analysis around that reference and returns candidates to audition. It does not
claim that the candidates will mix or belong in the same genre.

Use one seed for a focused neighborhood or several seeds for a blended target. The result is a
ranked listening list, not an automatic crate.

## Browser and API entry points

The browser provides MERT, MUQ, SONARA, and LAB tabs. Direct clients can use `POST /api/search` for
`maest`, `mert`, `muq`, or `clap` seed search, `POST /api/search/sonara` for SONARA, and
`POST /api/reference/compare` for per-model comparison. Request fields, limits, and response
identity are documented in the [API reference](../reference/api.md).

## Choose the kind of neighborhood

| Use | When it helps | What you can change |
| --- | --- | --- |
| MERT | You want a broad learned audio neighborhood with few decisions | Similarity threshold and result limit |
| MuQ | You want a second generic acoustic embedding neighborhood | Similarity threshold and result limit |
| SONARA | You know which audible qualities should stay close or move | Feature mode, mixer weights, and directional modifiers |
| LAB | You want to hear how separate model families disagree | Model columns, result limit, and listening verdicts |

MERT and MuQ ask the quicker question: "what is near these tracks in this model's audio space?"
SONARA asks the more explicit question: "what is near them according to the qualities I care about
now?"

## Choose seeds

In the library list, add tracks to the seed strip. The search panel uses the selected seed IDs for
MERT, MuQ, SONARA, SET, Hybrid preview, and the LAB Reference Compare panel.

Hybrid and feedback endpoints accept one to five unique seeds. SET manual mode also expects one to five practical anchors because the artist guard and waypoint placement are built around a small seed set.

## MERT and MUQ tabs

Both tabs call `/api/search` with selected seed IDs and the matching `analysis_family`. They compare
only exact-current stored embeddings for that family and return scored candidates.

Use MERT or MuQ when you want audio-to-audio similarity from a learned embedding space. MERT is a
broad musical representation. MuQ adds a separate generic acoustic view. Neither knows your exact
DJ intention, and their scores are not one shared scale.

Common controls:

- **Similarity**: minimum score threshold from `0.00` to `1.00`.
- **Limit**: maximum result count, `1..500`.

When a tab has zero current embeddings, its search action is disabled with a source-specific
reason. Request errors remain visible instead of looking like an empty successful result.

When BPM filtering is applied, embedding search resolves current SONARA tempo evidence first. At low
confidence, it also checks ranked SONARA candidates and the Mutagen BPM tag. Unreliable tempo does
not become a hard rejection after those alternatives are checked.

## SONARA tab

SONARA search calls `/api/search/sonara` and uses stored SONARA feature rows. It is useful when you want more explainable control over rhythm, timbre, level and energy, harmonic color, and tempo compatibility.

Use **Mode** first:

- **Balanced** blends broad vibe, sound, tempo, and light harmonic agreement.
- **Vibe** emphasizes energy, danceability, valence, acousticness, and broad dynamics.
- **Sound** emphasizes timbre, MFCC, and spectral texture.
- **DJ transition** emphasizes BPM, onset density, energy, danceability, and tonal compatibility.
- **Custom mixer** enables the visible mixer weights and directional modifiers.

The mixer weights are:

- **Timbre**: spectral texture and MFCC-related features.
- **Rhythm**: onset density, danceability, and related rhythm signals.
- **Dynamics**: energy, RMS, LUFS, SONARA 2.0 loudness range, and momentary loudness.
- **Harmonic**: chroma, dissonance, chord movement, and graduated SONARA Camelot compatibility.
  Key confidence only weakens uncertain harmonic evidence. It is not scored as a similarity value.
- **Tempo**: BPM compatibility, including half/double tempo logic.

Tempo confidence changes the strength of this evidence, not the similarity question. The exact
neutralization and candidate rules are in the
[SONARA v0.3.1 project contract](../reference/sonara-v0-3-1-contract.md).

Modifiers bias the result direction relative to the seed context: energy, valence, acousticness, brightness, rhythm density, level range, loudness, and SONARA 2.0 vocalness. A modifier value of `0` does not pull in either direction.

## LAB tab

The LAB tab opens **Model Listening Lab**. It compares how CLAP, MERT, MuQ, MAEST, and SONARA rank candidates for the first selected seed track. Use it as a diagnostic listening view for separate model groups.

Use it when one reference track feels important and you want to hear which model family is finding useful neighbors. Each model stays in its own column so you can compare the model ears directly instead of flattening them into one score.

Common controls:

- **Limit**: candidates per model, `1..100`.
- **Compare models**: calls `/api/reference/compare` for the first seed.
- **Verdict buttons**: save listening notes for a candidate and model as `mood`, `palette`, `instruments`, `groove`, `genre`, `transition`, or `miss`.

Verdicts are stored as local pair feedback with a `reference_compare:<model>` source. They are listening notes for later review and calibration. They do not retag audio files or change the ranked results immediately.
Each write carries the current `catalog_uuid`, `track_uuid`, and `content_generation`. An unavailable
model stays in the comparison with its own reason instead of silently disappearing.

## Review results

Result rows support preview, likes, metadata, seed actions, and current-set actions. Your useful
output is the handful of candidates that survive listening. Treat the score as a ranking hint. A
candidate with a lower score can still be the better mix.

## When results are empty

- Confirm the selected model family was analyzed.
- Lower the similarity threshold.
- Use fewer or clearer seeds.
- Check that the database path in the UI is the database you analyzed.
- In LAB, a model can be unavailable for the seed if that seed is missing the matching embedding or SONARA features.
