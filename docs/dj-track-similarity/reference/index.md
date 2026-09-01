# Reference

Reference pages state contracts exhaustively. Use the guide and workflow pages when you want task
flow instead.

## Pages

- [Commands and arguments](./commands.md): the complete `dj-sim`, launcher, tool, and script command line, with every range and default.
- [API](./api.md): every registered HTTP route, with payload constraints and status codes.
- [Database](./database.md): the SQLite tables, plus the connection policy and the write boundaries.
- [Configuration](./configuration.md): environment variables, browser storage keys, paths, ports, and build commands.
- [Analysis families](./analysis-families.md): what SONARA, MAEST, MERT, MuQ, MuQ-MuLan, CLAP, and classifiers read and write.
- [SONARA integration](./sonara-integration.md): decoding, Direct and Staged capture, and the storage boundary.
- [Model citations and licenses](./model-citations.md): upstream sources, checkpoints, and license notes.
- [UI controls](./ui-controls.md): every browser control, with the Russian label on screen.

## Language

The browser UI mixes Russian and English labels. The documentation is English throughout and names
every control by its English name, whichever way its label reads on screen. The full mapping lives
in the [UI language glossary](../help/ui-language.md).

## Source of truth

These pages are based on current source files such as `cli.py`, `api_schemas.py`, `api_routes_*.py`,
`db_ddl.py`, `frontend/src/api.ts`, and the UI components. If source and docs disagree, trust the
current source and fix the docs.
