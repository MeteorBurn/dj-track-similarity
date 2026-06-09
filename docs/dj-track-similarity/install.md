# Installation

This page covers how to install `dj-track-similarity` locally, including the
optional dependency groups, the verified Windows CUDA stack, and the FFmpeg
requirement. Read it before the first run, then use [CLI](cli.md) to
scan a folder and start the server.

## Requirements

| Requirement | Notes |
| --- | --- |
| Python `>= 3.10` | The backend and CLI target Python 3.10 or newer. |
| FFmpeg | Required for server startup and audio decoding. Must be on `PATH` or set through `DJ_TRACK_SIMILARITY_FFMPEG`. |
| CUDA GPU | Optional. Speeds up MAEST, MERT, and CLAP. CPU works without a GPU. |

The project installs the `dj-sim` command from `pyproject.toml`. After install,
`dj-sim doctor` reports the Python, PyTorch, and CUDA runtime it sees.

## Dependency Groups

Core dependencies (`numpy`, `mutagen`, `pydantic`, `typer`, `fastapi`,
`uvicorn`, `joblib`) install with the base package. Optional extras enable the
analysis families and the local lab:

| Group | Installs | Enables |
| --- | --- | --- |
| `sonara` | Sonara support | Sonara playlist feature extraction and SONARA search. |
| `ml` | PyTorch/Torchaudio/Torchvision/TorchCodec, nnaudio, Transformers, Hugging Face Hub, LAION-CLAP, MAEST | MAEST genre analysis, MERT embeddings, CLAP audio/text embeddings. |
| `rhythm-lab` | scikit-learn | Local classifier training and benchmarking in Rhythm Lab. |
| `dev` | pytest, Ruff | Tests and linting. |

Combine the groups you need, for example `.[sonara,ml,dev]` for the full local
analysis stack without Rhythm Lab training, or `.[sonara,ml,rhythm-lab,dev]`
when the same environment will also train classifier profiles.

## Base Install

For a development checkout, install the project in editable mode:

```powershell
python -m pip install -e ".[dev]"
```

This is enough to run the CLI, the server, scanning, search, and exports.
Analysis families that need machine-learning models additionally require the
`sonara` and `ml` groups described below.

## ML Stack (CUDA, Windows)

The verified Windows CUDA stack is:

| Component | Version |
| --- | --- |
| PyTorch | `2.11.0` |
| Torchaudio | `2.11.0` |
| Torchvision | `0.26.0` |
| TorchCodec | `0.13.0` |
| nnaudio | installed by the `ml` extra |
| NumPy | `>=1.26,<2.0` |
| PyTorch wheel index | `https://download.pytorch.org/whl/cu130` |

Install the matching CUDA wheels from the official PyTorch wheel index first,
then install the remaining ML dependencies:

```powershell
python -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install torchcodec==0.13.0 --index-url https://download.pytorch.org/whl/cu130
python -m pip install -e ".[sonara,ml,dev]"
```

Use `.[sonara,ml,rhythm-lab,dev]` instead when the same environment will also
train Rhythm Lab classifier profiles.

> Warning: keep the PyTorch, Torchaudio, Torchvision, and TorchCodec versions
> synchronized with the CUDA wheel index above, and keep `numpy` below `2.0`.
> The `ml` extra also installs nnaudio from the normal Python package index.
> Mixing PyTorch-family versions is the most common cause of import or decode
> failures.

## FFmpeg

`ffmpeg` is required for robust server startup and shared audio decoding. It is
found from `PATH` or configured with:

```text
DJ_TRACK_SIMILARITY_FFMPEG
```

On Windows, TorchCodec-backed Torchaudio decoding needs an FFmpeg **shared**
build with DLLs on `PATH`, not only a static `ffmpeg.exe`. The verified portable
build is GyanD `ffmpeg 8.1.1-full_build-shared`, with a layout such as:

```text
C:\Utils\tools\ffmpeg\bin\ffmpeg.exe
C:\Utils\tools\ffmpeg\bin\avcodec-*.dll
C:\Utils\tools\ffmpeg\bin\avformat-*.dll
```

> Warning: a static `ffmpeg.exe` alone is not enough for TorchCodec decoding on
> Windows. Make sure the `bin` folder with the `av*.dll` files is on `PATH`.

## CPU-Only Install

A GPU is not required. Install the same `sonara` and `ml` groups, but you can
skip the CUDA wheel index and let PyTorch install its default build:

```powershell
python -m pip install -e ".[sonara,ml,dev]"
```

Analysis then runs on CPU. Use `--device cpu` (or leave `--device auto`, which
selects CPU when no GPU is visible) for MAEST, MERT, and CLAP work.

## Verify the Install

Check the command and the runtime:

```powershell
dj-sim --help
dj-sim doctor
```

`dj-sim doctor` prints the detected Python and PyTorch versions, whether CUDA is
available, and the device `auto` would choose. Use it whenever `auto`, `cpu`, or
`cuda` behavior is unclear, or after changing Python packages, CUDA wheels,
drivers, or the FFmpeg/TorchCodec setup. See [CLI](cli.md) for the
full `doctor` output.

## Next Steps

- Read the [Overview](overview.md) for the typical workflow.
- Use [CLI](cli.md) to scan a folder and start the server.
- See [Models](models.md) for what each model does and which extras it
  needs, and [Analysis](analysis.md) to decide which pass to run first.
