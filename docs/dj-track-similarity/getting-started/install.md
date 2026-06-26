# Install the project

Audience: users and power users  
Goal: choose the right dependency set  
Type: how-to

The project has a small base install plus optional extras. Start with the base
install unless you already know you need model analysis or Rhythm Lab.

## Base install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Expected result:

```text
dj-sim --help
```

prints the CLI command list. Keep the environment active for later commands.

## Optional extras

| Extra | Use it when |
| --- | --- |
| `dev` | You want normal local checks and pytest. |
| `sonara` | You want SONARA local audio features. |
| `ml` | You want MAEST, MERT, CLAP, PyTorch, and TorchCodec. |
| `rhythm-lab` | You want classifier labeling and training with scikit-learn. |
| `ann` | You want optional persistent ANN sidecar indexes. |

Common installs:

```powershell
python -m pip install -e ".[sonara,dev]"
python -m pip install -e ".[sonara,ml,dev]"
python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"
```

For ANN experiments:

```powershell
python -m pip install -e ".[sonara,ml,ann,dev]"
```

## FFmpeg

Server startup requires FFmpeg. Put `ffmpeg` on `PATH`, or set:

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG = "C:\path\to\ffmpeg.exe"
```

On Windows, TorchCodec-backed torchaudio decoding needs a shared FFmpeg build
with DLLs available on `PATH`.

## Verify the install

```powershell
dj-sim doctor
```

Expected result:

```text
doctor reports Python, FFmpeg, optional PyTorch/CUDA state, and the selected
analysis device behavior.
```

If `doctor` reports missing FFmpeg or unavailable CUDA, fix that before running
long analysis jobs.
