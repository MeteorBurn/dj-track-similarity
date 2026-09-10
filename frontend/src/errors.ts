/** Error shapes every caller has to handle, in one place.
 *
 * This module imports nothing on purpose: the frontend tests build their
 * module graph by hand, and a leaf is cheap for them to provide.
 */

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/** The message a caught value carries, whatever kind of value it is. */
export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
