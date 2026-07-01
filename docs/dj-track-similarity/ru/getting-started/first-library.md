# First Library

> Audience: Пользователи этой страницы.
> Type: how-to

Library — это SQLite database с track paths, file facts, readable Mutagen tags, metadata JSON и analysis flags. `dj-sim scan <music-folder> --db .\data\library.sqlite` читает metadata и пишет SQLite rows; audio files не retag. Refresh Tags тоже пишет только SQLite.
