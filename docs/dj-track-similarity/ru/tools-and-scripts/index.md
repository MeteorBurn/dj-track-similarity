# Инструменты и скрипты

> Audience: Пользователи этого раздела.
> Goal: Найти нужную страницу и не смешивать workflow с reference.
> Type: how-to

Выберите страницу под конкретную задачу. Workflow pages описывают практический сценарий, а reference pages дают короткую форму команд и контрактов.

## Pages

- [Rhythm Lab](rhythm-lab.md) — label and train personal classifiers.
- [Audio Dedup](audio-dedup.md) — report likely duplicates before any delete.
- [Audio Doctor](audio-doctor.md) — dry-run-first metadata/container repair.
- [Persistent ANN indexes](persistent-ann-indexes.md) — optional generated sidecars для более быстрого MERT, MAEST или CLAP vector lookup.
- [Optimize database](optimize-database.md) — backup, VACUUM, ANALYZE и integrity checks.

## Generated output

Эти tools могут создавать local reports, state files, backups или sidecar indexes. Считайте их private library artifacts, пока они не очищены вручную.

## Privacy

Используйте `<library-db>` и `<music-folder>` в публичных examples. Не публикуйте private paths, usernames, real track names или personal library contents.
