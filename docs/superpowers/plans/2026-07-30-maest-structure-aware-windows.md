# MAEST Structure-Aware Window Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select up to three centered MAEST windows from the best available current-generation SONARA content range, require current SONARA before project ML/classifier work, and preserve score precision and embedding behavior.

**Architecture:** Add a pure `maest_windows` module that owns the optional SONARA boundary value and deterministic start selection. Candidate collection attaches current-generation boundaries, and the existing MAEST runner passes them to the adapter without changing shared decoding or any other model family.

**Tech Stack:** Python 3.10+, dataclasses, NumPy, SQLite through `LibraryDatabase`, pytest.

## Global Constraints

- MAEST uses `discogs-maest-30s-pw-129e-519l` through `maest-infer==0.2.0`.
- MAEST windows remain 30 seconds at 16 kHz `float32`.
- Window centers are exactly `(0.2, 0.5, 0.8)`.
- Deduplicate starts only when their distance is less than `1.0` second.
- Range fallback order is main range, non-silent range, full decoded duration.
- SONARA context is optional and must match the track's current `content_generation`.
- Project ML jobs select only tracks with current-generation SONARA.
- ML and classifier jobs cannot start until the catalog contains at least one
  current-generation SONARA result.
- A pipeline containing SONARA may establish that prerequisite before ML and
  classifiers start.
- Direct adapter calls and current SONARA rows without usable structure values
  retain the full-duration window fallback.
- Do not persist `energy_curve`, `segments`, or per-track MAEST offsets.
- Preserve full scalar precision and the current mean-before-top-K score aggregation.
- Preserve 768-dimensional MAEST window-mean plus L2-normalized embeddings.
- Do not modify source audio or tags.
- Do not use a real project database or real music files in tests.
- Preserve unrelated worktree changes and stage only the files named by each task.

---

## File Structure

- Create `src/dj_track_similarity/maest_windows.py`: immutable boundary context, constants, range fallback, and pure start calculation.
- Create `tests/test_maest_windows.py`: exhaustive unit tests for starts and fallback behavior.
- Modify `src/dj_track_similarity/analysis_models.py`: add optional MAEST context to `AnalysisCandidate` and update canonical MAEST runtime metadata.
- Modify `src/dj_track_similarity/db_analysis_candidates.py`: read current-generation SONARA boundaries into candidates.
- Modify `tests/test_analysis_repository.py`: repository coverage for current and stale SONARA generations.
- Modify `src/dj_track_similarity/genres.py`: consume contexts while preparing per-track windows.
- Modify `src/dj_track_similarity/analysis_model_runners.py`: pass candidate contexts to the adapter.
- Modify `tests/test_genres.py`: verify context-aware window slicing and unchanged short-track padding.
- Modify `tests/test_analysis_orchestration.py`: verify runner-to-adapter context propagation and unchanged persistence.
- Modify `tests/test_model_adapter_identity.py`: verify the reported active window policy.
- Modify `docs/dj-track-similarity/reference/analysis-families.md`: document the MAEST window policy.
- Modify `docs/dj-track-similarity/ru/reference/analysis-families.md`: maintain the Russian mirror.

---

### Task 1: Pure MAEST window selector

**Files:**

- Create: `src/dj_track_similarity/maest_windows.py`
- Create: `tests/test_maest_windows.py`

**Interfaces:**

- Produces: `MaestWindowContext`
- Produces: `MAEST_WINDOW_POSITIONS`
- Produces: `MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS`
- Produces: `select_maest_window_starts(duration_seconds, window_seconds, context=None) -> tuple[float, ...]`
- Consumes: no project database or model runtime

- [ ] **Step 1: Write the failing pure-selection tests**

Create `tests/test_maest_windows.py` with duration, boundary, fallback, and invalid-context cases:

```python
from __future__ import annotations

import math

import pytest

from dj_track_similarity.maest_windows import (
    MaestWindowContext,
    select_maest_window_starts,
)


@pytest.mark.parametrize(
    ("duration", "expected"),
    (
        (20.0, (0.0,)),
        (30.0, (0.0,)),
        (30.5, (0.0,)),
        (40.0, (0.0, 5.0, 10.0)),
        (60.0, (0.0, 15.0, 30.0)),
        (180.0, (21.0, 75.0, 129.0)),
        (300.0, (45.0, 135.0, 225.0)),
    ),
)
def test_centered_full_duration_starts(
    duration: float,
    expected: tuple[float, ...],
) -> None:
    assert select_maest_window_starts(duration, 30.0) == expected


def test_prefers_intro_outro_range_inside_non_silent_range() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )

    assert select_maest_window_starts(200.0, 30.0, context) == (
        51.0,
        90.0,
        129.0,
    )


def test_short_main_range_relaxes_to_non_silent_range() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=100.0,
        outro_start_seconds=120.0,
    )

    assert select_maest_window_starts(200.0, 30.0, context) == pytest.approx(
        (27.0, 82.5, 138.0)
    )


def test_short_non_silent_range_relaxes_to_full_duration() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=20.0,
        trailing_silence_seconds=20.0,
        intro_end_seconds=None,
        outro_start_seconds=None,
    )

    assert select_maest_window_starts(60.0, 30.0, context) == (
        0.0,
        15.0,
        30.0,
    )


@pytest.mark.parametrize(
    "context",
    (
        MaestWindowContext(
            leading_silence_seconds=math.nan,
            trailing_silence_seconds=None,
            intro_end_seconds=None,
            outro_start_seconds=None,
        ),
        MaestWindowContext(
            leading_silence_seconds=None,
            trailing_silence_seconds=None,
            intro_end_seconds=170.0,
            outro_start_seconds=40.0,
        ),
    ),
)
def test_invalid_context_falls_back_without_failure(
    context: MaestWindowContext,
) -> None:
    assert select_maest_window_starts(200.0, 30.0, context) == (
        25.0,
        85.0,
        145.0,
    )


def test_rejects_invalid_duration_or_window() -> None:
    with pytest.raises(ValueError, match="duration_seconds"):
        select_maest_window_starts(0.0, 30.0)
    with pytest.raises(ValueError, match="window_seconds"):
        select_maest_window_starts(60.0, 0.0)
```

- [ ] **Step 2: Run the new tests and verify the missing-module failure**

Run:

```powershell
python -m pytest tests\test_maest_windows.py --override-ini addopts=
```

Expected: collection fails because `dj_track_similarity.maest_windows` does not exist.

- [ ] **Step 3: Implement the immutable context and deterministic selector**

Create `src/dj_track_similarity/maest_windows.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass


MAEST_WINDOW_POSITIONS = (0.2, 0.5, 0.8)
MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class MaestWindowContext:
    leading_silence_seconds: float | None
    trailing_silence_seconds: float | None
    intro_end_seconds: float | None
    outro_start_seconds: float | None


def select_maest_window_starts(
    duration_seconds: float,
    window_seconds: float,
    context: MaestWindowContext | None = None,
) -> tuple[float, ...]:
    duration = _positive_finite(duration_seconds, "duration_seconds")
    window = _positive_finite(window_seconds, "window_seconds")
    if duration <= window:
        return (0.0,)

    selected_range = _selected_range(duration, window, context)
    range_start, range_end = selected_range
    max_start = range_end - window
    starts: list[float] = []
    for position in MAEST_WINDOW_POSITIONS:
        center = range_start + position * (range_end - range_start)
        start = min(max(range_start, center - window / 2.0), max_start)
        if not any(
            abs(start - existing) < MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS
            for existing in starts
        ):
            starts.append(start)
    return tuple(starts) or (range_start,)


def _selected_range(
    duration: float,
    window: float,
    context: MaestWindowContext | None,
) -> tuple[float, float]:
    full = (0.0, duration)
    if context is None:
        return full

    leading = _optional_boundary(context.leading_silence_seconds, duration)
    trailing = _optional_boundary(context.trailing_silence_seconds, duration)
    hard_start = 0.0 if leading is None else leading
    hard_end = duration if trailing is None else duration - trailing
    hard = (hard_start, hard_end)

    intro = _optional_boundary(context.intro_end_seconds, duration)
    outro = _optional_boundary(context.outro_start_seconds, duration)
    main = (
        max(hard_start, 0.0 if intro is None else intro),
        min(hard_end, duration if outro is None else outro),
    )
    for candidate in (main, hard, full):
        if candidate[1] - candidate[0] >= window:
            return candidate
    return full


def _optional_boundary(value: float | None, duration: float) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return min(max(number, 0.0), duration)


def _positive_finite(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return number
```

- [ ] **Step 4: Run the pure-selection tests**

Run:

```powershell
python -m pytest tests\test_maest_windows.py --override-ini addopts=
```

Expected: all tests pass.

- [ ] **Step 5: Commit the selector**

Run:

```powershell
git add -- src/dj_track_similarity/maest_windows.py tests/test_maest_windows.py
git diff --cached --check
git commit -m "feat: add structure-aware MAEST window selector"
```

Expected: one commit containing only the selector and its tests.

---

### Task 2: Attach current-generation SONARA context to candidates

**Files:**

- Modify: `src/dj_track_similarity/analysis_models.py:818-847`
- Modify: `src/dj_track_similarity/db_analysis_candidates.py:71-82`
- Modify: `src/dj_track_similarity/db_analysis_candidates.py:281-315`
- Modify: `tests/test_analysis_repository.py:1-163`

**Interfaces:**

- Consumes: `MaestWindowContext` from Task 1
- Produces: `AnalysisCandidate.maest_window_context: MaestWindowContext | None`
- Produces: candidate query fields joined only from `sonara.content_generation = tracks.content_generation`

- [ ] **Step 1: Write failing repository tests for current and stale SONARA rows**

Add imports to `tests/test_analysis_repository.py`:

```python
from dj_track_similarity.maest_windows import MaestWindowContext
```

Add a helper:

```python
def _insert_sonara_window_context(
    repository: LibraryDatabase,
    *,
    generation: int,
) -> None:
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO sonara(
                track_id, content_generation,
                analyzed_duration_seconds,
                intro_end_seconds, outro_start_seconds,
                leading_silence_seconds, trailing_silence_seconds,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (1, ?, 200.0, 40.0, 170.0, 5.0, 10.0, ?, ?, ?, ?)
            """,
            (
                generation,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                ANALYZED_AT,
            ),
        )
        connection.commit()
```

Add the tests:

```python
def test_candidate_includes_current_sonara_maest_window_context(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _insert_sonara_window_context(repository, generation=1)

    candidate = repository.list_analysis_candidates(
        (AnalysisOutput("maest", "embedding"),)
    )[0]

    assert candidate.maest_window_context == MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )


def test_candidate_ignores_stale_sonara_maest_window_context(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _insert_sonara_window_context(repository, generation=1)
    with repository.connect() as connection:
        connection.execute(
            "UPDATE tracks SET content_generation = 2 WHERE track_id = 1"
        )
        connection.commit()

    candidate = repository.list_analysis_candidates(
        (AnalysisOutput("maest", "embedding"),)
    )[0]

    assert candidate.target.content_generation == 2
    assert candidate.maest_window_context is None
```

- [ ] **Step 2: Run the repository tests and verify the missing-field failure**

Run:

```powershell
python -m pytest tests\test_analysis_repository.py -k "maest_window_context" --override-ini addopts=
```

Expected: tests fail because `AnalysisCandidate` has no `maest_window_context`.

- [ ] **Step 3: Add the optional candidate field**

In `src/dj_track_similarity/analysis_models.py`, import and add:

```python
from .maest_windows import MaestWindowContext
```

```python
@dataclass(frozen=True)
class AnalysisCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    missing_outputs: tuple[AnalysisOutput, ...]
    maest_window_context: MaestWindowContext | None = None

    def __post_init__(self) -> None:
        # Preserve the existing path, size, timestamp, and output validation.
        if (
            self.maest_window_context is not None
            and not isinstance(self.maest_window_context, MaestWindowContext)
        ):
            raise TypeError(
                "maest_window_context must be a MaestWindowContext or None"
            )
```

Keep the existing `__post_init__` body and append only the context type check.

- [ ] **Step 4: Left-join current SONARA context during candidate collection**

Change `read_current_track_rows()` in
`src/dj_track_similarity/db_analysis_candidates.py` to:

```python
def read_current_track_rows(
    core_connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return core_connection.execute(
        """
        SELECT
            tracks.track_id, tracks.track_uuid, tracks.file_path,
            tracks.file_size_bytes, tracks.file_modified_ns,
            tracks.content_generation,
            sonara.leading_silence_seconds,
            sonara.trailing_silence_seconds,
            sonara.intro_end_seconds,
            sonara.outro_start_seconds
        FROM tracks
        LEFT JOIN sonara
          ON sonara.track_id = tracks.track_id
         AND sonara.content_generation = tracks.content_generation
        WHERE tracks.missing_since IS NULL
        ORDER BY tracks.file_path COLLATE NOCASE, tracks.track_id
        """
    ).fetchall()
```

Import the context and add a converter:

```python
from .maest_windows import MaestWindowContext


def _maest_window_context(row: sqlite3.Row) -> MaestWindowContext | None:
    values = (
        row["leading_silence_seconds"],
        row["trailing_silence_seconds"],
        row["intro_end_seconds"],
        row["outro_start_seconds"],
    )
    if all(value is None for value in values):
        return None
    return MaestWindowContext(
        leading_silence_seconds=(
            None if values[0] is None else float(values[0])
        ),
        trailing_silence_seconds=(
            None if values[1] is None else float(values[1])
        ),
        intro_end_seconds=None if values[2] is None else float(values[2]),
        outro_start_seconds=None if values[3] is None else float(values[3]),
    )
```

Pass it when constructing each candidate:

```python
maest_window_context=_maest_window_context(row),
```

- [ ] **Step 5: Run focused repository and candidate-readiness tests**

Run:

```powershell
python -m pytest tests\test_analysis_repository.py tests\test_scanner_database.py --override-ini addopts=
```

Expected: all tests pass, including unchanged readiness behavior.

- [ ] **Step 6: Commit candidate context**

Run:

```powershell
git add -- src/dj_track_similarity/analysis_models.py src/dj_track_similarity/db_analysis_candidates.py tests/test_analysis_repository.py
git diff --cached --check
git commit -m "feat: attach SONARA window context to analysis candidates"
```

Expected: one commit containing only the candidate model, query, and tests.

---

### Task 3: Use contexts in MAEST inference and report the new policy

**Files:**

- Modify: `src/dj_track_similarity/genres.py:21-76`
- Modify: `src/dj_track_similarity/genres.py:86-154`
- Modify: `src/dj_track_similarity/genres.py:177-204`
- Modify: `src/dj_track_similarity/genres.py:318-331`
- Modify: `src/dj_track_similarity/analysis_model_runners.py:169-227`
- Modify: `src/dj_track_similarity/analysis_model_runners.py:248-284`
- Modify: `src/dj_track_similarity/analysis_model_runners.py:440-470`
- Modify: `src/dj_track_similarity/analysis_models.py:199-234`
- Modify: `tests/test_genres.py:82-204`
- Modify: `tests/test_analysis_orchestration.py:442-510`
- Modify: `tests/test_model_adapter_identity.py:1-55`

**Interfaces:**

- Consumes: `select_maest_window_starts()` and `MaestWindowContext`
- Extends: `MaestGenreAdapter.predict_decoded_batch(decoded_items, window_contexts=None)`
- Preserves: `MaestGenreAdapter.predict_batch(paths)` without a required context
- Preserves: MAEST mean score aggregation and embedding aggregation

- [ ] **Step 1: Write failing adapter tests for context-aware slicing**

In `tests/test_genres.py`, import:

```python
from dj_track_similarity.maest_windows import MaestWindowContext
```

Add a direct preparation test:

```python
def test_maest_windows_use_sonara_main_range() -> None:
    sample_rate = 16_000
    audio = np.arange(sample_rate * 200, dtype=np.float32)
    adapter = BatchMaestAdapter()
    adapter._load_model()
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )

    prepared = adapter._prepare_audio_windows_from_audio(
        "structured.wav",
        audio,
        sample_rate,
        window_context=context,
    )

    assert [window[0].item() for window in prepared] == [
        sample_rate * 51,
        sample_rate * 90,
        sample_rate * 129,
    ]
    assert all(window.numel() == sample_rate * 30 for window in prepared)
```

Add a context-count guard:

```python
def test_maest_decoded_batch_rejects_context_count_mismatch() -> None:
    adapter = BatchMaestAdapter()
    decoded = [
        DecodedAudio(
            path="a.wav",
            audio=np.zeros(16_000 * 60, dtype=np.float32),
            sample_rate=16_000,
            detail="test",
        )
    ]

    with pytest.raises(ValueError, match="window context count"):
        adapter.predict_decoded_batch(decoded, window_contexts=[])
```

Update the existing
`test_maest_prepares_three_30_second_windows()` assertions for the new
full-duration fallback. A 200-second track now starts at 25, 85, and 145
seconds:

```python
assert prepared[0][0].item() == sample_rate * 25
assert prepared[0][-1].item() == sample_rate * 55 - 1
assert prepared[1][0].item() == sample_rate * 85
assert prepared[1][-1].item() == sample_rate * 115 - 1
assert prepared[2][0].item() == sample_rate * 145
assert prepared[2][-1].item() == sample_rate * 175 - 1
```

- [ ] **Step 2: Add short-track and per-track-context preparation tests**

Add a short-track padding test:

```python
def test_maest_short_track_remains_right_zero_padded() -> None:
    sample_rate = 16_000
    audio = np.ones(sample_rate * 10, dtype=np.float32)
    adapter = BatchMaestAdapter()
    adapter._load_model()

    prepared = adapter._prepare_audio_windows_from_audio(
        "short.wav",
        audio,
        sample_rate,
    )

    assert len(prepared) == 1
    assert prepared[0].numel() == sample_rate * 30
    assert torch.all(prepared[0][: sample_rate * 10] == 1.0)
    assert torch.all(prepared[0][sample_rate * 10 :] == 0.0)
```

Extend `BatchMaestModel` with:

```python
self.first_samples: list[float] = []
```

and at the start of `__call__()`:

```python
self.first_samples.extend(float(row[0].item()) for row in audio)
```

Then add:

```python
def test_maest_decoded_batch_applies_context_per_track() -> None:
    sample_rate = 16_000
    base = np.arange(sample_rate * 200, dtype=np.float32)
    adapter = BatchMaestAdapter()
    structured = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )
    decoded = [
        DecodedAudio(
            path="structured.wav",
            audio=base,
            sample_rate=sample_rate,
            detail="test",
        ),
        DecodedAudio(
            path="fallback.wav",
            audio=base + 10_000_000.0,
            sample_rate=sample_rate,
            detail="test",
        ),
    ]

    adapter.predict_decoded_batch(
        decoded,
        window_contexts=[structured, None],
    )

    assert adapter.fake_model.first_samples == [
        float(sample_rate * 51),
        float(sample_rate * 90),
        float(sample_rate * 129),
        float(10_000_000 + sample_rate * 25),
        float(10_000_000 + sample_rate * 85),
        float(10_000_000 + sample_rate * 145),
    ]
```

- [ ] **Step 3: Write the failing runner propagation test**

Extend `_FakeMaestAdapter` in `tests/test_analysis_orchestration.py`:

```python
class _FakeMaestAdapter(MaestGenreAdapter):
    received_window_contexts: tuple[MaestWindowContext | None, ...]

    def __init__(self) -> None:
        super().__init__(
            device="cpu",
            top_k=3,
            inference_batch_size=2,
        )
        self._vectors = {}
        self.received_window_contexts = ()

    def predict_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        window_contexts: Sequence[MaestWindowContext | None] | None = None,
    ) -> list[list[dict[str, object]]]:
        self.received_window_contexts = tuple(window_contexts or ())
        for item in decoded_items:
            vector = np.zeros(768, dtype=np.float32)
            vector[:2] = (3.0, 4.0)
            self._vectors[item.path] = vector
        return [
            [{"label": "Breaks", "score": 0.9}]
            for _item in decoded_items
        ]
```

Import `MaestWindowContext`, construct the candidate with a context, and assert
after `runner.analyze_batch(...)`:

```python
context = MaestWindowContext(
    leading_silence_seconds=5.0,
    trailing_silence_seconds=10.0,
    intro_end_seconds=40.0,
    outro_start_seconds=170.0,
)
adapter = _FakeMaestAdapter()
runner = MaestModelRunner(
    device="cpu",
    top_k=3,
    inference_batch_size=2,
    adapter=adapter,
)
base_candidate = _candidate(1, (runner.candidate_outputs[1],))
candidate = AnalysisCandidate(
    target=base_candidate.target,
    file_path=base_candidate.file_path,
    file_size_bytes=base_candidate.file_size_bytes,
    file_modified_ns=base_candidate.file_modified_ns,
    missing_outputs=(runner.candidate_outputs[1],),
    maest_window_context=context,
)
```

```python
assert adapter.received_window_contexts == (context,)
```

- [ ] **Step 4: Write the failing runtime-metadata assertion**

In `tests/test_model_adapter_identity.py`, assert:

```python
def test_maest_runtime_parameters_describe_structure_aware_windows() -> None:
    parameters = MaestGenreAdapter(device="cpu").runtime_parameters()

    assert parameters["analysis_window_positions"] == (0.2, 0.5, 0.8)
    assert (
        parameters["window_selection"]
        == "structure-aware-main-range-centered-20-50-80"
    )
    assert parameters["window_context"] == "sonara-current-generation-optional"
    assert (
        parameters["window_fallback"]
        == "main-range->non-silent-range->full-duration"
    )
    assert parameters["window_dedup_tolerance_seconds"] == 1.0
    assert "analysis_offset_seconds" not in parameters
    assert "analysis_window_ratios" not in parameters
```

- [ ] **Step 5: Run the new adapter, runner, and metadata tests**

Run:

```powershell
python -m pytest tests\test_genres.py tests\test_analysis_orchestration.py tests\test_model_adapter_identity.py -k "maest" --override-ini addopts=
```

Expected: failures show missing context parameters and legacy runtime metadata.

- [ ] **Step 6: Integrate the pure selector in `MaestGenreAdapter`**

Import:

```python
from collections.abc import Sequence

from .maest_windows import (
    MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS,
    MAEST_WINDOW_POSITIONS,
    MaestWindowContext,
    select_maest_window_starts,
)
```

Replace adapter class constants:

```python
analysis_window_positions = MAEST_WINDOW_POSITIONS
```

Update `runtime_parameters()` to return:

```python
"analysis_window_positions": self.analysis_window_positions,
"window_selection": "structure-aware-main-range-centered-20-50-80",
"window_context": "sonara-current-generation-optional",
"window_fallback": "main-range->non-silent-range->full-duration",
"window_dedup_tolerance_seconds": (
    MAEST_WINDOW_DEDUP_TOLERANCE_SECONDS
),
```

Remove the legacy `analysis_offset_seconds`,
`analysis_window_ratios`, and old `window_selection` entries.

Update the decoded API:

```python
def predict_decoded_batch(
    self,
    decoded_items: list[DecodedAudio],
    *,
    window_contexts: Sequence[MaestWindowContext | None] | None = None,
) -> list[list[dict[str, float | str]]]:
    self._load_model()
    contexts = (
        [None] * len(decoded_items)
        if window_contexts is None
        else list(window_contexts)
    )
    if len(contexts) != len(decoded_items):
        raise ValueError("MAEST window context count does not match track count")
    prepared = []
    window_track_indexes: list[int] = []
    prepare_started = time.perf_counter()
    for track_index, (decoded, context) in enumerate(
        zip(decoded_items, contexts)
    ):
        windows = self._prepare_audio_windows_from_audio(
            decoded.path,
            decoded.audio,
            decoded.sample_rate,
            window_context=context,
        )
        prepared.extend(windows)
        window_track_indexes.extend([track_index] * len(windows))
    prepare_seconds = time.perf_counter() - prepare_started
    return self._predict_prepared_batch(
        [str(decoded.path) for decoded in decoded_items],
        prepared,
        window_track_indexes,
        0.0,
        prepare_seconds,
    )
```

Add the optional keyword to preparation:

```python
def _prepare_audio_windows_from_audio(
    self,
    path: str | Path,
    audio_values: np.ndarray,
    sample_rate: int,
    *,
    window_context: MaestWindowContext | None = None,
):
```

Replace the legacy `_analysis_window_starts(...)` call:

```python
starts = select_maest_window_starts(
    audio.numel() / self.target_rate,
    self.input_seconds,
    window_context,
)
```

Remove the private `_analysis_window_starts` function from `genres.py`.
`predict_batch(paths)` continues to pass no contexts and therefore selects
centered full-duration windows when the adapter is invoked directly. Project
ML jobs filter candidates through current-generation SONARA first.

- [ ] **Step 7: Pass contexts through `MaestModelRunner`**

In `MaestModelRunner.analyze_batch()`:

```python
decoded_items = _decoded_items(items)
genres_by_track = self.adapter.predict_decoded_batch(
    decoded_items,
    window_contexts=[
        item.candidate.maest_window_context for item in items
    ],
)
```

Do not change conversion to `MaestGenreScore`, atomic repository writes,
syncopated-rhythm derivation, or embedding normalization.

- [ ] **Step 8: Replace legacy canonical MAEST runtime metadata**

In `src/dj_track_similarity/analysis_models.py`, change both MAEST entries in
`_ML_CANONICAL_RUNTIME_PARAMETERS` to use:

```python
"sample_rate_hz": 16_000,
"input_seconds": 30.0,
"analysis_window_positions": (0.2, 0.5, 0.8),
"channel_downmix": "arithmetic-mean",
"decoder": "shared-load-audio-mono-v1",
"resampler": "torchaudio",
"window_selection": "structure-aware-main-range-centered-20-50-80",
"window_context": "sonara-current-generation-optional",
"window_fallback": "main-range->non-silent-range->full-duration",
"window_dedup_tolerance_seconds": 1.0,
"short_audio": "right-zero-pad-to-30s",
"model_input": "raw-waveform-melspectrogram-input-false",
"score_activation": "sigmoid-logits",
"score_pooling": "window-mean-then-top-k",
```

Keep the embedding-only `pooling` entry.

Update `maest_analysis_output()`, `maest_embedding_output()`, and their callers
to accept `analysis_window_positions` instead of
`analysis_offset_seconds` plus `analysis_window_ratios`.

In `MaestModelRunner.__init__()`, reserve:

```python
(
    "sample_rate_hz",
    "input_seconds",
    "analysis_window_positions",
    "top_k",
    "pooling",
)
```

Pass the new value to both output factories:

```python
analysis_window_positions=cast(
    Sequence[float],
    facts["analysis_window_positions"],
),
```

Make the same reserved-key and factory-call replacement in the MAEST branch of
`embedding_analysis_output()`.

In `analysis_models.py`, give `maest_analysis_output()` this window argument:

```python
analysis_window_positions: Sequence[float],
```

Validate and merge it as:

```python
positions = _validate_window_ratios(
    analysis_window_positions,
    "analysis_window_positions",
)
reserved: dict[str, object] = {
    "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
    "input_seconds": _positive_number(input_seconds, "input_seconds"),
    "analysis_window_positions": positions,
    "top_k": _positive_int(top_k, "top_k"),
}
```

Give `maest_embedding_output()` the same window argument and reserved entry,
plus its existing `pooling` entry. The existing `_validate_window_ratios()`
implementation is suitable for the renamed positions because it requires
finite values strictly between zero and one.

Finally, replace `analysis_offset_seconds` and `analysis_window_ratios` with
`analysis_window_positions` in both MAEST entries of
`_REQUIRED_PARAMETER_KEYS`. The output factories still return only
family/output identity; the canonical parameter map remains the source of
runtime identity.

- [ ] **Step 9: Run focused MAEST tests**

Run:

```powershell
python -m pytest tests\test_maest_windows.py tests\test_genres.py tests\test_analysis_orchestration.py tests\test_model_adapter_identity.py --override-ini addopts=
```

Expected: all focused MAEST tests pass.

- [ ] **Step 10: Run adjacent multi-model analysis tests**

Run:

```powershell
python -m pytest tests\test_multi_model_analysis_jobs.py tests\test_analysis_repository.py --override-ini addopts=
```

Expected: all tests pass; MERT, MuQ, and CLAP behavior remains unchanged.

- [ ] **Step 11: Commit MAEST integration**

Run:

```powershell
git add -- src/dj_track_similarity/genres.py src/dj_track_similarity/analysis_model_runners.py src/dj_track_similarity/analysis_models.py tests/test_genres.py tests/test_analysis_orchestration.py tests/test_model_adapter_identity.py
git diff --cached --check
git commit -m "feat: use SONARA boundaries for MAEST windows"
```

Expected: one commit containing only adapter, runner, runtime metadata, and
their tests.

---

### Task 4: Document the active MAEST sampling policy

**Files:**

- Modify: `docs/dj-track-similarity/reference/analysis-families.md`
- Modify: `docs/dj-track-similarity/ru/reference/analysis-families.md`

**Interfaces:**

- Consumes: the final behavior from Tasks 1-3
- Produces: maintained English and Russian user-facing descriptions

- [ ] **Step 1: Update the English analysis-family reference**

Add this MAEST behavior to
`docs/dj-track-similarity/reference/analysis-families.md` near the MAEST
description:

```markdown
MAEST analyzes up to three 30-second windows centered at 20%, 50%, and 80% of
the best available content range. Current SONARA leading and trailing silence
form hard boundaries and intro/outro form preferred soft boundaries. A range
shorter than 30 seconds falls back first to the non-silent range and then to
the full track. Project ML jobs process only tracks with current SONARA; when
its structure values are unusable, MAEST centers windows over the full track.
Window scores are averaged before top-K genres are selected.
```

- [ ] **Step 2: Update the Russian mirror**

Add the corresponding text near the MAEST description in
`docs/dj-track-similarity/ru/reference/analysis-families.md`:

```markdown
MAEST анализирует до трёх 30-секундных окон с центрами в 20%, 50% и 80%
лучшего доступного диапазона содержимого. В актуальном результате SONARA
начальная и конечная тишина задают жёсткие границы, а конец интро и начало
аутро — предпочтительные мягкие границы. Диапазон короче 30 секунд сначала
ослабляется до участка без краевой тишины, а затем до полного трека. Проектные
ML-задачи обрабатывают только треки с актуальным SONARA; если его структурные
поля непригодны, MAEST выбирает центры по полной длительности. Оценки окон
усредняются до выбора жанров top-K.
```

- [ ] **Step 3: Verify the documentation**

Run from `docs/dj-track-similarity`:

```powershell
npm run check
```

Expected: Vale and the VitePress build pass.

- [ ] **Step 4: Commit documentation**

Run from the repository root:

```powershell
git add -- docs/dj-track-similarity/reference/analysis-families.md docs/dj-track-similarity/ru/reference/analysis-families.md
git diff --cached --check
git commit -m "docs: explain MAEST window selection"
```

Expected: one documentation-only commit.

---

### Task 5: Final focused verification

**Files:**

- Verify only; no planned source changes

**Interfaces:**

- Consumes: all earlier tasks
- Produces: fresh evidence that the implementation and adjacent analysis paths pass

- [ ] **Step 1: Run the complete touched backend scope**

Run:

```powershell
python -m pytest tests\test_maest_windows.py tests\test_genres.py tests\test_analysis_orchestration.py tests\test_model_adapter_identity.py tests\test_analysis_repository.py tests\test_scanner_database.py tests\test_multi_model_analysis_jobs.py --override-ini addopts=
```

Expected: all tests pass.

- [ ] **Step 2: Verify formatting and the scoped diff**

Run:

```powershell
git diff --check HEAD~4..HEAD
git status --short
```

Expected: no whitespace errors. Only pre-existing unrelated worktree changes
remain unstaged.

- [ ] **Step 3: Review behavior sentinels**

Run:

```powershell
rg -n "offset60s|0\.38|0\.72|analysis_offset_seconds|analysis_window_ratios" src/dj_track_similarity tests
rg -n "structure-aware-main-range-centered-20-50-80|main-range->non-silent-range->full-duration" src/dj_track_similarity tests
```

Expected: no active MAEST policy retains the legacy window terms; the new
policy appears in adapter metadata, canonical parameters, and tests. Matches
for unrelated models or historical docs are reviewed but not changed.

- [ ] **Step 4: Inspect the final commits**

Run:

```powershell
git log -5 --oneline
git show --stat --oneline HEAD
```

Expected: selector, candidate context, MAEST integration, and documentation are
separate intentional commits, with the earlier design commit preserved.
