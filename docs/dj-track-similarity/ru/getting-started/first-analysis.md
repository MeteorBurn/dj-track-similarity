# Первый анализ библиотеки

> Audience: Пользователи, которые уже просканировали треки и хотят полезный поиск.
> Goal: Запустить текущую unified analysis command и правильно выбрать лимит.
> Type: how-to

Анализ нужен после `scan`: он добавляет измеренные аудио-признаки и embeddings, по которым приложение сравнивает треки. Сначала запустите малую пачку, убедитесь, что результаты полезны, затем переходите к полной библиотеке.

## Unified command

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

`--limit 25` обрабатывает небольшое число треков, которым не хватает выбранных результатов анализа. Это удобная проверка декодирования, загрузки моделей и выбора CPU/GPU.

## Что открывает каждый анализ

- `sonara` сохраняет измеренные audio features для вкладки SONARA, переходов Smart Set, энергии и fallback BPM/key.
- `maest` сохраняет genre labels и MAEST embeddings. Genre tag apply использует labels; Smart Set может использовать embeddings, но не MAEST genre labels.
- `mert` сохраняет MERT embeddings для seed-based similarity search.
- `clap` сохраняет CLAP audio embeddings для CLAP text search и дополнительных SET-сигналов.

## Опции и лимиты

Поддерживаются `--models`, `--device auto|cpu|cuda`, `--top-k`, `--track-batch-size`, `--inference-batch-size` и `--diagnostics`. `auto` выбирает CUDA, если PyTorch видит GPU, иначе CPU.

Для всей библиотеки в CLI не указывайте `--limit`. Не используйте `--limit 0` как CLI-обозначение всех треков.

В UI наоборот: `Analyze limit = 0` означает всю библиотеку, потому что UI отправляет `null` или отсутствие лимита в `/api/analysis/jobs`. Положительные значения считают треки, которым не хватает выбранной analysis family.
