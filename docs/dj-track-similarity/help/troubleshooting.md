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

## The interface is in Russian and this page is in English

That is expected. The browser UI is written in Russian throughout, headings and tooltips alike, while
the documentation names controls in English. [UI language](./ui-language.md) maps every control both
ways. Model names, tab labels, mode names, and numeric field labels such as `Limit` and `Mode` stay
English on screen.

## The ML model checkboxes are greyed out

MAEST, MERT, MUQ, MULAN, and CLAP stay disabled until the library holds at least one current SONARA
row. Run SONARA first, on any number of tracks, and the checkboxes unlock. Starting an ML stage
through the API without that row is refused with `Сначала выполните SONARA-анализ хотя бы одного
трека` (run SONARA on at least one track first).

Only the SONARA checkbox is available on an unanalyzed library. This is the intended order, since
the ML stage plans its work against the SONARA rows.

## PROMPT search is greyed out

The PROMPT search button needs stored audio embeddings for the model selected in that tab. With
MuQ-MuLan selected and no `mulan_embeddings` rows, the button title reads
`<model> search requires stored audio embeddings` and asks you to run that analysis first.

Run the matching analysis family, then return to the tab. Switching the model select to the family
you already analysed also works, since the check is per family.

The same rule applies to the SIMILARITY tab, which disables its search with a per-family reason when
the selected model has zero embeddings.

## Staged Mode will not start

Staged Mode needs a folder before the run begins. The browser refuses a SONARA Staged run with an
empty folder and shows `Выберите папку staging перед запуском Staged Mode` (choose a staging folder
before starting Staged Mode). The backend refuses both SONARA and ML Staged runs the same way, and
also refuses a folder that does not exist.

The staging folder is deliberately not remembered between sessions, because it receives temporary
copies of your audio. Every session asks for it again. SONARA and ML keep separate folders. The
other Staged settings are remembered in browser storage.

## The BPM range is locked in the SONARA settings dialog

The BPM range belongs to the library rather than to a single run. Once one SONARA row exists, the
SONARA settings dialog (opened with `Настройки анализа SONARA` on the SONARA card) shows the stored
range and refuses a change, with the note `База уже проанализирована этим диапазоном. Чтобы задать
другой, сбросьте анализ SONARA.` (this database was analysed with this range, reset SONARA analysis
to choose another).

To move to a different range, reset SONARA analysis first, then set the range and analyse again. The
upper bound must be at least twice the lower one, because SONARA folds estimated tempos into the
range by octaves.

## `uv sync` cannot read the SONARA wheel

The `sonara` extra resolves through `[tool.uv.sources]` to a patched `0.3.6` wheel at a local path
rather than to a package index. On a machine without that file, `uv` reports that it cannot read the
source. Build the `0.3.6` wheel from the SONARA sources and point `[tool.uv.sources]` at your copy.

After installing, confirm the runtime before analyzing:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

Expect `0.3.6` or newer. Version `0.3.5` installs cleanly and then fails on the first analysis,
because it does not return the BPM range provenance that storage requires. Use `uv` rather than
`pip` for anything including the `ml` extra, because `pip` does not apply the PyTorch source
declared in `pyproject.toml`.

## Classifier scoring reports success and scores nothing

Scoring is incremental. The candidate query skips every track that already holds a row for that
classifier key, so a job started after a retrain finds zero work and completes.

Reset that classifier's scores first, then run scoring. The CLASS tab pairs a reset button with a
play button on each profile for exactly this.

A related trap: resetting SONARA does not delete classifier scores. They survive and go stale
silently. Reset the affected classifier keys yourself after a SONARA reset.

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
