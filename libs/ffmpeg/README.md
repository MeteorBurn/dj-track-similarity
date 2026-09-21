# FFmpeg 8.1.1 — Windows 11 x64 audio shared SDK

Built from the signed FFmpeg 8.1.1 source release for DJ Track Similarity.
`bin/` contains exactly seven DLLs. There are no executable programs, video
encoders/decoders, capture devices, or network protocols. Containers such as
MP4 and Matroska remain available for their audio streams.

Audio includes MP3, AAC, FLAC, ALAC, WAV/PCM, AIFF, Opus, Vorbis, WavPack,
TTA, WMA/APE decoding and other native audio decoders. LAME, Opus, Vorbis,
Ogg and SoXR are statically linked into the FFmpeg DLLs. `loudnorm`, `ebur128`,
`aresample` with SoXR and the native audio filter set are included.

`swscale-9.dll` and the device-free `avdevice-62.dll` retain the API/ABI needed
by PyAV and TorchCodec. Their presence does not enable video codecs or devices.
Headers and both MSVC `.lib` and GNU `.dll.a` import libraries are in the SDK.

## Python integration

`python/av-17.1.0-1audio-cp310-cp310-win_amd64.whl` is a custom PyAV 17.1.0
wheel for CPython 3.10 x64, built against these DLLs. Unlike the stock PyAV
wheel, it does not bundle or rename FFmpeg DLLs. It has no console entry point.
Keep the DLL directory registered with `os.add_dll_directory()` before importing
PyAV or TorchCodec. DJ Track Similarity already provides this registration
through `configure_shared_ffmpeg_runtime()`. Discovery checks `libs/ffmpeg/bin/`
first, then the DLL directory in the optional `DJTS_FFMPEG` environment variable,
then PATH, skipping missing or invalid candidates.

The stock PyAV wheel uses its own renamed FFmpeg DLLs; changing PATH alone does
not switch that wheel to this build. The custom wheel is included for that reason.
TorchCodec does not need rebuilding. Tested with TorchCodec 0.16.0+cu130,
PyTorch 2.11.0+cu130 and Python 3.10.20 on Windows 11 build 26200.

The build was tested in a temporary environment reusing the project's installed
Torch/TorchCodec packages. The project installation and global PATH were not changed.
`verification.json` records the actual loaded DLL paths and runtime checks:
11 audio format round trips through both APIs, waveform comparison, seek,
48 kHz stereo to 16 kHz mono, SoXR/loudnorm/ebur128, Unicode paths, memory
inputs and corrupt input rejection. No FFmpeg subprocess was used.

## Build provenance

`build-info.json` contains versions, original URLs and SHA-256 hashes.
`build/` contains the build configuration and verification driver.
The companion `ffmpeg-8.1.1-audio-build-sources.zip` contains the exact source
archives and build scripts. Extract those archives into `work/` as named;
run the dependency script, FFmpeg script, then the PyAV script using the listed
toolchain. The PyAV script records this machine's paths and needs adjustment
if the tools or project interpreter are elsewhere. FFmpeg source is unmodified;
the PyAV console-entry-point metadata is removed for API-only installation.
One redundant `seek_func` type annotation in PyAV's `av/container/pyio.py` is
removed because Cython 3.3 rejects redeclarations; the variable's original type
and assignment are retained. The memory-input and seek checks exercise this path.
The `amovie` audio filter is enabled to supply the libavformat dependency also
needed by `ametadata` in this reduced configuration.

License texts are in `licenses/`. `SHA256SUMS.txt` covers every packaged file
except itself. This is a custom local build, not an official upstream binary.
