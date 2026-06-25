import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

const apiSource = readFileSync(fileURLToPath(new URL("../src/api.ts", import.meta.url)), "utf8");
const panelSource = readFileSync(fileURLToPath(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url)), "utf8");

test("PR-21 pair feedback payload uses session id and seed id list", () => {
  const pairPayloadBlock = apiSource.match(/export type EvaluationPairFeedbackPayload = \{[\s\S]*?\n};/)?.[0] || "";

  assert.match(apiSource, /record_session\?: boolean;/);
  assert.match(apiSource, /feedback\?: EvaluationPairFeedbackState \| null;/);
  assert.match(apiSource, /session_id\?: number \| null;/);
  assert.match(pairPayloadBlock, /seed_track_ids: number\[\];/);
  assert.doesNotMatch(pairPayloadBlock, /seed_track_id: number;/);
});

test("PR-21 reason tag allowlist is mirrored by the Hybrid feedback UI", () => {
  for (const reasonTag of [
    "good_groove",
    "good_density",
    "good_texture",
    "good_mood",
    "good_tonal",
    "too_vocal",
    "bad_density",
    "bad_tonal",
    "too_obvious",
    "interesting_adjacent",
    "wrong_energy",
    "wrong_texture",
    "bad_transition_risk"
  ]) {
    assert.match(apiSource, new RegExp(`\\| "${reasonTag}"`));
    assert.match(panelSource, new RegExp(`value: "${reasonTag}"`));
  }
});

test("Hybrid feedback rating labels map to the PR-21 numeric scale", () => {
  assert.match(panelSource, /\{ value: 3, label: "Strong" \}/);
  assert.match(panelSource, /\{ value: 2, label: "Works" \}/);
  assert.match(panelSource, /\{ value: 1, label: "Maybe" \}/);
  assert.match(panelSource, /\{ value: 0, label: "Reject" \}/);
  assert.match(panelSource, /Rated: \$\{ratingLabel\}\$\{tagText\}/);
});
