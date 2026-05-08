import { ListMusic, Search } from "lucide-react";
import { Track } from "./api";
import { TrackList } from "./TrackRows";
import { displayTrack } from "./trackDisplay";

export function TrackPanel({
  query,
  onQueryChange,
  preview,
  tracks,
  seedSet,
  playlistSet,
  librarySearchHelp,
  onSeed,
  onTogglePlaylist,
  onPreview,
  onDetails
}: {
  query: string;
  onQueryChange: (value: string) => void;
  preview: Track | null;
  tracks: Track[];
  seedSet: Set<number>;
  playlistSet: Set<number>;
  librarySearchHelp: string;
  onSeed: (track: Track) => void;
  onTogglePlaylist: (track: Track) => void;
  onPreview: (track: Track) => void;
  onDetails: (track: Track) => void;
}) {
  return (
    <section className="panel track-panel">
      <div className="panel-title">
        <ListMusic size={18} />
        <h2>2. Библиотека и прослушивание</h2>
      </div>
      <div className="search-input">
        <Search size={16} />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="artist, title, path" title={librarySearchHelp} />
      </div>
      <div className="player library-player">
        <span>{preview ? displayTrack(preview) : "Preview"}</span>
        {preview && <audio controls src={`/media/${preview.id}`} />}
      </div>
      <TrackList
        tracks={tracks}
        seedSet={seedSet}
        playlistSet={playlistSet}
        onSeed={onSeed}
        onTogglePlaylist={onTogglePlaylist}
        onPreview={onPreview}
        onDetails={onDetails}
      />
    </section>
  );
}
