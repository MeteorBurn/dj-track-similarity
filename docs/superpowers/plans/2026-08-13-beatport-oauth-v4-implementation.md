# Beatport OAuth v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Audio Online obtain, persist, validate, refresh, and use a Beatport OAuth v4 token for documented catalog-track search.

**Architecture:** Keep OAuth protocol code in `metadata_enrichment/auth.py`, use the existing local TOML serializer for token persistence, and pass a current bearer token into a focused `BeatportSource`. The source returns a normal `SourceResult`; existing report code owns provenance and confidence display.

**Tech Stack:** Python 3.10, stdlib `urllib`, TOML (`tomli` fallback), pytest.

## Global Constraints

- Store credentials and all OAuth state only in ignored `tools/Audio-Online/config.toml`; never use `.env`.
- Do not print, commit, or report a client secret, access token, or refresh token.
- Use only Beatport documented v4 OAuth and Catalog endpoints; no storefront scraping or password grant.
- Preserve per-source provenance, status, IDs, URLs, and independent genre evidence.
- Database and audio inputs remain read-only.

---

### Task 1: Represent Beatport OAuth state and HTTP form posts

**Files:**
- Modify: `tools/Audio-Online/config.example.toml`
- Modify: `tools/Audio-Online/metadata_enrichment/http.py`
- Modify: `tools/Audio-Online/metadata_enrichment/config.py`
- Test: `tools/Audio-Online/tests/test_config.py`

**Interfaces:**
- Produces `post_form_json(url: str, *, headers: Mapping[str, str], fields: Mapping[str, str]) -> Mapping[str, object>`.
- Produces `save_auth_data(..., {"access_token": ..., "refresh_token": ..., "expires_at": ..., "scope": ...})` with deterministic TOML output.

- [ ] **Step 1: Write failing tests for persisting Beatport auth fields and form encoding.**

```python
def test_beatport_auth_state_is_written_under_ignored_local_config(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_auth_data(path, "beatport", {"access_token": "token", "expires_at": "2030-01-01T00:00:00+00:00"})
    assert '[sources.beatport.auth]' in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the focused tests and verify they fail before the new form helper exists.**

Run: `python -m pytest tools/Audio-Online/tests/test_config.py -q`

- [ ] **Step 3: Add the minimal form-post helper and example config.**

```toml
[sources.beatport]
client_id = ""
client_secret = ""

[sources.beatport.auth]
access_token = ""
refresh_token = ""
expires_at = ""
scope = ""
```

- [ ] **Step 4: Run the focused tests and inspect the rendered TOML.**

Run: `python -m pytest tools/Audio-Online/tests/test_config.py -q`

- [ ] **Step 5: Commit the independently testable configuration/HTTP change.**

```powershell
git add tools/Audio-Online/config.example.toml tools/Audio-Online/metadata_enrichment/config.py tools/Audio-Online/metadata_enrichment/http.py tools/Audio-Online/tests/test_config.py
git commit -m "feat: add Beatport OAuth config support"
```

### Task 2: Add grant, introspection, and refresh lifecycle

**Files:**
- Modify: `tools/Audio-Online/metadata_enrichment/auth.py`
- Create: `tools/Audio-Online/metadata_enrichment/beatport_auth.py`
- Test: `tools/Audio-Online/tests/test_auth.py`

**Interfaces:**
- Produces `authorize_beatport(config_path: Path, config: ToolConfig, *, post_form_json: FormPost) -> str`.
- Produces `check_beatport_auth(config: ToolConfig, *, get_json: JsonGet) -> Mapping[str, object]`.
- Produces `refresh_beatport_access_token(config_path: Path, config: ToolConfig, *, post_form_json: FormPost, now: datetime) -> ToolConfig`.

- [ ] **Step 1: Write failing tests for client-credentials request, safe persistence, introspection, and five-minute proactive refresh.**

```python
def test_authorize_beatport_requests_client_credentials_and_hides_token(tmp_path: Path, capsys) -> None:
    message = authorize_beatport(path, config, post_form_json=fake_token_response)
    assert message == "Beatport authorization saved."
    assert "access-token" not in capsys.readouterr().out
```

- [ ] **Step 2: Run those tests and verify the missing lifecycle functions fail.**

Run: `python -m pytest tools/Audio-Online/tests/test_auth.py -q`

- [ ] **Step 3: Implement only documented grants.**

Use `POST https://api.beatport.com/v4/auth/o/token/` with
`client_id`, `client_secret`, and `grant_type=client_credentials`; persist the
returned token fields and calculated UTC `expires_at`. Refresh with
`grant_type=refresh_token`, current bearer token header, `client_id`, and
`refresh_token`. Introspect with `GET /v4/auth/o/introspect/` and a bearer
header. Raise clear errors for absent fields or an invalid OAuth response.

- [ ] **Step 4: Run focused lifecycle tests.**

Run: `python -m pytest tools/Audio-Online/tests/test_auth.py -q`

- [ ] **Step 5: Commit OAuth lifecycle.**

```powershell
git add tools/Audio-Online/metadata_enrichment/auth.py tools/Audio-Online/metadata_enrichment/beatport_auth.py tools/Audio-Online/tests/test_auth.py
git commit -m "feat: add Beatport OAuth lifecycle"
```

### Task 3: Query and map documented v4 Catalog search

**Files:**
- Modify: `tools/Audio-Online/metadata_enrichment/beatport.py`
- Modify: `tools/Audio-Online/metadata_enrichment/sources.py`
- Test: `tools/Audio-Online/tests/test_sources.py`

**Interfaces:**
- `BeatportSource(access_token: str | None, get_json: JsonGet).fetch(track) -> SourceResult`.
- Uses `GET https://api.beatport.com/v4/catalog/search/` with `q`, `type=tracks`, `artist_name`, and `per_page=5`.

- [ ] **Step 1: Write a failing mapping test against a documented representative search payload.**

```python
payload = {"results": [{"id": 123, "name": "Title", "artists": [{"name": "Artist"}], "genre": {"name": "Techno"}}]}
result = BeatportSource(access_token="token", get_json=lambda *_a, **_k: payload).fetch(TrackInput(artist="Artist", title="Title"))
assert result.record.genres == ("Techno",)
assert result.record.record_id == "123"
```

- [ ] **Step 2: Run the focused source test and verify it fails.**

Run: `python -m pytest tools/Audio-Online/tests/test_sources.py -q`

- [ ] **Step 3: Implement one safe mapper.**

Add bearer headers, restrict the endpoint to the fixed Beatport v4 URL, select
the returned candidate with the existing deterministic scorer, map only fields
whose types are validated, and return `unavailable` with a schema error if no
usable track representation is present.

- [ ] **Step 4: Run focused source tests.**

Run: `python -m pytest tools/Audio-Online/tests/test_sources.py -q`

- [ ] **Step 5: Commit the catalog adapter.**

```powershell
git add tools/Audio-Online/metadata_enrichment/beatport.py tools/Audio-Online/metadata_enrichment/sources.py tools/Audio-Online/tests/test_sources.py
git commit -m "feat: query Beatport catalog metadata"
```

### Task 4: Expose CLI commands and document local setup

**Files:**
- Modify: `tools/Audio-Online/metadata_enrichment_cli.py`
- Modify: `tools/Audio-Online/README.md`
- Test: `tools/Audio-Online/tests/test_cli.py`

**Interfaces:**
- `authorize beatport --config <path>` returns a secret-safe success/error message.
- `check-auth beatport --config <path>` reports valid/invalid plus non-secret expiry/scope.

- [ ] **Step 1: Write CLI tests using injected authorization functions and a temporary config.**

```python
def test_check_auth_beatport_reports_valid_without_secret(monkeypatch, capsys, tmp_path):
    assert main(["check-auth", "beatport", "--config", str(tmp_path / "config.toml")]) == 0
    assert "token" not in capsys.readouterr().out.casefold()
```

- [ ] **Step 2: Run CLI tests and verify they fail before the subcommand exists.**

Run: `python -m pytest tools/Audio-Online/tests/test_cli.py -q`

- [ ] **Step 3: Add the two commands and README setup.**

The README must say to enter client ID/secret directly in ignored local
`config.toml`, run the authorization command, and use `check-auth` before an
enrichment job. It must state the 10-hour example token lifetime is supplied
by Beatport and real expiry is taken from the response.

- [ ] **Step 4: Run focused CLI tests.**

Run: `python -m pytest tools/Audio-Online/tests/test_cli.py -q`

- [ ] **Step 5: Commit the user-facing commands.**

```powershell
git add tools/Audio-Online/metadata_enrichment_cli.py tools/Audio-Online/README.md tools/Audio-Online/tests/test_cli.py
git commit -m "feat: expose Beatport authorization commands"
```

### Task 5: Verify the integrated tool and real local authorization

**Files:**
- Modify only if verification exposes a failing scoped defect.
- Test: `tools/Audio-Online/tests/`

- [ ] **Step 1: Run all focused Audio Online tests, Python compilation, and workbook bridge tests.**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q .\tools\Audio-Online
.\.venv\Scripts\python.exe -m pytest .\tools\Audio-Online\tests -q
<bundled-node> .\tools\Audio-Online\workbook_bridge.test.mjs
```

- [ ] **Step 2: Inspect diff and working tree.**

Run: `git diff --check -- tools/Audio-Online; git status --short`

- [ ] **Step 3: With local client credentials present, run the real authorization and introspection once.**

Run:

```powershell
python .\tools\Audio-Online\metadata_enrichment_cli.py authorize beatport --config .\tools\Audio-Online\config.toml
python .\tools\Audio-Online\metadata_enrichment_cli.py check-auth beatport --config .\tools\Audio-Online\config.toml
```

Expected: success status with no credential values. If client credentials are
not yet present, report that exact external blocker and do not alter config.

- [ ] **Step 4: Commit any verification-only source fix, then report exact results.**

```powershell
git add tools/Audio-Online
git commit -m "fix: verify Beatport OAuth integration"
```
