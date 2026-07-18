import type { SonaraCurves, SonaraFeaturePayload } from "./api";

export type ReadableSonaraCurve = {
  key: string;
  label: string;
  value: string;
  description: string;
};

type CurveDefinition = Omit<ReadableSonaraCurve, "value"> & {
  summaryKind?: "embedding" | "fingerprint";
};

const curveDefinitions: readonly CurveDefinition[] = [
  {
    key: "beats",
    label: "Beat positions",
    description: "Complete stored beat-frame sequence; shown as summary statistics only"
  },
  {
    key: "onset_frames",
    label: "Onset positions",
    description: "Complete stored onset-frame sequence; shown as summary statistics only"
  },
  {
    key: "chord_sequence",
    label: "Chord sequence",
    description: "Complete stored chord-label sequence; the dialog shows only its item count"
  },
  {
    key: "chord_events",
    label: "Chord events",
    description: "Complete stored chord events with start/end times; the dialog shows only their count"
  },
  {
    key: "energy_curve",
    label: "Energy curve",
    description: "Stored within-track energy envelope; shown as summary statistics only"
  },
  {
    key: "loudness_curve",
    label: "Loudness curve",
    description: "Stored within-track loudness envelope; shown as summary statistics only"
  },
  {
    key: "downbeats",
    label: "Downbeats",
    description: "Stored downbeat positions; shown as summary statistics only"
  },
  {
    key: "tempo_curve",
    label: "Tempo curve",
    description: "Stored within-track tempo estimates in BPM; shown as summary statistics only"
  },
  {
    key: "embedding",
    label: "Audio embedding",
    description: "Stored SONARA audio vector for possible future use; only its dimensions and summary statistics are shown",
    summaryKind: "embedding"
  },
  {
    key: "fingerprint",
    label: "Audio fingerprint",
    description: "Stored SONARA audio fingerprint for possible future use; only its encoded size is shown",
    summaryKind: "fingerprint"
  }
];

export function readableSonaraCurves(raw: SonaraCurves): ReadableSonaraCurve[] {
  return curveDefinitions.flatMap((definition) => {
    const payload = raw[definition.key];
    if (!payload || payload.type === "unavailable") return [];
    const value = definition.summaryKind === "fingerprint"
      ? formatFingerprintSummary(payload)
      : definition.summaryKind === "embedding"
        ? formatEmbeddingSummary(payload)
        : formatCurveSummary(payload);
    return [{ key: definition.key, label: definition.label, description: definition.description, value }];
  });
}

export function formatCurveSummary(payload: SonaraFeaturePayload): string {
  const values = numericValues(payload.value);
  const summary = isRecord(payload.summary) ? payload.summary : {};
  const count = declaredCurveSize(payload) ?? values.length;
  const min = finiteNumber(summary.min) ?? finiteMinimum(values);
  const max = finiteNumber(summary.max) ?? finiteMaximum(values);
  const mean = finiteNumber(summary.mean) ?? finiteMean(values);
  const countLabel = `${count} ${count === 1 ? "value" : "values"}`;
  if (min == null || max == null || mean == null) return countLabel;
  return `${countLabel} · min ${formatMetric(min)} · max ${formatMetric(max)} · mean ${formatMetric(mean)}`;
}

function formatEmbeddingSummary(payload: SonaraFeaturePayload): string {
  return formatCurveSummary(payload).replace(/^([0-9]+) value(?:s)?/, "$1 dimensions");
}

function formatFingerprintSummary(payload: SonaraFeaturePayload): string {
  const encodedLength = typeof payload.value === "string"
    ? payload.value.length
    : finiteNonNegativeInteger(payload.length) ?? finiteNonNegativeInteger(payload.size);
  if (encodedLength == null) return "Stored fingerprint";
  return `${encodedLength} encoded ${encodedLength === 1 ? "character" : "characters"}`;
}

function declaredCurveSize(payload: SonaraFeaturePayload): number | null {
  const direct = finiteNonNegativeInteger(payload.size) ?? finiteNonNegativeInteger(payload.length);
  if (direct != null) return direct;
  if (!Array.isArray(payload.shape) || !payload.shape.length) return null;
  let size = 1;
  for (const rawDimension of payload.shape) {
    const dimension = finiteNonNegativeInteger(rawDimension);
    if (dimension == null) return null;
    size *= dimension;
  }
  return size;
}

function numericValues(value: unknown): number[] {
  if (!Array.isArray(value)) {
    const number = finiteNumber(value);
    return number == null ? [] : [number];
  }
  return value.flatMap(numericValues);
}

function finiteMinimum(values: number[]): number | null {
  return values.length ? values.reduce((minimum, value) => Math.min(minimum, value)) : null;
}

function finiteMaximum(values: number[]): number | null {
  return values.length ? values.reduce((maximum, value) => Math.max(maximum, value)) : null;
}

function finiteMean(values: number[]): number | null {
  if (!values.length) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function finiteNonNegativeInteger(value: unknown): number | null {
  const number = finiteNumber(value);
  return number != null && number >= 0 && Number.isInteger(number) ? number : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatMetric(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(1);
  return value.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}
