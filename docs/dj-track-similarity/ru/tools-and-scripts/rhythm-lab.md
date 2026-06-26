# Rhythm Lab

Аудитория: power users, обучающие personal classifiers  
Цель: работать с отдельным local labeling and training app  
Тип: how-to/reference

Rhythm Lab запускается отдельно от main app. Он читает selected source library
database для track metadata и feature inputs, а lab state пишет в
`tools/rhythm-lab/data/` by default.

## Start the lab

Активируйте project environment один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite `
  --host 127.0.0.1 `
  --port 8777
```

Откройте `http://127.0.0.1:8777/`.

## CLI commands

Текущие top-level Rhythm Lab commands:

- `serve`
- `train`
- `predict`
- `export-predictions`
- `promote`
- `calibration-report`
- `suggest-labels`
- `queue`, `queue-export`, `queue-mark`, `queue-clear`
- `delete-profile`

Перед automation смотрите command-specific help:

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

Promotion copies selected combined artifact into main app classifier model
directory. Scoring library остается отдельным main-app action.

## Calibration flags

- `train --calibrate` attempts calibrated training when profile has enough
  labels.
- `promote --require-calibration` fails if selected artifact is not calibrated.
- `promote --allow-uncalibrated` allows experimental promotion when you accept
  that risk.

## Files to keep out of git

Lab labels, predictions, queues, checkpoints и generated artifacts - local
state. Они должны оставаться ignored, если только вы намеренно не добавляете
test fixture.
