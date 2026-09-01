# Build crates for later listening

A crate is useful when you want to collect possibilities before deciding on an order. It can hold a
sound family or a warmup direction. Difficult-to-name textures and tracks that deserve another
listening pass also fit here.

The result is a reviewed pool, broader than a set. Revisit it later or play it outside the app. It
can also feed a later selection pass. Control names below are given in English, and
[UI language](../help/ui-language.md) carries the on-screen string for each one.

## Recipe

1. Scan and analyze enough of the library for the search surface you need.
2. Use the library search box to narrow by artist, title, album, path, or MAEST genres, then add the
   liked-only filter, the syncopated-rhythm preset, or a classifier minimum score.
3. Press the plus icon at the right of the library controls to add every loaded row of the current
   page to the set, when the filter already describes the crate. It works on the loaded page only,
   and it skips tracks already in the set.
4. Use the `SIMILARITY` or `SONARA` tab from a few seeds to expand around a sound.
5. Use the `PROMPT` tab when the crate is easier to describe than to seed. Pick presets from its
   picker rather than writing prose, because short tag lines measured stronger than scene
   descriptions.
6. Preview results and remove obvious misses with the trash icon on each set row, titled
   **Remove from the set**.
7. Export CSV for review or M3U for playback.

## Watch the page boundary

Library pages are fixed at up to `200` tracks per request, and both the add-visible button and the
shuffle/sort controls act on the loaded page only. A crate built from a wide filter needs a pass per
page.

## Useful split

- Use CSV when you want metadata and path review. Its columns are `artist,title,bpm,key,energy,path`.
- Use M3U when you want to load the list into a player.
- Use `Collection` when the same track list should become Rhythm Lab review material.

## Keep score spaces apart

A crate assembled from several searches mixes evidence from different scales. A MERT cosine, a
SONARA Core score, a CLAP text contrast, and a classifier probability are not comparable numbers.
Judge the pool by ear rather than by re-sorting it on scores that came from different questions.

## Privacy

Crate exports contain local paths and possibly style decisions. Do not publish them without review.
