# Smart Set Builder

Аудитория: DJs и продвинутые пользователи UI  
Цель: генерировать ordered read-only set previews  
Тип: how-to

Smart Set Builder в tab `SET` строит ordered preview из manual seeds или auto
anchors. Он не изменяет библиотеку. Preview добавляется в current set только
явным действием.

## Requirements

SET требует feature-complete candidates:

- SONARA features;
- MERT embeddings;
- MAEST embeddings;
- CLAP audio embeddings.

MAEST genre labels не являются selection source для SET. MAEST embeddings могут
использоваться как один similarity signal.

## Seed source

- `Manual`: использовать selected tracks как seeds.
- `Auto`: выбрать первый anchor из feature-complete library, затем построить
  related waypoint anchors и bridge tracks.

Manual seeds с одинаковым known artist отклоняются. Generated previews тоже
сохраняют строгий known-artist guard.

## Core controls

| Control | Meaning |
| --- | --- |
| `Set mode` | Similar crate, weird adjacent, balanced set или discovery. |
| `Track limit` | Количество preview tracks, от 1 до 500. |
| `Auto anchors` | Количество automatic anchors, от 1 до 5. |
| `Energy curve` | Warmup, balanced, peak или wave intensity shape. |
| `Diversity` | Насколько широко route исследует related candidates. |

## BPM controls

`BPM mode = general` сохраняет обычную transition compatibility.
`low_to_high` или `high_to_low` добавляют actual BPM trajectory.

Если в file tags есть BPM, SET предпочитает его. SONARA BPM используется как
fallback. Half/double tempo matching помогает transition compatibility, но не
переписывает actual BPM trajectory.

## Classifier controls

Promoted classifier scores - optional modifiers. Missing scores остаются
neutral. Preference может быть positive или negative, flow - flat, rise или
fall.

`Reset sliders` сбрасывает diversity и classifier preference/flow values, но не
меняет seed source, mode, limit, anchors, energy curve или BPM controls.

## Добавить preview

Сгенерируйте preview, послушайте, проверьте список и только потом используйте
add action для переноса preview в current set. Export остается отдельным шагом.
