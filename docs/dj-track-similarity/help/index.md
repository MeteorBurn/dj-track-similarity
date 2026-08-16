# Help

> Audience: Users diagnosing a local run.
> Goal: Route symptoms to fixes and explain current limits.
> Type: help index

Start with the symptom page, then check known limits and FAQ.

## Pages

- [Troubleshooting](./troubleshooting.md): common local errors and checks.
- [FAQ](./faq.md): short answers to repeated user questions.
- [Known limits](./known-limits.md): current boundaries that are not bugs.

## First checks

- Confirm the UI is connected to the SQLite database you expect.
- Confirm a directory containing shared FFmpeg libraries is on `PATH` or is set through
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR`; `ffmpeg.exe` alone is insufficient.
- Confirm the analysis family required by the feature has been run.
- Check the process log in the top bar for job errors.
