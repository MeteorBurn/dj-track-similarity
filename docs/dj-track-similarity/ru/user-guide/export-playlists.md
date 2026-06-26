# Export playlists

Аудитория: пользователи UI  
Цель: экспортировать reviewed current set  
Тип: how-to

Export нужен после ручной проверки candidates или SET preview.

## Before export

Проверьте:

- порядок tracks;
- наличие файлов на диске;
- BPM/key и metadata, если они важны для downstream app;
- что список не является unreviewed search dump.

## What export writes

Export пишет playlist/report files. Он не переписывает source audio и не меняет
tags.

## Practical advice

Экспортируйте маленькие reviewed lists. Если список слишком большой для
прослушивания, лучше сузить search или разбить его на crates.
