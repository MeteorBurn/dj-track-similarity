# Install

> Audience: Пользователи этой страницы.
> Type: how-to

Нужны Python 3.10+, `ffmpeg` on `PATH` или `DJ_TRACK_SIMILARITY_FFMPEG`, и Node/npm только для frontend/docs build. Используйте `python -m pip install -e ".[sonara,ml,rhythm-lab,dev]"` и проверяйте `dj-sim doctor`. Docs build: `npm run build` from `docs\dj-track-similarity`, output `site/`, served at `/docs/`.
