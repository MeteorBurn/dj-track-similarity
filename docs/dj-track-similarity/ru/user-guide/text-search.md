# Text search

Аудитория: пользователи CLAP search  
Цель: искать треки по короткому музыкальному описанию  
Тип: how-to

Text search использует CLAP embeddings. Он подходит для prompts вроде:

```text
dark hypnotic techno, rolling bass, no vocals
```

## Requirements

Нужны CLAP audio embeddings для tracks, которые должны участвовать в search.

## Хорошие prompts

Пишите музыкальные признаки:

- mood or energy;
- genre-adjacent language;
- rhythm or texture;
- vocal/no vocal preference;
- instrumentation.

Не ожидайте exact database search. CLAP ранжирует по embedding similarity.

## CLI example

Активируйте окружение один раз:

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" `
  --limit 5 `
  --db .\data\library.sqlite
```
