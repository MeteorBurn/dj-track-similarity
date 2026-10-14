# SQLite persistence, inspection and diagnostics

Read before inspecting, validating, comparing, querying, or maintaining a real
project SQLite database, or changing persistence, stored identities, database
switching, migrations, or deferred writes. Use root safety rules for every access.

Project instructions: [AGENTS.md](../../AGENTS.md). Commands and inline code paths
are relative to the repository root unless explicitly absolute; Markdown links
are relative to this file. These guides are read by task, not imported as a batch.

## PERSISTENCE CONTRACTS

- Use `LibraryDatabase` for the main application's library reads and writes;
  explicit read-only inspection follows [SQLITE TOOLKIT](#sqlite-toolkit).
  Preserve WAL, the busy timeout and `BEGIN IMMEDIATE` on library writes: each
  write is one transaction that runs its identity and freshness checks (track
  ID/UUID, file facts, locked settings) inside it, never before it. SQLite's
  write lock guards normal library mutations across the server, CLI, Rhythm
  Lab and scripts; the per-path `RLock` orders threads of one process, and the
  server's job exclusion does not see another process's jobs. Fresh database
  creation also uses the bootstrap file lock in
  `src/dj_track_similarity/db/connection.py`; preserve that separate boundary.
- Rhythm Lab keeps its existing `SourceDatabase` boundary: query-only library
  reads, a read-only `ATTACH` that syncs `track_sightings` into the lab
  database, and the explicit liked-track toggle with its in-transaction
  ID/UUID checks. It switches libraries at runtime: the launcher's catalog pin
  covers only the first open, a switch is refused while a profile operation
  runs, and the main app verifies the catalog a managed lab returns after a
  switch. Its other state remains separate from the source library.
  This exception does not authorize additional direct library writes.
- Real-database destructive work requires a backup or disposable copy plus
  integrity and orphan checks.
- Rhythm Lab labels, predictions, the label queue and review collections are
  keyed by `content_key` = `"sfp<version>:" + sha256("sfp:<version>:" +
  SONARA fingerprint bytes)`, so fingerprint bytes and version are preserved
  identities. SONARA supplies `fingerprint_version`; the project never assigns
  it. A library whose version differs from the stored sightings is refused
  rather than synced, and re-keying labels onto a new version is not
  implemented. A pre-content-identity lab database is rejected on open.
- For model output storage, readiness and validation, also read
  [Model layer](model-layer.md), including its SONARA and ML run contracts.

## SQLITE TOOLKIT

For SQLite inspection and diagnostics in this project, agents must use the
shared installation at `C:\Utils\tools\sqlite-toolkit`. This section is the
complete project usage guide: do not read that directory's `AGENTS.md` as a
prerequisite. Use the selected command's `--help` only when a needed option is
unclear. Invoke the selected executable by its absolute path from PowerShell;
check that it exists instead of silently substituting another installation.

| Executable | Use |
|---|---|
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe` | Default for SQL, tables/schema/indexes, query plans, and exports |
| `C:\Utils\tools\sqlite-toolkit\bin\sqlite-utils.exe` | Discovery and JSON/CSV conversion when it simplifies the task |
| `C:\Utils\tools\sqlite-toolkit\bin\datasette.exe` | Interactive browsing when requested; bind to loopback |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_analyzer.exe` | Database size and storage analysis |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqldiff.exe` | Compare schema and data in two databases; review its output before applying SQL |
| `C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3_rsync.exe` | Synchronization only when explicitly requested |

### Read-only inspection

- Identify the exact database under [AGENTS.md](../../AGENTS.md#execution-and-scope).
  Resolve an existing path so a typo cannot create a new file.
- Start with `sqlite3 -readonly`, inspect tables/schema, and use `LIMIT` for
  exploratory queries. Use a consistent snapshot for comparisons of a live DB.
  Keep deterministic automation on `sqlite3`; use the other tools as needed.
- For project integrity validation, use
  `db.connection.connect_database_read_only()` with the root `.venv` (it sets
  `PRAGMA query_only = ON` without enforcing WAL). This opens a connection; it
  does not itself validate the database. `DatabaseValidator` in
  `src/dj_track_similarity/db/validation.py` performs the integrity and foreign-key
  checks. A CLI `-readonly` integrity result alone does not replace the project's
  CHECK-constraint validation.
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
$ErrorActionPreference = 'Stop'
$databasePath = (Resolve-Path -LiteralPath 'C:\path\selected.sqlite' -ErrorAction Stop).Path
$sqliteTool = 'C:\Utils\tools\sqlite-toolkit\native\windows-x64\sqlite3.exe'
$inspectionQueries = @('.tables', '.schema', 'SELECT name, type FROM sqlite_schema ORDER BY name LIMIT 50;')
foreach ($inspectionQuery in $inspectionQueries) {
    & $sqliteTool -readonly -header -column $databasePath $inspectionQuery
    if ($LASTEXITCODE -ne 0) { throw 'Read-only SQLite inspection failed.' }
}
```

### Authorized maintenance

- Follow [SAFETY INVARIANTS](../../AGENTS.md#safety-invariants) for application
  database access. Imports, migrations, destructive work and synchronization
  require an explicit target and the prescribed backup or disposable copy.
  Toolkit availability is not authorization to change user data.
- Project optimization (FTS merge, `VACUUM`, `ANALYZE`) is
  `dj-sim optimize-database --db <path>`. It verifies, backs up and writes the
  file, so run `--dry-run` first and use it only on an explicitly requested
  target. Do not use this write workflow as an inspection shortcut.
