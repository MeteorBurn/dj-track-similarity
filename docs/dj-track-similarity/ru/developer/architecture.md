# Architecture

> Audience: Пользователи этой страницы.
> Type: how-to

CLI and FastAPI backend use `LibraryDatabase`. React UI calls API routes. Scanner and analysis jobs read audio and write SQLite. Search and SET read stored features/embeddings. Rhythm Lab and Audio Dedup are helper projects.
