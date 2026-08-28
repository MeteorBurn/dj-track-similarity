# Classifiers and Rhythm Lab

Most analysis models arrive with their own general audio representation. A personal classifier asks
a different question: "can the app reuse a distinction that I make repeatedly?"

One possible profile separates vocal-forward tracks from mostly instrumental tracks. Another could
focus on whether live instrumentation is present. The definition and examples come from your
library. New databases begin without profiles, and the resulting score reflects your labels.

## Why train one

A classifier is useful when a concept:

- matters repeatedly across your library,
- is not captured reliably by existing tags,
- is specific enough that you can label consistent examples,
- should become a filter or a gentle preference rather than a one-time search.

If you only need a list for one session, seed search or CLAP text search is usually less work.

## From examples to a useful control

```text
label examples -> train -> review predictions -> promote -> score library -> filter or steer
```

Promotion does not make the model silently choose music for you. It makes one reviewed profile
available as a score in the main app. Missing and borderline cases still need listening.

Rhythm Lab is the companion tool for local labels, training, prediction review, and promotion.
Promoted classifiers become optional signals in the main UI.

## Profiles

Rhythm Lab supports two profile types:

- **binary**: one positive label and one negative label, plus optional review labels,
- **multiclass**: class labels where one track has one current class label for the active profile.

Labels, predictions, queues, and training checkpoints live in `tools/rhythm-lab/database/rhythm_lab.sqlite` by default. Profile training data lives under `tools/rhythm-lab/profiles/<profile-key>/`.

Rhythm Lab does not create a built-in starter profile. Existing profiles, including older Break Energy profiles, remain normal profile rows in the labels database, but new labels databases start empty until you create a profile.

## Training inputs

Training uses the feature families declared by the selected profile artifact. A recipe that uses
SONARA, MERT, and MAEST requires their current outputs; a feature set that includes CLAP also
requires stored CLAP audio embeddings.

MuQ and MuQ-MuLan are normal embedding feature sources. The `muq` and `mulan` sets emit ordered
`muq:<index>` and `mulan:<index>` features from the dimension expected by the current feature
recipe. They can be combined with other sources, such as `sonara+muq`, `mert+muq`, or
`sonara+mert+maest+clap+muq`. The default training recipe is the six-source
`sonara+mert+maest+clap+muq+mulan`, so MuQ-MuLan is part of default training. Missing
required values make a track ineligible. Required values are not zero-imputed.

SONARA inputs must provide the ordered feature recipe selected for training. A row missing a
requested opt-in field is skipped rather than zero-imputed.

The `sonara` feature source deliberately leaves out `vocal_probability` and the entire aggression
family. The stated reason is to keep the classifier baseline independent of SONARA's own bundled
learned outputs. Those values remain available for inspection and for Custom search, and they never
enter a training recipe.

## Promotion

Promotion publishes one artifact pair, `model.joblib` and `model.json`, into
`models/classifiers/<artifact-prefix>/`. The layout is flat. One directory holds one current
artifact per prefix, and promoting again replaces that pair.

The write is staged rather than in place. Promotion first writes both files into a temporary
`.staging-<uuid>` directory and fsyncs them. It fences both SHA-256 hashes, then exercises the
staged classifier through the production scorer on a zero vector. Only after that does the live pair
change: `model.json` is marked `publication_status: "publishing"`, `model.joblib` is replaced, and
`model.json` is replaced with the `ready` manifest. A pair caught half-published refuses to load.

Two gates decide whether a promotion is allowed at all:

- The artifact's `source_catalog_uuid` must equal the active library's `catalog_uuid`. An artifact
  trained against another library is refused.
- Calibration is required by default. Promoting an uncalibrated artifact takes an explicit opt-out.

Each promoted artifact records its exact ordered feature names and required inputs, including the
vector dimension for `muq:<index>` and `mulan:<index>` features. An incomplete or changed recipe is
blocked from scoring until that profile is retrained and promoted.

## Scoring

Promoted classifier scoring is database-only. Each manifest identifies the exact current SONARA and
MERT/MAEST/CLAP/MuQ/MuQ-MuLan inputs it needs. The aggregate job writes `classifier_scores` for every
selected compatible classifier-track pair without reading audio.

A track missing any required input is excluded by the candidate query before the job total is
formed, so it is reported as neither scored nor failed. Incompatible promoted artifacts stay visible
with a retrain and promote blocker, and they are never executed.

### Scoring is incremental and never re-scores

The candidate query skips every track that already holds a row for that `classifier_key`. There is
no staleness column, no `model_id`, and no automatic invalidation. A promoted artifact can change
underneath existing scores without the app noticing.

The practical consequence: reset a key before you rescore it. Retrain, promote, reset, then score.
Skip the reset and the scoring job finds zero work while reporting success.

Adding or promoting one classifier does not delete scores for other keys.

### A SONARA reset leaves classifier scores in place

Resetting SONARA deletes `sonara_features` rows and reports zero classifier rows deleted. The
classifier scores survive, so a library can carry scores computed from Core rows that no longer
exist. Nothing flags them. Reset the affected classifier keys yourself after a SONARA reset if you
want those scores rebuilt.

The one-time `dj-sim migrate-database` command only converts the former split Core/Artifacts layout;
it is not a general SONARA-schema migration. For a SONARA update, reanalysis, retraining, promotion,
and rescoring remain separate deliberate choices for affected profiles.
Labels, feedback, and unrelated artifacts remain available.

## Current UI status

The static Rhythm Lab UI shows current/missing/stale state for every source and provides a
**Training recipe** selector for any supported source combination. Use
`benchmark-ablation` with explicit `--feature-set` values when you need a repeatable CLI matrix.

The main frontend lists promoted profiles in CLASS and serializes minimum-score filters. It also
exposes per-profile reset plus rescore, while missing scores do not satisfy that profile's filter.
Malformed manifests stay visible but block scoring with a clear status.
