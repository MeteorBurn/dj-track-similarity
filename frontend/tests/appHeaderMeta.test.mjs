import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

test("mobile topbar keeps actions compact and gives status its own row", () => {
  const styles = readFileSync(fileURLToPath(new URL("../src/styles.css", import.meta.url)), "utf8");
  const mobileStyles = styles.match(/@media \(max-width: 720px\)\s*{([\s\S]*)$/)?.[1] || "";
  const actionsRule = mobileStyles.match(/\.topbar-actions\s*{([\s\S]*?)}/)?.[1] || "";
  const noticeRule = mobileStyles.match(/\.topbar-actions \.notice\s*{([\s\S]*?)}/)?.[1] || "";

  assert.match(actionsRule, /align-items:\s*center/);
  assert.match(actionsRule, /flex-direction:\s*row/);
  assert.match(actionsRule, /flex-wrap:\s*wrap/);
  assert.doesNotMatch(actionsRule, /flex-direction:\s*column/);
  assert.match(noticeRule, /flex:\s*1 0 100%/);
  assert.match(noticeRule, /max-width:\s*none/);
  assert.match(noticeRule, /width:\s*100%/);
});
