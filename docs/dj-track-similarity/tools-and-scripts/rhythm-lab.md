# Rhythm Lab

> Audience: Power users training local classifiers.
> Goal: Run the separate labeling/training helper safely.
> Type: how-to

## Commands

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --profile <classifier-key> --source <library-db> --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile <classifier-key> --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Calibration

Use `--calibrate` only when you intentionally want calibration and have enough labels. Use `promote --require-calibration` only when calibrated output is required.
