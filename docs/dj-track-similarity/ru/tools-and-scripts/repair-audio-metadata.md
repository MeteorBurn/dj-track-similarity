# Repair Audio Metadata

> Audience: Пользователи этой страницы.
> Type: how-to

Dry-run does not write or copy audio. `--db` opens SQLite read-only; `--db-root` plus `--file-root` can remap stored paths; missing remapped files are skipped. `--apply` creates a full-file backup unless `--no-backup`; backup is deleted after successful verification or after restore on failure.
