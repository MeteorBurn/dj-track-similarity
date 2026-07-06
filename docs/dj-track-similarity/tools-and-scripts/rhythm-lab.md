# Rhythm Lab

> Audience: Users creating local classifier profiles.
> Goal: Label, train, promote, and send collections without losing source boundaries.
> Type: guide

Rhythm Lab is a separate labeling and training app. The main UI can launch it, and the search panel can save the current set as a Rhythm Lab collection.

New labels databases do not create a built-in classifier profile. Create a profile in the UI, or pass the intended `--profile` to profile-specific CLI commands.

## Start the UI

From the main UI, click the flask icon. The backend starts or reuses Rhythm Lab at port `8777`.

Manual command:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Open:

```text
http://127.0.0.1:8777/
```

## Main CLI commands

Train:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Predict:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\live_instrumentation\combined\model.joblib --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promote:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Calibration report:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Calibrated training is explicit. The Training UI does not expose these actions:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --calibrate
```

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --calibrate-finalists --output tools\rhythm-lab\artifacts\ablation-calibrated.json
```

To promote a calibrated artifact intentionally, require calibration:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set 'mert+maest' --require-calibration --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Suggest labels:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py suggest-labels --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --limit 25
```

## Collections

The main UI can save the current set as a Rhythm Lab collection. The CLI can also create or update a collection:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py collection-save --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "review pile" --track-id 123 --track-id 456
```

List collections:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py collection-list --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Active-learning queue

The CLI can list, export, mark, and clear queue rows with `queue`, `queue-export`, `queue-mark`, and `queue-clear`. Queue commands are profile-scoped and require `--profile`.

## Delete profile

Profile deletion is explicit and confirmation-gated. In the UI, the `Delete`
button asks you to type the profile name or key before it removes Rhythm Lab
labels, predictions, queue rows, training checkpoints, metrics, and local
training artifacts for that profile. Promoted runtime models under
`models/classifiers/` are not removed.

The CLI uses the same exact-confirmation rule:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py delete-profile --profile live_instrumentation --confirm live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Ablation benchmarks

Run a benchmark when you want local evidence for feature-source variants on one
classifier profile:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\artifacts\ablation.json
```

The command reads the source library without writes. Experimental artifacts stay
under the profile artifact folder, and the benchmark output is a JSON report. It
does not promote models or write classifier scores.

The Training tab has the same active-profile workflow: collect labels, train,
review candidates, run a benchmark, choose a promotion variant, and promote.
`Train` retrains from current labels and refreshes candidates automatically.
The Training UI does not expose calibration for now. Promotion from the UI uses
uncalibrated artifacts and ignores calibrated finalists. Use the API or CLI when
you intentionally want calibration.

API calibration is available on a running Rhythm Lab server:

```text
POST /api/profiles/{profile_key}/training/calibrate
{"feature_set": "mert+maest"}
```

Omit `feature_set` to use the current default promotion variant.

## Safety

Rhythm Lab does not rewrite source audio. Its normal data stays under
`tools/rhythm-lab/data/` and `tools/rhythm-lab/artifacts/`. Profile deletion
can remove Rhythm Lab database rows and local training artifacts for one
profile. Promoted runtime models live under `models/classifiers/`, are not
removed by profile deletion, and should not be committed unless you
intentionally change that policy.
