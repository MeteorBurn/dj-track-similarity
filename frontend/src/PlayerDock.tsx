import { AudioLines, Pause, Play, Volume2 } from "lucide-react";
import type { RefObject } from "react";
import { useEffect, useState } from "react";
import type { Track } from "./api";
import { previewPositionForTrack, usePreviewPosition } from "./previewPosition";
import { displayTrack } from "./trackDisplay";
import type { PreviewTarget } from "./useSearchPlaylist";

const time = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;

export function PlayerDock({ preview, playing, audioRef, onToggle, onSeek }: {
  preview: PreviewTarget | null;
  playing: boolean;
  audioRef: RefObject<HTMLAudioElement | null>;
  onToggle: (track: PreviewTarget) => void;
  onSeek: (track: PreviewTarget, seconds: number) => void;
}) {
  const position = usePreviewPosition();
  const [volume, setVolume] = useState(1);
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [audioRef, preview, volume]);
  const { currentTime, duration } = previewPositionForTrack(position, preview?.track_id ?? -1);
  const track = preview && "file_path" in preview ? preview as Track : null;
  return (
    <footer className="player-dock" aria-label="Плеер">
      <div className="player-artwork" aria-hidden="true"><AudioLines size={30} /></div>
      <div className="player-track-info">
        <strong>{track ? displayTrack(track) : preview ? `Трек ${preview.track_id}` : "Выберите трек"}</strong>
        <span>{track?.album || "Прослушивание библиотеки"}</span>
      </div>
      <button type="button" className="player-play" disabled={!preview} onClick={() => preview && onToggle(preview)} aria-label={playing ? "Приостановить" : "Воспроизвести"}>
        {playing ? <Pause size={25} fill="currentColor" /> : <Play size={25} fill="currentColor" />}
      </button>
      <div className="player-timeline">
        <input type="range" min={0} max={duration || 1} step={0.1} value={currentTime} disabled={!preview || !duration} onChange={(event) => preview && onSeek(preview, Number(event.target.value))} aria-label="Позиция воспроизведения" />
        <span>{time(currentTime)} / {time(duration)}</span>
      </div>
      <div className="player-stat"><strong>{track?.tag_bpm ?? "—"}</strong><span>BPM</span></div>
      <div className="player-stat player-key"><strong>{track?.tag_key || "—"}</strong><span>KEY</span></div>
      <label className="player-volume"><Volume2 size={19} /><input type="range" aria-label="Громкость" min={0} max={1} step={0.01} value={volume} onChange={(event) => setVolume(Number(event.target.value))} /></label>
    </footer>
  );
}
