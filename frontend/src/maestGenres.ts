export function formatMaestGenreLabel(label: string) {
  return label.replace(/_/g, " ").split("---").pop()?.trim() || "";
}
