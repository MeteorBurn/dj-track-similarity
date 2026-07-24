export const libraryWindowSize = 120;

export type LibraryWindowBounds = {
  start: number;
  end: number;
  hasPrevious: boolean;
  hasNext: boolean;
};

export function libraryWindowBounds(
  total: number,
  requestedStart: number,
  windowSize = libraryWindowSize
): LibraryWindowBounds {
  const safeTotal = Math.max(0, Math.trunc(total));
  const safeWindowSize = Math.max(1, Math.trunc(windowSize));
  if (safeTotal === 0) {
    return { start: 0, end: 0, hasPrevious: false, hasNext: false };
  }
  const lastWindowStart = Math.floor((safeTotal - 1) / safeWindowSize) * safeWindowSize;
  const alignedStart = Math.floor(Math.max(0, Math.trunc(requestedStart)) / safeWindowSize) * safeWindowSize;
  const start = Math.min(alignedStart, lastWindowStart);
  const end = Math.min(safeTotal, start + safeWindowSize);
  return {
    start,
    end,
    hasPrevious: start > 0,
    hasNext: end < safeTotal
  };
}

export function shiftLibraryWindow(
  total: number,
  currentStart: number,
  direction: -1 | 1,
  windowSize = libraryWindowSize
) {
  return libraryWindowBounds(total, currentStart + direction * Math.max(1, Math.trunc(windowSize)), windowSize);
}

export function visibleLibraryWindow<T>(
  items: T[],
  requestedStart: number,
  windowSize = libraryWindowSize
) {
  const bounds = libraryWindowBounds(items.length, requestedStart, windowSize);
  return {
    ...bounds,
    items: items.slice(bounds.start, bounds.end)
  };
}
