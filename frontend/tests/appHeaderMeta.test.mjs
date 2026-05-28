import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const appPath = fileURLToPath(new URL("../src/App.tsx", import.meta.url));

test("top header meta omits liked track count", () => {
  const source = readFileSync(appPath, "utf8");
  const metaBlock = source.match(/<span className="meta">([\s\S]*?)<\/span>/)?.[1] || "";

  assert.match(metaBlock, /librarySummary\.tracks/);
  assert.match(metaBlock, /librarySummary\.clap/);
  assert.doesNotMatch(metaBlock, /librarySummary\.liked/);
  assert.doesNotMatch(metaBlock, /\|\s*liked/);
});
