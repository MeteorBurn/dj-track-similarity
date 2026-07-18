# Reference

> Audience: Users who already know which command, endpoint, or control they need.
> Goal: Provide concise facts that match the current code surface.
> Type: reference index

Reference pages are for exact names, ranges, and boundaries. Use the guide and workflow pages when you want task flow.

## Pages

- [CLI](./cli.md): `dj-sim` commands and standalone helper commands.
- [API](./api.md): endpoint families and important payload constraints.
- [Database](./database.md): local SQLite state at a high level.
- [Configuration](./configuration.md): paths, ports, environment variables, and generated artifacts.
- [Analysis families](./analysis-families.md): what SONARA, MAEST, MERT, MuQ, CLAP, and classifiers write.
- [SONARA v0.2.4 contract](./sonara-v0-2-4-contract.md): exact signature, storage, scoring, and confidence rules.
- [Model citations and licenses](./model-citations.md): upstream sources, checkpoints, and license notes.
- [UI controls](./ui-controls.md): common control ranges and defaults.

## Source of truth

These pages are based on current source files such as `cli.py`, `api_schemas.py`, `api_routes_*.py`, `frontend/src/api.ts`, and the UI components. If source and docs disagree, trust the current source and fix the docs.
