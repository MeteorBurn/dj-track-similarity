# Shared FFmpeg Runtime Design

## Goal

Run the application through shared FFmpeg libraries rather than `ffmpeg.exe` or
`ffprobe.exe`. TorchCodec supplies direct decoding, technical metadata, and WAV
preview encoding.

## Boundary

- A Windows shared runtime directory is discovered from an explicit
  `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` directory or from `PATH` entries that
  contain `avcodec-*.dll`.
- The runtime directory is registered with `os.add_dll_directory()` before the
  first TorchCodec import. FFmpeg 8 and 9 are accepted when TorchCodec loads a
  matching core library.
- Browser preview performs `AudioDecoder(source)` followed by
  `AudioEncoder(samples).to_file(temp_wav)`. It never starts an executable.
- Container and audio-stream technical metadata come from TorchCodec. Music
  tags remain Mutagen's responsibility.

## Recovery boundary

The existing ML and SONARA recovery path asks the CLI for tolerant decoding
with `ignore_err` and an explicit arithmetic mono mix. A plain `AudioDecoder`
retry is not equivalent. Do not remove that recovery code until a direct
shared-library implementation has passed corrupted-input and downmix parity
tests.

## Constraints

- Do not add FFmpeg binaries or DLLs to the repository.
- Do not mutate the machine `PATH`.
- Do not regress the current browser-preview extension set. A format absent
  from the selected shared build must be added to the external FFmpeg build
  before switching that format to direct preview.
- The global FFmpeg 8 CLI remains outside the application contract.
