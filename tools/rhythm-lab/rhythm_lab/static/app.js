const tracksEl = document.getElementById("tracks");
const queryEl = document.getElementById("query");
const sourcePathEl = document.getElementById("sourcePath");
const changeSourceEl = document.getElementById("changeSource");
const sourcePickerEl = document.getElementById("sourcePicker");
const profileSelectEl = document.getElementById("profileSelect");
const shutdownLabEl = document.getElementById("shutdownLab");
const libraryTabEl = document.getElementById("libraryTab");
const candidatesTabEl = document.getElementById("candidatesTab");
const collectionTabEl = document.getElementById("collectionTab");
const trainingTabEl = document.getElementById("trainingTab");
const settingsTabEl = document.getElementById("settingsTab");
const commonFiltersEl = document.getElementById("commonFilters");
const collectionControlsEl = document.getElementById("collectionControls");
const collectionSelectEl = document.getElementById("collectionSelect");
const deleteCollectionEl = document.getElementById("deleteCollection");
const collectionStatusEl = document.getElementById("collectionStatus");
const candidateFiltersEl = document.getElementById("candidateFilters");
const bpmMinEl = document.getElementById("bpmMin");
const bpmMaxEl = document.getElementById("bpmMax");
const labelEl = document.getElementById("label");
const libraryOrderEl = document.getElementById("libraryOrder");
const shuffleLibraryOrderEl = document.getElementById("shuffleLibraryOrder");
const candidatePredictedEl = document.getElementById("candidatePredicted");
const candidateMinBrokenEl = document.getElementById("candidateMinBroken");
const candidateMinPositiveEl = document.getElementById("candidateMinPositive");
const deleteProfileEl = document.getElementById("deleteProfile");
const summaryCoverageEl = document.getElementById("summaryCoverage");
const summaryLabelsEl = document.getElementById("summaryLabels");
const pageControlsEl = document.getElementById("pageControls");
const pageSizeEl = document.getElementById("pageSize");
const pageNumberEl = document.getElementById("pageNumber");
const prevPageEl = document.getElementById("prevPage");
const nextPageEl = document.getElementById("nextPage");
const pageInfoEl = document.getElementById("pageInfo");
const guidancePanelEl = document.getElementById("guidancePanel");
const trainingPanelEl = document.getElementById("trainingPanel");
const settingsPanelEl = document.getElementById("settingsPanel");
const profileDialogEl = document.getElementById("profileDialog");
const newProfileTypeEl = document.getElementById("newProfileType");
const binaryLabelGridEl = document.getElementById("binaryLabelGrid");
const multiclassLabelEditorEl = document.getElementById("multiclassLabelEditor");
const multiclassLabelRowsEl = document.getElementById("multiclassLabelRows");
const FEATURE_FAMILY_LABELS = {
  sonara: "SONARA",
  mert: "MERT",
  mert_v2: "MERT-v2",
  maest: "MAEST",
  clap: "CLAP",
  muq: "MuQ",
  mulan: "MuLan",
};
// Picker order in the UI; the backend canonical order is being aligned to it.
const FEATURE_FAMILY_ORDER = ["sonara", "maest", "mert", "mert_v2", "muq", "mulan", "clap"];
const MERT_V2_DEFAULT_LAYER = 24;
const DEFAULT_BENCHMARK_STRATEGY = "singles+all";
// Labels are UI copy; the keys are the values sent to the API.
const BENCHMARK_STRATEGY_LABELS = {
  singles: "One model at a time",
  "singles+all": "One at a time + all",
  greedy: "Greedy selection",
  full: "Full grid",
  layers: "MERT-v2 layers",
  "layers+all": "MERT-v2 layers + others",
  custom: "Custom list",
};
const BENCHMARK_RUN_WARNING = 30;
const STEP_STATUS_LABELS = { done: "Done", ready: "Ready", blocked: "Blocked" };
const FEATURE_STATE_LABELS = { current: "current", missing: "missing", stale: "stale" };
// Backend training rule (rhythm_lab.web_app.MIN_TRAINING_ROWS_PER_LABEL); shown so an enabled Train is understandable.
const MIN_ROWS_PER_CLASS = 2;
const READINESS_DEBOUNCE_MS = 250;

let profiles = [];
let activeProfile = null;
let offset = 0;
let total = 0;
let visibleTrackContext = null;
let activeView = "library";
let collections = [];
const viewOffsets = { library: 0, candidates: 0, liked: 0, collection: 0, training: 0, settings: 0 };
let loadSequence = 0;
let libraryRandomSeed = makeLibraryRandomSeed();
let latestTrainingReadiness = null;
let latestProfileSummary = null;
let promoteFeatureSetEl = null;
let selectedTrainingFeatureSet = null;
let recipeMertV2Layer = null;
let sourceCatalogUuid = null;
let sourceSwitchPending = false;
let benchmarkStrategy = DEFAULT_BENCHMARK_STRATEGY;
let benchmarkCustomSets = [];
let latestBenchmarkReport = null;
let trainingViewProfileKey = null;
let trainingPlanText = "";
let recipeRefreshTimer = null;
let readinessRequestId = 0;
let trainingProgressPollHandle = null;
let trainingProgressPollGeneration = 0;
let trainingProgressHasStarted = false;
let latestWorkflowProgress = { status: "idle" };
let workflowStatusText = "";
const player = createRhythmPlayer({ onChange: updatePlayingRows });

document.getElementById("load").addEventListener("click", () => loadActive({ reset: true }));
changeSourceEl.addEventListener("click", () => setSourcePickerOpen(sourcePickerEl.hidden));
document.addEventListener("click", event => {
  if (!sourcePickerEl.hidden && !changeSourceEl.parentElement.contains(event.target)) setSourcePickerOpen(false);
});
sourcePickerEl.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    event.preventDefault();
    setSourcePickerOpen(false);
  }
});
document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(showError));
document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(showError));
document.getElementById("newProfile").addEventListener("click", () => { document.getElementById("newProfileError").hidden = true; updateNewProfilePreview(); profileDialogEl.showModal(); });
shutdownLabEl.addEventListener("click", () => shutdownLab().catch(showError));
deleteProfileEl.addEventListener("click", () => deleteActiveProfile().catch(showError));
document.getElementById("cancelProfileButton").addEventListener("click", () => profileDialogEl.close());
document.getElementById("newProfileForm").addEventListener("submit", event => createProfile(event).catch(showError));
document.getElementById("newProfileType").addEventListener("change", updateNewProfileTypeControls);
document.querySelectorAll("[data-profile-type]").forEach(button => button.addEventListener("click", () => {
  newProfileTypeEl.value = button.dataset.profileType;
  updateNewProfileTypeControls();
}));
document.getElementById("newProfileForm").addEventListener("input", updateNewProfilePreview);
document.getElementById("closeProfileButton")?.addEventListener("click", () => profileDialogEl.close());
document.getElementById("addMulticlassLabel").addEventListener("click", () => addMulticlassLabelRow());
document.getElementById("profileForm").addEventListener("submit", event => updateProfile(event).catch(showError));
document.getElementById("renameLabelForm").addEventListener("submit", event => renameLabel(event).catch(showError));

profileSelectEl.addEventListener("change", () => {
  if (!profileSelectEl.value) {
    clearActiveProfile();
    return;
  }
  setActiveProfile(profileSelectEl.value).catch(showError);
});
libraryTabEl.addEventListener("click", () => switchView("library"));
candidatesTabEl.addEventListener("click", () => switchView("candidates"));
document.getElementById("likedTab").addEventListener("click", () => switchView("liked"));
guidancePanelEl.addEventListener("click", event => {
  const target = event.target instanceof Element ? event.target.closest("[data-open-view]") : null;
  if (target) switchView(target.dataset.openView).catch(showError);
});
collectionTabEl.addEventListener("click", () => switchView("collection"));
trainingTabEl.addEventListener("click", () => switchView("training"));
settingsTabEl.addEventListener("click", () => switchView("settings"));
sourcePathEl.addEventListener("keydown", event => { if (event.key === "Enter") switchSource(sourcePathEl.value).catch(showError); });
queryEl.addEventListener("keydown", event => { if (event.key === "Enter") loadActive({ reset: true }); });
bpmMinEl.addEventListener("change", () => loadActive({ reset: true }));
bpmMaxEl.addEventListener("change", () => loadActive({ reset: true }));
labelEl.addEventListener("change", () => loadActive({ reset: true }));
collectionSelectEl.addEventListener("change", () => loadActive({ reset: true }));
deleteCollectionEl.addEventListener("click", () => deleteSelectedCollection().catch(showError));
libraryOrderEl.addEventListener("change", () => updateLibraryOrder({ reset: true }));
shuffleLibraryOrderEl.addEventListener("click", () => shuffleLibraryOrder());
candidatePredictedEl.addEventListener("change", () => loadActive({ reset: true }));
candidateMinBrokenEl.addEventListener("change", () => loadActive({ reset: true }));
candidateMinPositiveEl.addEventListener("change", () => {
  candidateMinPositiveEl.value = probabilityFilterValue();
  loadActive({ reset: true });
});
trainingPanelEl.addEventListener("click", event => handleTrainingActionClick(event).catch(showError));
trainingPanelEl.addEventListener("change", event => handleTrainingControlChange(event).catch(showError));
pageSizeEl.addEventListener("change", () => loadActive({ reset: true }));
pageNumberEl.addEventListener("change", () => jumpToPage());
pageNumberEl.addEventListener("keydown", event => { if (event.key === "Enter") jumpToPage(); });
prevPageEl.addEventListener("click", () => {
  offset = Math.max(0, offset - pageLimit());
  loadActive();
});
nextPageEl.addEventListener("click", () => {
  const limit = pageLimit();
  offset = Math.min(maxPageOffset(total, limit), offset + limit);
  loadActive();
});

async function init() {
  updateNewProfileTypeControls();
  await loadProfiles();
  await loadCollections();
  await loadSourceState();
  updateFilterPanelControls();
  await loadActive({ reset: true });
}

async function loadProfiles() {
  const data = await fetch("/api/profiles").then(parseJsonResponse);
  profiles = data.items || [];
  profileSelectEl.innerHTML = "";
  addOption(profileSelectEl, "", "Choose a profile");
  profiles.forEach(profile => {
    const option = document.createElement("option");
    option.value = profile.classifier_key;
    option.textContent = profile.name;
    profileSelectEl.appendChild(option);
  });
  if (activeProfile && profiles.some(profile => profile.classifier_key === activeProfile.classifier_key)) {
    await setActiveProfile(activeProfile.classifier_key, { skipLoad: true });
  } else {
    clearActiveProfile();
  }
}

async function setActiveProfile(profileKey, options = {}) {
  invalidateActiveLoads();
  activeProfile = profiles.find(profile => profile.classifier_key === profileKey) || null;
  if (!activeProfile) {
    clearActiveProfile();
    return;
  }
  profileSelectEl.value = activeProfile.classifier_key;
  resetProfileRecipeState();
  latestWorkflowProgress = { status: "idle" };
  renderProfileControls();
  offset = 0;
  viewOffsets.library = 0;
  viewOffsets.candidates = 0;
  viewOffsets.liked = 0;
  viewOffsets.collection = 0;
  if (!options.skipLoad) await loadActive({ reset: true });
}

function clearActiveProfile() {
  invalidateActiveLoads();
  activeProfile = null;
  resetProfileRecipeState();
  profileSelectEl.value = "";
  summaryCoverageEl.textContent = "";
  summaryLabelsEl.textContent = "";
  pageInfoEl.textContent = "";
  tracksEl.innerHTML = "";
  trainingPanelEl.innerHTML = "";
  guidancePanelEl.innerHTML = '<div class="guidance-card"><b>Choose a profile</b><span class="meta">Select or create a classifier profile to load tracks.</span></div>';
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "All labels");
  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "All predictions");
  document.getElementById("profileNameInput").value = "";
  document.getElementById("profileDescriptionInput").value = "";
  document.getElementById("profileArtifactPrefixInput").value = "";
  document.getElementById("profileTrainingMinAddedInput").value = "50";
  document.getElementById("profileTrainingMinLabelsInput").value = "100";
  document.getElementById("renameLabelSelect").innerHTML = "";
  document.getElementById("settingsLabels").innerHTML = "";
  document.getElementById("settingsCoverage").textContent = "";
  settingsPanelEl.querySelectorAll("input, textarea, select, button").forEach(control => { control.disabled = true; });
  deleteProfileEl.disabled = true;
  updateLibraryOrderControls();
}

function invalidateActiveLoads() {
  loadSequence += 1;
}

function resetProfileRecipeState() {
  latestTrainingReadiness = null;
  latestProfileSummary = null;
  promoteFeatureSetEl = null;
  selectedTrainingFeatureSet = null;
  recipeMertV2Layer = null;
  benchmarkCustomSets = [];
  latestBenchmarkReport = null;
  trainingViewProfileKey = null;
  trainingPlanText = "";
  readinessRequestId += 1;
  cancelScheduledReadinessRefresh();
}

function cancelScheduledReadinessRefresh() {
  if (recipeRefreshTimer !== null) {
    window.clearTimeout(recipeRefreshTimer);
    recipeRefreshTimer = null;
  }
}

function renderProfileControls() {
  // Step gates are not touched here: they come only from readiness (applyTrainingReadiness).
  deleteProfileEl.disabled = false;
  settingsPanelEl.querySelectorAll("input, textarea, select, button").forEach(control => { control.disabled = false; });
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "All labels");
  addOption(labelEl, "unlabeled", "Unlabeled");
  activeProfile.labels.forEach(label => addOption(labelEl, label.key, label.name));

  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "All predictions");
  trainingLabels().forEach(label => addOption(candidatePredictedEl, label.key, `Predicted ${label.name}`));

  const positive = labelByKey(activeProfile.positive_label);
  const negative = labelByKey(activeProfile.negative_label);
  if (isMulticlassProfile()) {
    if (candidateMinBrokenEl.value === "negative_highest") candidateMinBrokenEl.value = "positive_highest";
    candidateMinBrokenEl.options[0].textContent = "Highest confidence";
    candidateMinBrokenEl.options[1].hidden = true;
    candidateMinBrokenEl.options[1].disabled = true;
    candidateMinBrokenEl.options[2].textContent = "Lowest confidence";
  } else {
    candidateMinBrokenEl.options[1].hidden = false;
    candidateMinBrokenEl.options[1].disabled = false;
    candidateMinBrokenEl.options[0].textContent = `Highest P(${positive.name})`;
    candidateMinBrokenEl.options[1].textContent = `Highest P(${negative.name})`;
    candidateMinBrokenEl.options[2].textContent = "Uncertain first";
  }

  document.getElementById("profileNameInput").value = activeProfile.name || "";
  document.getElementById("profileDescriptionInput").value = activeProfile.description || "";
  document.getElementById("profileArtifactPrefixInput").value = activeProfile.artifact_prefix || "";
  document.getElementById("profileTrainingMinAddedInput").value = activeProfile.training_min_added || 50;
  document.getElementById("profileTrainingMinLabelsInput").value = activeProfile.training_min_labels ?? 100;

  const renameSelect = document.getElementById("renameLabelSelect");
  renameSelect.innerHTML = "";
  activeProfile.labels.forEach(label => addOption(renameSelect, label.key, `${label.name} (${label.key})`));
  document.getElementById("settingsLabels").innerHTML = `<div class="settings-label-heading"><span>Label</span><span>Key</span></div>${activeProfile.labels.map((label, index) => `<div class="settings-label-row ${labelRoleClass(label, index)}"><span><i class="label-dot"></i>${escapeHtml(label.name)}</span><span class="meta">${escapeHtml(label.key)}</span></div>`).join("")}`;
  updateFilterPanelControls();
}

function trainingActionElement(id) {
  return document.getElementById(id);
}

function setTrainingActionDisabled(id, disabled, title = null) {
  const button = trainingActionElement(id);
  if (!button) return;
  button.disabled = Boolean(disabled);
  if (title !== null) button.title = title;
}

function setWorkflowBusy(disabled) {
  ["openLibrary", "trainRefresh", "runBenchmark", "calibrateClassifier", "refreshCandidates", "promoteClassifier"].forEach(id => {
    setTrainingActionDisabled(id, disabled);
  });
  trainingPanelEl.querySelectorAll("button[data-training-action]").forEach(button => { button.disabled = Boolean(disabled); });
}

function setWorkflowStatus(message) {
  workflowStatusText = String(message || "");
  const globalStatus = document.getElementById("globalStatus");
  if (globalStatus) {
    globalStatus.textContent = workflowStatusText;
    globalStatus.hidden = !workflowStatusText;
  }
  const statusEl = document.getElementById("refreshCandidatesStatus");
  if (!statusEl) return;
  statusEl.textContent = workflowStatusText;
  statusEl.parentElement.hidden = !workflowStatusText;
}

function renderTrainingProgress(progress) {
  const container = document.getElementById("trainingProgress");
  const stageEl = document.getElementById("trainingProgressStage");
  const percentEl = document.getElementById("trainingProgressPercent");
  const barEl = document.getElementById("trainingProgressBar");
  if (!container || !stageEl || !percentEl || !barEl) return;
  latestWorkflowProgress = { ...progress };
  const status = String(progress?.status || "idle");
  if (status === "idle") {
    container.hidden = true;
    return;
  }
  const percent = Math.max(0, Math.min(100, Number(progress?.percent || 0)));
  stageEl.textContent = String(progress?.error || progress?.stage || "Preparing data");
  percentEl.textContent = `${Math.round(percent)}%`;
  barEl.style.width = `${percent}%`;
  container.dataset.status = status;
  container.dataset.operation = String(progress?.operation || "");
  container.hidden = false;
}

function stopTrainingProgressPolling() {
  trainingProgressPollGeneration += 1;
  if (trainingProgressPollHandle !== null) {
    window.clearInterval(trainingProgressPollHandle);
    trainingProgressPollHandle = null;
  }
}

async function pollTrainingProgress(profileKey, operation, pollingGeneration) {
  if (pollingGeneration !== trainingProgressPollGeneration) return;
  if (!activeProfile || activeProfile.classifier_key !== profileKey) {
    stopTrainingProgressPolling();
    return;
  }
  const response = await fetch(`/api/profiles/${profileKey}/training/progress`);
  if (!response.ok) return;
  const progress = await response.json();
  if (pollingGeneration !== trainingProgressPollGeneration) return;
  if (!activeProfile || activeProfile.classifier_key !== profileKey) {
    stopTrainingProgressPolling();
    return;
  }
  if (String(progress.operation || "") !== operation) return;
  if (progress.status === "running") {
    trainingProgressHasStarted = true;
  } else if (!trainingProgressHasStarted) {
    return;
  }
  renderTrainingProgress(progress);
  if (progress.status === "completed" || progress.status === "failed") {
    stopTrainingProgressPolling();
  }
}

function startTrainingProgressPolling(profileKey, operation, stage = "Starting…") {
  stopTrainingProgressPolling();
  trainingProgressHasStarted = false;
  renderTrainingProgress({ status: "running", operation, stage, percent: 0 });
  const pollingGeneration = trainingProgressPollGeneration;
  trainingProgressPollHandle = window.setInterval(() => {
    pollTrainingProgress(profileKey, operation, pollingGeneration).catch(() => {});
  }, 350);
}

async function handleTrainingActionClick(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const variantButton = target.closest("button[data-variant-select]");
  if (variantButton && promoteFeatureSetEl && !variantButton.disabled) {
    promoteFeatureSetEl.value = variantButton.dataset.variantSelect;
    applyTrainingReadiness(latestTrainingReadiness);
    if (latestProfileSummary) renderGuidance(latestProfileSummary);
    return;
  }
  const applyButton = target.closest("button[data-recipe-apply]");
  if (applyButton) return applyRecipe(applyButton.dataset.recipeApply);
  if (target.closest("button[data-benchmark-add]")) return addCurrentRecipeToBenchmark();
  const removeButton = target.closest("button[data-benchmark-remove]");
  if (removeButton) return removeBenchmarkRecipe(removeButton.dataset.benchmarkRemove);
  const button = target.closest("button[data-training-action]");
  if (!button) return;
  const action = button.dataset.trainingAction;
  if (action === "library") return openLibraryForLabels();
  if (action === "train") return trainRefresh();
  if (action === "benchmark") return runBenchmark();
  if (action === "calibrate") return calibrateClassifier();
  if (action === "refresh") return refreshCandidates();
  if (action === "promote") return promoteClassifier();
}

function addOption(select, value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  select.appendChild(option);
}

async function loadCollections() {
  const selected = collectionSelectEl.value;
  const data = await fetch("/api/collections").then(parseJsonResponse);
  collections = data.items || [];
  collectionSelectEl.innerHTML = "";
  if (!collections.length) {
    addOption(collectionSelectEl, "", "No collections");
    collectionStatusEl.textContent = "0 collections";
    deleteCollectionEl.disabled = true;
    return;
  }
  collections.forEach(collection => {
    addOption(collectionSelectEl, String(collection.id), `${collection.name} (${collection.track_count})`);
  });
  if (selected && collections.some(collection => String(collection.id) === selected)) {
    collectionSelectEl.value = selected;
  }
  const active = selectedCollection();
  collectionStatusEl.textContent = active
    ? `${active.track_count} ${plural(active.track_count, "track", "tracks")}, ${active.source}`
    : `${collections.length} ${plural(collections.length, "collection", "collections")}`;
  deleteCollectionEl.disabled = !active;
}

function selectedCollection() {
  return collections.find(collection => String(collection.id) === collectionSelectEl.value) || null;
}

function labelByKey(key) {
  return activeProfile.labels.find(label => label.key === key) || { key, name: key, role: "review" };
}

function isMulticlassProfile() {
  return activeProfile?.profile_type === "multiclass";
}

function trainingLabels() {
  if (!activeProfile) return [];
  if (isMulticlassProfile()) return activeProfile.labels.filter(label => label.role === "class");
  return activeProfile.labels.filter(label => label.role === "positive" || label.role === "negative");
}

function setSourcePickerOpen(open) {
  sourcePickerEl.hidden = !open;
  changeSourceEl.setAttribute("aria-expanded", String(open));
  if (open) sourcePathEl.focus();
  else if (sourcePickerEl.contains(document.activeElement)) changeSourceEl.focus();
}

async function chooseSource() {
  const response = await fetch("/api/source/dialog", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  const data = await parseJsonResponse(response);
  sourcePathEl.value = data.path || sourcePathEl.value || "";
}

async function switchSource(path) {
  if (sourceSwitchPending) return;
  sourceSwitchPending = true;
  player.reset();
  visibleTrackContext = null;
  invalidateActiveLoads();
  readinessRequestId += 1;
  tracksEl.inert = true;
  document.getElementById("loadSource").disabled = true;
  try {
    const response = await fetch("/api/source/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
    const data = await parseJsonResponse(response);
    applySourceState(data);
    setSourcePickerOpen(false);
    // Stored families and recipe evidence belong to the newly selected library.
    latestTrainingReadiness = null;
    selectedTrainingFeatureSet = null;
    recipeMertV2Layer = null;
    benchmarkCustomSets = [];
    latestBenchmarkReport = null;
    trainingViewProfileKey = null;
    cancelScheduledReadinessRefresh();
    await loadActive({ reset: true });
  } finally {
    sourceSwitchPending = false;
    tracksEl.inert = false;
    document.getElementById("loadSource").disabled = false;
  }
}

async function loadSourceState() {
  const data = await fetch("/api/source/current").then(parseJsonResponse);
  applySourceState(data);
}

function applySourceState(data) {
  if (sourceCatalogUuid && sourceCatalogUuid !== data.catalog_uuid) {
    player.reset();
    visibleTrackContext = null;
    invalidateActiveLoads();
  }
  sourcePathEl.value = data.path || sourcePathEl.value || "";
  sourceCatalogUuid = data.catalog_uuid ? String(data.catalog_uuid) : null;
  document.getElementById("sourceName").textContent = fileName(sourcePathEl.value) || "No library loaded";
  document.getElementById("sourceStatus").textContent = sourceCatalogUuid ? "Library loaded" : "No library loaded";
  document.getElementById("sourceStatus").classList.toggle("loaded", Boolean(sourceCatalogUuid));
  document.getElementById("sourceStatus").dataset.loaded = String(Boolean(sourceCatalogUuid));
}

function appendRecipeParam(params) {
  if (selectedTrainingFeatureSet) params.set("feature_set", selectedTrainingFeatureSet);
  return params;
}

async function shutdownLab() {
  shutdownLabEl.disabled = true;
  shutdownLabEl.classList.add("stopping");
  setWorkflowStatus("Stopping Rhythm Lab…");
  const response = await fetch("/api/shutdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  await parseJsonResponse(response);
  setWorkflowStatus("Rhythm Lab is stopping…");
  window.setTimeout(() => window.close(), 300);
}

async function switchView(view) {
  viewOffsets[activeView] = offset;
  activeView = view;
  offset = viewOffsets[view] || 0;
  document.querySelector(".track-table-scroll").scrollTop = 0;
  libraryTabEl.classList.toggle("active", view === "library");
  candidatesTabEl.classList.toggle("active", view === "candidates");
  document.getElementById("likedTab")?.classList.toggle("active", view === "liked");
  collectionTabEl.classList.toggle("active", view === "collection");
  trainingTabEl.classList.toggle("active", view === "training");
  settingsTabEl.classList.toggle("active", view === "settings");
  document.querySelectorAll(".tab-button").forEach(button => {
    if (button.classList.contains("active")) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  updateFilterPanelControls();
  trainingPanelEl.hidden = view !== "training";
  settingsPanelEl.hidden = view !== "settings";
  tracksEl.hidden = view === "training" || view === "settings";
  await loadActive();
}

function updateFilterPanelControls() {
  const trackView = activeView !== "training" && activeView !== "settings";
  document.body.dataset.view = activeView;
  document.getElementById("trackWorkspace").hidden = !trackView;
  document.getElementById("contextualSidebar").hidden = !trackView;
  const title = document.getElementById("pageTitle");
  const subtitle = document.getElementById("pageSubtitle");
  title.textContent = activeView === "candidates" ? "Candidates" : activeView === "collection" ? "Review collection" : "Profile settings";
  subtitle.textContent = activeView === "candidates" ? "Review model predictions and label by listening." : activeView === "settings" ? activeProfile?.name || "Choose a profile" : "";
  title.parentElement.hidden = ["library", "liked", "training"].includes(activeView);
  queryEl.placeholder = activeView === "liked" ? "Search liked tracks…" : "Search tracks, artists or paths…";
  commonFiltersEl.hidden = !trackView;
  pageControlsEl.hidden = !trackView;
  collectionControlsEl.hidden = activeView !== "collection";
  candidateFiltersEl.hidden = !trackView || (activeView !== "library" && activeView !== "candidates");
  candidateFiltersEl.classList.toggle("candidate-filters-placeholder", activeView !== "library" && activeView !== "candidates");
  updateLibraryOrderControls();
  renderTrackHeader();
}

function updateLibraryOrder(options = {}) {
  updateFilterPanelControls();
  return loadActive(options);
}

function shuffleLibraryOrder() {
  libraryRandomSeed = makeLibraryRandomSeed();
  updateFilterPanelControls();
  return loadTracks({ reset: true });
}

function updateLibraryOrderControls() {
  const libraryView = activeView === "library";
  const candidateView = activeView === "candidates";
  libraryOrderEl.hidden = !libraryView;
  libraryOrderEl.disabled = activeView !== "library";
  shuffleLibraryOrderEl.hidden = activeView !== "library";
  shuffleLibraryOrderEl.disabled = !libraryView || libraryOrderEl.value !== "random";
  candidatePredictedEl.hidden = activeView !== "candidates";
  candidatePredictedEl.disabled = !candidateView;
  candidateMinBrokenEl.hidden = activeView !== "candidates";
  candidateMinBrokenEl.disabled = !candidateView;
  candidateMinPositiveEl.hidden = activeView !== "candidates";
  candidateMinPositiveEl.disabled = !candidateView;
}

function makeLibraryRandomSeed() {
  return Math.floor(Math.random() * 2147483647);
}

async function loadActive(options = {}) {
  if (!activeProfile) return;
  if (activeView === "candidates") return loadCandidates(options).catch(showError);
  if (activeView === "liked") return loadLikedTracks(options).catch(showError);
  if (activeView === "collection") return loadCollectionTracks(options).catch(showError);
  if (activeView === "training") return loadTrainingView().catch(showError);
  if (activeView === "settings") return loadSettingsView().catch(showError);
  return loadTracks(options).catch(showError);
}

async function loadSummary(sequence = loadSequence) {
  if (!activeProfile) return;
  const profileKey = activeProfile.classifier_key;
  const params = new URLSearchParams();
  if (activeView === "collection" && selectedCollection()) params.set("collection_id", String(selectedCollection().id));
  const data = await fetch(`/api/profiles/${profileKey}/summary${params.size ? `?${params}` : ""}`).then(parseJsonResponse);
  if (sequence !== loadSequence || !activeProfile || activeProfile.classifier_key !== profileKey) return;
  latestProfileSummary = data;
  renderSummary(data);
  renderGuidance(data);
}

function labelTotals(source) {
  const totals = source?.total;
  return totals && typeof totals === "object" ? totals : null;
}

function formatLabelCounts(labels, totals = null, labelsList = activeProfile.labels) {
  // With phase-1 identity, readiness reports `current` (usable in the active
  // library) and `total` (all labeled content); render "current / total" then.
  const counts = labels || {};
  const totalCounts = totals && typeof totals === "object" ? totals : null;
  return labelsList
    .map(label => {
      const current = counts[label.key] || 0;
      return totalCounts ? `${label.name} ${current} / ${totalCounts[label.key] || 0}` : `${label.name} ${current}`;
    })
    .join(", ");
}

function renderSummary(data) {
  summaryCoverageEl.innerHTML = `<span>${escapeHtml(data.tracks || 0)} tracks</span><span class="summary-liked">♡ ${escapeHtml(data.liked || 0)} liked</span>`;
  summaryLabelsEl.innerHTML = labelCountBadges(data.labels || {});
  const settingsCoverage = document.getElementById("settingsCoverage");
  if (settingsCoverage) settingsCoverage.textContent = `In this library: ${formatLabelCounts(data.labels || {}, null, trainingLabels())}`;
}

function recipeChips(featureSet) {
  return `<div class="recipe-chips">${recipeTokens(featureSet).map(token => `<span>${escapeHtml(recipeTokenLabel(token))}</span>`).join("")}</div>`;
}

function labelRoleClass(label, index = 0) {
  return `role-${escapeHtml(label.role || "review")} label-color-${index % 7}`;
}

function coverageBars(data, compact = false) {
  const counts = data?.current || latestProfileSummary?.labels || {};
  const threshold = labelThreshold(data);
  return trainingLabels().map((label, index) => {
    const value = Number(counts[label.key] || 0);
    return `<div class="coverage-item ${labelRoleClass(label, index)}${compact ? " compact" : ""}"><div class="coverage-label"><span>${escapeHtml(label.name)}</span><span>${value} / ${threshold}</span></div><div class="coverage-track" role="meter" aria-label="${escapeHtml(label.name)} labels" aria-valuemin="0" aria-valuemax="${threshold}" aria-valuenow="${Math.min(value, threshold)}"><span style="width:${Math.min(100, value / threshold * 100)}%"></span></div></div>`;
  }).join("");
}

function sidebarModel(title, model, promoted = false) {
  const available = model && (!promoted || model.status !== "not_promoted");
  const score = promoted ? model?.calibration?.validation_f1 : model?.macro_f1_mean;
  return `<section class="sidebar-section"><h3 class="sidebar-kicker">${title}</h3>${available ? `<div class="model-score"><strong>${formatMetricPercent(score)}</strong><span>F1</span><span class="calibration-chip ${model.calibration_status === "calibrated" ? "calibrated" : ""}">${model.calibration_status === "calibrated" ? "Calibrated" : "Not calibrated"}</span></div><p class="meta">${escapeHtml(model.feature_set || "Unknown recipe")}</p>` : '<p class="meta">No model available yet.</p>'}<button type="button" class="text-button" data-open-view="training">View details →</button></section>`;
}

function labelCountBadges(labels) {
  // Header counters: once readiness is known, show "in this library / all labeled".
  const readiness = latestTrainingReadiness;
  const totals = labelTotals(readiness);
  return activeProfile.labels
    .map(label => {
      const summaryCount = labels[label.key] || 0;
      const current = readiness?.current ? (readiness.current[label.key] ?? summaryCount) : summaryCount;
      const total = totals ? (totals[label.key] ?? 0) : null;
      const value = totals ? `${current} / ${total}` : `${current}`;
      const title = totals ? `${current} of ${total} tracks labeled "${label.name}" are in this library` : `${label.name}: ${current}`;
      return `<span class="summary-badge label-count-badge" title="${escapeHtml(title)}"><span>${escapeHtml(label.name)}</span><b>${escapeHtml(value)}</b></span>`;
    })
    .join("");
}

function renderGuidance(summary) {
  if (!activeProfile) return;
  const data = latestTrainingReadiness;
  const selected = selectedPromotionOption(data);
  const profile = `<section class="sidebar-section"><h3 class="sidebar-kicker">${activeView === "candidates" ? "Review context" : "Profile"}</h3><h2 class="sidebar-title">${escapeHtml(activeProfile.name)}</h2><p class="meta">${isMulticlassProfile() ? "Multiclass" : "Binary"} classifier</p>`;
  const legendLabels = activeView === "library" && !isMulticlassProfile() ? trainingLabels() : activeProfile.labels;
  const legend = legendLabels.map((label, index) => `<div class="label-legend ${labelRoleClass(label, index)}"><span class="label-dot"></span><div><b>${escapeHtml(label.name)}</b><span class="meta">${escapeHtml(label.role === "positive" ? "Positive label" : label.role === "negative" ? "Negative reference" : label.role === "class" ? "Training class" : "Uncertain / review")}</span></div></div>`).join("");
  const trainingButton = '<button type="button" class="sidebar-action" data-open-view="training">Open Training</button>';
  if (activeView === "collection") {
    const collection = selectedCollection();
    const progress = summary.collection_progress;
    const count = progress?.total || 0;
    const progressLabels = [...activeProfile.labels, { key: "__unlabeled", name: "Unlabeled", role: "unlabeled" }];
    const countFor = label => label.key === "__unlabeled" ? progress?.unlabeled || 0 : progress?.labels?.[label.key] || 0;
    guidancePanelEl.innerHTML = `<section class="sidebar-section"><h3 class="sidebar-kicker">Collection</h3><h2 class="sidebar-title">${escapeHtml(collection?.name || "No collection selected")}</h2><p class="meta">For focused listening and labeling.</p></section><section class="sidebar-section"><h3 class="sidebar-kicker">Review progress</h3><div class="collection-progress">${progressLabels.map((label, index) => `<span class="${labelRoleClass(label, index)}" style="width:${count ? countFor(label) / count * 100 : 0}%"></span>`).join("")}</div>${progressLabels.map((label, index) => `<div class="label-legend ${labelRoleClass(label, index)}"><span class="label-dot"></span><b>${countFor(label)}</b><span>${escapeHtml(label.name)}</span></div>`).join("")}<p class="meta">${count} unique tracks in this collection</p></section><section class="sidebar-section"><h3 class="sidebar-kicker">Profile labels</h3><p>Labels belong to ${escapeHtml(activeProfile.name)}. Removing a collection keeps its labels.</p></section>${!collection ? '<section class="sidebar-empty"><b>No collections yet</b><p>Choose a saved review collection when one is available.</p></section>' : ""}`;
  } else if (activeView === "liked") {
    guidancePanelEl.innerHTML = `<section class="sidebar-section"><h3 class="sidebar-kicker">Liked tracks</h3><h2 class="sidebar-title"><span class="liked-heart">♥</span> Liked tracks</h2><p>${summary.liked || 0} tracks</p><p class="meta">Profile: ${escapeHtml(activeProfile.name)}</p><p>Your favorites are independent of classifier labels.</p></section><section class="sidebar-section"><h3 class="sidebar-kicker">Label legend</h3><div class="label-legend"><span class="liked-heart">♥</span><div><b>Liked</b><span class="meta">In your favorites</span></div></div>${legend}</section>${!summary.liked ? '<section class="sidebar-empty"><h3>No liked tracks yet</h3><p>Use the heart beside a track to add it here.</p><button type="button" data-open-view="library">Open Library</button></section>' : ""}`;
  } else if (activeView === "candidates") {
    guidancePanelEl.innerHTML = `${profile}<p>Selected recipe</p>${recipeChips(selectedTrainingFeatureSet)}</section><section class="sidebar-section"><p>Model prediction and your label are separate.</p><p class="meta">${selected?.calibration_status === "calibrated" ? "Calibrated classifier scores." : "Uncalibrated scores: use for ranking."}</p></section><section class="sidebar-empty"><h3 class="sidebar-kicker">Current library</h3><p>${total ? `${total} candidates match the current filters.` : "No candidates for the current recipe and filters yet."}</p>${trainingButton}<p class="meta">Refresh candidates there.</p></section>`;
  } else {
    const totals = labelTotals(data);
    guidancePanelEl.innerHTML = `${profile}<div class="profile-roles">${legend}</div></section><section class="sidebar-section"><h3 class="sidebar-kicker">Label coverage</h3><p class="meta">In this library</p>${coverageBars(data)}${totals ? `<p class="meta coverage-total">Across libraries: ${escapeHtml(formatLabelCounts(totals, null, trainingLabels()))}</p>` : ""}</section><section class="sidebar-section"><h3 class="sidebar-kicker">Training</h3><b class="training-state ${data?.ready ? "ready" : "blocked"}">${data ? data.ready ? "Ready to train" : "More labels or features needed" : "Loading training state…"}</b><p class="meta">${escapeHtml(data ? workflowRecommendation(data, selected) : "Checking this library.")}</p>${trainingButton}</section>${sidebarModel("Selected variant", selected)}${sidebarModel("Current promoted model", data?.promoted_model, true)}`;
  }
}

function labelCoverageSentence(data) {
  const totals = labelTotals(data);
  const current = data?.current || {};
  const threshold = Number(data?.label_threshold);
  const hasThreshold = Number.isFinite(threshold) && threshold > 0;
  const parts = trainingLabels().map(label => {
    const have = current[label.key] || 0;
    if (hasThreshold && totals) return `${label.name}: ${have} of ${threshold} needed (${totals[label.key] || 0} labeled in total)`;
    if (hasThreshold) return `${label.name}: ${have} of ${threshold} needed`;
    if (totals) return `${have} of ${totals[label.key] || 0} ${label.name}`;
    return `${label.name} ${have}`;
  });
  if (hasThreshold) return `In this library: ${parts.join("; ")}.`;
  return totals ? `In this library: ${parts.join(", ")}.` : `Labels: ${parts.join(", ")}.`;
}

function labelsElsewhereNote(data) {
  const totals = labelTotals(data);
  if (!totals) return "";
  const current = data?.current || {};
  const farBelow = trainingLabels().some(label => {
    const total = Number(totals[label.key] || 0);
    return total > 0 && Number(current[label.key] || 0) < total / 2;
  });
  return farBelow ? " The other labeled tracks are not in this library." : "";
}

function profileTypeLabel() {
  return activeProfile?.profile_type === "multiclass" ? "multiclass" : "binary";
}

function profileSignalText() {
  if (isMulticlassProfile()) {
    return `${profileTypeLabel()}, ${activeProfile.description || "ready for labeling"}`;
  }
  return `${profileTypeLabel()}, positive: ${labelByKey(activeProfile.positive_label).name}, negative: ${labelByKey(activeProfile.negative_label).name}`;
}

function plural(count, one, many) {
  return Math.abs(Number(count)) === 1 ? one : many;
}

async function loadTracks(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.library = offset;
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    bpm_min: bpmFilterValue(bpmMinEl.value),
    bpm_max: bpmFilterValue(bpmMaxEl.value),
    label: labelEl.value,
    limit: String(limit),
    offset: String(offset)
  });
  params.set("order", libraryOrderEl.value);
  params.set("seed", String(libraryRandomSeed));
  appendRecipeParam(params);
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "library") return;
  visibleTrackContext = { endpoint: `/api/profiles/${activeProfile.classifier_key}/tracks`, params: params.toString(), items: data.items, offset: data.offset, limit: data.limit || limit, total: data.total };
  total = data.total;
  offset = data.offset;
  viewOffsets.library = offset;
  tracksEl.innerHTML = data.items.length ? "" : emptyTracksMessage();
  markPageDuplicates(data.items);
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
  player.update();
  updatePager(data);
  await loadSummary(sequence);
  await loadTrainingReadiness();
}

async function loadLikedTracks(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.liked = offset;
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    bpm_min: bpmFilterValue(bpmMinEl.value),
    bpm_max: bpmFilterValue(bpmMaxEl.value),
    label: labelEl.value,
    limit: String(limit),
    offset: String(offset)
  });
  params.set("liked", "yes");
  appendRecipeParam(params);
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "liked") return;
  visibleTrackContext = { endpoint: `/api/profiles/${activeProfile.classifier_key}/tracks`, params: params.toString(), items: data.items, offset: data.offset, limit: data.limit || limit, total: data.total };
  total = data.total;
  offset = data.offset;
  viewOffsets.liked = offset;
  tracksEl.innerHTML = data.items.length ? "" : emptyTracksMessage();
  markPageDuplicates(data.items);
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
  player.update();
  updatePager(data);
  await loadSummary(sequence);
  await loadTrainingReadiness();
}

async function loadCollectionTracks(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.collection = offset;
  await loadCollections();
  const collection = selectedCollection();
  if (!collection) {
    total = 0;
    offset = 0;
    tracksEl.innerHTML = '<div class="empty-state">No collection selected</div>';
    updatePager({ items: [], total: 0, limit: pageLimit(), offset: 0 });
    await loadSummary(sequence);
    await loadTrainingReadiness();
    return;
  }
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    bpm_min: bpmFilterValue(bpmMinEl.value),
    bpm_max: bpmFilterValue(bpmMaxEl.value),
    label: labelEl.value,
    collection_id: String(collection.id),
    limit: String(limit),
    offset: String(offset)
  });
  appendRecipeParam(params);
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "collection") return;
  visibleTrackContext = { endpoint: `/api/profiles/${activeProfile.classifier_key}/tracks`, params: params.toString(), items: data.items, offset: data.offset, limit: data.limit || limit, total: data.total };
  total = data.total;
  offset = data.offset;
  viewOffsets.collection = offset;
  tracksEl.innerHTML = data.items.length ? "" : emptyTracksMessage();
  markPageDuplicates(data.items);
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
  player.update();
  updatePager(data);
  await loadSummary(sequence);
  await loadTrainingReadiness();
}

async function deleteSelectedCollection() {
  const collection = selectedCollection();
  if (!collection) return;
  if (!window.confirm(`Delete the collection "${collection.name}"? Labels stay in the active profile.`)) return;
  const response = await fetch(`/api/collections/${collection.id}`, { method: "DELETE" });
  await parseJsonResponse(response);
  offset = 0;
  viewOffsets.collection = 0;
  await loadCollections();
  await loadActive({ reset: true });
}

async function loadCandidates(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.candidates = offset;
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    bpm_min: bpmFilterValue(bpmMinEl.value),
    bpm_max: bpmFilterValue(bpmMaxEl.value),
    label: labelEl.value,
    predicted: candidatePredictedEl.value,
    probability_focus: candidateMinBrokenEl.value,
    min_positive: probabilityFilterValue(),
    limit: String(limit),
    offset: String(offset)
  });
  appendRecipeParam(params);
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "candidates") return;
  visibleTrackContext = { endpoint: `/api/profiles/${activeProfile.classifier_key}/predictions`, params: params.toString(), items: data.items, offset: data.offset, limit: data.limit || limit, total: data.total };
  total = data.total;
  offset = data.offset;
  viewOffsets.candidates = offset;
  tracksEl.innerHTML = data.items.length ? "" : emptyTracksMessage();
  markPageDuplicates(data.items);
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderCandidate(track));
  });
  player.update();
  updatePager(data);
  await loadSummary(sequence);
  await loadTrainingReadiness();
}

function probabilityFilterValue() {
  const value = String(candidateMinPositiveEl.value || "").trim().replace(",", ".");
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "0";
  return String(Math.max(0, Math.min(1, parsed)));
}

function bpmFilterValue(value) {
  const text = String(value || "").trim().replace(",", ".");
  if (!text) return "";
  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  return String(parsed);
}

function emptyTracksMessage() {
  const message = activeView === "candidates"
    ? `No candidates for ${recipeText()} yet. Refresh candidates in the Training tab.`
    : "No tracks match these filters.";
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

async function openLibraryForLabels() {
  await switchView("library");
  await loadActive({ reset: true });
}

async function trainRefresh() {
  if (trainingActionElement("trainRefresh")?.disabled) return;
  if (!window.confirm(`Train a new ${activeProfile.name} model with recipe ${recipeText()} and refresh candidates?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Training…");
  startTrainingProgressPolling(activeProfile.classifier_key, "train-refresh", "Training…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedTrainingFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Training complete. Trained on ${formatLabelCounts(data.training_counts)}; updated ${data.predicted}, skipped ${data.skipped}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "train-refresh", stage: "Training complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "train-refresh", stage: "Training failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

async function runBenchmark() {
  if (trainingActionElement("runBenchmark")?.disabled) return;
  const plan = plannedBenchmarkRuns();
  const strategyLabel = BENCHMARK_STRATEGY_LABELS[benchmarkStrategy] || benchmarkStrategy;
  const warning = plan.count > BENCHMARK_RUN_WARNING ? " This is a large plan and will take a long time." : "";
  if (!window.confirm(`Run the "${strategyLabel}" benchmark for ${activeProfile.name}? ${plannedRunsText(plan)}.${warning}`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Benchmark running…");
  startTrainingProgressPolling(activeProfile.classifier_key, "benchmark", "Benchmark running…");
  try {
    const body = { strategy: benchmarkStrategy };
    if (benchmarkStrategy === "custom") body.feature_sets = [...benchmarkCustomSets];
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/benchmark`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await parseRefreshResponse(response);
    latestBenchmarkReport = data;
    const winner = data.winner?.feature_set ? ` Best recipe: ${data.winner.feature_set}.` : "";
    setWorkflowStatus(`Benchmark complete.${winner}`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "benchmark", stage: "Benchmark complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "benchmark", stage: "Benchmark failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
    renderBenchmarkResultsInPlace();
  }
}

function selectedArtifactFeatureSet(data = latestTrainingReadiness) {
  return promoteFeatureSetEl?.value
    || selectedPromotionOption(data)?.feature_set
    || selectedTrainingFeatureSet
    || null;
}

function recipeBody(featureSet) {
  return featureSet ? { feature_set: featureSet } : {};
}

function recipeText() {
  return selectedTrainingFeatureSet || latestTrainingReadiness?.feature_recipe?.feature_set || "the default recipe";
}

async function calibrateClassifier() {
  if (trainingActionElement("calibrateClassifier")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  if (!window.confirm(`Calibrate a new ${activeProfile.name} ${selectedFeatureSet || recipeText()} model on all current labels?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Calibrating…");
  startTrainingProgressPolling(activeProfile.classifier_key, "calibrate", "Calibrating…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/calibrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Calibration complete. ${data.feature_set}: ${fileName(data.artifact)}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "calibrate", stage: "Calibration complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "calibrate", stage: "Calibration failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

async function refreshCandidates() {
  if (trainingActionElement("refreshCandidates")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  setWorkflowBusy(true);
  setWorkflowStatus("Refreshing candidates…");
  startTrainingProgressPolling(activeProfile.classifier_key, "refresh", "Refreshing candidates…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Candidate refresh complete. ${data.feature_set}: updated ${data.predicted}, skipped ${data.skipped}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "refresh", stage: "Candidate refresh complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "refresh", stage: "Candidate refresh failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

async function promoteClassifier() {
  if (trainingActionElement("promoteClassifier")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  if (!window.confirm(`Promote the latest ${activeProfile.name} ${selectedFeatureSet || recipeText()} model to the main app?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Promoting…");
  startTrainingProgressPolling(activeProfile.classifier_key, "promote", "Promoting…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Promotion complete. Model ${fileName(data.model_path)}, metadata ${fileName(data.metadata_path)}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "promote", stage: "Promotion complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "promote", stage: "Promotion failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

// Fetches readiness for the current recipe and applies it. This is the only
// path that sets the Training gates, on the first render and on every refresh.
async function loadTrainingReadiness() {
  if (!activeProfile) return null;
  const profileKey = activeProfile.classifier_key;
  const requestId = ++readinessRequestId;
  const params = appendRecipeParam(new URLSearchParams());
  const query = params.toString();
  const response = await fetch(`/api/profiles/${profileKey}/training/readiness${query ? `?${query}` : ""}`);
  const data = await response.json();
  if (requestId !== readinessRequestId || !activeProfile || activeProfile.classifier_key !== profileKey) return null;
  if (!response.ok) {
    // Keep the last readiness on screen; the server says why this request failed.
    setWorkflowStatus(data.detail || response.statusText);
    return null;
  }
  latestTrainingReadiness = data;
  syncRecipeFromReadiness(data);
  normalizeBenchmarkStrategy(data);
  refreshVisibleTrackStates();
  applyTrainingReadiness(data);
  if (latestProfileSummary) {
    renderSummary(latestProfileSummary);
    renderGuidance(latestProfileSummary);
  }
  return data;
}

// Everything on the mounted Training block that depends on readiness. The
// skeleton (rack, selects, progress bar) keeps its DOM identity; only the
// readiness-driven parts are re-rendered.
function applyTrainingReadiness(data) {
  if (!data || !trainingPanelEl.querySelector(".classifier-workflow-card")) return;
  const selected = selectedPromotionOption(data);
  const chip = document.getElementById("workflowStateChip");
  if (chip) {
    chip.className = `workflow-state-chip ${data.ready ? "ready" : "blocked"}`;
    chip.textContent = data.ready ? "Ready to train" : "Not ready yet";
  }
  const recommendation = document.getElementById("workflowRecommendation");
  if (recommendation) recommendation.textContent = workflowRecommendation(data, selected);
  syncRecipeRack(data);
  updatePromoteFeatureSetOptions(data);
  const artifactState = document.getElementById("artifactState");
  if (artifactState) artifactState.textContent = artifactStateText(selected);
  const facts = document.getElementById("workflowFacts");
  if (facts) facts.innerHTML = renderWorkflowFacts(data, selected);
  const steps = document.getElementById("workflowSteps");
  if (steps) steps.innerHTML = renderWorkflowSteps(data, selected);
  updateBenchmarkControls(data);
  refreshTrainingInformation(data);
  renderTrainingModels(data, selected);
}

function syncRecipeFromReadiness(data) {
  const recipe = data?.feature_recipe?.feature_set;
  if (!recipe) return;
  selectedTrainingFeatureSet = String(recipe);
  const layer = recipeMertV2LayerFromRecipe(selectedTrainingFeatureSet);
  if (layer !== null) recipeMertV2Layer = layer;
}

function promoteBlockedTitle(selected) {
  if (!selected) return "Train and calibrate a variant first";
  if (selected.spec_compatible !== true) return selected.spec_reason || "The selected variant does not match the current feature spec";
  if (selected.calibration_status !== "calibrated") return "Calibrate the selected variant first";
  return "Promote the selected calibrated variant";
}

function trainingBlockMounted(profileKey) {
  return trainingViewProfileKey === profileKey && Boolean(trainingPanelEl.querySelector(".classifier-workflow-card"));
}

async function loadTrainingView() {
  if (!activeProfile) return;
  const profileKey = activeProfile.classifier_key;
  // Keep the mounted block on screen while readiness is in flight; only an
  // empty panel (first open, other profile) shows the loading card.
  if (!trainingBlockMounted(profileKey)) trainingPanelEl.innerHTML = renderTrainingLoading(activeProfile.name);
  try {
    const data = await loadTrainingReadiness();
    if (!activeProfile || activeProfile.classifier_key !== profileKey || activeView !== "training" || !data) return;
    await loadSummary();
    if (!activeProfile || activeProfile.classifier_key !== profileKey || activeView !== "training") return;
    if (!trainingBlockMounted(profileKey)) mountTrainingBlock(data);
  } catch (error) {
    if (activeProfile?.classifier_key === profileKey && activeView === "training" && !trainingBlockMounted(profileKey)) {
      trainingPanelEl.innerHTML = renderTrainingLoadError(error);
    }
    throw error;
  }
}

function mountTrainingBlock(data) {
  trainingPlanText = isMulticlassProfile()
    ? `Logistic regression across ${trainingLabels().map(label => label.name).join(", ")}. Each track contributes at most one class label.`
    : `Logistic regression: ${labelByKey(activeProfile.positive_label).name} vs ${labelByKey(activeProfile.negative_label).name}. Review labels stay out of training.`;
  trainingPanelEl.innerHTML = renderTrainingSkeleton();
  trainingViewProfileKey = activeProfile.classifier_key;
  promoteFeatureSetEl = document.getElementById("promoteFeatureSet");
  promoteFeatureSetEl?.addEventListener("change", () => loadTrainingReadiness().catch(showError));
  applyTrainingReadiness(data);
  renderTrainingProgress(latestWorkflowProgress);
}

function renderTrainingLoading(profileName) {
  return `<div class="training-info-card"><b>Loading training</b>
    <span class="meta training-info-text">Checking labels, feature sources and saved models for ${escapeHtml(profileName)}…</span>
  </div>`;
}

function renderTrainingLoadError(error) {
  return `<div class="training-info-card"><b>Training could not load</b>
    <span class="meta training-info-text">${escapeHtml(error?.message || String(error))}</span>
  </div>`;
}

// Static skeleton of the Training block, mounted once per profile. Everything
// that depends on readiness is filled by applyTrainingReadiness().
function renderTrainingSkeleton() {
  return `<div class="classifier-workflow-card">
    <div class="training-heading"><h1>Training</h1><span class="meta">Classifier workflow / ${escapeHtml(activeProfile.name)} · ${isMulticlassProfile() ? "Multiclass" : "Binary"}</span></div>
    <div id="trainingCoverage" class="training-coverage"></div>
    <div class="training-workflow-feedback"${workflowStatusText ? "" : " hidden"}><span id="refreshCandidatesStatus" class="meta source-status-line">${escapeHtml(workflowStatusText)}</span></div>
    <div id="trainingProgress" class="training-progress" role="status" aria-live="polite" hidden><div class="training-progress-header"><span id="trainingProgressStage"></span><b id="trainingProgressPercent">0%</b></div><div class="training-progress-track"><span id="trainingProgressBar"></span></div></div>
    <div class="training-columns">
      <section class="training-workflow tool-panel"><h2 class="section-kicker">Workflow</h2><div id="workflowSteps" class="workflow-steps"></div></section>
      <div class="training-center">
        <section class="recipe-builder tool-panel"><h2 class="section-kicker">Training recipe</h2><p class="meta">Select model features to include in the recipe.</p><div id="recipeRack" class="recipe-rack"></div><details class="recipe-details"><summary>Recipe details</summary><p class="recipe-line"><code id="recipeString"></code><span id="recipeMissing" class="recipe-missing"></span></p><p id="workflowRecommendation" class="meta"></p></details></section>
        <section id="savedVariants" class="tool-panel saved-variants"></section>
        <details class="tool-panel model-contribution" open><summary>Model contribution</summary><p class="meta">Relative feature weights in the selected variant.</p><div id="modelContribution" class="contribution-metrics"></div></details>
        <details class="tool-panel training-details"><summary>Artifact and training details</summary><label class="workflow-variant-select">Selected variant<select id="promoteFeatureSet"></select></label><p id="artifactState" class="meta"></p><div id="workflowFacts"></div><div id="trainingInformation"></div></details>
      </div>
      <div class="training-models"><section id="selectedVariant" class="tool-panel selected-variant"></section><section id="promotedModel" class="tool-panel promoted-model"></section></div>
    </div>
  </div>`;
}

function renderTrainingModels(data, selected) {
  const options = data?.artifact_summary?.promotion_options || [];
  const totals = labelTotals(data);
  document.getElementById("trainingCoverage").innerHTML = `<b class="training-state ${data.ready ? "ready" : "blocked"}" id="workflowStateChip">${data.ready ? "Ready to train in this library" : "Training needs more labels or features in this library"}</b>${coverageBars(data, true)}${totals ? `<span class="meta cross-library-labels"><span>Total labels across libraries:</span>${trainingLabels().map((label, index) => `<span class="cross-library-label ${labelRoleClass(label, index)}">${escapeHtml(label.name)} <b>${escapeHtml(totals[label.key] || 0)}</b></span>`).join("")}</span>` : ""}`;
  document.getElementById("savedVariants").innerHTML = `<header class="saved-variants-heading"><h2 class="section-kicker">Saved variants</h2><span class="meta">${options.length} saved variants</span></header>${options.length ? `<div class="variants-table"><table><thead><tr><th>#</th><th>Recipe</th><th>F1</th><th>Calibration</th></tr></thead><tbody>${options.map((row, index) => `<tr class="${row.feature_set === selected?.feature_set ? "selected" : ""}"><td>${row.rank ?? index + 1}</td><td><button type="button" class="variant-select" data-variant-select="${escapeHtml(row.feature_set)}" ${selectableOption(row) ? "" : "disabled"} aria-pressed="${row.feature_set === selected?.feature_set}" title="${escapeHtml(promotionOptionLabel(row))}">${escapeHtml(recipeTokens(row.feature_set).map(recipeTokenLabel).join(" + "))}</button></td><td title="${escapeHtml(row.macro_f1_mean ?? "Unavailable")}">${formatMetricPercent(row.macro_f1_mean)}</td><td>${escapeHtml(row.calibration_status === "calibrated" ? row.calibration_method || "Calibrated" : "Uncalibrated")}</td></tr>`).join("")}</tbody></table></div>` : '<p class="empty-state">Train a model to save the first variant.</p>'}`;
  document.getElementById("selectedVariant").innerHTML = `<h2 class="section-kicker">Selected variant</h2>${selected ? `<div class="model-score"><strong>${formatMetricPercent(selected.macro_f1_mean)}</strong><span>F1</span><span class="calibration-chip ${selected.calibration_status === "calibrated" ? "calibrated" : ""}">${selected.calibration_status === "calibrated" ? "Calibrated" : "Not calibrated"}</span></div><p>Recall ${formatMetricPercent(selected.positive_recall_mean)}</p><p class="meta">Recipe</p>${recipeChips(selected.feature_set)}<div class="model-provenance"><p>${escapeHtml(artifactProvenanceText(selected))}</p><p class="${selected.source_data_ready ? "ready" : "blocked"}">${selected.source_data_ready ? "Source data current" : escapeHtml(selected.source_data_reason || "Source data unavailable")}</p></div>${workflowButton("", "promote", "Promote", "promote-classifier", !canPromoteArtifact(data), promoteBlockedTitle(selected))}<p class="meta">${escapeHtml(selected.calibration_status === "calibrated" ? selected.spec_compatible ? "Ready for promotion." : selected.spec_reason || "Feature spec does not match." : "Calibrate before promotion.")}</p>` : '<p class="empty-state">No trained variant selected.</p>'}`;
  const model = data.promoted_model;
  const calibration = model?.calibration || {};
  document.getElementById("promotedModel").innerHTML = `<h2 class="section-kicker">Current promoted model</h2>${model && model.status !== "not_promoted" ? `<span class="calibration-chip ${model.calibration_status === "calibrated" ? "calibrated" : ""}">${model.calibration_status === "calibrated" ? `Calibrated${calibration.method ? ` · ${escapeHtml(calibration.method)}` : ""}` : "Not calibrated"}</span><p class="meta">Recipe</p>${recipeChips(model.feature_set)}<div class="promoted-metrics">${[["F1", calibration.validation_f1], ["ROC-AUC", calibration.validation_roc_auc], ["Avg precision", calibration.validation_average_precision], ["Brier", calibration.brier], ["ECE10", calibration.ece10]].map(([name, value]) => `<div><span class="meta">${name}</span><b>${name === "Brier" ? nullableNumber(value) === null ? "—" : Number(value).toFixed(3) : formatMetricPercent(value)}</b></div>`).join("")}</div><p class="model-date">Promoted ${escapeHtml(formatHumanDate(model.promoted_at))}</p>${model.status !== "ready" ? `<p class="blocked">${escapeHtml((model.manifest_errors || ["Production manifest unavailable"])[0])}</p>` : ""}` : '<p class="empty-state">No model has been promoted yet.</p>'}<p class="meta">Latest training: ${data.trained_model?.artifact ? `${escapeHtml(data.trained_model.feature_set || "Unknown recipe")} · ${escapeHtml(formatHumanDate(data.trained_model.trained_at))}` : "No training checkpoint yet"}</p>`;
  const weights = Object.entries(selected?.feature_group_weights || {});
  document.getElementById("modelContribution").innerHTML = weights.length ? weights.map(([source, weight]) => `<div><span class="meta">${escapeHtml(recipeTokenLabel(source))}</span><b>${nullableNumber(weight) === null ? "—" : Number(weight).toFixed(3)}</b></div>`).join("") : '<p class="meta">Not recorded for this artifact.</p>';
}

function renderWorkflowFacts(data, selected) {
  const featureRecipe = data?.feature_recipe || {};
  const winner = data?.artifact_summary?.benchmark_winner;
  const selectedCalibrated = selected?.calibration_status === "calibrated";
  return `
    ${trainingInfoLine("Sources", (featureRecipe.required_sources || []).map(recipeTokenLabel).join(" + ") || "none")}
    ${trainingInfoLine("Data", featureRecipe.ready ? "Ready" : recipeBlockingText(featureRecipe))}
    ${trainingInfoLine("Benchmark", winner ? `${winner.feature_set}, F1 ${formatMetricPercent(winner.macro_f1_mean)}, recall ${formatMetricPercent(winner.positive_recall_mean)}` : "Run a benchmark to compare recipes.")}
    ${trainingInfoLine("Selection", selected ? `${selected.feature_set}, rank ${selected.rank ?? "–"}, F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "Choose a trained variant.")}
    ${trainingInfoLine("Calibration", selectedCalibrated ? `${selected.calibration_method || "Calibrated"}, ready to promote` : selected ? `Not calibrated${selected.calibration_reason ? `: ${selected.calibration_reason}` : ""}` : "No variant selected.")}
    ${trainingInfoLine("Model contribution", formatFeatureGroupWeights(selected?.feature_group_weights))}
    ${trainingInfoLine("Provenance", selected ? artifactProvenanceText(selected) : "No variant selected.")}
    ${trainingInfoLine("Main app", selected ? (selected.spec_compatible === true ? "Feature spec matches; ready to promote." : selected.spec_reason || "The feature spec does not match the main app.") : "No variant selected.")}`;
}

// The six steps. Every gate here reads the readiness payload only; the
// per-class label threshold (label_threshold_ready) blocks training,
// benchmark and calibration, never labeling, refresh or promotion.
function renderWorkflowSteps(data, selected) {
  const winner = data?.artifact_summary?.benchmark_winner;
  const selectedReady = selected?.source_data_ready === true;
  const selectedCalibrated = selected?.calibration_status === "calibrated";
  const thresholdBlocked = data?.label_threshold_ready === false;
  const thresholdReason = thresholdBlocked ? labelThresholdReason(data) : "";
  const canCalibrate = Boolean(data?.calibration_ready && selectedReady && !selectedCalibrated && !thresholdBlocked);
  const canPromote = canPromoteArtifact(data);
  const trainingBlocked = readinessBlockedTitle(data);
  const benchmarkRun = benchmarkRunState(data);
  const hasSources = (data?.available_feature_sources || []).length > 0;
  const skipped = Number(data?.skipped_training_rows || 0);
  const perClassRule = `at least ${labelThreshold(data)} per class`;
  const thresholdNote = "the label minimum in step 1 is not met.";
  return `
    ${renderWorkflowStep({
      number: 1,
      title: "Collect labels",
      status: data?.labels_ready && !thresholdBlocked ? "done" : "blocked",
      body: thresholdBlocked
        ? thresholdReason
        : data?.labels_ready
          ? `Enough labels (rule: ${perClassRule}). ${labelCoverageSentence(data)}${labelsElsewhereNote(data)} New since the last training: ${formatLabelCounts(data?.added || {}, null, trainingLabels())}.`
          : skipped > 0
            ? `${skipped} labeled ${plural(skipped, "track has", "tracks have")} no current features for this recipe. Restore the features or add examples with the full feature set: ${missingLabelText(data) || perClassRule}. ${labelCoverageSentence(data)}`
            : `Add the missing labels (rule: ${perClassRule}): ${missingLabelText(data) || perClassRule}. ${labelCoverageSentence(data)}${labelsElsewhereNote(data)}`,
      action: workflowButton("openLibrary", "library", "Open library", "open-library", false, "Open the library to label tracks")
    })}
    ${renderWorkflowStep({
      number: 2,
      title: "Train model",
      status: data?.ready ? "ready" : "blocked",
      body: `${trainingPlanText} Recipe: ${recipeText()}. Evaluation metrics come first, then the saved model is refit on all current labels and candidates refresh automatically.${data?.ready ? "" : ` Not available yet: ${thresholdBlocked ? thresholdNote : trainingBlocked}`}`,
      action: workflowButton("trainRefresh", "train", "Train", "train-refresh", !data?.ready, data?.ready ? `Train ${recipeText()} and refresh candidates` : trainingBlocked)
    })}
    ${renderWorkflowStep({
      number: 3,
      title: "Benchmark recipes",
      status: winner ? "done" : benchmarkRun.runnable ? "ready" : "blocked",
      body: `${winner
        ? `Best trained recipe: ${winner.feature_set}, F1 ${formatMetricPercent(winner.macro_f1_mean)}.`
        : hasSources
          ? "Compares recipes by cross-validated macro-F1."
          : "This library has no stored feature sources to compare."}${benchmarkRun.runnable ? "" : ` Not available yet: ${thresholdBlocked ? thresholdNote : benchmarkRun.title}`}`,
      details: renderBenchmarkControls(data),
      wide: true,
      action: ""
    })}
    ${renderWorkflowStep({
      number: 4,
      title: "Calibrate variant",
      status: selectedCalibrated ? "done" : canCalibrate ? "ready" : "blocked",
      body: selectedCalibrated
        ? `${selected.feature_set} uses ${selected.calibration_method || "calibrated"} probabilities and can be promoted.`
        : thresholdBlocked
          ? `Not available yet: ${thresholdNote}`
          : selectedReady && data?.calibration_ready
            ? "Refit the selected recipe with probability calibration before promoting."
            : data?.calibration_readiness?.reason || "Train or benchmark a variant whose sources are stored in this library.",
      action: workflowButton("calibrateClassifier", "calibrate", "Calibrate", "calibrate-classifier", !canCalibrate, canCalibrate ? `Calibrate ${selected.feature_set}` : selectedCalibrated ? "The selected variant is already calibrated" : thresholdBlocked ? thresholdReason : data?.calibration_readiness?.reason || "Select a variant whose data is in this library")
    })}
    ${renderWorkflowStep({
      number: 5,
      title: "Review candidates",
      status: selectedReady ? "ready" : "blocked",
      body: selectedReady ? `Refresh predictions with ${selected.feature_set}, then review uncertain and confident candidates.` : "Train a variant whose sources are stored in this library first.",
      action: workflowButton("refreshCandidates", "refresh", "Refresh candidates", "refresh-candidates", !selectedReady, selectedReady ? `Refresh candidates with ${selected.feature_set}` : "Select a variant whose data is in this library")
    })}
    ${renderWorkflowStep({
      number: 6,
      title: "Promote model",
      status: canPromote ? "ready" : "blocked",
      body: canPromote
        ? `Promote the calibrated ${selected.feature_set} model to models/classifiers for scoring in the main app.`
        : selected && selected.spec_compatible !== true
          ? `Lab only: ${selected.spec_reason || "the feature spec does not match the main app"}.`
          : "Promotion needs a calibrated artifact whose feature spec matches the main app.",
      action: workflowButton("promoteClassifier", "promote", "Promote", "promote-classifier", !canPromote, canPromote ? "Promote the selected calibrated variant" : promoteBlockedTitle(selected))
    })}`;
}

// Per-class label threshold from readiness (label_threshold); older payloads
// fall back to the backend's fixed minimum.
function labelThreshold(data) {
  const threshold = Number(data?.label_threshold);
  return Number.isFinite(threshold) && threshold > 0 ? threshold : MIN_ROWS_PER_CLASS;
}

function labelThresholdReason(data) {
  const direct = data?.label_threshold_reason;
  if (typeof direct === "string" && direct.trim()) return direct.trim();
  const blocking = Array.isArray(data?.blocking) ? data.blocking : [];
  const texts = blocking
    .map(item => (typeof item === "string" ? item : item?.reason || item?.message || ""))
    .map(text => String(text).trim())
    .filter(Boolean);
  if (texts.length) return texts.join(" ");
  return `This library has fewer than ${labelThreshold(data)} labels per class, the minimum for training.`;
}

function canPromoteArtifact(data) {
  const selected = selectedPromotionOption(data);
  return Boolean(
    selected?.spec_compatible === true
    && selected?.calibration_status === "calibrated"
  );
}

function renderWorkflowStep({ number, title, status, body, details = "", action = "" }) {
  const short = number === 1 ? `${trainingLabels().map(label => latestTrainingReadiness?.current?.[label.key] || 0).join(" + ")} in this library` : number === 2 || number === 4 ? status === "blocked" ? "More labels or features needed" : status === "done" ? "Calibrated" : "Ready" : number === 3 ? latestTrainingReadiness?.artifact_summary?.benchmark_winner ? "Previous results available" : "Compare model recipes" : number === 5 ? status === "ready" ? "Ready" : "Train a variant first" : status === "ready" ? "Ready for the main app" : "Calibration or matching spec required";
  return `<section class="workflow-step workflow-step-${status}"><div class="workflow-step-main"><div class="workflow-step-index">${number}</div><div class="workflow-step-copy"><b>${escapeHtml(title)}</b><span class="meta">${escapeHtml(short)}</span></div><span class="workflow-state-chip ${status}">${escapeHtml(STEP_STATUS_LABELS[status] || status)}</span>${action ? `<div class="workflow-step-action">${action}</div>` : ""}</div>${details}<details class="workflow-step-details"><summary>Details</summary><p class="meta">${escapeHtml(body)}</p></details></section>`;
}

function workflowButton(id, action, label, className, disabled, title) {
  return `<button ${id ? `id="${id}"` : ""} data-training-action="${action}" type="button" class="workflow-action-button ${className}" title="${escapeHtml(title)}" ${disabled ? "disabled" : ""}>${actionIcon(action)}<span>${escapeHtml(label)}</span></button>`;
}

function actionIcon(action) {
  if (action === "library") return '<svg class="lucide lucide-library-big" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="18" x="3" y="3" rx="1" /><path d="M7 3v18" /><path d="M20.4 18.9c.2.7-.2 1.4-.9 1.6l-3.7 1c-.7.2-1.4-.2-1.6-.9L9.1 5.1c-.2-.7.2-1.4.9-1.6l3.7-1c.7-.2 1.4.2 1.6.9Z" /></svg>';
  if (action === "train") return '<svg class="lucide lucide-brain" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" /><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" /></svg>';
  if (action === "candidates") return '<svg class="lucide lucide-sparkles" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594Z" /><path d="M20 2v4" /><path d="M22 4h-4" /></svg>';
  if (action === "benchmark") return '<svg class="lucide lucide-chart-no-axes-column-increasing" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" x2="12" y1="20" y2="10" /><line x1="18" x2="18" y1="20" y2="4" /><line x1="6" x2="6" y1="20" y2="16" /></svg>';
  if (action === "calibrate") return '<svg class="lucide lucide-gauge" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 14 4-4" /><path d="M3.34 19a10 10 0 1 1 17.32 0" /></svg>';
  if (action === "refresh") return '<svg class="lucide lucide-refresh-cw" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5" /><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5" /></svg>';
  return '<svg class="lucide lucide-upload" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" x2="12" y1="3" y2="15" /></svg>';
}

function workflowRecommendation(data, selected) {
  const missing = missingLabelText(data);
  const skipped = Number(data?.skipped_training_rows || 0);
  if (data?.label_threshold_ready === false) return labelThresholdReason(data);
  if (missing && skipped > 0) return `Restore features for ${skipped} labeled ${plural(skipped, "track", "tracks")} or add ${missing} examples with the full feature set.`;
  if (missing) return `Add ${missing} before the next training run.`;
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  if (!data?.model_artifact && !(data?.artifact_summary?.promotion_options || []).length) return "Train the first model for this profile.";
  if (!data?.artifact_summary?.benchmark_winner) return "Run a benchmark to find the strongest recipe.";
  if (!selected) return "Retrain a variant on the current library data before calibrating or promoting.";
  if (selected?.calibration_status !== "calibrated" && !data?.calibration_ready) {
    return data?.calibration_readiness?.reason || "Add more labels before calibrating.";
  }
  if (selected?.calibration_status !== "calibrated") return "Calibrate the selected variant, then refresh its candidates.";
  return "Refresh and review candidates from the calibrated variant, then promote it.";
}

function missingLabelText(data) {
  const missingTrainingRows = data?.missing_training_rows || {};
  const missing = {};
  const missingRows = [];
  let hasMissing = false;
  trainingLabels().forEach(label => {
    const value = Math.max(0, Number(missingTrainingRows[label.key] || 0));
    if (value > 0) {
      missing[label.key] = value;
      missingRows.push(value);
      hasMissing = true;
    }
  });
  if (missingRows.length > 4) {
    const total = missingRows.reduce((sum, value) => sum + value, 0);
    const uniqueValues = new Set(missingRows);
    if (uniqueValues.size === 1) {
      return `${missingRows[0]} per class across ${missingRows.length} classes`;
    }
    return `${total} ${plural(total, "label", "labels")} across ${missingRows.length} classes`;
  }
  return hasMissing ? formatLabelCounts(missing) : "";
}

// ---- Training recipe builder ------------------------------------------------
// A recipe is a "+"-joined set of stored feature families in the server's
// canonical order; MERT-v2 may carry a layer as "mert_v2@N" (bare token =
// layer 24). Only families reported in available_feature_sources are offered.

function familyLabel(family) {
  return FEATURE_FAMILY_LABELS[family] || String(family || "").toUpperCase();
}

function recipeTokens(featureSet) {
  return String(featureSet || "").split("+").map(part => part.trim()).filter(Boolean);
}

function recipeTokenFamily(token) {
  return String(token || "").split("@")[0];
}

function recipeTokenLabel(token) {
  const [family, layer] = String(token || "").split("@");
  return layer ? `${familyLabel(family)} layer ${layer}` : familyLabel(family);
}

function recipeMertV2LayerFromRecipe(featureSet) {
  const token = recipeTokens(featureSet).find(item => recipeTokenFamily(item) === "mert_v2");
  if (!token) return null;
  const layer = Number(token.split("@")[1]);
  return Number.isFinite(layer) && layer > 0 ? layer : MERT_V2_DEFAULT_LAYER;
}

function storedMertV2Layers(data = latestTrainingReadiness) {
  return (data?.mert_v2_layers || []).map(Number).filter(layer => Number.isFinite(layer) && layer > 0);
}

function currentMertV2Layer(data = latestTrainingReadiness) {
  const fromRecipe = recipeMertV2LayerFromRecipe(selectedTrainingFeatureSet);
  if (fromRecipe !== null) return fromRecipe;
  if (recipeMertV2Layer !== null) return recipeMertV2Layer;
  const layers = storedMertV2Layers(data);
  return !layers.length || layers.includes(MERT_V2_DEFAULT_LAYER) ? MERT_V2_DEFAULT_LAYER : layers[layers.length - 1];
}

function selectedRecipeFamilies() {
  return new Set(recipeTokens(selectedTrainingFeatureSet).map(recipeTokenFamily));
}

function orderedFamilies(families) {
  const list = Array.from(families || []).map(String);
  return [
    ...FEATURE_FAMILY_ORDER.filter(family => list.includes(family)),
    ...list.filter(family => !FEATURE_FAMILY_ORDER.includes(family)),
  ];
}

function buildRecipe(families, layer, data = latestTrainingReadiness) {
  return orderedFamilies(data?.available_feature_sources || [])
    .filter(family => families.has(family))
    .map(family => (family === "mert_v2" && Number(layer) !== MERT_V2_DEFAULT_LAYER ? `mert_v2@${layer}` : family))
    .join("+");
}

async function applyRecipe(featureSet) {
  cancelScheduledReadinessRefresh();
  selectedTrainingFeatureSet = featureSet ? String(featureSet) : null;
  const layer = recipeMertV2LayerFromRecipe(selectedTrainingFeatureSet);
  if (layer !== null) recipeMertV2Layer = layer;
  syncRecipeRack(latestTrainingReadiness);
  await loadTrainingView();
}

async function handleTrainingControlChange(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  if (target.matches("input[data-recipe-family], select[data-recipe-layer]")) return handleRackChange(target);
  if (target.matches("#benchmarkStrategy")) {
    benchmarkStrategy = target.value;
    updateBenchmarkControls();
  }
}

// A rack click updates the recipe at once (string line only) and refetches
// readiness after a short quiet period: a burst of clicks costs one request,
// and nothing on the block is rebuilt until the new readiness arrives.
function handleRackChange(target) {
  const rackEl = document.getElementById("recipeRack");
  if (!rackEl) return;
  const layerChanged = target.matches("select[data-recipe-layer]");
  if (layerChanged) recipeMertV2Layer = Number(target.value) || MERT_V2_DEFAULT_LAYER;
  const families = new Set(
    Array.from(rackEl.querySelectorAll("input[data-recipe-family]"))
      .filter(input => input.checked)
      .map(input => input.dataset.recipeFamily)
  );
  if (!families.size) {
    if (target.matches("input")) target.checked = true;
    return;
  }
  if (layerChanged && !families.has("mert_v2")) return;
  const recipe = buildRecipe(families, layerChanged ? recipeMertV2Layer : currentMertV2Layer());
  if (!recipe || recipe === selectedTrainingFeatureSet) return;
  selectedTrainingFeatureSet = recipe;
  const tokenLayer = recipeMertV2LayerFromRecipe(recipe);
  if (tokenLayer !== null) recipeMertV2Layer = tokenLayer;
  readinessRequestId += 1;
  updateRecipeLine();
  scheduleReadinessRefresh();
}

function scheduleReadinessRefresh() {
  cancelScheduledReadinessRefresh();
  recipeRefreshTimer = window.setTimeout(() => {
    recipeRefreshTimer = null;
    loadTrainingView().catch(showError);
  }, READINESS_DEBOUNCE_MS);
}

function joinNames(names) {
  const list = names.map(String);
  if (list.length <= 1) return list.join("");
  return `${list.slice(0, -1).join(", ")} and ${list[list.length - 1]}`;
}

// The rack: one strip of equal-height slots, one per model stored in this
// library, in the mandated order. A recipe is the set of engaged slots.
function renderRecipeSlots(data) {
  const available = orderedFamilies(data?.available_feature_sources || []);
  if (!available.length) return '<span class="meta">This library has no stored feature sources.</span>';
  const selected = selectedRecipeFamilies();
  const layers = storedMertV2Layers(data);
  const layer = currentMertV2Layer(data);
  return available.map(family => {
    const layerSelect = family === "mert_v2" && layers.length
      ? `<select data-recipe-layer aria-label="MERT-v2 layer" title="MERT-v2 layer stored in this library">${layers.map(value => `<option value="${value}" ${value === layer ? "selected" : ""}>Layer ${value}</option>`).join("")}</select>`
      : "";
    return `<div class="recipe-slot">
      <label>
        <input type="checkbox" data-recipe-family="${escapeHtml(family)}" ${selected.has(family) ? "checked" : ""} />
        <span>${escapeHtml(familyLabel(family))}</span>
      </label>
      ${layerSelect}
    </div>`;
  }).join("");
}

function rackSignature(data) {
  return JSON.stringify([orderedFamilies(data?.available_feature_sources || []), storedMertV2Layers(data)]);
}

// Rebuild the slots only when the library's stored models change; otherwise
// just sync checked/layer state so the rack keeps its DOM identity.
function syncRecipeRack(data = latestTrainingReadiness) {
  const rackEl = document.getElementById("recipeRack");
  if (!rackEl || !data) return;
  const signature = rackSignature(data);
  if (rackEl.dataset.signature !== signature) {
    rackEl.innerHTML = renderRecipeSlots(data);
    rackEl.dataset.signature = signature;
  }
  const selected = selectedRecipeFamilies();
  rackEl.querySelectorAll("input[data-recipe-family]").forEach(input => {
    input.checked = selected.has(input.dataset.recipeFamily);
  });
  const layerSelect = rackEl.querySelector("select[data-recipe-layer]");
  if (layerSelect) layerSelect.value = String(currentMertV2Layer(data));
  updateRecipeLine(data);
}

function updateRecipeLine(data = latestTrainingReadiness) {
  const codeEl = document.getElementById("recipeString");
  if (codeEl) codeEl.textContent = selectedTrainingFeatureSet || "none";
  const missingEl = document.getElementById("recipeMissing");
  if (missingEl) missingEl.textContent = missingFamiliesText(data);
}

function missingFamiliesText(data) {
  const available = orderedFamilies(data?.available_feature_sources || []);
  const missing = orderedFamilies(Object.keys(data?.source_features || {}))
    .filter(family => !available.includes(family))
    .map(familyLabel);
  if (!missing.length) return "";
  return ` Not in this library: ${missing.join(", ")}. Run ${joinNames(missing)} analysis in the main app, then reload the library.`;
}

// ---- Benchmark panel ---------------------------------------------------------

function benchmarkStrategies(data = latestTrainingReadiness) {
  const hasLayers = (data?.available_feature_sources || []).includes("mert_v2") && storedMertV2Layers(data).length > 0;
  return Object.keys(BENCHMARK_STRATEGY_LABELS).filter(key => hasLayers || !key.startsWith("layers"));
}

function normalizeBenchmarkStrategy(data = latestTrainingReadiness) {
  if (!benchmarkStrategies(data).includes(benchmarkStrategy)) benchmarkStrategy = DEFAULT_BENCHMARK_STRATEGY;
}

function plannedBenchmarkRuns(data = latestTrainingReadiness) {
  const n = (data?.available_feature_sources || []).length;
  const layers = storedMertV2Layers(data).length;
  switch (benchmarkStrategy) {
    case "singles": return { count: n, bound: false };
    case "singles+all": return { count: n > 1 ? n + 1 : n, bound: false };
    case "greedy": return { count: (n * (n + 1)) / 2, bound: true };
    case "full": return { count: n ? 2 ** n - 1 : 0, bound: false };
    case "layers": return { count: layers, bound: false };
    case "layers+all": return { count: n > 1 ? layers * 2 : layers, bound: false };
    case "custom": return { count: benchmarkCustomSets.length, bound: false };
    default: return { count: 0, bound: false };
  }
}

function plannedRunsText(plan = plannedBenchmarkRuns()) {
  const runs = `${plan.count} ${plural(plan.count, "run", "runs")}`;
  return plan.bound ? `up to ${runs}` : runs;
}

function benchmarkRunState(data = latestTrainingReadiness) {
  const plan = plannedBenchmarkRuns(data);
  if (data?.labels_ready !== true || data?.label_threshold_ready === false) {
    return { runnable: false, plan, title: readinessBlockedTitle(data) };
  }
  if (plan.count <= 0) {
    return {
      runnable: false,
      plan,
      title: benchmarkStrategy === "custom" ? "Add at least one recipe to compare" : "This library has no stored feature sources",
    };
  }
  return { runnable: true, plan, title: `Run benchmark: ${BENCHMARK_STRATEGY_LABELS[benchmarkStrategy] || benchmarkStrategy}, ${plannedRunsText(plan)}` };
}

function benchmarkPlanHintText(plan) {
  const runs = plannedRunsText(plan);
  return plan.count > BENCHMARK_RUN_WARNING ? `${runs}, this will take a while` : runs;
}

function renderBenchmarkControls(data) {
  const run = benchmarkRunState(data);
  const options = benchmarkStrategies(data)
    .map(key => `<option value="${escapeHtml(key)}" ${key === benchmarkStrategy ? "selected" : ""}>${escapeHtml(BENCHMARK_STRATEGY_LABELS[key])}</option>`)
    .join("");
  return `<div class="benchmark-controls">
    <div class="benchmark-row">
      <label class="benchmark-strategy">Strategy
        <select id="benchmarkStrategy">${options}</select>
      </label>
      <span id="benchmarkPlanHint" class="benchmark-plan-hint${run.plan.count > BENCHMARK_RUN_WARNING ? " warning" : ""}">${escapeHtml(benchmarkPlanHintText(run.plan))}</span>
      ${workflowButton("runBenchmark", "benchmark", "Run benchmark", "run-benchmark", !run.runnable, run.title)}
    </div>
    <div id="benchmarkCustom" class="benchmark-custom" hidden>
      <button type="button" data-benchmark-add title="Add the current training recipe to the comparison">Add current recipe</button>
      <div id="benchmarkCustomList"></div>
    </div>
    <details class="benchmark-result-details"><summary>Benchmark results</summary><div id="benchmarkResults" class="benchmark-results">${renderBenchmarkResults()}</div></details>
  </div>`;
}

function updateBenchmarkControls(data = latestTrainingReadiness) {
  const state = benchmarkRunState(data);
  const hintEl = document.getElementById("benchmarkPlanHint");
  if (hintEl) {
    hintEl.textContent = benchmarkPlanHintText(state.plan);
    hintEl.classList.toggle("warning", state.plan.count > BENCHMARK_RUN_WARNING);
  }
  const customEl = document.getElementById("benchmarkCustom");
  if (customEl) customEl.hidden = benchmarkStrategy !== "custom";
  const listEl = document.getElementById("benchmarkCustomList");
  if (listEl) listEl.innerHTML = renderBenchmarkCustomList();
  setTrainingActionDisabled("runBenchmark", !state.runnable, state.title);
}

function addCurrentRecipeToBenchmark() {
  if (!selectedTrainingFeatureSet) return;
  if (!benchmarkCustomSets.includes(selectedTrainingFeatureSet)) benchmarkCustomSets.push(selectedTrainingFeatureSet);
  updateBenchmarkControls();
}

function removeBenchmarkRecipe(featureSet) {
  benchmarkCustomSets = benchmarkCustomSets.filter(item => item !== featureSet);
  updateBenchmarkControls();
}

function renderBenchmarkCustomList() {
  if (!benchmarkCustomSets.length) return '<span class="meta">No recipes added yet. Build a recipe in the rack and add it here.</span>';
  return `<ul class="benchmark-custom-list">${benchmarkCustomSets
    .map(featureSet => `<li><code>${escapeHtml(featureSet)}</code><button type="button" data-benchmark-remove="${escapeHtml(featureSet)}" title="Remove ${escapeHtml(featureSet)} from the comparison">Remove</button></li>`)
    .join("")}</ul>`;
}

function benchmarkResultRows(report = latestBenchmarkReport) {
  const rows = Array.isArray(report?.profile?.results) ? report.profile.results : [];
  return rows
    .map(row => {
      const cv = row?.metrics?.cross_validation || {};
      const mean = nullableNumber(cv.macro_f1_mean);
      const std = nullableNumber(cv.macro_f1_std);
      return {
        featureSet: String(row?.feature_set || ""),
        status: String(row?.status || "unknown"),
        mean: Number.isFinite(mean) ? mean : null,
        std: Number.isFinite(std) ? std : null,
        error: String(row?.error || row?.reason || ""),
      };
    })
    .sort((a, b) => {
      const aTrained = a.mean !== null;
      const bTrained = b.mean !== null;
      if (aTrained !== bTrained) return aTrained ? -1 : 1;
      if (!aTrained) return a.featureSet.localeCompare(b.featureSet);
      if (b.mean !== a.mean) return b.mean - a.mean;
      return (a.std ?? Number.POSITIVE_INFINITY) - (b.std ?? Number.POSITIVE_INFINITY);
    });
}

function formatLadderDelta(current, reference) {
  const delta = (Number(current) - Number(reference)) * 100;
  if (!Number.isFinite(delta)) return "";
  const text = Math.abs(delta).toFixed(1);
  if (Number(text) === 0) return "0.0";
  return delta > 0 ? `+${text}` : `−${text}`;
}

// The ladder: ranked by cross-validated macro-F1. The rows within one standard
// deviation of the best form a prefix of the ranking, so they are bracketed as
// a group on the left edge instead of being badged one by one.
function renderBenchmarkResults(report = latestBenchmarkReport) {
  if (!report) return '<span class="meta">Run a benchmark to compare recipes.</span>';
  const rows = benchmarkResultRows(report);
  if (!rows.length) return '<span class="meta">The benchmark returned no results.</span>';
  const trained = rows.filter(row => row.mean !== null);
  const best = trained[0] || null;
  const bandSize = best && best.std !== null ? trained.filter(row => row.mean >= best.mean - best.std).length : 0;
  const bracket = bandSize >= 2;
  const allModels = latestTrainingReadiness?.default_feature_set || null;
  const reference = trained.find(row => row.featureSet === allModels) || null;
  const body = [];
  rows.forEach((row, index) => {
    const isTrained = row.mean !== null;
    const inBand = bracket && isTrained && index < bandSize;
    const classes = [inBand ? "ladder-band" : "", isTrained ? "" : "ladder-unavailable"].filter(Boolean).join(" ");
    const score = isTrained
      ? `${(row.mean * 100).toFixed(1)}${row.std !== null ? ` ± ${(row.std * 100).toFixed(1)}` : ""}`
      : "";
    const delta = isTrained && reference ? (row === reference ? "baseline" : formatLadderDelta(row.mean, reference.mean)) : "";
    const recipe = isTrained
      ? `<code>${escapeHtml(row.featureSet)}</code>`
      : `<code>${escapeHtml(row.featureSet)}</code> <span class="meta">${escapeHtml(row.error || row.status)}</span>`;
    const action = isTrained
      ? `<button type="button" data-recipe-apply="${escapeHtml(row.featureSet)}" title="Make ${escapeHtml(row.featureSet)} the training recipe">Use this recipe</button>`
      : "";
    body.push(`<tr class="${classes}"><td class="ladder-rank">${isTrained ? index + 1 : ""}</td><td class="ladder-recipe">${recipe}</td><td class="ladder-number">${score}</td><td class="ladder-number">${delta}</td><td class="ladder-action">${action}</td></tr>`);
    if (bracket && index === bandSize - 1) {
      body.push('<tr class="ladder-band ladder-band-caption"><td></td><td colspan="4">Within noise of the best</td></tr>');
    }
  });
  const note = reference
    ? ""
    : '<p class="meta ladder-note">The all-models recipe was not in this run, so the comparison column is empty.</p>';
  return `<div class="ladder-scroll"><table class="ladder">
    <thead><tr><th class="ladder-rank">#</th><th>Recipe</th><th class="ladder-number">Macro-F1 (%)</th><th class="ladder-number">vs all models</th><th></th></tr></thead>
    <tbody>${body.join("")}</tbody>
  </table></div>${note}`;
}

function renderBenchmarkResultsInPlace() {
  const resultsEl = document.getElementById("benchmarkResults");
  if (resultsEl) resultsEl.innerHTML = renderBenchmarkResults();
}

// ---- Artifact options --------------------------------------------------------

function selectableOption(row) {
  return row?.source_data_ready === true || row?.spec_compatible === true;
}

function artifactProvenanceText(row) {
  const uuid = String(row?.source_catalog_uuid || "").trim();
  if (!uuid) return "Source library unknown";
  const short = uuid.slice(0, 8);
  return sourceCatalogUuid && uuid === sourceCatalogUuid ? `Trained on this library (${short})` : `Trained on another library (${short})`;
}

function sentenceFragment(text, fallback) {
  return String(text || fallback).trim().replace(/\.$/, "");
}

function artifactStateText(row) {
  if (!row) return "No trained variant yet.";
  const dataState = row.source_data_ready === true
    ? "Source data is current."
    : `Source data is blocked: ${sentenceFragment(row.source_data_reason, "unavailable")}.`;
  const specState = row.spec_compatible === true
    ? "Can be promoted to the main app."
    : `Cannot be promoted: ${sentenceFragment(row.spec_reason, "the feature spec does not match")}.`;
  return `${artifactProvenanceText(row)}. ${dataState} ${specState}`;
}

function recipeBlockingText(recipe) {
  const blocking = recipe?.blocking || [];
  if (!blocking.length) return "Feature recipe state is unavailable";
  return blocking
    .map(item => `${recipeTokenLabel(item.source)}: ${item.reason || FEATURE_STATE_LABELS[item.status] || item.status || "not current"}`)
    .join("; ");
}

// The reason a training gate is closed, in priority order: per-class label
// threshold (backend text verbatim), recipe data, then missing labels.
function readinessBlockedTitle(data) {
  if (data?.label_threshold_ready === false) return labelThresholdReason(data);
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  return `Add the missing labels: ${missingLabelText(data) || `at least ${labelThreshold(data)} per class`}.`;
}

function updatePromoteFeatureSetOptions(data) {
  if (!promoteFeatureSetEl) return;
  const options = data?.artifact_summary?.promotion_options || [];
  const usableOptions = options.filter(selectableOption);
  const selected = selectedPromotionOption(data);
  const previous = promoteFeatureSetEl.value;
  promoteFeatureSetEl.innerHTML = options.length
    ? renderPromotionOptions(options)
    : '<option value="">No trained model</option>';
  const allowedValues = new Set(usableOptions.map(row => String(row.feature_set || "")));
  promoteFeatureSetEl.value = allowedValues.has(previous) ? previous : String(selected?.feature_set || "");
  promoteFeatureSetEl.disabled = usableOptions.length === 0;
}

function selectedPromotionOption(data) {
  // A variant is selectable when it can be refreshed here (source data ready)
  // or promoted to the main app (spec compatible); each action gates itself.
  const options = (data?.artifact_summary?.promotion_options || []).filter(selectableOption);
  const requested = promoteFeatureSetEl?.value;
  const latestPromotable = data?.artifact_summary?.latest_promotable;
  return options.find(row => row.feature_set === requested)
    || (selectableOption(latestPromotable) ? latestPromotable : null)
    || options[0]
    || null;
}

function renderPromotionOptions(options) {
  return options.length
    ? options.map(row => `<option value="${escapeHtml(String(row.feature_set || ""))}" ${selectableOption(row) ? "" : "disabled"}>${escapeHtml(promotionOptionLabel(row))}</option>`).join("")
    : '<option value="">No trained model</option>';
}

function promotionOptionLabel(row) {
  const rank = row.rank ? `rank ${row.rank}` : "unranked";
  const calibration = row.calibration_status === "calibrated"
    ? `calibrated ${row.calibration_method || ""}`.trim()
    : "not calibrated";
  const uuid = String(row.source_catalog_uuid || "").trim();
  const provenance = !uuid ? "unknown library" : sourceCatalogUuid && uuid === sourceCatalogUuid ? "this library" : "another library";
  const state = `${row.source_data_ready === true ? "data current" : "data blocked"}, ${row.spec_compatible === true ? "promotable" : "not promotable"}`;
  return `${row.feature_set || "model"}, ${rank}, F1 ${formatMetricPercent(row.macro_f1_mean)}, ${calibration}, ${formatHumanDate(row.created_at)}, ${provenance}, ${state}`;
}

function formatFeatureGroupWeights(weights) {
  if (!weights || typeof weights !== "object") return "Not recorded for this artifact.";
  const entries = Object.entries(weights);
  if (!entries.length) return "Not recorded for this artifact.";
  return entries
    .map(([source, value]) => `${recipeTokenLabel(source)} ${Number(value).toFixed(3)}`)
    .join(", ");
}

function refreshTrainingInformation(data) {
  const informationEl = document.getElementById("trainingInformation");
  if (!informationEl || !data) return;
  informationEl.innerHTML = renderTrainingInformationMetrics(data);
}

function renderTrainingInformationMetrics(data) {
  return `<section class="training-info-card">
    <header class="training-info-heading">
      <b>Training overview</b>
      <span class="meta">The latest training checkpoint and the promoted model that scores tracks.</span>
    </header>
    <div class="meta training-info-text">
      ${renderTrainingLastRunLine(data)}
      ${renderTrainingPromotedModelLine(data?.promoted_model)}
      ${renderTrainingMetricsLine(data?.promoted_model)}
      ${renderTrainingDynamicsLine(data?.metrics_history)}
    </div>
  </section>`;
}

function renderTrainingLastRunLine(data) {
  const model = data?.trained_model;
  if (!model?.artifact) {
    return trainingInfoLine("Trained model", "No training checkpoint recorded yet.");
  }
  return trainingInfoLine(
    "Trained model",
    `Latest checkpoint: ${model.feature_set || "unknown recipe"}, ${formatHumanDate(model.trained_at)}, ${formatLabelCounts(model.label_counts || {})}`
  );
}

function renderTrainingPromotedModelLine(model) {
  if (!model || model.status === "not_promoted") {
    return trainingInfoLine("Promoted model", "No model has been promoted yet.");
  }
  const status = model.status === "ready"
    ? "ready for scoring"
    : `invalid: ${(model.manifest_errors || ["the production manifest is unusable"])[0]}`;
  const promotedAt = model.promoted_at ? formatHumanDate(model.promoted_at) : "date unknown";
  return trainingInfoLine(
    "Promoted model",
    `${model.feature_set || "unknown recipe"}, promoted ${promotedAt}, ${status}`
  );
}

function renderTrainingMetricsLine(model) {
  if (!model || model.status !== "ready") {
    return trainingInfoLine("Quality", "No promoted model.json to assess scoring quality.");
  }
  const calibration = model.calibration || {};
  const calibrationState = model.calibration_status === "calibrated"
    ? `calibrated${calibration.method ? ` (${calibration.method})` : ""}`
    : `not calibrated${calibration.reason ? `: ${calibration.reason}` : ""}`;
  const values = [
    `variant ${model.feature_set || "unknown recipe"}`,
    calibrationState,
    `scoring: ${model.score_semantics || "not recorded"}`,
    metricPercentText("validation F1", calibration.validation_f1),
    metricPercentText("ROC-AUC", calibration.validation_roc_auc),
    metricPercentText("average precision", calibration.validation_average_precision),
    metricNumberText("Brier", calibration.brier),
    metricPercentText("ECE10", calibration.ece10),
  ].filter(Boolean).join(", ");
  return trainingInfoLine("Quality", `Promoted model.json: ${values}`);
}

function metricPercentText(label, value) {
  return nullableNumber(value) !== null ? `${label} ${formatMetricPercent(value)}` : "";
}

function metricNumberText(label, value) {
  const number = nullableNumber(value);
  return number !== null ? `${label} ${number.toFixed(3)}` : "";
}

function renderTrainingDynamicsLine(history) {
  const latest = (history || [])[0];
  const previous = (history || [])[1];
  if (!latest) return trainingInfoLine("Change", `Train ${recipeText()} to set a baseline.`);
  const trend = previous
    ? `vs the previous run: accuracy ${formatMetricDelta(latest.accuracy_mean, previous.accuracy_mean)}, F1 ${formatMetricDelta(latest.macro_f1_mean, previous.macro_f1_mean)}`
    : "First recorded model for this recipe.";
  return trainingInfoLine(
    "Change",
    `${trend}; ${formatHumanDate(latest.created_at)}, labeled tracks: ${latest.trained_rows ?? "–"}, accuracy ${formatMetricPercent(latest.accuracy_mean)}, F1 ${formatMetricPercent(latest.macro_f1_mean)}`
  );
}

function trainingInfoLine(label, text) {
  return `<span class="training-info-line"><b class="training-info-label">${escapeHtml(label)}</b><span class="training-info-value">${escapeHtml(text)}</span></span>`;
}

async function loadSettingsView() {
  tracksEl.innerHTML = "";
  await loadSummary();
}

function renderTrack(track) {
  const row = document.createElement("section");
  row.className = "track";
  row.tabIndex = 0;
  row.dataset.trackId = String(track.track_id);
  row.dataset.trackUuid = String(track.track_uuid || "");
  row.dataset.catalogUuid = String(track.catalog_uuid || "");
  row.innerHTML = trackMarkup(track);
  wireTrackRow(row, track);
  return row;
}

function renderCandidate(track) {
  return renderTrack(track);
}

function formatMaestGenreLabel(label) {
  return String(label).replace(/_/g, " ").split("---").pop()?.trim() || "";
}

function genreBadges(track) {
  const scores = track.maest_genre_scores || {};
  return (track.genres || [])
    .map(rawGenre => {
      const genre = formatMaestGenreLabel(rawGenre);
      if (!genre) return "";
      const score = Number(scores[rawGenre]);
      const confidence = Number.isFinite(score) ? `<b>${Math.round(score * 100)}%</b>` : "";
      return `<span class="maest-genre-pill" title="${escapeHtml(genre)}"><span class="genre-name">${escapeHtml(genre)}</span>${confidence}</span>`;
    })
    .join("");
}

function trackMarkup(track) {
  const candidates = activeView === "candidates";
  const score = predictedScore(track);
  const validScore = score !== null && score !== undefined && Number.isFinite(Number(score));
  const label = labelByKey(track.predicted_label);
  return `<span class="row-index">${track.rowNumber}</span>
    <div class="row-play"><button type="button" class="track-play-button" data-action="play" aria-label="Play ${escapeHtml(displayTrackTitle(track))}" title="Play"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m8 5 11 7-11 7z"/></svg></button></div>
    <div class="track-details"><strong class="track-heading"><span class="track-title-main">${escapeHtml(displayTrackTitle(track))}</span>${activeView === "library" ? featuresIndicator(track) : ""}</strong><span class="track-artist">${escapeHtml(track.artist || "Unknown Artist")}</span>${activeView === "library" || activeView === "liked" ? `<span class="meta track-path" title="${escapeHtml(track.file_path)}">${escapeHtml(track.file_path)}</span>` : ""}${badgeRow(track)}</div>
    <div class="track-genres">${genreBadges(track)}${syncopatedBadge(track)}</div>
    ${candidates ? `<div class="track-score" title="${validScore ? escapeHtml(formatProbability(score)) : "Score unavailable"}"><span>${validScore ? Number(score).toFixed(6) : "—"}</span><span class="score-track"><i style="width:${validScore ? Math.max(0, Math.min(1, Number(score))) * 100 : 0}%"></i></span></div><div class="track-prediction ${labelRoleClass(label, activeProfile.labels.indexOf(label))}">${track.predicted_label ? escapeHtml(displayLabel(track.predicted_label)) : "—"}</div>` : activeView === "collection" ? "" : `<div class="track-state">${renderTrackState(track)}</div>`}
    <div class="track-actions">${renderLikeButton(track)}<div class="label-actions ${isMulticlassProfile() ? "multiclass-label-actions" : ""}">${hasContentKey(track) ? renderLabelButtons(track) : noFingerprintHint()}</div></div>`;
}

function renderTrackState(track) {
  const status = `<span class="track-state-primary ${track.label_trained ? "ready" : "warning"}"><span class="status-dot" aria-hidden="true"></span>${track.label_trained ? "Trained" : "Not trained"}</span>`;
  if (activeView !== "liked") return status;
  return `${status}<span class="meta">${track.label_trained_at ? escapeHtml(formatHumanDate(track.label_trained_at)) : "—"}</span>`;
}

function refreshVisibleTrackStates() {
  if (!visibleTrackContext || !activeProfile || activeView !== "library") return;
  tracksEl.querySelectorAll(".track").forEach(row => {
    const track = visibleTrackContext.items.find(item => String(item.track_id) === row.dataset.trackId);
    if (!track) return;
    const state = row.querySelector(".track-state");
    if (state) state.innerHTML = renderTrackState(track);
    const heading = row.querySelector(".track-heading");
    if (heading) {
      heading.querySelector(".features-indicator")?.remove();
      heading.insertAdjacentHTML("beforeend", featuresIndicator(track));
    }
  });
}

function renderTrackHeader() {
  const candidates = activeView === "candidates";
  document.getElementById("trackTableHeader").innerHTML = `<span class="row-index">#</span><span class="row-play"></span><span class="track-details">Track</span><span class="track-genres">${candidates ? "" : "Genres"}</span>${candidates ? `<span class="track-score">${isMulticlassProfile() ? "Confidence" : `P(${escapeHtml(activeProfile ? labelByKey(activeProfile.positive_label).name : "positive")})`}</span><span class="track-prediction">Predicted</span>` : activeView === "collection" ? "" : `<span class="track-state">${activeView === "liked" ? "Trained" : "Status"}</span>`}<span class="track-actions">${candidates ? "Your label" : "Label"}</span>`;
  const hints = document.getElementById("keyboardHints");
  if (hints) {
    hints.hidden = !candidates;
    hints.innerHTML = activeProfile ? activeProfile.labels.slice(0, 9).map((label, index) => `<span><kbd>${index + 1}</kbd> ${escapeHtml(label.name)}</span>`).join("") + '<span><kbd>0</kbd> Clear label</span>' : "";
  }
}

function updatePlayingRows({ track, playing }) {
  tracksEl.querySelectorAll(".track").forEach(row => {
    const active = Boolean(track && row.dataset.trackId === String(track.track_id) && row.dataset.trackUuid === String(track.track_uuid || "") && row.dataset.catalogUuid === String(track.catalog_uuid || ""));
    row.classList.toggle("selected", active);
    row.classList.toggle("playing", active && playing);
    const button = row.querySelector('[data-action="play"]');
    if (button) {
      button.setAttribute("aria-label", active && playing ? "Pause" : "Play");
      button.title = active && playing ? "Pause" : "Play";
      button.innerHTML = active && playing ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>' : '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m8 5 11 7-11 7z"/></svg>';
    }
  });
}

function hasContentKey(track) {
  return typeof track?.content_key === "string" && track.content_key.length > 0;
}

function noFingerprintHint() {
  return '<span class="meta label-hint" title="Labels are bound to the SONARA fingerprint, and this track has none yet">No SONARA fingerprint for this track. Analyze it in the main app.</span>';
}

function markPageDuplicates(items) {
  const seen = new Set();
  (items || []).forEach(track => {
    const key = hasContentKey(track) ? track.content_key : null;
    track.duplicateOnPage = key !== null && seen.has(key);
    if (key !== null) seen.add(key);
  });
  return items;
}

function duplicateBadge(track) {
  return track.duplicateOnPage
    ? '<span class="profile-label-badge duplicate-badge" title="Same audio as a row above on this page; the rows share one label">Duplicate</span>'
    : "";
}

function renderLikeButton(track) {
  const active = track.liked ? " active intent-liked" : "";
  const fill = track.liked ? "currentColor" : "none";
  const title = track.liked ? "Remove from liked" : "Add to liked";
  return `
    <button type="button" class="icon-button track-like-button${active}" data-action="like" title="${title}" aria-label="${title}" aria-pressed="${track.liked ? "true" : "false"}">
      <svg class="lucide lucide-heart" aria-hidden="true" viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
      </svg>
    </button>`;
}

function renderLabelButtons(track) {
  const buttons = activeProfile.labels.map((label, index) => {
    const active = track.label === label.key;
    const shortcut = index < 9 ? ` (key ${index + 1})` : "";
    return `<button type="button" class="${labelRoleClass(label, index)}${active ? " active" : ""}" data-action="label" data-label="${escapeHtml(label.key)}" aria-pressed="${active ? "true" : "false"}" title="${escapeHtml(`${label.name}${shortcut}`)}">${escapeHtml(label.name)}</button>`;
  });
  buttons.push('<button type="button" class="label-clear" data-action="label" data-label="" title="Clear the label (key 0)" aria-label="Clear label">↶</button>');
  return buttons.join("");
}

function wireTrackRow(row, track) {
  const context = visibleTrackContext;
  const likeButton = row.querySelector('[data-action="like"]');
  if (likeButton) likeButton.addEventListener("click", () => toggleLike(track).catch(showError));
  row.querySelector('[data-action="play"]').addEventListener("click", () => { if (!sourceSwitchPending) player.select(track, context, track.rowNumber - 1); });
  row.querySelectorAll('[data-action="label"]').forEach(button => {
    button.addEventListener("click", () => setLabel(track.track_id, button.dataset.label).catch(showError));
  });
  row.addEventListener("keydown", event => {
    if (sourceSwitchPending) return;
    if (event.key === " " && event.target === row) {
      event.preventDefault();
      player.select(track, context, track.rowNumber - 1);
      return;
    }
    if (!hasContentKey(track) || event.ctrlKey || event.altKey || event.metaKey) return;
    const keys = { "0": "" };
    activeProfile.labels.forEach((label, index) => { if (index < 9) keys[String(index + 1)] = label.key; });
    if (keys[event.key] !== undefined) { event.preventDefault(); setLabel(track.track_id, keys[event.key]).catch(showError); }
  });
}

async function toggleLike(track) {
  const response = await fetch(`/api/tracks/${track.track_id}/liked`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      catalog_uuid: track.catalog_uuid,
      track_uuid: track.track_uuid,
      liked: !track.liked
    })
  });
  await parseJsonResponse(response);
  await loadActive();
}

async function setLabel(trackId, label) {
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks/${trackId}/label`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label })
  });
  await parseJsonResponse(response);
  await loadActive();
}

async function createProfile(event) {
  event.preventDefault();
  const response = await fetch("/api/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      classifier_key: document.getElementById("newProfileKey").value,
      profile_type: document.getElementById("newProfileType").value,
      name: document.getElementById("newProfileName").value,
      description: document.getElementById("newProfileDescription").value,
      training_min_added: Number(document.getElementById("newProfileTrainingMinAdded").value || 50),
      training_min_labels: Number(document.getElementById("newProfileTrainingMinLabels").value || 100),
      labels: collectNewProfileLabels()
    })
  });
  const profile = await parseJsonResponse(response);
  profileDialogEl.close();
  await loadProfiles();
  await setActiveProfile(profile.classifier_key);
}

function collectNewProfileLabels() {
  if (newProfileTypeEl.value === "multiclass") {
    return Array.from(multiclassLabelRowsEl.querySelectorAll(".multiclass-label-row"))
      .map(row => ({
        key: row.querySelector(".multiclass-label-key").value,
        name: row.querySelector(".multiclass-label-name").value,
        description: row.querySelector(".multiclass-label-description").value,
        role: "class"
      }))
      .filter(label => label.key.trim());
  }
  const labels = [
    {
      key: document.getElementById("newPositiveKey").value,
      name: document.getElementById("newPositiveName").value,
      role: "positive"
    },
    {
      key: document.getElementById("newNegativeKey").value,
      name: document.getElementById("newNegativeName").value,
      role: "negative"
    }
  ];
  const reviewKey = document.getElementById("newReviewKey").value.trim();
  if (reviewKey) {
    labels.push({
      key: reviewKey,
      name: document.getElementById("newReviewName").value || reviewKey,
      role: "review"
    });
  }
  return labels;
}

function updateNewProfileTypeControls() {
  const multiclass = newProfileTypeEl.value === "multiclass";
  binaryLabelGridEl.hidden = multiclass;
  multiclassLabelEditorEl.hidden = !multiclass;
  binaryLabelGridEl.querySelectorAll("input").forEach(input => { input.required = !multiclass && ["newPositiveKey", "newPositiveName", "newNegativeKey", "newNegativeName"].includes(input.id); });
  multiclassLabelRowsEl.querySelectorAll(".multiclass-label-key, .multiclass-label-name").forEach(input => { input.required = multiclass; });
  document.querySelectorAll("[data-profile-type]").forEach(button => {
    const active = button.dataset.profileType === newProfileTypeEl.value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  document.getElementById("newProfileTypeHint").textContent = multiclass ? "Choose one class for each track." : "Two training classes and one optional review label.";
  updateNewProfilePreview();
}

function updateNewProfilePreview() {
  const multiclass = newProfileTypeEl.value === "multiclass";
  const labels = multiclass ? Array.from(multiclassLabelRowsEl.querySelectorAll(".multiclass-label-row")).map((row, index) => ({ name: row.querySelector(".multiclass-label-name").value || `Class ${index + 1}`, role: "class" })) : [{ name: document.getElementById("newPositiveName").value || "Positive", role: "positive" }, { name: document.getElementById("newNegativeName").value || "Negative", role: "negative" }, ...(document.getElementById("newReviewKey").value.trim() ? [{ name: document.getElementById("newReviewName").value || document.getElementById("newReviewKey").value, role: "review" }] : [])];
  multiclassLabelRowsEl.querySelectorAll(".multiclass-label-row").forEach((row, index) => { row.className = `multiclass-label-row role-class label-color-${index % 7}`; });
  document.getElementById("newProfileLabelPreview").innerHTML = labels.map((label, index) => `<span class="preview-label ${labelRoleClass(label, index)}"><span class="label-dot"></span>${escapeHtml(label.name)}</span>`).join("");
  document.getElementById("newProfileFooterSummary").textContent = multiclass ? `Multiclass · ${labels.length} classes` : `Binary · 2 training classes${labels.length > 2 ? " + 1 review label" : ""}`;
}

function addMulticlassLabelRow() {
  const row = document.createElement("div");
  row.className = "multiclass-label-row";
  row.innerHTML = `
    <div class="class-row-heading"><span class="label-dot"></span><b>Class ${multiclassLabelRowsEl.children.length + 1}</b></div>
    <label>Class key <input class="multiclass-label-key" placeholder="dreamy" /></label>
    <label>Class name <input class="multiclass-label-name" placeholder="Dreamy" /></label>
    <label>Description <textarea class="multiclass-label-description" placeholder="Optional class description"></textarea></label>`;
  multiclassLabelRowsEl.appendChild(row);
  updateNewProfileTypeControls();
}

async function updateProfile(event) {
  event.preventDefault();
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: document.getElementById("profileNameInput").value,
      description: document.getElementById("profileDescriptionInput").value,
      artifact_prefix: document.getElementById("profileArtifactPrefixInput").value,
      training_min_added: Number(document.getElementById("profileTrainingMinAddedInput").value || 50),
      training_min_labels: Number(document.getElementById("profileTrainingMinLabelsInput").value || 100)
    })
  });
  const profile = await parseJsonResponse(response);
  await loadProfiles();
  await setActiveProfile(profile.classifier_key, { skipLoad: true });
  setWorkflowStatus("Profile saved");
}

async function renameLabel(event) {
  event.preventDefault();
  const oldKey = document.getElementById("renameLabelSelect").value;
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/labels/${oldKey}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      new_key: document.getElementById("renameLabelKeyInput").value,
      name: document.getElementById("renameLabelNameInput").value || null
    })
  });
  const profile = await parseJsonResponse(response);
  await loadProfiles();
  await setActiveProfile(profile.classifier_key, { skipLoad: true });
  await loadActive({ reset: true });
}

async function deleteActiveProfile() {
  if (!activeProfile) return;
  const confirmation = window.prompt(
    `Delete ${activeProfile.name}? This permanently removes the profile's Rhythm Lab labels, predictions, labeling queue, checkpoints, metrics and local training artifacts. Promoted models in models/classifiers stay.\n\nType "${activeProfile.name}" or "${activeProfile.classifier_key}" to delete.`
  );
  if (confirmation === null) return;
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: confirmation })
  });
  const data = await parseJsonResponse(response);
  const deletedFiles = data.artifact_cleanup?.deleted_files || 0;
  setWorkflowStatus(`Deleted ${data.name} and ${deletedFiles} artifact ${plural(deletedFiles, "file", "files")}`);
  activeProfile = null;
  await loadProfiles();
  await loadActive({ reset: true });
}

async function parseRefreshResponse(response) {
  const data = await response.json();
  if (!response.ok) {
    setWorkflowStatus(data.detail || response.statusText);
    throw new Error(data.detail || response.statusText);
  }
  return data;
}

async function parseJsonResponse(response) {
  if (response instanceof Response) {
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || response.statusText);
    return data;
  }
  return response.json();
}

function pageLimit() {
  return Number(pageSizeEl.value || 100);
}

function pageCount(totalItems, limit) {
  return totalItems > 0 ? Math.ceil(totalItems / Math.max(1, limit)) : 0;
}

function currentPage(data) {
  const pages = pageCount(data.total, data.limit);
  return pages ? Math.floor(data.offset / Math.max(1, data.limit)) + 1 : 0;
}

function maxPageOffset(totalItems, limit) {
  const pages = pageCount(totalItems, limit);
  return pages ? (pages - 1) * Math.max(1, limit) : 0;
}

function jumpToPage() {
  const limit = pageLimit();
  const pages = pageCount(total, limit);
  const requested = Number.parseInt(pageNumberEl.value || "1", 10);
  const targetPage = Math.min(Math.max(Number.isFinite(requested) ? requested : 1, 1), Math.max(1, pages));
  pageNumberEl.value = String(targetPage);
  offset = (targetPage - 1) * limit;
  loadActive();
}

function updatePager(data) {
  const shown = data.items.length;
  const first = shown ? data.offset + 1 : 0;
  const last = shown ? data.offset + shown : 0;
  const pages = pageCount(data.total, data.limit);
  const current = currentPage(data);
  pageInfoEl.textContent = data.total > 0 ? `${first}–${last} of ${data.total}, page ${current} of ${pages}` : "No tracks";
  pageNumberEl.value = String(current || 1);
  pageNumberEl.max = String(Math.max(1, pages));
  pageNumberEl.disabled = pages <= 0;
  prevPageEl.disabled = data.offset <= 0;
  nextPageEl.disabled = data.offset + data.limit >= data.total;
}

function badgeRow(track) {
  const badges = [duplicateBadge(track)].filter(Boolean);
  return badges.length ? `<div class="badge-row">${badges.join("")}</div>` : "";
}

function syncopatedBadge(track) {
  return track.maest_syncopated_rhythm === true
    ? `<span class="syncopated-rhythm-indicator" role="img" aria-label="Syncopated rhythm" title="MAEST detected a syncopated rhythm">
        <svg class="lucide lucide-audio-waveform" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 12h.01" /><path d="M6 12v4" /><path d="M10 12v-2" /><path d="M14 12v6" /><path d="M18 12v-8" /><path d="M22 12v2" />
        </svg>
      </span>`
    : "";
}

function displayLabel(key) {
  if (!key || key === "none") return "none";
  return labelByKey(key).name || key;
}

function displayTrackTitle(track) {
  return track.title || fileName(track.file_path) || "Untitled track";
}

function nullableNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatProbability(value) {
  const number = nullableNumber(value);
  return number === null ? "—" : formatScore(number);
}

function formatScore(number) {
  if (number < 1 && number.toFixed(6) === "1.000000") return "0.999999";
  return number.toFixed(6);
}

function formatMetricPercent(value) {
  const number = nullableNumber(value);
  return number === null ? "—" : `${(number * 100).toFixed(1)}%`;
}

function formatMetricDelta(current, previous) {
  const currentNumber = nullableNumber(current);
  const previousNumber = nullableNumber(previous);
  if (currentNumber === null || previousNumber === null) return "—";
  const delta = (currentNumber - previousNumber) * 100;
  const sign = delta < 0 ? "−" : "+";
  return `${sign}${Math.abs(delta).toFixed(1)} pp`;
}

function formatHumanDate(value) {
  const date = parseTrainingDate(value);
  if (!date) return "never";
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function parseTrainingDate(value) {
  if (!value) return null;
  const text = String(value);
  const compact = text.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  if (compact) {
    const [, year, month, day, hour, minute, second] = compact;
    return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second)));
  }
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const date = new Date(hasTimezone ? normalized : `${normalized}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes)) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileName(path) {
  return path ? String(path).split(/[\\/]/).pop() : "";
}

function trackFeatureState(track, source) {
  return track.feature_status?.[recipeTokenFamily(source)];
}

function featuresReady(track) {
  return requiredFeatureSources().every(source => featureStateStatus(trackFeatureState(track, source)) === "current");
}

function missingFeatures(track) {
  return requiredFeatureSources()
    .filter(source => featureStateStatus(trackFeatureState(track, source)) !== "current")
    .map(source => {
      const state = trackFeatureState(track, source);
      const status = featureStateStatus(state);
      return `${recipeTokenLabel(source)} (${FEATURE_STATE_LABELS[status] || status}: ${featureStateReason(state) || "not current"})`;
    });
}

function featuresIndicator(track) {
  const required = requiredFeatureSources();
  if (!required.length) return "";
  const ready = featuresReady(track);
  const recipe = latestTrainingReadiness?.feature_recipe?.feature_set || required.join("+");
  const label = ready
    ? `Features for ${recipe} are ready: ${required.map(recipeTokenLabel).join(", ")}`
    : `${recipe} is missing: ${missingFeatures(track).join(", ")}`;
  return `<span class="features-indicator ${ready ? "ready" : "missing"}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${ready ? "✓" : "!"}</span>`;
}

function requiredFeatureSources() {
  return latestTrainingReadiness?.feature_recipe?.required_sources || [];
}

function featureStateStatus(state) {
  if (typeof state === "boolean") return state ? "current" : "missing";
  const status = String(state?.status || "missing");
  return ["current", "missing", "stale"].includes(status) ? status : "missing";
}

function featureStateReason(state) {
  return typeof state === "object" && state ? String(state.reason || "") : "";
}

function predictedScore(track) {
  if (isMulticlassProfile()) return track.confidence;
  return positiveScore(track);
}

function positiveScore(track) {
  const positive = nullableNumber(track.positive_probability);
  const negative = nullableNumber(track.negative_probability);
  if (positive === 1 && negative > 0 && negative < 1) return 1 - negative;
  return positive;
}

function showError(error) {
  const message = error.message || String(error);
  if (profileDialogEl.open) {
    const dialogError = document.getElementById("newProfileError");
    dialogError.textContent = message;
    dialogError.hidden = false;
  }
  setWorkflowStatus(message);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

init().catch(showError);
