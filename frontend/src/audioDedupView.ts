import type {
  AudioDedupDeleteRequest,
  AudioDedupDeletionMode,
  AudioDedupFile,
  AudioDedupGroup,
  AudioDedupReportSummary
} from "./api";

/**
 * The phrase the delete endpoint requires in its body.
 *
 * The reviewer confirms in a dialog, so this is the client speaking the
 * word the API demands rather than something anyone types: the phrase keeps
 * a stray POST from deleting audio.
 */
export const applyDeleteConfirmation = "APPLY DELETE";

/** Selected files to delete, keyed by group so an off-page choice survives paging. */
export type DedupSelection = Record<number, number[]>;

/**
 * The report to review after a listing refresh.
 *
 * A report is a file on disk that the reviewer can delete between two visits to
 * the dialog, so the report already chosen may no longer exist. It is kept only
 * while the listing still holds it; otherwise the review moves to the newest
 * report, or to none at all when nothing is left to review.
 */
export function reconcileReportId(
  reports: AudioDedupReportSummary[],
  current: string | null
): string | null {
  if (current && reports.some((report) => report.report_id === current)) return current;
  return reports[0]?.report_id ?? null;
}

/**
 * Lines that state nothing about the copy they sit under.
 *
 * The keeper ranking line only repeats that the keeper is the keeper. Reports
 * written before it was dropped still carry it, so it is filtered here too.
 */
const emptyReasonPatterns = [
  /^highest keeper ranking inside this duplicate group$/i,
  // The fingerprint score is stated once for the group, above both copies.
  /^SONARA fingerprint-only candidate/i
];

function isEmptyReason(reason: string) {
  return emptyReasonPatterns.some((pattern) => pattern.test(reason));
}

/** The comparator keys as the kept copy states them. */
const keeperKeyStatements: Record<string, string> = {
  "measured bandwidth": "Самый широкий в группе измеренный спектр",
  bitrate: "Самый высокий в группе битрейт",
  "bit depth": "Самая высокая в группе разрядность",
  "sample rate": "Самая высокая в группе частота",
  "true peak": "Лучший в группе пик",
  "dynamic range": "Самый широкий в группе динамический диапазон",
  "loudness range": "Самый широкий в группе разброс громкости",
  format: "Лучший в группе формат",
  // Reports written before the key was renamed still say "format rank", and a
  // scan takes the better part of an hour, so their sentence keeps its wording.
  "format rank": "Лучший в группе ранг формата",
  "file size": "Самый большой в группе файл",
  "tag completeness": "Лучшая в группе полнота тегов",
  "dj tags": "Лучшие в группе DJ-теги"
};

/** Word values inside those comparisons; numbers with units pass through. */
const keeperValueWords: Record<string, string> = {
  "full band": "полный спектр",
  "suspected transcode": "похоже на транскод",
  lossless: "без потерь",
  lossy: "с потерями",
  unmeasured: "не измерен",
  "not measured": "не измерена",
  none: "нет тегов"
};

function keeperValueText(value: string) {
  const known = keeperValueWords[value.toLowerCase()];
  if (known) return known;
  const fields = value.match(/^(\d+) fields?$/i);
  if (fields) return fields[1];
  const kilohertz = value.match(/^([\d.]+) kHz$/i);
  return kilohertz ? `${kilohertz[1]} кГц` : value;
}

/** Loudness facts the report names when a group may hold two masters. */
const masterFactLabels: Record<string, string> = {
  "integrated loudness": "интегральная громкость",
  "dynamic range": "динамический диапазон",
  "loudness range": "разброс громкости"
};

/**
 * Russian wording for the report's own English sentences.
 *
 * The JSON, XLSX and log artifacts stay English because they are the record the
 * CLI writes and reads; only the screen is translated. An unrecognised sentence
 * is passed through untouched rather than dropped: showing the original beats
 * hiding evidence nobody translated yet.
 */
const reasonTranslations: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [
    // Stated on the kept copy, and only where the technical lines read alike:
    // where they differ, the reviewer already sees the difference.
    /^Best (.+?) in group: (.+)$/i,
    (m) =>
      `${keeperKeyStatements[m[1].toLowerCase()] ?? m[1]}: ${keeperValueText(m[2])}`
  ],
  [
    // The key behind this line is the transcode flag, not the band: it wins when
    // this copy is unflagged and every other one is flagged. The kept copy can
    // still end at a 320-class wall, so the wording claims no full band.
    /^Full-band spectrum in group$/i,
    () => "Не помечена как фейк-битрейт, в отличие от других копий"
  ],
  [/^Lossless in group$/i, () => "Единственная копия без потерь"],
  [
    /^Every compared fact ties; newest file in group$/i,
    () => "Все признаки совпали — самая свежая копия"
  ],
  [
    /^Every compared fact ties; scanned first in group$/i,
    () => "Все признаки совпали — отсканирована первой"
  ],
  [
    // The extension names a container, not the codec inside it, so neither the
    // lossless class nor the format preference can be proven for this group.
    /^codec is not stored for ambiguous container\(s\): (.+); lossless\/lossy quality class cannot be proven from extension$/i,
    (m) =>
      `Кодек не записан для неоднозначных контейнеров: ${m[1]}`
      + " — по расширению нельзя доказать, lossless это или lossy"
  ],
  [
    /^mixed DSD\/non-DSD duplicate group: bit depth and sample rate are not directly comparable across encoding families$/i,
    () =>
      "В группе смешаны DSD и PCM: разрядность и частоту дискретизации"
      + " нельзя сравнивать напрямую"
  ],
  [
    // The group is one recording in more than one mastering. Which master to
    // keep is the reviewer's taste, so the tool refuses to delete inside it.
    /^possible different master: (.+) differs by ([\d.]+) (LU|dB)$/i,
    (m) =>
      `Возможно разные мастеринги: ${masterFactLabels[m[1].toLowerCase()] ?? m[1]}`
      + ` расходится на ${m[2]} ${m[3]}`
  ],
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
    // The copy reached the keeper only through another copy, so the reviewer,
    // not the chain, decides whether it is the same recording.
    /^no direct fingerprint match with the keeper$/i,
    () => "Нет прямого совпадения отпечатков с сохраняемой копией"
  ],
  [
    /^candidate spectrum looks transcoded \((.+)\); the keeper holds the wider band$/i,
    (m) =>
      `Спектр копии похож на транскод (${spectralNoteText(m[1])}) — у сохраняемой полоса шире`
  ],
  [
    /^ambiguous chain: not every copy matched the keeper's fingerprint directly$/i,
    () => "Неоднозначная цепочка: не каждая копия совпала с отпечатком сохраняемой напрямую"
  ],
  [/^every remaining copy is a suspected transcode; verify spectra by ear$/i, () => "Все оставшиеся копии похожи на фейк-битрейт — сверьте спектры на слух"]
];

export function translateReason(reason: string) {
  for (const [pattern, render] of reasonTranslations) {
    const match = reason.match(pattern);
    if (match) return render(match);
  }
  return reason;
}

/**
 * What the fingerprints say about the group as a whole.
 *
 * The score compares the two copies, so it belongs between them rather than
 * inside one card, where it read as a fact about that copy alone.
 */
export function groupFingerprintLine(group: AudioDedupGroup): string | null {
  const fingerprint = group.fingerprint_similarity;
  if (fingerprint === null) return null;
  // A clamped score reaches 1 only on an identical fingerprint, which is the
  // one verdict the tool can state outright instead of hedging.
  if (fingerprint >= 1) return `Отпечатки совпали полностью (${formatSimilarity(fingerprint)}).`;
  return fingerprint >= 0.9
    ? `Отпечатки совпали почти полностью (${formatSimilarity(fingerprint)}).`
    : `Отпечатки совпали лишь частично (${formatSimilarity(fingerprint)})`
      + " — так бывает у винил-рипа против цифры и у ремастеров.";
}

function normalizeReason(reason: string) {
  // The keeper's `why_keep` lines end in a period and the review lines do not,
  // and they are the same sentences to whoever reads them.
  return reason.replace(/\.$/, "").trim();
}

/**
 * The report's own wording about this copy, deduplicated.
 *
 * The keeper carries its `why_keep` lines and a duplicate carries the reasons
 * the group still needs a look, so the two lists are read together. What the
 * group already states is dropped: the report repeats a quality-comparison note
 * on every copy it applies to, and printing it once per card buried the lines
 * that are about that copy alone.
 */
export function copyDetailReasons(file: AudioDedupFile, groupReasons: string[] = []): string[] {
  const seen = new Set(groupReasons.map((reason) => normalizeReason(reason).toLowerCase()));
  const reasons: string[] = [];
  for (const raw of [...file.reasons, ...file.review_reasons]) {
    const reason = normalizeReason(raw);
    if (!reason || isEmptyReason(reason)) continue;
    const key = reason.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    reasons.push(translateReason(reason));
  }
  return reasons;
}

/** The group-wide notes: what to look at before marking anything inside it. */
export function groupReviewReasons(group: AudioDedupGroup): string[] {
  return group.review_reasons
    .map(normalizeReason)
    .filter((reason) => reason && !isEmptyReason(reason))
    .map(translateReason);
}

export function selectedTrackIds(selection: DedupSelection, groupId: number): number[] {
  return selection[groupId] ?? [];
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

export function selectionGroupCount(selection: DedupSelection) {
  return Object.keys(selection).length;
}

/**
 * Whether a group keeps at least one copy under this selection.
 *
 * The server decides for real, including whether the surviving file is still on
 * disk. This mirrors the rule so an impossible choice is refused while the
 * reviewer is still making it. The filter keeps whole groups, so the screen
 * always holds every copy that is at stake.
 */
export function groupSurvivesSelection(group: AudioDedupGroup, trackIds: number[]) {
  return group.files.some((file) => !trackIds.includes(file.track_id));
}

/**
 * The tool's own recommendation: keep the suggested keeper, drop the rest.
 *
 * A stale row is left out — the report no longer describes the file behind it.
 */
export function suggestedGroupSelection(group: AudioDedupGroup): number[] {
  return group.files
    .filter((file) => !file.stale && file.role === "duplicate")
    .map((file) => file.track_id);
}

export function selectionSummary(groups: AudioDedupGroup[], selection: DedupSelection) {
  const byId = new Map<number, AudioDedupFile>();
  for (const group of groups) for (const file of group.files) byId.set(file.track_id, file);
  let files = 0;
  let bytes = 0;
  for (const ids of Object.values(selection)) {
    for (const trackId of ids) {
      files += 1;
      const file = byId.get(trackId);
      if (file) bytes += file.size;
    }
  }
  return { files, bytes, groups: selectionGroupCount(selection) };
}

export function buildDeleteRequest(
  groups: AudioDedupGroup[],
  selection: DedupSelection,
  deletionMode: AudioDedupDeletionMode,
  // The filter the review was reading under, carried so the server can refuse a
  // copy that was never on screen.
  pathFilter: string
): { ok: true; payload: AudioDedupDeleteRequest } | { ok: false; error: string } {
  const selections = Object.entries(selection)
    .map(([groupId, trackIds]) => ({ group_id: Number(groupId), track_ids: trackIds }))
    .filter((entry) => entry.track_ids.length > 0)
    .sort((left, right) => left.group_id - right.group_id);
  if (selections.length === 0) return { ok: false, error: "Не выбрано ни одного файла" };
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
  return {
    ok: true,
    payload: {
      selections,
      path_filter: pathFilter,
      deletion_mode: deletionMode,
      confirmation: applyDeleteConfirmation
    }
  };
}

/**
 * The Russian count form for a number: 1 копия, 2 копии, 5 копий.
 *
 * The screen states these counts next to the delete control, so a single
 * hard-coded form read as broken next to the one number the reviewer checks
 * before erasing audio. The caller supplies the three forms because the case
 * differs between "2 копии в группе" and "удалить 2 копии".
 */
export function pluralRu(count: number, one: string, few: string, many: string) {
  const tail = Math.abs(count) % 100;
  if (tail >= 11 && tail <= 14) return many;
  const last = tail % 10;
  if (last === 1) return one;
  if (last >= 2 && last <= 4) return few;
  return many;
}

/** "копия / копии / копий" in the nominative, the form every count line uses. */
export function copiesWord(count: number) {
  return pluralRu(count, "копия", "копии", "копий");
}

export function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
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

/**
 * The fingerprint band behind the chosen confidence level.
 *
 * Where confidence is read from the fingerprint, a level is a band of that
 * score, so the field shows the band rather than a number that looks like a
 * filter the reviewer set. Reports whose confidence comes from the weighted
 * score carry no bands, and there the field only states the report's own floor.
 */
export function fingerprintBandText(
  confidence: string,
  report: AudioDedupReportSummary | null
): string {
  // A report written before a field existed, or served by a backend that does
  // not send it yet, arrives with it missing rather than null.
  const floor = report?.fingerprint_min_similarity ?? null;
  const high = report?.fingerprint_confidence_high ?? null;
  const medium = report?.fingerprint_confidence_medium ?? null;
  if (floor === null) return "—";
  if (high === null || medium === null) return `≥ ${formatBand(floor)}`;
  if (confidence === "high") return `${formatBand(high)} – 1.00`;
  if (confidence === "medium") return `${formatBand(medium)} – ${formatBand(high)}`;
  if (confidence === "review") return `${formatBand(floor)} – ${formatBand(medium)}`;
  return `${formatBand(floor)} – 1.00`;
}

function formatBand(score: number) {
  return score.toFixed(2);
}

export function formatSimilarity(score: number | null) {
  if (score === null || !Number.isFinite(score)) return "—";
  const rounded = score.toFixed(3);
  // 1.000 has to mean 1: rounding 0.9999 up to it hides the one difference that
  // separates an identical fingerprint from a very close one.
  if (rounded === "1.000" && score < 1) return (Math.floor(score * 1000) / 1000).toFixed(3);
  return rounded;
}

export function formatCutoff(hz: number | null) {
  if (hz === null || !Number.isFinite(hz)) return "—";
  return `${(hz / 1000).toFixed(1)} кГц`;
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

/** Sample rate and bit depth: what resolution means for a scanned file. */
function sampleRateLabel(hertz: number | null) {
  if (hertz === null || !Number.isFinite(hertz) || hertz <= 0) return null;
  return `${hertz.toLocaleString("en-US")} Hz`;
}

function bitDepthLabel(bits: number | null) {
  if (bits === null || !Number.isFinite(bits) || bits <= 0) return null;
  return `${bits}-bit`;
}

/**
 * The technical line of one copy: format, stream, resolution, size, length.
 *
 * Every token is a fact the library scanned from the file, printed in the units
 * the track metadata dialog uses, so one file reads the same way in both
 * places. Bitrate and resolution stand side by side on purpose: between two
 * lossless copies the bitrate measures packing rather than quality, and a FLAC
 * at 900 kbps next to the WAV it came from at 1411 kbps carries the same
 * 44,100 Hz / 16-bit samples.
 */
export type DedupSpecCell = { key: string; text: string };

export function fileSpecCells(file: AudioDedupFile): DedupSpecCell[] {
  return [
    { key: "format", text: file.audio_format || "—" },
    { key: "bitrate", text: fileBitrateLabel(file) ?? "—" },
    { key: "sample_rate", text: sampleRateLabel(file.sample_rate_hz) ?? "—" },
    { key: "bit_depth", text: bitDepthLabel(file.bit_depth) ?? "—" },
    { key: "size", text: formatBytes(file.size) },
    { key: "duration", text: formatSeconds(file.duration) }
  ];
}

/**
 * The spec keys that actually separate the copies on screen.
 *
 * Two copies of one recording agree on most of this line, and reading six
 * identical tokens twice to find the one that differs is the work the review
 * should not ask for. The cards keep every token in the same position and lift
 * only the ones that disagree.
 */
export function differingSpecKeys(files: AudioDedupFile[]): Set<string> {
  const differing = new Set<string>();
  if (files.length < 2) return differing;
  const byKey = new Map<string, Set<string>>();
  for (const file of files) {
    for (const cell of fileSpecCells(file)) {
      const seen = byKey.get(cell.key) ?? new Set<string>();
      seen.add(cell.text);
      byKey.set(cell.key, seen);
    }
  }
  for (const [key, values] of byKey) {
    if (values.size > 1) differing.add(key);
  }
  return differing;
}

/** The folder holding a copy: the file name is already the card's heading. */
export function copyDirectory(path: string) {
  const separator = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return separator > 0 ? path.slice(0, separator) : path;
}

/**
 * The scan reports its progress in the engine's own English. The review is
 * Russian, and the counter in the section title is the one place a long run
 * speaks to the reviewer, so the step and the finished state are translated
 * here rather than renamed in the engine.
 */
const scanStepTranslations: Record<string, string> = {
  "Reading database": "чтение базы",
  "Loading scoped tracks": "загрузка треков",
  "Matching SONARA fingerprints": "сверка отпечатков",
  "Loading saved SONARA fingerprint sketches": "загрузка отпечатков",
  "Verifying SONARA fingerprint candidates": "проверка кандидатов",
  "Searching duplicate pairs": "поиск пар",
  "Building duplicate groups": "сборка групп",
  "No fingerprint duplicates": "дубликатов нет",
  "Analyzing spectra of duplicate-group files": "анализ спектра",
  "Writing reports": "запись отчёта",
  "Reports written": "отчёт записан"
};

const scanStateTranslations: Record<string, string> = {
  queued: "в очереди",
  running: "идёт поиск",
  completed: "готово",
  cancelled: "остановлено",
  failed: "ошибка"
};

export function scanStepLabel(step: string) {
  const known = scanStepTranslations[step];
  if (known) return known;
  // The one step that carries its own number: "Loaded 63220 scoped tracks".
  const loaded = step.match(/^Loaded (\d+) scoped tracks$/);
  if (loaded) return `загружено треков: ${loaded[1]}`;
  return step;
}

export function scanStateLabel(state: string) {
  return scanStateTranslations[state] ?? state;
}

/**
 * Why a reported copy no longer matches the library, in Russian.
 *
 * The report keeps the engine's English because it is the record the CLI
 * writes; the screen says it in the language of the review.
 */
const staleReasonTranslations: Record<string, string> = {
  "track is no longer in the library": "трека больше нет в базе",
  "report identity is stale": "идентичность трека изменилась после отчёта",
  "report file facts are missing": "в отчёте нет фактов файла",
  "report file facts are stale": "файл изменился после отчёта",
  "file is missing on disk": "файла нет на диске"
};

export function staleReasonLabel(reason: string) {
  return staleReasonTranslations[reason] ?? reason;
}

/** The copy that survives leads the group, whatever order the report kept. */
export function orderedGroupFiles(files: AudioDedupFile[]) {
  return [...files].sort((left, right) => {
    if (left.role === right.role) return left.track_id - right.track_id;
    return left.role === "keeper" ? -1 : 1;
  });
}

/** What this group's current marks amount to: what goes, what is left. */
export function groupSelectionOutcome(group: AudioDedupGroup, trackIds: number[]) {
  const marked = group.files.filter((file) => trackIds.includes(file.track_id)).length;
  return { marked, surviving: group.files.length - marked };
}

/**
 * The loudness and tag facts, shown under the technical line.
 *
 * Dynamic range, loudness range and true peak decide the keeper below the
 * declared facts, so the card states them: a reason nobody can check against
 * the copy in front of them is not evidence.
 */
export function fileQualityLine(file: AudioDedupFile) {
  const parts: string[] = [];
  if (file.dynamic_range_db !== null) parts.push(`DR ${file.dynamic_range_db.toFixed(1)} dB`);
  if (file.loudness_range_lu !== null) parts.push(`LRA ${file.loudness_range_lu.toFixed(1)} LU`);
  if (file.true_peak_dbtp !== null) parts.push(`TP ${file.true_peak_dbtp.toFixed(1)} dBTP`);
  if (file.metadata_completeness !== null) parts.push(`теги ${file.metadata_completeness}`);
  if (file.bpm !== null) parts.push(`${Math.round(file.bpm)} BPM`);
  if (file.musical_key) parts.push(file.musical_key);
  return parts.join(" · ");
}

/** Why a copy carries no spectral measurement, in Russian. */
const spectralSkipTranslations: Record<string, string> = {
  "ffmpeg unavailable": "ffmpeg не найден",
  "track not loaded": "трек не загружен",
  "file not reachable": "файл недоступен",
  "unknown sample rate": "частота дискретизации неизвестна",
  "decode failed": "не удалось декодировать",
  "decoded segment too short": "фрагмент слишком короткий",
  "decoded segment is silent or invalid": "тишина или битые данные",
  "reference band missing": "нет опорной полосы 1–8 кГц",
  "no band above floor": "сигнал ниже порога"
};

/** The detector's bitrate class as the screen prints it: "~160 kbps", "≤112 kbps". */
function bitrateClassText(label: string) {
  return label.replace("<=", "≤");
}

/**
 * The detector's English note as the short Russian phrase the screen carries.
 *
 * It words the reason a copy went unmeasured and the note a candidate's review
 * reason quotes; the chip states the copy's cutoff itself, so the frequency
 * inside the note is not repeated. The declared-bitrate clause exists only on a
 * lossy copy and can follow any of the three shapes, so it is split off first.
 * An unrecognised note passes through untouched, as a review reason does.
 *
 * The class is worded as the encoder whose wall it resembles, never as a bare
 * bitrate: the card prints the file's own bitrate beside the chip, and
 * "~320 kbps" next to a WAV's 1411 kbps read as a contradiction.
 */
export function spectralNoteText(note: string) {
  const skipped = spectralSkipTranslations[note];
  if (skipped) return skipped;
  const declared = note.match(/^(.*), (matches|below) declared (\d+) kbps$/i);
  const shape = declared ? declared[1] : note;
  const matches = declared !== null && declared[2].toLowerCase() === "matches";
  let relation = "";
  if (declared) {
    relation = matches
      ? `соответствует заявленным ${declared[3]} kbps`
      : `ниже заявленных ${declared[3]} kbps`;
  }
  const wall = shape.match(/^brickwall at [\d.]+ kHz(?: \((.+) class\))?$/i);
  // A lossy copy walled where its own bitrate puts the wall is the encoder at
  // work, so the match is the whole statement.
  if (wall && matches) return relation;
  let base: string | null = null;
  if (/^full band$/i.test(shape)) base = "полная полоса";
  else if (/^rolls off near [\d.]+ kHz$/i.test(shape)) base = "плавный спад";
  else if (wall) base = wall[1] ? `стена как у MP3 ${bitrateClassText(wall[1])}` : "стена";
  if (base === null) return note;
  return relation ? `${base}, ${relation}` : base;
}

/** The widest measured band among a group's copies, which the others are read against. */
export function groupBestCutoff(files: AudioDedupFile[]): number | null {
  let best: number | null = null;
  for (const file of files) {
    const cutoff = file.spectral_cutoff_hz;
    if (cutoff !== null && (best === null || cutoff > best)) best = cutoff;
  }
  return best;
}

/** Two cutoffs closer than this are one band measured twice, not a narrower copy. */
const SPECTRAL_SHORTFALL_MIN_HZ = 100;

/**
 * The cutoff the reviewer allows, the same level as the "allow cutoffs above"
 * setting of the checker they calibrate against. A wall at or above it is an
 * ordinary master or an honest 320 kbps source, which the spectrum cannot tell
 * apart, so the chip says nothing about bitrate there. Naming "~320 kbps" on a
 * 1411 kbps WAV with a 20.2 kHz cutoff read as an accusation the tool cannot make.
 */
const SPECTRAL_ALLOWED_CUTOFF_HZ = 19_600;

export type DedupSpectralBadge = {
  text: string;
  tone: "warn" | "ok" | "muted";
  /** Which explanation the chip's tooltip carries; absent where the text needs none. */
  kind?: "recompressed" | "transcoded" | "wall" | "clean";
};

/**
 * The spectral verdict, which is the fake-bitrate evidence.
 *
 * Every chip reads the same way: what the spectrum means in plain words, then
 * how high the audio reaches. A bare cutoff, or the shape of its roll-off, told
 * the reviewer nothing, so the meaning leads and the number backs it. A flagged
 * copy names which fake it is and the bitrate its band gives away, a lossy copy
 * that keeps its promise says so, and a copy the detector has nothing against is
 * simply in order unless it carries less band than the group's widest copy,
 * because the copies are one recording and that gap is the comparison itself.
 */
export function fileSpectralBadge(
  file: AudioDedupFile,
  bestCutoffHz: number | null = null
): DedupSpectralBadge {
  const note = file.spectral_note ?? "";
  if (file.spectral_cutoff_hz === null) {
    return { text: note ? spectralNoteText(note) : "спектр не проверен", tone: "muted" };
  }
  const band = `до ${formatCutoff(file.spectral_cutoff_hz)}`;
  const sourceClass = note.match(/\((.+) class\)/i);
  const source = sourceClass ? bitrateClassText(sourceClass[1]) : null;
  if (file.suspected_transcode) {
    // Only a lossy copy is judged against its declared bitrate, so that clause
    // tells a re-encode at a higher rate from lossy audio in a lossless container.
    const recompressed = /below declared/i.test(note);
    return {
      text: `${recompressed ? "пережат" : "транскод"}${source ? ` из ${source}` : ""} · ${band}`,
      tone: "warn",
      kind: recompressed ? "recompressed" : "transcoded"
    };
  }
  // A lossy copy walled where its own bitrate puts the wall is the encoder at
  // work, and its gap to a lossless copy is expected, so the match is all it says.
  const honest = note.match(/matches declared (\d+) kbps/i);
  if (honest) return { text: `честные ${honest[1]} kbps · ${band}`, tone: "ok" };
  if (/^brickwall /i.test(note) && file.spectral_cutoff_hz < SPECTRAL_ALLOWED_CUTOFF_HZ) {
    return { text: `похоже на MP3${source ? ` ${source}` : ""} · ${band}`, tone: "ok", kind: "wall" };
  }
  const shortfall = bestCutoffHz === null ? 0 : bestCutoffHz - file.spectral_cutoff_hz;
  if (shortfall >= SPECTRAL_SHORTFALL_MIN_HZ) {
    return { text: `−${formatCutoff(shortfall)} к лучшей копии · ${band}`, tone: "ok" };
  }
  return { text: `в норме · ${band}`, tone: "ok", kind: "clean" };
}

export const dedupConfidenceOptions = ["high", "medium", "review"] as const;

export function confidenceLabel(confidence: string) {
  if (confidence === "high") return "высокая";
  if (confidence === "medium") return "средняя";
  if (confidence === "review") return "ручная";
  return confidence || "—";
}
