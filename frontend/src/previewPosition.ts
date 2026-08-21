import { useSyncExternalStore } from "react";

export type PreviewPosition = {
  trackId: number | null;
  currentTime: number;
  duration: number;
};

export const emptyPreviewPosition: PreviewPosition = {
  trackId: null,
  currentTime: 0,
  duration: 0
};

/**
 * Playback position lives outside React state on purpose.
 *
 * The `timeupdate` event fires several times per second while a preview plays.
 * Holding the position in `App` state made every tick re-render the whole tree,
 * including every visible library, search and playlist row, even though the
 * only consumer is the seek control of the track being previewed. Keeping it in
 * a subscribable store lets that one control re-render on its own.
 */
let current: PreviewPosition = emptyPreviewPosition;
const listeners = new Set<() => void>();

export function readPreviewPosition(): PreviewPosition {
  return current;
}

export function writePreviewPosition(next: PreviewPosition) {
  if (
    next.trackId === current.trackId
    && next.currentTime === current.currentTime
    && next.duration === current.duration
  ) {
    return;
  }
  current = next;
  for (const listener of listeners) listener();
}

export function subscribePreviewPosition(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function usePreviewPosition(): PreviewPosition {
  return useSyncExternalStore(
    subscribePreviewPosition,
    readPreviewPosition,
    readPreviewPosition
  );
}

/** Resolve the position a single track's seek control should display. */
export function previewPositionForTrack(
  position: PreviewPosition,
  trackId: number
): { currentTime: number; duration: number } {
  if (position.trackId !== trackId) return { currentTime: 0, duration: 0 };
  return { currentTime: position.currentTime, duration: position.duration };
}
