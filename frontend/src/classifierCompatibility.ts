import type { PromotedClassifier } from "./api";

export function classifierScoringBlockedReason(classifier: PromotedClassifier | undefined): string {
  if (!classifier) return "Classifier profile is no longer available.";

  if (classifier.is_scoring_compatible === false) {
    const manifestErrorText = (classifier.manifest_errors || []).filter(Boolean).join("; ");
    if (manifestErrorText) return manifestErrorText;
    if (classifier.manifest_status) return `Classifier manifest status is ${classifier.manifest_status}.`;
    return "Classifier manifest is not compatible with scoring.";
  }

  return "";
}

export function classifierIsAvailable(classifier: PromotedClassifier): boolean {
  return classifierScoringBlockedReason(classifier) === "";
}

export function classifierProfileStatus(classifier: PromotedClassifier): string {
  if (classifierIsAvailable(classifier)) return "available";
  return classifier.production_status || classifier.manifest_status || "blocked";
}

export function formatClassifierScoredTracks(value: number | undefined): string {
  const count = Math.max(0, Math.trunc(Number(value || 0)));
  return `${count} tracks`;
}

export function filterAvailableClassifierValues<T>(
  classifiers: PromotedClassifier[],
  values: Record<string, T>,
): Record<string, T> {
  const availableKeys = new Set(
    classifiers
      .filter(classifierIsAvailable)
      .map((classifier) => classifier.classifier_key),
  );
  return Object.fromEntries(
    Object.entries(values).filter(([classifierKey]) => availableKeys.has(classifierKey)),
  );
}

export function orderPromotedClassifiers(classifiers: PromotedClassifier[]): PromotedClassifier[] {
  return classifiers
    .map((classifier, index) => ({
      classifier,
      index,
      promotedAt: promotionTimestamp(classifier.promoted_at),
    }))
    .sort((left, right) => {
      if (left.promotedAt !== null && right.promotedAt !== null) {
        return left.promotedAt - right.promotedAt || left.index - right.index;
      }
      if (left.promotedAt !== null) return -1;
      if (right.promotedAt !== null) return 1;
      return left.index - right.index;
    })
    .map(({ classifier }) => classifier);
}

function promotionTimestamp(value: string | null | undefined): number | null {
  if (!value) return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}
