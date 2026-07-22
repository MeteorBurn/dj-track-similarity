import { Check, Copy, X } from "lucide-react";
import { Fragment, useState } from "react";
import { Track, TrackDetailV7 } from "./api";
import { formatMaestGenreLabel, hasMaestSyncopatedRhythm, SYNCOPATED_RHYTHM_LABEL } from "./syncopatedRhythm";
import { basename, displayTrack, trackHasAnalysis } from "./trackDisplay";

const trackTagLabels: Record<string, string> = {
  genre: "Genre",
  bpm: "BPM",
  key: "Key",
  comment: "Comment",
  year: "Year",
  label: "Label",
  catalog_number: "Catalog Number",
  country: "Country",
  isrc: "ISRC",
  track_number: "Track Number",
  disc_number: "Disc Number"
};

const trackTagOrder = [
  "genre",
  "bpm",
  "key",
  "comment",
  "year",
  "label",
  "catalog_number",
  "country",
  "isrc",
  "track_number",
  "disc_number"
];

function readablePrimaryTrackInfo(track: Track | TrackDetailV7) {
  let audioFormatRaw: string | null | undefined;
  let audioCodecRaw: string | null | undefined;
  let duration: number | null | undefined;
  let size: number | null | undefined;
  let path: string;
  let title: string;

  if ("file" in track) {
    audioFormatRaw = track.file.audio_format;
    audioCodecRaw = track.file.audio_codec;
    duration = track.file.audio_duration_seconds;
    size = track.file.file_size_bytes;
    path = track.file_path;
    title = track.title || basename(path);
  } else {
    const metadata = (track.metadata && typeof track.metadata === "object" && !Array.isArray(track.metadata)
      ? track.metadata
      : {}) as Record<string, unknown>;
    audioFormatRaw = metadata.audio_format as string;
    audioCodecRaw = metadata.audio_codec as string;
    duration = track.duration;
    size = track.size;
    path = track.path;
    title = track.title || String(metadata.title || basename(path));
  }

  const audioFormat = displayAudioFormat(audioFormatRaw, path);
  const audioCodec = formatTagValue(audioCodecRaw);
  const formatAndCodec = formatAudioFormat(audioFormat, audioCodec);

  return [
    ["Title", title],
    ["Audio Length", typeof duration === "number" ? formatPlayerDuration(duration) : "-"],
    ["Audio Format", formatAndCodec],
    ["File Size", formatFileSizeMb(size || 0)],
    ["File Path", path]
  ] as const;
}

function readableTrackTags(track: Track | TrackDetailV7) {
  const record: Record<string, unknown> = {};
  if ("file_tags" in track) {
    if (track.file_tags) {
      record.genre = track.file_tags.genres?.join(", ");
      record.bpm = track.file_tags.tag_bpm;
      record.key = track.file_tags.tag_key;
      record.comment = track.file_tags.comment;
      record.year = track.file_tags.year;
      record.label = track.file_tags.label;
      record.catalog_number = track.file_tags.catalog_number;
      record.country = track.file_tags.country;
      record.isrc = track.file_tags.isrc;
      record.track_number = track.file_tags.track_number;
      record.disc_number = track.file_tags.disc_number;
    }
  } else {
    const raw = track.metadata;
    if (raw && typeof raw === "object" && !Array.isArray(raw)) {
      Object.assign(record, raw);
    }
  }

  return trackTagOrder
    .filter((key) => record[key] != null && record[key] !== "")
    .map((key) => [trackTagLabels[key] || key, record[key]] as const);
}

export function TrackMetadataDialog({
  track,
  onClose
}: {
  track: Track | TrackDetailV7;
  onClose: () => void;
}) {
  const [filePathCopied, setFilePathCopied] = useState(false);
  
  let genres: string[] = [];
  let scores: Record<string, number> = {};
  if ("maest" in track) {
    if (track.maest?.genres) {
      genres = track.maest.genres.map(g => g.genre_name);
      track.maest.genres.forEach(g => {
        scores[g.genre_name] = g.score;
      });
    }
  } else {
    genres = track.genres || [];
    scores = track.genre_scores || {};
  }

  const trackHasSyncopatedRhythmFlag = hasMaestSyncopatedRhythm(track);
  const hasSonaraAnalysis = trackHasAnalysis(track, "sonara");
  
  let timelineFields: string[] = [];
  let sonaraEmbeddingAvailable = false;
  let audioFingerprintAvailable = false;

  if ("optional_outputs" in track) {
    timelineFields = track.optional_outputs?.timeline_fields || [];
    sonaraEmbeddingAvailable = !!track.optional_outputs?.sonara_embedding_available;
    audioFingerprintAvailable = !!track.optional_outputs?.audio_fingerprint_available;
  } else {
    timelineFields = track.timeline_fields || [];
    const representationFields = track.representation_fields || [];
    sonaraEmbeddingAvailable = representationFields.includes("embedding");
    audioFingerprintAvailable = representationFields.includes("fingerprint");
  }

  const sonaraFeatureGroups = readableSonaraFeatureGroups(track);
  const sonaraFeatureCount = sonaraFeatureGroups.reduce((total, group) => total + group.features.length, 0);
  const classifierScores = readableClassifierScores(track);
  const analysisBadges = readableAnalysisBadges(track);
  const primaryEntries = readablePrimaryTrackInfo(track);
  const metadataEntries = readableTrackTags(track);
  const path = "file_path" in track ? track.file_path : track.path;

  async function copyFilePath() {
    const copied = await copyTextToClipboard(path);
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
                      aria-label={`Copy file path: ${path}`}
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
          <strong>SONARA · Core</strong>
          {sonaraFeatureCount || hasSonaraAnalysis ? (
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
            <span className="empty-genres">Core данные ещё не рассчитаны</span>
          )}
        </div>
        <StoragePresenceBlock title="Timeline" fields={timelineFields} emptyText="Timeline данные ещё не рассчитаны" />
        
        <div className="sonara-storage-block">
          <strong>SONARA optional outputs</strong>
          <dl className="metadata-grid tag-grid sonara-feature-grid">
            <Fragment key="sonara_embedding">
              <dt>Similarity embedding</dt>
              <dd>{sonaraEmbeddingAvailable ? <span className="sonara-storage-present"><Check size={14} /> Present</span> : "-"}</dd>
            </Fragment>
            <Fragment key="audio_fingerprint">
              <dt>Audio fingerprint</dt>
              <dd>{audioFingerprintAvailable ? <span className="sonara-storage-present"><Check size={14} /> Present</span> : "-"}</dd>
            </Fragment>
          </dl>
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
              {trackHasSyncopatedRhythmFlag ? <span className="genre-pill syncopated-rhythm-pill">{SYNCOPATED_RHYTHM_LABEL}</span> : null}
            </div>
          ) : (
            <span className="empty-genres">Жанры ещё не извлечены</span>
          )}
        </div>
      </section>
    </div>
  );
}

function StoragePresenceBlock({
  title,
  fields,
  emptyText
}: {
  title: string;
  fields: string[];
  emptyText: string;
}) {
  return (
    <div className="sonara-storage-block">
      <strong>{title}</strong>
      {fields.length ? (
        <>
          <span className="sonara-storage-present"><Check size={14} /> Данные присутствуют</span>
          <div className="sonara-storage-fields">
            {fields.map((field) => <code key={field}>{field}</code>)}
          </div>
        </>
      ) : (
        <span className="empty-genres">{emptyText}</span>
      )}
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

function readableClassifierScores(track: Track | TrackDetailV7) {
  const result: Array<{ key: string; label: string; value: string }> = [];
  if ("classifier_scores_detail" in track) {
    (track.classifier_scores_detail || []).forEach((score) => {
      result.push({
        key: score.classifier_key,
        label: readableClassifierName(score.classifier_key),
        value: `${score.predicted_class} (${score.score_bucket})`
      });
    });
  } else {
    Object.entries(track.classifier_scores || {}).forEach(([key, score]) => {
      result.push({
        key,
        label: readableClassifierName(key),
        value: formatClassifierScore(score.score)
      });
    });
  }
  return result;
}

function readableAnalysisBadges(track: Track | TrackDetailV7) {
  const badges: Array<{ key: string; label: string }> = (["sonara", "maest", "mert", "muq", "clap"] as const)
    .filter((model) => trackHasAnalysis(track, model))
    .map((model) => ({ key: model, label: model.toUpperCase() }));
  
  if ("classifier_scores_detail" in track) {
    if (track.classifier_scores_detail && track.classifier_scores_detail.length > 0) {
      badges.push({ key: "classifiers", label: "CLASSIFIERS" });
    }
  } else {
    if (track.classifier_scores && Object.keys(track.classifier_scores).length) {
      badges.push({ key: "classifiers", label: "CLASSIFIERS" });
    }
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
  bpm_raw: "Raw BPM",
  bpm_candidates: "BPM candidates",
  bpm_confidence: "BPM confidence",
  tempo_variability: "Tempo variability",
  time_signature: "Time signature",
  time_signature_confidence: "Time signature confidence",
  duration_sec: "Duration",
  key: "Key",
  key_camelot: "Camelot",
  key_confidence: "Key confidence",
  key_candidates: "Key candidates",
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
  energy_level: "Energy level",
  intro_end_sec: "Intro end",
  outro_start_sec: "Outro start",
  segments: "Structure segments",
  energy_curve_hop_sec: "Energy curve hop",
  energy_curve_summary: "Energy curve summary",
  true_peak_db: "True peak",
  replaygain_db: "ReplayGain",
  loudness_momentary_max_db: "Momentary max",
  loudness_range_lu: "Loudness range",
  grid_offset_sec: "Grid offset",
  grid_stability: "Grid stability",
  vocalness: "Vocalness",
  instrumentalness: "Instrumentalness",
  mood_happy: "Happy",
  mood_aggressive: "Aggressive",
  mood_relaxed: "Relaxed",
  mood_sad: "Sad",
  leading_silence_sec: "Leading silence",
  trailing_silence_sec: "Trailing silence",
};

const sonaraFeatureDescriptions: Record<string, string> = {
  bpm: "Tempo (BPM)",
  bpm_raw: "Unfolded tempo estimate before the configured BPM range is applied",
  bpm_candidates: "Ranked tempo candidates as BPM and confidence-score pairs",
  bpm_confidence: "Tempo detection confidence (0.0 - 1.0)",
  tempo_variability: "Within-track tempo variation retained as archival data for future rhythm features",
  time_signature: "Detected musical meter; shown as Unknown when confidence is zero",
  time_signature_confidence: "Confidence in the detected time signature (0.0 - 1.0)",
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
  key_camelot: "Camelot wheel code for harmonic mixing (SONARA analysis output)",
  key_candidates: "Top key candidates with Camelot code and score",
  energy_level: "Overall energy tier (1 = calm, 10 = intense)",
  intro_end_sec: "Estimated end of the intro",
  outro_start_sec: "Estimated start of the outro",
  segments: "Estimated within-track structure segments",
  energy_curve_hop_sec: "Time spacing between stored energy-curve values",
  energy_curve_summary: "Compact min, max, mean, and standard-deviation summary of the energy curve",
  true_peak_db: "True peak level (dBTP, ITU-R BS.1770-4)",
  replaygain_db: "Suggested ReplayGain adjustment (dB)",
  loudness_momentary_max_db: "Maximum momentary loudness (LUFS)",
  loudness_range_lu: "Loudness range (LU)",
  grid_offset_sec: "Beat-grid offset from the first sample",
  grid_stability: "Beat-grid stability (0 = drifting, 1 = steady)",
  vocalness: "Bundled SONARA vocal model score P(vocal) (0 = instrumental, 1 = vocal)",
  instrumentalness: "Bundled SONARA instrumental score (1 - P(vocal))",
  mood_happy: "Heuristic v1 affinity for a happy mood (0.0 - 1.0; not a classifier)",
  mood_aggressive: "Heuristic v1 affinity for an aggressive mood (0.0 - 1.0; not a classifier)",
  mood_relaxed: "Heuristic v1 affinity for a relaxed mood (0.0 - 1.0; not a classifier)",
  mood_sad: "Heuristic v1 affinity for a sad mood (0.0 - 1.0; not a classifier)",
  leading_silence_sec: "Silence before the first sound",
  trailing_silence_sec: "Silence after the last sound",
};

const sonaraPlaylistFeatureGroups = [
  {
    title: "Core",
    keys: ["duration_sec", "bpm", "bpm_raw", "bpm_confidence", "bpm_candidates", "onset_density", "n_beats", "spectral_centroid_mean", "zero_crossing_rate", "rms_mean", "rms_max", "loudness_lufs", "dynamic_range_db"]
  },
  {
    title: "Perceptual",
    keys: ["energy", "energy_level", "danceability", "valence", "acousticness"]
  },
  {
    title: "Tonal",
    keys: ["key", "key_camelot", "key_confidence", "key_candidates", "predominant_chord", "chord_change_rate", "dissonance"]
  },
  {
    title: "Spectral",
    keys: ["spectral_bandwidth_mean", "spectral_rolloff_mean", "spectral_flatness_mean", "spectral_contrast_mean", "mfcc_mean", "chroma_mean"]
  },
  {
    title: "Loudness",
    keys: ["true_peak_db", "replaygain_db", "loudness_momentary_max_db", "loudness_range_lu"]
  },
  {
    title: "Structure",
    keys: ["intro_end_sec", "outro_start_sec", "energy_curve_hop_sec", "energy_curve_summary"]
  },
  {
    title: "Beatgrid",
    keys: ["grid_offset_sec", "grid_stability"]
  },
  {
    title: "Voice",
    keys: ["vocalness", "instrumentalness"]
  },
  {
    title: "Mood",
    keys: ["mood_happy", "mood_aggressive", "mood_relaxed", "mood_sad"]
  },
  {
    title: "Silence",
    keys: ["leading_silence_sec", "trailing_silence_sec"]
  },
  {
    title: "Rhythm metadata",
    keys: ["tempo_variability", "time_signature", "time_signature_confidence"]
  }
] as const;

const sonaraPlaylistFeatureKeys = new Set(sonaraPlaylistFeatureGroups.flatMap((group) => [...group.keys]));

function readableSonaraFeatureGroups(track: Track | TrackDetailV7) {
  let record: Record<string, unknown> = {};
  let timeSignatureConfidence: number | undefined;

  if ("sonara_core" in track) {
    if (!track.sonara_core) return [];
    const core = track.sonara_core;
    record = {
      duration_sec: core.analyzed_duration_seconds,
      bpm: core.detected_bpm,
      bpm_raw: core.raw_bpm,
      bpm_confidence: core.bpm_confidence,
      bpm_candidates: core.bpm_candidates,
      onset_density: core.onset_density_per_second,
      n_beats: core.beat_count,
      spectral_centroid_mean: core.spectral_centroid_hz,
      zero_crossing_rate: core.zero_crossing_rate,
      rms_mean: core.rms_mean,
      rms_max: core.rms_max,
      loudness_lufs: core.integrated_loudness_lufs,
      dynamic_range_db: core.dynamic_range_db,
      energy: core.energy_score,
      energy_level: core.energy_level,
      danceability: core.danceability_score,
      valence: core.valence_score,
      acousticness: core.acousticness_score,
      key: core.detected_key_name,
      key_camelot: core.detected_key_camelot,
      key_confidence: core.key_confidence,
      key_candidates: core.key_candidates,
      predominant_chord: core.predominant_chord,
      chord_change_rate: core.chord_changes_per_second,
      dissonance: core.dissonance_score,
      spectral_bandwidth_mean: core.spectral_bandwidth_hz,
      spectral_rolloff_mean: core.spectral_rolloff_hz,
      spectral_flatness_mean: core.spectral_flatness,
      true_peak_db: core.true_peak_dbtp,
      replaygain_db: core.replay_gain_db,
      loudness_momentary_max_db: core.max_momentary_loudness_lufs,
      loudness_range_lu: core.loudness_range_lu,
      intro_end_sec: core.intro_end_seconds,
      outro_start_sec: core.outro_start_seconds,
      energy_curve_hop_sec: core.energy_curve_hop_seconds,
      energy_curve_summary: core.energy_curve_sample_count != null ? {
        min: core.energy_curve_min,
        max: core.energy_curve_max,
        mean: core.energy_curve_mean,
        stddev: core.energy_curve_stddev
      } : null,
      grid_offset_sec: core.beat_grid_offset_seconds,
      grid_stability: core.beat_grid_stability,
      vocalness: core.vocal_probability,
      instrumentalness: core.vocal_probability != null ? 1.0 - core.vocal_probability : null,
      mood_happy: core.mood_happy_score,
      mood_aggressive: core.mood_aggressive_score,
      mood_relaxed: core.mood_relaxed_score,
      mood_sad: core.mood_sad_score,
      leading_silence_sec: core.leading_silence_seconds,
      trailing_silence_sec: core.trailing_silence_seconds,
      tempo_variability: core.tempo_variability,
    };
  } else {
    const raw = track.metadata?.sonara_features;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    record = raw as Record<string, unknown>;
    timeSignatureConfidence = sonaraNumericPayloadValue(record.time_signature_confidence);
  }

  return sonaraPlaylistFeatureGroups
    .map((group) => ({
      title: group.title,
      features: group.keys
        .map((key) => {
          let value: unknown;
          let isUnavailable = false;
          
          if ("sonara_core" in track) {
            value = record[key];
            if (value == null) isUnavailable = true;
          } else {
            const payload = record[key];
            const featureRecord = payload && typeof payload === "object" && !Array.isArray(payload) ? payload as Record<string, unknown> : {};
            if (featureRecord.type === "unavailable" || (featureRecord.value == null && featureRecord.summary == null)) {
              isUnavailable = true;
            } else {
              value = featureRecord;
            }
          }

          if (!sonaraPlaylistFeatureKeys.has(key) || isUnavailable) return null;

          let formattedValue = "-";
          if ("sonara_core" in track) {
            formattedValue = formatSonaraValueV7(value, key);
          } else {
            formattedValue = key === "time_signature" && timeSignatureConfidence === 0
              ? "Unknown"
              : formatSonaraValue(value as Record<string, unknown>, key);
          }

          return {
            key,
            label: sonaraFeatureLabels[key] || formatFeatureLabel(key),
            value: formattedValue,
            description: sonaraFeatureDescriptions[key] || ""
          };
        })
        .filter((feature) => feature != null)
    }))
    .filter((group) => group.features.length);
}

function sonaraNumericPayloadValue(payload: unknown) {
  if (typeof payload === "number") return payload;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return undefined;
  const value = (payload as Record<string, unknown>).value;
  return typeof value === "number" ? value : undefined;
}

function formatFeatureLabel(key: string) {
  return key
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

const sonaraSecondKeys = new Set([
  "grid_offset_sec",
  "intro_end_sec",
  "outro_start_sec",
  "energy_curve_hop_sec",
  "leading_silence_sec",
  "trailing_silence_sec"
]);

function formatSonaraValueV7(value: unknown, key?: string) {
  if ((key === "bpm" || key === "bpm_raw") && typeof value === "number") return value.toFixed(2);
  if (key === "bpm_candidates" && Array.isArray(value)) return formatBpmCandidatesV7(value);
  if (key === "key_candidates" && Array.isArray(value)) return formatKeyCandidatesV7(value);
  if (key === "duration_sec" && typeof value === "number") return formatPlayerDuration(value);
  
  if (key === "energy_curve_summary" && value && typeof value === "object") {
    const summary = value as Record<string, number>;
    return `mean ${formatNumber(summary.mean)}`;
  }

  if (typeof value === "number") {
    if (key === "onset_density") return `${formatNumber(value)}/sec`;
    if (key === "chord_change_rate") return `${formatNumber(value)}/sec`;
    if (key === "loudness_lufs") return `${value.toFixed(2)} LUFS`;
    if (key === "dynamic_range_db") return `${value.toFixed(2)} dB`;
    if (key === "loudness_range_lu") return `${value.toFixed(2)} LU`;
    if (key === "true_peak_db") return `${value.toFixed(2)} dBTP`;
    if (key === "replaygain_db") return `${value.toFixed(2)} dB`;
    if (key === "loudness_momentary_max_db") return `${value.toFixed(2)} LUFS`;
    if (key && sonaraSecondKeys.has(key)) return `${formatNumber(value)} s`;
    return formatNumber(value);
  }
  if (Array.isArray(value)) return `${value.length} values`;
  if (value == null) return "-";
  return String(value);
}

function formatSonaraValue(record: Record<string, unknown>, key?: string) {
  const value = record.value;
  if (record.type === "unavailable") return "-";
  if ((key === "bpm" || key === "bpm_raw") && typeof value === "number") return value.toFixed(2);
  if (key === "bpm_candidates" && Array.isArray(value)) return formatBpmCandidates(value);
  if (key === "key_candidates" && Array.isArray(value)) return formatKeyCandidates(value);
  if (record.type === "duration" && typeof value === "number") return formatPlayerDuration(value);
  if (record.type === "ndarray" || record.storage) {
    const compactValues = compactNumericValues(value);
    if (compactValues) return compactValues.map(formatNumber).join(", ");
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
    if (key === "loudness_range_lu") return `${value.toFixed(2)} LU`;
    if (key === "true_peak_db") return `${value.toFixed(2)} dBTP`;
    if (key === "replaygain_db") return `${value.toFixed(2)} dB`;
    if (key === "loudness_momentary_max_db") return `${value.toFixed(2)} LUFS`;
    if (key && sonaraSecondKeys.has(key)) return `${formatNumber(value)} s`;
    return formatNumber(value);
  }
  if (Array.isArray(value)) return `${value.length} values`;
  if (value == null) return "-";
  return String(value);
}

function compactNumericValues(value: unknown) {
  const flattened: number[] = [];
  function append(item: unknown): boolean {
    if (typeof item === "number" && Number.isFinite(item)) {
      flattened.push(item);
      return flattened.length <= 64;
    }
    if (!Array.isArray(item)) return false;
    return item.every(append);
  }
  return append(value) && flattened.length ? flattened : null;
}

function formatBpmCandidates(value: unknown[]) {
  const candidates = value.map((item) => {
    if (!Array.isArray(item) || typeof item[0] !== "number") return null;
    const bpm = item[0].toFixed(2);
    return typeof item[1] === "number" ? `${bpm} (${formatNumber(item[1])})` : bpm;
  }).filter((candidate): candidate is string => candidate != null);
  return candidates.length ? candidates.join(", ") : `${value.length} values`;
}

function formatBpmCandidatesV7(value: unknown[]) {
  const candidates = value.map((item) => {
    if (!item || typeof item !== "object") return null;
    const record = item as Record<string, unknown>;
    if (typeof record.bpm !== "number") return null;
    const bpm = record.bpm.toFixed(2);
    return typeof record.score === "number" ? `${bpm} (${formatNumber(record.score)})` : bpm;
  }).filter((candidate): candidate is string => candidate != null);
  return candidates.length ? candidates.join(", ") : `${value.length} values`;
}

function formatKeyCandidates(value: unknown[]) {
  const codes = value
    .map((item) => (Array.isArray(item) ? item[1] ?? item[0] : item))
    .filter((code): code is string | number => code != null)
    .map((code) => String(code));
  return codes.length ? codes.join(", ") : `${value.length} values`;
}

function formatKeyCandidatesV7(value: unknown[]) {
  const codes = value
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const record = item as Record<string, unknown>;
      return record.camelot || record.key;
    })
    .filter((code): code is string | number => code != null)
    .map((code) => String(code));
  return codes.length ? codes.join(", ") : `${value.length} values`;
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
