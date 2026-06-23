import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");

function cssRule(selector) {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return styles.match(new RegExp(`${escapedSelector}\\s*{([\\s\\S]*?)}`))?.[1] || "";
}

test("suggested-track results panel has a wider desktop column and larger viewport", () => {
  const workspaceRule = cssRule(".workspace");
  const resultsRule = cssRule(".search-workflow-section .results-list");

  assert.match(workspaceRule, /minmax\(360px,\s*1\.24fr\)/);
  assert.doesNotMatch(workspaceRule, /minmax\(240px,\s*0\.96fr\)/);
  assert.match(resultsRule, /min-height:\s*280px/);
  assert.match(resultsRule, /max-height:\s*min\(520px,\s*52vh\)/);
  assert.doesNotMatch(resultsRule, /max-height:\s*160px/);
});
