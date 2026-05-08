import { Save, X } from "lucide-react";
import { Fragment } from "react";
import { Track } from "./api";
import { basename, displayTrack } from "./trackDisplay";

const trackTagLabels: Record<string, string> = {
  artist: "Artist",
  album: "Album",
  genre: "Genre",
  year: "Year",
  country: "Country",
  label: "Label",
  catalog_number: "Catalog",
  track_number: "Track no.",
  disc_number: "Disc no.",
  bpm: "BPM tag",
  key: "Key tag",
  comment: "Comment",
  isrc: "ISRC"
};

const trackTagOrder = [
  "artist",
  "album",
  "genre",
  "year",
  "country",
  "label",
  "catalog_number",
  "track_number",
  "disc_number",
  "bpm",
  "key",
  "comment",
  "isrc"
];

function readablePrimaryTrackInfo(track: Track) {
  const metadata = (track.metadata && typeof track.metadata === "object" && !Array.isArray(track.metadata)
    ? track.metadata
    : {}) as Record<string, unknown>;
  const audioFormat = displayAudioFormat(metadata.audio_format, track.path);
  const audioCodec = formatTagValue(metadata.audio_codec);
  const formatAndCodec = formatAudioFormat(audioFormat, audioCodec);
  return [
    ["Title", track.title || String(metadata.title || basename(track.path))],
    ["Audio Length", typeof track.duration === "number" ? formatPlayerDuration(track.duration) : "-"],
    ["Audio Format", formatAndCodec],
    ["File Size", formatFileSizeMb(track.size)],
    ["File Path", track.path]
  ] as const;
}

function readableTrackTags(raw: Track["metadata"]) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  const record = raw as Record<string, unknown>;
  return trackTagOrder
    .filter((key) => record[key] != null && record[key] !== "")
    .map((key) => [trackTagLabels[key] || key, record[key]] as const);
}

export function TrackMetadataDialog({
  track,
  busy,
  onWriteGenres,
  onClose
}: {
  track: Track;
  busy: boolean;
  onWriteGenres: (track: Track) => void;
  onClose: () => void;
}) {
  const genres = track.genres || [];
  const scores = track.genre_scores || {};
  const sonaraFeatureGroups = readableSonaraFeatureGroups(track.metadata?.sonara_features);
  const sonaraFeatureCount = sonaraFeatureGroups.reduce((total, group) => total + group.features.length, 0);
  const primaryEntries = readablePrimaryTrackInfo(track);
  const metadataEntries = readableTrackTags(track.metadata);
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="metadata-dialog" role="dialog" aria-modal="true" aria-label="Теги трека" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">
          <div>
            <h2>Теги и жанры</h2>
            <span>{basename(track.path)}</span>
          </div>
          <button className="icon-button" title="Закрыть" aria-label="Закрыть" onClick={onClose}><X size={15} /></button>
        </div>
        <strong className="metadata-track-title">{displayTrack(track)}</strong>
        <div className="mutagen-block">
          <dl className="metadata-grid mutagen-grid">
            {primaryEntries.map(([key, value]) => (
              <Fragment key={key}><dt>{key}</dt><dd>{value}</dd></Fragment>
            ))}
            {metadataEntries.map(([key, value]) => (
              <Fragment key={key}><dt>{key}</dt><dd>{formatTagValue(value)}</dd></Fragment>
            ))}
          </dl>
        </div>
        <div className="sonara-block">
          <strong>SONARA features</strong>
          {sonaraFeatureCount ? (
            <div className="sonara-feature-groups">
              {sonaraFeatureGroups.map((group) => (
                <div className="sonara-feature-group" key={group.title}>
                  <span className="sonara-feature-group-title">{group.title}</span>
                  <dl className="metadata-grid tag-grid sonara-feature-grid">
                    {group.features.map((feature) => (
                      <Fragment key={feature.key}><dt title={feature.description}>{feature.label}</dt><dd title={feature.description}>{feature.value}</dd></Fragment>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          ) : (
            <span className="empty-genres">SONARA признаки ещё не извлечены</span>
          )}
        </div>
        <div className="genre-block">
          <div className="genre-block-title">
            <strong>MAEST genres</strong>
            <button className="secondary-mini" disabled={busy || !genres.length} title="Перезаписать стандартный Genre тег этого файла жанрами MAEST" onClick={() => onWriteGenres(track)}>
              <Save size={13} />
              Save
            </button>
          </div>
          {genres.length ? (
            <div className="genre-list">
              {genres.map((genre) => (
                <span className="genre-pill" key={genre}>{formatGenreLabel(genre)} <b>{formatConfidence(scores[genre])}</b></span>
              ))}
            </div>
          ) : (
            <span className="empty-genres">Жанры ещё не извлечены</span>
          )}
        </div>
      </section>
    </div>
  );
}

const sonaraFeatureLabels: Record<string, string> = {
  bpm: "BPM",
  camelot_key: "Musical Key",
  duration_sec: "Duration",
  key: "Key",
  key_confidence: "Key confidence",
  energy: "Energy",
  danceability: "Danceability",
  valence: "Valence",
  acousticness: "Acousticness",
  loudness_lufs: "Loudness",
  dynamic_range_db: "Dynamic range",
  predominant_chord: "Predominant chord",
  chord_change_rate: "Chord changes",
  dissonance: "Dissonance",
  onset_density: "Onset density",
  beats: "Beats",
  n_beats: "Beat count",
  onset_frames: "Onsets",
  spectral_centroid_mean: "Brightness",
  spectral_bandwidth_mean: "Bandwidth",
  spectral_rolloff_mean: "Rolloff",
  spectral_flatness_mean: "Flatness",
  spectral_contrast_mean: "Contrast",
  zero_crossing_rate: "ZCR",
  mfcc_mean: "MFCC mean",
  chroma_mean: "Chroma mean",
  chord_sequence: "Chord sequence"
};

const sonaraPlaylistFeatureGroups = [
  {
    title: "Core features",
    keys: ["bpm", "camelot_key", "beats", "onset_frames", "onset_density", "n_beats", "rms_mean", "rms_max", "loudness_lufs", "dynamic_range_db", "spectral_centroid_mean", "zero_crossing_rate", "duration_sec"]
  },
  {
    title: "Perceptual features (0.0 - 1.0)",
    keys: ["energy", "danceability", "valence", "acousticness"]
  },
  {
    title: "Musical key",
    keys: ["key", "key_confidence"]
  },
  {
    title: "Tonal analysis",
    keys: ["chord_sequence", "predominant_chord", "chord_change_rate", "dissonance"]
  },
  {
    title: "Spectral features",
    keys: ["spectral_bandwidth_mean", "spectral_rolloff_mean", "spectral_flatness_mean", "spectral_contrast_mean", "mfcc_mean", "chroma_mean"]
  }
] as const;

const sonaraPlaylistFeatureKeys = new Set(sonaraPlaylistFeatureGroups.flatMap((group) => [...group.keys]));

function readableSonaraFeatureGroups(raw: unknown) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
  const record = raw as Record<string, unknown>;
  return sonaraPlaylistFeatureGroups
    .map((group) => ({
      title: group.title,
      features: group.keys
        .map((key) => {
          const payload = record[key];
          const featureRecord = payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : {};
          if (!sonaraPlaylistFeatureKeys.has(key) || featureRecord.type === "unavailable" || featureRecord.value == null) return null;
          return {
            key,
            label: sonaraFeatureLabels[key] || formatFeatureLabel(key),
            value: formatSonaraValue(featureRecord, key),
            description: typeof featureRecord.description === "string" ? featureRecord.description : ""
          };
        })
        .filter((feature) => feature != null)
    }))
    .filter((group) => group.features.length);
}

function formatFeatureLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function formatSonaraValue(record: Record<string, unknown>, key?: string) {
  const value = record.value;
  if (record.type === "unavailable") return "-";
  if (record.type === "duration" && typeof value === "number") return formatPlayerDuration(value);
  if (record.type === "ndarray" || record.storage) {
    const shape = Array.isArray(record.shape) ? record.shape.join("x") : "";
    const summary = record.summary && typeof record.summary === "object" ? record.summary as Record<string, unknown> : null;
    const mean = typeof summary?.mean === "number" ? ` mean ${formatNumber(summary.mean)}` : "";
    return `${shape || record.size || "array"}${mean}`;
  }
  if (typeof value === "number") {
    if (key === "onset_density") return `${formatNumber(value)} value/sec`;
    return formatNumber(value);
  }
  if (Array.isArray(value)) return `${value.length} values`;
  if (value == null) return "-";
  return String(value);
}

function formatNumber(value: number) {
  if (Math.abs(value) >= 100) return value.toFixed(1);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatTagValue(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ");
  if (value == null) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function displayAudioFormat(value: unknown, path: string) {
  const stored = formatTagValue(value);
  if (stored && stored !== "-") {
    if (stored.toLowerCase().startsWith("audio/")) return audioFormatFromPath(path) || stored.replace(/^audio\//i, "").toUpperCase();
    return stored;
  }
  return audioFormatFromPath(path) || "-";
}

function audioFormatFromPath(path: string) {
  const extension = path.split(".").pop()?.toLowerCase();
  const formats: Record<string, string> = {
    aif: "AIFF",
    aiff: "AIFF",
    alac: "ALAC",
    flac: "FLAC",
    m4a: "M4A",
    mp3: "MP3",
    ogg: "Ogg",
    opus: "Opus",
    wav: "Wave",
    wave: "Wave"
  };
  return extension ? formats[extension] : undefined;
}

function formatAudioFormat(audioFormat: string, audioCodec: string) {
  if (!audioCodec || audioCodec === "-") return audioFormat || "-";
  if (!audioFormat || audioFormat === "-") return audioCodec;
  const normalizedFormat = normalizeAudioFormatPart(audioFormat);
  const normalizedCodec = normalizeAudioFormatPart(audioCodec);
  if (normalizedFormat && normalizedFormat === normalizedCodec) return audioFormat;
  return `${audioFormat} / ${audioCodec}`;
}

function normalizeAudioFormatPart(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function formatFileSizeMb(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatConfidence(value: number | undefined) {
  if (value == null) return "0%";
  return `${Math.round(value * 100)}%`;
}

function formatGenreLabel(label: string) {
  return label.replace(/^Electronic---/i, "");
}

function formatPlayerDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const rest = (rounded % 60).toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${rest}`;
  return `${minutes}:${rest}`;
}
