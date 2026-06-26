# Tools and scripts

Аудитория: power users  
Цель: найти helper tools и не смешивать их с обычными workflows app  
Тип: how-to index

Эти tools - локальные helpers вокруг main database и audio library.

| Tool | Для чего |
| --- | --- |
| [Rhythm Lab](rhythm-lab.md) | labeling, training, promotion classifier profiles |
| [Audio dedup](audio-dedup.md) | duplicate candidate reports и explicit cleanup |
| [Audio repair](repair-audio-metadata.md) | dry-run-first metadata/container repair checks |
| [Optimize database](optimize-database.md) | SQLite backup, integrity check, compact, analyze |

Сначала используйте reports and dry-runs. Apply modes описаны отдельно, потому
что могут менять files или database rows.
