# Audio Online

Audio Online collects independent online metadata for a track list and writes one formatted XLSX
workbook. Each provider gets its own column block, so you can compare what Discogs, MusicBrainz,
Last.fm, and Beatport say about the same track side by side.

It is read-only. It never writes audio file tags, and it opens the library database in SQLite's
read-only mode.

```powershell
python tools\audio-online\metadata_enrichment_cli.py --help
```

## Before the first run

The tool runs on the project environment and has no install path of its own. Its extra dependencies
are the `audio-online` extra in `pyproject.toml`, so install them with the same `uv sync` as
everything else, from the repository root, then copy the configuration template:

```powershell
uv sync --locked --extra audio-online
Copy-Item tools\audio-online\config.example.toml tools\audio-online\config.toml
```

The extra adds `openpyxl` for the workbook, plus `tomli` on Python versions with no `tomllib` in the
standard library, which includes the pinned `3.10`. Mutagen is already a base dependency. Name every
extra you want in one `uv sync`, because each run installs exactly the set you name.

The workbook is written through a Node bridge, so `enrich` also needs Node and a `node_modules`
directory that resolves `@oai/artifact-tool`. That package is declared in no manifest in this
repository, and you supply its location yourself. Without it, `enrich` cannot produce output and
`.xlsx` input cannot be read.

## Three subcommands

| Subcommand | Purpose |
| --- | --- |
| `enrich` | Create a metadata workbook |
| `authorize <source>` | Authorize one configured source, `lastfm` or `beatport` |
| `check-auth beatport` | Validate a saved Beatport authorization |

### enrich

```powershell
python tools\audio-online\metadata_enrichment_cli.py enrich --input D:\Music\Crate --output D:\reports\metadata.xlsx --db .\data\library.sqlite
```

`--input` and `--output` are required. `--output` takes no default and the tool does not create
missing parent directories, so point it at a folder that exists.

`--db` is optional. It fills two columns from your library, `Genres` from stored file tags and
`MAEST Genres` from stored MAEST labels. Without it those two columns stay empty. `--db` cannot
select which tracks to process, only enrich the ones already on the list.

`--config` defaults to `config.toml` beside the CLI script, regardless of your working directory.

`--node-executable` and `--node-modules` override the two environment variables described below.

On success the run prints one line: `Wrote <output> (<n> tracks)`.

### Accepted input forms

`--input` dispatches on what it finds:

| Input | Handling |
| --- | --- |
| a directory | scanned recursively, sorted, filtered to supported audio extensions |
| a single audio file | one track |
| `.txt` | one line per track as `Artist - Title`, em dash also accepted |
| `.csv` | headers matched case-insensitively: `artist`, `title`, `album`, `country`, `label`, `year` |
| `.xlsx` | the same column mapping as CSV, read through the Node bridge |
| `.m3u` or `.m3u8` | `#EXTINF` supplies artist and title, the following line is used as the file path verbatim |

Supported audio extensions: `.mp3`, `.flac`, `.m4a`, `.aiff`, `.aif`, `.wav`, `.ogg`. Anything else
raises `unsupported input format`.

For folder and single-file input, Mutagen reads `artist`, `title`, and `album` from the file. When a
tag read fails, the filename stem is split instead. Nothing is written back to the file.

### authorize and check-auth

```powershell
python tools\audio-online\metadata_enrichment_cli.py authorize lastfm
python tools\audio-online\metadata_enrichment_cli.py authorize beatport
python tools\audio-online\metadata_enrichment_cli.py check-auth beatport
```

`authorize lastfm` opens a browser consent page, waits for you to paste the token, then calls
`auth.getSession` and stores the session key. That session key is provenance only. The `enrich` run
uses the API key rather than the session.

`authorize beatport` performs a Beatport v4 `client_credentials` grant against
`https://api.beatport.com/v4/auth/o/token/` and stores `access_token`, `expires_at`, and any
`refresh_token` and `scope` the response carries.

`check-auth beatport` calls the v4 introspect endpoint and prints whether the token is still valid,
with its scope when one is present.

Any other source name is a parser error.

## Providers

| Provider | Auth | What it contributes | Rate limit |
| --- | --- | --- | --- |
| Discogs | personal access token | release styles as genres, album, year, country, first label | none |
| MusicBrainz | a descriptive `user_agent` string | recording tags and title | 1 request per second |
| Last.fm | API key | top tags | none |
| Beatport | v4 OAuth client credentials | genre, album, year, label | none |
| Local file tags | `--db` | the `Genres` column, from stored library tags | none |
| MAEST | `--db` | the `MAEST Genres` column, top 3 labels with confidence | none |

Discogs takes the first search result without a confidence check. Beatport is the one provider that
scores candidates, awarding points for exact title, artist, album, and year matches and rejecting a
candidate that scores zero.

MuQ, MERT, CLAP, and SONARA play no part here. This tool reads catalog metadata rather than audio.

### Beatport token handling during a run

`enrich` refreshes the Beatport token once, before the track loop, and only when both `client_id`
and `client_secret` are configured. A token with more than five minutes left is reused. Otherwise
the tool refreshes with the stored refresh token, or requests a fresh grant. A run longer than the
token's remaining lifetime starts returning Beatport errors without refreshing again.

### When a provider fails

Each provider call is wrapped, so one dead provider never aborts the run or blocks the others. The
failure is recorded internally and the affected cells come out empty.

The workbook carries no status column, so an unconfigured provider, a no-match, a rate-limited
request, and a network error all look identical: an empty cell. There is no retry, no backoff, and
no `Retry-After` handling. Check your configuration before concluding that a provider had nothing.

## Configuration

The config file lives at `tools/audio-online/config.toml`. It is ignored by Git through the tool's
own `.gitignore`, so your credentials stay out of the repository. `config.example.toml` is the
committed template.

```toml
[sources.discogs]
token = ""

[sources.musicbrainz]
user_agent = ""

[sources.lastfm]
api_key = ""
shared_secret = ""

[sources.beatport]
client_id = ""
client_secret = ""

[sources.beatport.auth]
access_token = ""
refresh_token = ""
expires_at = ""
scope = ""
```

`authorize lastfm` adds a `[sources.lastfm.auth]` table holding `session_key`.

Three things to know about this file:

- A missing file is not an error. It yields an empty configuration and every provider reports itself
  as unconfigured.
- Only the four source names are accepted. A `[sources.something-else]` table raises
  `unsupported source`. Individual keys are not validated, so a typo is ignored silently.
- Running `authorize` rewrites the whole file from the parsed structure. Comments and any table
  outside `[sources.*]` are lost. Keep your own copy of anything you added by hand.

MusicBrainz asks for a descriptive `user_agent` naming your application and a contact address.
Sending a browser user-agent string violates their policy.

### Environment variables

| Variable | Effect | Default |
| --- | --- | --- |
| `METADATA_ENRICHMENT_NODE` | absolute path to `node`, the default for `--node-executable` | falls back to `node` on `PATH` |
| `METADATA_ENRICHMENT_NODE_MODULES` | directory resolving `@oai/artifact-tool`, the default for `--node-modules` | none, so it is required in practice |

Both are re-injected into the Node subprocess environment. `enrich` refuses to start when either
value is missing after the fallbacks.

## The workbook

One sheet called `Metadata`, one row per track, 42 columns.

The first block is the summary: `Track Name`, then `Genres` from your library tags, then
`MAEST Genres`, then one genre column per online provider. The second block repeats your input
values. The remaining 28 columns are seven fields for each of the four providers, named with the
provider as a prefix, such as `Discogs Title` and `Beatport Label`.

Every list value is truncated to its first three entries and joined with a semicolon and a space.
MAEST labels are rendered as `House (81%)`, with the part before `---` dropped from a hierarchical
label.

Formatting applied to the sheet:

- gridlines hidden
- a dark header row in bold white, at a taller row height
- thin row separators
- a green tint on every genre and tag column
- the first row and first column frozen
- column widths fitted to content

Every cell is written as a string, with no hyperlink, formula, or number format anywhere.

Several columns are structurally always empty, because the provider does not supply that field.
MusicBrainz and Last.fm leave album, year, country, and label blank. Discogs leaves tags blank.
Beatport leaves country and tags blank.

### Other files it touches

The run writes a temporary `<output-stem>.contract.json` beside the workbook and deletes it in a
`finally` block. Reading `.xlsx` input creates a temporary JSON file in the system temp directory
and deletes it the same way. Those two temporary files are the only side effects beyond the
workbook itself.

`data/*.xlsx`, `data/*.json`, and `data/*.inspect.ndjson` under the tool directory are ignored by
Git.

## Read-only guarantees

Two claims worth stating precisely, because this tool touches both your audio and your library.

**It never writes audio tags.** Mutagen is used once, to read `artist`, `title`, and `album` during
input loading. There is no save call anywhere in the tool.

**It opens the library read-only.** The connection string is the resolved database path as a URI
with `?mode=ro` appended, opened with `uri=True`. SQLite enforces that mode, so a write attempt
would raise rather than succeed. The tool runs two `SELECT` statements against the library and
nothing else.

Library matching is exact rather than fuzzy. With a file path it matches the literal path plus
slash-direction variants. Without one it requires a case-insensitive artist and title match and
returns nothing when more than one row qualifies.

## Interruption and resume

Results accumulate in memory and the workbook is written once, after the last track. An interruption
before that point loses everything collected so far. Every run starts from scratch, because the tool
keeps no checkpoint and offers no resume flag.

Two failures abort the whole run rather than degrading. A bad input path is the first. A database
error while reading local evidence is the second, and because that read happens per track, a failure
partway through discards the earlier results.

Plan large lists in batches.

## Tests

```powershell
python -m pytest tools/audio-online/tests
```

Ten pytest modules cover configuration, both authorization flows, the CLI, input parsing, library
matching, candidate scoring, provider isolation, the report contract, and workbook formatting. A
separate Node test covers the workbook bridge and needs `METADATA_ENRICHMENT_NODE_MODULES` set.

Run this suite on its own. Both `tests/` and `tools/audio-online/tests/` contain a `test_cli.py` and
neither has an `__init__.py`, so naming both paths in one pytest command fails on an import
collision.

## Related pages

- [Scripts](./scripts.md)
- [CLI reference](../reference/commands.md)
