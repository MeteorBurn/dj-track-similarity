import type { PromotedClassifier } from "./api";

export function classifierScoringBlockedReason(classifier: PromotedClassifier | undefined): string {
  if (!classifier) return "Classifier profile is no longer available.";
  if (classifier.is_scoring_compatible !== false) return "";

  const manifestErrorText = (classifier.manifest_errors || []).filter(Boolean).join("; ");
  if (manifestErrorText) return manifestErrorText;
  if (classifier.manifest_status) return `Classifier manifest status is ${classifier.manifest_status}.`;
  return "Classifier manifest is not compatible with scoring.";
}
