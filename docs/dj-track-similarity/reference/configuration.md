# Configuration reference

> Audience: Users setting paths, ports, builds, and generated output locations.
> Goal: List the practical knobs exposed by the current repo.
> Type: reference

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` | Directory containing shared FFmpeg libraries; used after the project-local runtime and before `PATH` discovery |

The main application requires a system-available shared FFmpeg runtime. Its exact discovery order is:

1. Project-root `libs/ffmpeg`, when it contains a shared `avcodec` library.
2. `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`, when set.
3. The first `PATH` directory containing a shared `avcodec` library.

`libs/ffmpeg` is a gitignored local runtime directory. On Windows it normally contains
`avcodec-*.dll` alongside the dependent FFmpeg DLLs; Linux and macOS use the equivalent
`libavcodec.so*` or `libavcodec.*.dylib` library. If the environment variable points to another
directory, or no eligible library directory is available, server startup fails clearly.

The project does not version or vendor FFmpeg in the repository. The main application opens the
shared libraries directly through TorchCodec, so `ffmpeg.exe` or `ffprobe.exe` alone does not
satisfy this configuration and is irrelevant to the application's decoder selection.

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

The active main runtime log is `logs/dj-track-similarity.log`. If that file starts with an older
logged date when the app launches, the project runtime logs are archived with that date suffix and a
new active log is opened. A server that stays running through midnight keeps writing to the same
active log until it is restarted.

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
It uses project-root `libs/ffmpeg` when present, otherwise inherits the environment-variable and
`PATH` discovery order. It does not bundle or select FFmpeg.

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
