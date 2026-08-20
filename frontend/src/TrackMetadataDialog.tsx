import { AudioWaveform, Check, Copy, FolderOpen, Pause, Play, Trash2, X } from "lucide-react";
import { Fragment, useState } from "react";
import type { SonaraCore, TrackDetail } from "./api";
import { api } from "./apiClient";
import { formatMaestGenreLabel, hasMaestSyncopatedRhythm, SYNCOPATED_RHYTHM_LABEL } from "./syncopatedRhythm";
import { displayTrack } from "./trackDisplay";

type MetadataEntry = readonly [label: string, value: string];
type CoreFeatureKey = keyof SonaraCore;
type CoreFeature = {
  key: CoreFeatureKey;
  label: string;
  description: string;
};
type CoreFeatureGroup = {
  title: string;
  features: CoreFeature[];
};

const twoDecimalSonaraScoreKeys = new Set<keyof SonaraCore>([
  "bpm_confidence",
  "key_confidence",
  "energy_score",
  "danceability_score",
  "valence_score",
  "acousticness_score",
]);

const sonaraCoreFeatureGroups: CoreFeatureGroup[] = [
  {
    title: "Tempo",
    features: [
      feature("detected_bpm", "BPM", "Detected tempo after applying the active SONARA BPM range."),
      feature("bpm_confidence", "BPM confidence", "Confidence of the detected tempo."),
      feature("bpm_candidates", "BPM candidates", "Ranked tempo candidates returned by SONARA."),
      feature("onset_density_per_second", "Onset density", "Detected onsets per second."),
      feature("beat_count", "Beat count", "Number of detected beats."),
      feature("tempo_variability", "Tempo variability", "Within-track tempo variation retained by SONARA."),
      feature("beat_grid_offset_seconds", "Beat-grid offset", "Offset of the detected beat grid from the beginning of the audio."),
      feature("beat_grid_stability", "Beat-grid stability", "Stability of the detected beat grid."),
      feature("analyzed_duration_seconds", "Duration", "Duration represented by the current SONARA Core analysis."),
    ],
  },
  {
    title: "Tonal",
    features: [
      feature("detected_key_name", "Key", "Detected musical key with SONARA Camelot notation."),
      feature("key_confidence", "Key confidence", "Confidence of the detected key."),
      feature("key_candidates", "Key candidates", "Ranked key candidates returned by SONARA."),
      feature("predominant_chord", "Predominant chord", "Most frequent detected chord."),
      feature("chord_changes_per_second", "Chord changes", "Detected chord changes per second."),
      feature("dissonance_score", "Dissonance", "SONARA dissonance score."),
    ],
  },
  {
    title: "Loudness",
    features: [
      feature("integrated_loudness_lufs", "Integrated loudness", "Overall programme loudness across the track in LUFS. Use it to compare perceived level between tracks; less-negative values are louder."),
      feature("loudness_range_lu", "Loudness range", "Variation of loudness across the track in LU. Higher values usually mean a less even, more dynamic loudness profile."),
      feature("dynamic_range_db", "Dynamic range", "SONARA estimate of the spread between quieter and louder material in dB. Use it as a relative signal, not a mastering-quality grade."),
      feature("max_momentary_loudness_lufs", "Momentary max", "Highest short-term loudness in LUFS. It represents the loudest sustained moment, not an instantaneous sample peak."),
      feature("true_peak_dbtp", "True peak", "Highest reconstructed sample peak in dBTP. Values near 0 dBTP leave less headroom and can matter for limiting or lossy encoding."),
      feature("rms_mean", "RMS", "Average RMS energy across the track. It is a simple signal-strength measure and should be read alongside integrated loudness."),
      feature("rms_max", "RMS max", "Highest RMS energy observed during analysis. It indicates the densest sustained section of the track."),
      feature("replay_gain_db", "ReplayGain", "Suggested gain adjustment in dB for consistent playback level. Negative values reduce a louder track; positive values raise a quieter one."),
    ],
  },
  {
    title: "Structure",
    features: [
      feature("intro_end_seconds", "Intro end", "Estimated end of the intro."),
      feature("outro_start_seconds", "Outro start", "Estimated beginning of the outro."),
      feature("leading_silence_seconds", "Leading silence", "Silence before the first detected sound."),
      feature("trailing_silence_seconds", "Trailing silence", "Silence after the last detected sound."),
      feature("energy_curve_hop_seconds", "Energy-curve hop", "Spacing between stored energy-curve samples."),
      feature("energy_curve_sample_count", "Energy-curve samples", "Number of stored energy-curve samples."),
      feature("energy_curve_min", "Energy-curve min", "Minimum stored energy-curve value."),
      feature("energy_curve_max", "Energy-curve max", "Maximum stored energy-curve value."),
      feature("energy_curve_mean", "Energy-curve mean", "Mean stored energy-curve value."),
      feature("energy_curve_stddev", "Energy-curve stddev", "Standard deviation of the stored energy curve."),
    ],
  },
  {
    title: "Spectral",
    features: [
      feature("spectral_centroid_hz", "Spectral centroid", "Center of mass of the spectrum in hertz."),
      feature("spectral_bandwidth_hz", "Spectral bandwidth", "Frequency spread in hertz."),
      feature("spectral_rolloff_hz", "Spectral rolloff", "Rolloff frequency in hertz."),
      feature("spectral_flatness", "Spectral flatness", "Tonal-to-noise-like spectral measure."),
      feature("zero_crossing_rate", "Zero-crossing rate", "Rate of waveform sign changes."),
    ],
  },
  {
    title: "Perceptual",
    features: [
      feature("energy_level", "Level", "SONARA energy tier."),
      feature("energy_score", "Energy", "SONARA energy ranking signal."),
      feature("danceability_score", "Danceability", "SONARA danceability ranking signal."),
      feature("valence_score", "Valence", "SONARA valence ranking signal."),
      feature("acousticness_score", "Acousticness", "SONARA acousticness ranking signal."),
    ],
  },
  {
    title: "Mood",
    features: [
      feature("mood_happy_score", "Happy", "SONARA happy-mood ranking signal."),
      feature("mood_aggressive_score", "Aggressive", "SONARA aggressive-mood heuristic; distinct from the dedicated Aggression model."),
      feature("mood_relaxed_score", "Relaxed", "SONARA relaxed-mood ranking signal."),
      feature("mood_sad_score", "Sad", "SONARA sad-mood ranking signal."),
    ],
  },
  {
    title: "Aggression",
    features: [
      feature("aggression_score", "Score", "Dedicated SONARA aggression perceptual rank; not the aggressive-mood heuristic."),
      feature("aggression_confidence", "Evidence support", "Supported musical evidence for the aggression analysis, not rank certainty."),
      feature("aggression_forcefulness", "Forcefulness", "SONARA forcefulness component of the aggression analysis."),
      feature("aggression_harshness", "Harshness", "SONARA harshness component of the aggression analysis."),
      feature("aggression_tension", "Tension", "SONARA tension component of the aggression analysis."),
      feature("aggression_rhythm", "Rhythm", "SONARA rhythmic component of the aggression analysis."),
    ],
  },
  {
    title: "Vocalness",
    features: [
      feature("vocal_probability", "Vocal probability", "Probability returned by the bundled SONARA vocal model."),
    ],
  },
  {
    title: "Vector summaries",
    features: [
      feature("vector_summaries", "Vectors", "Compact summaries for stored SONARA Core vectors."),
    ],
  },
];

function feature(key: keyof SonaraCore, label: string, description: string): CoreFeature {
  return { key, label, description };
}

export function metadataDialogModel(track: TrackDetail) {
  const genres = track.maest?.genres ?? [];
  return {
    trackDetailsEntries: readablePrimaryTrackInfo(track),
    tagEntries: readableTagInfo(track),
    audioEntries: readableAudioData(track),
    scanEntries: readableScanDetails(track),
    sonaraAnalysisEntries: readableSonaraAnalysisDetails(track),
    sonaraProvenanceEntries: readableSonaraProvenance(track.sonara_core),
    coreGroups: readableSonaraCoreGroups(track.sonara_core),
    classifierScores: readableClassifierScores(track),
    classifierAnalysisEntries: readableClassifierAnalysisDetails(track),
    embeddings: readableEmbeddings(track),
    genres,
    maestAnalyzed: track.maest !== null,
    syncopatedRhythm: hasMaestSyncopatedRhythm(track),
  };
}

export function TrackMetadataDialog({
  track,
  onClose,
  onDelete,
  onPreview,
  playingTrackId,
}: {
  track: TrackDetail;
  onClose: () => void;
  onDelete: (track: TrackDetail) => void;
  onPreview: (track: TrackDetail) => void;
  playingTrackId: number | null;
}) {
  const [filePathCopied, setFilePathCopied] = useState(false);
  const [fileNameCopied, setFileNameCopied] = useState(false);
  const [revealError, setRevealError] = useState<string | null>(null);
  const view = metadataDialogModel(track);
  const sonaraFeatureCount = view.coreGroups.reduce((total, group) => total + group.features.length, 0);
  const previewActive = playingTrackId === track.track_id;

  async function copyFilePath() {
    const copied = await copyTextToClipboard(track.file_path);
    if (!copied) return;
    setFilePathCopied(true);
    window.setTimeout(() => setFilePathCopied(false), 1400);
  }

  async function copyFileName() {
    const copied = await copyTextToClipboard(displayTrack(track));
    if (!copied) return;
    setFileNameCopied(true);
    window.setTimeout(() => setFileNameCopied(false), 1400);
  }

  async function revealFileLocation() {
    try {
      await api.revealTrackFile(track.track_id);
      setRevealError(null);
    } catch {
      setRevealError("Could not open containing folder");
    }
  }

  return (
    <div className="metadata-dialog-backdrop" role="presentation">
      <section
        className="metadata-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Теги и анализ трека"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="metadata-dialog-close-actions">
          <button
            className="icon-button close-metadata-dialog-button"
            title="Закрыть"
            aria-label="Закрыть"
            onClick={onClose}
            type="button"
          >
            <X size={15} />
          </button>
        </div>
        <div className="metadata-dialog-title">
          <h2 className="metadata-track-title">
            <span>{displayTrack(track)}</span>
            <button
              className="icon-button metadata-preview-button"
              title={previewActive ? "Pause preview" : "Preview"}
              aria-label={`${previewActive ? "Pause" : "Preview"} ${displayTrack(track)}`}
              onClick={() => onPreview(track)}
              type="button"
            >
              {previewActive ? <Pause size={16} /> : <Play size={16} />}
            </button>
            <button
              className="icon-button intent-remove metadata-delete-button"
              title="Удалить из базы"
              aria-label={`Удалить ${displayTrack(track)} из базы`}
              onClick={() => onDelete(track)}
              type="button"
            >
              <Trash2 size={16} />
            </button>
          </h2>
        </div>

        <div className="maest-genres-block">
          {view.maestAnalyzed ? (
            <div className="maest-genre-list" title="MAEST-detected genres">
              {view.genres.map((genre) => (
                <span className="maest-genre-pill" key={`${genre.rank}:${genre.genre_name}`}>
                  {formatMaestGenreLabel(genre.genre_name)} <b>{formatConfidence(genre.score)}</b>
                </span>
              ))}
              {view.syncopatedRhythm ? (
                <span
                  aria-label={SYNCOPATED_RHYTHM_LABEL}
                  className="maest-syncopated-rhythm-indicator"
                  role="img"
                  title="MAEST detected syncopated rhythm"
                >
                  <AudioWaveform size={13} />
                </span>
              ) : null}
            </div>
          ) : (
            <span className="maest-genres-empty">MAEST analysis has not been run for this track.</span>
          )}
        </div>

        <div className="metadata-details-block">
          <strong>Track Details</strong>
          <dl className="metadata-grid metadata-details-grid">
            {view.trackDetailsEntries.map(([label, value]) => (
              <Fragment key={label}>
                <dt>{label}</dt>
                {label === "File Path" || label === "File Name" ? (
                  <dd className="metadata-file-value-row">
                    <span className="metadata-file-value">{value}</span>
                    <button
                      className="icon-button metadata-copy-value-button"
                      title={
                        label === "File Path"
                          ? filePathCopied ? "Copied" : "Copy file path"
                          : fileNameCopied ? "Copied" : "Copy file name"
                      }
                      aria-label={
                        label === "File Path"
                          ? `Copy file path: ${track.file_path}`
                          : `Copy file name: ${displayTrack(track)}`
                      }
                      onClick={() => void (label === "File Path" ? copyFilePath() : copyFileName())}
                      type="button"
                    >
                      {(label === "File Path" ? filePathCopied : fileNameCopied) ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                    {label === "File Path" ? (
                      <button
                        className="icon-button metadata-copy-value-button"
                        title={revealError ?? "Open containing folder"}
                        aria-label={`Open containing folder: ${track.file_path}`}
                        onClick={() => void revealFileLocation()}
                        type="button"
                      >
                        <FolderOpen size={14} />
                      </button>
                    ) : null}
                  </dd>
                ) : (
                  <dd>{value}</dd>
                )}
              </Fragment>
            ))}
          </dl>
          <span className="metadata-section-title">Tags</span>
          <dl className="metadata-grid metadata-details-grid">
            {view.tagEntries.map(([label, value]) => (
              <Fragment key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </Fragment>
            ))}
          </dl>
        </div>

        <details className="metadata-data-details">
          <summary>Data</summary>
          <dl className="metadata-grid metadata-details-grid">
            {view.audioEntries.map(([label, value]) => (
              <Fragment key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </Fragment>
            ))}
          </dl>
        </details>

        <div className="sonara-block">
          <strong>SONARA features</strong>
          {sonaraFeatureCount ? (
            <div className="sonara-feature-groups">
              {view.coreGroups.map((group) => (
                <div className="sonara-feature-group" key={group.title}>
                  <span className="sonara-feature-group-title">{group.title}</span>
                  <dl className="metadata-grid sonara-feature-grid">
                    {group.features.map((coreFeature) => (
                      <Fragment key={coreFeature.key}>
                        <dt title={coreFeature.description}>{coreFeature.label}</dt>
                        <dd title={coreFeature.description}>{coreFeature.value}</dd>
                      </Fragment>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          ) : (
            <span className="metadata-empty-state">Core данные ещё не рассчитаны</span>
          )}
          {view.sonaraProvenanceEntries.length ? (
            <dl className="metadata-grid sonara-feature-grid">
              {view.sonaraProvenanceEntries.map(([label, value]) => (
                <Fragment key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </Fragment>
              ))}
            </dl>
          ) : null}
        </div>

        <div className="metadata-classifier-block">
          <strong>Classifier scores</strong>
          {view.classifierScores.length ? (
            <dl className="metadata-grid metadata-analysis-grid">
              {view.classifierScores.map((score) => (
                <Fragment key={score.key}><dt>{score.label}</dt><dd>{score.value}</dd></Fragment>
              ))}
            </dl>
          ) : (
            <span className="metadata-empty-state">Classifier scores ещё не рассчитаны</span>
          )}
        </div>

        <details className="metadata-scan-analyses-details">
          <summary>Scan analyses details</summary>
          <section className="metadata-scan-analyses-section">
            <span className="metadata-scan-analyses-section-title">File scan (Mutagen)</span>
            <dl className="metadata-grid metadata-details-grid">
              {view.scanEntries.map(([label, value]) => (
                <Fragment key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </Fragment>
              ))}
            </dl>
          </section>
          <section className="metadata-scan-analyses-section">
            <span className="metadata-scan-analyses-section-title">SONARA</span>
            {view.sonaraAnalysisEntries.length ? (
              <dl className="metadata-grid metadata-details-grid">
                {view.sonaraAnalysisEntries.map(([label, value]) => (
                  <Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl>
            ) : (
            <span className="metadata-empty-state">SONARA features ещё не рассчитаны</span>
            )}
          </section>
          <section className="metadata-scan-analyses-section">
            <span className="metadata-scan-analyses-section-title">Embedding analyses</span>
          {view.embeddings.length ? (
            <dl className="metadata-grid metadata-analysis-grid">
              {view.embeddings.map((embedding) => (
                <Fragment key={embedding.key}>
                  <dt>{embedding.label}</dt>
                  <dd>{embedding.value}</dd>
                </Fragment>
              ))}
            </dl>
          ) : (
            <span className="metadata-empty-state">Embedding-анализы ещё не рассчитаны</span>
          )}
          </section>
          <section className="metadata-scan-analyses-section">
            <span className="metadata-scan-analyses-section-title">Classifier analyses</span>
            {view.classifierAnalysisEntries.length ? (
              <dl className="metadata-grid metadata-details-grid">
                {view.classifierAnalysisEntries.map(([label, value]) => (
                  <Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl>
            ) : (
              <span className="metadata-empty-state">Classifier analyses ещё не рассчитаны</span>
            )}
          </section>
        </details>

      </section>
    </div>
  );
}

function readablePrimaryTrackInfo(track: TrackDetail): MetadataEntry[] {
  return [
    ["File Name", displayTrack(track)],
    ["File Path", track.file_path],
    ["File Size", formatFileSizeMb(track.file.file_size_bytes)],
  ];
}

function readableTagInfo(track: TrackDetail): MetadataEntry[] {
  const tags = track.file_tags;
  const duration = track.file.audio_duration_seconds ?? track.audio_duration_seconds;
  return [
    ["Title", formatOptionalText(tags?.title ?? track.title)],
    ["Artist", formatOptionalText(tags?.artist ?? track.artist)],
    ["Album", formatOptionalText(tags?.album ?? track.album)],
    ["Year", formatOptionalNumber(tags?.year ?? null)],
    ["Country", formatOptionalText(tags?.country ?? null)],
    ["Label", formatOptionalText(tags?.label ?? null)],
    ["Genre", tags?.genres.length ? tags.genres.join(", ") : "-"],
    ["Duration", formatDuration(duration)],
    ["BPM", formatOptionalNumber(tags?.tag_bpm ?? track.tag_bpm)],
    ["Key", formatOptionalText(tags?.tag_key ?? track.tag_key)],
    ["Comment", formatOptionalText(tags?.comment ?? null)],
  ];
}

function readableAudioData(track: TrackDetail): MetadataEntry[] {
  const duration = track.file.audio_duration_seconds ?? track.audio_duration_seconds;
  return [
    ["Audio Format", formatOptionalText(track.file.audio_format)],
    ["Audio Length", formatAudioLength(duration)],
    ["Sample Rate", formatFrequency(track.file.sample_rate_hz)],
    ["Bit Rate", formatBitRate(track.file.bit_rate_bps)],
    ["Bit Depth", formatBitDepth(track.file.bit_depth)],
    ["Channels", formatChannelCount(track.file.channel_count)],
  ];
}

function readableScanDetails(track: TrackDetail): MetadataEntry[] {
  return [
    ["Last Scanned", formatTimestamp(track.file.last_scanned_at)],
    ["Missing Since", formatTimestamp(track.file.missing_since)],
  ];
}

function readableSonaraAnalysisDetails(track: TrackDetail): MetadataEntry[] {
  if (!track.sonara_core) return [];
  return [["Analyzed at", formatTimestamp(track.sonara_core.analyzed_at)]];
}

function readableSonaraProvenance(core: SonaraCore | null): MetadataEntry[] {
  if (!core) return [];
  return [["Analysis schema", `v${core.analysis_schema_version}`]];
}

function readableSonaraCoreGroups(core: SonaraCore | null) {
  if (!core) return [];
  return sonaraCoreFeatureGroups
    .map((group) => ({
      title: group.title,
      features: group.features
        .map((descriptor) => {
          if (descriptor.key === "detected_key_name") {
            const value = formatDetectedKey(
              core.detected_key_name,
              core.detected_key_camelot,
            );
            return value ? { ...descriptor, value } : null;
          }
          const value = core[descriptor.key];
          if (value == null || (Array.isArray(value) && value.length === 0)) return null;
          if (descriptor.key === "bpm_candidates" && Array.isArray(value)) {
            return {
              ...descriptor,
              value: formatBpmCandidates(value, core.bpm_min, core.bpm_max),
            };
          }
          return {
            ...descriptor,
            value: formatSonaraCoreValue(descriptor.key, value),
          };
        })
        .filter((entry): entry is CoreFeature & { value: string } => entry != null),
    }))
    .filter((group) => group.features.length > 0);
}

function readableClassifierScores(track: TrackDetail) {
  return track.classifier_scores_detail.map((score) => ({
    key: score.classifier_key,
    label: readableClassifierName(score.classifier_key),
    value: [
      `${score.predicted_class} (${score.score_bucket})`,
      `score ${formatScore(score.score)}`,
    ].join(" · "),
  }));
}

function readableClassifierAnalysisDetails(track: TrackDetail): MetadataEntry[] {
  return track.classifier_scores_detail.map((score) => [
    readableClassifierName(score.classifier_key),
    formatTimestamp(score.analyzed_at),
  ]);
}

function readableEmbeddings(track: TrackDetail) {
  return track.embeddings.map((embedding) => ({
    key: embedding.analysis_family,
    label: embedding.analysis_family.toUpperCase(),
    value: [
      `${embedding.dim}D`,
      embedding.normalization,
      formatTimestamp(embedding.analyzed_at),
    ].filter((part): part is string => Boolean(part)).join(" · "),
  }));
}

function readableClassifierName(key: string) {
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatSonaraCoreValue(key: keyof SonaraCore, value: SonaraCore[keyof SonaraCore]) {
  if (key === "analyzed_at") return formatTimestamp(String(value));
  if (key === "key_candidates" && Array.isArray(value)) return formatKeyCandidates(value);
  if (key === "vector_summaries" && Array.isArray(value)) return formatVectorSummaries(value);
  if (Array.isArray(value)) return formatRecordList(value);
  if (typeof value === "number") {
    if (key === "detected_bpm") return value.toFixed(2);
    if (key === "beat_count" || key === "energy_curve_sample_count") {
      return formatInteger(value);
    }
    if (twoDecimalSonaraScoreKeys.has(key)) return value.toFixed(2);
    if (key === "onset_density_per_second" || key === "chord_changes_per_second") {
      return `${value.toFixed(2)}/s`;
    }
    if (key === "tempo_variability") return formatSmallPercentage(value);
    if (key === "beat_grid_offset_seconds") return formatShortDuration(value);
    if (key === "beat_grid_stability") return `${(value * 100).toFixed(1)}%`;
    if (key === "analyzed_duration_seconds") return formatClockPosition(value, 0);
    if (key === "energy_level") return `${formatInteger(value)}/10`;
    if (key === "vocal_probability") return formatProbability(value);
    if (key === "dissonance_score") return value.toFixed(3);
    if (
      key === "energy_curve_stddev"
      || key === "spectral_flatness"
      || key === "zero_crossing_rate"
    ) {
      return value.toFixed(4);
    }
    if (key === "spectral_centroid_hz" || key === "spectral_bandwidth_hz" || key === "spectral_rolloff_hz") {
      return `${formatInteger(value)} Hz`;
    }
    if (key === "integrated_loudness_lufs" || key === "max_momentary_loudness_lufs") {
      return `${value.toFixed(1)} LUFS`;
    }
    if (key === "dynamic_range_db") return `${value.toFixed(1)} dB`;
    if (key === "true_peak_dbtp") return `${formatSignedNumber(value, 2)} dBTP`;
    if (key === "replay_gain_db") return `${formatSignedNumber(value, 2)} dB`;
    if (key === "loudness_range_lu") return `${value.toFixed(1)} LU`;
    if (key === "intro_end_seconds" || key === "outro_start_seconds") {
      return formatClockPosition(value, 0);
    }
    if (key === "leading_silence_seconds" || key === "trailing_silence_seconds") {
      return `${value.toFixed(2)} s`;
    }
    if (key === "energy_curve_hop_seconds") return `${Math.round(value * 1000)} ms`;
    return formatNumber(value);
  }
  return String(value);
}

function formatDetectedKey(
  keyName: string | null,
  camelot: string | null,
): string {
  return [keyName, camelot]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(" · ");
}

function formatBpmCandidates(
  value: Record<string, unknown>[],
  bpmMin: number | null,
  bpmMax: number | null,
) {
  const range = bpmMin != null && bpmMax != null
    ? `(analysis range ${formatOptionalNumber(bpmMin)}–${formatOptionalNumber(bpmMax)} BPM) `
    : "";
  return range + value.map((candidate, index) => {
    const rank = candidateRank(candidate, index);
    const bpm = typeof candidate.bpm === "number"
      ? candidate.bpm.toFixed(2)
      : "-";
    const score = typeof candidate.score === "number"
      ? ` (score ${candidate.score.toFixed(2)})`
      : "";
    return `#${rank} ${bpm}${score}`;
  }).join(" · ");
}

function formatKeyCandidates(value: Record<string, unknown>[]) {
  return value.map((candidate, index) => {
    const rank = candidateRank(candidate, index);
    const camelot = typeof candidate.camelot === "string" ? candidate.camelot : "";
    const keyName = typeof candidate.key_name === "string" ? candidate.key_name : "";
    const name = [camelot, keyName].filter(Boolean).join(" · ") || "-";
    const score = typeof candidate.score === "number"
      ? ` (${candidate.score.toFixed(2)})`
      : "";
    return `#${rank} ${name}${score}`;
  }).join(" | ");
}

function candidateRank(candidate: Record<string, unknown>, index: number) {
  return typeof candidate.rank === "number" && Number.isInteger(candidate.rank)
    ? candidate.rank
    : index + 1;
}

function formatVectorSummaries(value: Record<string, unknown>[]) {
  const labels: Record<string, string> = {
    mfcc_mean: "MFCC",
    chroma_mean: "Chroma",
    spectral_contrast_mean: "Spectral Contrast",
  };
  return value.map((summary) => {
    const vectorType = typeof summary.vector_type === "string"
      ? summary.vector_type
      : "";
    const label = labels[vectorType] || vectorType || "Vector";
    const dim = typeof summary.dim === "number" ? ` [${summary.dim}]` : "";
    return `${label}${dim}`;
  }).join(" · ");
}

function formatRecordList(value: Record<string, unknown>[]) {
  const visible = value.slice(0, 4).map((record) => {
    const entries = Object.entries(record)
      .filter(([, item]) => typeof item === "string" || typeof item === "number" || typeof item === "boolean")
      .slice(0, 4)
      .map(([key, item]) => `${key}=${String(item)}`);
    return entries.length ? entries.join(", ") : "record";
  });
  const remainder = value.length - visible.length;
  return `${visible.join(" | ")}${remainder > 0 ? ` | +${remainder} more` : ""}`;
}

async function copyTextToClipboard(text: string) {
  try {
    if (window.navigator.clipboard?.writeText) {
      await window.navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the textarea fallback.
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

function formatScore(value: number) {
  return Number.isFinite(value) ? value.toFixed(6) : "-";
}

function formatNumber(value: number) {
  return value.toFixed(3);
}

function formatInteger(value: number) {
  return Math.round(value).toLocaleString("en-US");
}

function formatSmallPercentage(value: number) {
  if (value === 0) return "0%";
  if (value > 0 && value < 0.0001) return "<0.01%";
  return `${(value * 100).toFixed(2)}%`;
}

function formatProbability(value: number) {
  if (value === 0) return "0%";
  if (value === 1) return "100%";
  if (value > 0 && value < 0.0001) return "<0.01%";
  if (value < 1 && value > 0.9999) return ">99.99%";
  return `${(value * 100).toFixed(2)}%`;
}

function formatShortDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  return `${seconds.toFixed(2)} s`;
}

function formatClockPosition(seconds: number, decimalPlaces: number) {
  const scale = 10 ** decimalPlaces;
  const totalUnits = Math.round(Math.max(0, seconds) * scale);
  const wholeSeconds = Math.floor(totalUnits / scale);
  const fraction = totalUnits % scale;
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const rest = (wholeSeconds % 60).toString().padStart(2, "0");
  const fractionText = decimalPlaces > 0
    ? `.${fraction.toString().padStart(decimalPlaces, "0")}`
    : "";
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${rest}${fractionText}`;
  }
  return `${minutes}:${rest}${fractionText}`;
}

function formatSignedNumber(value: number, decimalPlaces: number) {
  const rounded = Number(value.toFixed(decimalPlaces));
  const sign = rounded > 0 ? "+" : rounded < 0 ? "-" : "";
  return `${sign}${Math.abs(rounded).toFixed(decimalPlaces)}`;
}

function formatDuration(seconds: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return "-";
  const rounded = Math.max(0, Math.round(seconds));
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const rest = (rounded % 60).toString().padStart(2, "0");
  if (hours > 0) return `${hours}:${minutes.toString().padStart(2, "0")}:${rest}`;
  return `${minutes}:${rest}`;
}

function formatAudioLength(seconds: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return "-";
  return seconds.toFixed(2);
}

function formatTimestamp(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const milliseconds = date.getMilliseconds();
  const hasFractionalSeconds = /\.(\d+)/.test(value) && milliseconds !== 0;
  return [
    `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}.${date.getFullYear()}`,
    `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}${hasFractionalSeconds ? `.${pad3(milliseconds)}` : ""}`,
  ].join(" ");
}

function pad2(value: number) {
  return value.toString().padStart(2, "0");
}

function pad3(value: number) {
  return value.toString().padStart(3, "0");
}

function formatFrequency(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("en-US")} Hz`;
}

function formatBitRate(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${Math.round(value / 1000)} kbps`;
}

function formatBitDepth(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${value}-bit`;
}

function formatChannelCount(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "-";
  if (value === 1) return "Mono (1)";
  if (value === 2) return "Stereo (2)";
  return `${value} channels`;
}

function formatFileSizeMb(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "-";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatOptionalNumber(value: number | null) {
  return value == null || !Number.isFinite(value) ? "-" : String(value);
}

function formatOptionalText(value: string | null) {
  return value || "-";
}

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}
