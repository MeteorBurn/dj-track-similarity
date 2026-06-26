# Release checklist

Аудитория: maintainers  
Цель: compact release gate  
Тип: checklist

Before publishing or merging release-sized docs/code change, verify actual
changed surface.

## Source checks

- Current behavior checked against code, CLI help, API schemas, tests or
  command output.
- Old docs not used as trusted facts without verification.
- Generated local artifacts are not added accidentally.
- Real user databases and audio files not modified during routine tests.

## Build checks

- Backend focused tests passed for changed behavior.
- Frontend build passed if frontend source changed.
- Docs build passed if Markdown under `docs/dj-track-similarity` changed.
- `git diff --check` passed.

## Safety checks

- Destructive/apply workflows require explicit confirmation.
- Tag-writing docs mention genre writing as deliberate audio-write exception.
- Database maintenance docs mention backups and integrity checks.
- Rhythm Lab docs keep lab state separate from runtime promoted models.

## Publish notes

Call out breaking URL moves, required rebuilds and known gaps. Keep generated
`site/` changes separate from source review when possible.
