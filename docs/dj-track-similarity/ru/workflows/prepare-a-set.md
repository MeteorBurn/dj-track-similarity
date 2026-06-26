# Prepare a set

Аудитория: DJs, работающие в browser UI  
Цель: превратить несколько tracks в reviewed export  
Тип: tutorial

Workflow начинается с trusted tracks, затем создает candidates, строит preview
и экспортирует только после ручной проверки.

## Before you start

Нужна scanned library и analysis для выбранного search mode:

- SONARA features для explainable feature search;
- MERT embeddings для audio seed similarity;
- CLAP embeddings для text prompts;
- SONARA, MERT, MAEST и CLAP для Smart Set Builder.

## 1. Pick first anchors

В library table найдите один-пять tracks, представляющих нужный sound. Если
планируете SET, не выбирайте несколько tracks одного known artist: SET сохраняет
strict artist guard.

## 2. Search around anchors

Используйте tab под задачу:

| Need | Tab |
| --- | --- |
| похожий audio feel от selected tracks | `MERT` |
| explainable musical features | `SONARA` |
| text prompt вроде "dark rolling techno" | `CLAP` |
| ordered set preview | `SET` |
| promoted personal concept | `CLASS` |

Добавляйте только candidates, которые хотите слушать. Search results не
являются finished set.

## 3. Generate SET preview

Откройте `SET`, выберите `Manual` или `Auto`, задайте track limit, energy curve,
diversity и BPM mode, затем generate preview.

Preview read-only. Оно становится частью current set только через явное add
action.

## 4. Listen and remove weak links

Используйте playback, metadata, BPM/key и собственный DJ judgement. Similarity
scores - ranking hints, а не знание о room, crowd или transition style.

## 5. Export

Когда current set полезен, export его как playlist/report из UI. Export пишет
playlist/report files и не переписывает source audio.
