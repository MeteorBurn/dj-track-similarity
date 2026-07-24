import { useEffect, useRef, useState } from "react";
import { ArrowDownUp, AudioWaveform, Heart, ListMusic, Plus, Search, X } from "lucide-react";
import type { Track } from "./api";
import {
  isPagedLibraryLoadSize,
  libraryLoadSizes,
  libraryPageSizeForLoadSize,
  type LibraryLoadProgress,
  type LibraryLoadSize
} from "./libraryLoading";
import {
  likedTracksFilterTitle,
  libraryCurrentPageNumber,
  libraryPageCount,
  librarySearchModeTitle,
  type LibraryPreset,
  type LibrarySearchMode,
  type LibrarySortDirection
} from "./libraryView";
import { TrackList } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

export function TrackPanel({
  databaseSelected,
  query,
  onQueryChange,
  searchMode,
  onSearchModeChange,
  libraryPreset,
  onToggleLibraryPreset,
  likedOnly,
  likedTrackCount,
  onToggleLikedOnly,
  librarySortDirection,
  onToggleLibrarySortDirection,
  loadSize,
  onLoadSizeChange,
  loadProgress,
  loadError,
  onCancelLoading,
  preview,
  playingTrackId,
  tracks,
  total,
  offset,
  loading,
  canGoBack,
  canGoForward,
  onPreviousPage,
  onNextPage,
  onPageJump,
  busy,
  seedSet,
  playlistSet,
  librarySearchHelp,
  onAddVisibleTracks,
  onSeed,
  onToggleLiked,
  onTogglePlaylist,
  onPreview,
  onPreviewPlaying,
  onPreviewPaused,
  onDetails
}: {
  databaseSelected: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  searchMode: LibrarySearchMode;
  onSearchModeChange: (mode: LibrarySearchMode) => void;
  libraryPreset: LibraryPreset;
  onToggleLibraryPreset: (preset: LibraryPreset) => void;
  likedOnly: boolean;
  likedTrackCount: number;
  onToggleLikedOnly: () => void;
  librarySortDirection: LibrarySortDirection;
  onToggleLibrarySortDirection: () => void;
  loadSize: LibraryLoadSize;
  onLoadSizeChange: (loadSize: LibraryLoadSize) => void;
  loadProgress: LibraryLoadProgress | null;
  loadError: string | null;
  onCancelLoading: () => void;
  preview: Track | null;
  playingTrackId: number | null;
  tracks: Track[];
  total: number;
  offset: number;
  loading: boolean;
  canGoBack: boolean;
  canGoForward: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onPageJump: (pageNumber: number) => void;
  busy: boolean;
  seedSet: Set<number>;
  playlistSet: Set<number>;
  librarySearchHelp: string;
  onAddVisibleTracks: () => void;
  onSeed: (track: Track) => void;
  onToggleLiked: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onPreviewPlaying: (trackId: number) => void;
  onPreviewPaused: (trackId: number) => void;
  onDetails: (track: Track) => void;
}) {
  const pageSize = libraryPageSizeForLoadSize(loadSize);
  const paged = isPagedLibraryLoadSize(loadSize);
  const pageCount = pageSize == null ? 0 : libraryPageCount(total, pageSize);
  const currentPage = pageSize == null
    ? 0
    : libraryCurrentPageNumber(total, offset, pageSize);
  const syncedPageInput = currentPage ? String(currentPage) : "";
  const [pageInput, setPageInput] = useState(syncedPageInput);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const addVisibleTitle = total === 0
    ? "Нет отфильтрованных треков для добавления"
    : "Добавить все отфильтрованные треки в сет. Уже добавленные треки будут пропущены.";
  const reverseSortActive = librarySortDirection === "reverse";
  const rangeStart = tracks.length ? offset + 1 : 0;
  const rangeEnd = paged ? Math.min(total, offset + tracks.length) : tracks.length;

  useEffect(() => {
    setPageInput(syncedPageInput);
  }, [syncedPageInput]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !preview) return;
    if (playingTrackId === preview.track_id) {
      void audio.play().catch(() => undefined);
    } else {
      audio.pause();
    }
  }, [preview, playingTrackId]);

  function submitPageInput() {
    const requestedPage = Number.parseInt(pageInput, 10);
    if (!Number.isFinite(requestedPage) || pageCount === 0) {
      setPageInput(syncedPageInput);
      return;
    }
    const clampedPage = Math.min(Math.max(requestedPage, 1), pageCount);
    setPageInput(String(clampedPage));
    if (clampedPage !== currentPage) onPageJump(clampedPage);
  }

  return (
    <section className="panel track-panel">
      <div className="panel-title">
        <ListMusic size={18} />
        <h2>2. Библиотека и прослушивание</h2>
      </div>
      <div className="search-input">
        <Search size={16} />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="artist, title, genre, path"
          title={librarySearchHelp}
          disabled={!databaseSelected}
        />
        <div className="library-search-mode-toggle" role="group" aria-label="Library search mode">
          <button
            className={`library-search-like-button ${searchMode === "like" ? "active" : ""}`}
            title={librarySearchModeTitle("like")}
            aria-label="LIKE search"
            aria-pressed={searchMode === "like"}
            disabled={!databaseSelected}
            onClick={() => onSearchModeChange("like")}
            type="button"
          >
            LIKE
          </button>
          <button
            className={`library-search-fts-button ${searchMode === "fts" ? "active" : ""}`}
            title={librarySearchModeTitle("fts")}
            aria-label="FTS search"
            aria-pressed={searchMode === "fts"}
            disabled={!databaseSelected}
            onClick={() => onSearchModeChange("fts")}
            type="button"
          >
            FTS
          </button>
        </div>
      </div>
      <div className="library-load-size-control" role="group" aria-label="Количество загружаемых треков">
        <span>Загрузить</span>
        {libraryLoadSizes.map((size) => (
          <button
            className={`library-load-size-button ${loadSize === size ? "active" : ""}`}
            key={size}
            type="button"
            title={`Загрузить ${size === "all" ? "все треки" : `${size} треков`}`}
            aria-pressed={loadSize === size}
            disabled={!databaseSelected}
            onClick={() => onLoadSizeChange(size)}
          >
            {size === "all" ? "Все" : size}
          </button>
        ))}
      </div>
      <div className="library-view-controls">
        <button
          className={`icon-button library-preset-button ${libraryPreset === "syncopated" ? "active" : ""}`}
          title="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-label="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-pressed={libraryPreset === "syncopated"}
          disabled={!databaseSelected}
          onClick={() => onToggleLibraryPreset("syncopated")}
          type="button"
        >
          <AudioWaveform size={16} />
        </button>
        <button
          className={`icon-button liked-filter-button ${likedOnly ? "active" : ""}`}
          title={likedTracksFilterTitle(likedOnly, likedTrackCount)}
          aria-label="Показать список лайкнутых треков"
          aria-pressed={likedOnly}
          disabled={busy || (!likedOnly && likedTrackCount === 0)}
          onClick={onToggleLikedOnly}
          type="button"
        >
          <Heart size={16} />
        </button>
        {paged ? (
          <>
            <button className="library-page-previous-button" title="Предыдущая страница библиотеки" disabled={!canGoBack} onClick={onPreviousPage} type="button">Prev</button>
            <button className="library-page-next-button" title="Следующая страница библиотеки" disabled={!canGoForward} onClick={onNextPage} type="button">Next</button>
            <input
              className="library-page-index-input"
              type="number"
              min={1}
              max={Math.max(1, pageCount)}
              value={pageInput}
              placeholder="0"
              title="Перейти к странице библиотеки. Введите номер страницы и нажмите Enter или уберите фокус."
              aria-label="Номер страницы библиотеки"
              disabled={loading || pageCount === 0}
              onBlur={submitPageInput}
              onChange={(event) => setPageInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  submitPageInput();
                }
              }}
            />
            <span className="library-page-number-status" title="Текущая страница / всего страниц">
              {loading ? "..." : `${currentPage} / ${pageCount}`}
            </span>
          </>
        ) : null}
        <span className="library-range-status" title="Диапазон загруженных треков">
          {loading && loadProgress
            ? `Загружено ${loadProgress.loaded} из ${loadProgress.total || "…"}`
            : loadProgress?.cancelled
              ? `Остановлено ${loadProgress.loaded} из ${loadProgress.total}`
              : `${rangeStart}–${rangeEnd} / ${total}`}
        </span>
        {loading ? (
          <button
            className="icon-button library-load-cancel-button"
            title="Отменить загрузку библиотеки"
            aria-label="Отменить загрузку библиотеки"
            onClick={onCancelLoading}
            type="button"
          >
            <X size={16} />
          </button>
        ) : null}
        <button
          className={`icon-button library-sort-direction-button ${reverseSortActive ? "active" : ""}`}
          title={reverseSortActive ? "Показать загруженные треки в прямом порядке" : "Показать загруженные треки в обратном порядке"}
          aria-label="Переключить порядок загруженных треков"
          aria-pressed={reverseSortActive}
          disabled={loading || tracks.length < 2}
          onClick={onToggleLibrarySortDirection}
          type="button"
        >
          <ArrowDownUp size={16} />
        </button>
        <button
          className="icon-button intent-add add-visible-tracks-button"
          title={addVisibleTitle}
          aria-label="Добавить все отфильтрованные треки в сет"
          disabled={busy || total === 0}
          onClick={onAddVisibleTracks}
          type="button"
        >
          <Plus size={16} />
        </button>
      </div>
      {loadError ? <small className="library-load-error" role="alert">{loadError}</small> : null}
      {!databaseSelected ? (
        <div className="library-empty-state">Выберите SQLite базу данных.</div>
      ) : !loading && tracks.length === 0 ? (
        <div className="library-empty-state">В текущем запросе треков нет.</div>
      ) : null}
      <div className="library-preview-player">
        <span>{preview ? displayTrack(preview) : "Preview"}</span>
        {preview && (
          <audio
            ref={audioRef}
            controls
            src={`/media/${preview.track_id}`}
            onPlay={() => {
              if (playingTrackId === preview.track_id) onPreviewPlaying(preview.track_id);
            }}
            onPause={() => onPreviewPaused(preview.track_id)}
            onEnded={() => onPreviewPaused(preview.track_id)}
          />
        )}
      </div>
      {tracks.length ? (
        <TrackList
          tracks={tracks}
          seedSet={seedSet}
          playlistSet={playlistSet}
          playingTrackId={playingTrackId}
          onSeed={onSeed}
          onToggleLiked={onToggleLiked}
          onTogglePlaylist={onTogglePlaylist}
          onPreview={onPreview}
          onDetails={onDetails}
        />
      ) : null}
    </section>
  );
}
