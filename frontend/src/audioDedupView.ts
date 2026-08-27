import type {
  AudioDedupDeleteRequest,
  AudioDedupDeletionMode,
  AudioDedupFile,
  AudioDedupGroup,
  AudioDedupSearchMode
} from "./api";

export const applyDeleteConfirmation = "APPLY DELETE";

/** Selected files to delete, keyed by group so an off-page choice survives paging. */
export type DedupSelection = Record<number, number[]>;

/**
 * Blocked reasons that only say the embedding evidence was not loaded.
 *
 * Fingerprint mode never loads embeddings, so these describe the mode rather
 * than the pair. Showing them next to a 1.000 fingerprint match reads as doubt
 * about the match, which is the opposite of what the report means.
 */
const embeddingAbsencePatterns = [
  /source disabled$/i,
  /^missing (mert|maest|muq|clap) embedding$/i,
  /^missing content similarity$/i,
  /^content similarity below threshold$/i,
  /weight is not positive$/i
];

function isEmbeddingAbsence(reason: string) {
  return embeddingAbsencePatterns.some((pattern) => pattern.test(reason));
}

/**
 * Russian wording for the report's own English sentences.
 *
 * The JSON, XLSX and log artifacts stay English because they are the record the
 * CLI writes and reads; only the screen is translated. An unrecognised sentence
 * is passed through untouched rather than dropped: showing the original beats
 * hiding evidence nobody translated yet.
 */
const reasonTranslations: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [/^Highest keeper ranking inside this duplicate group$/i, () => "Лучший ранг для сохранения в группе"],
  [
    /^Best or tied-best audio format rank in group: (\d+)$/i,
    (m) => `Лучший в группе ранг формата: ${m[1]}`
  ],
  [
    /^Best or tied-best size-per-second quality proxy: ([\d.]+)$/i,
    (m) => `Лучшее в группе соотношение размера к длительности: ≈${Math.round((Number(m[1]) * 8) / 1000)} kbps`
  ],
  [
    /^Best or tied-best metadata completeness: (\d+) fields?$/i,
    (m) => `Лучшая в группе полнота тегов: ${m[1]}`
  ],
  [
    /^Full-band spectrum while (\d+) duplicate cop(?:y|ies) look transcoded$/i,
    (m) => `Полный спектр, тогда как копий с признаками фейк-битрейта: ${m[1]}`
  ],
  [
    /^SONARA fingerprint-only candidate: exact fingerprint match ([\d.]+) is strong duplicate evidence, but fingerprint evidence alone never authorizes automatic deletion$/i,
    (m) => `Точный матч отпечатков ${m[1]} — сильное доказательство дубликата, но одного отпечатка для автоудаления недостаточно`
  ],
  [
    /^SONARA fingerprint-only candidate requires manual review$/i,
    () => "Кандидат найден только по отпечатку — нужна ручная проверка"
  ],
  [/^ambiguous chain: not every candidate has a direct high-confidence match to keeper$/i, () => "Неоднозначная цепочка: не у каждой копии есть прямое уверенное совпадение с сохраняемой"],
  [/^ambiguous chain$/i, () => "Неоднозначная цепочка совпадений"],
  [/^weak direct keeper match$/i, () => "Слабое прямое совпадение с сохраняемой копией"],
  [/^every remaining copy is a suspected transcode; verify spectra by ear$/i, () => "Все оставшиеся копии похожи на фейк-битрейт — сверьте спектры на слух"],
  [/^duration mismatch$/i, () => "Длительности расходятся сильнее допуска"],
  [/^missing duration$/i, () => "Нет длительности"],
  [/^missing content similarity$/i, () => "Нет оценки схожести содержимого"],
  [/^content similarity below threshold$/i, () => "Схожесть содержимого ниже порога"],
  [/^(\w+) source disabled$/i, (m) => `Источник ${m[1].toUpperCase()} выключен`],
  [/^missing (\w+) embedding$/i, (m) => `Нет эмбеддинга ${m[1].toUpperCase()}`],
  [/^(\w+) weight is not positive$/i, (m) => `Вес ${m[1].toUpperCase()} не положительный`],
  [
    /^MERT\+MAEST corroboration below delete safety threshold \(([^)]+)\)$/i,
    (m) => `Подтверждение MERT+MAEST ниже порога безопасного удаления (${m[1]})`
  ]
];

export function translateReason(reason: string) {
  for (const [pattern, render] of reasonTranslations) {
    const match = reason.match(pattern);
    if (match) return render(match);
  }
  return reason;
}

/**
 * Why this copy is a candidate and what still has to be decided by hand.
 *
 * "Needs manual review" on its own said nothing: not what matched, not how
 * strongly, not why the tool refuses to act. The basis is the exact fingerprint
 * score, so the line states it.
 */
export function copyStatusLine(
  file: AudioDedupFile,
  group: AudioDedupGroup,
  searchMode: AudioDedupSearchMode | ""
): string | null {
  if (file.role === "keeper") return null;
  if (file.safe_to_delete) {
    return "MERT и MAEST подтвердили совпадение — копию можно удалять автоматически.";
  }
  const fingerprint = group.fingerprint_similarity;
  if (fingerprint !== null) {
    const match =
      fingerprint >= 0.9
        ? `Отпечатки совпали почти полностью (${formatSimilarity(fingerprint)})`
        : `Отпечатки совпали лишь частично (${formatSimilarity(fingerprint)}) — так бывает у винил-рипа против цифры и у ремастеров`;
    return `${match}. Одного отпечатка для автоудаления недостаточно — сравните копии на слух.`;
  }
  const blockers = copyDetailReasons(file, searchMode);
  if (blockers.length > 0) return `Автоудаление заблокировано: ${blockers[0]}.`;
  return "Требуется ручная проверка.";
}

/**
 * The report's own wording about this pair, deduplicated.
 *
 * `Manual review required: X.` and `X` are the same fact, so the prefix and the
 * trailing period are stripped before matching. In fingerprint mode the
 * embedding-absence lines are dropped rather than listed: no embedding was
 * loaded by design, so they describe the run, not this pair, and reading them as
 * findings is what made the card confusing.
 */
export function copyDetailReasons(
  file: AudioDedupFile,
  searchMode: AudioDedupSearchMode | ""
): string[] {
  const seen = new Set<string>();
  const reasons: string[] = [];
  for (const raw of [...file.reasons, ...file.blocked_reasons]) {
    const reason = raw.replace(/^manual review required:\s*/i, "").replace(/\.$/, "").trim();
    if (!reason) continue;
    if (searchMode === "fingerprint" && isEmbeddingAbsence(reason)) continue;
    const key = reason.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    reasons.push(translateReason(reason));
  }
  return reasons;
}

export function selectedTrackIds(selection: DedupSelection, groupId: number): number[] {
  return selection[groupId] ?? [];
}

export function isFileSelected(selection: DedupSelection, groupId: number, trackId: number) {
  return selectedTrackIds(selection, groupId).includes(trackId);
}

export function setGroupSelection(
  selection: DedupSelection,
  groupId: number,
  trackIds: number[]
): DedupSelection {
  const next = { ...selection };
  if (trackIds.length === 0) delete next[groupId];
  else next[groupId] = [...new Set(trackIds)].sort((left, right) => left - right);
  return next;
}

export function toggleFileSelection(
  selection: DedupSelection,
  groupId: number,
  trackId: number
): DedupSelection {
  const current = selectedTrackIds(selection, groupId);
  const next = current.includes(trackId)
    ? current.filter((item) => item !== trackId)
    : [...current, trackId];
  return setGroupSelection(selection, groupId, next);
}

export function selectionFileCount(selection: DedupSelection) {
  return Object.values(selection).reduce((total, ids) => total + ids.length, 0);
}

export function selectionGroupCount(selection: DedupSelection) {
  return Object.keys(selection).length;
}

/**
 * Whether a group keeps at least one copy under this selection.
 *
 * The server decides for real, including whether the surviving file is still on
 * disk. This mirrors the rule so an impossible choice is refused while the
 * reviewer is still making it.
 */
export function groupSurvivesSelection(group: AudioDedupGroup, trackIds: number[]) {
  return group.files.some((file) => !trackIds.includes(file.track_id));
}

/** The tool's own recommendation: keep the suggested keeper, drop the rest. */
export function suggestedGroupSelection(group: AudioDedupGroup): number[] {
  return group.files
    .filter((file) => file.role === "duplicate" && !file.stale)
    .map((file) => file.track_id);
}

export function selectionSummary(groups: AudioDedupGroup[], selection: DedupSelection) {
  const byId = new Map<number, AudioDedupFile>();
  for (const group of groups) for (const file of group.files) byId.set(file.track_id, file);
  let files = 0;
  let bytes = 0;
  let unknownSize = 0;
  for (const ids of Object.values(selection)) {
    for (const trackId of ids) {
      files += 1;
      const file = byId.get(trackId);
      if (file) bytes += file.size;
      else unknownSize += 1;
    }
  }
  return { files, bytes, unknownSize, groups: selectionGroupCount(selection) };
}

export function buildDeleteRequest(
  groups: AudioDedupGroup[],
  selection: DedupSelection,
  deletionMode: AudioDedupDeletionMode,
  confirmation: string
): { ok: true; payload: AudioDedupDeleteRequest } | { ok: false; error: string } {
  const selections = Object.entries(selection)
    .map(([groupId, trackIds]) => ({ group_id: Number(groupId), track_ids: trackIds }))
    .filter((entry) => entry.track_ids.length > 0)
    .sort((left, right) => left.group_id - right.group_id);
  if (selections.length === 0) return { ok: false, error: "Не выбрано ни одного файла" };
  if (confirmation !== applyDeleteConfirmation) {
    return { ok: false, error: `Для удаления введите "${applyDeleteConfirmation}"` };
  }
  const loaded = new Map(groups.map((group) => [group.group_id, group]));
  for (const entry of selections) {
    const group = loaded.get(entry.group_id);
    if (group && !groupSurvivesSelection(group, entry.track_ids)) {
      return {
        ok: false,
        error: `Группа ${entry.group_id}: нельзя удалить все копии, оставьте хотя бы одну`
      };
    }
  }
  return { ok: true, payload: { selections, deletion_mode: deletionMode, confirmation } };
}

export function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatSeconds(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

export function formatSimilarity(score: number | null) {
  if (score === null || !Number.isFinite(score)) return "—";
  return score.toFixed(3);
}

export function formatCutoff(hz: number | null) {
  if (hz === null || !Number.isFinite(hz)) return "—";
  return `${(hz / 1000).toFixed(1)} кГц`;
}

const losslessFormats = new Set([
  "FLAC",
  "WAV",
  "WAVE",
  "AIF",
  "AIFF",
  "AIFC",
  "ALAC",
  "APE",
  "WV",
  "TAK",
  "TTA",
  "DFF",
  "DSF"
]);

export function isLosslessFormat(audioFormat: string) {
  return losslessFormats.has(audioFormat.toUpperCase());
}

/**
 * The bitrate the file declares.
 *
 * Reports written before the stored bitrate was recorded fall back to size over
 * duration, marked approximate: that average also counts container overhead and,
 * for a variable-bitrate file, is not what the encoder was asked for.
 */
export function fileBitrateLabel(file: AudioDedupFile) {
  if (file.bit_rate_bps !== null && file.bit_rate_bps > 0) {
    return `${Math.round(file.bit_rate_bps / 1000)} kbps`;
  }
  if (file.size_per_second !== null && file.size_per_second > 0) {
    return `≈${Math.round((file.size_per_second * 8) / 1000)} kbps`;
  }
  return null;
}

/** Sample rate and bit depth, which is what resolution means for lossless audio. */
export function fileResolutionLabel(file: AudioDedupFile) {
  const parts: string[] = [];
  if (file.sample_rate_hz !== null && file.sample_rate_hz > 0) {
    parts.push(`${(file.sample_rate_hz / 1000).toFixed(1)} кГц`);
  }
  if (file.bit_depth !== null && file.bit_depth > 0) parts.push(`${file.bit_depth} бит`);
  return parts.length > 0 ? parts.join(" / ") : null;
}

/**
 * The headline facts a reviewer compares first.
 *
 * Lossless copies lead with resolution, not bitrate. A FLAC carries the same
 * samples as the WAV it was made from at roughly half the bits, so comparing
 * their bitrates measures packing rather than quality and reads as if the FLAC
 * were the worse copy. Sample rate and bit depth are the real resolution, and
 * they compare honestly across both containers. For a lossy copy the bitrate is
 * the quality signal, so that is what leads there.
 */
export function fileSpecLine(file: AudioDedupFile) {
  const lossless = isLosslessFormat(file.audio_format);
  const headline = lossless ? fileResolutionLabel(file) : fileBitrateLabel(file);
  return [
    file.audio_format || "—",
    ...(headline ? [headline] : []),
    formatBytes(file.size),
    formatSeconds(file.duration)
  ].join(" · ");
}

/** Secondary facts, shown under the headline strip. */
export function fileQualityLine(file: AudioDedupFile) {
  const parts: string[] = [];
  // Lossless already leads with resolution; the packed rate is context, not a
  // verdict, so it trails and is marked as such.
  if (isLosslessFormat(file.audio_format)) {
    const bitrate = fileBitrateLabel(file);
    if (bitrate) parts.push(`поток ${bitrate}`);
  } else {
    const resolution = fileResolutionLabel(file);
    if (resolution) parts.push(resolution);
  }
  if (file.metadata_completeness !== null) parts.push(`теги ${file.metadata_completeness}`);
  if (file.bpm !== null) parts.push(`${Math.round(file.bpm)} BPM`);
  if (file.musical_key) parts.push(file.musical_key);
  return parts.join(" · ");
}

export type DedupSpectralBadge = { text: string; tone: "warn" | "ok" | "muted" };

/**
 * The spectral verdict, which is the fake-bitrate evidence.
 *
 * A brickwall well under the container's ceiling means the audio was once lossy,
 * whatever the extension claims, so it leads rather than sits in a list.
 */
export function fileSpectralBadge(file: AudioDedupFile): DedupSpectralBadge {
  if (file.spectral_cutoff_hz === null) {
    return { text: file.spectral_note || "спектр не проверен", tone: "muted" };
  }
  const cutoff = `срез ${formatCutoff(file.spectral_cutoff_hz)}`;
  if (file.suspected_transcode) return { text: `${cutoff} · фейк-битрейт`, tone: "warn" };
  return { text: `${cutoff}${file.spectral_note ? ` · ${file.spectral_note}` : ""}`, tone: "ok" };
}

export const dedupConfidenceOptions = ["high", "medium", "review"] as const;

export function confidenceLabel(confidence: string) {
  if (confidence === "high") return "высокая";
  if (confidence === "medium") return "средняя";
  if (confidence === "review") return "ручная";
  return confidence || "—";
}
