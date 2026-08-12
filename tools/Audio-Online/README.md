# Audio Online

`Audio Online` is a standalone, read-only metadata enrichment CLI for DJ track
lists. It does not decide a single "correct" genre. Instead, it writes one
formatted XLSX sheet where each track is a vertical block and every provider
gets its own column, so Discogs genres, MusicBrainz tags, Last.fm tags, local
file tags, and MAEST predictions remain independent evidence.

The tool is contained in this folder and does not import or change the main
application. Database access, when requested, is read-only and uses only the
exact local file path.

## Install and configure

From this folder, install the small Python requirements into the interpreter
you will run:

```powershell
python -m pip install -r requirements.txt
Copy-Item .\config.example.toml .\config.toml
```

`config.toml` and its saved authorization data stay inside this tool folder and
are ignored by Git. Do not put them in a project-wide `.env` file.

- **Discogs:** create a personal access token and set `sources.discogs.token`.
- **MusicBrainz:** has no key here; set a descriptive `user_agent`, including a
  contact address. Its public endpoint is queried only when this is set.
- **Last.fm:** create an API application, set `api_key` and `shared_secret`,
  then authorize once with the command below. The returned session key is saved
  under `sources.lastfm.auth` in this local `config.toml`.
- **Beatport:** create an OAuth application in the Beatport Developer portal,
  then set its `client_id` and `client_secret`. Do not use your Beatport
  password and do not share these values. The CLI obtains and renews its
  catalog token locally; it never scrapes the storefront.

The XLSX writer uses the bundled Artifact Tool Node runtime. Set the following
only for the terminal session in which you run the CLI:

```powershell
$env:METADATA_ENRICHMENT_NODE_MODULES = 'C:\path\to\node_modules'
# Optional when node.exe is not already on PATH:
$env:METADATA_ENRICHMENT_NODE = 'C:\path\to\node.exe'
```

## Last.fm authorization

```powershell
python .\metadata_enrichment_cli.py authorize lastfm --config .\config.toml
```

The command opens the Last.fm consent page, asks you to paste the returned
token, exchanges it for a session key, and saves it locally. No key or secret
is printed.

## Beatport authorization

For catalog metadata, Audio Online uses Beatport v4's `client_credentials`
OAuth grant. Enter the Client ID and Client Secret from your Beatport OAuth
application in the ignored local config:

```toml
[sources.beatport]
client_id = "..."
client_secret = "..."
```

Then obtain and validate the local token:

```powershell
python .\metadata_enrichment_cli.py authorize beatport --config .\config.toml
python .\metadata_enrichment_cli.py check-auth beatport --config .\config.toml
```

The token response, refresh token, scope, and calculated expiry are stored
under `[sources.beatport.auth]` in the same ignored file. A normal `enrich`
run proactively renews a token that has five minutes or less remaining. The
actual expiry is taken from Beatport's `expires_in` response field; do not copy
or print the token values.

## Create a workbook

```powershell
python .\metadata_enrichment_cli.py enrich `
  --input .\data\tracks.csv `
  --output .\data\metadata.xlsx `
  --config .\config.toml `
  --db C:\projects\dj-track-similarity\database\library.sqlite
```

Supported inputs are a folder of audio files (`.mp3`, `.flac`, `.m4a`, `.aiff`,
`.wav`, `.ogg`), plain text `Artist - Title`, CSV/XLSX tables with `Artist`,
`Title`, `Album`, `Year`, `Country`, `Label` columns, and M3U/M3U8 playlists.
For folders and playlists, source file paths are preserved so matching local
database data is exact rather than fuzzy.

The output sheet is named `Metadata`. Each block has source columns `Local
tags`, `Discogs`, `MusicBrainz`, `Last.fm`, `Beatport`, and `MAEST` (always
last). Rows include `Track Name` (`Artist — Title`), title/release fields,
`Genre`, `Style`, `Tags`, duration, plus record type/ID/URL, source status,
match confidence/evidence, and query time. Lists are joined with `; `.

`MAEST` appears only in the final column and shows its top three genres with
percentages, for example `House (81%); Techno (64%); Electronic (52%)`.

## Source behavior

`matched` means the source returned a record; it is not an assertion that the
genre is correct. The workbook's match-confidence/evidence rows let you judge
the identification independently. `not_configured`, `no_match`, `unavailable`,
and `error` remain visible per source and per track.

The adapters use documented APIs only. MusicBrainz is configured with a
meaningful User-Agent and its request interval is kept at no more than one
request per second. Last.fm uses `track.getTopTags`, which requires an API key;
the optional saved Last.fm session is provenance/configuration only for future
authenticated endpoints. Beatport uses v4 Catalog Search with a bearer token;
its top-level genre and subgenre are reported separately as `Genre` and
`Style` when the API returns them.
