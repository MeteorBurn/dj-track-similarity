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
your labels -> trained candidate -> promoted profile -> per-track scores -> CLASS / SET / Hybrid
```

The final score is not a tag written into the audio and not an objective truth. It is a reusable
ranking signal for one profile. The score can filter the library and steer SET toward or away from
the concept. A promoted manifest may also expose it as diagnostic evidence in Hybrid.

Rhythm Lab is the classifier workspace. It uses the main SQLite library as source context and keeps
labels, predictions, queues, and checkpoints in its own labels database.

## 1. Prepare source analysis

For combined training, run SONARA, MERT, and MAEST first:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert --db .\data\library.sqlite
```

Benchmark variants can also use CLAP when CLAP embeddings already exist. SONARA 2.0 benchmark variants still read stored SONARA features. The `sonara2vocal` variant adds `vocalness` to the candidate feature set.

The command above uses the current SONARA `core` output, matching the CLI and direct API defaults.
The `timeline`, `embedding`, and `fingerprint` outputs are not classifier inputs. The exact `core`
contract becomes part of a SONARA-dependent artifact identity.

## 2. Start Rhythm Lab

The React frontend's v7 port is deferred. Start Rhythm Lab directly:

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
candidates automatically. Calibration is not exposed in this UI for now. Use
the API or CLI only when you intentionally want calibration and have enough
labels for the calibration gate. UI promotion ignores calibrated artifacts
while calibration is hidden, so an older uncalibrated winner is safer than an
automatically generated calibrated finalist.

After training, listen to high-scoring, low-scoring, and borderline candidates. Useful mistakes
often reveal that the concept or the label set needs refinement before promotion.

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
profiles. A stale promoted artifact stays blocked because its manifest signature cannot score current
tracks.

Use [Prepare and rebuild a SONARA release](./reanalyze-sonara-split-storage.md) when the source
analysis contract changes.

The runtime accepts manifest version `2`. The promoted `model.json` files currently in
`models/classifiers/` still declare version `1`, so they are blocked until their profiles are
retrained and promoted.

## Safety

Rhythm Lab labels and predictions stay under `tools/rhythm-lab/data/`. Promoted scoring writes only SQLite classifier scores. Source audio is not rewritten.
