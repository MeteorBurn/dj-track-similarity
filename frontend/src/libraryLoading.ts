import type { Track } from "./api";

export const libraryPageSize = 500;

export type LibraryRequestKeyParts = {
  databaseKey: string;
  query: string;
  searchMode: "like" | "fts";
  preset: string;
  liked: boolean;
  classifierMinScores: Record<string, number>;
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
    Math.max(0, Math.trunc(parts.offset))
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
