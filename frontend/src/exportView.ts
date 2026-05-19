export function exportDirectoryError(path: string) {
  return path.trim() ? null : "Укажите папку экспорта";
}
