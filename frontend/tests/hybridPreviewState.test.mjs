import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";
import ts from "typescript";

async function loadSearchSurfaceState() {
  const sourcePath = new URL("../src/searchSurfaceState.ts", import.meta.url);
  const tempDir = mkdtempSync(join(tmpdir(), "search-surface-state-"));
  const modulePath = join(tempDir, "searchSurfaceState.cjs");
  const compiled = ts.transpileModule(readFileSync(sourcePath, "utf8"), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022
    }
  }).outputText;
  writeFileSync(modulePath, compiled, "utf8");
  return import(pathToFileURL(modulePath));
}

function hybridDraft(overrides = {}) {
  return {
    databasePath: "C:/temp/core.sqlite",
    databaseIdentity: "catalog-a",
    seedTrackIds: [10, 11],
    sources: { mert: true, maest: true, muq: true, sonara: true, clap: true },
    useCustomWeights: false,
    weights: { mert: 1, maest: 1, muq: 1, sonara: 1, clap: 1 },
    perSource: 30,
    limit: 25,
    transitionRiskWeight: 0,
    classifierPreferences: {},
    classifierRiskWeights: {},
    ...overrides
  };
}

test("Hybrid defaults keep all five sources and delegate weight normalization to backend", async () => {
  const { buildHybridPayload } = await loadSearchSurfaceState();
  const result = buildHybridPayload(hybridDraft());

  assert.equal(result.ok, true);
  assert.deepEqual(result.payload.sources, ["mert", "maest", "muq", "sonara", "clap"]);
  assert.equal(result.payload.weights, null);
  assert.equal(result.payload.record_session, true);
  assert.equal(result.payload.include_diagnostics, true);
});

test("Hybrid legacy opt-out omits MuQ without retaining a hidden readiness key", async () => {
  const { buildHybridPayload } = await loadSearchSurfaceState();
  const result = buildHybridPayload(hybridDraft({
    sources: { mert: true, maest: true, muq: false, sonara: true, clap: true }
  }));

  assert.equal(result.ok, true);
  assert.deepEqual(result.payload.sources, ["mert", "maest", "sonara", "clap"]);
  assert.equal(result.payload.weights, null);
  assert.equal("muq" in (result.payload.weights || {}), false);
});

test("Hybrid custom weights serialize exact enabled keys and reject invalid values", async () => {
  const { buildHybridPayload } = await loadSearchSurfaceState();
  const valid = buildHybridPayload(hybridDraft({
    sources: { mert: true, maest: false, muq: true, sonara: false, clap: true },
    useCustomWeights: true,
    weights: { mert: 0.4, maest: 99, muq: 0.3, sonara: 99, clap: 0.3 }
  }));
  assert.equal(valid.ok, true);
  assert.deepEqual(valid.payload.weights, { mert: 0.4, muq: 0.3, clap: 0.3 });

  const invalid = buildHybridPayload(hybridDraft({
    useCustomWeights: true,
    weights: { mert: 0, maest: 0, muq: -0.1, sonara: 0, clap: 0 }
  }));
  assert.equal(invalid.ok, false);
  assert.match(invalid.error, /finite and nonnegative/);
});

test("Hybrid request guard rejects late success error and finally from an older request", async () => {
  const { createRequestTokenGuard } = await loadSearchSurfaceState();
  const guard = createRequestTokenGuard();
  const older = guard.begin();
  const newer = guard.begin();

  assert.equal(guard.isCurrent(older), false, "older success/error/finally must be ignored");
  assert.equal(guard.isCurrent(newer), true);
  guard.invalidate();
  assert.equal(guard.isCurrent(newer), false, "config or catalog changes invalidate the active request");
});

test("generic search results require an exact request key and their originating tab", async () => {
  const { genericSearchResultIsCurrent } = await loadSearchSurfaceState();

  assert.equal(
    genericSearchResultIsCurrent("sonara", "sonara", "request-a", "request-a"),
    true
  );
  assert.equal(
    genericSearchResultIsCurrent("muq", "sonara", "request-a", "request-a"),
    false,
    "SONARA results must not render below MUQ"
  );
  assert.equal(
    genericSearchResultIsCurrent("class", "sonara", "request-a", "request-a"),
    false,
    "generic results must not render below CLASS"
  );
  assert.equal(
    genericSearchResultIsCurrent("sonara", "sonara", "request-a", "request-b"),
    false,
    "changed seed/filter/catalog input invalidates the response"
  );
});

test("generic search requests are abortable and commit provenance only while current", () => {
  const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  const panelSource = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(appSource, /genericSearchRequestGuard\.current\.begin\(\)/);
  assert.match(appSource, /genericSearchAbortController\.current\?\.abort\(\)/);
  assert.match(appSource, /genericSearchInputKeyRef\.current === ticket\.requestKey/);
  assert.match(appSource, /commitGenericSearchResults\(ticket, "sonara", value\)/);
  assert.match(appSource, /commitGenericSearchResults\(ticket, "clap", value\)/);
  assert.match(appSource, /signal: ticket\.controller\.signal/);
  assert.match(panelSource, /genericSearchResultIsCurrent\(/);
  assert.match(panelSource, /primaryTabPresentation\[genericSearchResultOrigin\]\.label} results/);
  assert.match(panelSource, /\{showGenericSearchResults && genericSearchResultOrigin \?/);
});

test("Hybrid signature includes database path catalog identity and only Hybrid config", async () => {
  const { hybridSignature } = await loadSearchSurfaceState();
  const base = hybridSignature(hybridDraft());
  assert.notEqual(base, hybridSignature(hybridDraft({ databasePath: "D:/other.sqlite" })));
  assert.notEqual(base, hybridSignature(hybridDraft({ databaseIdentity: "catalog-b" })));
  assert.notEqual(base, hybridSignature(hybridDraft({ sources: { mert: true, maest: true, muq: false, sonara: true, clap: true } })));
});

test("Hybrid UI consumes backend sources weights contract hashes and MuQ support", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /setHybridSourcesUsed\(response\.sources\)/);
  assert.match(source, /setHybridWeightsUsed\(response\.weights_used\)/);
  assert.match(source, /setHybridSourceContractHashes\(response\.source_contract_hashes\)/);
  assert.match(source, /key: "muq"/);
  assert.match(source, /current-contract stored MuQ acoustic embeddings/);
  assert.match(source, /CLAP text prompts are not used here/);
});

test("Hybrid request completion is token signature and abort guarded", () => {
  const source = readFileSync(new URL("../src/SearchPlaylistPanel.tsx", import.meta.url), "utf8");

  assert.match(source, /new AbortController\(\)/);
  assert.match(source, /hybridRequestGuard\.current\.isCurrent\(requestToken\)/);
  assert.match(source, /hybridInputKeyRef\.current !== requestKey/);
  assert.match(source, /isAbortError\(error\)/);
  assert.match(source, /finally \{[\s\S]*hybridRequestGuard\.current\.isCurrent\(requestToken\)[\s\S]*setHybridLoading\(false\)/);
});
