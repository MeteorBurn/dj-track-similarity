# Train a personal classifier

> Audience: Users who want the app to learn a local concept from labels.
> Goal: Move from review labels to a promoted classifier score.
> Type: workflow

Rhythm Lab is the classifier workspace. It uses the main SQLite library as source context and keeps labels, predictions, queues, and checkpoints in its own labels database.

## 1. Prepare source analysis

For combined training, run SONARA, MERT, and MAEST first:

```powershell
dj-sim analyze --models sonara,maest,mert --db .\data\library.sqlite
```

Benchmark variants can also use CLAP when CLAP embeddings already exist.

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
candidates automatically. Calibration is not exposed in this UI for now. In the
CLI, add `--calibrate` only when you intentionally want calibration and have
enough labels for the calibration gate.

## 5. Benchmark variants

Run a benchmark when you want to compare feature-source variants for the active
profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\artifacts\ablation.json
```

The Training tab shows the benchmark winner and lets you choose a different
trained variant before promotion.

## 6. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set combined --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promotion copies the selected runtime artifact into
`models/classifiers/<artifact-prefix>/`.

## 7. Score in the main app

Use the CLASS tab or CLI:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

After retraining and promoting the same classifier key, reset only that classifier's old scores before rescoring.

## Safety

Rhythm Lab labels and predictions stay under `tools/rhythm-lab/data/`. Promoted scoring writes only SQLite classifier scores. Source audio is not rewritten.
