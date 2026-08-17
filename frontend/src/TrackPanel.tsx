import { useEffect, useState } from "react";
import { ArrowDownUp, AudioWaveform, Heart, ListMusic, Plus, Search, Shuffle } from "lucide-react";
import type { Track } from "./api";
import { libraryPageSize } from "./libraryLoading";
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
  libraryPlaybackShuffle,
  onToggleLibraryPlaybackShuffle,
  librarySortDirection,
  onToggleLibrarySortDirection,
  loadError,
  playingTrackId,
  previewTrackId,
  previewCurrentTime,
  previewDuration,
  tracks,
  libraryTotalTracks,
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
  onSeekPreview,
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
  libraryPlaybackShuffle: boolean;
  onToggleLibraryPlaybackShuffle: () => void;
  librarySortDirection: LibrarySortDirection;
  onToggleLibrarySortDirection: () => void;
  loadError: string | null;
  playingTrackId: number | null;
  previewTrackId: number | null;
  previewCurrentTime: number;
  previewDuration: number;
  tracks: Track[];
  libraryTotalTracks: number;
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
  onSeekPreview: (track: Track, seconds: number) => void;
  onDetails: (track: Track) => void;
}) {
  const pageCount = libraryPageCount(total, libraryPageSize);
  const currentPage = libraryCurrentPageNumber(total, offset, libraryPageSize);
  const syncedPageInput = currentPage ? String(currentPage) : "";
  const [pageInput, setPageInput] = useState(syncedPageInput);
  const addVisibleTitle = total === 0
    ? "Нет треков текущей страницы для добавления"
    : "Добавить треки текущей страницы в сет. Уже добавленные треки будут пропущены.";
  const reverseSortActive = librarySortDirection === "reverse";
  const rangeStart = tracks.length ? offset + 1 : 0;
  const rangeEnd = tracks.length ? Math.min(total, offset + tracks.length) : 0;

  useEffect(() => {
    setPageInput(syncedPageInput);
  }, [syncedPageInput]);

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
        <span
          className="library-summary-badge library-summary-total-badge"
          title="Общее количество треков в библиотеке"
          aria-label={`Общее количество треков в библиотеке: ${libraryTotalTracks}`}
        >
          <span>tracks</span>
          <strong>{libraryTotalTracks}</strong>
        </span>
      </div>
      <div className="search-input">
        <Search size={16} />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="path, title, artist, genre"
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
      <div className="library-view-controls">
        <div className="library-pagination-controls" role="group" aria-label="Пагинация библиотеки">
          <button className="library-page-previous-button" title="Предыдущая страница библиотеки" disabled={!canGoBack} onClick={onPreviousPage} type="button">Prev</button>
          <button className="library-page-next-button" title="Следующая страница библиотеки" disabled={!canGoForward} onClick={onNextPage} type="button">Next</button>
          <input
            className="library-page-index-input"
            type="number"
            min={1}
            max={Math.max(1, pageCount)}
            value={pageInput}
            placeholder="0"
            title={`Перейти к странице библиотеки от 1 до ${Math.max(1, pageCount)}. Введите номер и нажмите Enter или уберите фокус.`}
            aria-label={`Номер страницы библиотеки, всего страниц: ${pageCount}`}
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
          <span
            className="library-page-number-status"
            title="Текущая страница / всего страниц"
            aria-live="polite"
          >
            {loading ? "..." : `${currentPage} / ${pageCount}`}
          </span>
          <span
            className="library-range-status"
            title="Диапазон треков на текущей странице"
            aria-live="polite"
          >
            {loading ? "..." : `${rangeStart}–${rangeEnd}`}
          </span>
          <span
            className="library-filtered-total-status"
            title="Общее число треков в текущей выборке"
            aria-live="polite"
          >
            {loading ? "..." : `(${total})`}
          </span>
        </div>
        <div className="library-playback-controls">
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
          <div className="library-playback-order-controls">
          <button
            className={`icon-button library-playback-shuffle-button ${libraryPlaybackShuffle ? "active" : ""}`}
            title={libraryPlaybackShuffle ? "Отключить случайный порядок воспроизведения на текущей странице" : "Включить случайный порядок воспроизведения на текущей странице"}
            aria-label="Переключить случайный порядок воспроизведения на текущей странице"
            aria-pressed={libraryPlaybackShuffle}
            disabled={loading || tracks.length < 2}
            onClick={onToggleLibraryPlaybackShuffle}
            type="button"
          >
            <Shuffle size={16} />
          </button>
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
          </div>
        </div>
        <button
          className="icon-button intent-add add-visible-tracks-button"
          title={addVisibleTitle}
          aria-label="Добавить треки текущей страницы в сет"
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
      {tracks.length ? (
        <TrackList
          tracks={tracks}
          startIndex={offset}
          seedSet={seedSet}
          playlistSet={playlistSet}
          playingTrackId={playingTrackId}
          previewTrackId={previewTrackId}
          previewCurrentTime={previewCurrentTime}
          previewDuration={previewDuration}
          onSeed={onSeed}
          onToggleLiked={onToggleLiked}
          onTogglePlaylist={onTogglePlaylist}
          onPreview={onPreview}
          onSeekPreview={onSeekPreview}
          onDetails={onDetails}
        />
      ) : null}
    </section>
  );
}
