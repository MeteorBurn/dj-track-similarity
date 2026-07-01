# Troubleshooting

> Audience: Пользователи этой страницы.
> Type: how-to

If `ffmpeg` is missing, add it to `PATH` or set `DJ_TRACK_SIMILARITY_FFMPEG`. If analysis finds zero tracks, check scan state and limits: UI `0` means whole library, CLI whole library omits `--limit`. If CLAP search is empty, run CLAP analysis. If SET eligible count is low, run missing MERT/MAEST/CLAP/SONARA.
