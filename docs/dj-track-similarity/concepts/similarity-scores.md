# Read similarity scores as suggestions

Scores answer "which candidates should I inspect first under these settings?" They can tell you that
one candidate ranked ahead of another inside the same search. They cannot judge musical quality or
promise that a transition will work.

The practical output of a score is an audition order. Listen from the top, keep useful exceptions,
and stop when you have enough candidates.

This page owns the rules for keeping score spaces apart. Other pages link here.

## Eight scales that never mix

One search means one evidence source and one score space. The app produces eight distinct scales,
and a value from one says nothing about a value from another.

| Scale | Where it appears | What it measures |
| --- | --- | --- |
| SONARA Core similarity | SONARA tab, `/api/search/sonara` | weighted agreement across named audio features |
| ML seed cosine | SIMILARITY tab and LAB, one value per family | cosine between L2-normalized embeddings of one family |
| CLAP text contrast | PROMPT tab with CLAP selected | prompt vector against stored CLAP audio vectors |
| MuQ-MuLan text contrast | PROMPT tab with MuQ-MuLan selected | prompt vector against stored MuQ-MuLan audio vectors |
| Audio Dedup `min_similarity` | Audio Dedup embedding mode | content gate over MERT, MAEST, MuQ, and CLAP vectors |
| `fingerprint_similarity` | Audio Dedup reports | native SONARA acoustic fingerprint agreement, `0` to `1` |
| Transition risk | Evaluation transition diagnostics | weighted mean of mix-risk components |
| Classifier probability | CLASS filters | probability of a promoted classifier's positive label |

A threshold tuned on one of these is meaningless on another. The `0.45` fingerprint floor in Audio
Dedup and the `0.45` low-confidence tempo cutoff in SONARA share a number and nothing else.

Even inside one family, the question changes with the input. CLAP text search and CLAP seed search
read the same `clap_embeddings` table, and their scores are still separate: a text score is
prompt against audio, a seed score is audio against audio.

## ML seed search

The SIMILARITY tab searches one embedding family at a time over MAEST, MERT, MuQ, or MuQ-MuLan. The
query is the L2-normalized mean of the selected seed rows, the seeds are removed from the results,
and the score is a cosine over unit vectors. Values fall in `-1` to `1` in principle, and useful
neighborhoods sit well above zero in practice.

CLAP is available for seed search through the HTTP API and in LAB, without an entry in the browser
model selector.

## SONARA feature search

SONARA search compares stored feature values under mixer weights, with optional modifier bias on
top. It explains itself better than an embedding cosine, and it is still a similarity model.
Raising a mixer weight changes the ranking question rather than improving the answer.

### How a Custom score is assembled

Custom mode is the mode where every part is visible:

- Five mixer groups carry a weight from `0` to `5`: `Timbre` and `Rhythm` default to `1.0`,
  `Dynamics` and `Harmonic` to `0.8`, and `Tempo` to `0.35`.
- Each numeric dimension is normalized against a 2nd to 98th percentile band computed over the
  candidate set of that request. Values outside the band clamp to the edge, so one outlier track
  cannot flatten the scale.
- A vector field splits its weight across its components, so 13 MFCC values cannot outvote the rest
  of the timbre group.
- Nine modifiers run from `-1` to `1`. A modifier weight is `|direction| x 2.5`, and the field a
  modifier drives leaves the group similarity so the two do not cancel each other.
- `Aggression` is the one modifier attenuated by evidence confidence, and it drops out entirely when
  SONARA stored no aggression confidence for a candidate.
- A candidate is dropped when fewer than two numeric dimensions overlap with the seed.

Harmonic scoring uses Camelot compatibility attenuated by key confidence. Key confidence is a
reliability weight rather than a similarity dimension of its own. The harmonic group in Custom mode
uses lighter tonal weights than Balanced and DJ transition do.

### DJ transition adds a structural term

DJ transition mode blends the feature similarity with a directional structural fit:

```text
score = 0.8 x similarity + 0.2 x transition_fit
```

`transition_fit` compares the seed outro against the candidate intro, the two energy levels, and the
stored energy-curve summary. Missing parts are left out of the mean rather than counted as zero, so
a track with partial structure data is not penalized for the gap.

## Text search and the contrast score

With no negatives and a single positive prompt, the score is the cosine between the prompt vector
and each stored audio vector.

With a negative bank, the visible number is a contrast score:

```text
contrast = positive - negative_weight x mean(two highest negative cosines)
```

The negative term is the **mean of the two highest** negative similarities, not the single strongest
one. Asking a second negative prompt to agree before a track is pushed down measured better than
the maximum at every weight for both text models. A bank holding one negative collapses the two
terms into the same value, which reproduces the older behavior.

The default negative weight is `0.5`, and the API accepts `0` to `2`. A contrast score can go
negative and is not a probability. The result rows show the positive and negative parts separately
so you can see which side moved a track.

Rank fusion between CLAP and MuQ-MuLan was measured and rejected. The app never blends them, and the
preset picker reports a conflict rather than mixing two banks across models.

## Reference Compare scores

The LAB panel keeps CLAP, MERT, MuQ, MuQ-MuLan, MAEST, and SONARA in six separate groups for one
seed track. Compare scores within one model group first. A high MERT score, a high MuQ-MuLan score,
a high CLAP audio score, and a high SONARA score are related listening hints from four different
measurements.

Saved LAB verdicts are manual pair-feedback labels for a specific model source. They record what you
heard. They are not automatic truth labels and they do not rewrite the model score.

## Audio Dedup thresholds

Audio Dedup `min_similarity` is an audio-to-audio content gate over the enabled stored MERT, MAEST,
MuQ, and CLAP audio embeddings. MuQ-MuLan is not one of its sources. MuQ evidence alone does not
satisfy the separate safe-delete corroboration rules.

The `fingerprint_similarity` value in dedup reports is another separate scale. At `0.45` or above it
creates manual-review candidates and never authorizes deletion.

## Two ranking controls that do not change the score

The HTTP search API carries two filters with no browser control:

- `epsilon` keeps only candidates within that distance of the best score.
- `noise` from `0` to `1` adds a deterministic jitter derived from the catalog and track UUIDs. It
  perturbs the ranking order only, and the score returned in the response stays untouched. The same
  request returns the same order every time.

## Practical reading

- Compare scores inside the same tab and the same settings.
- Be careful after changing thresholds, weights, or prompts.
- Preview audio before adding to a set.
- Do not use one tab's threshold as another tab's safety rule.
- Use LAB when you want to compare model families by ear before trusting one for a reference track.

## Related pages

- [Features, embeddings, and tags](./features-embeddings-tags.md)
- [Search with seed tracks](../user-guide/search-with-seeds.md)
- [Text search](../user-guide/text-search.md)
