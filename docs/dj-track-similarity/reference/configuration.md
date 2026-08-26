# Configuration reference

Exact names, ports, paths, and build commands. Look here when you need the value rather than the
explanation.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` | Directory containing a complete FFmpeg `8.1.1` shared runtime; used before `PATH` discovery |

The main application requires FFmpeg `8.1.1` as a full shared runtime. Its exact discovery order is:

1. `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, when set to a valid complete runtime.
2. The first valid complete FFmpeg `8.1.1` runtime directory on `PATH`.

On Windows, the configured directory must contain `ffmpeg.exe`, `avcodec-62.dll`,
`avformat-62.dll`, `avutil-60.dll`, `avfilter-11.dll`, `swresample-6.dll`, and `swscale-9.dll`.
Linux and macOS use the equivalent shared-library names. If the environment variable points to
another directory, or no eligible library directory is available, server startup fails clearly.

The project does not version or vendor FFmpeg in the repository. The main application opens the
shared libraries directly through TorchCodec, so `ffmpeg.exe` or `ffprobe.exe` alone does not
satisfy this configuration. PyAV is a base dependency pinned to `17.1.0` and must load from the
active Python environment. Use `dj-sim doctor` to inspect both runtimes.

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
| Promoted classifier models | `models/classifiers/<artifact-prefix>/` |
| Persistent ANN sidecars | `.dj-track-similarity-indexes/` beside the selected DB by default |

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
the browser process log is separate and unchanged.

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

The docs route `/docs/` returns a clear "Documentation is not built" page when `docs/dj-track-similarity/site/` is absent.
