# Audio Online metadata enrichment design

## Scope

Create a standalone command-line tool in `tools/Audio-Online/`. It enriches a
user-supplied track list with metadata from configured online sources and reads
two existing local genre surfaces from a chosen SQLite library database. It
does not import the main application, start its API, alter its schema, write to
the library database, or change audio-file tags.

The tool presents independent evidence. It never selects an authoritative genre
or merges data from sources into a new tag value.

## Commands and inputs

`metadata_enrichment_cli.py enrich` accepts exactly one input source:

- a directory of audio files;
- a CSV or XLSX track table;
- an M3U playlist; or
- a UTF-8 text list containing `Artist - Title` or `Artist — Title` entries.

Inputs are normalized into records with available `Title`, `Artist`, `Album`,
`Year`, `Country`, `Label`, and `Duration` values. Audio-file inputs read their
embedded metadata. Tabular inputs use recognized column names and retain blank
values when an input does not supply a field.

`--db <path>` is optional and read-only. When supplied, the tool associates
local values only by the exact input file path. It reads file-tag genres from
`tags.genres_json` and MAEST predictions from `maest_genres.genres_json`.
There is no fuzzy database fallback, avoiding an accidental association with a
differently titled track.

`metadata_enrichment_cli.py authorize <source>` runs an official OAuth flow
only when the selected source supports one and its client configuration is
present.

## Source adapters and credentials

Each service has an independent adapter behind one normalized result model.
The initial registry names Discogs, MusicBrainz, Last.fm, and Beatport, and it
can add further sources without changing input handling or workbook rendering.

Before an adapter is enabled, its current official API and authentication path
must be verified. The tool uses no undocumented browser scraping. A service
without permitted automated access returns `unavailable`; a missing credential
returns `not_configured`; either condition leaves the rest of the run intact.

`tools/Audio-Online/config.toml` contains service keys and OAuth data locally.
It is ignored by Git. `config.example.toml` documents the non-secret structure.
The authorization command securely updates the local configuration. Users
supply service keys and complete browser consent; the tool does not create
third-party accounts or expose secrets in reports or logs.

## Matching and provenance

An adapter searches with artist and title, then ranks candidates using available
album, year, duration, and track-number evidence. It emits one selected record
for its source and a confidence explanation. A low-confidence match remains
visible as low confidence; it is not silently discarded or promoted to fact.

For every service, provenance includes the source record type, source ID,
clickable record URL, query time, query status, match confidence, and a concise
matching explanation. These values are preserved in the per-track block and
never incorporated into another source's genre, style, or tag values.

## Workbook output

Each run produces one formatted XLSX file containing one `Metadata` worksheet.
Every input track becomes a vertical block, with blocks stacked top to bottom.
The first column is `Field`. The remaining columns are, in order:

1. `Local tags`
2. each configured online service in registry order
3. `MAEST` (always last)

The primary rows, in order, are:

1. `Title`
2. `Artist`
3. `Album`
4. `Year`
5. `Country`
6. `Label`
7. `Genre`
8. `Style`
9. `Tags`
10. `Duration`

All multi-value fields are rendered in one cell, joined with `; `.
`Genre` in the MAEST column contains exactly the best three stored predictions,
sorted by their stored score, with rounded whole-percent confidence, for example
`House (81%); Techno (64%); Electronic (52%)`. MAEST `Style` and `Tags` remain
blank.

The primary rows are followed by compact provenance rows for each source:
`Record`, `Record ID`, `URL`, `Status`, `Match confidence`, `Match evidence`,
and `Queried at`. Hyperlinks are clickable. Missing data is rendered as an em
dash, while statuses distinguish absence from request failures.

The sheet uses a frozen header, wrapped cells, readable source colors,
alternating track blocks, highlighted genre/style/tag rows, column widths, and
clickable links. It has no second summary or hidden raw-data sheet.

## Failure behavior and rate limits

The run is report-first: it writes a workbook even if some sources fail. A
single-source timeout, authentication failure, rate-limit response, malformed
payload, or no-match result affects only that source's cells and provenance
status. Adapters use their documented request limits, bounded retries only for
transient failures, and clear status messages without credential values.

## Test strategy

Tests run entirely with fixture adapter payloads, temporary SQLite databases,
and temporary XLSX outputs. They cover input normalization, exact-path local
lookup, source-status isolation, matching confidence, semicolon rendering,
three-item MAEST percentage formatting, provenance rows, clickable links, and
the configured column order with MAEST last. No test calls a real source,
requires an API key/OAuth login, opens the user database, or mutates audio.
