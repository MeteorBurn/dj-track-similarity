# Tags Metadata Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the metadata dialog render the requested `Tags` list, preserve filesystem casing in `tracks.file_path`, store one two-decimal duration value, and remove three unused tag fields from code and the real Core database.

**Architecture:** Keep presentation formatting in `TrackMetadataDialog.tsx`, keep `audio_duration_seconds` numeric and rounded at the persistence boundary, and keep case-insensitive Windows path identities transient in Python. Update the unversioned Core DDL and then rebuild the affected tables directly inside the original `volumes.sqlite` transaction without a backup or migration artifact.

**Tech Stack:** Python 3.10, SQLite/FTS5, FastAPI/Pydantic, React 19, TypeScript 5.9, Node's built-in test runner, pytest.

## Global Constraints

- Work directly on `C:\projects\dj-track-similarity\database\volumes.sqlite`.
- Do not create a database backup, copy, migration, schema version, or contract version.
- Do not add `file_path_key` or any other persisted normalized-path column.
- Preserve unrelated untracked files and generated output.
- Do not read, modify, retag, move, or delete source audio.
- Apply real-database DDL and data changes in one `BEGIN IMMEDIATE` transaction and roll back on any failure.
- Preserve the existing `track_id`, `track_uuid`, `content_generation`, analysis rows, likes, feedback, and artifact sidecar identity.

---

### Task 1: Remove unused stored tags and normalize duration persistence

**Files:**
- Modify: `tests/test_db_ddl.py`
- Modify: `tests/test_scanner_database.py`
- Modify: `tests/test_track_repository.py`
- Modify: `tests/test_library_repository.py`
- Modify: `tests/test_api_tracks.py`
- Modify: `src/dj_track_similarity/db_ddl.py`
- Modify: `src/dj_track_similarity/db_schema.py`
- Modify: `src/dj_track_similarity/track_models.py`
- Modify: `src/dj_track_similarity/library_models.py`
- Modify: `src/dj_track_similarity/scanner.py`
- Modify: `src/dj_track_similarity/db_tracks.py`
- Modify: `src/dj_track_similarity/db_library_queries.py`
- Modify: `src/dj_track_similarity/db_search_fts.py`
- Modify: `src/dj_track_similarity/api_schemas.py`
- Modify: `src/dj_track_similarity/db_migration.py` only where its current target copies the removed fields

**Interfaces:**
- Consumes: `ScannedFile.audio_duration_seconds: float | None`
- Produces: `audio_duration_seconds` persisted as `round(value, 2)` and tag/API models without `catalog_number`, `isrc`, or `disc_number`

- [ ] **Step 1: Write failing schema and repository tests**

  Change the expected `file_tags` and FTS column sets to omit
  `catalog_number`, `isrc`, and `disc_number`. Add a real repository assertion:

  ```python
  mutation = database.upsert_scanned_track(
      file=ScannedFile(
          file_path=str(audio_path),
          file_size_bytes=1,
          file_modified_ns=1,
          audio_duration_seconds=247.368,
      ),
      tags=FileTags(title="Track"),
      scanned_at=_NOW,
  )
  with database.connect() as connection:
      stored = connection.execute(
          "SELECT audio_duration_seconds FROM tracks WHERE track_id = ?",
          (mutation.identity.track_id,),
      ).fetchone()[0]
  assert stored == 247.37
  ```

- [ ] **Step 2: Run the focused tests and verify RED**

  Run:

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest `
    tests\test_db_ddl.py `
    tests\test_scanner_database.py `
    tests\test_track_repository.py `
    tests\test_library_repository.py `
    tests\test_api_tracks.py `
    --override-ini addopts=
  ```

  Expected: failures show the three old fields remain and duration is stored
  with more than two decimal places.

- [ ] **Step 3: Implement the minimal persistence changes**

  - Remove the three fields from the current DDL, structural column maps,
    FTS statements, Python tag models, scanner aliases, SQL row projections,
    API response model, and current-target migration copying.
  - Normalize a finite positive duration once at the persistence boundary:

    ```python
    normalized_duration = (
        None
        if file.audio_duration_seconds is None
        else round(float(file.audio_duration_seconds), 2)
    )
    ```

  - Use the normalized value for inserts, updates, returned file facts, and
    equality decisions.
  - Add the current DDL check:

    ```sql
    CHECK(
        audio_duration_seconds IS NULL
        OR (
            audio_duration_seconds > 0
            AND audio_duration_seconds = round(audio_duration_seconds, 2)
        )
    )
    ```

- [ ] **Step 4: Run the focused tests and verify GREEN**

  Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Inspect the diff for removed-field leaks**

  Run:

  ```powershell
  rg -n "catalog_number|isrc|disc_number" src frontend\src tests
  ```

  Every remaining match must be an explicitly retained historical fixture;
  otherwise remove it and rerun the focused tests.

---

### Task 2: Preserve display-path casing without a stored identity key

**Files:**
- Modify: `tests/test_scanner_runtime.py`
- Modify: `tests/test_scanner_database.py`
- Modify: `tests/test_track_repository.py`
- Modify: `src/dj_track_similarity/db_tracks.py`
- Modify: `src/dj_track_similarity/scanner.py`
- Modify: `src/dj_track_similarity/scan_jobs.py`

**Interfaces:**
- Consumes: filesystem-discovered `Path`
- Produces: `tracks.file_path` as resolved POSIX text with filesystem casing; `ordinal_path_key()` remains a transient comparison helper

- [ ] **Step 1: Write failing path-casing tests**

  Add a test with a mixed-case path and assert:

  ```python
  stored = connection.execute(
      "SELECT file_path FROM tracks WHERE track_id = ?",
      (mutation.identity.track_id,),
  ).fetchone()[0]
  assert stored == mixed_case_path.resolve().as_posix()
  assert stored != stored.lower()
  ```

  Add a rescan assertion showing unchanged content refreshes stored casing
  without creating a second row. Retain the existing
  `ordinal_path_key(..., windows=True)` Unicode identity test.

- [ ] **Step 2: Run the focused path tests and verify RED**

  Run:

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest `
    tests\test_scanner_runtime.py `
    tests\test_scanner_database.py `
    tests\test_track_repository.py `
    --override-ini addopts=
  ```

  Expected: the stored path is lowercase before implementation.

- [ ] **Step 3: Separate display path from transient identity**

  Introduce a case-preserving resolver:

  ```python
  def resolved_file_path(path: str | Path) -> str:
      return Path(path).expanduser().resolve(strict=False).as_posix()

  def canonical_file_path(path: str | Path) -> str:
      return ordinal_path_key(resolved_file_path(path))
  ```

  Store `resolved_file_path(...)` in `tracks.file_path`. Use
  `canonical_file_path(...)` only for transient maps and comparisons.
  Update repository lookup helpers to compare canonical keys under
  `_write_lock`, while preserving exact stored paths for filesystem access.
  When an unchanged scan finds the same identity, update `file_path` to the
  newly discovered case-preserving spelling.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run the Step 2 command. Expected: all selected tests pass and no persisted
  normalized key exists.

---

### Task 3: Render the final Tags block

**Files:**
- Modify: `frontend/tests/metadataReference.test.mjs`
- Modify: `frontend/tests/sonaraFeatureLabels.test.mjs`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/TrackMetadataDialog.tsx`

**Interfaces:**
- Consumes: current `TrackDetail` with numeric file facts and RFC 3339 timestamps
- Produces: one ordered `primaryEntries` array matching the approved `Tags` list

- [ ] **Step 1: Write failing dialog-model tests**

  Set the fixture duration to `247.37`, use a mixed-case path, and assert the
  complete literal entry array:

  ```javascript
  assert.deepEqual(Array.from(model.primaryEntries), [
    ["Title", "Track"],
    ["Artist", "Artist"],
    ["Album", "Album"],
    ["Year", "2026"],
    ["Country", "UA"],
    ["Genre", "Breakbeat"],
    ["BPM", "128"],
    ["Key", "8A"],
    ["Label", "Label"],
    ["Audio Length", "4:07 (247.37 sec.)"],
    ["Audio Format", "FLAC"],
    ["Sample Rate", "48,000 Hz"],
    ["Bit Rate", "1,000 kbps"],
    ["Channels", "2"],
    ["Last Scanned", "24.07.2026 10:00:00"],
    ["Missing Since", "-"],
    ["File Name", "Artist - Track.flac"],
    ["File Size", "40.00 MB"],
    ["File Path", "D:/Music/Artist - Track.flac"],
  ]);
  ```

- [ ] **Step 2: Run the metadata tests and verify RED**

  Run:

  ```powershell
  node --test tests\metadataReference.test.mjs tests\sonaraFeatureLabels.test.mjs
  ```

  from `frontend`. Expected: order, combined duration, timestamp, and filename
  assertions fail against the current two-list implementation.

- [ ] **Step 3: Implement the requested presentation**

  - Rename the heading to `Tags`.
  - Build one ordered metadata array.
  - Remove frontend types for the three deleted tags.
  - Format duration with the existing rounded clock plus
    `${seconds.toFixed(2)} sec.`.
  - Parse valid RFC 3339 timestamps and render `DD.MM.YYYY HH:mm:ss` without
    fractions.
  - Derive `File Name` with `basename(track.file_path)`.
  - Keep the copy button only on `File Path`.
  - Do not render comment, track number, or tag-read time in this block.

- [ ] **Step 4: Run metadata tests, typecheck, and build**

  Run from `frontend`:

  ```powershell
  node --test tests\metadataReference.test.mjs tests\sonaraFeatureLabels.test.mjs
  npm run typecheck
  npm run build
  ```

  Expected: all commands exit zero.

---

### Task 4: Update the original real database in one transaction

**Files:**
- Modify in place: `database/volumes.sqlite`
- Do not create: backup databases, migration files, export files, or sidecar copies

**Interfaces:**
- Consumes: the approved current DDL and actual filesystem paths below `M:/Volumes`
- Produces: the same 3,017 identities with retained tags, rounded durations, case-preserving paths, and rebuilt FTS

- [ ] **Step 1: Prove source files are not modified**

  Capture only metadata needed for comparison:

  ```powershell
  Get-ChildItem -LiteralPath 'M:\Volumes' -Recurse -File |
    Measure-Object
  ```

  Do not open files for writing and do not invoke tag writers.

- [ ] **Step 2: Execute one bounded maintenance transaction**

  Use the toolkit SQLite engine plus a bounded Python casing map when needed.
  The transaction must:

  - `BEGIN IMMEDIATE`;
  - rebuild `tracks` with identical IDs and all retained columns;
  - write filesystem-cased paths when present and round durations to two decimals;
  - rebuild `file_tags` without the three removed columns;
  - recreate `track_search_fts` without those fields and repopulate it;
  - assert 3,017 `tracks`, 3,017 `file_tags`, and one FTS row per track;
  - commit only after all assertions pass; otherwise roll back.

- [ ] **Step 3: Verify the real database**

  Run read-only:

  ```sql
  PRAGMA integrity_check;
  PRAGMA foreign_key_check;
  SELECT COUNT(*) FROM tracks;
  SELECT COUNT(*) FROM file_tags;
  SELECT COUNT(*) FROM track_search_fts;
  SELECT COUNT(*) FROM tracks
  WHERE audio_duration_seconds IS NOT NULL
    AND audio_duration_seconds <> round(audio_duration_seconds, 2);
  ```

  Inspect `.schema tracks`, `.schema file_tags`, and
  `.schema track_search_fts`. Expected: integrity `ok`, no FK rows, counts
  preserved, no removed fields, no path-key field, and zero invalid durations.

---

### Task 5: Integrated verification and change review

**Files:**
- Review all changed source, test, design, and plan files
- Leave `frontend/dist`, caches, audio, and unrelated untracked paths untouched

**Interfaces:**
- Consumes: completed Tasks 1-4
- Produces: evidence-backed implementation ready for review

- [ ] **Step 1: Run focused backend regression**

  ```powershell
  & '.\.venv\Scripts\python.exe' -m pytest `
    tests\test_db_ddl.py `
    tests\test_scanner_runtime.py `
    tests\test_scanner_database.py `
    tests\test_track_repository.py `
    tests\test_library_repository.py `
    tests\test_api_tracks.py `
    --override-ini addopts=
  ```

- [ ] **Step 2: Run frontend regression**

  From `frontend`:

  ```powershell
  npm test
  npm run typecheck
  npm run build
  ```

- [ ] **Step 3: Inspect scope and whitespace**

  ```powershell
  git status --short
  git diff --check
  git diff --stat
  ```

  Confirm that no source audio, generated bundle, backup, or unrelated
  untracked file changed.

- [ ] **Step 4: Review the concrete diff**

  Use the project change-review workflow. Resolve every blocking finding and
  rerun the smallest relevant check before reporting completion.
