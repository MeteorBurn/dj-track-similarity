# Shared FFmpeg Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the application startup and browser preview dependency on FFmpeg executables with the installed shared FFmpeg runtime.

**Architecture:** A focused runtime module finds and registers a shared-library directory before TorchCodec is imported. The preview path uses TorchCodec's direct `AudioDecoder` and `AudioEncoder`; recovery decoding remains untouched until its tolerant semantics have a tested direct replacement.

**Tech Stack:** Python 3.10, TorchCodec 0.16, FFmpeg shared libraries 8 or 9, pytest, FastAPI.

## Global Constraints

- FFmpeg DLLs stay outside the repository.
- Application code must not invoke `ffmpeg.exe` or `ffprobe.exe` for startup or browser preview.
- Windows runtime discovery must not modify machine or parent-process `PATH`.
- Tests use temporary fixtures only; never project music or databases.

---

### Task 1: Shared-runtime discovery and registration

**Files:**
- Create: `src/dj_track_similarity/ffmpeg_runtime.py`
- Modify: `src/dj_track_similarity/dependencies.py`
- Modify: `tests/test_dependencies.py`

**Interfaces:**
- Produces `configure_shared_ffmpeg_runtime() -> Path`.
- Produces `shared_ffmpeg_runtime_configured() -> bool`.
- Consumes optional `DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR` and Windows `PATH` entries.

- [ ] **Step 1: Write failing runtime-discovery tests**

```python
def test_configure_shared_ffmpeg_runtime_registers_explicit_dll_directory(monkeypatch, tmp_path):
    (tmp_path / "avcodec-63.dll").touch()
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_FFMPEG_SHARED_DIR", str(tmp_path))
    registered = []
    monkeypatch.setattr(os, "add_dll_directory", lambda path: registered.append(path))
    assert configure_shared_ffmpeg_runtime() == tmp_path
    assert registered == [str(tmp_path)]
```

- [ ] **Step 2: Run the focused test and verify it fails because the module is absent**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_dependencies.py -q`

- [ ] **Step 3: Implement the minimal runtime module and replace executable lookup**

```python
def configure_shared_ffmpeg_runtime() -> Path:
    directory = _configured_or_path_shared_directory()
    if os.name == "nt":
        os.add_dll_directory(str(directory))
    return directory
```

- [ ] **Step 4: Add error coverage for a missing directory and a directory without `avcodec` shared libraries**

- [ ] **Step 5: Run `tests/test_dependencies.py` and commit the scoped change**

### Task 2: API and CLI bootstrap

**Files:**
- Modify: `src/dj_track_similarity/api.py`
- Modify: `src/dj_track_similarity/cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes `configure_shared_ffmpeg_runtime()` before adapters, analysis, or preview routes import TorchCodec.
- Produces a startup error that names the missing shared runtime rather than `ffmpeg.exe`.

- [ ] **Step 1: Write failing API/CLI tests that patch `configure_shared_ffmpeg_runtime()`**

```python
monkeypatch.setattr(cli, "configure_shared_ffmpeg_runtime", lambda: Path("C:/ffmpeg/bin"))
```

- [ ] **Step 2: Run the focused CLI tests and verify their current `require_ffmpeg` expectation fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_cli.py -q`

- [ ] **Step 3: Replace `require_ffmpeg()` startup calls with shared-runtime configuration and log the selected directory**

- [ ] **Step 4: Run `tests/test_cli.py` and `tests/test_dependencies.py`**

- [ ] **Step 5: Commit the scoped change**

### Task 3: Direct TorchCodec browser preview

**Files:**
- Modify: `src/dj_track_similarity/media_preview.py`
- Modify: applicable preview-route tests
- Create or modify: `tests/test_media_preview.py`

**Interfaces:**
- Consumes `AudioDecoder(path).get_all_samples()` and `AudioEncoder(samples, sample_rate=rate).to_file(temp_path)`.
- Produces the existing temporary WAV `FileResponse` and cleanup callback.

- [ ] **Step 1: Write a failing AIFF-to-WAV preview test**

```python
def test_transcoded_wav_file_response_uses_torchcodec_without_subprocess(tmp_path, monkeypatch):
    monkeypatch.setattr(media_preview.subprocess, "run", fail_if_called)
    response = transcoded_wav_file_response(source_aiff)
    assert response.path.endswith(".wav")
```

- [ ] **Step 2: Run the focused preview test and verify it fails because the function requires an executable path**

- [ ] **Step 3: Replace CLI invocation with direct TorchCodec decode and `AudioEncoder.to_file()`**

- [ ] **Step 4: Add a real temporary round-trip test that checks channels, sample rate, finite float32 output, and cleanup**

- [ ] **Step 5: Run preview tests plus `tests/test_cli.py` and commit the scoped change**

### Task 4: Format compatibility gate

**Files:**
- Modify: `src/dj_track_similarity/media_preview.py` only if the external shared build cannot decode an existing preview suffix
- Test: `tests/test_media_preview.py`

**Interfaces:**
- Consumes the existing `BROWSER_PREVIEW_TRANSCODE_SUFFIXES`.
- Produces either unchanged coverage or a precise startup/preview error naming an unsupported external runtime codec.

- [ ] **Step 1: Create temporary files in every existing preview suffix supported by the selected shared build**

- [ ] **Step 2: Verify each file decodes and encodes through TorchCodec without executable invocation**

- [ ] **Step 3: If a current suffix is unsupported, extend the external FFmpeg shared build before changing application behavior**

- [ ] **Step 4: Run the full preview test file and commit only after all existing supported suffixes retain preview behavior**

### Task 5: Direct recovery feasibility gate

**Files:**
- Test: `tests/test_audio_loader.py`
- Test: `tests/test_sonara_features.py`
- No production-code change unless the tests establish parity.

**Interfaces:**
- Compares current tolerant CLI recovery with a candidate direct shared-library decoder on corrupted-input and stereo downmix fixtures.
- Produces an explicit go/no-go decision for replacing `load_audio_mono_with_ffmpeg()`.

- [ ] **Step 1: Add fixtures that exercise tolerated decode errors and arithmetic mono downmix**

- [ ] **Step 2: Run the current recovery tests to record baseline behavior**

- [ ] **Step 3: Run the same fixtures through direct TorchCodec decoding**

- [ ] **Step 4: Replace recovery only if direct output and recovery behavior meet the documented assertions; otherwise retain the existing recovery code and report the direct-API gap**

### Task 6: Documentation after implemented behavior

**Files:**
- Modify only when requested: `README.md` and `docs/dj-track-similarity/`

- [ ] **Step 1: Document that shared FFmpeg libraries are required, one `ffmpeg.exe` is insufficient, and DLLs remain external to the repository**

- [ ] **Step 2: Run instruction/docs-only verification and commit documentation separately**
