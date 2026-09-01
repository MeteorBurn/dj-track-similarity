# Find compatible tracks around a reference

Here, "compatible" means worth auditioning next to the reference under the search question you
choose. It does not mean guaranteed harmonic, rhythmic, or stylistic compatibility.

The useful result is a manageable list of alternatives and adjacent ideas. Export the list as a
crate, reuse useful tracks as new seeds, or add the strongest candidates to the current set. Control
names below are given in English, and [UI language](../help/ui-language.md) carries the on-screen
string for each one.

## Steps

1. Search the library for the reference track in panel 2, library and listening.
2. Press the magnifier icon on its row, titled `Seed`. The track appears as a chip above the tab
   strip in panel 3, search and listening.
3. Open the `SIMILARITY` tab, leave its `Model` select on `MERT`, and press `Search` for
   embedding-near candidates.
4. Open the `SONARA` tab and press `SONARA search` when you want more control over rhythm, timbre,
   dynamics, harmonic color, or tempo. Its `Mode` select opens on `Custom mixer`, where the sliders
   are active.
5. Raise `Limit` if you want to hear more lower-ranked candidates. It runs `1..500` and is shared
   between the `SONARA`, `SIMILARITY`, and `PROMPT` tabs.
6. Preview candidates before adding them to the current set.
7. Add good candidates with the plus icon titled **Add to the set**, then export or save them as a
   Rhythm Lab collection.

With no reference in mind, press **Add Random Track** in either tab. It pulls one eligible track
from the library and seeds the search with it.

## Compare model ears first

When one reference feels important and you do not know which family hears it well, open the `LAB`
tab and press `Compare models`. It ranks candidates for the first seed with CLAP, MERT, MuQ,
MuQ-MuLan, MAEST, and SONARA in six separate columns, at up to `100` candidates each. Use it to pick
the family worth searching properly, then go back to `SIMILARITY` or `SONARA`.

## When one seed is too narrow

Add a second or third seed that represents the intended direction. The query becomes the normalized
mean of the seed rows, so unrelated seeds blur the target rather than widening it. The API accepts
one to five seeds.

## Tempo note

Tempo-aware search starts with current SONARA evidence. Below `0.45` confidence, it inspects ranked
SONARA candidates and the Mutagen BPM tag. A tag BPM within 4 BPM of a SONARA option is promoted
as tag-confirmed evidence. Grid stability can weaken the evidence. Low reliability moves the score
toward neutral rather than creating a bonus or an automatic rejection. A missing BPM confidence
yields zero reliability and the neutral score, so the tag BPM is not promoted then.

## Output

Keep a small result in the current set while you compare by ear. For a reusable review list, export
CSV. For a player or DJ app, export M3U and verify that the paths work on the target machine. Both
buttons are inside the collapsible **Set and export** block.
