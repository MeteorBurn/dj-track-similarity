# Release checklist

Walk through this before releasing a change that touches docs, the CLI, the API, or SONARA behavior.

## Privacy and hygiene

- No examples expose private paths, usernames, real track names, secrets, or local database locations. This includes drive letters from the author's own machine and any hard-coded default path a tool carries.
- Generated reports, SQLite files, logs, node_modules, and local model artifacts are not staged.

## Contract drift

Each item below names a mismatch that has already reached a release once.

- Every registered route appears in `reference/api.md`. Compare the `@app.get` and `@app.post` decorators across `api_routes_*.py` against the tables on that page.
- Every option on every command appears in `reference/commands.md` with its real range and default. Compare against the Typer signatures in `cli.py` and the argparse definitions under `tools/` and `scripts/`.
- Every environment variable the code reads appears in `reference/configuration.md`.
- Every table in `db_ddl.py` appears in `reference/database.md`.
- `uv.lock` and `pyproject.toml` agree about extras, so `uv sync --locked` succeeds.
- Any control named in the documentation exists in the UI, under the label the UI actually shows.
- Any safety gate described in the documentation exists in code. A phrase, a prompt, or a confirmation that no source file contains must be removed rather than softened.

## Behavior

- CLI docs use the unified `dj-sim analyze` command.
- Frontend and docs builds ran when touched.
- Focused tests cover touched behavior.
- SONARA decode, requested fields, output storage, and current tested dependency agree with `sonara_runtime.py` and `sonara_features.py`.
- A SONARA semantic change also reviews database structure, classifier feature recipes, optional reanalysis, and focused SONARA tests.
- Sidebar entries and local links include every new documentation page, and no sidebar entry points at a page that was removed.

## Safety audit

Review any code path that writes audio tags or deletes audio. Also check relocation, analysis reset, and database clear paths.
