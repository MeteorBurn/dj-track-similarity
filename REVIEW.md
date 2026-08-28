

# Primary goal

Deeply understand how the whole project actually works, then identify the highest-value ways to improve it.

Priorities, in order:

1. Correctness

2. Architectural simplification

3. Reliability

4. MIR / similarity quality

5. Performance

6. Maintainability

7. Test quality

8. Developer ergonomics

Do NOT optimize for preserving the current architecture.

If the same behavior can be achieved with fewer abstractions, fewer modules, fewer files, clearer data flow, or a substantially simpler architecture, prefer the simpler solution.

At the same time, do NOT perform speculative rewrites or cosmetic refactoring.

Every significant proposed change must be justified by evidence from the actual repository.

# Project context

`dj-track-similarity` is a local music-information-retrieval system intended for a large DJ music library.

Its purpose is not generic genre classification.

The important use case is:

- finding tracks similar by sound, vibe, atmosphere and musical characteristics;

- finding tracks that work together in DJ sets;

- going beyond simple BPM / key / genre matching;

- combining several complementary audio representations;

- eventually supporting automatic set construction and dramaturgy.

The project includes or has included models/signals such as:

- MERT

- CLAP

- MAEST

- SONARA

- MuQ / MuQ-MuLan or related integration work

- custom classifiers

- BPM / musical metadata

- Hybrid similarity/scoring

There are also concepts such as:

- embeddings

- track similarity

- model-specific search

- hybrid ranking

- classifier signals

- transition/mixability signals

- feedback/judged evaluation

- score/profile optimization

- persistent ANN/indexing

- SQLite-backed state/metadata

- audio preprocessing/decoding

- React/TypeScript UI

The library can become very large, so architecture and performance must make sense at tens of thousands to approximately 100k tracks rather than only on toy datasets.

The project should remain practical on Windows and Linux.

# Important philosophy

This codebase has evolved through experimentation.

Therefore, actively investigate whether experimental layers, adapters, abstractions, old compatibility paths, duplicated implementations, temporary architecture, or prematurely generalized systems have survived after their original purpose disappeared.

Do not assume complexity is intentional just because it already exists.

A major objective of this audit is to discover opportunities to make the project smaller and easier to understand while preserving useful functionality.

Be especially suspicious of:

- abstractions with only one meaningful implementation;

- wrapper-on-wrapper architecture;

- repeated adapters;

- duplicated model pipelines;

- compatibility layers nobody needs anymore;

- pass-through classes/functions;

- excessive dependency injection;

- configuration that merely mirrors function arguments;

- factories that add no useful abstraction;

- tiny modules split unnecessarily;

- APIs created only to accommodate old architecture;

- duplicated preprocessing paths;

- duplicated persistence/indexing logic;

- parallel implementations that have drifted apart;

- tests whose only purpose is protecting obsolete architecture.

Do NOT add more architecture to fix excessive architecture.

# Phase 1 — Understand the repository

Before proposing changes, explore the repository deeply.

Read applicable project instructions first.

Then construct an internal map of:

- packages/modules;

- CLI/application entry points;

- backend services;

- frontend;

- configuration;

- model adapters;

- audio loading/preprocessing;

- embedding extraction;

- indexing;

- persistence;

- similarity calculation;

- ranking;

- hybrid scoring;

- classifiers;

- evaluation;

- feedback;

- API boundaries;

- background/batch processing;

- tests;

- scripts/tools;

- documentation relevant to implementation.

Do not review files independently.

Trace actual execution paths end-to-end.

For example, where applicable:

audio file  
→ decoding  
→ preprocessing  
→ segmentation  
→ model inference  
→ embedding normalization  
→ persistence  
→ ANN/index  
→ candidate retrieval  
→ scoring  
→ hybrid ranking  
→ API  
→ UI

Trace several representative workflows this way.

Determine which code actually participates in production/runtime behavior and which code is legacy, experimental, duplicated, or unused.

Use git history/blame when useful to understand suspicious architecture, but judge the current design on current requirements rather than historical intent.

# Phase 2 — MIR correctness audit

Pay special attention to problems that could silently make similarity results worse even if the software appears to work.

Investigate:

## Audio decoding and preprocessing

Check:

- sample-rate assumptions;

- resampling;

- mono/stereo handling;

- channel mixing;

- dtype/range conversion;

- normalization;

- clipping;

- padding;

- truncation;

- segment/window selection;

- deterministic vs random preprocessing;

- track duration handling;

- short-track handling;

- decoder differences;

- inconsistent preprocessing between indexing and querying.

Determine whether each model receives the audio representation it actually expects.

Look for subtle differences between model pipelines that may invalidate comparisons or produce inconsistent results.

## Model inference

For each embedding/model pipeline, examine:

- model loading lifecycle;

- device selection;

- CPU/GPU transfers;

- dtype;

- inference mode / no_grad;

- batching;

- memory usage;

- preprocessing;

- output selection;

- pooling;

- embedding dimensions;

- normalization;

- caching;

- determinism;

- failure handling.

Verify that embeddings generated during database/index creation are semantically compatible with embeddings generated during queries.

## Embedding similarity

Audit:

- cosine similarity;

- dot product;

- Euclidean distance where applicable;

- vector normalization;

- ANN distance metric;

- index configuration;

- score conversion;

- score direction;

- ranking order;

- thresholds.

Look for situations where normalized and non-normalized vectors are mixed.

Check whether ANN retrieval and final exact scoring are mathematically consistent.

## Multiple models

Determine whether MERT, CLAP, MAEST, MuQ/MuLan, SONARA and custom signals have sufficiently clean model boundaries.

Look for duplicated infrastructure that could be replaced by a small common inference contract without forcing fundamentally different models into an inappropriate abstraction.

Avoid both extremes:

- duplicated implementation everywhere;

- an over-generalized universal model framework.

Find the smallest useful common abstraction.

## Hybrid similarity

Inspect the complete Hybrid ranking path.

Determine:

- how individual signals are normalized;

- whether scores from different models are actually comparable;

- how weights are applied;

- whether missing signals change score scale;

- whether fallback behavior is mathematically sound;

- whether one model can dominate accidentally;

- whether weights correspond to empirical evaluation;

- whether score transformations distort ranking;

- whether per-model confidence is represented correctly.

Look for hidden coupling between UI settings, stored profiles and backend scoring.

## BPM / musical metadata

Where BPM, key, Camelot or other external/analyzed metadata participates in similarity or mixability:

- inspect fallback rules;

- inspect missing values;

- inspect half/double BPM handling;

- distinguish metadata confidence from actual value;

- check whether metadata affects similarity in unexpected ways.

Do not assume SONARA BPM and externally sourced/Mixed-In-Key-style metadata have identical reliability.

## Custom classifiers

Inspect training and inference separately.

Look for:

- train/inference preprocessing mismatch;

- label leakage;

- accidental class imbalance;

- invalid threshold assumptions;

- inconsistent feature normalization;

- stale checkpoints;

- feature/model version mismatch;

- ambiguous positive-only semantics;

- accidental coupling between classifier training experiments and production inference.

# Phase 3 — Architecture audit

Identify architecture that can be simplified.

For every major subsystem ask:

1. What responsibility does it own?

2. Who calls it?

3. What does it depend on?

4. Does the abstraction protect a real boundary?

5. Could this be understood with fewer layers?

6. Is the same concept represented multiple times?

7. Is state ownership obvious?

8. Is configuration ownership obvious?

9. Could a developer change this subsystem without understanding unrelated parts?

Search specifically for:

- circular dependencies;

- unclear ownership;

- duplicated concepts;

- god objects;

- service-locator patterns;

- excessive registries;

- excessive factories;

- needless inheritance;

- generic frameworks built for hypothetical future models;

- model-specific hacks leaking into generic layers;

- backend/frontend duplicated business logic;

- unnecessary mutable global state;

- configuration scattered across modules;

- incorrect package boundaries.

Estimate where deleting code is better than refactoring it.

# Phase 4 — Data and persistence

Deeply inspect SQLite/database usage and persistent artifacts.

Check:

- schema ownership;

- migrations;

- transaction handling;

- concurrency;

- connection lifecycle;

- indexes;

- N+1 patterns;

- bulk operations;

- unnecessary commits;

- repeated queries;

- stale data;

- cache invalidation;

- model/version metadata;

- embedding provenance;

- classifier version provenance.

The system must be able to tell whether a stored embedding/index was generated by a compatible:

- model;

- model version;

- preprocessing version;

- embedding dimension;

- normalization strategy;

- segmentation strategy.

If that guarantee is missing or fragile, report it prominently.

# Phase 5 — ANN / large-library scalability

Evaluate behavior for approximately 50k–100k tracks.

Investigate:

- persistent ANN lifecycle;

- full rebuilds;

- incremental indexing;

- invalidation;

- duplicate vectors;

- stale vectors;

- memory mapping;

- startup cost;

- query latency;

- batch insertion;

- exact reranking;

- serialization;

- consistency between DB state and ANN state.

Do not prematurely optimize.

Identify actual algorithmic or architectural bottlenecks first.

Separate:

- problems relevant at 100k tracks;

- theoretical scaling concerns that do not matter yet.

# Phase 6 — Performance

Look for measurable high-value improvements.

Especially inspect:

- repeated model loading;

- repeated audio decoding;

- repeated resampling;

- unnecessary tensor copies;

- CPU↔GPU transfers;

- tiny GPU batches;

- excessively large GPU batches;

- per-track DB transactions;

- redundant serialization;

- duplicate feature extraction;

- recomputing immutable data;

- synchronous work unnecessarily blocking UI/API;

- unnecessary filesystem scans.

Prioritize structural performance improvements over micro-optimizations.

# Phase 7 — Frontend/API integration

Trace important React/TypeScript flows into backend behavior.

Check for:

- duplicated backend state;

- stale client state;

- inconsistent API types;

- implicit defaults;

- race conditions;

- unnecessary polling;

- broken cancellation;

- expensive rerenders;

- state synchronization problems;

- errors swallowed by the UI;

- backend errors converted into misleading UI states.

Identify UI architecture that exists only because backend boundaries are unnecessarily complicated.

# Phase 8 — Cross-platform reliability

The project should work cleanly on Windows and Linux.

Inspect assumptions involving:

- filesystem paths;

- separators;

- case sensitivity;

- subprocess invocation;

- shell commands;

- FFmpeg/audio tools;

- temporary files;

- multiprocessing;

- file locking;

- Unicode paths;

- long paths;

- CUDA;

- CPU fallback;

- environment variables.

Prefer Python/native-library behavior over shell-specific workarounds where practical.

# Phase 9 — Dependencies

Inspect runtime and development dependencies.

Identify:

- unused dependencies;

- duplicated libraries solving the same problem;

- heavy dependencies used for trivial functionality;

- optional dependencies imported as mandatory;

- dependencies leaking across architectural boundaries;

- obsolete compatibility packages.

Do not remove a dependency merely to reduce the dependency count.

Remove or replace it only when there is a concrete benefit.

# Phase 10 — Tests

Do NOT optimize for having more tests.

Optimize for tests that protect important behavior.

Separate tests into:

- high-value behavioral tests;

- regression tests;

- integration tests;

- model/pipeline contract tests;

- low-value implementation-detail tests.

Find tests that make refactoring unnecessarily difficult because they assert internal architecture rather than observable behavior.

Look for missing tests around high-risk boundaries such as:

- audio preprocessing;

- embedding normalization;

- persisted embedding compatibility;

- ANN consistency;

- Hybrid ranking;

- fallback behavior;

- DB migrations;

- model failures.

Do not propose a huge test-suite expansion unless risk justifies it.

# Phase 11 — Dead code and repository reduction

Aggressively search for:

- unused modules;

- unused classes;

- unused functions;

- obsolete experiments;

- old model integrations;

- dead configuration options;

- stale feature flags;

- compatibility shims;

- duplicated scripts;

- tests covering code no longer used;

- documentation for removed behavior.

Use references/search/git history to distinguish genuinely dead code from dynamically used code.

Estimate how much of the repository can safely disappear.

Reducing code size is a positive outcome if behavior and clarity improve.

# Phase 12 — Evaluation architecture

Because this is a similarity system, subjective intuition alone is not sufficient.

Inspect whether the project has a coherent path from:

human feedback / judged pairs  
→ evaluation dataset  
→ metrics  
→ model comparison  
→ Hybrid weighting/profile optimization  
→ regression detection.

Determine whether current evaluation can actually tell us if a refactor or scoring change made recommendations better or worse.

Identify cases where architectural complexity exists without measurable evidence that it improves retrieval quality.

This is especially important.

A sophisticated similarity component that cannot demonstrate improvement over a simpler baseline should be questioned.

# Review standards

Do NOT report generic advice such as:

- "add documentation";

- "add more tests";

- "use dependency injection";

- "split large files";

- "apply SOLID";

- "improve error handling";

unless you identify a concrete location, concrete failure mode and concrete benefit.

Do not reward architectural sophistication.

Reward clarity.

Do not propose patterns simply because they are conventional.

Do not introduce new abstractions unless they eliminate more complexity than they add.

Prefer:

simple explicit code

> clever generic code

small coherent modules

> fragmented micro-modules

measured improvements

> theoretical improvements

behavioral contracts

> implementation-detail tests

deleting obsolete code

> maintaining compatibility nobody uses

# Finding confidence

Before reporting an issue, validate it.

Classify findings as:

- CONFIRMED

- HIGH CONFIDENCE

- NEEDS MEASUREMENT

Do not include low-confidence speculation in the main findings.

If something cannot be verified statically, say exactly what experiment or benchmark would verify it.

# Required output

Do not modify the repository yet.

First produce a complete audit.

Structure the result as:

## 1. System map

Concise explanation of how the current system actually works.

Include important execution/data flows and architectural boundaries.

## 2. Executive findings

The 10–20 highest-value findings across the entire repository.

For every finding include:

- Severity: Critical / High / Medium / Low

- Confidence

- Area

- Exact files/modules/symbols

- Evidence

- Why it matters

- Proposed change

- Expected impact

- Risk of change

## 3. Correctness risks

Especially silent issues that could alter similarity/search results.

## 4. MIR / retrieval-quality risks

Problems that may reduce recommendation quality even though the application functions correctly.

## 5. Architecture simplification

Show specifically which layers/modules/abstractions could:

- disappear;

- merge;

- become simpler;

- move;

- lose generic infrastructure.

Where possible estimate:

CURRENT:  
A → B → C → D → E

PROPOSED:  
A → B → C

Explain why.

## 6. Dead/obsolete code

List concrete deletion candidates with confidence.

## 7. Performance/scalability

Separate:

- currently relevant;

- relevant around 100k tracks;

- premature optimization.

## 8. Persistence/index consistency

Report DB/embedding/ANN/versioning risks separately.

## 9. Test architecture

Explain what tests are valuable, what tests create noise, and which critical contracts are insufficiently protected.

## 10. Repository reduction estimate

Give a rough assessment of whether the repository appears:

- appropriately sized;

- moderately over-engineered;

- heavily over-engineered.

Identify the largest opportunities to reduce conceptual and physical code size.

## 11. Target architecture

Describe what the project should look like after high-value simplification.

Do NOT design an entirely new system unless the current one truly requires it.

Prefer evolution from the current implementation.

Show the main modules and data flow.

## 12. Prioritized improvement roadmap

Create phases.

For each phase specify:

- exact goal;

- affected subsystem;

- expected benefit;

- behavior that must remain unchanged;

- tests/evaluation needed before and after;

- dependencies on other phases;

- estimated risk.

Prioritize by:

impact × confidence ÷ risk

not by ease of implementation.

# Important final step

After producing the audit, critically review your OWN findings.

Try to disprove the major recommendations.

Remove recommendations that are:

- speculative;

- cosmetic;

- architecture-for-architecture's-sake;

- unlikely to produce meaningful benefit.

Then present the final validated audit.

Do not start modifying code until the audit and roadmap are complete.

Once the audit is complete, stop and wait for the next instruction before implementation.
