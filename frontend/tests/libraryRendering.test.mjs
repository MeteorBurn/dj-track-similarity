import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const trackRowsSource = readFileSync(
  new URL("../src/TrackRows.tsx", import.meta.url),
  "utf8"
);
const styles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8"
);

test("library renders every track supplied by the fixed 500-track page", () => {
  assert.match(trackRowsSource, /\{tracks\.map\(\(track\) => \{/);
  assert.doesNotMatch(
    trackRowsSource,
    /visibleLibraryWindow|shiftLibraryWindow|windowStart|track-window-controls/
  );
  assert.doesNotMatch(styles, /\.track-window-(controls|previous-button|next-button|status)/);
  assert.match(
    styles,
    /@media \(max-width: 1180px\)[\s\S]*?\.track-list\s*\{[\s\S]*?max-height:\s*min\(720px,\s*70vh\)/
  );
});
