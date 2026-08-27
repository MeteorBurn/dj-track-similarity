# Troubleshooting by symptom

Find your symptom below. Each entry gives the check that tells you what is actually wrong, tied to
how the current build stores and analyzes data.

## Server says the shared FFmpeg runtime is missing

Run `dj-sim doctor` first. You need FFmpeg `8.1.1` as a full shared build, which means `ffmpeg.exe`
alongside `avcodec-62.dll`, `avformat-62.dll`, `avutil-60.dll`, `avfilter-11.dll`,
`swresample-6.dll`, and `swscale-9.dll`. Point `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` at that
library directory, or put the directory on `PATH`. A lone `ffmpeg.exe` will not do, because the main
application loads the shared libraries directly through TorchCodec. `dj-sim doctor` also confirms
that PyAV `17.1.0` is imported from the active Python environment. The project does not load either
runtime from `libs`.

```powershell
$env:DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR = 'C:\path\to\ffmpeg\bin'
dj-sim serve --host 127.0.0.1 --port 8765
```

## The selected library will not open

A library needs one `.sqlite` file with a valid `library` identity row. If the message reports an
incompatible legacy layout, leave the old files alone instead of editing them by hand. Stop the
server and every database tool, then run:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'
```

The migration keeps your original files in a timestamped backup directory and does not start
analysis.

## A model adapter cannot load its dependencies

Run `python -m pip check` in the same activated environment that runs `dj-sim`, then compare what is
installed against `pyproject.toml` and `uv.lock`. Update the related packages together, so the
adapter still gets the APIs, checkpoints, and output shapes it expects.

```powershell
python -m pip check
```

Restart `dj-sim serve` and any running Rhythm Lab process after you change the environment.

## Timeline, SONARA embedding, or fingerprint data is unavailable

Timeline collection remains disabled. A complete SONARA analysis stores its embedding in
`sonara_embeddings` and its versioned native-base64 acoustic fingerprint in `sonara_fingerprints`.
Neither raw value reaches track responses, and neither is a current UI, similarity, search, or
classifier input. The Audio Dedup tool is the fingerprint's one consumer: it reads stored
fingerprints for candidate retrieval and manual-review verification. Run normal SONARA analysis
again whenever any of its Core, embedding, or fingerprint rows is missing.

## A classifier is incompatible

Rebuild and promote an artifact whose ordered feature names and required inputs match your current
data. Classifier scoring stays database-only and remains scoped by `classifier_key`.

## One track fails ML analysis while the rest of the job succeeds

Each ML track passes through two decoders before it is failed. TorchCodec reads it first. If that
read fails, a tolerant PyAV decode over the same shared FFmpeg libraries drops the damaged packet
and keeps the valid frames around it. A `Track failed` event whose text names both a TorchCodec
failure and an FFmpeg fallback failure means neither decoder found usable audio, so the file itself
is the problem rather than the model or
the device. `[ffmpeg] Track analyzed` is the opposite result: the recovery decoder read the file. If
it had to drop damaged packets to do so, `logs/dj-track-similarity.log` carries one warning naming
the file and the number discarded. The app never rewrites the source file in either case; repair it
with your own tool if you want a clean copy.

## The app log no longer shows the HTTP requests I used to see

Uvicorn access records go to the console only, because the browser polls job endpoints
continuously and those lines otherwise fill `logs/dj-track-similarity.log`. Watch the server console
window for request traffic. See
[Runtime log](../reference/configuration.md#runtime-log) for the rest of what the file keeps and
drops.

## CUDA was requested but analysis fails

Run `dj-sim doctor`, then try `--device cpu`. If the CPU run succeeds, the problem lies in device
setup rather than the analysis workflow.
