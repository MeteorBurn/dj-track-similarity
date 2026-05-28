# Rhythm Lab

Rhythm Lab - вспомогательный UI для разметки и обучения классификаторов для
`dj-track-similarity`. Он запускается отдельно от основного приложения, открывает
основную SQLite database проекта read-only и сохраняет только lab labels,
predictions и training checkpoints в собственный writable SQLite file.

Используйте Rhythm Lab, когда generic similarity или genre labels недостаточны
и нужен персональный reusable classifier, например "has live instrumentation",
"vocal presence", "peak-time tool" или любой другой library-specific concept,
который вы можете размечать consistently.

Rhythm Lab основан на profiles. Classifier profile определяет:

- стабильный `classifier_key`
- уникальные display name и description
- profile type:
  - `binary`: ровно один positive training label, ровно один negative training
    label и optional review-only labels, которые сохраняются, но исключаются из
    fitting
  - `multiclass`: два или больше user-defined class labels; каждый label -
    trainable class
- profile-specific artifact folder и artifact filename prefix
- train-refresh threshold: сколько новых labels per training class требуется
  после последнего training checkpoint, прежде чем UI включит training

Profiles могут быть binary или multiclass. Binary profile может использовать:

- `live_instrument`: positive class для tracks с live/acoustic instrument
  material
- `no_instrument`: negative/reference class
- `uncertain`: review-only label, excluded from fitting

Track labels - current-state annotations. Если track был размечен неправильно
или ваша оценка изменилась, выберите другой label или Clear в UI; старое
значение заменяется, и следующий training run использует только current label.
Это относится и к binary, и к multiclass profiles: один track может иметь только
один current label для active profile.

Хороший workflow: создать один сфокусированный profile, сначала разметить
очевидные examples, обучить несколько benchmark models, проверить predictions,
добавить labels для mistakes или uncertain areas, затем promote лучший combined
model для использования в main app.

## Storage layout

Lab state:

```text
tools/rhythm-lab/data/rhythm_lab.sqlite
```

Training artifacts для profile:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

New profiles могут использовать собственную folder, например:

```text
tools/rhythm-lab/artifacts/vocal-presence/
```

Promoted runtime model, используемая main app:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Lab database использует classifier-scoped tables:

```text
classifier_profiles
classifier_profile_labels
classifier_labels
classifier_predictions
classifier_training_checkpoints
classifier_track_likes
```

Rows разных profiles изолированы `classifier_key`, поэтому labels, predictions
и training checkpoints не смешиваются.

Profile display names уникальны case-insensitively внутри одной lab database.
Например, `Electronic Mood` и `electronic mood` не могут существовать вместе.
Если older lab database уже содержит duplicate profile names, Rhythm Lab
откажется открывать ее, пока duplicate names не будут resolved.

## Quick start

Запустить из repository root:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Открыть:

```text
http://127.0.0.1:8777/
```

Source database не загружается при startup, если не передан `--source`. UI имеет
source database path field, file picker и Load database button. Selected source
DB opened read-only. При startup classifier profile не выбран; выберите
существующий profile или создайте новый перед loading tracks.

Используйте UI для labeling и review. Используйте CLI для training, prediction
export, promotion и permanent profile deletion.

## Labeling UI

UI включает:

- profile creation, editing, archiving и switching
- profile type selection в New classifier profile dialog
- multiclass label creation с custom keys, display names и descriptions
- explicit profile selection on startup
- profile-scoped Library, Candidates, Training и Profile Settings views
- text search by path/title/artist
- source database picker и load control
- syncopated rhythm filter
- dynamic manual label и predicted-label filters
- pagination
- audio preview from source paths
- MAEST genres и SONARA/MERT/MAEST feature availability from source DB
- compact app-shell coverage badges для Tracks, SONARA, MAEST и MERT
- compact label-count badges for active profile
- training readiness и guidance cards
- per-profile train-refresh threshold editing в Profile Settings

Archiving profile скрывает его из normal active profile list, но сохраняет
labels, predictions, likes и training checkpoints в lab database. Permanent
deletion намеренно доступно через CLI, а не UI.

Keyboard shortcuts на focused row используют label order active profile:

- `1`..`9` = profile labels in display order
- `0` = clear label

AIFF/AIF previews транскодируются во временные WAV files для browser playback.
Это read-only для source audio file и дает browser seekable codec с duration и
scrubbing support.

Размечайте только concept текущего profile. Смешивание нескольких concepts в
одном profile делает model менее интерпретируемой и обычно дает менее полезные
CLASS filters в main app.

## Training

Training и prediction используют scikit-learn. Установите optional Rhythm Lab
dependency group в project environment перед training commands:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[rhythm-lab]"
```

Для одной environment, которая также запускает main app analysis passes,
установите `.[sonara,ml,rhythm-lab,dev]`.

После разметки достаточного количества examples:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Train custom profile:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py train --profile vocal_presence --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Training command benchmarks these feature sets:

- `sonara`
- `mert`
- `maest`
- `combined`

`combined` требует все три family: SONARA features из
`metadata_json.sonara_features`, MERT embeddings и MAEST embeddings. Tracks без
любого из этих inputs пропускаются для combined model.

UI train-refresh button управляется threshold active profile для new labels per
training class. Default - 50. Изменение значения в Profile Settings сразу
меняет readiness calculation и display "required new labels" для active
profile.

Artifacts и metrics пишутся в artifact folder active profile:

```text
tools/rhythm-lab/artifacts/live-instrumentation/
```

Artifact names используют profile artifact prefix, например:

```text
live-instrumentation-combined-20260525T010203Z.joblib
live-instrumentation-combined-20260525T010203Z.metrics.json
```

Metrics используют profile-neutral names, например `positive_discovery`,
`positive_precision`, `positive_recall`, `negative_candidates` и `label_order`.
Profiles не должны писать classifier-specific legacy metric fields.

Apply trained model и export candidates:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\live-instrumentation\<model>.joblib --source C:\db\abstracted.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py export-predictions --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Для custom profiles передавайте `--profile <classifier_key>`, когда artifact не
содержит profile metadata или когда экспортируете profile-scoped predictions.

Promote latest combined model for any profile into the main project:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Это копирует latest `<artifact-prefix>-combined-*.joblib` artifact в
`models/classifiers/<artifact-prefix>/model.joblib` и пишет local metadata в
`models/classifiers/<artifact-prefix>/model.json`. Metadata записывается из
selected profile и artifact payload (`classifier_key`, profile name, labels,
feature set и label counts). Эти promoted files - local runtime artifacts и
ignored by git.

## Profile deletion

Delete - destructive operation. Она навсегда удаляет profile row и все
profile-scoped lab data из `rhythm_lab.sqlite`: profile labels, manual track
labels, likes, saved predictions и training checkpoints. Она не удаляет source
audio files, source database rows или training/model artifact files on disk.

Delete by unique profile name:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "Electronic Mood" --confirm "Electronic Mood"
```

Delete by `classifier_key`:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py delete-profile --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile electronic_mood --confirm electronic_mood
```

Значение `--confirm` должно точно совпадать с выбранным `--name` или `--profile`
value. Это предотвращает accidental deletion при использовании shell history
или copy/paste.

## Useful checks

Count labels for a profile:

```powershell
@'
from pathlib import Path
import sqlite3
path = Path(r"E:\Projects\dj-track-similarity\tools\rhythm-lab\data\rhythm_lab.sqlite")
conn = sqlite3.connect(path)
try:
    print(conn.execute("""
        SELECT label, COUNT(*)
        FROM classifier_labels
        WHERE classifier_key = 'live_instrumentation'
        GROUP BY label
        ORDER BY label
    """).fetchall())
finally:
    conn.close()
'@ | .\.venv\Scripts\python.exe -
```

Run focused tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```

## Интеграция с основным приложением

Promoted classifiers - локальные classifier profiles, а не audio-analysis
models, которые сами декодируют files. Они оценивают tracks из уже сохраненных
analysis outputs:

- SONARA playlist features из `metadata_json.sonara_features`;
- MERT embeddings из `embeddings.embedding_key = "mert"`;
- MAEST embeddings из `embeddings.embedding_key = "maest"`.

Tracks без любого из этих inputs пропускаются classifier job. Scores
сохраняются в `track_classifier_scores` под profile classifier key.

Stable model locations используют profile artifact prefix:

```text
models/classifiers/<artifact-prefix>/model.joblib
models/classifiers/<artifact-prefix>/model.json
```

Promoted files - local runtime artifacts и ignored by git. Main app может
оценить promoted profile командой:

```powershell
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

User-facing score - classifier probability для positive training label профиля.
Поскольку UI displays могут округлять probabilities, значение `1.0000` может
быть немного ниже mathematical `1.0`. Для practical filtering используйте
thresholds вроде `0.99`, `0.95` или `0.90`, а не точное `1.0`.

