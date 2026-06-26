import { Check, Copy, X } from "lucide-react";
import { Fragment, useState } from "react";
import { Track } from "./api";
import { formatMaestGenreLabel, hasMaestSyncopatedRhythm, SYNCOPATED_RHYTHM_LABEL } from "./syncopatedRhythm";
import { basename, displayTrack, trackHasAnalysis } from "./trackDisplay";

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
  bpm: "BPM",
  key: "Key",
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
  onClose
}: {
  track: Track;
  onClose: () => void;
}) {
  const [filePathCopied, setFilePathCopied] = useState(false);
  const genres = track.genres || [];
  const scores = track.genre_scores || {};
  const trackHasSyncopatedRhythm = hasMaestSyncopatedRhythm(track.metadata);
  const sonaraFeatureGroups = readableSonaraFeatureGroups(track.metadata?.sonara_features);
  const sonaraFeatureCount = sonaraFeatureGroups.reduce((total, group) => total + group.features.length, 0);
  const classifierScores = readableClassifierScores(track);
  const analysisBadges = readableAnalysisBadges(track);
  const primaryEntries = readablePrimaryTrackInfo(track);
  const metadataEntries = readableTrackTags(track.metadata);

  async function copyFilePath() {
    const copied = await copyTextToClipboard(track.path);
    if (!copied) return;
    setFilePathCopied(true);
    window.setTimeout(() => setFilePathCopied(false), 1400);
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="metadata-dialog" role="dialog" aria-modal="true" aria-label="Теги трека" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-title">
          <div>
            <h2 className="metadata-track-title">{displayTrack(track)}</h2>
            {analysisBadges.length ? (
              <div className="analysis-badge-row">
                {analysisBadges.map((badge) => (
                  <span className="analysis-badge" key={badge.key}>{badge.label}</span>
                ))}
              </div>
            ) : null}
          </div>
          <button className="icon-button close-metadata-dialog-button" title="Закрыть" aria-label="Закрыть" onClick={onClose}><X size={15} /></button>
        </div>
        <div className="mutagen-block">
          <strong>Mutagen tags</strong>
          <dl className="metadata-grid mutagen-grid">
            {primaryEntries.map(([key, value]) => (
              <Fragment key={key}>
                <dt>{key}</dt>
                {key === "File Path" ? (
                  <dd className="metadata-file-path-row">
                    <span className="metadata-file-path-value">{value}</span>
                    <button
                      className="icon-button metadata-copy-path-button"
                      title={filePathCopied ? "Copied" : "Copy file path"}
                      aria-label={`Copy file path: ${track.path}`}
                      onClick={() => void copyFilePath()}
                      type="button"
                    >
                      {filePathCopied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </dd>
                ) : (
                  <dd>{value}</dd>
                )}
              </Fragment>
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
        <div className="classifier-score-block">
          <strong>Classifier scores</strong>
          {classifierScores.length ? (
            <dl className="metadata-grid classifier-score-grid">
              {classifierScores.map((score) => (
                <Fragment key={score.key}><dt>{score.label}</dt><dd>{score.value}</dd></Fragment>
              ))}
            </dl>
          ) : (
            <span className="empty-genres">Classifier scores ещё не рассчитаны</span>
          )}
        </div>
        <div className="genre-block">
          <div className="genre-block-title">
            <strong>MAEST genres</strong>
          </div>
          {genres.length ? (
            <div className="genre-list">
              {genres.map((genre) => (
                <span className="genre-pill" key={genre}>{formatMaestGenreLabel(genre)} <b>{formatConfidence(scores[genre])}</b></span>
              ))}
              {trackHasSyncopatedRhythm ? <span className="genre-pill syncopated-rhythm-pill">{SYNCOPATED_RHYTHM_LABEL}</span> : null}
            </div>
          ) : (
            <span className="empty-genres">Жанры ещё не извлечены</span>
          )}
        </div>
      </section>
    </div>
  );
}

async function copyTextToClipboard(text: string) {
  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the textarea fallback below.
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.left = "-1000px";
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

function readableClassifierScores(track: Track) {
  const result: Array<{ key: string; label: string; value: string }> = [];
  Object.entries(track.classifier_scores || {}).forEach(([key, score]) => {
    result.push({
      key,
      label: readableClassifierName(key),
      value: formatClassifierScore(score.score)
    });
  });
  return result;
}

function readableAnalysisBadges(track: Track) {
  const badges: Array<{ key: string; label: string }> = (["sonara", "maest", "mert", "clap"] as const)
    .filter((model) => trackHasAnalysis(track, model))
    .map((model) => ({ key: model, label: model.toUpperCase() }));
  if (track.classifier_scores && Object.keys(track.classifier_scores).length) {
    badges.push({ key: "classifiers", label: "CLASSIFIERS" });
  }
  return badges;
}

function readableClassifierName(key: string) {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatClassifierScore(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return formatScore(value);
}

function formatScore(value: number) {
  if (value < 1 && value.toFixed(6) === "1.000000") return "0.999999";
  return value.toFixed(6);
}

const sonaraFeatureLabels: Record<string, string> = {
  bpm: "BPM",
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
  rms_mean: "RMS",
  rms_max: "RMS max",
  beats: "Beats",
  n_beats: "Beat count",
  onset_frames: "Onsets",
  spectral_centroid_mean: "Spectral Centroid",
  spectral_bandwidth_mean: "Bandwidth",
  spectral_rolloff_mean: "Rolloff",
  spectral_flatness_mean: "Flatness",
  spectral_contrast_mean: "Contrast",
  zero_crossing_rate: "ZCR",
  mfcc_mean: "MFCC",
  chroma_mean: "Chroma",
};

const sonaraFeatureDescriptions: Record<string, string> = {
  bpm: "Tempo (BPM)",
  beats: "Beat frame positions",
  onset_frames: "Onset positions",
  onset_density: "Onsets per second",
  n_beats: "Number of detected beats",
  rms_mean: "Average loudness (RMS)",
  rms_max: "Peak loudness (RMS)",
  loudness_lufs: "Integrated loudness (LUFS, ITU-R BS.1770-4)",
  dynamic_range_db: "Loudness range (p95 - p5, dB)",
  spectral_centroid_mean: "Brightness (Hz)",
  zero_crossing_rate: "Percussiveness proxy",
  duration_sec: "Track length",
  energy: "Perceived intensity (loudness + brightness + activity)",
  danceability: "Beat regularity + tempo sweet spot + rhythm",
  valence: "Mood (0 = sad/dark, 1 = happy/bright)",
  acousticness: "Acoustic vs electronic character",
  key: "Musical key, for example C major or A minor",
  key_confidence: "Key detection confidence (0.0 - 1.0)",
  predominant_chord: "Most frequent chord",
  chord_change_rate: "Chord changes per second (harmonic complexity)",
  dissonance: "Sensory dissonance (0 = consonant, 1 = rough)",
  spectral_bandwidth_mean: "Frequency spread",
  spectral_rolloff_mean: "Frequency below which 85% of energy sits",
  spectral_flatness_mean: "Tonal (0) vs noise-like (1)",
  spectral_contrast_mean: "Peak-valley ratio per band (7 values)",
  mfcc_mean: "Timbre fingerprint (13 coefficients)",
  chroma_mean: "Pitch class distribution (12 values)",
};

const sonaraPlaylistFeatureGroups = [
  {
    title: "Core",
    keys: ["duration_sec", "bpm", "beats", "onset_frames", "onset_density", "n_beats", "spectral_centroid_mean", "zero_crossing_rate", "rms_mean", "rms_max", "loudness_lufs", "dynamic_range_db"]
  },
  {
    title: "Perceptual",
    keys: ["energy", "danceability", "valence", "acousticness"]
  },
  {
    title: "Tonal",
    keys: ["key", "key_confidence", "predominant_chord", "chord_change_rate", "dissonance"]
  },
  {
    title: "Spectral",
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
            description: sonaraFeatureDescriptions[key] || ""
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
  if (key === "bpm" && typeof value === "number") return value.toFixed(2);
  if (record.type === "duration" && typeof value === "number") return formatPlayerDuration(value);
  if (record.type === "ndarray" || record.storage) {
    const shape = Array.isArray(record.shape) ? record.shape.join("x") : "";
    const summary = record.summary && typeof record.summary === "object" ? record.summary as Record<string, unknown> : null;
    const mean = typeof summary?.mean === "number" ? ` mean ${formatNumber(summary.mean)}` : "";
    return `${shape || record.size || "array"}${mean}`;
  }
  if (typeof value === "number") {
    if (key === "onset_density") return `${formatNumber(value)}/sec`;
    if (key === "chord_change_rate") return `${formatNumber(value)}/sec`;
    if (key === "loudness_lufs") return `${value.toFixed(2)} LUFS`;
    if (key === "dynamic_range_db") return `${value.toFixed(2)} dB`;
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

function formatPlayerDuration(seconds: number) {
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const rest = (rounded % 60).toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${rest}`;
  return `${minutes}:${rest}`;
}
