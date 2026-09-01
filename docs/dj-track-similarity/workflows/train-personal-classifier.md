# Train a personal classifier

Train a classifier when you repeatedly sort tracks by a personal concept that metadata and one-off
searches do not express well. You define the concept and provide examples. Rhythm Lab learns a
local boundary from those labels, and the main app can later score compatible tracks against it.

A binary profile could separate "vocal-forward" from "mostly instrumental" tracks. Another profile
could focus on the presence or absence of a kind of live instrumentation. You define these profiles.
A new Rhythm Lab database does not contain them automatically.

## When this is worth doing

Use a classifier when:

- the same judgment matters across many searches or sets,
- reliable tags do not already answer it,
- you can label clear positive and negative or multiclass examples,
- you are willing to review mistakes and ambiguous tracks.

Use seed search, SONARA search, or the `PROMPT` tab instead when the question is temporary or you
only need one shortlist. Training adds maintenance: a weak or narrow label set produces a weak or
narrow score.

## What the finished workflow produces

```text
your labels -> trained candidate -> promoted profile -> per-track scores -> CLASS
```

The final score is not a tag written into the audio and not an objective truth. It is a reusable
ranking signal for one profile. The score can filter the library through the
[CLASS tab](../user-guide/class-tab.md).

Rhythm Lab is the classifier workspace. It uses the main SQLite library as source context and keeps
labels, predictions, queues, and checkpoints in its own labels database. The only write it makes
back into the source library is the liked-track toggle.

## 1. Prepare source analysis

For a recipe that uses SONARA, MERT, and MAEST, run those analyses first:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert --db .\data\library.sqlite
```

If a selected feature set contains MuQ, MuQ-MuLan, or CLAP, store the current embedding for that
family first:

```powershell
dj-sim analyze --models muq,mulan,clap --db .\data\library.sqlite
```

The `sonara` feature source contributes 74 values, made of 19 core scalars, 19 current extras, 4
mood scalars, MFCC (13), chroma (12), and spectral contrast (7). `vocalness` and the whole aggression
family are excluded by design, to keep the baseline independent of SONARA's bundled learned outputs.

The `timeline`, `embedding`, and `fingerprint` SONARA outputs are not classifier inputs. A
SONARA-dependent artifact records the ordered Core feature names it uses. A track missing any
requested value is skipped entirely rather than zero-imputed.

## 2. Start Rhythm Lab

Choose the database in the main app and press the flask icon in the top bar, titled **Start Rhythm
Lab**, or **Open Rhythm Lab** when it is already running; its on-screen string is in
[UI language](../help/ui-language.md). The app starts or reuses the local Lab process and opens its
URL. You can also start it directly:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

Reuse requires a matching catalog binding, so a Lab process bound to another library is not reused
for this one.

## 3. Pick profile type

- Binary profiles use one positive and one negative training label.
- Multiclass profiles use class labels, and one track can hold only one current class label for the active profile.

Choose labels that answer one clear question. For a binary profile, positive should mean "this is the
concept" and negative should mean "this is not the concept." Avoid assigning a clean label while you
are unsure about a track. Use review labels and queues to keep borderline tracks visible without
turning them into training labels too early.

## 4. Train

Use Library, Collection, or Candidates to collect enough training labels for the active profile. New
profiles start from Library or Collection labeling. Candidate review becomes useful after the first
trained artifact exists.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

Training needs at least 4 labelled rows and at least 2 per label. The pipeline is a standard scaler,
a per-source column transformer, and a balanced logistic regression. Metrics are written beside the
artifact as a `.metrics.json` file holding the classification report, the confusion matrix, the
positive-discovery threshold and top-N tables, a stratified cross-validation, and the production
calibration report.

In the Training tab, `Train` retrains from all current labels and refreshes candidates
automatically. `Calibrate` refits the selected binary variant once the label gate is met.

CLI and UI training default to `sonara+mert+maest+clap+muq+mulan`, which combines all six feature
sources. Its dimensionality is 3658. The `Training recipe` selector also exposes individual sources
and supported combinations, such as the five-source `sonara+mert+maest+clap+muq`. Readiness is
calculated from labels that have every current output required by the selected recipe.

After training, listen to high-scoring, low-scoring, and borderline candidates. Useful mistakes
often reveal that the concept or the label set needs refinement before promotion.

## 5. Benchmark variants

Run a benchmark when you want to compare feature-source variants for the active profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\profiles\live-instrumentation\ablation.json
```

The Training tab benchmarks all 63 non-empty combinations of SONARA, MERT, MAEST, CLAP, MuQ, and
MuQ-MuLan, then identifies the best trained variant for the active profile before promotion.

For any other combination, repeat the CLI option:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite --profile live_instrumentation --feature-set muq --feature-set sonara+muq --output tools\rhythm-lab\profiles\live-instrumentation\ablation-muq.json
```

## 6. Calibration

Calibration turns the raw classifier score into a positive-label probability, and promotion requires
it by default.

Calibration is data-gated. Binary profiles need at least 100 training labels, 20 positive labels, and
20 negative labels. Multiclass profiles are not calibrated. If the gate is not satisfied, the
artifact stays uncalibrated and records the reason in its calibration report, which then blocks
promotion unless you pass the experimental override.

Calibrate the normal training command:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite --calibrate
```

Calibrate benchmark winners after an ablation run:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite --profile live_instrumentation --calibrate-finalists --output tools\rhythm-lab\profiles\live-instrumentation\ablation-calibrated.json
```

Calibrate one selected feature set through the Rhythm Lab API:

```text
POST http://127.0.0.1:8777/api/profiles/live_instrumentation/training/calibrate
{"feature_set": "mert+maest"}
```

Use `calibration-report` to inspect the selected artifact before promotion:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

It reports Brier score, expected calibration error over 10 bins, ROC-AUC, average precision, F1 at
0.5, and the precision-80 and recall-80 thresholds.

## 7. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

Two gates apply before anything is written.

**Calibration is required by default.** The CLI computes its requirement as
`--require-calibration or not --allow-uncalibrated`, so a plain `promote` demands a calibrated
artifact. An uncalibrated one fails with
`Artifact calibration is required but not available: <reason>`. Pass `--allow-uncalibrated` to opt
into an experimental uncalibrated promotion, which records `allowed_uncalibrated` in the manifest.
The `--require-calibration` flag makes the default intent explicit:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set 'mert+maest' --require-calibration --source .\data\library.sqlite --labels tools\rhythm-lab\database\rhythm_lab.sqlite
```

**The artifact is bound to one source catalog.** `--source` is required, and promotion compares the
artifact's `source_catalog_uuid` against that database's `catalog_uuid`. A mismatch fails with
`Artifact source catalog <a> does not match active catalog <b>`, and an artifact carrying no binding
at all fails with `Artifact is not bound to a source catalog UUID`. Train against the library you
intend to score.

`--feature-set` selects which recipe to promote and defaults to
`sonara+mert+maest+clap+muq+mulan`.

Promotion writes a flat pair of files:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Publication is atomic. The pair is staged and fsynced under a temporary directory, both hashes are
fenced, the staged classifier is exercised through the production scorer on a zero vector, then
`model.json` flips to `publication_status: "publishing"`, `model.joblib` is replaced, and
`model.json` is replaced with the `ready` manifest. There is no generation directory and no pointer
file to switch.

## 8. Score through the current backend

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

**Scoring is incremental and never re-scores.** The candidate query excludes every track that
already carries a row for that classifier key. After retraining and promoting the same key, a plain
rescore finds zero work and the old scores stay in place. Reset the key first:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/classifiers/reset -Method Post -ContentType 'application/json' -Body '{"classifier_key":"live_instrumentation"}'
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

The payload field is `classifier_key`, singular, and the contract rejects unknown fields. The play
button on a `CLASS` row does both steps in one press, which is the reason it is labelled
`Reset and rescore all <name> classifier results`.

After a SONARA feature revision, dependent main-library scores and Rhythm Lab predictions are
invalidated while labels and feedback remain. Reanalyze SONARA, then retrain and promote the affected
profiles. A promoted artifact with a mismatched ordered feature recipe cannot score current tracks.

Use [Reanalyze SONARA data](./reanalyze-sonara-split-storage.md) when the source analysis update
changes stored structure or the classifier's feature recipe.

A promoted artifact may declare ordered `muq:<index>` or `mulan:<index>` features and the expected
vector dimension for each family. Backend scoring loads those values from SQLite without decoding
audio. A profile whose ordered feature recipe no longer matches must be retrained and promoted.

## Safety

Rhythm Lab labels and predictions stay in `tools/rhythm-lab/database/`. Profile training data stays
under `tools/rhythm-lab/profiles/<profile-key>/`. Promoted scoring writes only SQLite classifier
scores. Source audio is not rewritten.

`delete-profile` requires `--confirm` matching the exact profile key or name.
