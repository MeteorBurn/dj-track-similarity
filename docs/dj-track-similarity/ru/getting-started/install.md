# Install

> Audience: Пользователи, которые настраивают проект локально.
> Goal: Установить Python dependencies и понять, когда нужны Node/npm и optional extras.
> Type: how-to

## Requirements

- Python 3.10+.
- `ffmpeg` в `PATH` или `DJ_TRACK_SIMILARITY_FFMPEG`, указывающий на executable.
- PyTorch stack, подходящий под CPU/GPU среду, если вы запускаете MERT, MAEST или CLAP analysis.
- Node/npm нужны только для rebuild frontend или docs assets.

## Base install

Базовой установки достаточно для scan, UI browse, backend serve и работы с уже сохраненными данными:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Analysis install

Установите local ML extras, когда нужны SONARA, MERT, MAEST, CLAP или Rhythm Lab workflows:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
dj-sim doctor
```

Держите PyTorch-family packages синхронизированными с wheel set, который реально используете. `dj-sim doctor` печатает detected Torch/CUDA state и suggested install index, когда может его определить.

## Optional ANN index install

Persistent ANN sidecar indexes необязательны. Установите `hnswlib` через `ann` extra, если нужны HNSW-backed indexes:

```powershell
python -m pip install -e ".[ann]"
```

Без этого extra `dj-sim index build --backend auto` может вернуться к exact NumPy sidecar. См. [Persistent ANN indexes](../tools-and-scripts/persistent-ann-indexes.md).

## Build assets

Собирайте frontend из `frontend/` только когда изменился frontend source. Собирайте docs из `docs\dj-track-similarity` через `npm run build` только когда нужен local site output или deployment output. Docs build пишет `site/`, этот каталог ignored by Git.
