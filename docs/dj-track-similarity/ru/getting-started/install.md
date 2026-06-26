# Install

Аудитория: пользователи и power users  
Цель: установить базовые и опциональные зависимости  
Тип: how-to

## Python

Проект требует Python 3.10 или новее.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Все следующие Python-команды предполагают активное окружение.

## Optional extras

Используйте extras только когда они действительно нужны:

```powershell
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

Основные extras:

| Extra | Для чего нужен |
| --- | --- |
| `sonara` | SONARA feature extraction |
| `ml` | PyTorch/Torchaudio/TorchCodec, MERT, CLAP, MAEST |
| `rhythm-lab` | sklearn dependency для Rhythm Lab training |
| `ann` | optional hnswlib ANN sidecar indexes |
| `dev` | pytest, ruff и dev checks |

## FFmpeg

FFmpeg нужен server startup и robust audio decoding.

Варианты:

- добавить `ffmpeg.exe` в `PATH`;
- или задать `DJ_TRACK_SIMILARITY_FFMPEG`.

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

## Проверка

```powershell
dj-sim doctor
dj-sim --help
```

Если `dj-sim` не найден, проверьте, что окружение активировано и пакет
установлен в это окружение.
