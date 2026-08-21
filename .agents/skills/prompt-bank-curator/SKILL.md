---
name: prompt-bank-curator
description: Owns the text-search preset and tag vocabulary of dj-track-similarity. Use when adding or reworking presets, axes, or zero-shot tag labels for CLAP and MuQ-MuLan, when a prompt bank needs wording review, when a label's reliability must be measured against Rhythm Lab labels with scripts/text_prompt_benchmark.py, or when textPromptPresets.ts and the tag vocabulary drift apart.
---

# Prompt Bank Curator

The search operator finds tracks. This skill owns the words it searches with: the
axes, the presets, and the zero-shot tag vocabulary, plus the evidence for how well
each one actually works.

## Layer Boundary

This skill owns vocabulary for the text and tagging layer built on **CLAP and MuQ-MuLan**.
The **SONARA, MERT, MAEST** layers, their features, their analysis jobs, and the promoted
Rhythm Lab classifiers belong to other agents.

Their signals are inputs here. Cross-check a label against SONARA tempo or energy, against
a MAEST genre, or against a promoted classifier score whenever that sharpens the judgement,
and never change how they are produced. Zero-shot tags are an additional evidence channel
beside MAEST genres and promoted classifiers, never a replacement, and they are never
written into `classifier_scores` or into audio files.

## Source Of Truth

- Vocabulary: `frontend/src/textPromptPresets.ts` — axes, presets, per-model prompt
  variants (`shared` / `clap` / `mulan`), `negativeWeight`, and `measured` ROC-AUC.
- Structure tests: `frontend/tests/textPromptPresets.test.mjs`.
- Benchmark: `scripts/text_prompt_benchmark.py` with `scripts/text_prompt_benchmark_prompts.json`.
- Labels for measurement: the Rhythm Lab database, bound to the catalog of
  `database/volumes_old.sqlite`. Five concepts are labelled today: break_energy,
  voice_presence, live_instrumentation, minimal_deep_tech, abstract_edge.

## What A Good Label Looks Like

Every preset or tag carries a positive bank, an optional negative bank, a weight, and,
where it can be measured, its reliability. The wording rules are measured on this
library:

1. Four to five short prompts, one of them a bare label anchor. One long caption is the
   least stable form; it ranged from 0.955 to 0.495 ROC-AUC depending only on wording.
2. No word from the competing class inside a positive prompt. "over the instrumental"
   inside a voice prompt cost 0.873 to 0.640.
3. No `no`, `not`, `without` anywhere in a positive. Name the competing class in the
   negative bank instead.
4. A negative bank only when it names a real competing class. Where it does, weights of
   0.75-1.0 help; where it was invented, ROC-AUC fell monotonically, so ship `negativeWeight: 0`
   and no negatives at all.
5. Every prompt stays far below the 77-token CLAP ceiling; the current presets peak at 19.
6. Presets that get compared with each other keep the same number of positives.

## Granularity Honesty

Fine-grained labels are weaker than coarse ones, and this is not fixable by wording.
Measured here, "live instrumentation" reaches only 0.778 with MuQ-MuLan and 0.792 with
CLAP, and two-tower text towers are known to be weak at instrument identity. So:

- Mark every label with what is known about it: measured ROC-AUC per model, or explicitly
  unvalidated.
- Never present an unvalidated fine-grained label as if it were as trustworthy as a
  measured coarse one.
- Prefer adding a label as unvalidated over silently implying precision.

## Genres

MAEST already produces genre labels from the Discogs taxonomy. The zero-shot genre
vocabulary is **complementary**: scenes and sub-styles that taxonomy misses or keeps too
coarse. Do not duplicate the mainline taxonomy, and expect to lose to MAEST where they
overlap. A disagreement between MAEST and a tag is a signal worth surfacing, not a bug.

## Workflow

1. **Draft.** Write the bank as JSON and check the structure without loading any model:
   `python .agents\skills\clap-query-workflow\scripts\validate_prompt_bank.py <draft.json>`
2. **Measure, when labels exist.** Add the concept to
   `scripts/text_prompt_benchmark_prompts.json` and run:
   `python scripts\text_prompt_benchmark.py --db database\volumes_old.sqlite --models mulan,clap`
   Record ROC-AUC and average precision per model.
3. **Sweep the negative weight** over 0, 0.15, 0.35, 0.5, 0.75, 1.0. Adopt the peak. If the
   curve falls monotonically, the negatives are wrong: remove them and set the weight to 0.
4. **Land it** in `frontend/src/textPromptPresets.ts` with `measured` filled in, or marked
   unvalidated, and the axis it belongs to.
5. **Verify** with `cd frontend; node --test tests/textPromptPresets.test.mjs; npm run typecheck`.
6. **Listen.** For anything unmeasurable, ask the user to audition the top ten and record the
   verdict beside the label. Ears are the only ground truth for concepts with no labels.

## Axes

The vocabulary is organised on axes so presets can be combined and tags can become
coordinates for set building: groove, low end, texture, voice, instruments, space,
energy, style. An axis is exclusive only when exactly one of its labels can be true at a
time; exclusive axes are scored with a softmax inside the group, everything else stays an
independent percentile.

When adding a label, place it on an existing axis or justify a new one. An axis with a
single label is a smell.

## Verification

- Structure and wording: `cd frontend; node --test tests/textPromptPresets.test.mjs`
- Types: `cd frontend; npm run typecheck`
- Skill contract: `.\.venv\Scripts\python.exe -m pytest tests\test_clap_query_workflow_scripts.py --override-ini addopts=`
- Reliability claims: a committed benchmark table, never an impression.
