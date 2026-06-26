# Release checklist

Audience: maintainers  
Goal: provide a compact release gate  
Type: checklist

Before publishing or merging a release-sized docs/code change, verify the
actual changed surface.

## Source checks

- Current behavior was checked against code, CLI help, API schemas, tests, or
  command output.
- Old docs were not used as trusted facts without verification.
- Generated local artifacts are not being added accidentally.
- Real user databases and audio files were not modified during routine tests.

## Build checks

- Backend focused tests passed for changed behavior.
- Frontend build passed if frontend source changed.
- Docs build passed if Markdown under `docs/dj-track-similarity` changed.
- `git diff --check` passed.

## Safety checks

- Destructive/apply workflows require explicit confirmation.
- Tag-writing docs mention that genre writing is the deliberate audio-write
  exception.
- Database maintenance docs mention backups and integrity checks.
- Rhythm Lab docs keep lab state separate from runtime promoted models.

## Publish notes

Call out breaking URL moves, required rebuilds, and any known gaps. Keep
generated `site/` changes separate from source review when possible.
