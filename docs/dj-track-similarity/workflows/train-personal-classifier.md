# Train a personal classifier

Audience: power users using Rhythm Lab  
Goal: label tracks, train a profile, promote it, and score the main library  
Type: tutorial

Rhythm Lab is the separate local tool for personal classifier profiles. It reads
the main project database for track metadata and analysis inputs, but keeps lab
labels, predictions, queues, and training checkpoints under
`tools/rhythm-lab/data/`.

## 1. Activate the environment

From the project root:

```powershell
.\.venv\Scripts\Activate.ps1
```

All following commands assume the environment is active.

## 2. Start Rhythm Lab

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite `
  --host 127.0.0.1 `
  --port 8777
```

Open `http://127.0.0.1:8777/`.

## 3. Label a profile

Create or select a classifier profile in the lab UI.

- Binary profiles use one positive and one negative training label.
- Multiclass profiles use `class` labels.
- A track can hold only one current class label for the active multiclass
  profile.

## 4. Train

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train `
  --profile live_instrumentation `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Add `--calibrate` when you intentionally want calibration and have enough
labels. If the gate is not satisfied, training can still produce an
uncalibrated artifact with a diagnostic calibration report.

## 5. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote `
  --profile live_instrumentation `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Use `--require-calibration` only when an uncalibrated production artifact should
be rejected.

## 6. Score the main library

After promotion, run classifier scoring from the main app or CLI for that
classifier key. Scores are written to `track_classifier_scores` and stay scoped
to the promoted profile.

If you retrain and promote the same classifier key, deliberately reset only
that classifier's old scores before rescoring. Do not clear scores for other
classifier keys.
