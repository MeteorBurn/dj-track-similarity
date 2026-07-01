# Rhythm Lab

> Audience: Power users training local classifiers.
> Goal: Run the separate labeling/training helper safely.
> Type: how-to

## Commands

The main app top bar launches Rhythm Lab in a separate window. Stop the lab from
inside that Rhythm Lab window with its power button; the main app keeps only the
launch shortcut.

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py train --profile <classifier-key> --source <library-db> --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile <classifier-key> --labels tools\rhythm-lab\data\rhythm_lab.sqlite
python tools\rhythm-lab\rhythm_lab_cli.py collection-save --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "Agent finds" --track-id 123 --track-ids .\ids.txt --replace
python tools\rhythm-lab\rhythm_lab_cli.py collection-list --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Review collections

Review collections are temporary track batches for manual labeling. Use them for
AI search results, saved playlist candidates, or other review sets that should
not mix into normal Library, Candidates, or Liked browsing.

Rhythm Lab shows them in the Collection tab. Choose a collection from the select
next to the tab, then label tracks with the same profile controls and filters as
the rest of the lab. Deleting a collection removes only that review list; labels
already written for the active profile remain in Rhythm Lab state, and source
audio is not touched.

Agents, scripts, or the main UI can add tracks through the collection API. The
CLI can create, append to, replace, and list collections with `collection-save`
and `collection-list`.

## Filtering

The library, liked, collection, and candidate views share the search, label, and
BPM filters. `BPM from` and `BPM to` use only stored SONARA BPM from the selected
source database. Leave either bound blank to make it open-ended; leave both
blank to skip BPM filtering.

## Calibration

Use `--calibrate` only when you intentionally want calibration and have enough labels. Use `promote --require-calibration` only when calibrated output is required.
