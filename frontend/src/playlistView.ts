import type { Track } from "./api";

export function playlistPage(playlist: Track[], offset: number, pageSize: number) {
  const limit = Math.max(1, pageSize);
  const total = playlist.length;
  const maxOffset = Math.max(0, Math.floor(Math.max(0, total - 1) / limit) * limit);
  const boundedOffset = Math.min(Math.max(0, offset), maxOffset);
  const items = playlist.slice(boundedOffset, boundedOffset + limit);
  return {
    items,
    total,
    offset: boundedOffset,
    pageStart: total && items.length ? boundedOffset + 1 : 0,
    pageEnd: Math.min(boundedOffset + items.length, total),
    canGoBack: boundedOffset > 0,
    canGoForward: boundedOffset + items.length < total
  };
}
