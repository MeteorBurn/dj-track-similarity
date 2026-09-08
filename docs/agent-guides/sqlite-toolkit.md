# SQLite inspection and diagnostics

Read before inspecting, validating, comparing, querying, or maintaining a real project SQLite database. Use root safety rules for every access.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## SQLITE TOOLKIT

For SQLite inspection and diagnostics in this project, agents must use the
shared installation at `C:\Utils\tools\sqlite-toolkit`. This section is the
complete project usage guide: do not read that directory's `AGENTS.md` as a
prerequisite. Use the selected command's `--help` only when a needed option is
unclear. Invoke these verified absolute paths from PowerShell:

| Executable | Use |
|---|---|
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe` | Default for SQL, tables/schema/indexes, query plans, and exports |
| `C:\Utils\tools\sqlite-toolkit\bin\sqlite-utils.exe` | Discovery and JSON/CSV conversion when it simplifies the task |
| `C:\Utils\tools\sqlite-toolkit\bin\datasette.exe` | Interactive browsing when requested; bind to loopback |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_analyzer.exe` | Database size and storage analysis |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqldiff.exe` | Compare schema and data in two databases; review its output before applying SQL |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_rsync.exe` | Synchronization only when explicitly requested |

- Identify the exact database first, following [STRUCTURE](architecture.md#structure); never guess the
  current library. Resolve an existing path so a typo cannot create a new file.
- Start with `sqlite3 -readonly`, inspect tables/schema, and use `LIMIT` for
  exploratory queries. Use a consistent snapshot for comparisons of a live DB.
  Keep deterministic automation on `sqlite3`; use the other tools as needed.
- Follow [SAFETY INVARIANTS](../../AGENTS.md#safety-invariants) for application database access. Imports,
  migrations, destructive work, and synchronization require an explicit
  target and the prescribed backup or disposable copy. Toolkit availability is
  not authorization to change user data.
- For project integrity validation, use
  `db.connection.connect_database_read_only()` with the root `.venv` (it sets
  `PRAGMA query_only = ON` without enforcing WAL). A CLI `-readonly` integrity
  result alone does not replace the project's CHECK-constraint validation.
- Ordinary application startup is not a read-only database inspection:
  `LibraryDatabase.connect()` enforces WAL, and database selection can refresh
  `track_search_fts` through `ensure_search_index_current()`. Use the explicit
  read-only path for verification of a user library.
- These are shared external utilities. Keep application SQLite on the pinned
  project interpreter. Toolkit engines can differ; verify the actual engine
  when investigating compatibility.
  Do not add Toolkit packages to the project, activate its private environments,
  change PATH, or install/update tools as a prerequisite to routine use.

Read-only PowerShell example (replace the example path with the identified DB):

```powershell
$databasePath = (Resolve-Path -LiteralPath 'C:\path\selected.sqlite' -ErrorAction Stop).Path
$sqlite = 'C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe'
& $sqlite -readonly $databasePath '.tables'
& $sqlite -readonly $databasePath '.schema'
& $sqlite -readonly -header -column $databasePath 'SELECT name, type FROM sqlite_schema ORDER BY name LIMIT 50;'
```
