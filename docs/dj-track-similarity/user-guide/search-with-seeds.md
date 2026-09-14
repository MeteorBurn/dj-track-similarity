# Search with seed tracks

Seed search is useful when a real track communicates your intention better than tags or words. The
app compares stored analysis around that reference and returns candidates to audition. It does not
claim that the candidates will mix or belong in the same genre.

Use one seed for a focused neighborhood or several seeds for a blended target. The result is a
ranked listening list, not an automatic crate.

Control names below are given in English. The search tabs and most of their controls are already
English on screen. The full mapping to the on-screen strings is in
[UI language](../help/ui-language.md).

## Where seed search lives

Panel 3, search and listening, opens with a removable seed chip strip, then a four-tab strip. Tabs
are ordered `LAB`, `SIMILARITY`, `PROMPT`, `CLASS`, and the panel opens on `SIMILARITY` with SONARA
selected. Arrow keys, `Home`, and `End` move between tabs.

Two of those tabs take seeds:

| Selection | Endpoint | What it compares |
| --- | --- | --- |
| `SIMILARITY` with SONARA | `POST /api/search/sonara` | stored SONARA Core feature rows |
| `SIMILARITY` with an embedding model | `POST /api/search` | one selected embedding family |
| `LAB` | `POST /api/reference/compare` | six families side by side for the first seed |

Direct clients can also call `POST /api/search` with `analysis_family: "clap"`. CLAP has no browser
seed-search entry, though `LAB` shows it. Request fields, limits, and response identity are
documented in the [API reference](../reference/api.md).

## Choose seeds

In the library list, press the magnifier icon on a row, titled `Seed`. Selected seeds appear as
chips above the tab strip, each removable through its own **Remove that seed** tooltip. The API
accepts one to five seeds, and a request outside that range is refused with a message asking for 1
to 5 unique seed tracks.

The `SIMILARITY` tab also carries an **Add Random Track** button. It pulls one eligible track from
the library and adds it as a seed. With SONARA selected, it calls
`POST /api/search/sonara/random-track` and needs current SONARA features. With an embedding model
selected, it calls `POST /api/search/random-track` and needs a current embedding in that family.
Use it to start exploring with nothing particular in mind.

## Choose the kind of neighborhood

| Use | When it helps | What you can change |
| --- | --- | --- |
| `SIMILARITY` with SONARA | You know which audible qualities should stay close or move | Mixer weights, directional modifiers, and `Limit` |
| `SIMILARITY` with MAEST | You want to search the MAEST embedding space | `Limit` |
| `SIMILARITY` with MERT | You want a broad learned audio neighborhood with few decisions | `Limit` |
| `SIMILARITY` with MuQ | You want a second generic acoustic embedding neighborhood | `Limit` |
| `SIMILARITY` with MuQ-MuLan | You want a music-text-aligned audio neighborhood without mixing it into another family | `Limit` |
| `LAB` | You want to hear how separate model families disagree | Model columns, `Limit`, and listening verdicts |

The embedding families ask the quicker question: what is near these tracks in this model's audio
space? SONARA asks the more explicit one: what is near them according to the qualities I care about
now?

## SIMILARITY tab

The `Model` select offers `SONARA`, `MAEST`, `MERT`, `MuQ`, and `MuQ-MuLan`, starting on SONARA.
It shares a row with **Add Random Track** and `Limit`. A short description below explains what the
selected model compares. Selecting SONARA reveals its mixer and modifiers; selecting an embedding
model hides those controls while preserving their values.

`Limit` controls the maximum result count, `1..500`, and is shared with the `PROMPT` tab. The
browser ranks every returned candidate by score, from highest to lowest, and applies no
minimum-similarity threshold.

When the selected model has no current analysis, both its search and its random-track button are
disabled with a model-specific reason. Request errors remain visible instead of looking like an
empty successful result. The search button is also disabled while no seed is selected.

### Embedding models

MAEST, MERT, MuQ, and MuQ-MuLan call `/api/search` with the selected seed IDs and
`analysis_family`. Search compares only exact-current stored embeddings for that family. The query
vector is the L2-normalized mean of the seed rows, and the seeds themselves are excluded from the
results. Scoring is exact cosine similarity over a NumPy matrix, with no approximate index anywhere
in the project.

When BPM filtering is applied, embedding search resolves current SONARA tempo evidence first. Below
`0.45` confidence, it also checks ranked SONARA candidates and the Mutagen BPM tag. Unreliable tempo
does not become a hard rejection after those alternatives are checked.

## SONARA settings

Select SONARA in the `SIMILARITY` tab to search stored SONARA Core feature rows through
`/api/search/sonara`. Its mixer and modifiers are always active, so you can directly set the
importance of rhythm, timbre, level and energy, harmonic color, and tempo compatibility before
pressing `Search`.

### Mixer weights

The `Mixer` block is introduced on screen as a note saying it decides which kinds of similarity
come first. Each slider runs `0` to `5` in steps of `0.05` and shows `Off` at zero.

| Slider | Default | What it weighs |
| --- | ---: | --- |
| `Timbre` | `1.00` | spectral texture and MFCC-related features |
| `Rhythm` | `1.00` | onset density, danceability, and related rhythm signals |
| `Dynamics` | `0.80` | energy, RMS, LUFS, loudness range, and momentary loudness |
| `Harmonic` | `0.80` | chroma, dissonance, chord movement, and graduated Camelot compatibility |
| `Tempo` | `0.35` | BPM compatibility, including half and double tempo logic |

Key confidence only weakens harmonic evidence the analyzer is unsure about. It is not scored as a
similarity value.
Tempo confidence changes the strength of this evidence, not the similarity question. The exact
neutralization and candidate rules are in the
[SONARA integration reference](../reference/sonara-integration.md).

Each mixer field is normalized against a library-scoped percentile band computed over the candidate
set of the request, so a single outlier cannot dominate a dimension. Vector fields split
their weight across their components for the same reason.

### Modifiers

The `Modifiers` block is introduced as a note saying they steer the character of the results. Each
slider runs `-1` to `+1` in steps of `0.05`, starts at `0.00`, and carries its own `Off` reset
button. A value of `0` does not pull in either direction.

| Slider | Steers |
| --- | --- |
| `Energy` | how active the track feels |
| `Valence` | emotional tone, darker against brighter |
| `Aggression` | hardness and tension |
| `Vocal` | audible presence of a voice |
| `Acoustic` | organic instruments against synthetic sound |
| `Bright` | perceived high-frequency content |
| `Density` | how densely the track is filled with hits and detail, which is separate from BPM |
| `Range` | how noticeable the internal contrasts are, which is separate from total loudness |
| `LUFS` | mastering loudness |

A field driven by an active modifier is excluded from group similarity, so the two do not cancel
each other. `Aggression` is the only confidence-attenuated modifier: SONARA's own evidence
confidence pulls it toward neutral, and it is skipped entirely when that confidence is missing. It
does not turn weak evidence into a low-aggression verdict.

A `Reset` button beside the `Mixer` heading, titled **Reset the SONARA mixer and modifiers**,
returns both blocks to their defaults.

## LAB tab

The `LAB` tab opens `Model Listening Lab`. It compares how CLAP, MERT, MuQ, MuQ-MuLan, MAEST, and
SONARA rank candidates for the **first** selected seed, in six separate groups. Use it as a
diagnostic listening view rather than a ranked answer.

With no seed selected it shows `Select one seed track to compare model ears.` With one, the subline
reads `Reference: <track>`.

Controls:

- `Limit`: candidates per model, `1..100`, starting at `10`. This value is local to `LAB` and does
  not follow the shared `Limit` used by the other tabs.
- `Compare models`: calls `/api/reference/compare` for the first seed.
- Per-candidate `Notes`, a free-text field of up to 1000 characters.
- Verdict buttons `Mood`, `Palette`, `Instruments`, `Groove`, `Genre`, `Transition`, and `Miss`.

Each model stays in its own column so you can compare the model ears directly instead of flattening
them into one score. A family that cannot answer stays in the response with `available=false` and its
own reason, such as a seed missing that embedding or missing SONARA features.

Verdicts are stored as local pair feedback with a `reference_compare:<model>` source. They are
listening notes for later review and calibration. They do not retag audio files or change the ranked
results immediately. Each write carries the current `catalog_uuid` and `track_uuid`.

## Review results

The result list carries a provenance header naming its origin, such as `SONARA results` or `MERT
results`, plus the count. For the `SIMILARITY` tab that header names the model, not the tab.

Each result row shows a 1-based index, a preview button, the track's file name without its
extension, an optional reason chip, and a score meter with the score to three decimals. The row
currently previewing replaces its meter with a seek slider.

Hovering the meter, the score, or the reason chip shows a breakdown: one line per score component,
SONARA group contributions prefixed `sonara`, classifier values prefixed `classifier`, and, when a
transition is present, its confidence, key relation, and BPM delta.

Rows support preview, likes, metadata, seed actions, and current-set actions. Your useful output is
the handful of candidates that survive listening. Treat the score as a ranking hint. A candidate
with a lower score can still be the better mix.

Scores from different families are different scales. A MERT cosine, a SONARA Core score, a CLAP text
contrast, and a classifier probability answer different questions and cannot be compared with one
another.

## When results are empty

- Confirm the selected model family was analyzed. The empty state reads
  `No current MERT results matched this request.`
- Increase `Limit`.
- Use fewer or clearer seeds.
- Check that the database path in the UI is the database you analyzed.
- In `LAB`, a model can be unavailable for the seed if that seed is missing the matching embedding
  or SONARA features.
