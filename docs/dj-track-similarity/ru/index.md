---
layout: page
title: DJ Track Similarity
aside: false
---

<!-- markdownlint-disable MD033 MD041 -->

<section class="dts-hero" aria-labelledby="dts-hero-title">
  <div class="dts-hero-copy">
    <h1 id="dts-hero-title">DJ Track Similarity</h1>
    <p class="dts-hero-lead">
      Локальный анализ DJ-библиотеки: соберите searchable crates, ищите похожие
      треки по звуку и готовьте идеи сетов без загрузки аудио наружу.
    </p>
    <div class="dts-hero-actions" aria-label="Основные пути документации">
      <a
        class="dts-button dts-button-brand"
        href="/docs/ru/getting-started/quickstart.html"
      >Начать</a>
      <a class="dts-button" href="/docs/ru/user-guide/">UI-гайд</a>
      <a class="dts-button" href="/docs/ru/reference/">Reference</a>
    </div>
  </div>
  <div class="dts-hero-console" aria-label="Превью локального workflow">
    <div class="dts-console-topline">
      <span>local session</span>
      <strong>safe by default</strong>
    </div>
    <div class="dts-console-row is-active">
      <span>scan</span>
      <strong>tags -> SQLite</strong>
    </div>
    <div class="dts-console-row">
      <span>analyze</span>
      <strong>SONARA / MERT / CLAP / MAEST</strong>
    </div>
    <div class="dts-console-row">
      <span>audition</span>
      <strong>seed search, text search, SET preview</strong>
    </div>
    <div class="dts-console-footer">
      <span>audio files</span>
      <strong>unchanged unless you choose an explicit write workflow</strong>
    </div>
  </div>
</section>

<section class="dts-workbench" aria-labelledby="dts-workbench-title">
  <div class="dts-workbench-copy">
    <p class="dts-eyebrow">Local workflow surface</p>
    <h2 id="dts-workbench-title">От crate к shortlist, с рискованными шагами
      отдельно.</h2>
    <p>
      Документация теперь строится вокруг реального workbench: просканировать
      маленькую папку, добрать недостающий анализ, прослушать кандидатов и
      экспортировать проверенный список. File writes и deletes вынесены из
      обычного пути.
    </p>
  </div>
  <ol class="dts-signal-chain" aria-label="Main documentation workflow">
    <li>
      <span class="dts-step">01</span>
      <strong>Scan</strong>
      <span>tags -> SQLite</span>
    </li>
    <li>
      <span class="dts-step">02</span>
      <strong>Analyze</strong>
      <span>SONARA / MERT / CLAP / MAEST</span>
    </li>
    <li>
      <span class="dts-step">03</span>
      <strong>Audition</strong>
      <span>seed search and SET preview</span>
    </li>
    <li>
      <span class="dts-step">04</span>
      <strong>Export</strong>
      <span>reviewed playlist or report</span>
    </li>
  </ol>
</section>

<section class="dts-status-board" aria-label="Documentation safety boundaries">
  <div>
    <span class="dts-status-label">Normal path</span>
    <strong>Read-only toward audio</strong>
    <p>Browse, preview, search, SET, reset and export не переписывают source
      files.</p>
  </div>
  <div>
    <span class="dts-status-label">Explicit write</span>
    <strong>Genre tags only</strong>
    <p>MAEST genre labels пишутся только через documented tag-write workflow.</p>
  </div>
  <div>
    <span class="dts-status-label">Maintenance</span>
    <strong>Dry-run before apply</strong>
    <p>Repair and dedup workflows начинаются с reports и держат apply modes
      отдельно.</p>
  </div>
</section>

## Что это за проект

`dj-track-similarity` - локальный инструмент для DJs, коллекционеров музыки и
power users, которые работают с локальными аудиофайлами. Он сканирует
библиотеку в SQLite, запускает опциональный аудиоанализ и дает browser UI для
просмотра, поиска, подготовки временных сетов и экспорта плейлистов.

Это персональный enthusiast-проект, а не коммерческий продукт и не research
benchmark. Оценки похожести полезны как подсказки для ранжирования, но
финальное музыкальное решение остается за вами.

## Куда идти сначала

| Если нужно... | Начните с |
| --- | --- |
| установить и открыть UI | [Quickstart](getting-started/quickstart.md) |
| понять safety model | [Local-first safety](concepts/local-first-safety.md) |
| искать и слушать из UI | [User guide](user-guide/index.md) |
| подготовить идею сета | [Prepare a set](workflows/prepare-a-set.md) |
| найти CLI/API/DB детали | [Reference](reference/index.md) |
| починить частые ошибки | [Troubleshooting](help/troubleshooting.md) |

## Обычный путь

```mermaid
flowchart LR
    A[Выбрать локальную папку с музыкой] --> B[Сканировать теги в SQLite]
    B --> C[Запустить нужные analysis families]
    C --> D[Искать по seed, features, text или classifier scores]
    D --> E[Проверить preview в UI]
    E --> F[Экспортировать временный playlist]
```

Сканирование и анализ создают локальное состояние базы. Поиск и Smart Set
Builder создают preview. Export пишет playlist/report файлы. Исходное аудио не
меняется, кроме явно выбранных workflows для записи тегов, repair или duplicate
apply.
