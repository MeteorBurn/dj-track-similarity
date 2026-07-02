# Rhythm Lab

> Audience: Users creating local classifier profiles.
> Goal: Label, train, promote, and send collections without losing source boundaries.
> Type: guide

Rhythm Lab is a separate labeling and training app. The main UI can launch it, and the search panel can save the current set as a Rhythm Lab collection.

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
python tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\live_instrumentation\combined\model.joblib --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promote:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Calibration report:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
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

The CLI can list, export, mark, and clear queue rows with `queue`, `queue-export`, `queue-mark`, and `queue-clear`.

## Delete profile

Profile deletion is explicit and confirmation-gated:

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
The Training UI does not expose calibration for now.

## Safety

Rhythm Lab does not rewrite source audio. Its normal data stays under `tools/rhythm-lab/data/` and `tools/rhythm-lab/artifacts/`. Promoted runtime models live under `models/classifiers/` and should not be committed unless you intentionally change that policy.
