# Configuration

> Audience: Пользователи, которые настраивают local paths, ports и build outputs.
> Goal: Быстро вспомнить важные runtime и docs settings.
> Type: reference

## Paths

- Source package: `src/dj_track_similarity/`.
- Frontend source: `frontend/`.
- Docs source: `docs/dj-track-similarity/`.
- Docs output: `docs/dj-track-similarity/site/` — local build output, ignored by Git.
- Promoted classifiers: `models/classifiers/<artifact-prefix>/`.
- Persistent ANN sidecars: `.dj-track-similarity-indexes/` рядом с выбранной SQLite database по умолчанию или `--index-dir <index-folder>` при переопределении.

## Ports

Main backend использует `8765`, frontend Vite — `5173`, Rhythm Lab — `8777`. Перед запуском fixed-port server проверьте, что уже не запущен другой project process.

Main UI top bar содержит local server stop button для текущего backend process. Он вызывает `/api/server/shutdown` с explicit shutdown action header, после чего backend завершает работу после подтверждения.

## Runtime

`ffmpeg` должен быть в `PATH` или настроен через `DJ_TRACK_SIMILARITY_FFMPEG`. Analysis device values: `auto`, `cpu`, `cuda`.

Persistent ANN index backend выбирается через `dj-sim index build --backend auto|hnswlib|exact-numpy`. `auto` предпочитает `hnswlib`, когда установлен optional `ann` extra, и возвращается к `exact-numpy`, если его нет.

## Generated local state

Generated databases, logs, reports, backups, promoted classifier artifacts и index sidecars могут раскрывать private library information. Не добавляйте их в Git, пока они не sanitized intentionally.

## Docs

Из `docs\dj-track-similarity` запускайте `npm run build` только когда нужен local preview или deployment output. VitePress uses `base: "/docs/"` and `outDir: "site"`. Backend serves `/docs/` from that folder when it exists; otherwise it shows a clear not-built page.
