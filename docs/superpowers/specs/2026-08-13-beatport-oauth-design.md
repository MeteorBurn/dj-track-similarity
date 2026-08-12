# Beatport OAuth v4 for Audio Online

## Goal

Connect the standalone `tools/Audio-Online` CLI to Beatport's documented v4
Catalog API without storefront scraping. Beatport evidence remains a separate
report column and never overrides local tags, other sources, or MAEST.

## Credentials and local state

`tools/Audio-Online/config.toml`, which is already ignored by Git, becomes the
only credential store. The Beatport section contains `client_id` and
`client_secret`; the saved `auth` subsection contains `access_token`,
`refresh_token`, `expires_at`, and optional returned scope. Secrets are never
printed, added to `.env`, included in reports, or committed.

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

## Authorization lifecycle

For catalog-only enrichment, `authorize beatport` uses the OAuth2
`client_credentials` grant against `/v4/auth/o/token/`. It stores the returned
token response locally. `check-auth beatport` calls `/v4/auth/o/introspect/`
with `Authorization: Bearer <token>` and displays only the validation result,
expiry, and non-secret account/scope fields returned by Beatport.

Before each catalog request, the adapter refreshes a token that is expired or
within five minutes of expiry using the documented `refresh_token` grant. A
refresh failure remains visible as a per-track `error`; it never falls back to
web scraping or the user's Beatport password. The password grant and browser
authorization-code flow are deliberately out of scope because the tool only
needs catalog metadata, not a user's Beatport library or write permissions.

## Catalog adapter and provenance

The adapter calls the documented v4 catalog-search endpoint with a bearer token
and Artist/Title query parameters from the input. It selects a returned track
only through the existing deterministic identity assessment and stores source
fields separately: track title, artists, release, label, release year,
duration, Beatport genre/subgenre when supplied, Beatport track/release ID, and
direct URL. The workbook continues to write `Record`, `Record ID`, `URL`,
`Status`, `Match confidence`, `Match evidence`, and `Queried at` for Beatport.

If the returned contract cannot support the required fields, the adapter reports
`unavailable` with a concise schema error rather than mislabelling fields.

## CLI and validation

Commands:

```powershell
python .\metadata_enrichment_cli.py authorize beatport --config .\config.toml
python .\metadata_enrichment_cli.py check-auth beatport --config .\config.toml
python .\metadata_enrichment_cli.py enrich --input .\tracks.csv --output .\metadata.xlsx --config .\config.toml
```

Focused tests cover grant request construction, secret-safe persistence,
introspection, proactive refresh, catalog mapping, and an end-to-end report
contract using faked HTTP. A real authorization check runs only after the user
has entered credentials into the ignored local config.
