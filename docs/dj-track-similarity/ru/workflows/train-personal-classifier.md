# Train a personal classifier

Аудитория: power users, использующие Rhythm Lab  
Цель: разметить tracks, обучить profile, promote его и score main library  
Тип: tutorial

Rhythm Lab - отдельный local tool для personal classifier profiles. Он читает
main project database для metadata и analysis inputs, но labels, predictions,
queues и checkpoints хранит в `tools/rhythm-lab/data/`.

## 1. Activate environment

Из корня проекта:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

## 2. Start Rhythm Lab

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite `
  --host 127.0.0.1 `
  --port 8777
```

Откройте `http://127.0.0.1:8777/`.

## 3. Label a profile

Создайте или выберите classifier profile в lab UI.

- Binary profiles используют один positive и один negative training label.
- Multiclass profiles используют `class` labels.
- Один track может иметь только один current class label для active profile.

## 4. Train

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train `
  --profile live_instrumentation `
  --source .\data\library.sqlite `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Добавьте `--calibrate`, когда намеренно нужна calibration и labels достаточно.
Если gate не выполнен, training может создать uncalibrated artifact с diagnostic
calibration report.

## 5. Promote

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote `
  --profile live_instrumentation `
  --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Используйте `--require-calibration` только когда uncalibrated production
artifact должен быть rejected.

## 6. Score main library

После promotion запустите classifier scoring из main app или CLI для этого
classifier key. Scores пишутся в `track_classifier_scores` и остаются scoped to
profile.

Если вы retrain/promote тот же classifier key, deliberately reset только старые
scores этого classifier перед rescoring. Не очищайте scores других classifier
keys.
