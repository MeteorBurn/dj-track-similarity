# Rhythm Lab

Audience: power users training personal classifiers  
Goal: operate the separate local labeling and training app  
Type: how-to/reference

Rhythm Lab runs separately from the main app. It reads the selected source
library database for track metadata and feature inputs, and writes lab state
under `tools/rhythm-lab/data/` by default.

## Start the lab

Activate the project environment once:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite `
  --host 127.0.0.1 `
  --port 8777
```

Open `http://127.0.0.1:8777/`.

## CLI commands

Current top-level Rhythm Lab commands include:

- `serve`
- `train`
- `predict`
- `export-predictions`
- `promote`
- `calibration-report`
- `suggest-labels`
- `queue`, `queue-export`, `queue-mark`, `queue-clear`
- `delete-profile`

Run command-specific help before automation:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --help
python tools\rhythm-lab\rhythm_lab_cli.py promote --help
```

## Train and promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train `
  --profile live_instrumentation `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite

python tools\rhythm-lab\rhythm_lab_cli.py promote `
  --profile live_instrumentation `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Promotion copies the selected combined artifact into the main app classifier
model directory. Scoring the library is still a separate main-app action.

## Calibration flags

- `train --calibrate` attempts calibrated training when the profile has enough
  labels.
- `promote --require-calibration` fails if the selected artifact is not
  calibrated.
- `promote --allow-uncalibrated` allows experimental promotion when you accept
  that risk.

## Files to keep out of git

Lab labels, predictions, queues, checkpoints, and generated artifacts are local
state. They should stay ignored unless a specific fixture is intentionally
added.
