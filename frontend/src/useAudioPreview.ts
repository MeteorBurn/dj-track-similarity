import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { errorText, isAbortError } from "./errors";
import { emptyPreviewPosition, writePreviewPosition } from "./previewPosition";
import type { PreviewTarget } from "./useSearchPlaylist";

type Selection = {
  track: PreviewTarget;
  databaseKey: string | null;
  duration: number;
  controller: AbortController;
};

type Stream = {
  id: number;
  selection: Selection;
  start: number;
  elapsed: number;
  playing: boolean;
  ended: boolean;
  failed: boolean;
  audio: HTMLAudioElement | null;
};

function releaseAudio(audio: HTMLAudioElement | null) {
  if (!audio) return;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

export function useAudioPreview(options: {
  databaseKey: string | null;
  onEnded: (track: PreviewTarget) => void;
  onError: (message: string) => void;
}) {
  const latest = useRef(options);
  latest.current = options;
  const previewAudioRef = useRef<HTMLAudioElement | null>(null);
  const current = useRef<Stream | null>(null);
  const nextId = useRef(0);
  const [stream, setStream] = useState<Stream | null>(null);
  const [playingTrackId, setPlayingTrackId] = useState<number | null>(null);

  function isCurrent(value: Stream) {
    return current.current === value
      && value.selection.databaseKey === latest.current.databaseKey;
  }

  function updatePosition(value: Stream) {
    if (!isCurrent(value)) return;
    if (value.audio && Number.isFinite(value.audio.currentTime)) {
      value.elapsed = Math.max(0, value.audio.currentTime);
    }
    const position = value.start + value.elapsed;
    const duration = value.selection.duration;
    writePreviewPosition({
      trackId: value.selection.track.track_id,
      currentTime: duration > 0 ? Math.min(position, duration) : position,
      duration,
    });
  }

  function failPlayback(value: Stream, error: unknown) {
    if (!isCurrent(value) || value.failed) return;
    updatePosition(value);
    value.failed = true;
    value.playing = false;
    setPlayingTrackId(null);
    const audio = value.audio;
    value.audio = null;
    releaseAudio(audio);
    latest.current.onError(`Не удалось воспроизвести трек: ${errorText(error)}`);
  }

  function play(value: Stream) {
    if (!isCurrent(value) || !value.audio || !value.playing) return;
    void value.audio.play().catch((error: unknown) => {
      if (!isCurrent(value) || !value.playing || isAbortError(error)) return;
      failPlayback(value, error);
    });
  }

  function finish(value: Stream) {
    if (!isCurrent(value) || !value.playing || value.ended || value.failed) return;
    value.ended = true;
    value.playing = false;
    updatePosition(value);
    setPlayingTrackId(null);
    latest.current.onEnded(value.selection.track);
  }

  function startStream(selection: Selection, start: number, playing: boolean) {
    const previous = current.current;
    const value: Stream = {
      id: ++nextId.current, selection, start, elapsed: 0, playing,
      ended: false, failed: false, audio: null,
    };
    // Invalidate old callbacks before pause/load can queue further media events.
    current.current = value;
    releaseAudio(previous?.audio ?? null);
    setStream(value);
    setPlayingTrackId(playing ? selection.track.track_id : null);
    updatePosition(value);
    if (selection.duration > 0 && start >= selection.duration) {
      if (playing) finish(value);
      else value.ended = true;
    }
    return value;
  }

  function togglePreview(track: PreviewTarget) {
    const value = current.current;
    if (value && isCurrent(value) && value.selection.track.track_id === track.track_id) {
      if (value.playing) {
        value.playing = false;
        setPlayingTrackId(null);
        value.audio?.pause();
      } else if (value.ended || value.failed) {
        startStream(value.selection, value.ended ? 0 : value.start + value.elapsed, true);
      } else {
        value.playing = true;
        setPlayingTrackId(track.track_id);
        play(value);
      }
      return;
    }
    value?.selection.controller.abort();
    const selection: Selection = {
      track, databaseKey: latest.current.databaseKey, duration: 0,
      controller: new AbortController(),
    };
    startStream(selection, 0, true);
    // Metadata is independent of the stream: playback never waits for it.
    void api.previewInfo(track.track_id, { signal: selection.controller.signal }).then((info) => {
      const active = current.current;
      if (!active || !isCurrent(active) || active.selection !== selection) return;
      selection.duration = info.duration_seconds != null && Number.isFinite(info.duration_seconds)
        ? Math.max(0, info.duration_seconds) : 0;
      updatePosition(active);
    }).catch((error: unknown) => {
      const active = current.current;
      if (!active || !isCurrent(active) || active.selection !== selection || isAbortError(error)) return;
      latest.current.onError(`Не удалось определить длительность трека: ${errorText(error)}`);
    });
  }

  function seekPreview(track: PreviewTarget, seconds: number) {
    const value = current.current;
    if (!value || !isCurrent(value) || value.selection.track.track_id !== track.track_id
      || !Number.isFinite(seconds) || value.selection.duration <= 0) return;
    const start = Math.min(Math.max(0, seconds), value.selection.duration);
    startStream(value.selection, start, value.playing);
  }

  function stopPreview() {
    const value = current.current;
    current.current = null;
    value?.selection.controller.abort();
    releaseAudio(value?.audio ?? null);
    setStream(null);
    setPlayingTrackId(null);
    writePreviewPosition(emptyPreviewPosition);
  }

  useEffect(() => {
    stopPreview();
  }, [options.databaseKey]);

  useEffect(() => () => {
    const value = current.current;
    current.current = null;
    value?.selection.controller.abort();
    releaseAudio(value?.audio ?? null);
    writePreviewPosition(emptyPreviewPosition);
  }, []);

  const sourceUrl = stream && !(stream.selection.duration > 0 && stream.start >= stream.selection.duration)
    ? `/media/${stream.selection.track.track_id}?start=${stream.start}` : undefined;

  useEffect(() => {
    const audio = previewAudioRef.current;
    if (!stream || !sourceUrl || !audio || !isCurrent(stream)) return;
    stream.audio = audio;
    // Restore the source if React Strict Mode replayed this effect's cleanup.
    if (audio.getAttribute("src") !== sourceUrl) audio.src = sourceUrl;
    const position = () => updatePosition(stream);
    const events = {
      timeupdate: position,
      durationchange: position,
      play: () => { if (!isCurrent(stream) || !stream.playing) audio.pause(); },
      pause: () => {
        if (!isCurrent(stream) || !audio.paused || audio.ended || stream.failed) return;
        stream.playing = false;
        setPlayingTrackId(null);
      },
      ended: () => finish(stream),
      error: () => failPlayback(stream, audio.error?.message || "Не удалось прочитать аудиопоток"),
    };
    for (const [name, handler] of Object.entries(events)) audio.addEventListener(name, handler);
    play(stream);
    return () => {
      for (const [name, handler] of Object.entries(events)) audio.removeEventListener(name, handler);
      stream.audio = null;
      releaseAudio(audio);
    };
  }, [stream, sourceUrl]);

  return {
    preview: stream?.selection.track ?? null,
    playingTrackId,
    previewAudioRef,
    sourceKey: stream?.id,
    sourceUrl,
    togglePreview,
    seekPreview,
    stopPreview,
  };
}
