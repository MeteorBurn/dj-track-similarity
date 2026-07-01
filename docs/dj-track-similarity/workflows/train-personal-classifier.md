# Train a personal classifier

> Audience: Power users who want their own taste signals in the main app.
> Goal: Label in Rhythm Lab, train, promote, and score safely.
> Type: how-to

Personal classifiers are useful when your taste signal is hard to express as one prompt or feature slider, such as "live percussion feel" or "avoid festival vocals." Expect an iterative loop: label a clear idea, train, listen to mistakes, add better labels, then train again.

## Flow

- Launch Rhythm Lab from the main UI or CLI.
- Pick a binary or multiclass profile.
- Use Library, Candidates, Liked, or Collection to choose the review surface.
- Add enough labels for the active profile.
- Train; calibration is optional and data-gated.
- Promote to `models/classifiers/<artifact-prefix>/`.
- Score that classifier in the main app CLASS tab.

## Pick the profile type

- Use a binary profile when you want one positive idea and one negative counterexample. This is the easiest starting point for a yes/no taste signal.
- Use a multiclass profile when tracks should belong to one of several user-defined classes. One track can hold only one current class label for the active multiclass profile.

## What each stage means

- Collections are review-only track lists for AI finds, saved playlist candidates, or other batches. They help focus labeling without changing source audio or mixing those tracks into liked state.
- Labeling creates training examples in Rhythm Lab state under `tools/rhythm-lab/data/`; it does not edit source audio.
- Training reads existing SONARA, MERT, and MAEST inputs, then writes classifier artifacts under `tools/rhythm-lab/artifacts/<artifact-prefix>/`. Calibration is optional and only applies when the label set is large enough.
- Promotion copies the selected trained model into `models/classifiers/<artifact-prefix>/` so the main app can discover it.
- Scoring writes that promoted model's probabilities to `track_classifier_scores` in SQLite. Scores are scoped by `classifier_key`, so scoring one promoted classifier should not erase scores for another.

Beginner expectation: the first model is usually a rough filter, not a final taste engine. Use the CLASS tab results as listening suggestions and improve the labels when obvious false positives or false negatives appear.

## Safety

Rhythm Lab does not write source audio. Promoted scoring writes only `track_classifier_scores` in SQLite.
