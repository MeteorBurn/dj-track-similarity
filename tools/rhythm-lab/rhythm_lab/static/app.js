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
  singles: "По одной модели",
  "singles+all": "По одной + все",
  greedy: "Жадный отбор",
  full: "Полная сетка",
  layers: "Слои MERT-v2",
  "layers+all": "Слои MERT-v2 + остальные",
  custom: "Свой список",
};
const BENCHMARK_RUN_WARNING = 30;
const STEP_STATUS_LABELS = { done: "выполнено", ready: "доступно", blocked: "заблокировано" };
const FEATURE_STATE_LABELS = { current: "актуально", missing: "отсутствует", stale: "устарело" };
// Backend training rule (rhythm_lab.web_app.MIN_TRAINING_ROWS_PER_LABEL); shown so an enabled Train is understandable.
const MIN_ROWS_PER_CLASS = 2;
const READINESS_DEBOUNCE_MS = 250;

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
let selectedTrainingFeatureSet = null;
let recipeMertV2Layer = null;
let sourceCatalogUuid = null;
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
  addOption(profileSelectEl, "", "Выберите профиль");
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
  guidancePanelEl.innerHTML = '<div class="guidance-card"><b>Выберите профиль</b><span class="meta">Выберите или создайте профиль классификатора, чтобы загрузить треки.</span></div>';
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "все метки");
  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "все прогнозы");
  document.getElementById("profileNameInput").value = "";
  document.getElementById("profileDescriptionInput").value = "";
  document.getElementById("profileArtifactPrefixInput").value = "";
  document.getElementById("profileTrainingMinAddedInput").value = "50";
  document.getElementById("profileTrainingMinLabelsInput").value = "100";
  document.getElementById("renameLabelSelect").innerHTML = "";
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
  labelEl.innerHTML = "";
  addOption(labelEl, "all", "все метки");
  addOption(labelEl, "unlabeled", "без метки");
  activeProfile.labels.forEach(label => addOption(labelEl, label.key, label.name));

  candidatePredictedEl.innerHTML = "";
  addOption(candidatePredictedEl, "all", "все прогнозы");
  trainingLabels().forEach(label => addOption(candidatePredictedEl, label.key, `прогноз: ${label.name}`));

  const positive = labelByKey(activeProfile.positive_label);
  const negative = labelByKey(activeProfile.negative_label);
  if (isMulticlassProfile()) {
    if (candidateMinBrokenEl.value === "negative_highest") candidateMinBrokenEl.value = "positive_highest";
    candidateMinBrokenEl.options[0].textContent = "наибольшая уверенность";
    candidateMinBrokenEl.options[1].hidden = true;
    candidateMinBrokenEl.options[1].disabled = true;
    candidateMinBrokenEl.options[2].textContent = "наименьшая уверенность";
  } else {
    candidateMinBrokenEl.options[1].hidden = false;
    candidateMinBrokenEl.options[1].disabled = false;
    candidateMinBrokenEl.options[0].textContent = `наибольшая P(${positive.name})`;
    candidateMinBrokenEl.options[1].textContent = `наибольшая P(${negative.name})`;
    candidateMinBrokenEl.options[2].textContent = "неуверенные / пограничные";
  }

  document.getElementById("profileNameInput").value = activeProfile.name || "";
  document.getElementById("profileDescriptionInput").value = activeProfile.description || "";
  document.getElementById("profileArtifactPrefixInput").value = activeProfile.artifact_prefix || "";
  document.getElementById("profileTrainingMinAddedInput").value = activeProfile.training_min_added || 50;
  document.getElementById("profileTrainingMinLabelsInput").value = activeProfile.training_min_labels ?? 100;

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
  ["openLibrary", "trainRefresh", "runBenchmark", "calibrateClassifier", "refreshCandidates", "promoteClassifier"].forEach(id => {
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
  stageEl.textContent = String(progress?.error || progress?.stage || "Подготовка данных");
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

function startTrainingProgressPolling(profileKey, operation, stage = "Запуск…") {
  stopTrainingProgressPolling();
  trainingProgressHasStarted = false;
  renderTrainingProgress({ status: "running", stage, percent: 0 });
  const pollingGeneration = trainingProgressPollGeneration;
  trainingProgressPollHandle = window.setInterval(() => {
    pollTrainingProgress(profileKey, operation, pollingGeneration).catch(() => {});
  }, 350);
}

async function handleTrainingActionClick(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
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
    addOption(collectionSelectEl, "", "Нет коллекций");
    collectionStatusEl.textContent = "0 коллекций";
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
    ? `${active.track_count} ${pluralRu(active.track_count, "трек", "трека", "треков")}, ${active.source}`
    : `${collections.length} ${pluralRu(collections.length, "коллекция", "коллекции", "коллекций")}`;
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
  // A new library has its own stored families: drop the recipe so readiness
  // returns that library's default, and forget comparisons built for the old one.
  latestTrainingReadiness = null;
  selectedTrainingFeatureSet = null;
  recipeMertV2Layer = null;
  benchmarkCustomSets = [];
  latestBenchmarkReport = null;
  trainingViewProfileKey = null;
  cancelScheduledReadinessRefresh();
  await loadActive({ reset: true });
}

async function loadSourceState() {
  const data = await fetch("/api/source/current").then(parseJsonResponse);
  applySourceState(data);
}

function applySourceState(data) {
  sourcePathEl.value = data.path || sourcePathEl.value || "";
  sourceCatalogUuid = data.catalog_uuid ? String(data.catalog_uuid) : null;
}

function appendRecipeParam(params) {
  if (selectedTrainingFeatureSet) params.set("feature_set", selectedTrainingFeatureSet);
  return params;
}

async function shutdownLab() {
  shutdownLabEl.disabled = true;
  shutdownLabEl.classList.add("stopping");
  setWorkflowStatus("Останавливаю Rhythm Lab…");
  const response = await fetch("/api/shutdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  await parseJsonResponse(response);
  setWorkflowStatus("Rhythm Lab останавливается…");
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
  const coverage = [
    coverageBadge("Треки", data.tracks || 0, "tracks"),
    coverageBadge("Избранное", data.liked || 0, "liked")
  ].join("");
  summaryCoverageEl.innerHTML = `
    <span class="summary-group summary-coverage" aria-label="Покрытие">
      <span class="summary-group-title">Покрытие</span>${coverage}
    </span>`;
  summaryLabelsEl.innerHTML = `
    <span class="summary-group summary-labels" aria-label="Число меток">
      <span class="summary-group-title">Метки</span>${labelCountBadges(data.labels || {})}
    </span>`;
}

function coverageBadge(label, value, key) {
  if (key === "liked") {
    return `
      <button id="likedTab" type="button" class="summary-badge coverage-liked${activeView === "liked" ? " active" : ""}" title="Показать избранные треки" aria-label="Показать избранные треки">
        <svg class="lucide lucide-heart" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
        </svg>
        <span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b>
      </button>`;
  }
  return `<span class="summary-badge coverage-${escapeHtml(key)}"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></span>`;
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
      const title = totals ? `${current} из ${total} размеченных треков «${label.name}» есть в этой библиотеке` : `${label.name}: ${current}`;
      return `<span class="summary-badge label-count-badge" title="${escapeHtml(title)}"><span>${escapeHtml(label.name)}</span><b>${escapeHtml(value)}</b></span>`;
    })
    .join("");
}

function renderGuidance(summary) {
  // Label counts and gates come from the latest readiness only; the summary
  // supplies track/like totals. Before readiness arrives the cards say so.
  const readiness = latestTrainingReadiness;
  const labelsText = readiness
    ? `${labelCoverageSentence(readiness)}${labelsElsewhereNote(readiness)}`
    : "Загружаю состояние обучения…";
  const winner = readiness?.artifact_summary?.benchmark_winner;
  const selected = selectedPromotionOption(readiness);
  const lastRun = readiness?.last_trained_at ? formatHumanDate(readiness.last_trained_at) : "ещё не обучалась";
  const recipe = readiness?.feature_recipe;
  const readinessState = readiness
    ? readiness.ready
      ? "Готово к обучению"
      : "Пока не готово"
    : "Загружаю состояние обучения";
  const recipeState = readiness
    ? recipe?.ready
      ? `признаки ${recipe.feature_set} актуальны`
      : recipeBlockingText(recipe)
    : "проверяю рецепт признаков";
  guidancePanelEl.innerHTML = `
    <div class="guidance-card"><b>${escapeHtml(activeProfile.name)}</b><span class="meta">${escapeHtml(profileSignalText())}</span></div>
    <div class="guidance-card"><b>Метки</b><span class="meta">${escapeHtml(labelsText)}</span></div>
    <div class="guidance-card"><b>Состояние обучения</b><span class="meta">${escapeHtml(readinessState)}, ${escapeHtml(recipeState || "рецепт признаков недоступен")}, последнее обучение: ${escapeHtml(lastRun)}</span></div>
    <div class="guidance-card"><b>Бенчмарк</b><span class="meta">${winner ? `${escapeHtml(winner.feature_set)}, F1 ${formatMetricPercent(winner.macro_f1_mean)}, полнота ${formatMetricPercent(winner.positive_recall_mean)}` : "Победителя бенчмарка пока нет"}</span></div>
    <div class="guidance-card"><b>Продакшен</b><span class="meta">${selected ? `Выбран ${escapeHtml(selected.feature_set)}, F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "Вариант для продвижения пока не выбран"}</span></div>`;
}

// «В этой библиотеке: 11 из 321 abstract_edge, 6 из 315 reference.» — the
// per-class current/total counts from readiness (old payload: current only).
function labelCoverageSentence(data) {
  const totals = labelTotals(data);
  const current = data?.current || {};
  const threshold = Number(data?.label_threshold);
  const hasThreshold = Number.isFinite(threshold) && threshold > 0;
  const parts = trainingLabels().map(label => {
    const have = current[label.key] || 0;
    if (hasThreshold && totals) return `${label.name}: ${have} из ${threshold} нужных (всего размечено ${totals[label.key] || 0})`;
    if (hasThreshold) return `${label.name}: ${have} из ${threshold} нужных`;
    if (totals) return `${have} из ${totals[label.key] || 0} ${label.name}`;
    return `${label.name} ${have}`;
  });
  if (hasThreshold) return `В этой библиотеке: ${parts.join("; ")}.`;
  return totals ? `В этой библиотеке: ${parts.join(", ")}.` : `Метки: ${parts.join(", ")}.`;
}

function labelsElsewhereNote(data) {
  const totals = labelTotals(data);
  if (!totals) return "";
  const current = data?.current || {};
  const farBelow = trainingLabels().some(label => {
    const total = Number(totals[label.key] || 0);
    return total > 0 && Number(current[label.key] || 0) < total / 2;
  });
  return farBelow ? " Остальные размеченные треки не входят в эту библиотеку." : "";
}

function profileTypeLabel() {
  return activeProfile?.profile_type === "multiclass" ? "мультикласс" : "бинарный";
}

function profileSignalText() {
  if (isMulticlassProfile()) {
    return `${profileTypeLabel()}, ${activeProfile.description || "профиль готов к разметке"}`;
  }
  return `${profileTypeLabel()}, положительная: ${labelByKey(activeProfile.positive_label).name}, отрицательная: ${labelByKey(activeProfile.negative_label).name}`;
}

function pluralRu(count, one, few, many) {
  const n = Math.abs(Math.trunc(Number(count) || 0)) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return many;
  if (n1 > 1 && n1 < 5) return few;
  if (n1 === 1) return one;
  return many;
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
  total = data.total;
  offset = data.offset;
  viewOffsets.library = offset;
  tracksEl.innerHTML = "";
  markPageDuplicates(data.items);
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
  appendRecipeParam(params);
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks?${params}`).then(parseJsonResponse);
  if (sequence !== loadSequence || activeView !== "liked") return;
  total = data.total;
  offset = data.offset;
  viewOffsets.liked = offset;
  tracksEl.innerHTML = "";
  markPageDuplicates(data.items);
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
    tracksEl.innerHTML = '<div class="empty-state">Коллекция не выбрана</div>';
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
  total = data.total;
  offset = data.offset;
  viewOffsets.collection = offset;
  tracksEl.innerHTML = "";
  markPageDuplicates(data.items);
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
  if (!window.confirm(`Удалить коллекцию «${collection.name}»? Метки останутся в активном профиле.`)) return;
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
  total = data.total;
  offset = data.offset;
  viewOffsets.candidates = offset;
  tracksEl.innerHTML = "";
  markPageDuplicates(data.items);
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

async function trainRefresh() {
  if (trainingActionElement("trainRefresh")?.disabled) return;
  if (!window.confirm(`Обучить новую модель ${activeProfile.name} по рецепту ${recipeText()} и обновить кандидатов?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Обучение…");
  startTrainingProgressPolling(activeProfile.classifier_key, "train-refresh", "Обучение…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedTrainingFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Обучение завершено. Обучено: ${formatLabelCounts(data.training_counts)}; обновлено ${data.predicted}, пропущено ${data.skipped}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "train-refresh", stage: "Обучение завершено", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", stage: "Обучение не удалось", error: error.message || String(error), percent: 0 });
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
  const warning = plan.count > BENCHMARK_RUN_WARNING ? " Это большой план, он займёт много времени." : "";
  if (!window.confirm(`Запустить бенчмарк «${strategyLabel}» для ${activeProfile.name}? ${plannedRunsText(plan)}.${warning}`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Бенчмарк выполняется…");
  startTrainingProgressPolling(activeProfile.classifier_key, "benchmark", "Бенчмарк выполняется…");
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
    const winner = data.winner?.feature_set ? ` Лучший рецепт: ${data.winner.feature_set}.` : "";
    setWorkflowStatus(`Бенчмарк завершён.${winner}`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "benchmark", stage: "Бенчмарк завершён", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", stage: "Бенчмарк не удался", error: error.message || String(error), percent: 0 });
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
  return selectedTrainingFeatureSet || latestTrainingReadiness?.feature_recipe?.feature_set || "рецепт по умолчанию";
}

async function calibrateClassifier() {
  if (trainingActionElement("calibrateClassifier")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  if (!window.confirm(`Откалибровать новую модель ${activeProfile.name} ${selectedFeatureSet || recipeText()} по всем текущим меткам?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Калибровка…");
  startTrainingProgressPolling(activeProfile.classifier_key, "calibrate", "Калибровка…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/calibrate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Калибровка завершена. ${data.feature_set}: ${fileName(data.artifact)}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "calibrate", stage: "Калибровка завершена", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "calibrate", stage: "Калибровка не удалась", error: error.message || String(error), percent: 0 });
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
  setWorkflowStatus("Обновление кандидатов…");
  startTrainingProgressPolling(activeProfile.classifier_key, "refresh", "Обновление кандидатов…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Обновление кандидатов завершено. ${data.feature_set}: обновлено ${data.predicted}, пропущено ${data.skipped}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "refresh", stage: "Обновление кандидатов завершено", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "refresh", stage: "Обновление кандидатов не удалось", error: error.message || String(error), percent: 0 });
    throw error;
  } finally {
    stopTrainingProgressPolling();
    await loadTrainingReadiness();
  }
}

async function promoteClassifier() {
  if (trainingActionElement("promoteClassifier")?.disabled) return;
  const selectedFeatureSet = selectedArtifactFeatureSet();
  if (!window.confirm(`Продвинуть последнюю модель ${activeProfile.name} ${selectedFeatureSet || recipeText()} в основное приложение?`)) {
    return;
  }
  setWorkflowBusy(true);
  setWorkflowStatus("Продвижение модели…");
  startTrainingProgressPolling(activeProfile.classifier_key, "promote", "Продвижение модели…");
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(recipeBody(selectedFeatureSet))
    });
    const data = await parseRefreshResponse(response);
    setWorkflowStatus(`Продвижение завершено. Модель ${fileName(data.model_path)}, метаданные ${fileName(data.metadata_path)}.`);
    stopTrainingProgressPolling();
    renderTrainingProgress({ status: "completed", operation: "promote", stage: "Продвижение завершено", percent: 100 });
  } catch (error) {
    renderTrainingProgress({ status: "failed", operation: "promote", stage: "Продвижение не удалось", error: error.message || String(error), percent: 0 });
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
    chip.textContent = data.ready ? "Готово к обучению" : "Пока не готово";
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
}

function syncRecipeFromReadiness(data) {
  const recipe = data?.feature_recipe?.feature_set;
  if (!recipe) return;
  selectedTrainingFeatureSet = String(recipe);
  const layer = recipeMertV2LayerFromRecipe(selectedTrainingFeatureSet);
  if (layer !== null) recipeMertV2Layer = layer;
}

function promoteBlockedTitle(selected) {
  if (!selected) return "Сначала обучите и откалибруйте вариант";
  if (selected.spec_compatible !== true) return selected.spec_reason || "Выбранный вариант не соответствует текущей спецификации признаков";
  if (selected.calibration_status !== "calibrated") return "Сначала откалибруйте выбранный вариант";
  return "Продвинуть выбранный откалиброванный вариант";
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
    ? `Логистическая регрессия по классам ${trainingLabels().map(label => label.name).join(", ")}. Каждый трек даёт не больше одной метки класса.`
    : `Логистическая регрессия: ${labelByKey(activeProfile.positive_label).name} против ${labelByKey(activeProfile.negative_label).name}. Метки для ревью в обучение не входят.`;
  trainingPanelEl.innerHTML = `${renderTrainingSkeleton()}<div id="trainingInformation"></div>`;
  trainingViewProfileKey = activeProfile.classifier_key;
  promoteFeatureSetEl = document.getElementById("promoteFeatureSet");
  promoteFeatureSetEl?.addEventListener("change", () => loadTrainingReadiness().catch(showError));
  applyTrainingReadiness(data);
  renderTrainingProgress(latestWorkflowProgress);
}

function renderTrainingLoading(profileName) {
  return `<div class="training-info-card"><b>Загружаю обучение</b>
    <span class="meta training-info-text">Проверяю метки, источники признаков и сохранённые модели для ${escapeHtml(profileName)}…</span>
  </div>`;
}

function renderTrainingLoadError(error) {
  return `<div class="training-info-card"><b>Не удалось загрузить обучение</b>
    <span class="meta training-info-text">${escapeHtml(error?.message || String(error))}</span>
  </div>`;
}

// Static skeleton of the Training block, mounted once per profile. Everything
// that depends on readiness is filled by applyTrainingReadiness().
function renderTrainingSkeleton() {
  return `<div class="classifier-workflow-card">
    <div class="workflow-header">
      <div>
        <b>Рабочий процесс классификатора</b>
        <span class="meta">${escapeHtml(activeProfile.name)}, ${escapeHtml(profileTypeLabel())}</span>
      </div>
      <span id="workflowStateChip" class="workflow-state-chip"></span>
    </div>
    <div class="workflow-recommendation">
      <b>Рекомендация</b>
      <span id="workflowRecommendation"></span>
    </div>
    <div class="recipe-builder">
      <div class="recipe-builder-header">
        <b>Рецепт обучения</b>
        <span class="meta">Выберите одну или несколько моделей, сохранённых в этой библиотеке.</span>
      </div>
      <div id="recipeRack" class="recipe-rack"></div>
      <p class="recipe-line">Рецепт <code id="recipeString"></code>.<span id="recipeMissing" class="recipe-missing"></span></p>
    </div>
    <div class="workflow-variant-row">
      <label class="workflow-variant-select">Выбранный вариант
        <select id="promoteFeatureSet"></select>
      </label>
      <div class="workflow-variant-select">Состояние артефакта
        <span id="artifactState" class="workflow-variant-note"></span>
      </div>
      <div id="workflowFacts" class="workflow-variant-facts"></div>
    </div>
    <div class="training-workflow-feedback"${workflowStatusText ? "" : " hidden"}>
      <span id="refreshCandidatesStatus" class="meta source-status-line">${escapeHtml(workflowStatusText)}</span>
    </div>
    <div id="trainingProgress" class="training-progress" role="status" aria-live="polite" hidden>
      <div class="training-progress-header"><span id="trainingProgressStage"></span><b id="trainingProgressPercent">0%</b></div>
      <div class="training-progress-track"><span id="trainingProgressBar"></span></div>
    </div>
    <div id="workflowSteps" class="workflow-steps"></div>
  </div>`;
}

function renderWorkflowFacts(data, selected) {
  const featureRecipe = data?.feature_recipe || {};
  const winner = data?.artifact_summary?.benchmark_winner;
  const selectedCalibrated = selected?.calibration_status === "calibrated";
  return `
    ${trainingInfoLine("Источники", (featureRecipe.required_sources || []).map(recipeTokenLabel).join(" + ") || "нет")}
    ${trainingInfoLine("Данные", featureRecipe.ready ? "Готовы" : recipeBlockingText(featureRecipe))}
    ${trainingInfoLine("Бенчмарк", winner ? `${winner.feature_set}, F1 ${formatMetricPercent(winner.macro_f1_mean)}, полнота ${formatMetricPercent(winner.positive_recall_mean)}` : "Запустите бенчмарк, чтобы сравнить рецепты.")}
    ${trainingInfoLine("Выбор", selected ? `${selected.feature_set}, место ${selected.rank ?? "-"}, F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "Выберите обученный вариант.")}
    ${trainingInfoLine("Калибровка", selectedCalibrated ? `${selected.calibration_method || "Откалибрована"}, готова к продвижению` : selected ? `Не откалибрована${selected.calibration_reason ? `: ${selected.calibration_reason}` : ""}` : "Вариант не выбран.")}
    ${trainingInfoLine("Вклад моделей", formatFeatureGroupWeights(selected?.feature_group_weights))}
    ${trainingInfoLine("Происхождение", selected ? artifactProvenanceText(selected) : "Вариант не выбран.")}
    ${trainingInfoLine("Основное приложение", selected ? (selected.spec_compatible === true ? "Спецификация признаков совпадает; можно продвигать." : selected.spec_reason || "Спецификация признаков не совпадает с основным приложением.") : "Вариант не выбран.")}`;
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
  const perClassRule = `минимум ${labelThreshold(data)} на класс`;
  return `
    ${renderWorkflowStep({
      number: 1,
      title: "Собрать метки",
      status: data?.labels_ready && !thresholdBlocked ? "done" : "blocked",
      body: thresholdBlocked
        ? `${thresholdReason} ${labelCoverageSentence(data)}${labelsElsewhereNote(data)}`
        : data?.labels_ready
          ? `Меток достаточно (правило: ${perClassRule}). ${labelCoverageSentence(data)}${labelsElsewhereNote(data)} Новых с последнего обучения: ${formatLabelCounts(data?.added || {}, null, trainingLabels())}.`
          : skipped > 0
            ? `${skipped} ${pluralRu(skipped, "размеченный трек не имеет", "размеченных трека не имеют", "размеченных треков не имеют")} актуальных признаков для этого рецепта. Восстановите признаки или добавьте примеры с полным набором признаков: ${missingLabelText(data) || perClassRule}. ${labelCoverageSentence(data)}`
            : `Добавьте недостающие метки (правило: ${perClassRule}): ${missingLabelText(data) || perClassRule}. ${labelCoverageSentence(data)}${labelsElsewhereNote(data)}`,
      action: workflowButton("openLibrary", "library", "Открыть библиотеку", "open-library", false, "Открыть библиотеку для разметки")
    })}
    ${renderWorkflowStep({
      number: 2,
      title: "Обучить модель",
      status: data?.ready ? "ready" : "blocked",
      body: `${trainingPlanText} Рецепт: ${recipeText()}. Считаются метрики оценки, затем сохранённая продакшен-модель переобучается на всех текущих метках; кандидаты обновляются автоматически.${data?.ready ? "" : ` Пока недоступно: ${trainingBlocked}`}`,
      action: workflowButton("trainRefresh", "train", "Обучить", "train-refresh", !data?.ready, data?.ready ? `Обучить ${recipeText()} и обновить кандидатов` : trainingBlocked)
    })}
    ${renderWorkflowStep({
      number: 3,
      title: "Бенчмарк рецептов",
      status: winner ? "done" : benchmarkRun.runnable ? "ready" : "blocked",
      body: `${winner
        ? `Лучший обученный рецепт: ${winner.feature_set}, F1 ${formatMetricPercent(winner.macro_f1_mean)}.`
        : hasSources
          ? "Сравнение рецептов по кросс-валидационному macro-F1."
          : "В этой библиотеке нет сохранённых источников признаков, сравнивать нечего."}${benchmarkRun.runnable ? "" : ` Пока недоступно: ${benchmarkRun.title}`}`,
      details: renderBenchmarkControls(data),
      wide: true,
      action: ""
    })}
    ${renderWorkflowStep({
      number: 4,
      title: "Откалибровать выбранный вариант",
      status: selectedCalibrated ? "done" : canCalibrate ? "ready" : "blocked",
      body: selectedCalibrated
        ? `${selected.feature_set} использует ${selected.calibration_method || "калиброванные"} вероятности и может быть продвинут.`
        : thresholdBlocked
          ? thresholdReason
          : selectedReady && data?.calibration_ready
            ? "Переобучите выбранный рецепт с калибровкой вероятностей перед продвижением."
            : data?.calibration_readiness?.reason || "Обучите или сравните вариант, источники которого сохранены в этой библиотеке.",
      action: workflowButton("calibrateClassifier", "calibrate", "Откалибровать", "calibrate-classifier", !canCalibrate, canCalibrate ? `Откалибровать ${selected.feature_set}` : selectedCalibrated ? "Выбранный вариант уже откалиброван" : thresholdBlocked ? thresholdReason : data?.calibration_readiness?.reason || "Выберите вариант, данные которого есть в этой библиотеке")
    })}
    ${renderWorkflowStep({
      number: 5,
      title: "Обновить и проверить кандидатов",
      status: selectedReady ? "ready" : "blocked",
      body: selectedReady ? `Обновите прогнозы моделью ${selected.feature_set}, затем проверьте неуверенных и уверенных кандидатов.` : "Сначала обучите вариант, источники которого сохранены в этой библиотеке.",
      action: workflowButton("refreshCandidates", "refresh", "Обновить кандидатов", "refresh-candidates", !selectedReady, selectedReady ? `Обновить кандидатов моделью ${selected.feature_set}` : "Выберите вариант, данные которого есть в этой библиотеке")
    })}
    ${renderWorkflowStep({
      number: 6,
      title: "Продвинуть модель",
      status: canPromote ? "ready" : "blocked",
      body: canPromote
        ? `Продвинуть откалиброванную модель ${selected.feature_set} в models/classifiers для скоринга в основном приложении.`
        : selected && selected.spec_compatible !== true
          ? `Только для лаборатории: ${selected.spec_reason || "спецификация признаков не совпадает с основным приложением"}.`
          : "Для продвижения нужен откалиброванный артефакт, спецификация признаков которого совпадает с основным приложением.",
      action: workflowButton("promoteClassifier", "promote", "Продвинуть модель", "promote-classifier", !canPromote, canPromote ? "Продвинуть выбранный откалиброванный вариант" : promoteBlockedTitle(selected))
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
  return `В этой библиотеке меньше ${labelThreshold(data)} меток на класс, а это минимум для обучения.`;
}

function canPromoteArtifact(data) {
  const selected = selectedPromotionOption(data);
  return Boolean(
    selected?.spec_compatible === true
    && selected?.calibration_status === "calibrated"
  );
}

function renderWorkflowStep({ number, title, status, body, details = "", wide = false, action = "" }) {
  return `<section class="workflow-step workflow-step-${status}${wide ? " workflow-step-wide" : ""}">
    <div class="workflow-step-index">${number}</div>
    <div class="workflow-step-copy">
      <div class="workflow-step-title"><b>${escapeHtml(title)}</b><span class="workflow-state-chip ${status}">${escapeHtml(STEP_STATUS_LABELS[status] || status)}</span></div>
      <span class="meta">${escapeHtml(body)}</span>
      ${details}
    </div>
    ${wide ? "" : `<div class="workflow-step-action">${action}</div>`}
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
  if (data?.label_threshold_ready === false) return labelThresholdReason(data);
  if (missing && skipped > 0) return `Восстановите признаки для ${skipped} размеченных треков или добавьте ${missing} примеров с полным набором признаков.`;
  if (missing) return `Добавьте ${missing} перед следующим обучением.`;
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  if (!data?.model_artifact && !(data?.artifact_summary?.promotion_options || []).length) return "Обучите первую модель для этого профиля.";
  if (!data?.artifact_summary?.benchmark_winner) return "Запустите бенчмарк, чтобы выбрать самый сильный рецепт.";
  if (!selected) return "Переобучите вариант на текущих данных источника перед калибровкой или продвижением.";
  if (selected?.calibration_status !== "calibrated" && !data?.calibration_ready) {
    return data?.calibration_readiness?.reason || "Добавьте больше меток перед калибровкой.";
  }
  if (selected?.calibration_status !== "calibrated") return "Откалибруйте выбранный вариант, затем обновите его кандидатов.";
  return "Обновите и проверьте кандидатов откалиброванного варианта, затем продвиньте его.";
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
      return `по ${missingRows[0]} на класс в ${missingRows.length} классах`;
    }
    return `${total} ${pluralRu(total, "метку", "метки", "меток")} в ${missingRows.length} классах`;
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
  return `${list.slice(0, -1).join(", ")} и ${list[list.length - 1]}`;
}

// The rack: one strip of equal-height slots, one per model stored in this
// library, in the mandated order. A recipe is the set of engaged slots.
function renderRecipeSlots(data) {
  const available = orderedFamilies(data?.available_feature_sources || []);
  if (!available.length) return '<span class="meta">В этой библиотеке нет сохранённых источников признаков.</span>';
  const selected = selectedRecipeFamilies();
  const layers = storedMertV2Layers(data);
  const layer = currentMertV2Layer(data);
  return available.map(family => {
    const layerSelect = family === "mert_v2" && layers.length
      ? `<select data-recipe-layer aria-label="Слой MERT-v2" title="Слой MERT-v2, сохранённый в этой библиотеке">${layers.map(value => `<option value="${value}" ${value === layer ? "selected" : ""}>слой ${value}</option>`).join("")}</select>`
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
  if (codeEl) codeEl.textContent = selectedTrainingFeatureSet || "нет";
  const missingEl = document.getElementById("recipeMissing");
  if (missingEl) missingEl.textContent = missingFamiliesText(data);
}

function missingFamiliesText(data) {
  const available = orderedFamilies(data?.available_feature_sources || []);
  const missing = orderedFamilies(Object.keys(data?.source_features || {}))
    .filter(family => !available.includes(family))
    .map(familyLabel);
  if (!missing.length) return "";
  return ` Нет в этой библиотеке: ${missing.join(", ")}. Запустите анализ ${joinNames(missing)} в основном приложении, затем перезагрузите источник.`;
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
  const runs = `${plan.count} ${pluralRu(plan.count, "прогон", "прогона", "прогонов")}`;
  return plan.bound ? `до ${runs}` : runs;
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
      title: benchmarkStrategy === "custom" ? "Добавьте хотя бы один рецепт для сравнения" : "В этой библиотеке нет сохранённых источников признаков",
    };
  }
  return { runnable: true, plan, title: `Запустить бенчмарк: ${BENCHMARK_STRATEGY_LABELS[benchmarkStrategy] || benchmarkStrategy}, ${plannedRunsText(plan)}` };
}

function benchmarkPlanHintText(plan) {
  const runs = plannedRunsText(plan);
  return plan.count > BENCHMARK_RUN_WARNING ? `${runs}, это займёт много времени` : runs;
}

function renderBenchmarkControls(data) {
  const run = benchmarkRunState(data);
  const options = benchmarkStrategies(data)
    .map(key => `<option value="${escapeHtml(key)}" ${key === benchmarkStrategy ? "selected" : ""}>${escapeHtml(BENCHMARK_STRATEGY_LABELS[key])}</option>`)
    .join("");
  return `<div class="benchmark-controls">
    <div class="benchmark-row">
      <label class="benchmark-strategy">Стратегия
        <select id="benchmarkStrategy">${options}</select>
      </label>
      <span id="benchmarkPlanHint" class="benchmark-plan-hint${run.plan.count > BENCHMARK_RUN_WARNING ? " warning" : ""}">${escapeHtml(benchmarkPlanHintText(run.plan))}</span>
      ${workflowButton("runBenchmark", "benchmark", "Запустить бенчмарк", "run-benchmark", !run.runnable, run.title)}
    </div>
    <div id="benchmarkCustom" class="benchmark-custom" hidden>
      <button type="button" data-benchmark-add title="Добавить текущий рецепт обучения в сравнение">Добавить текущий рецепт</button>
      <div id="benchmarkCustomList"></div>
    </div>
    <div id="benchmarkResults" class="benchmark-results">${renderBenchmarkResults()}</div>
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
  if (!benchmarkCustomSets.length) return '<span class="meta">Рецепты ещё не добавлены. Соберите рецепт в стойке и добавьте его сюда.</span>';
  return `<ul class="benchmark-custom-list">${benchmarkCustomSets
    .map(featureSet => `<li><code>${escapeHtml(featureSet)}</code><button type="button" data-benchmark-remove="${escapeHtml(featureSet)}" title="Убрать ${escapeHtml(featureSet)} из сравнения">Убрать</button></li>`)
    .join("")}</ul>`;
}

function benchmarkResultRows(report = latestBenchmarkReport) {
  const rows = Array.isArray(report?.profile?.results) ? report.profile.results : [];
  return rows
    .map(row => {
      const cv = row?.metrics?.cross_validation || {};
      const mean = Number(cv.macro_f1_mean);
      const std = Number(cv.macro_f1_std);
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
  if (!report) return '<span class="meta">Запустите бенчмарк, чтобы сравнить рецепты.</span>';
  const rows = benchmarkResultRows(report);
  if (!rows.length) return '<span class="meta">Бенчмарк не вернул результатов.</span>';
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
    const delta = isTrained && reference ? (row === reference ? "база" : formatLadderDelta(row.mean, reference.mean)) : "";
    const recipe = isTrained
      ? `<code>${escapeHtml(row.featureSet)}</code>`
      : `<code>${escapeHtml(row.featureSet)}</code> <span class="meta">${escapeHtml(row.error || row.status)}</span>`;
    const action = isTrained
      ? `<button type="button" data-recipe-apply="${escapeHtml(row.featureSet)}" title="Сделать ${escapeHtml(row.featureSet)} рецептом обучения">Использовать этот рецепт</button>`
      : "";
    body.push(`<tr class="${classes}"><td class="ladder-rank">${isTrained ? index + 1 : ""}</td><td class="ladder-recipe">${recipe}</td><td class="ladder-number">${score}</td><td class="ladder-number">${delta}</td><td class="ladder-action">${action}</td></tr>`);
    if (bracket && index === bandSize - 1) {
      body.push('<tr class="ladder-band ladder-band-caption"><td></td><td colspan="4">в пределах шума лучшего</td></tr>');
    }
  });
  const note = reference
    ? ""
    : '<p class="meta ladder-note">Рецепт со всеми моделями не участвовал в прогоне, поэтому колонка с разницей пуста.</p>';
  return `<div class="ladder-scroll"><table class="ladder">
    <thead><tr><th class="ladder-rank">#</th><th>Рецепт</th><th class="ladder-number">Macro-F1 (%)</th><th class="ladder-number">к рецепту со всеми моделями</th><th></th></tr></thead>
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
  if (!uuid) return "Каталог источника неизвестен";
  const short = uuid.slice(0, 8);
  return sourceCatalogUuid && uuid === sourceCatalogUuid ? `Обучена на этой библиотеке (${short})` : `Обучена на другой библиотеке (${short})`;
}

function sentenceFragment(text, fallback) {
  return String(text || fallback).trim().replace(/\.$/, "");
}

function artifactStateText(row) {
  if (!row) return "Обученного варианта пока нет.";
  const dataState = row.source_data_ready === true
    ? "Данные источника актуальны."
    : `Данные источника заблокированы: ${sentenceFragment(row.source_data_reason, "недоступны")}.`;
  const specState = row.spec_compatible === true
    ? "Можно продвинуть в основное приложение."
    : `Нельзя продвинуть: ${sentenceFragment(row.spec_reason, "спецификация признаков не совпадает")}.`;
  return `${artifactProvenanceText(row)}. ${dataState} ${specState}`;
}

function recipeBlockingText(recipe) {
  const blocking = recipe?.blocking || [];
  if (!blocking.length) return "Состояние рецепта признаков недоступно";
  return blocking
    .map(item => `${recipeTokenLabel(item.source)}: ${item.reason || FEATURE_STATE_LABELS[item.status] || item.status || "не актуально"}`)
    .join("; ");
}

// The reason a training gate is closed, in priority order: per-class label
// threshold (backend text verbatim), recipe data, then missing labels.
function readinessBlockedTitle(data) {
  if (data?.label_threshold_ready === false) return labelThresholdReason(data);
  if (!data?.features_ready) return recipeBlockingText(data?.feature_recipe);
  return `Добавьте недостающие метки: ${missingLabelText(data) || `минимум ${labelThreshold(data)} на класс`}.`;
}

function updatePromoteFeatureSetOptions(data) {
  if (!promoteFeatureSetEl) return;
  const options = data?.artifact_summary?.promotion_options || [];
  const usableOptions = options.filter(selectableOption);
  const selected = selectedPromotionOption(data);
  const previous = promoteFeatureSetEl.value;
  promoteFeatureSetEl.innerHTML = options.length
    ? renderPromotionOptions(options)
    : '<option value="">Нет обученной модели</option>';
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
    : '<option value="">Нет обученной модели</option>';
}

function promotionOptionLabel(row) {
  const rank = row.rank ? `место ${row.rank}` : "без места";
  const calibration = row.calibration_status === "calibrated"
    ? `откалибрована ${row.calibration_method || ""}`.trim()
    : "не откалибрована";
  const uuid = String(row.source_catalog_uuid || "").trim();
  const provenance = !uuid ? "библиотека неизвестна" : sourceCatalogUuid && uuid === sourceCatalogUuid ? "эта библиотека" : "другая библиотека";
  const state = `${row.source_data_ready === true ? "данные актуальны" : "данные заблокированы"}, ${row.spec_compatible === true ? "можно продвигать" : "нельзя продвигать"}`;
  return `${row.feature_set || "модель"}, ${rank}, F1 ${formatMetricPercent(row.macro_f1_mean)}, ${calibration}, ${formatHumanDate(row.created_at)}, ${provenance}, ${state}`;
}

function formatFeatureGroupWeights(weights) {
  if (!weights || typeof weights !== "object") return "Для этого артефакта не записан.";
  const entries = Object.entries(weights);
  if (!entries.length) return "Для этого артефакта не записан.";
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
      <b>Обзор обучения</b>
      <span class="meta">Последний чекпоинт обучения и продвинутая модель, которой считаются оценки.</span>
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
    return trainingInfoLine("Обученная модель", "Чекпоинт обучения ещё не записан.");
  }
  return trainingInfoLine(
    "Обученная модель",
    `Последний чекпоинт: ${model.feature_set || "рецепт неизвестен"}, ${formatHumanDate(model.trained_at)}, ${formatLabelCounts(model.label_counts || {})}`
  );
}

function renderTrainingPromotedModelLine(model) {
  if (!model || model.status === "not_promoted") {
    return trainingInfoLine("Продвинутая модель", "Продакшен-модель ещё не продвинута.");
  }
  const status = model.status === "ready"
    ? "готова к скорингу"
    : `недействительна: ${(model.manifest_errors || ["продакшен-манифест непригоден"])[0]}`;
  const promotedAt = model.promoted_at ? formatHumanDate(model.promoted_at) : "дата неизвестна";
  return trainingInfoLine(
    "Продвинутая модель",
    `${model.feature_set || "рецепт неизвестен"}, продвинута ${promotedAt}, ${status}`
  );
}

function renderTrainingMetricsLine(model) {
  if (!model || model.status !== "ready") {
    return trainingInfoLine("Качество", "Нет продвинутого model.json, чтобы оценить качество скоринга.");
  }
  const calibration = model.calibration || {};
  const calibrationState = model.calibration_status === "calibrated"
    ? `откалибрована${calibration.method ? ` (${calibration.method})` : ""}`
    : `не откалибрована${calibration.reason ? `: ${calibration.reason}` : ""}`;
  const values = [
    `вариант ${model.feature_set || "рецепт неизвестен"}`,
    calibrationState,
    `скоринг: ${model.score_semantics || "не записан"}`,
    metricPercentText("F1 на валидации", calibration.validation_f1),
    metricPercentText("ROC-AUC", calibration.validation_roc_auc),
    metricPercentText("средняя точность", calibration.validation_average_precision),
    metricNumberText("Brier", calibration.brier),
    metricPercentText("ECE10", calibration.ece10),
  ].filter(Boolean).join(", ");
  return trainingInfoLine("Качество", `Продвинутый model.json: ${values}`);
}

function metricPercentText(label, value) {
  return Number.isFinite(Number(value)) ? `${label} ${formatMetricPercent(value)}` : "";
}

function metricNumberText(label, value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${label} ${number.toFixed(3)}` : "";
}

function renderTrainingDynamicsLine(history) {
  const latest = (history || [])[0];
  const previous = (history || [])[1];
  if (!latest) return trainingInfoLine("Динамика", `Обучите ${recipeText()}, чтобы получить базовую линию.`);
  const trend = previous
    ? `к предыдущему запуску: точность ${formatMetricDelta(latest.accuracy_mean, previous.accuracy_mean)}, F1 ${formatMetricDelta(latest.macro_f1_mean, previous.macro_f1_mean)}`
    : "Первая записанная модель для этого рецепта.";
  return trainingInfoLine(
    "Динамика",
    `${trend}; ${formatHumanDate(latest.created_at)}, размеченных треков: ${latest.trained_rows ?? "-"}, точность ${formatMetricPercent(latest.accuracy_mean)}, F1 ${formatMetricPercent(latest.macro_f1_mean)}`
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
      return `<span class="maest-genre-pill">${escapeHtml(genre)}${confidence}</span>`;
    })
    .join("");
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
        <div class="meta genres-line"><span class="status-item"><b>ЖАНРЫ</b></span><span class="genres">${genreBadges(track)}</span>${badgeRow(track)}</div>
        <audio controls preload="none" src="/media/${track.track_id}"></audio>
      </div>
    </div>
    <div class="actions">
      <div class="row-tools">${renderLikeButton(track)}</div>
      <div class="label-actions ${isMulticlassProfile() && hasContentKey(track) ? "multiclass-label-actions" : ""}">${hasContentKey(track) ? renderLabelButtons(track) : noFingerprintHint()}</div>
    </div>`;
}

// Phase-1 identity: labels bind to the SONARA fingerprint (content_key), so a
// track without one cannot be labeled here, and rows sharing a key share a label.
function hasContentKey(track) {
  return typeof track?.content_key === "string" && track.content_key.length > 0;
}

function noFingerprintHint() {
  return '<span class="meta label-hint" title="Метки привязаны к отпечатку SONARA, у этого трека его пока нет">Нет отпечатка SONARA для этого трека. Проанализируйте его в основном приложении.</span>';
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
    ? '<span class="profile-label-badge duplicate-badge" title="Тот же контент, что и у строки выше на этой странице; метка общая">дубль</span>'
    : "";
}

function renderLikeButton(track) {
  const active = track.liked ? " active intent-liked" : "";
  const fill = track.liked ? "currentColor" : "none";
  const title = track.liked ? "Убрать из избранного" : "В избранное";
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
  buttons.push('<button type="button" data-action="label" data-label="">Снять метку</button>');
  return buttons.join("");
}

function wireTrackRow(row, track) {
  const likeButton = row.querySelector('[data-action="like"]');
  if (likeButton) likeButton.addEventListener("click", () => toggleLike(track).catch(showError));
  row.querySelectorAll('[data-action="label"]').forEach(button => {
    button.addEventListener("click", () => setLabel(track.track_id, button.dataset.label));
  });
  row.addEventListener("keydown", event => {
    if (!hasContentKey(track)) return;
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
      training_min_added: Number(document.getElementById("profileTrainingMinAddedInput").value || 50),
      training_min_labels: Number(document.getElementById("profileTrainingMinLabelsInput").value || 100)
    })
  });
  const profile = await parseJsonResponse(response);
  await loadProfiles();
  await setActiveProfile(profile.classifier_key, { skipLoad: true });
  setWorkflowStatus("Профиль сохранён");
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
    `Удалить ${activeProfile.name}? Будут безвозвратно удалены метки Rhythm Lab, прогнозы, очередь разметки, чекпоинты, метрики и локальные артефакты обучения этого профиля. Продвинутые модели в models/classifiers останутся.\n\nВведите «${activeProfile.name}» или «${activeProfile.classifier_key}», чтобы удалить.`
  );
  if (confirmation === null) return;
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: confirmation })
  });
  const data = await parseJsonResponse(response);
  setWorkflowStatus(`Удалён ${data.name}, файлов артефактов: ${data.artifact_cleanup?.deleted_files || 0}`);
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
  const badges = [duplicateBadge(track), syncopatedBadge(track)].filter(Boolean);
  return badges.length ? `<div class="badge-row">${badges.join('<span class="badge-separator">·</span>')}</div>` : "";
}

function syncopatedBadge(track) {
  return track.maest_syncopated_rhythm === true
    ? `<span aria-label="синкопированный ритм" class="syncopated-rhythm-indicator" role="img" title="MAEST обнаружил синкопированный ритм">
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
  const sign = delta < 0 ? "−" : "+";
  return `${sign}${Math.abs(delta).toFixed(1)} п.п.`;
}

function formatHumanDate(value) {
  const date = parseTrainingDate(value);
  if (!date) return "никогда";
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

function mark(value) {
  return value ? "ДА" : "НЕТ";
}

function trackStatusLine(track) {
  return [
    trainedStatus(track),
    assignedLabelStatus(track),
    activeView === "candidates" ? predictionScoreStatus(track) : "",
  ].filter(Boolean).join(" ");
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
      return `${recipeTokenLabel(source)} (${FEATURE_STATE_LABELS[status] || status}: ${featureStateReason(state) || "не актуально"})`;
    });
}

function featuresIndicator(track) {
  const required = requiredFeatureSources();
  if (!required.length) return "";
  const ready = featuresReady(track);
  const recipe = latestTrainingReadiness?.feature_recipe?.feature_set || required.join("+");
  const label = ready
    ? `Признаки для ${recipe} готовы: ${required.map(recipeTokenLabel).join(", ")}`
    : `Для ${recipe} не хватает: ${missingFeatures(track).join(", ")}`;
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

function trainedStatus(track) {
  return featureStatusBadge("ОБУЧЕНО", track.label_trained);
}

function assignedLabelStatus(track) {
  if (isMulticlassProfile()) return "";
  if (track.label !== activeProfile.positive_label && track.label !== activeProfile.negative_label) return "";
  const label = labelByKey(track.label);
  const status = track.label === activeProfile.positive_label ? "status-yes" : "status-no";
  return `<span class="status-item"><b>МЕТКА</b><span class="analysis-status-badge ${status}">${escapeHtml(label.name)}</span></span>`;
}

function predictionScoreStatus(track) {
  return track.predicted_label
    ? `<span class="status-item"><b>ОЦЕНКА</b><span class="status-detail">${formatProbability(predictedScore(track))}</span></span>`
    : "";
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
