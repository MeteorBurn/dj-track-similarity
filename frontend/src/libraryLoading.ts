import type { Track } from "./api";

export const libraryLoadSizes = [100, 500, 1000, "all"] as const;
export type LibraryLoadSize = (typeof libraryLoadSizes)[number];
export type PagedLibraryLoadSize = 100 | 500;

export type LibraryChunk = {
  offset: number;
  limit: number;
};

export type LibraryLoadProgress = {
  loaded: number;
  total: number;
  target: number;
  cancelled: boolean;
};

export type LibraryRequestKeyParts = {
  databaseKey: string;
  query: string;
  searchMode: "like" | "fts";
  preset: string;
  liked: boolean;
  classifierMinScores: Record<string, number>;
  loadSize: LibraryLoadSize;
  offset: number;
};

export type LibraryLoadTicket = {
  id: number;
  requestKey: string;
  signal: AbortSignal;
};

export type LibraryLoadCoordinator = {
  start: (requestKey: string) => LibraryLoadTicket;
  isCurrent: (ticket: LibraryLoadTicket) => boolean;
  complete: (ticket: LibraryLoadTicket) => boolean;
  cancel: () => boolean;
};

const maximumLibraryChunkSize = 500;

export function isPagedLibraryLoadSize(loadSize: LibraryLoadSize): loadSize is PagedLibraryLoadSize {
  return loadSize === 100 || loadSize === 500;
}

export function libraryPageSizeForLoadSize(loadSize: LibraryLoadSize) {
  return isPagedLibraryLoadSize(loadSize) ? loadSize : null;
}

export function libraryLoadTarget(total: number, loadSize: LibraryLoadSize, offset = 0) {
  const safeTotal = Math.max(0, Math.trunc(total));
  if (loadSize === "all") return safeTotal;
  if (isPagedLibraryLoadSize(loadSize)) {
    return Math.min(loadSize, Math.max(0, safeTotal - Math.max(0, Math.trunc(offset))));
  }
  return Math.min(loadSize, safeTotal);
}

export function libraryChunkPlan(total: number, loadSize: LibraryLoadSize, offset = 0): LibraryChunk[] {
  const safeTotal = Math.max(0, Math.trunc(total));
  if (safeTotal === 0) return [];

  if (isPagedLibraryLoadSize(loadSize)) {
    const safeOffset = Math.min(Math.max(0, Math.trunc(offset)), safeTotal);
    const remaining = safeTotal - safeOffset;
    return remaining > 0 ? [{ offset: safeOffset, limit: Math.min(loadSize, remaining) }] : [];
  }

  const target = libraryLoadTarget(safeTotal, loadSize);
  const chunks: LibraryChunk[] = [];
  for (let loaded = 0; loaded < target; loaded += maximumLibraryChunkSize) {
    chunks.push({
      offset: loaded,
      limit: Math.min(maximumLibraryChunkSize, target - loaded)
    });
  }
  return chunks;
}

export function firstLibraryChunk(loadSize: LibraryLoadSize, offset = 0): LibraryChunk {
  if (isPagedLibraryLoadSize(loadSize)) {
    return { offset: Math.max(0, Math.trunc(offset)), limit: loadSize };
  }
  return { offset: 0, limit: maximumLibraryChunkSize };
}

export function libraryTrackIdentityKey(track: Pick<Track, "catalog_uuid" | "track_uuid">) {
  return `${track.catalog_uuid}:${track.track_uuid}`;
}

export function libraryTracksBelongToCatalog(
  tracks: Array<Pick<Track, "catalog_uuid">>,
  catalogUuid: string
) {
  return tracks.every((track) => track.catalog_uuid === catalogUuid);
}

export function mergeLibraryTracks(current: Track[], incoming: Track[]) {
  const merged: Track[] = [];
  const indexes = new Map<string, number>();

  for (const track of [...current, ...incoming]) {
    const key = libraryTrackIdentityKey(track);
    const existingIndex = indexes.get(key);
    if (existingIndex == null) {
      indexes.set(key, merged.length);
      merged.push(track);
      continue;
    }
    if (track.content_generation >= merged[existingIndex].content_generation) {
      merged[existingIndex] = track;
    }
  }
  return merged;
}

export function libraryRequestKey(parts: LibraryRequestKeyParts) {
  const classifierMinScores = Object.entries(parts.classifierMinScores)
    .sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify([
    parts.databaseKey,
    parts.query,
    parts.searchMode,
    parts.preset,
    parts.liked,
    classifierMinScores,
    parts.loadSize,
    isPagedLibraryLoadSize(parts.loadSize) ? Math.max(0, Math.trunc(parts.offset)) : 0
  ]);
}

export function createLibraryLoadCoordinator(): LibraryLoadCoordinator {
  let nextId = 0;
  let active: { ticket: LibraryLoadTicket; controller: AbortController } | null = null;

  return {
    start(requestKey) {
      active?.controller.abort();
      const controller = new AbortController();
      const ticket = {
        id: ++nextId,
        requestKey,
        signal: controller.signal
      };
      active = { ticket, controller };
      return ticket;
    },
    isCurrent(ticket) {
      return active?.ticket.id === ticket.id
        && active.ticket.requestKey === ticket.requestKey
        && !ticket.signal.aborted;
    },
    complete(ticket) {
      if (active?.ticket.id !== ticket.id || active.ticket.requestKey !== ticket.requestKey) return false;
      active = null;
      return true;
    },
    cancel() {
      if (!active) return false;
      active.controller.abort();
      active = null;
      return true;
    }
  };
}
