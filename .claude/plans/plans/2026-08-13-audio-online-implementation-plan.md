# Audio Online Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone `tools/Audio-Online/` CLI that obtains independent online metadata evidence and creates one styled XLSX `Metadata` sheet.

**Architecture:** Python owns config, input normalization, read-only SQLite evidence, candidate matching, source adapters, and the report contract. An internal Node bridge uses `@oai/artifact-tool` for XLSX import and authoring. Neither layer writes the main database or audio tags.

**Tech Stack:** Python 3.10 standard library and Mutagen, SQLite, pytest, Node.js, `@oai/artifact-tool`.

## Global Constraints

- Change only `tools/Audio-Online/`; do not add API routes, frontend work, migrations, database writes, or tag writes.
- `--db` opens SQLite read-only and associates local data only through exact `tracks.file_path`.
- `config.toml` and OAuth data stay in `tools/Audio-Online/`, are ignored by Git, and are never logged or put into XLSX.
- Use only documented access. Source statuses are `matched`, `no_match`, `not_configured`, `unavailable`, or `error`; one source never stops the run.
- The only worksheet is `Metadata`. A track occupies one vertical block. Columns are `Field`, `Local tags`, Discogs, MusicBrainz, Last.fm, Beatport, then `MAEST` last.
- Rows are `Track Name`, `Title`, `Artist`, `Album`, `Year`, `Country`, `Label`, `Genre`, `Style`, `Tags`, and `Duration`.
- Join all multi-values with `; `. MAEST displays exactly the top three stored labels as rounded whole percentages in `Genre`; its `Style` and `Tags` cells are empty.
- All workbook import/output uses `@oai/artifact-tool`; do not add `openpyxl`, `xlsxwriter`, or `pandas.ExcelWriter`.
- Use fixture payloads, temporary SQLite/WAV/XLSX files, and no real credentials or network calls in tests.

---

## File map

- `metadata_enrichment_cli.py`: only the executable `argparse` entrypoint.
- `metadata_enrichment/models.py`: frozen report and source domain types.
- `config.py`, `inputs.py`, `local_library.py`, `matching.py`, `http.py`, `sources.py`, `auth.py`, `report.py`: one responsibility each.
- `discogs.py`, `musicbrainz.py`, `lastfm.py`, `beatport.py`: independent adapter modules.
- `workbook_bridge.mjs`: two Node commands, `read` and `write`, backed by `@oai/artifact-tool`.
- `tests/`: focused pytest files; `workbook_bridge.test.mjs` is the bridge test.
- `.gitignore`, `config.example.toml`, `README.md`: local credential protection and user instructions.

### Task 1: Models, safe config, and CLI shell

**Files:**
- Create: `tools/Audio-Online/metadata_enrichment/__init__.py`
- Create: `tools/Audio-Online/metadata_enrichment/models.py`
- Create: `tools/Audio-Online/metadata_enrichment/config.py`
- Create: `tools/Audio-Online/metadata_enrichment_cli.py`
- Create: `tools/Audio-Online/config.example.toml`
- Create: `tools/Audio-Online/.gitignore`
- Test: `tools/Audio-Online/tests/test_config.py`

**Interfaces:**
- `TrackInput`, `SourceRecord`, `SourceResult`, `TrackReport`, and `ToolConfig` are frozen dataclasses.
- `load_config(path: Path) -> ToolConfig`; `save_auth_data(path: Path, source: str, values: Mapping[str, str]) -> None`.
- `main(argv: Sequence[str] | None = None) -> int` exposes `enrich` and `authorize`.

- [ ] **Step 1: Write the failing tests**

```python
def test_unknown_configured_source_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[sources.unknown]\ntoken = 'secret'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported source"):
        load_config(path)


def test_auth_writer_never_prints_secret(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save_auth_data(tmp_path / "config.toml", "lastfm", {"session_key": "not-for-output"})

    assert "not-for-output" not in capsys.readouterr().out
```

- [ ] **Step 2: Verify red**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_config.py -q`

Expected: FAIL because package modules do not exist.

- [ ] **Step 3: Implement minimal config and command dispatch**

Use `tomllib` to read, validate only `discogs`, `musicbrainz`, `lastfm`, and `beatport`, and write deterministic escaped TOML without exposing secrets in dataclass reprs. Add `config.toml` and `auth*.toml` to the tool-local ignore file. Add `argparse` commands only; they call injected functions so imports have no network side effects.

- [ ] **Step 4: Verify green**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_config.py -q
.\.venv\Scripts\python.exe .\tools\Audio-Online\metadata_enrichment_cli.py --help
```

Expected: test passes and help lists `enrich`, `authorize`, and no credentials.

- [ ] **Step 5: Commit**

```powershell
git add tools/Audio-Online
git commit -m "feat: scaffold Audio Online metadata tool"
```

### Task 2: Input readers and exact local evidence

**Files:**
- Create: `tools/Audio-Online/metadata_enrichment/inputs.py`
- Create: `tools/Audio-Online/metadata_enrichment/local_library.py`
- Test: `tools/Audio-Online/tests/test_inputs.py`
- Test: `tools/Audio-Online/tests/test_local_library.py`

**Interfaces:**
- `load_tracks(path: Path, *, xlsx_reader: Callable[[Path], list[dict[str, str]]]) -> list[TrackInput]`.
- `read_local_evidence(db_path: Path, track: TrackInput) -> LocalEvidence`.
- `LocalEvidence(file_tags: tuple[str, ...], maest: tuple[tuple[str, float], ...], matched_path: str | None)`.

- [ ] **Step 1: Write failing tests**

```python
def test_text_reader_accepts_hyphen_and_em_dash(tmp_path: Path) -> None:
    path = tmp_path / "tracks.txt"
    path.write_text("Artist A - Title A\nArtist B — Title B\n", encoding="utf-8")

    assert [item.track_name for item in load_tracks(path)] == [
        "Artist A — Title A", "Artist B — Title B"
    ]


def test_local_reader_uses_exact_file_path_and_keeps_three_maest_scores(tmp_path: Path) -> None:
    db = create_db(tmp_path, file_path=r"C:\music\one.flac")
    evidence = read_local_evidence(db, TrackInput(file_path=Path(r"C:\music\one.flac")))

    assert evidence.file_tags == ("Electronic", "Dance")
    assert evidence.maest[:3] == (("House", 0.81), ("Techno", 0.64), ("Electronic", 0.52))
```

- [ ] **Step 2: Verify red**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_inputs.py tools\Audio-Online\tests\test_local_library.py -q`

Expected: FAIL because the readers do not exist.

- [ ] **Step 3: Implement inputs and DB reader**

Read folder tags with Mutagen; read CSV using `csv.DictReader`; parse M3U `#EXTINF` plus file lines; dispatch XLSX import to the Node bridge. Recognize case-insensitive headers `track name`, `title`, `artist`, `album`, `year`, `country`, `label`, `duration`. Connect via `sqlite3.connect("file:<absolute-path>?mode=ro", uri=True)`, join `tracks`, `tags`, and `maest_genres` by `tracks.file_path = ?`, parse JSON, and never fuzzy-match a DB row.

- [ ] **Step 4: Verify green**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_inputs.py tools\Audio-Online\tests\test_local_library.py -q
rg -n "mode=ro|tracks\.file_path|maest_genres" tools/Audio-Online/metadata_enrichment
```

Expected: tests pass and no SQLite write SQL exists.

- [ ] **Step 5: Commit**

```powershell
git add tools/Audio-Online
git commit -m "feat: read Audio Online inputs and local genres"
```

### Task 3: Source protocol, deterministic matching, and safe transport

**Files:**
- Create: `tools/Audio-Online/metadata_enrichment/matching.py`
- Create: `tools/Audio-Online/metadata_enrichment/http.py`
- Create: `tools/Audio-Online/metadata_enrichment/sources.py`
- Test: `tools/Audio-Online/tests/test_matching.py`
- Test: `tools/Audio-Online/tests/test_http.py`

**Interfaces:**
- `score_candidate(track: TrackInput, candidate: SourceRecord) -> MatchAssessment`.
- `MetadataSource.fetch(track: TrackInput, client: HttpClient) -> SourceResult`.
- `HttpClient.get_json(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> Mapping[str, object]`.

- [ ] **Step 1: Write failing tests**

```python
def test_exact_title_artist_album_and_duration_is_high_confidence() -> None:
    assessment = score_candidate(
        TrackInput(title="Title", artist="Artist", album="Album", duration_seconds=402),
        SourceRecord(title="Title", artist="Artist", album="Album", duration_seconds=401),
    )

    assert assessment.confidence == "high"
    assert assessment.evidence == ("title exact", "artist exact", "album exact", "duration within 2s")


def test_source_error_does_not_block_next_source() -> None:
    results = collect_source_results(track, (ErroringSource(), MatchingSource()), FakeClient())

    assert [item.status for item in results] == ["error", "matched"]
```

- [ ] **Step 2: Verify red**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_matching.py tools\Audio-Online\tests\test_http.py -q`

Expected: FAIL because matching and transport are absent.

- [ ] **Step 3: Implement minimal behavior**

Normalize with Unicode normalization, casefold, collapsed whitespace, and removed punctuation. Score exact title +4, artist +4, album +1, year +1, duration within 2 s +1; use high for 8+, medium for 6–7, low otherwise. Missing artist/title or a zero-score candidate is `no_match`. Limit each adapter serially, retry only 429 and 5xx twice with capped backoff, and redact every credential from errors.

- [ ] **Step 4: Verify green**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_matching.py tools\Audio-Online\tests\test_http.py -q`

Expected: all tests pass and persistent retryable responses make exactly three attempts.

- [ ] **Step 5: Commit**

```powershell
git add tools/Audio-Online
git commit -m "feat: add Audio Online matching contract"
```

### Task 4: Official adapters and authorization

**Files:**
- Create: `tools/Audio-Online/metadata_enrichment/discogs.py`
- Create: `tools/Audio-Online/metadata_enrichment/musicbrainz.py`
- Create: `tools/Audio-Online/metadata_enrichment/lastfm.py`
- Create: `tools/Audio-Online/metadata_enrichment/beatport.py`
- Create: `tools/Audio-Online/metadata_enrichment/auth.py`
- Test: `tools/Audio-Online/tests/test_sources.py`
- Test: `tools/Audio-Online/tests/test_auth.py`

**Interfaces:**
- `source_registry(config: ToolConfig) -> tuple[MetadataSource, ...]` returns Discogs, MusicBrainz, Last.fm, Beatport.
- `authorize_source(source: str, config_path: Path, *, opener: Callable[[str], None], input_fn: Callable[[str], str]) -> str`.

- [ ] **Step 1: Write failing fixture tests**

```python
def test_discogs_preserves_genres_and_styles_in_separate_fields() -> None:
    result = DiscogsSource(token="token").fetch(track, FakeClient(discogs_release_fixture))

    assert result.record.genres == ("Electronic", "Dance")
    assert result.record.styles == ("Melodic Techno", "Progressive House")


def test_musicbrainz_uses_one_second_interval_without_credentials() -> None:
    assert MusicBrainzSource(user_agent="AudioOnline/0.1 (local@example.invalid)").minimum_interval_seconds == 1.0


def test_lastfm_needs_api_key_for_top_tags() -> None:
    assert LastFmSource(api_key=None).fetch(track, FakeClient({})).status == "not_configured"


def test_beatport_without_approved_access_is_unavailable_not_scraped() -> None:
    assert BeatportSource(access_token=None, search_url=None).fetch(track, FakeClient({})).status == "unavailable"
```

- [ ] **Step 2: Verify red**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_sources.py tools\Audio-Online\tests\test_auth.py -q`

Expected: FAIL because adapters are absent.

- [ ] **Step 3: Implement only documented access paths**

Discogs uses configured personal-token database search plus release detail and keeps `genres` distinct from `styles`. MusicBrainz uses public `/ws/2/recording/` JSON, a meaningful configured User-Agent, and the documented 1 Hz ceiling. Last.fm uses `track.getInfo` and `track.getTopTags` with its API key, mapping community values to `Tags`; its authorization command exchanges a user-approved token for a session key only after provider confirmation. Beatport uses only an operator-configured official catalog endpoint and bearer token; without both it returns `unavailable` and never fetches storefront HTML. Unsupported `authorize` sources state that fact.

- [ ] **Step 4: Verify green**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_sources.py tools\Audio-Online\tests\test_auth.py -q
.\.venv\Scripts\python.exe .\tools\Audio-Online\metadata_enrichment_cli.py authorize beatport --config .\tools\Audio-Online\config.example.toml
```

Expected: tests pass; the CLI reports missing approved configuration without a secret.

- [ ] **Step 5: Commit**

```powershell
git add tools/Audio-Online
git commit -m "feat: add Audio Online source adapters"
```

### Task 5: Workbook bridge and report rendering

**Files:**
- Create: `tools/Audio-Online/metadata_enrichment/report.py`
- Create: `tools/Audio-Online/workbook_bridge.mjs`
- Create: `tools/Audio-Online/workbook_bridge.test.mjs`
- Test: `tools/Audio-Online/tests/test_report.py`

**Interfaces:**
- `build_report_contract(reports: Sequence[TrackReport], source_names: Sequence[str]) -> dict[str, object]`.
- `write_workbook(contract_path: Path, output_path: Path, *, node_executable: Path) -> None`.
- `node workbook_bridge.mjs read --input <tracks.xlsx> --output <tracks.json>`.
- `node workbook_bridge.mjs write --input <contract.json> --output <report.xlsx>`.

- [ ] **Step 1: Write failing tests**

```python
def test_contract_places_maest_last_and_joins_genres_with_semicolon() -> None:
    contract = build_report_contract([sample_track_report()], ["Discogs", "MusicBrainz", "Last.fm", "Beatport"])

    assert contract["columns"] == ["Field", "Local tags", "Discogs", "MusicBrainz", "Last.fm", "Beatport", "MAEST"]
    assert cell(contract, "Genre", "MAEST") == "House (81%); Techno (64%); Electronic (52%)"
```

```javascript
test("bridge creates only Metadata with Track Name and MAEST last", async () => {
  const workbook = await buildWorkbook(sampleContract);
  assert.deepEqual(workbook.worksheets.items.map((sheet) => sheet.name), ["Metadata"]);
  assert.equal(await cellText(workbook, "Metadata", "A3"), "Track Name");
});
```

- [ ] **Step 2: Verify red**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_report.py -q
& $env:METADATA_ENRICHMENT_NODE .\tools\Audio-Online\workbook_bridge.test.mjs
```

Expected: both tests fail because contract builder and bridge do not exist.

- [ ] **Step 3: Implement JSON bridge and workbook style**

Write a non-secret JSON contract into a task-specific temporary directory and delete it in `finally`. The bridge imports XLSX inputs and writes one `Metadata` sheet with hidden gridlines, a frozen header/first column, wrapped capped cells, coloured source headers, alternating blocks, highlighted Genre/Style/Tags rows, em dash for missing provider data, and clickable record URLs. Append provenance rows `Record`, `Record ID`, `URL`, `Status`, `Match confidence`, `Match evidence`, and `Queried at` after each track block. The bridge uses the loader-provided Node runtime and `@oai/artifact-tool`.

- [ ] **Step 4: Verify green and visually inspect**

Run the Python and Node tests from Step 2. Then inspect `Metadata!A1:G24`, scan for `#REF!|#DIV/0!|#VALUE!|#NAME\?|#N/A`, render the populated range with `workbook.render`, and view it. Fix clipping, a wrong column order, missing link, or MAEST text before committing.

- [ ] **Step 5: Commit**

```powershell
git add tools/Audio-Online
git commit -m "feat: export Audio Online metadata workbook"
```

### Task 6: Orchestration, documentation, and offline delivery

**Files:**
- Modify: `tools/Audio-Online/metadata_enrichment_cli.py`
- Create: `tools/Audio-Online/README.md`
- Modify: `tools/Audio-Online/config.example.toml`
- Test: `tools/Audio-Online/tests/test_cli.py`

**Interfaces:**
- `enrich --input <path> --output <report.xlsx> [--db <library.sqlite>] [--config <config.toml>] [--node-executable <node>]`.
- Exit 0 after a workbook is written, even with partial-source failures; malformed input, malformed config, and writer failure are nonzero.

- [ ] **Step 1: Write the failing CLI orchestration test**

```python
def test_enrich_writes_workbook_when_one_source_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "metadata.xlsx"
    monkeypatch.setattr(cli, "source_registry", lambda config: (ErroringSource("Discogs"), MatchingSource("MusicBrainz")))
    monkeypatch.setattr(cli, "write_workbook", fake_workbook_writer)

    assert cli.main(["enrich", "--input", str(write_text_input(tmp_path)), "--output", str(output)]) == 0
    assert output.exists()
```

- [ ] **Step 2: Verify red**

Run: `.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests\test_cli.py -q`

Expected: FAIL because CLI orchestration is absent.

- [ ] **Step 3: Implement report-first command and user guide**

Process input order, source results, and local evidence without mutation; invoke the bridge once. README provides PowerShell examples for folder, CSV/XLSX, M3U, text, `--db`, config, and Last.fm authorization. Document each source status, independent-evidence semantics, official-access-only policy, and `METADATA_ENRICHMENT_NODE` for the bundled Node executable.

- [ ] **Step 4: Verify full offline run**

Run:
```powershell
.\.venv\Scripts\python.exe -m pytest tools\Audio-Online\tests -q
@'
Artist A — Title A
'@ | Set-Content -LiteralPath .\tools\Audio-Online\data\sample-tracks.txt -Encoding utf8
.\.venv\Scripts\python.exe .\tools\Audio-Online\metadata_enrichment_cli.py enrich --input .\tools\Audio-Online\data\sample-tracks.txt --output .\tools\Audio-Online\data\sample-report.xlsx --config .\tools\Audio-Online\config.example.toml
```

Expected: all focused tests pass; the report has all source columns and `not_configured`/`unavailable` cells without a network request.

- [ ] **Step 5: Inspect scope and commit**

Run:
```powershell
git diff --check
git status --short
git diff -- tools/Audio-Online
git add tools/Audio-Online
git commit -m "feat: add Audio Online metadata enrichment CLI"
```

Expected: only intended tool files are staged; never stage `config.toml`, OAuth credentials, sample report, or a user database.

