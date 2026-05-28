import { useEffect, useState } from "react";
import { ArrowDownUp, AudioWaveform, Heart, ListMusic, Plus, Search } from "lucide-react";
import { Track } from "./api";
import { likedTracksFilterTitle, libraryCurrentPageNumber, libraryPageCount, type LibraryPreset, type LibrarySortDirection } from "./libraryView";
import { TrackList } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

export function TrackPanel({
  query,
  onQueryChange,
  libraryPreset,
  onToggleLibraryPreset,
  likedOnly,
  likedTrackCount,
  onToggleLikedOnly,
  librarySortDirection,
  onToggleLibrarySortDirection,
  preview,
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
  onDetails
}: {
  query: string;
  onQueryChange: (value: string) => void;
  libraryPreset: LibraryPreset;
  onToggleLibraryPreset: (preset: LibraryPreset) => void;
  likedOnly: boolean;
  likedTrackCount: number;
  onToggleLikedOnly: () => void;
  librarySortDirection: LibrarySortDirection;
  onToggleLibrarySortDirection: () => void;
  preview: Track | null;
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
  onDetails: (track: Track) => void;
}) {
  const pageCount = libraryPageCount(total);
  const currentPage = libraryCurrentPageNumber(total, offset);
  const syncedPageInput = currentPage ? String(currentPage) : "";
  const [pageInput, setPageInput] = useState(syncedPageInput);
  const addVisibleTitle = total === 0
    ? "Нет отфильтрованных треков для добавления"
    : "Добавить все отфильтрованные треки в сет с учетом поиска, preset-фильтра и всех страниц. Уже добавленные треки будут пропущены.";
  const reverseSortActive = librarySortDirection === "reverse";

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
      </div>
      <div className="search-input">
        <Search size={16} />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="artist, title, genre, path" title={librarySearchHelp} />
      </div>
      <div className="library-view-controls">
        <button
          className={`icon-button library-preset-button ${libraryPreset === "syncopated" ? "active" : ""}`}
          title="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-label="Показать только треки с сохранённым MAEST-флагом syncopated rhythm"
          aria-pressed={libraryPreset === "syncopated"}
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
        <button className="secondary-mini library-page-previous-button" title="Предыдущая страница библиотеки" disabled={!canGoBack} onClick={onPreviousPage} type="button">Prev</button>
        <button className="secondary-mini library-page-next-button" title="Следующая страница библиотеки" disabled={!canGoForward} onClick={onNextPage} type="button">Next</button>
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
        <span className="library-range-status" title="Количество треков в текущей выдаче">
          {loading ? "..." : `${total}`}
        </span>
        <button
          className={`icon-button library-sort-direction-button ${reverseSortActive ? "active" : ""}`}
          title={reverseSortActive ? "Показать текущую страницу библиотеки в прямом порядке" : "Показать текущую страницу библиотеки в обратном порядке"}
          aria-label="Переключить порядок треков на текущей странице библиотеки"
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
      <div className="player library-player">
        <span>{preview ? displayTrack(preview) : "Preview"}</span>
        {preview && <audio controls autoPlay src={`/media/${preview.id}`} />}
      </div>
      <TrackList
        tracks={tracks}
        seedSet={seedSet}
        playlistSet={playlistSet}
        onSeed={onSeed}
        onToggleLiked={onToggleLiked}
        onTogglePlaylist={onTogglePlaylist}
        onPreview={onPreview}
        onDetails={onDetails}
      />
    </section>
  );
}
