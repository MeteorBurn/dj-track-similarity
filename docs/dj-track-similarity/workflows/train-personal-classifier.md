# Train a personal classifier

> Audience: Users who want the app to learn a local concept from labels.
> Goal: Move from review labels to a promoted classifier score.
> Type: workflow

Rhythm Lab is the classifier workspace. It uses the main SQLite library as source context and keeps labels, predictions, queues, and checkpoints in its own labels database.

## 1. Prepare source analysis

For combined training, run SONARA, MERT, and MAEST first:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert --db .\data\library.sqlite
```

Benchmark variants can also use CLAP when CLAP embeddings already exist. SONARA 2.0 benchmark variants still read stored SONARA features. The `sonara2vocal` variant adds `vocalness` to the candidate feature set.

The command above uses current SONARA Core, matching the browser and direct API defaults. Timeline
and Representations are not classifier inputs. The exact Core profile becomes part of the artifact
signature.

## 2. Start Rhythm Lab

From the main UI, use the flask icon to launch Rhythm Lab. Or start it manually:

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

Use review labels and queues to keep borderline tracks visible without turning them into training labels too early.

## 4. Train

Use Library, Collection, or Candidates to collect enough training labels for the
active profile. New profiles start from Library or Collection labeling. Candidate
review becomes useful after the first trained artifact exists.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

In the Training tab, `Train` retrains from all current labels and refreshes
candidates automatically. Calibration is not exposed in this UI for now. Use
the API or CLI only when you intentionally want calibration and have enough
labels for the calibration gate. UI promotion ignores calibrated artifacts
while calibration is hidden, so an older uncalibrated winner is safer than an
automatically generated calibrated finalist.

## 5. Benchmark variants

Run a benchmark when you want to compare feature-source variants for the active
profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\artifacts\ablation.json
```

The Training tab shows the benchmark winner and lets you choose a different
trained variant before promotion. The default benchmark matrix includes
embedding-only combinations, the original SONARA feature set, `sonara2`, and
`sonara2vocal`.

## 6. Optional calibration

Calibration is advanced and opt-in. Use it only when you explicitly want
calibrated positive-label probabilities instead of the normal uncalibrated
classifier score. It is available through API and CLI, not through the Training
UI.

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

Normal UI promotion ignores calibrated artifacts. To promote a calibrated
artifact intentionally, use the CLI requirement flag:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set 'mert+maest' --require-calibration --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Use `calibration-report` to inspect the selected artifact before promotion:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## 7. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set combined --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promotion copies the selected runtime artifact into
`models/classifiers/<artifact-prefix>/`.

## 8. Score in the main app

Use the CLASS tab or CLI:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

After retraining and promoting the same classifier key outside a feature-revision migration, reset
only that classifier's old scores before rescoring. In the CLASS tab, the classifier play action
performs that reset-and-rescore flow. API clients can reset the key explicitly:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/classifiers/reset -Method Post -ContentType 'application/json' -Body '{"classifiers":["live_instrumentation"]}'
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

After a SONARA feature revision, dependent main-library scores and Rhythm Lab predictions are
invalidated while labels and feedback remain. Reanalyze SONARA, then retrain and promote the affected
profiles. A stale promoted artifact stays blocked because its manifest signature cannot score current
tracks.

Use the complete [split SONARA storage workflow](./reanalyze-sonara-split-storage.md) when the source
analysis contract changed. Its revision and per-track guards already remove dependent scores.

## Safety

Rhythm Lab labels and predictions stay under `tools/rhythm-lab/data/`. Promoted scoring writes only SQLite classifier scores. Source audio is not rewritten.
