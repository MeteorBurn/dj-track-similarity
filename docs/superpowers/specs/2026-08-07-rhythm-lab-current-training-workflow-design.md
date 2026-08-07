# Rhythm Lab Current Training Workflow Design

## Goal

Make the local Rhythm Lab workflow use the active project database and its
current SONARA, MERT, MAEST, CLAP, and MuQ outputs consistently from training
through calibration, candidate refresh, and promotion.

## Approved behavior

- Keep `combined` as the compatibility alias for SONARA + MERT + MAEST.
- Add and prefer the explicit modern recipe
  `sonara2vocal+mert+maest+clap+muq`; do not silently redefine `combined`.
- Permit an explicit retrain whenever every fitted label has enough total rows
  and the selected feature recipe is available. The per-profile "new labels"
  threshold remains a recommendation, not a hard block.
- Balance feature blocks after per-column standardization so a 1024-dimensional
  embedding does not receive more aggregate regularization influence merely
  because it has more columns. Store the effective block weights in artifacts
  and metrics.
- Evaluate on a held-out split and cross-validation, then fit the serialized
  production estimator on all usable labeled rows.
- Bind every new artifact to the active source `catalog_uuid`. The web workflow
  must not promote an artifact trained against another or unknown catalog.
- Prefer the newest artifact for a feature recipe. A calibration run creates a
  new calibrated artifact, which must immediately become visible to readiness,
  candidate refresh, and promotion.
- Candidate refresh accepts an explicit feature recipe and otherwise uses the
  current best promotable recipe instead of hard-coded `combined`.
- Web promotion requires calibrated probabilities by default. An API caller
  may explicitly opt into an uncalibrated experimental promotion.

## API flow

1. `GET .../training/readiness` reports total-label sufficiency, new-label
   recommendation, selected source readiness, artifact source binding, and
   calibration state.
2. `POST .../training/train-refresh` trains the selected recipe from all usable
   labels, fits the production estimator on all rows, stores source provenance,
   refreshes candidates with that exact artifact, and records the checkpoint.
3. `POST .../training/benchmark` compares the supported ablation recipes,
   including the modern full recipe, per profile.
4. `POST .../training/calibrate` retrains the selected recipe with calibration,
   returns the exact new artifact, and records it as the latest checkpoint.
5. `POST .../predictions/refresh` refreshes candidates with the explicitly
   selected recipe or the current best promotable recipe.
6. `POST .../promote` publishes the exact selected, source-compatible,
   calibrated artifact atomically.

## UI flow

The Training view exposes the modern recipe, keeps the compatibility recipes,
shows effective feature-block weights and calibration state, and provides
explicit actions for Train, Benchmark, Calibrate, Refresh candidates, Review,
and Promote. Buttons use readiness for the currently selected recipe or
promotion variant; they do not assume `combined`.

## Error handling and safety

- Missing source data, insufficient fitted labels, mismatched catalog binding,
  invalid artifacts, and unavailable calibration return actionable 4xx errors.
- Training and prediction write only the Lab database and local artifact tree.
- Promotion remains the only path in this workflow that writes a versioned
  classifier generation under `models/classifiers/`.
- The real project database, source audio, unrelated classifier scores, and
  existing user changes remain untouched during verification.

## Verification

- Observe failing tests for each current mismatch before production edits.
- Run focused Rhythm Lab unit and integration tests.
- Run the promoted-classifier consumer boundary test.
- Parse the static JavaScript and exercise the local UI in a browser without
  starting real training or promotion.
