# Help

Start with the symptom page, then check known limits and FAQ.

If a page tells you to press a control you cannot find on screen, its label is one of the Russian
ones. [UI language](./ui-language.md) has the mapping.

## Pages

- [UI language](./ui-language.md): the Russian on-screen strings and their English meanings.
- [Troubleshooting](./troubleshooting.md): common local errors and checks.
- [FAQ](./faq.md): short answers to repeated user questions.
- [Known limits](./known-limits.md): current boundaries that are working as intended.

## First checks

- Confirm the UI is connected to the SQLite database you expect.
- Run `dj-sim doctor` to check FFmpeg `8.1.1` and PyAV `17.1.0` in the active environment.
- Configure the complete shared FFmpeg runtime with
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` or `PATH`. `ffmpeg.exe` alone is insufficient.
- Confirm the analysis family required by the feature has been run.
- Check the process log in the top bar for job errors. The scroll icon opens it, and it turns red
  when any job or activity event failed.
