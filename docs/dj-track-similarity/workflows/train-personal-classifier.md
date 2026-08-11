# Train a personal classifier

> Audience: Users who want the app to learn a local concept from labels.
> Goal: Move from review labels to a promoted classifier score.
> Type: workflow

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

Use MERT, SONARA, or CLAP instead when the question is temporary or you only need one shortlist.
Training adds maintenance: a weak or narrow label set produces a weak or narrow score.

## What the finished workflow produces

```text
your labels -> trained candidate -> promoted profile -> per-track scores -> CLASS
```

The final score is not a tag written into the audio and not an objective truth. It is a reusable
ranking signal for one profile. The score can filter the library through CLASS.

Rhythm Lab is the classifier workspace. It uses the main SQLite library as source context and keeps
labels, predictions, queues, and checkpoints in its own labels database.

## 1. Prepare source analysis

For a recipe that uses SONARA, MERT, and MAEST, run those analyses first:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert --db .\data\library.sqlite
```

If a selected feature set contains MuQ, store its current embedding first:

```powershell
dj-sim analyze --models muq --db .\data\library.sqlite
```

Benchmark variants can also use CLAP when CLAP embeddings already exist. The single current
`sonara` source includes the current Core fields, including `vocalness`.

The command above uses the current SONARA `core` output, matching the CLI and direct API defaults.
The `timeline`, `embedding`, and `fingerprint` outputs are not classifier inputs. A
SONARA-dependent artifact records the ordered Core feature names it uses.

## 2. Start Rhythm Lab

Choose the database in the main app and click the Rhythm Lab flask in the top bar. The app starts
or reuses the local Lab process and opens its URL. You can also start it directly:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

## 3. Pick profile type

- Binary profiles use one positive and one negative training label.
- Multiclass profiles use class labels, and one track can hold only one current class label for the active profile.

Choose labels that answer one clear question. For a binary profile, positive should mean "this is the
concept" and negative should mean "this is not the concept." Avoid assigning a clean label while you
are unsure about a track. Use review labels and queues to keep borderline tracks visible without
turning them into training labels too early.

## 4. Train

Use Library, Collection, or Candidates to collect enough training labels for the
active profile. New profiles start from Library or Collection labeling. Candidate
review becomes useful after the first trained artifact exists.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

In the Training tab, `Train` retrains from all current labels and refreshes
candidates automatically. `Calibrate` explicitly refits the selected binary
variant after the usable-row gate is met: at least 100 total examples, including
20 positive and 20 negative. Promotion requires a calibrated artifact bound to
the active source catalog unless the CLI receives the experimental
`--allow-uncalibrated` override.

CLI and UI training default to the current full recipe,
`sonara+mert+maest+clap+muq`. The **Training recipe** selector also exposes
individual sources and supported combinations. Readiness is calculated from
labels that have every current output required by the selected recipe.

After training, listen to high-scoring, low-scoring, and borderline candidates. Useful mistakes
often reveal that the concept or the label set needs refinement before promotion.

## 5. Benchmark variants

Run a benchmark when you want to compare feature-source variants for the active
profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\artifacts\ablation.json
```

The Training tab benchmarks all 31 non-empty combinations of SONARA, MERT,
MAEST, CLAP, and MuQ, then identifies the best trained variant for the active
profile before promotion.

For any other combination, repeat the CLI option:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --feature-set muq --feature-set sonara+muq --output tools\rhythm-lab\artifacts\ablation-muq.json
```

## 6. Optional calibration

Calibration is advanced and opt-in. Use it only when you explicitly want
calibrated positive-label probabilities instead of the normal uncalibrated
classifier score.

Calibration is data-gated. Binary profiles need at least 100 training labels,
20 positive labels, and 20 negative labels. If the gate is not satisfied, the
artifact stays uncalibrated and records the reason in its calibration report.

Calibrate the normal training command:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --calibrate
```

Calibrate benchmark winners after an ablation run:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --calibrate-finalists --output tools\rhythm-lab\artifacts\ablation-calibrated.json
```

Calibrate one selected feature set through the Rhythm Lab API:

```text
POST http://127.0.0.1:8777/api/profiles/live_instrumentation/training/calibrate
{"feature_set": "mert+maest"}
```

UI and CLI promotion require a calibrated artifact for the active source
catalog by default. The requirement flag makes that intent explicit:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set 'mert+maest' --require-calibration --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Use `calibration-report` to inspect the selected artifact before promotion:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## 7. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promotion copies the selected runtime artifact into
an immutable generation under `models/classifiers/<artifact-prefix>/`, then
atomically switches `current.json` after the model and manifest hashes pass.

## 8. Score through the current backend

Use the CLI:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

After retraining and promoting the same classifier key, reset only that classifier's old scores
before rescoring. API clients can reset the key explicitly:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/classifiers/reset -Method Post -ContentType 'application/json' -Body '{"classifier_keys":["live_instrumentation"]}'
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

After a SONARA feature revision, dependent main-library scores and Rhythm Lab predictions are
invalidated while labels and feedback remain. Reanalyze SONARA, then retrain and promote the affected
profiles. A promoted artifact with a mismatched ordered feature recipe cannot score current tracks.

Use [Migrate and reanalyze SONARA storage](./reanalyze-sonara-split-storage.md) when the source
analysis update changes stored structure or the classifier's feature recipe.

A promoted artifact may declare ordered `muq:<index>` features and the expected MuQ vector
dimension. Backend scoring loads those values from SQLite without decoding audio. A profile whose
ordered feature recipe no longer matches must be retrained and promoted.

## Safety

Rhythm Lab labels and predictions stay under `tools/rhythm-lab/data/`. Promoted scoring writes only SQLite classifier scores. Source audio is not rewritten.
