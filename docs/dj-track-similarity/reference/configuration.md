# Configuration reference

> Audience: Users setting paths, ports, builds, and generated output locations.
> Goal: List the practical knobs exposed by the current repo.
> Type: reference

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DJ_TRACK_SIMILARITY_FFMPEG` | Full path to ffmpeg executable when `ffmpeg` is not on `PATH` |

If the variable is set but points to a missing file, server startup fails clearly.

## Default paths

| State | Default or common path |
| --- | --- |
| Default non-server CLI database | `dj-track-similarity.sqlite` when `--db` is omitted |
| Initial `serve` database | None when `--db` is omitted |
| Example project database | `.\data\library.sqlite` |
| No-argument Windows launcher suggestion | `C:\db\volumes.sqlite` |
| Runtime logs | `logs/` |
| Audio Doctor reports/state/backups | `tools/audio-doctor/data/` |
| Audio Dedup reports | `tools/audio-dedup/data/reports/` |
| Rhythm Lab labels | `tools/rhythm-lab/data/rhythm_lab.sqlite` |
| Rhythm Lab artifacts | `tools/rhythm-lab/artifacts/` |
| Promoted classifier models | `models/classifiers/<artifact-prefix>/` |
| Persistent ANN sidecars | `.dj-track-similarity-indexes/` beside the selected DB by default |

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

With no arguments, the launcher prompts for a database path with `C:\db\volumes.sqlite` as the shown
default, then prompts for local or LAN mode. It forwards the confirmed path only after both prompts
complete.

For non-interactive use, run `run_server.cmd local --db C:\db\volumes.sqlite` or replace `local` with
`lan`. Explicit mode commands use only the supplied arguments. Direct `dj-sim serve` commands still
create no database when `--db` is omitted and wait for a selection through the database API or picker.

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
