# Configuration reference

Exact names, ports, paths, and build commands. Look here when you need the value rather than the
explanation.

## Environment variables

Nine variables affect the Python side. None of them is required for a default local run.

| Variable | Read by | Purpose |
| --- | --- | --- |
| `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` | `ffmpeg_runtime.py` | Directory containing a complete FFmpeg `8.1.1` shared runtime. Checked before `PATH` discovery. When it is set and invalid, startup fails instead of falling back. |
| `DJ_TRACK_SIMILARITY_LOG` | `logging_config.py` | Override the active log file path. Default: `logs/dj-track-similarity.log`. |
| `DJ_TRACK_SIMILARITY_LOG_LEVEL` | `logging_config.py` | Override the file-log level. `dj-sim serve --log-level` sets the same thing per run. |
| `DJ_TRACK_SIMILARITY_LOG_TRACK_EVENTS` | `logging_config.py` | Include successful per-track events in the file log, matching `dj-sim serve --log-track-events`. |
| `DJ_TRACK_SIMILARITY_ANALYSIS_DIAGNOSTICS` | `logging_config.py` | Write decoder and batch timing diagnostics, matching `dj-sim analyze --diagnostics`. |
| `DJ_TRACK_SIMILARITY_LAUNCHER_HOST` | `scripts/run_server_launcher.py` | Bind address the launcher passes to `dj-sim serve`. Missing host or port exits `2`. |
| `DJ_TRACK_SIMILARITY_LAUNCHER_PORT` | `scripts/run_server_launcher.py` | Bind port the launcher passes to `dj-sim serve`. |
| `DJ_TRACK_SIMILARITY_LAUNCHER_DATABASE` | `scripts/run_server_launcher.py` | Database path the launcher appends as `--db` when the prompt supplied one. |
| `DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_DEV` | `scripts/run_server_launcher.py` | Selects the npm script for the Vite child, `dev` or `dev:lan`. |
| `DJ_TRACK_SIMILARITY_LAUNCHER_FRONTEND_HOST` | `scripts/run_server_launcher.py` | Host the Vite child binds to. |

`run_server.cmd` sets the five launcher variables from its own prompts or arguments, so setting them
by hand is only useful when starting `scripts/run_server_launcher.py` directly.

The project also writes one variable rather than reading it. SONARA Staged Mode sets
`RAYON_NUM_THREADS` inside each worker process from the Threads setting, so a value inherited from
your shell is replaced in those processes.

Two more variables belong to separate tools:

| Variable | Read by | Purpose |
| --- | --- | --- |
| `METADATA_ENRICHMENT_NODE` | `tools/audio-online` | Node executable for XLSX export. Falls back to `node` on `PATH`. `--node-executable` overrides it. |
| `METADATA_ENRICHMENT_NODE_MODULES` | `tools/audio-online` | Node module directory for XLSX export. `--node-modules` overrides it. XLSX output fails without one of the two. |
| `VALE_EXE` | `docs/dj-track-similarity/scripts/run-vale.mjs` | Explicit Vale binary. The resolver tries this first, then `vale` on `PATH`, then `C:\Utils\tools\vale\vale.exe` on Windows. |

## FFmpeg runtime

The main application requires FFmpeg `8.1.1` as a full shared runtime. Its exact discovery order is:

1. `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, when set to a valid complete runtime.
2. The first valid complete FFmpeg `8.1.1` runtime directory on `PATH`.

On Windows, the configured directory must contain `ffmpeg.exe`, `avcodec-62.dll`,
`avformat-62.dll`, `avutil-60.dll`, `avfilter-11.dll`, `swresample-6.dll`, and `swscale-9.dll`.
Linux and macOS use the equivalent shared-library names. A candidate directory must also have an
`ffmpeg` binary that reports exactly `8.1.1`. If the environment variable points to
another directory, or no eligible library directory is available, server startup fails clearly and
names the rejected candidates.

This validation runs while the application is being constructed, so an invalid runtime fails at
startup rather than at the first decode.

The project does not version or vendor FFmpeg in the repository. The main application opens the
shared libraries directly through TorchCodec, so `ffmpeg.exe` or `ffprobe.exe` alone does not
satisfy this configuration. PyAV is a base dependency pinned to `17.1.0` and must load from the
active Python environment. Use `dj-sim doctor` to inspect both runtimes.

## Browser storage keys

The UI keeps three values in browser `localStorage`. They are per-browser and per-profile, and
clearing site data resets them to the defaults below.

| Key | Holds | Default |
| --- | --- | --- |
| `dj-track-similarity.sonara-analysis-settings` | SONARA mode, Direct BatchSize, BPM range, and the Staged Processes, Threads, BatchSize, and StageSize | mode `direct`, BatchSize `8`, BPM `70..180`, Processes `4`, Threads `4`, Staged BatchSize `4`, StageSize `32` |
| `dj-track-similarity.ml-analysis-settings` | ML mode plus Staged Workers and StageSize | mode `direct`, Workers `4`, StageSize `64` |
| `dj-track-similarity-theme` | light or dark appearance for the top-bar toggle | follows the stored value, otherwise the browser preference |

Both staging folder paths are deliberately left out of storage. A staging folder receives temporary
read-only copies of your audio, so the UI asks for it again in every session and overwrites any
previously stored value on the next save.

## Default paths

| State | Default or common path |
| --- | --- |
| Default non-server CLI database | `dj-track-similarity.sqlite` when `--db` is omitted |
| Initial `serve` database | None when `--db` is omitted |
| Example project database | `.\data\library.sqlite` |
| No-argument Windows launcher suggestion | `database\volumes.sqlite` under the repository root |
| Runtime logs | `logs/` |
| Audio Doctor reports/state/backups | `tools/audio-doctor/data/` |
| Audio Dedup reports | `tools/audio-dedup/data/reports/` |
| Rhythm Lab labels | `tools/rhythm-lab/database/rhythm_lab.sqlite` |
| Rhythm Lab profile data | `tools/rhythm-lab/profiles/<profile-key>/` |
| Promoted classifier models | `models/classifiers/<profile-key>/model.joblib` and `model.json` |
| Audio Online credentials | `tools/audio-online/config.toml`, ignored by Git |

Rhythm Lab uses `rhythm_lab.sqlite` as its single writable state database. When launched from the
main app, it reads tracks and analysis from the currently selected library database while
keeping profiles, labels, predictions, queues, and checkpoints in this Lab database.

Generated local artifacts are ignored by Git unless explicitly tracked by policy.

## Runtime log

The active main runtime log is `logs/dj-track-similarity.log`. If that file starts with an older
logged date when the app launches, the project runtime logs are archived with that date suffix and a
new active log is opened. One dated archive is kept. A server that stays running through midnight
keeps writing to the same active log until it is restarted, so the file also rolls over once it
passes 8 MiB and keeps one numbered backup, `dj-track-similarity.log.1`. Startup pruning matches
dated archives only and leaves the numbered backup alone.

The file holds the application's own records plus whatever the process writes to standard output and
standard error. Both streams are mirrored into it at `INFO`, because the libraries that print them
already state their own severity in the text. ANSI color codes are stripped before a line is
matched or stored.

Three kinds of console output are dropped instead of stored:

- Uvicorn HTTP access records, which stay on the console. The browser polls job endpoints while a
  job runs, and those records otherwise crowd out everything else in the file.
- Progress bars, including model weight loading and file-download redraws, which would otherwise be
  recorded once per redraw.
- The `LOAD REPORT` block that `transformers` prints when it loads a model, together with its table,
  separator row, and trailing notes. The filter applies to whichever model class was instantiated.

A scan or analysis failure for one track is written to the file once. The job event stream shown in
the browser process log is separate and unchanged. That stream keeps at most 200 events per job.

## Ports

| Service | Default |
| --- | ---: |
| Main backend/UI | `8765` |
| Vite frontend dev server | `5173` |
| Rhythm Lab | `8777` |

Check for existing listeners before starting another fixed-port process.

## Server commands

Local-only:

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

LAN:

```powershell
dj-sim serve --host 0.0.0.0 --port 8765
```

Windows helper:

```powershell
run_server.cmd
```

With no arguments, the launcher suggests `database\volumes.sqlite` under the repository root, then
prompts for local or LAN mode. It forwards the confirmed path only after both prompts complete.
It inherits the environment-variable and `PATH` discovery order. It does not bundle or select
FFmpeg.

For non-interactive use, run `run_server.cmd local --db .\database\volumes.sqlite` or replace `local`
with `lan`. Explicit mode commands use only the supplied arguments. Direct `dj-sim serve` commands
still create no database when `--db` is omitted and wait for a selection through the database API or
picker.

## Build commands

Frontend bundle:

```powershell
cd frontend
npm install
npm run build
```

Docs site:

```powershell
cd docs\dj-track-similarity
npm install --no-package-lock
npm run vale:sync
npm run check
```

The VitePress `base` is `/docs/` and the build output directory is `site`. The backend mounts that
same `site` folder at `/docs`, so the two values have to stay in agreement. When `site/` is absent,
`/docs/` returns a "Documentation is not built" page with status `503`.
