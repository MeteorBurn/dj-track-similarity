# Build crates

Аудитория: DJs и music collectors  
Цель: создавать review lists без иллюзии финального алгоритмического taste  
Тип: how-to

Crate - это рабочий список: warmup pool, peak-time pool, left-field folder или
short list для прослушивания позже.

## Recommended loop

1. Начните с narrow seed: track, prompt, classifier или filter.
2. Search через подходящий mode.
3. Добавьте candidates в current set или export list.
4. Удалите tracks, которые не прошли listening check.
5. Повторите с другим seed или signal.

## Keep crates small

Самые полезные crates - reviewed crates. Большие unreviewed exports часто
становятся еще одной библиотекой, которую нужно разбирать.

Используйте `Track limit`, result limits и focused prompts, чтобы output был
достаточно маленьким для inspection.

## Mix signals deliberately

Хороший crate workflow часто смешивает signals:

- MERT for near audio neighbors;
- SONARA for feature balance;
- CLAP for descriptive searches;
- CLASS for trained concepts;
- SET for ordered previews.

Не используйте MAEST genre labels как crate builder, если workflow не про
запись или inspection genre metadata.
