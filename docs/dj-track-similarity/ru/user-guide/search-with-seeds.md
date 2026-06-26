# Search with seeds

Аудитория: DJs и пользователи search UI  
Цель: использовать selected tracks как seed для related results  
Тип: how-to

Seed search полезен, когда вы знаете один или несколько tracks и хотите найти
related candidates.

## MERT seed search

Используйте `MERT`, когда нужен поиск "что звучит похоже на это?". Требуются
stored MERT embeddings.

## SONARA search

Используйте `SONARA`, когда нужно управлять feature-oriented matching через
микшер и modifiers. Требуются SONARA features.

## Практический workflow

1. Выберите один или несколько seed tracks.
2. Откройте подходящий tab.
3. Запустите search.
4. Прослушайте candidates.
5. Добавляйте только tracks, которые проходят ручную проверку.

Search results - это candidates, а не final set.
