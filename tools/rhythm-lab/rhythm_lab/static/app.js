const tracksEl = document.getElementById("tracks");
const queryEl = document.getElementById("query");
const sourcePathEl = document.getElementById("sourcePath");
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
const DEFAULT_TRAINING_FEATURE_SET = "sonara+mert+maest+clap+muq";

let profiles = [];
let activeProfile = null;
let offset = 0;
let total = 0;
let activeAudio = null;
let activeView = "library";
let collections = [];
const viewOffsets = { library: 0, candidates: 0, liked: 0, collection: 0, training: 0, settings: 0 };
let loadSequence = 0;
let libraryRandomSeed = makeLibraryRandomSeed();
let latestTrainingReadiness = null;
let latestProfileSummary = null;
let promoteFeatureSetEl = null;
let trainingFeatureSetEl = null;
let selectedTrainingFeatureSet = DEFAULT_TRAINING_FEATURE_SET;
let trainingProgressPollHandle = null;
let trainingProgressPollGeneration = 0;
let trainingProgressHasStarted = false;
let latestWorkflowProgress = { status: "idle" };
let workflowStatusText = "";

document.getElementById("load").addEventListener("click", () => loadActive({ reset: true }));
document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(showError));
document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(showError));
document.getElementById("newProfile").addEventListener("click", () => profileDialogEl.showModal());
shutdownLabEl.addEventListener("click", () => shutdownLab().catch(showError));
deleteProfileEl.addEventListener("click", () => deleteActiveProfile().catch(showError));
document.getElementById("cancelProfileButton").addEventListener("click", () => profileDialogEl.close());
document.getElementById("newProfileForm").addEventListener("submit", event => createProfile(event).catch(showError));
document.getElementById("newProfileType").addEventListener("change", updateNewProfileTypeControls);
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
summaryCoverageEl.addEventListener("click", event => {
  const likedButton = event.target instanceof Element ? event.target.closest("#likedTab") : null;
  if (likedButton) switchView("liked");
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
  addOption(profileSelectEl, "", "Choose profile");
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
  latestTrainingReadiness = null;
  latestProfileSummary = null;
  promoteFeatureSetEl = null;
  trainingFeatureSetEl = null;
  selectedTrainingFeatureSet = DEFAULT_TRAINING_FEATURE_SET;
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
  latestTrainingReadiness = null;
  latestProfileSummary = null;
  promoteFeatureSetEl = null;
  trainingFeatureSetEl = null;
  selectedTrainingFeatureSet = DEFAULT_TRAINING_FEATURE_SET;
  profileSelectEl.value = "";
  summaryCoverageEl.textContent = "";
  summaryLabelsEl.textContent = "";
  pageInfoEl.textContent = "";
  tracksEl.innerHTML = "";
  trainingPanelEl.innerHTML = "";
  guidancePanelEl.innerHTML = '<div class="guidance-card"><b>Choose profile</b><span class="meta">Select or create a classifier profile before loading tracks.</span></div>';
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "all labels");
  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "all predictions");
  document.getElementById("profileNameInput").value = "";
  document.getElementById("profileDescriptionInput").value = "";
  document.getElementById("profileArtifactPrefixInput").value = "";
  document.getElementById("profileTrainingMinAddedInput").value = "50";
  document.getElementById("renameLabelSelect").innerHTML = "";
  deleteProfileEl.disabled = true;
  setWorkflowBusy(true);
  updateLibraryOrderControls();
}

function invalidateActiveLoads() {
  loadSequence += 1;
}

function renderProfileControls() {
  deleteProfileEl.disabled = false;
  setTrainingActionDisabled("openLibrary", false);
  setTrainingActionDisabled("openCandidates", true);
  setTrainingActionDisabled("runBenchmark", true);
  setTrainingActionDisabled("calibrateClassifier", true);
  setTrainingActionDisabled("refreshCandidates", true);
  setTrainingActionDisabled("promoteClassifier", true, "Train a model before promoting");
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "all labels");
  addOption(labelEl, "unlabeled", "unlabeled");
  activeProfile.labels.forEach(label => addOption(labelEl, label.key, label.name));

  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "all predictions");
  trainingLabels().forEach(label => addOption(candidatePredictedEl, label.key, `predicted ${label.name}`));

  const positive = labelByKey(activeProfile.positive_label);
  const negative = labelByKey(activeProfile.negative_label);
  if (isMulticlassProfile()) {
    if (candidateMinBrokenEl.value === "negative_highest") candidateMinBrokenEl.value = "positive_highest";
    candidateMinBrokenEl.options[0].textContent = "highest confidence";
    candidateMinBrokenEl.options[1].hidden = true;
    candidateMinBrokenEl.options[1].disabled = true;
    candidateMinBrokenEl.options[2].textContent = "lowest confidence";
  } else {
    candidateMinBrokenEl.options[1].hidden = false;
    candidateMinBrokenEl.options[1].disabled = false;
    candidateMinBrokenEl.options[0].textContent = `highest P(${positive.name})`;
    candidateMinBrokenEl.options[1].textContent = `highest P(${negative.name})`;
    candidateMinBrokenEl.options[2].textContent = "uncertain / balanced";
  }

  document.getElementById("profileNameInput").value = activeProfile.name || "";
  document.getElementById("profileDescriptionInput").value = activeProfile.description || "";
  document.getElementById("profileArtifactPrefixInput").value = activeProfile.artifact_prefix || "";
  document.getElementById("profileTrainingMinAddedInput").value = activeProfile.training_min_added || 50;

  const renameSelect = document.getElementById("renameLabelSelect");
  renameSelect.innerHTML = "";
  activeProfile.labels.forEach(label => addOption(renameSelect, label.key, `${label.name} (${label.key})`));
  updateLibraryOrderControls();
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
  ["openLibrary", "trainRefresh", "openCandidates", "runBenchmark", "calibrateClassifier", "refreshCandidates", "promoteClassifier"].forEach(id => {
    setTrainingActionDisabled(id, disabled);
  });
}

function setWorkflowStatus(message) {
  workflowStatusText = String(message || "");
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
  stageEl.textContent = String(progress?.error || progress?.stage || "Preparing training data");
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

function startTrainingProgressPolling(profileKey, operation) {
  stopTrainingProgressPolling();
  trainingProgressHasStarted = false;
  renderTrainingProgress({ status: "running", stage: "Starting training", percent: 0 });
  const pollingGeneration = trainingProgressPollGeneration;
  trainingProgressPollHandle = window.setInterval(() => {
    pollTrainingProgress(profileKey, operation, pollingGeneration).catch(() => {});
  }, 350);
}

async function handleTrainingActionClick(event) {
  const button = event.target.closest("button[data-training-action]");
  if (!button) return;
  const action = button.dataset.trainingAction;
  if (action === "library") return openLibraryForLabels();
  if (action === "train") return trainRefresh();
  if (action === "candidates") return openCandidatesForReview();
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
  collectionStatusEl.textContent = active ? `${active.track_count} tracks · ${active.source}` : `${collections.length} collections`;
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

async function chooseSource() {
  const response = await fetch("/api/source/dialog", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  const data = await parseJsonResponse(response);
  sourcePathEl.value = data.path || sourcePathEl.value || "";
}

async function switchSource(path) {
  const response = await fetch("/api/source/switch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path })
  });
  const data = await parseJsonResponse(response);
  applySourceState(data);
  await loadActive({ reset: true });
}

async function loadSourceState() {
  const data = await fetch("/api/source/current").then(parseJsonResponse);
  applySourceState(data);
}

function applySourceState(data) {
  sourcePathEl.value = data.path || sourcePathEl.value || "";
}

async function shutdownLab() {
  shutdownLabEl.disabled = true;
  shutdownLabEl.classList.add("stopping");
  setWorkflowStatus("stopping Rhythm Lab...");
  const response = await fetch("/api/shutdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  await parseJsonResponse(response);
  setWorkflowStatus("Rhythm Lab stopping...");
  window.setTimeout(() => window.close(), 300);
}

async function switchView(view) {
  viewOffsets[activeView] = offset;
  activeView = view;
  offset = viewOffsets[view] || 0;
  libraryTabEl.classList.toggle("active", view === "library");
  candidatesTabEl.classList.toggle("active", view === "candidates");
  document.getElementById("likedTab")?.classList.toggle("active", view === "liked");
  collectionTabEl.classList.toggle("active", view === "collection");
  trainingTabEl.classList.toggle("active", view === "training");
  settingsTabEl.classList.toggle("active", view === "settings");
  updateFilterPanelControls();
  trainingPanelEl.hidden = view !== "training";
  settingsPanelEl.hidden = view !== "settings";
  tracksEl.hidden = view === "training" || view === "settings";
  await loadActive();
}

function updateFilterPanelControls() {
  commonFiltersEl.hidden = activeView === "training" || activeView === "settings";
  collectionControlsEl.hidden = activeView !== "collection";
  candidateFiltersEl.hidden = activeView === "training" || activeView === "settings";
  candidateFiltersEl.classList.toggle("candidate-filters-placeholder", activeView !== "library" && activeView !== "candidates");
  updateLibraryOrderControls();
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
  if (activeView === "candidates") return loadCandidates(options);
  if (activeView === "liked") return loadLikedTracks(options);
  if (activeView === "collection") return loadCollectionTracks(options);
  if (activeView === "training") return loadTrainingView();
  if (activeView === "settings") return loadSettingsView();
  return loadTracks(options);
}

async function loadSummary(sequence = loadSequence) {
  if (!activeProfile) return;
  const profileKey = activeProfile.classifier_key;
  const data = await fetch(`/api/profiles/${profileKey}/summary`).then(parseJsonResponse);
  if (sequence !== loadSequence || !activeProfile || activeProfile.classifier_key !== profileKey) return;
  latestProfileSummary = data;
  renderSummary(data);
  renderGuidance(data);
}

function formatLabelCounts(labels) {
  const counts = labels || {};
  return activeProfile.labels.map(label => `${label.name} ${counts[label.key] || 0}`).join(" · ");
}

function renderSummary(data) {
  const featureStates = data.feature_states || {};
  const coverage = [
    coverageBadge("Tracks", data.tracks || 0, "tracks"),
    featureCoverageBadge("SONARA", data.sonara || 0, featureStates.sonara),
    featureCoverageBadge("MERT", data.mert || 0, featureStates.mert),
    featureCoverageBadge("MAEST", data.maest || 0, featureStates.maest),
    featureCoverageBadge("CLAP", data.clap || 0, featureStates.clap),
    featureCoverageBadge("MuQ", data.muq || 0, featureStates.muq),
    coverageBadge("Liked", data.liked || 0, "liked")
  ].join("");
  summaryCoverageEl.innerHTML = `
    <span class="summary-group summary-coverage" aria-label="Feature coverage">
      <span class="summary-group-title">Coverage</span>${coverage}
    </span>`;
  summaryLabelsEl.innerHTML = `
    <span class="summary-group summary-labels" aria-label="Label counts">
      <span class="summary-group-title">Labels</span>${labelCountBadges(data.labels || {})}
    </span>`;
}

function featureCoverageBadge(label, value, state) {
  const status = featureStateStatus(state);
  const reason = featureStateReason(state) || `${label} data is ${status}.`;
  return `<span class="summary-badge coverage-feature feature-state-${escapeHtml(status)}" title="${escapeHtml(reason)}"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b><i>${escapeHtml(status)}</i></span>`;
}

function coverageBadge(label, value, key) {
  if (key === "liked") {
    return `
      <button id="likedTab" type="button" class="summary-badge coverage-liked${activeView === "liked" ? " active" : ""}" title="Show liked tracks" aria-label="Show liked tracks">
        <svg class="lucide lucide-heart" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
        </svg>
        <span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b>
      </button>`;
  }
  return `<span class="summary-badge coverage-${escapeHtml(key)}"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></span>`;
}

function labelCountBadges(labels) {
  return activeProfile.labels
    .map(label => `<span class="summary-badge label-count-badge"><span>${escapeHtml(label.name)}</span><b>${labels[label.key] || 0}</b></span>`)
    .join("");
}

function renderGuidance(summary) {
  const counts = summary.labels || {};
  const readiness = latestTrainingReadiness;
  const trainingCountText = trainingLabels().map(label => {
    const current = readiness?.current?.[label.key] ?? counts[label.key] ?? 0;
    const usable = readiness?.usable?.[label.key];
    const value = usable === undefined || usable === current ? `${current}` : `${usable}/${current} usable`;
    return `${escapeHtml(label.name)} ${escapeHtml(value)}`;
  }).join(" · ");
  const winner = readiness?.artifact_summary?.benchmark_winner;
  const selected = selectedPromotionOption(readiness);
  const lastRun = readiness?.last_trained_at ? formatHumanDate(readiness.last_trained_at) : "not trained yet";
  const recipe = readiness?.feature_recipe;
  const recipeState = recipe?.ready
    ? `${recipe.feature_set} features current`
    : recipeBlockingText(recipe);
  guidancePanelEl.innerHTML = `
    <div class="guidance-card"><b>${escapeHtml(activeProfile.name)}</b><span class="meta">${escapeHtml(profileSignalText())}</span></div>
    <div class="guidance-card"><b>Labels</b><span class="meta">${trainingCountText}</span></div>
    <div class="guidance-card"><b>Training state</b><span class="meta">${readiness?.ready ? "Ready to train" : "Not ready yet"} · ${escapeHtml(recipeState || "feature recipe unavailable")} · last ${escapeHtml(lastRun)}</span></div>
    <div class="guidance-card"><b>Benchmark</b><span class="meta">${winner ? `${escapeHtml(winner.feature_set)} · F1 ${formatMetricPercent(winner.macro_f1_mean)} · recall ${formatMetricPercent(winner.positive_recall_mean)}` : "No benchmark winner yet"}</span></div>
    <div class="guidance-card"><b>Production</b><span class="meta">${selected ? `Selected ${escapeHtml(selected.feature_set)} · F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "No promotion variant yet"}</span></div>`;
}

function nextStepText(counts) {
  const minAdded = activeProfile.training_min_added || 50;
  if (isMulticlassProfile()) {
    const lowClass = trainingLabels().find(label => (counts[label.key] || 0) < 20);
    if (lowClass) return "Label examples for every class before trusting metrics.";
    const lowRefreshClass = trainingLabels().find(label => (counts[label.key] || 0) < minAdded);
    if (lowRefreshClass) return `Keep labeling each class; train-refresh unlocks after ${minAdded} new examples per class.`;
    return "Refresh candidates, review low-confidence predictions, then retrain after another balanced batch.";
  }
  const positiveCount = counts[activeProfile.positive_label] || 0;
  const negativeCount = counts[activeProfile.negative_label] || 0;
  if (positiveCount < 20 || negativeCount < 20) return "Label balanced positive and negative examples before trusting metrics.";
  if (positiveCount < minAdded || negativeCount < minAdded) return `Keep labeling edge cases; train-refresh unlocks after ${minAdded} new examples per training label.`;
  return "Refresh candidates, review uncertain predictions, then retrain after another balanced batch.";
}

function profileSignalText() {
  const type = activeProfile.profile_type === "multiclass" ? "multiclass" : "binary";
  if (isMulticlassProfile()) {
    return `${type} · ${activeProfile.description || "Profile ready for labeling."}`;
  }
  return `${type} · positive ${labelByKey(activeProfile.positive_label).name} · negative ${labelByKey(activeProfile.negative_label).name}`;
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
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "library") return;
  total = data.total;
  offset = data.offset;
  viewOffsets.library = offset;
  tracksEl.innerHTML = "";
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
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
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "liked") return;
  total = data.total;
  offset = data.offset;
  viewOffsets.liked = offset;
  tracksEl.innerHTML = "";
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
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
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "collection") return;
  total = data.total;
  offset = data.offset;
  viewOffsets.collection = offset;
  tracksEl.innerHTML = "";
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderTrack(track));
  });
  updatePager(data);
  await loadSummary(sequence);
  await loadTrainingReadiness();
}

async function deleteSelectedCollection() {
  const collection = selectedCollection();
  if (!collection) return;
  if (!window.confirm(`Delete collection "${collection.name}"? Labels stay in the active profile.`)) return;
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
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "candidates") return;
  total = data.total;
  offset = data.offset;
  viewOffsets.candidates = offset;
  tracksEl.innerHTML = "";
  data.items.forEach((track, index) => {
    track.rowNumber = data.offset + index + 1;
    tracksEl.appendChild(renderCandidate(track));
  });
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

async function openLibraryForLabels() {
  await switchView("library");
  await loadActive({ reset: true });
}

async function openCandidatesForReview() {
  if (trainingActionElement("openCandidates")?.disabled) return;
  await switchView("candidates");
  await loadCandidates({ reset: true });
}

async function trainRefresh() {
  if (trainingActionElement("trainRefresh")?.disabled) return;
  if (!window.confirm(`Train a new ${activeProfile.name} ${selectedTrainingFeatureSet} model, then refresh candidates?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("training model...");
  startTrainingProgressPolling(activeProfile.classifier_key, "train-refresh");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_set: selectedTrainingFeatureSet })
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`trained ${formatLabelCounts(data.training_counts)} · updated ${data.predicted} · skipped ${data.skipped}`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "train-refresh", stage: "Training and candidate refresh complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", stage: "Training failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

async function runBenchmark() {
  if (trainingActionElement("runBenchmark")?.disabled) return;
  if (!window.confirm(`Run a full feature benchmark for ${activeProfile.name}?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("running benchmark...");
  startTrainingProgressPolling(activeProfile.classifier_key, "benchmark");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/benchmark`, { method: "POST" });
    const data = await parseRefreshResponse(response);
    const winner = data.winner?.feature_set ? ` · winner ${data.winner.feature_set}` : "";
    setWorkflowStatus(`benchmark complete${winner}`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "benchmark", stage: "Benchmark complete", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", stage: "Benchmark failed", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

function selectedArtifactFeatureSet(data = latestTrainingReadiness) {
  return promoteFeatureSetEl?.value
    || selectedPromotionOption(data)?.feature_set
    || selectedTrainingFeatureSet
    || DEFAULT_TRAINING_FEATURE_SET;
}

async function calibrateClassifier() {
  if (trainingActionElement("calibrateClassifier")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  if (!window.confirm(`Calibrate a new ${activeProfile.name} ${selectedFeatureSet} model from all current labels?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("calibrating model...");
  startTrainingProgressPolling(activeProfile.classifier_key, "calibrate");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/calibrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_set: selectedFeatureSet })
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`calibrated ${data.feature_set} · ${fileName(data.artifact)}`);
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
  setWorkflowStatus(`refreshing ${selectedFeatureSet} candidates...`);
  startTrainingProgressPolling(activeProfile.classifier_key, "refresh");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_set: selectedFeatureSet })
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`refreshed ${data.feature_set} · updated ${data.predicted} · skipped ${data.skipped}`);
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
  if (!window.confirm(`Promote the latest ${activeProfile.name} ${selectedFeatureSet} model to the main app?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("promoting model...");
  startTrainingProgressPolling(activeProfile.classifier_key, "promote");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_set: selectedFeatureSet || undefined })
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`promoted ${fileName(data.model_path)} · metadata ${fileName(data.metadata_path)}`);
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

async function refreshWorkflowData({ candidatesChanged = false } = {}) {
  if (!activeProfile) return;
  if (activeView === "training") {
    await loadTrainingView();
    return;
  }
  if (candidatesChanged && activeView === "candidates") {
    await loadCandidates({ reset: true });
    return;
  }
  await loadSummary();
  await loadTrainingReadiness();
}

async function loadTrainingReadiness() {
  if (!activeProfile) return null;
  const profileKey = activeProfile.classifier_key;
  const params = new URLSearchParams({ feature_set: selectedTrainingFeatureSet });
  const response = await fetch(`/api/profiles/${profileKey}/training/readiness?${params}`);
  const data = await response.json();
  if (!activeProfile || activeProfile.classifier_key !== profileKey) return null;
  if (!response.ok) {
    setWorkflowBusy(true);
    return null;
  }
  latestTrainingReadiness = data;
  selectedTrainingFeatureSet = data.feature_recipe?.feature_set || selectedTrainingFeatureSet;
  updateTrainingFeatureSetOptions(data);
  updatePromoteFeatureSetOptions(data);
  refreshTrainingInformation(data);
  const hasModel = hasTrainedVariant(data);
  setTrainingActionDisabled("openLibrary", false, "Open Library to label tracks");
  setTrainingActionDisabled(
    "trainRefresh",
    !data.ready,
    data.ready
      ? `Train ${selectedTrainingFeatureSet} from all current labels and refresh candidates`
      : readinessBlockedTitle(data)
  );
  setTrainingActionDisabled(
    "openCandidates",
    !hasModel,
    hasModel ? "Open model candidates for review" : "Train a model before reviewing candidates"
  );
  setTrainingActionDisabled(
    "runBenchmark",
    !data.labels_ready,
    data.labels_ready ? "Run benchmark across current feature recipes" : readinessBlockedTitle(data)
  );
  const selected = selectedPromotionOption(data);
  const selectedReady = selected?.source_data_ready === true;
  const canCalibrate = Boolean(
    data.calibration_ready
    && selectedReady
    && selected?.calibration_status !== "calibrated"
  );
  setTrainingActionDisabled(
    "calibrateClassifier",
    !canCalibrate,
    canCalibrate
      ? `Calibrate selected ${selected.feature_set} model`
      : selected?.calibration_status === "calibrated"
        ? `${selected.feature_set} is already calibrated`
        : data.calibration_readiness?.reason || "Select a source-ready trained variant"
  );
  setTrainingActionDisabled(
    "refreshCandidates",
    !selectedReady,
    selectedReady
      ? `Refresh candidates with selected ${selected.feature_set} model`
      : "Select a source-ready trained variant"
  );
  const canPromote = canPromoteArtifact(data);
  setTrainingActionDisabled(
    "promoteClassifier",
    !canPromote,
    canPromote
      ? `Promote calibrated ${selected?.feature_set || DEFAULT_TRAINING_FEATURE_SET} model to main app`
      : "Calibrate the selected source-ready model before promoting"
  );
  if (latestProfileSummary) renderGuidance(latestProfileSummary);
  return data;
}

async function loadTrainingView() {
  if (!activeProfile) return;
  const profileKey = activeProfile.classifier_key;
  trainingPanelEl.innerHTML = renderTrainingLoading(activeProfile.name);
  try {
    const data = await loadTrainingReadiness();
    if (!activeProfile || activeProfile.classifier_key !== profileKey || activeView !== "training" || !data) return;
    await loadSummary();
    if (!activeProfile || activeProfile.classifier_key !== profileKey || activeView !== "training") return;
    const planText = isMulticlassProfile()
      ? `Guided Logistic Regression across ${trainingLabels().map(label => escapeHtml(label.name)).join(", ")}. Each track contributes at most one class label.`
      : `Guided Logistic Regression on ${escapeHtml(labelByKey(activeProfile.positive_label).name)} vs ${escapeHtml(labelByKey(activeProfile.negative_label).name)}. Review-only labels stay out of fitting.`;
    trainingPanelEl.innerHTML = `
      ${renderTrainingWorkflow(data, planText)}
      <div id="trainingInformation">${renderTrainingInformationMetrics(data)}</div>`;
    promoteFeatureSetEl = document.getElementById("promoteFeatureSet");
    promoteFeatureSetEl?.addEventListener("change", () => loadTrainingReadiness().catch(showError));
    trainingFeatureSetEl = document.getElementById("trainingFeatureSet");
    trainingFeatureSetEl?.addEventListener("change", () => {
      selectedTrainingFeatureSet = trainingFeatureSetEl.value || DEFAULT_TRAINING_FEATURE_SET;
      loadTrainingView().catch(showError);
    });
    updateTrainingFeatureSetOptions(data);
    updatePromoteFeatureSetOptions(data);
    renderTrainingProgress(latestWorkflowProgress);
  } catch (error) {
    if (activeProfile?.classifier_key === profileKey && activeView === "training") {
      trainingPanelEl.innerHTML = renderTrainingLoadError(error);
    }
    throw error;
  }
}

function renderTrainingLoading(profileName) {
  return `<div class="training-info-card"><b>Loading Training</b>
    <span class="meta training-info-text">Checking labels, feature sources, and saved models for ${escapeHtml(profileName)}...</span>
  </div>`;
}

function renderTrainingLoadError(error) {
  return `<div class="training-info-card"><b>Training could not load</b>
    <span class="meta training-info-text">${escapeHtml(error?.message || String(error))}</span>
  </div>`;
}

function renderTrainingWorkflow(data, planText) {
  const options = data?.artifact_summary?.promotion_options || [];
  const selected = selectedPromotionOption(data);
  const winner = data?.artifact_summary?.benchmark_winner;
  const optionMarkup = renderPromotionOptions(options);
  const hasModel = hasTrainedVariant(data);
  const selectedReady = selected?.source_data_ready === true;
  const selectedCalibrated = selected?.calibration_status === "calibrated";
  const canCalibrate = Boolean(data?.calibration_ready && selectedReady && !selectedCalibrated);
  const canPromote = canPromoteArtifact(data);
  const featureRecipe = data?.feature_recipe || {};
  const featureOptions = renderTrainingFeatureOptions(data);
  const trainingBlocked = readinessBlockedTitle(data);
  return `<div class="classifier-workflow-card">
    <div class="workflow-header">
      <div>
        <b>Classifier workflow</b>
        <span class="meta">${escapeHtml(activeProfile.name)} · ${escapeHtml(activeProfile.profile_type || "profile")}</span>
      </div>
      <span class="workflow-state-chip ${data?.ready ? "ready" : "blocked"}">${data?.ready ? "Ready to train" : "Not ready yet"}</span>
    </div>
    <div class="workflow-recommendation">
      <b>Current recommendation</b>
      <span>${escapeHtml(workflowRecommendation(data, selected))}</span>
    </div>
    <div class="workflow-variant-row">
      <label class="workflow-variant-select">Training recipe
        <select id="trainingFeatureSet">${featureOptions}</select>
      </label>
      <label class="workflow-variant-select">Selected variant
        <select id="promoteFeatureSet" ${options.some(row => row.source_data_ready === true) ? "" : "disabled"}>${optionMarkup}</select>
      </label>
      <div class="workflow-variant-facts">
        ${trainingInfoLine("Sources", (featureRecipe.required_sources || []).map(source => source.toUpperCase()).join(" + ") || "None")}
        ${trainingInfoLine("Data", featureRecipe.ready ? "Ready to use" : recipeBlockingText(featureRecipe))}
        ${trainingInfoLine("Benchmark", winner ? `${winner.feature_set} · F1 ${formatMetricPercent(winner.macro_f1_mean)} · recall ${formatMetricPercent(winner.positive_recall_mean)}` : "Run benchmark to compare variants")}
        ${trainingInfoLine("Selection", selected ? `${selected.feature_set} · #${selected.rank ?? "-"} · F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "Choose a trained variant")}
        ${trainingInfoLine("Calibration", selectedCalibrated ? `${selected.calibration_method || "Calibrated"} · ready to promote` : selected ? `Not calibrated${selected.calibration_reason ? ` · ${selected.calibration_reason}` : ""}` : "No selected variant")}
        ${trainingInfoLine("Model mix", formatFeatureGroupWeights(selected?.feature_group_weights))}
      </div>
    </div>
    <div class="training-workflow-feedback"${workflowStatusText ? "" : " hidden"}>
      <span id="refreshCandidatesStatus" class="meta source-status-line">${escapeHtml(workflowStatusText)}</span>
    </div>
    <div id="trainingProgress" class="training-progress" role="status" aria-live="polite" hidden>
      <div class="training-progress-header"><span id="trainingProgressStage"></span><b id="trainingProgressPercent">0%</b></div>
      <div class="training-progress-track"><span id="trainingProgressBar"></span></div>
    </div>
    <div class="workflow-steps">
      ${renderWorkflowStep({
        number: 1,
        title: "Collect labels",
        status: data?.labels_ready ? "done" : "blocked",
        body: data?.labels_ready
          ? `Training labels are sufficient. Usable totals: ${formatLabelCounts(data?.usable || data?.current || {})}. New since the last run: ${formatLabelCounts(data?.added || {})}.`
          : Number(data?.skipped_training_rows || 0) > 0
            ? `${data.skipped_training_rows} labeled track(s) are missing current outputs for this recipe. Restore those outputs or add feature-complete examples: ${missingLabelText(data) || "at least two tracks per training class"}.`
            : `Add the missing training labels: ${missingLabelText(data) || "at least two tracks per training class"}.`,
        action: workflowButton("openLibrary", "library", "Open Library", "open-library", false, "Open Library to label tracks")
      })}
      ${renderWorkflowStep({
        number: 2,
        title: "Train model",
        status: data?.ready ? "ready" : "blocked",
        body: `${planText} Selected recipe: ${selectedTrainingFeatureSet}. Fit evaluation metrics, then refit the saved production model on all current labels. Candidate predictions refresh automatically.`,
        action: workflowButton("trainRefresh", "train", "Train", "train-refresh", !data?.ready, data?.ready ? `Train ${selectedTrainingFeatureSet} and refresh candidates` : trainingBlocked)
      })}
      ${renderWorkflowStep({
        number: 3,
        title: "Benchmark variants",
        status: winner ? "done" : data?.labels_ready ? "ready" : "blocked",
        body: winner ? `Current winner: ${winner.feature_set} · F1 ${formatMetricPercent(winner.macro_f1_mean)}.` : "Compare SONARA, MERT, MAEST, CLAP, and MuQ feature-source combinations.",
        action: workflowButton("runBenchmark", "benchmark", "Run benchmark", "run-benchmark", !data?.labels_ready, data?.labels_ready ? "Run benchmark" : trainingBlocked)
      })}
      ${renderWorkflowStep({
        number: 4,
        title: "Calibrate selected variant",
        status: selectedCalibrated ? "done" : canCalibrate ? "ready" : "blocked",
        body: selectedCalibrated
          ? `${selected.feature_set} uses ${selected.calibration_method || "calibrated"} probabilities and is eligible for promotion.`
          : selectedReady && data?.calibration_ready
            ? "Refit the selected recipe with probability calibration before promotion."
            : data?.calibration_readiness?.reason || "Train or benchmark a variant whose source data matches the active catalog.",
        action: workflowButton("calibrateClassifier", "calibrate", "Calibrate", "calibrate-classifier", !canCalibrate, canCalibrate ? `Calibrate ${selected.feature_set}` : selectedCalibrated ? "Selected variant is already calibrated" : data?.calibration_readiness?.reason || "Select a source-ready variant")
      })}
      ${renderWorkflowStep({
        number: 5,
        title: "Refresh and review candidates",
        status: selectedReady ? "ready" : "blocked",
        body: selectedReady ? `Refresh predictions with ${selected.feature_set}, then review uncertain and high-confidence candidates.` : "Train a source-ready variant before candidate review is available.",
        action: `${workflowButton("refreshCandidates", "refresh", "Refresh", "refresh-candidates", !selectedReady, selectedReady ? `Refresh candidates with ${selected.feature_set}` : "Select a source-ready model")}${workflowButton("openCandidates", "candidates", "Open", "open-candidates", !hasModel, hasModel ? "Open existing candidates" : "Train a model before reviewing candidates")}`
      })}
      ${renderWorkflowStep({
        number: 6,
        title: "Promote model",
        status: canPromote ? "ready" : "blocked",
        body: canPromote ? `Promote calibrated ${selected.feature_set} into models/classifiers for scoring in the main app.` : "Promotion is gated on a calibrated artifact bound to the active source catalog.",
        action: workflowButton("promoteClassifier", "promote", "Promote", "promote-classifier", !canPromote, canPromote ? "Promote selected calibrated variant" : "Calibrate the selected variant before promoting")
      })}
    </div>
  </div>`;
}

function hasTrainedVariant(data) {
  return Boolean(
    data?.model_artifact ||
    (data?.artifact_summary?.promotion_options || []).length
  );
}

function canPromoteArtifact(data) {
  const selected = selectedPromotionOption(data);
  return Boolean(
    selected?.source_data_ready === true
    && selected?.calibration_status === "calibrated"
  );
}

function renderWorkflowStep({ number, title, status, body, action }) {
  return `<section class="workflow-step workflow-step-${status}">
    <div class="workflow-step-index">${number}</div>
    <div class="workflow-step-copy">
      <div class="workflow-step-title"><b>${escapeHtml(title)}</b><span class="workflow-state-chip ${status}">${escapeHtml(status)}</span></div>
      <span class="meta">${escapeHtml(body)}</span>
    </div>
    <div class="workflow-step-action">${action}</div>
  </section>`;
}

function workflowButton(id, action, label, className, disabled, title) {
  return `<button id="${id}" data-training-action="${action}" type="button" class="workflow-action-button ${className}" title="${escapeHtml(title)}" ${disabled ? "disabled" : ""}>${actionIcon(action)}<span>${escapeHtml(label)}</span></button>`;
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
  if (missing && skipped > 0) return `Restore feature outputs for ${skipped} labeled track(s), or add ${missing} feature-complete examples.`;
  if (missing) return `Add ${missing} before the next train run.`;
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  if (!data?.model_artifact && !(data?.artifact_summary?.promotion_options || []).length) return "Train the first model for this profile.";
  if (!data?.artifact_summary?.benchmark_winner) return "Run benchmark to choose the strongest feature-source variant.";
  if (!selected) return "Retrain a variant against the current source data before calibration or promotion.";
  if (selected?.calibration_status !== "calibrated" && !data?.calibration_ready) {
    return data?.calibration_readiness?.reason || "Add more labels before calibration.";
  }
  if (selected?.calibration_status !== "calibrated") return "Calibrate the selected benchmark variant, then refresh its candidates.";
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
    return `${total} labels across ${missingRows.length} classes`;
  }
  return hasMissing ? formatLabelCounts(missing) : "";
}

function renderTrainingFeatureOptions(data) {
  const options = data?.available_feature_sets || [DEFAULT_TRAINING_FEATURE_SET];
  return options
    .map(featureSet => `<option value="${escapeHtml(featureSet)}" ${featureSet === selectedTrainingFeatureSet ? "selected" : ""}>${escapeHtml(featureSet)}</option>`)
    .join("");
}

function updateTrainingFeatureSetOptions(data) {
  if (!trainingFeatureSetEl) return;
  trainingFeatureSetEl.innerHTML = renderTrainingFeatureOptions(data);
  trainingFeatureSetEl.value = selectedTrainingFeatureSet;
}

function recipeBlockingText(recipe) {
  const blocking = recipe?.blocking || [];
  if (!blocking.length) return "Feature recipe status is unavailable";
  return blocking
    .map(item => `${String(item.source || "").toUpperCase()}: ${item.reason || item.status || "not current"}`)
    .join(" · ");
}

function readinessBlockedTitle(data) {
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  return `Add missing training labels: ${missingLabelText(data) || "at least two per class"}.`;
}

function updatePromoteFeatureSetOptions(data) {
  if (!promoteFeatureSetEl) return;
  const options = data?.artifact_summary?.promotion_options || [];
  const readyOptions = options.filter(row => row.source_data_ready === true);
  const selected = selectedPromotionOption(data);
  const previous = promoteFeatureSetEl.value;
  promoteFeatureSetEl.innerHTML = options.length
    ? renderPromotionOptions(options)
    : '<option value="">No trained model</option>';
  const allowedValues = new Set(readyOptions.map(row => String(row.feature_set || "")));
  promoteFeatureSetEl.value = allowedValues.has(previous) ? previous : String(selected?.feature_set || "");
  promoteFeatureSetEl.disabled = readyOptions.length === 0;
}

function selectedPromotionOption(data) {
  const options = data?.artifact_summary?.promotion_options || [];
  const readyOptions = options.filter(row => row.source_data_ready === true);
  const requested = promoteFeatureSetEl?.value;
  return readyOptions.find(row => row.feature_set === requested)
    || (data?.artifact_summary?.latest_promotable?.source_data_ready === true
      ? data.artifact_summary.latest_promotable
      : null)
    || readyOptions[0]
    || null;
}

function renderPromotionOptions(options) {
  return options.length
    ? options.map(row => `<option value="${escapeHtml(String(row.feature_set || ""))}" ${row.source_data_ready === true ? "" : "disabled"}>${escapeHtml(promotionOptionLabel(row))}</option>`).join("")
    : '<option value="">No trained model</option>';
}

function promotionOptionLabel(row) {
  const rank = row.rank ? `#${row.rank}` : "unranked";
  const sourceState = row.source_data_ready === true
    ? "source data current"
    : `blocked: ${row.source_data_reason || "source data unavailable"}`;
  const calibration = row.calibration_status === "calibrated"
    ? `calibrated ${row.calibration_method || ""}`.trim()
    : "not calibrated";
  return `${row.feature_set || "model"} · ${rank} · F1 ${formatMetricPercent(row.macro_f1_mean)} · ${calibration} · ${formatHumanDate(row.created_at)} · ${sourceState}`;
}

function formatFeatureGroupWeights(weights) {
  if (!weights || typeof weights !== "object") return "Not recorded for this artifact";
  const entries = Object.entries(weights);
  if (!entries.length) return "Not recorded for this artifact";
  return entries
    .map(([source, value]) => `${String(source).toUpperCase()} ${Number(value).toFixed(3)}`)
    .join(" · ");
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
      <span class="meta">Saved model, validation quality, and change since the previous run.</span>
    </header>
    <div class="meta training-info-text">
      ${renderTrainingLastRunLine(data)}
      ${renderTrainingArtifactsLine(data?.artifact_summary)}
      ${renderTrainingMetricsLine(data?.artifact_summary)}
      ${renderTrainingDynamicsLine(data?.metrics_history)}
    </div>
  </section>`;
}

function renderTrainingLastRunLine(data) {
  const current = featureSummary(data?.artifact_summary, selectedTrainingFeatureSet)
    || selectedPromotionOption(data);
  const artifact = data?.model_artifact || current?.latest_model;
  const runDate = current?.created_at || data?.last_trained_at;
  const modelText = current
    ? `${current.feature_set} model ${formatBytes(current.model_bytes)}`
    : fileName(artifact) || "no current model";
  return trainingInfoLine("Latest model", `${formatHumanDate(runDate)} · trained on ${formatLabelCounts(data?.last_trained || {})} · ${modelText}`);
}

function renderTrainingArtifactsLine(summary) {
  const features = summary?.by_feature || [];
  const current = featureSummary(summary, selectedTrainingFeatureSet);
  const header = `${summary?.model_count || 0} saved models · ${summary?.metrics_count || 0} metric reports`;
  const detail = features.length
    ? `${features.length} recipes are available. The selected training recipe was saved ${current?.created_at ? formatHumanDate(current.created_at) : "not yet"}.`
    : "No saved artifacts yet. Train a recipe to create the first model.";
  return trainingInfoLine("Saved files", `${header} · ${detail}`);
}

function renderTrainingMetricsLine(summary) {
  const current = featureSummary(summary, selectedTrainingFeatureSet)
    || selectedPromotionOption({ artifact_summary: summary })
    || (summary?.by_feature || [])[0];
  if (!current) return trainingInfoLine("Quality", "No validation report yet. Train a recipe to measure model quality.");
  const values = [
    `accuracy ${formatMetricPercent(current.accuracy_mean)}`,
    `F1 balance ${formatMetricPercent(current.macro_f1_mean)}`,
    `precision ${formatMetricPercent(current.positive_precision_mean)}`,
    `recall ${formatMetricPercent(current.positive_recall_mean)}`,
    `${current.trained_rows ?? "-"} labeled tracks`,
    `${current.feature_count ?? "-"} inputs`,
    current.calibration_status === "calibrated" ? `calibrated ${current.calibration_method || ""}`.trim() : "not calibrated"
  ].join(" · ");
  return trainingInfoLine("Quality", `${current.feature_set} · ${values}`);
}

function renderTrainingDynamicsLine(history) {
  const latest = (history || [])[0];
  const previous = (history || [])[1];
  if (!latest) return trainingInfoLine("Change", `Train ${selectedTrainingFeatureSet} to establish a baseline.`);
  const trend = previous
    ? `vs previous run: accuracy ${formatMetricDelta(latest.accuracy_mean, previous.accuracy_mean)} · F1 ${formatMetricDelta(latest.macro_f1_mean, previous.macro_f1_mean)}`
    : "First recorded model for this recipe.";
  return trainingInfoLine(
    "Change",
    `${trend} · ${formatHumanDate(latest.created_at)} · ${latest.trained_rows ?? "-"} labeled tracks · accuracy ${formatMetricPercent(latest.accuracy_mean)} · F1 ${formatMetricPercent(latest.macro_f1_mean)}`
  );
}

function trainingInfoLine(label, text) {
  return `<span class="training-info-line"><b class="training-info-label">${escapeHtml(label)}</b><span class="training-info-value">${escapeHtml(text)}</span></span>`;
}

function featureSummary(summary, featureSet) {
  return (summary?.by_feature || []).find(row => row.feature_set === featureSet);
}

async function loadSettingsView() {
  tracksEl.innerHTML = "";
  await loadSummary();
}

function renderTrack(track) {
  const row = document.createElement("section");
  row.className = "track";
  row.tabIndex = 0;
  row.innerHTML = trackMarkup(track);
  wireTrackRow(row, track);
  return row;
}

function renderCandidate(track) {
  const row = document.createElement("section");
  row.className = "track";
  row.tabIndex = 0;
  row.innerHTML = trackMarkup(track);
  wireTrackRow(row, track);
  return row;
}

function predictionBadge(track) {
  const label = track.predicted_label || "";
  const role = labelByKey(label).role || "review";
  return `<span class="profile-label-badge label-role-${escapeHtml(role)} label-${escapeHtml(label)}">${escapeHtml(displayLabel(label))}</span>`;
}

function predictedScore(track) {
  if (isMulticlassProfile()) return track.confidence;
  return positiveScore(track);
}

function positiveScore(track) {
  const positive = Number(track.positive_probability || 0);
  const negative = Number(track.negative_probability || 0);
  if (positive === 1 && negative > 0 && negative < 1) return 1 - negative;
  return positive;
}

function trackMarkup(track) {
  return `
    <div>
      <div class="track-main">
        <strong class="track-heading"><span class="track-title-main"><span class="track-number">#${track.rowNumber}</span>${escapeHtml(displayTrackTitle(track))}</span>${featuresIndicator(track)}</strong>
        <div class="meta track-path">${escapeHtml(track.file_path)}</div>
        <div class="meta feature-line">${trackStatusLine(track)}</div>
      </div>
      <div class="rhythm-media-block">
        <div class="meta genres-line"><span class="status-item"><b>GENRES</b></span><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>
        <audio controls preload="none" src="/media/${track.track_id}"></audio>
      </div>
    </div>
    <div class="actions">
      <div class="row-tools">${renderLikeButton(track)}</div>
      <div class="label-actions ${isMulticlassProfile() ? "multiclass-label-actions" : ""}">${renderLabelButtons(track)}</div>
    </div>`;
}

function renderLikeButton(track) {
  const active = track.liked ? " active intent-liked" : "";
  const fill = track.liked ? "currentColor" : "none";
  const title = track.liked ? "Unlike track" : "Like track";
  return `
    <button type="button" class="icon-button track-like-button${active}" data-action="like" title="${title}" aria-label="${title}" aria-pressed="${track.liked ? "true" : "false"}">
      <svg class="lucide lucide-heart" aria-hidden="true" viewBox="0 0 24 24" fill="${fill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
      </svg>
    </button>`;
}

function renderLabelButtons(track) {
  const buttons = activeProfile.labels.map(label => {
    const active = track.label === label.key ? " active" : "";
    return `<button type="button" class="${active}" data-action="label" data-label="${escapeHtml(label.key)}">${escapeHtml(label.name)}</button>`;
  });
  buttons.push('<button type="button" data-action="label" data-label="">Clear</button>');
  return buttons.join("");
}

function wireTrackRow(row, track) {
  const likeButton = row.querySelector('[data-action="like"]');
  if (likeButton) likeButton.addEventListener("click", () => toggleLike(track).catch(showError));
  row.querySelectorAll('[data-action="label"]').forEach(button => {
    button.addEventListener("click", () => setLabel(track.track_id, button.dataset.label));
  });
  row.addEventListener("keydown", event => {
    const keys = { "0": "" };
    activeProfile.labels.forEach((label, index) => {
      if (index < 9) keys[String(index + 1)] = label.key;
    });
    if (keys[event.key] !== undefined) setLabel(track.track_id, keys[event.key]);
  });
  wireAudioPreview(row.querySelector("audio"));
}

async function toggleLike(track) {
  const response = await fetch(`/api/tracks/${track.track_id}/liked`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      catalog_uuid: track.catalog_uuid,
      track_uuid: track.track_uuid,
      content_generation: track.content_generation,
      liked: !track.liked
    })
  });
  await parseJsonResponse(response);
  await loadActive();
}

function wireAudioPreview(audio) {
  if (!audio) return;
  audio.addEventListener("play", () => {
    if (activeAudio && activeAudio !== audio) {
      activeAudio.pause();
      activeAudio.currentTime = 0;
    }
    activeAudio = audio;
  });
  audio.addEventListener("ended", () => {
    if (activeAudio === audio) activeAudio = null;
  });
  audio.addEventListener("pause", () => {
    if (activeAudio === audio && audio.currentTime === 0) activeAudio = null;
  });
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
  binaryLabelGridEl.querySelectorAll("input").forEach(input => {
    input.required = !multiclass && ["newPositiveKey", "newPositiveName", "newNegativeKey", "newNegativeName"].includes(input.id);
  });
  multiclassLabelRowsEl.querySelectorAll(".multiclass-label-key, .multiclass-label-name").forEach(input => {
    input.required = multiclass;
  });
}

function addMulticlassLabelRow() {
  const row = document.createElement("div");
  row.className = "multiclass-label-row";
  row.innerHTML = `
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
      training_min_added: Number(document.getElementById("profileTrainingMinAddedInput").value || 50)
    })
  });
  const profile = await parseJsonResponse(response);
  await loadProfiles();
  await setActiveProfile(profile.classifier_key, { skipLoad: true });
  setWorkflowStatus("profile saved");
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
    `Delete ${activeProfile.name}? This permanently removes Rhythm Lab labels, predictions, training queue, checkpoints, metrics, and local training artifacts for this profile. Promoted runtime models stay in models/classifiers.\n\nType "${activeProfile.name}" or "${activeProfile.classifier_key}" to delete.`
  );
  if (confirmation === null) return;
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: confirmation })
  });
  const data = await parseJsonResponse(response);
  setWorkflowStatus(`deleted ${data.name} · artifacts ${data.artifact_cleanup?.deleted_files || 0}`);
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
  pageInfoEl.textContent = `${current} / ${pages} (${first}-${last} / ${data.total})`;
  pageNumberEl.value = String(current || 1);
  pageNumberEl.max = String(Math.max(1, pages));
  pageNumberEl.disabled = pages <= 0;
  prevPageEl.disabled = data.offset <= 0;
  nextPageEl.disabled = data.offset + data.limit >= data.total;
}

function badgeRow(track) {
  const badges = [syncopatedBadge(track)].filter(Boolean);
  return badges.length ? `<div class="badge-row">${badges.join('<span class="badge-separator">·</span>')}</div>` : "";
}

function syncopatedBadge(track) {
  return track.maest_syncopated_rhythm === true ? '<span class="syncopated-badge">syncopated rhythm</span>' : "";
}

function displayLabel(key) {
  if (!key || key === "none") return "none";
  return labelByKey(key).name || key;
}

function displayTrackTitle(track) {
  const title = track.title || track.file_path;
  return track.artist ? `${track.artist} - ${title}` : title;
}

function formatProbability(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "-";
  return formatScore(number);
}

function formatScore(number) {
  if (number < 1 && number.toFixed(6) === "1.000000") return "0.999999";
  return number.toFixed(6);
}

function formatMetricPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(1)}%`;
}

function formatMetricDelta(current, previous) {
  const currentNumber = Number(current);
  const previousNumber = Number(previous);
  if (!Number.isFinite(currentNumber) || !Number.isFinite(previousNumber)) return "-";
  const delta = (currentNumber - previousNumber) * 100;
  const sign = delta >= 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)} pp`;
}

function formatHumanDate(value) {
  const date = parseTrainingDate(value);
  if (!date) return "never";
  return new Intl.DateTimeFormat(undefined, {
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
  const date = new Date(normalized.endsWith("Z") ? normalized : `${normalized}Z`);
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

function mark(value) {
  return value ? "YES" : "NO";
}

function trackStatusLine(track) {
  return [
    trainedStatus(track),
    predictionStatus(track),
    predictionScoreStatus(track),
    ...["sonara", "mert", "maest", "clap", "muq"].map(
      source => trackFeatureStatus(source, track.feature_status?.[source])
    ),
  ].filter(Boolean).join(" ");
}

function trackFeatureStatus(source, state) {
  const status = featureStateStatus(state);
  const reason = featureStateReason(state) || `${source.toUpperCase()} output is ${status}.`;
  return `<span class="status-item" title="${escapeHtml(reason)}"><b>${escapeHtml(source.toUpperCase())}</b><span class="analysis-status-badge status-${escapeHtml(status)}">${escapeHtml(status)}</span></span>`;
}

function featuresReady(track) {
  return requiredFeatureSources().every(source => featureStateStatus(track.feature_status?.[source]) === "current");
}

function missingFeatures(track) {
  return requiredFeatureSources()
    .filter(source => featureStateStatus(track.feature_status?.[source]) !== "current")
    .map(source => {
      const state = track.feature_status?.[source];
      return `${source.toUpperCase()} (${featureStateStatus(state)}: ${featureStateReason(state) || "not current"})`;
    });
}

function featuresIndicator(track) {
  const ready = featuresReady(track);
  const sources = requiredFeatureSources().map(source => source.toUpperCase()).join(", ");
  const label = ready
    ? `Features ready for ${selectedTrainingFeatureSet}: ${sources}`
    : `Blocked for ${selectedTrainingFeatureSet}: ${missingFeatures(track).join(", ")}`;
  return `<span class="features-indicator ${ready ? "ready" : "missing"}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${ready ? "✓" : "!"}</span>`;
}

function requiredFeatureSources() {
  return latestTrainingReadiness?.feature_recipe?.required_sources || ["sonara", "mert", "maest", "clap", "muq"];
}

function featureStateStatus(state) {
  if (typeof state === "boolean") return state ? "current" : "missing";
  const status = String(state?.status || "missing");
  return ["current", "missing", "stale"].includes(status) ? status : "missing";
}

function featureStateReason(state) {
  return typeof state === "object" && state ? String(state.reason || "") : "";
}

function trainedStatus(track) {
  return featureStatusBadge("TRAINED", track.label_trained);
}

function predictionStatus(track) {
  return track.predicted_label ? `<span class="status-item"><b>PREDICTED</b>${predictionBadge(track)}</span>` : "";
}

function predictionScoreStatus(track) {
  return track.predicted_label ? `<span class="status-item"><b>SCORE</b><span class="status-detail">${formatProbability(predictedScore(track))}</span></span>` : "";
}

function featureStatusBadge(name, value) {
  return `<span class="status-item"><b>${name}</b><span class="analysis-status-badge ${value ? "status-yes" : "status-no"}">${mark(value)}</span></span>`;
}

function showError(error) {
  setWorkflowStatus(error.message || String(error));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

init().catch(showError);
