# Rhythm Lab Current Training Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Rhythm Lab training, calibration, candidate refresh, promotion, and UI with the active project's current feature data.

**Architecture:** Keep feature-recipe policy in `features.py`, model fitting and artifact metadata in `training.py`, and web orchestration in `web_app.py`. The static UI consumes readiness and artifact summaries rather than duplicating backend policy beyond the explicit default recipe string.

**Tech Stack:** Python 3.10, FastAPI, SQLite, NumPy, scikit-learn, joblib, plain browser JavaScript.

## Global Constraints

- `combined` remains SONARA + MERT + MAEST.
- The source Core and Artifacts databases remain read-only for this workflow.
- Real audio, project databases, promoted models, and existing unrelated dirty files are protected during tests.
- Every behavior change follows a red-green cycle.

---

### Task 1: Current recipe and production estimator

**Files:**
- Modify: `tools/rhythm-lab/rhythm_lab/features.py`
- Modify: `tools/rhythm-lab/rhythm_lab/training.py`
- Modify: `tools/rhythm-lab/rhythm_lab/ablation.py`
- Test: `tools/rhythm-lab/tests/test_rhythm_lab.py`

**Interfaces:**
- Produces: `DEFAULT_TRAINING_FEATURE_SET`, modern full recipe availability,
  serialized `source_catalog_uuid`, `feature_group_weights`, and full-data
  production fitting.

- [ ] Write tests proving the selected default requires all five sources, block weights are recorded, and the serialized model is fitted on all rows.
- [ ] Run the focused tests and confirm meaningful failures.
- [ ] Add the explicit modern recipe to UI and ablation options.
- [ ] Add post-standardization source-block balancing and full-data refit.
- [ ] Bind artifacts and metrics to the source catalog and skipped-row count.
- [ ] Re-run the focused tests.

### Task 2: Readiness and artifact lifecycle API

**Files:**
- Modify: `tools/rhythm-lab/rhythm_lab/web_app.py`
- Modify: `tools/rhythm-lab/rhythm_lab/cli.py`
- Test: `tools/rhythm-lab/tests/test_rhythm_lab.py`
- Test: `tools/rhythm-lab/tests/test_consumers.py`

**Interfaces:**
- Consumes: source-bound training artifacts from Task 1.
- Produces: total-label readiness, selected artifact resolution, calibrated
  artifact visibility, explicit candidate refresh recipes, and calibrated web
  promotion.

- [ ] Write API tests for retraining without new-label deltas, selected-recipe candidate refresh, calibrated artifact selection, and catalog mismatch rejection.
- [ ] Run the focused tests and confirm meaningful failures.
- [ ] Separate trainability from the new-label recommendation.
- [ ] Resolve refresh, calibration, and promotion through one selected artifact path.
- [ ] Surface the newest calibrated run and require calibration for web promotion unless explicitly overridden.
- [ ] Re-run the focused API tests.

### Task 3: Training workflow UI

**Files:**
- Modify: `tools/rhythm-lab/rhythm_lab/static/app.js`
- Test: `tools/rhythm-lab/tests/test_consumers.py`

**Interfaces:**
- Consumes: readiness and artifact summary fields from Task 2.
- Produces: explicit Calibrate and Refresh candidates actions with selected
  recipe/variant payloads and accurate enablement.

- [ ] Add a failing UI contract test for the missing actions and selected feature-set payload.
- [ ] Confirm the test fails for the missing workflow.
- [ ] Add the modern default, calibration action, candidate refresh action, calibration/source status copy, and promotion gate.
- [ ] Run the UI contract test and `node --check` for the static script.

### Task 4: Integrated proof

**Files:**
- Verify only; no production edits expected.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: evidence for the end-to-end local workflow.

- [ ] Run `python -m pytest tools\\rhythm-lab\\tests\\test_rhythm_lab.py tools\\rhythm-lab\\tests\\test_consumers.py --override-ini addopts=`.
- [ ] Run `python -m pytest tests\\test_break_energy.py --override-ini addopts=`.
- [ ] Run Ruff on the touched Python paths.
- [ ] Run `node --check tools\\rhythm-lab\\rhythm_lab\\static\\app.js`.
- [ ] Start a bounded local Rhythm Lab smoke session against temporary data and inspect the Training UI actions.
- [ ] Inspect the final scoped diff and run `git diff --check`.
