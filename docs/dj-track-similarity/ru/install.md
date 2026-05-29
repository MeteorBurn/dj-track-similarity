# Установка

Эта страница описывает, как установить `dj-track-similarity` локально, включая
необязательные группы зависимостей, проверенный CUDA-стек для Windows и
требование к FFmpeg. Прочитайте её перед первым запуском, а затем используйте
[CLI](cli.md), чтобы просканировать папку и запустить сервер.

## Требования

| Требование | Примечания |
| --- | --- |
| Python `>= 3.10` | Backend и CLI рассчитаны на Python 3.10 или новее. |
| FFmpeg | Необходим для запуска сервера и декодирования аудио. Должен быть в `PATH` или задан через `DJ_TRACK_SIMILARITY_FFMPEG`. |
| CUDA GPU | Необязателен. Ускоряет MAEST, MERT и CLAP. Без GPU работа идёт на CPU. |

Проект устанавливает команду `dj-sim` из `pyproject.toml`. После установки
`dj-sim doctor` сообщает, какие версии Python, PyTorch и среды выполнения CUDA
он видит.

## Группы зависимостей

Основные зависимости (`numpy`, `mutagen`, `pydantic`, `typer`, `fastapi`,
`uvicorn`, `joblib`) устанавливаются вместе с базовым пакетом. Необязательные
extras включают семейства анализа и локальную лабораторию:

| Группа | Устанавливает | Включает |
| --- | --- | --- |
| `sonara` | Поддержку Sonara | Извлечение Sonara playlist features и поиск SONARA. |
| `ml` | PyTorch/Torchaudio/Torchvision/TorchCodec, Transformers, Hugging Face Hub, LAION-CLAP, MAEST | Анализ жанров MAEST, MERT embeddings, аудио/текстовые embeddings CLAP. |
| `rhythm-lab` | scikit-learn | Локальное обучение и бенчмаркинг классификаторов в Rhythm Lab. |
| `dev` | pytest, Ruff | Тесты и линтинг. |

Комбинируйте нужные группы — например, `.[sonara,ml,dev]` для полного локального
стека анализа без обучения Rhythm Lab или `.[sonara,ml,rhythm-lab,dev]`, когда в
той же среде также будут обучаться classifier profiles.

## Базовая установка

Для рабочей копии разработчика установите проект в editable-режиме:

```powershell
python -m pip install -e ".[dev]"
```

Этого достаточно для запуска CLI, сервера, сканирования, поиска и экспорта.
Семейства анализа, которым нужны модели машинного обучения, дополнительно
требуют групп `sonara` и `ml`, описанных ниже.

## ML-стек (CUDA, Windows)

Проверенный CUDA-стек для Windows:

| Компонент | Версия |
| --- | --- |
| PyTorch | `2.11.0` |
| Torchaudio | `2.11.0` |
| Torchvision | `0.26.0` |
| TorchCodec | `0.13.0` |
| NumPy | `>=1.26,<2.0` |
| Индекс wheel-пакетов PyTorch | `https://download.pytorch.org/whl/cu130` |

Сначала установите подходящие CUDA-сборки wheel из официального индекса
wheel-пакетов PyTorch, затем установите остальные ML-зависимости:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Используйте `.[sonara,ml,rhythm-lab,dev]`, когда в той же среде также будут
обучаться classifier profiles Rhythm Lab.

> Внимание: держите версии PyTorch, Torchaudio, Torchvision и TorchCodec
> синхронизированными с указанным выше индексом wheel-пакетов CUDA и держите
> `numpy` ниже `2.0`. Смешивание версий — самая частая причина ошибок импорта
> или декодирования.

## FFmpeg

`ffmpeg` необходим для надёжного запуска сервера и общего декодирования аудио. Он
находится в `PATH` или настраивается через:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

В Windows декодирование Torchaudio на базе TorchCodec требует **shared**-сборки
FFmpeg с DLL в `PATH`, а не только статический `ffmpeg.exe`. Проверенная
портативная сборка — GyanD `ffmpeg 8.1.1-full_build-shared` с такой раскладкой:

```text
C:\Utils\tools\ffmpeg\bin\ffmpeg.exe
C:\Utils\tools\ffmpeg\bin\avcodec-*.dll
C:\Utils\tools\ffmpeg\bin\avformat-*.dll
```

> Внимание: одного статического `ffmpeg.exe` недостаточно для декодирования
> TorchCodec в Windows. Убедитесь, что папка `bin` с файлами `av*.dll` находится
> в `PATH`.

## Установка только для CPU

GPU не обязателен. Установите те же группы `sonara` и `ml`, но можно пропустить
индекс wheel-пакетов CUDA и позволить PyTorch установить свою сборку по
умолчанию:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Тогда анализ выполняется на CPU. Используйте `--device cpu` (или оставьте
`--device auto`, который выбирает CPU, когда GPU не виден) для работы MAEST, MERT
и CLAP.

## Проверка установки

Проверьте команду и среду выполнения:

```powershell
dj-sim --help
dj-sim doctor
```

`dj-sim doctor` выводит обнаруженные версии Python и PyTorch, доступность CUDA и
устройство, которое выбрал бы `auto`. Используйте его всякий раз, когда поведение
`auto`, `cpu` или `cuda` неясно, либо после изменения пакетов Python, CUDA-сборок
wheel, драйверов или конфигурации FFmpeg/TorchCodec. Полный вывод `doctor` см. в
разделе [CLI](cli.md).

## Дальнейшие шаги

- Прочитайте [Обзор](overview.md) для понимания типичного рабочего процесса.
- Используйте [CLI](cli.md), чтобы просканировать папку и запустить
  сервер.
- См. [Модели](models.md) о том, что делает каждая модель и какие extras
  ей нужны, и [Анализ](analysis.md), чтобы решить, какой проход
  запускать первым.
