# Browse library

Аудитория: пользователи UI  
Цель: находить, слушать и проверять tracks без изменения audio  
Тип: how-to

Library view показывает lightweight rows из server-side paginated/searchable
endpoint. Full metadata загружается только при открытии dialog.

## Что можно делать

- искать и фильтровать tracks;
- открыть details dialog;
- слушать preview;
- переключать liked state;
- смотреть tags, SONARA features, MAEST genres и classifier scores отдельно.

## Safety

Browsing и preview не переписывают source audio. AIFF/AIF preview может
транскодироваться в WAV response для browser playback, но source file не
кэшируется и не переписывается.

## Metadata dialog

Смысл блоков в dialog:

- Mutagen tags: metadata из файлов;
- SONARA features: analyzed values;
- MAEST genres: stored genre analysis;
- classifier scores: promoted model probabilities.

Не смешивайте эти источники при ручной проверке.
