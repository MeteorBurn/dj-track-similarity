const tracksEl = document.getElementById("tracks");
const queryEl = document.getElementById("query");
const sourcePathEl = document.getElementById("sourcePath");
const profileSelectEl = document.getElementById("profileSelect");
const activeProfileNameEl = document.getElementById("activeProfileName");
const shutdownLabEl = document.getElementById("shutdownLab");
const libraryTabEl = document.getElementById("libraryTab");
const candidatesTabEl = document.getElementById("candidatesTab");
const likedTabEl = document.getElementById("likedTab");
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
const archiveProfileEl = document.getElementById("archiveProfile");
const refreshCandidatesStatusEl = document.getElementById("refreshCandidatesStatus");
const summaryEl = document.getElementById("summary");
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

document.getElementById("load").addEventListener("click", () => loadActive({ reset: true }));
document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(showError));
document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(showError));
document.getElementById("newProfile").addEventListener("click", () => profileDialogEl.showModal());
shutdownLabEl.addEventListener("click", () => shutdownLab().catch(showError));
archiveProfileEl.addEventListener("click", () => archiveActiveProfile().catch(showError));
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
likedTabEl.addEventListener("click", () => switchView("liked"));
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
  if (!profiles.length) throw new Error("No classifier profiles are available");
  if (activeProfile && profiles.some(profile => profile.classifier_key === activeProfile.classifier_key)) {
    await setActiveProfile(activeProfile.classifier_key, { skipLoad: true });
  } else {
    clearActiveProfile();
  }
}

async function setActiveProfile(profileKey, options = {}) {
  activeProfile = profiles.find(profile => profile.classifier_key === profileKey) || null;
  if (!activeProfile) {
    clearActiveProfile();
    return;
  }
  profileSelectEl.value = activeProfile.classifier_key;
  activeProfileNameEl.textContent = activeProfile.name;
  latestTrainingReadiness = null;
  latestProfileSummary = null;
  promoteFeatureSetEl = null;
  renderProfileControls();
  offset = 0;
  viewOffsets.library = 0;
  viewOffsets.candidates = 0;
  viewOffsets.liked = 0;
  viewOffsets.collection = 0;
  if (!options.skipLoad) await loadActive({ reset: true });
}

function clearActiveProfile() {
  activeProfile = null;
  latestTrainingReadiness = null;
  latestProfileSummary = null;
  promoteFeatureSetEl = null;
  profileSelectEl.value = "";
  activeProfileNameEl.textContent = "No profile selected";
  summaryEl.textContent = "";
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
  document.getElementById("profileArtifactDirInput").value = "";
  document.getElementById("profileArtifactPrefixInput").value = "";
  document.getElementById("profileTrainingMinAddedInput").value = "50";
  document.getElementById("renameLabelSelect").innerHTML = "";
  archiveProfileEl.disabled = true;
  setWorkflowBusy(true);
  updateLibraryOrderControls();
}

function renderProfileControls() {
  archiveProfileEl.disabled = false;
  setTrainingActionDisabled("openLibrary", false);
  setTrainingActionDisabled("openCandidates", true);
  setTrainingActionDisabled("runBenchmark", true);
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
  document.getElementById("profileArtifactDirInput").value = activeProfile.artifact_dir || "";
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
  ["openLibrary", "trainRefresh", "openCandidates", "runBenchmark", "promoteClassifier"].forEach(id => {
    setTrainingActionDisabled(id, disabled);
  });
}

async function handleTrainingActionClick(event) {
  const button = event.target.closest("button[data-training-action]");
  if (!button) return;
  const action = button.dataset.trainingAction;
  if (action === "library") return openLibraryForLabels();
  if (action === "train") return trainRefresh();
  if (action === "candidates") return openCandidatesForReview();
  if (action === "benchmark") return runBenchmark();
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
  refreshCandidatesStatusEl.textContent = "stopping Rhythm Lab...";
  const response = await fetch("/api/shutdown", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  });
  await parseJsonResponse(response);
  refreshCandidatesStatusEl.textContent = "Rhythm Lab stopping...";
  window.setTimeout(() => window.close(), 300);
}

async function switchView(view) {
  viewOffsets[activeView] = offset;
  activeView = view;
  offset = viewOffsets[view] || 0;
  libraryTabEl.classList.toggle("active", view === "library");
  candidatesTabEl.classList.toggle("active", view === "candidates");
  likedTabEl.classList.toggle("active", view === "liked");
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
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/summary`).then(parseJsonResponse);
  if (sequence !== loadSequence) return;
  latestProfileSummary = data;
  summaryEl.innerHTML = renderSummary(data);
  renderGuidance(data);
}

function formatLabelCounts(labels) {
  const counts = labels || {};
  return activeProfile.labels.map(label => `${label.name} ${counts[label.key] || 0}`).join(" · ");
}

function renderSummary(data) {
  const coverage = [
    coverageBadge("Tracks", data.tracks || 0, "tracks"),
    coverageBadge("SONARA", data.sonara || 0, "sonara"),
    coverageBadge("MAEST", data.maest || 0, "maest"),
    coverageBadge("MERT", data.mert || 0, "mert"),
    coverageBadge("Liked", data.liked || 0, "liked")
  ].join("");
  return `
    <span class="summary-group summary-coverage" aria-label="Feature coverage">
      <span class="summary-group-title">Coverage</span>${coverage}
    </span>
    <span class="summary-group summary-labels" aria-label="Label counts">
      <span class="summary-group-title">Labels</span>${labelCountBadges(data.labels || {})}
    </span>`;
}

function coverageBadge(label, value, key) {
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
  const trainingCountText = trainingLabels().map(label => `${escapeHtml(label.name)} ${readiness?.current?.[label.key] ?? counts[label.key] ?? 0}`).join(" · ");
  const winner = readiness?.artifact_summary?.benchmark_winner;
  const selected = selectedPromotionOption(readiness);
  const lastRun = readiness?.last_trained_at ? formatHumanDate(readiness.last_trained_at) : "not trained yet";
  guidancePanelEl.innerHTML = `
    <div class="guidance-card"><b>${escapeHtml(activeProfile.name)}</b><span class="meta">${escapeHtml(profileSignalText())}</span></div>
    <div class="guidance-card"><b>Labels</b><span class="meta">${trainingCountText}</span></div>
    <div class="guidance-card"><b>Training state</b><span class="meta">${readiness?.ready ? "Ready to train" : "Not ready yet"} · last ${escapeHtml(lastRun)}</span></div>
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
  if (!window.confirm(`Train a new ${activeProfile.name} model, then refresh candidates?`)) {
    return;
  }
  setWorkflowBusy(true);
  refreshCandidatesStatusEl.textContent = "training model...";
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, { method: "POST" });
    const data = await parseRefreshResponse(response);
    refreshCandidatesStatusEl.textContent = `trained ${formatLabelCounts(data.training_counts)} · updated ${data.predicted} · skipped ${data.skipped}`;
    await switchView("candidates");
    await loadCandidates({ reset: true });
  } finally {
    await loadTrainingReadiness();
  }
}

async function runBenchmark() {
  if (trainingActionElement("runBenchmark")?.disabled) return;
  if (!window.confirm(`Run a full feature benchmark for ${activeProfile.name}?`)) {
    return;
  }
  setWorkflowBusy(true);
  refreshCandidatesStatusEl.textContent = "running benchmark...";
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/benchmark`, { method: "POST" });
    const data = await parseRefreshResponse(response);
    const winner = data.winner?.feature_set ? ` · winner ${data.winner.feature_set}` : "";
    refreshCandidatesStatusEl.textContent = `benchmark complete${winner}`;
    if (activeView === "training") {
      await loadTrainingView();
    } else {
      await loadTrainingReadiness();
    }
  } finally {
    await loadTrainingReadiness();
  }
}

async function promoteClassifier() {
  if (trainingActionElement("promoteClassifier")?.disabled) return;
  const selectedFeatureSet = promoteFeatureSetEl?.value || selectedPromotionOption(latestTrainingReadiness)?.feature_set || "combined";
  if (!window.confirm(`Promote the latest ${activeProfile.name} ${selectedFeatureSet} model to the main app?`)) {
    return;
  }
  setTrainingActionDisabled("promoteClassifier", true);
  refreshCandidatesStatusEl.textContent = "promoting model...";
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feature_set: selectedFeatureSet || undefined })
    });
    const data = await parseRefreshResponse(response);
    refreshCandidatesStatusEl.textContent = `promoted ${fileName(data.model_path)} · metadata ${fileName(data.metadata_path)}`;
  } finally {
    await loadTrainingReadiness();
  }
}

async function loadTrainingReadiness() {
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/readiness`);
  const data = await response.json();
  if (!response.ok) {
    setWorkflowBusy(true);
    return;
  }
  latestTrainingReadiness = data;
  updatePromoteFeatureSetOptions(data);
  const hasModel = hasTrainedVariant(data);
  setTrainingActionDisabled("openLibrary", false, "Open Library to label tracks");
  setTrainingActionDisabled(
    "trainRefresh",
    !data.ready,
    data.ready ? "Retrain from all current labels and refresh candidates" : `Need enough new labels. Added: ${formatLabelCounts(data.added)}.`
  );
  setTrainingActionDisabled(
    "openCandidates",
    !hasModel,
    hasModel ? "Open model candidates for review" : "Train a model before reviewing candidates"
  );
  setTrainingActionDisabled(
    "runBenchmark",
    !hasModel,
    hasModel ? "Run benchmark" : "Train the first model before benchmarking"
  );
  const canPromote = Boolean((data.artifact_summary?.promotion_options || []).length || data.artifact_summary?.latest_combined);
  setTrainingActionDisabled(
    "promoteClassifier",
    !canPromote,
    canPromote ? `Promote selected ${selectedPromotionOption(data)?.feature_set || "combined"} model to main app` : "Train a model before promoting"
  );
  if (latestProfileSummary) renderGuidance(latestProfileSummary);
  return data;
}

async function loadTrainingView() {
  const data = await loadTrainingReadiness();
  await loadSummary();
  const planText = isMulticlassProfile()
    ? `Guided Logistic Regression across ${trainingLabels().map(label => escapeHtml(label.name)).join(", ")}. Each track contributes at most one class label.`
    : `Guided Logistic Regression on ${escapeHtml(labelByKey(activeProfile.positive_label).name)} vs ${escapeHtml(labelByKey(activeProfile.negative_label).name)}. Review-only labels stay out of fitting.`;
  trainingPanelEl.innerHTML = `
    ${renderTrainingWorkflow(data, planText)}
    ${renderTrainingInformationMetrics(data)}`;
  promoteFeatureSetEl = document.getElementById("promoteFeatureSet");
  promoteFeatureSetEl?.addEventListener("change", () => loadTrainingReadiness().catch(showError));
  updatePromoteFeatureSetOptions(data);
}

function renderTrainingWorkflow(data, planText) {
  const options = data?.artifact_summary?.promotion_options || [];
  const selected = selectedPromotionOption(data);
  const winner = data?.artifact_summary?.benchmark_winner;
  const optionMarkup = renderPromotionOptions(options);
  const hasModel = hasTrainedVariant(data);
  const canPromote = Boolean(options.length || data?.artifact_summary?.latest_combined);
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
      <label class="workflow-variant-select">Selected variant
        <select id="promoteFeatureSet" ${options.length ? "" : "disabled"}>${optionMarkup}</select>
      </label>
      <div class="workflow-variant-facts">
        ${trainingInfoLine("Benchmark winner", winner ? `${winner.feature_set} · F1 ${formatMetricPercent(winner.macro_f1_mean)} · recall ${formatMetricPercent(winner.positive_recall_mean)}` : "No winner yet")}
        ${trainingInfoLine("Selected", selected ? `${selected.feature_set} · rank ${selected.rank ?? "-"} · F1 ${formatMetricPercent(selected.macro_f1_mean)}` : "No selected variant yet")}
      </div>
    </div>
    <div class="workflow-steps">
      ${renderWorkflowStep({
        number: 1,
        title: "Collect labels",
        status: "ready",
        body: `Label enough tracks for this profile before training. Need: ${formatLabelCounts(data?.required_added || {})}. Current new labels: ${formatLabelCounts(data?.added || {})}.`,
        action: workflowButton("openLibrary", "library", "Open Library", "open-library", false, "Open Library to label tracks")
      })}
      ${renderWorkflowStep({
        number: 2,
        title: "Train model",
        status: data?.ready ? "ready" : "blocked",
        body: `${planText} Retrain from all current labels, create a new artifact, then refresh candidates automatically.`,
        action: workflowButton("trainRefresh", "train", "Train", "train-refresh", !data?.ready, data?.ready ? "Retrain model and refresh candidates" : `Need enough new labels. Added: ${formatLabelCounts(data?.added || {})}.`)
      })}
      ${renderWorkflowStep({
        number: 3,
        title: "Review candidates",
        status: hasModel ? "ready" : "blocked",
        body: hasModel ? "Open model-suggested candidates, review uncertain or high-confidence predictions, and add more labels for the next training run." : "Train the first model before candidate review is available.",
        action: workflowButton("openCandidates", "candidates", "Open Candidates", "open-candidates", !hasModel, hasModel ? "Open model candidates for review" : "Train a model before reviewing candidates")
      })}
      ${renderWorkflowStep({
        number: 4,
        title: "Benchmark variants",
        status: winner ? "done" : hasModel ? "ready" : "blocked",
        body: winner ? `Current winner: ${winner.feature_set} · F1 ${formatMetricPercent(winner.macro_f1_mean)}.` : "Compare SONARA, MERT, MAEST, and CLAP feature-source combinations.",
        action: workflowButton("runBenchmark", "benchmark", "Run benchmark", "run-benchmark", !hasModel, hasModel ? "Run benchmark" : "Train the first model before benchmarking")
      })}
      ${renderWorkflowStep({
        number: 5,
        title: "Promote model",
        status: canPromote ? "ready" : "blocked",
        body: selected ? `Promote ${selected.feature_set} into models/classifiers, then reset and rescore this classifier in the main database.` : "No trained variant is available for promotion.",
        action: workflowButton("promoteClassifier", "promote", "Promote", "promote-classifier", !canPromote, canPromote ? "Promote selected variant" : "Train a model before promoting")
      })}
    </div>
  </div>`;
}

function hasTrainedVariant(data) {
  return Boolean(
    data?.model_artifact ||
    data?.artifact_summary?.latest_combined ||
    (data?.artifact_summary?.promotion_options || []).length
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
  return '<svg class="lucide lucide-upload" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" x2="12" y1="3" y2="15" /></svg>';
}

function workflowRecommendation(data, selected) {
  const missing = missingLabelText(data);
  if (missing) return `Add ${missing} before the next train run.`;
  if (!data?.model_artifact && !(data?.artifact_summary?.promotion_options || []).length) return "Train the first model for this profile.";
  if (!data?.artifact_summary?.benchmark_winner) return "Run benchmark to choose the strongest feature-source variant.";
  if (selected) return "Review the selected promotion variant, then promote it when the metrics look right.";
  return "Choose a promotion variant before releasing the classifier.";
}

function missingLabelText(data) {
  const added = data?.added || {};
  const required = data?.required_added || {};
  const missing = {};
  const missingRows = [];
  let hasMissing = false;
  trainingLabels().forEach(label => {
    const value = Math.max(0, Number(required[label.key] || 0) - Number(added[label.key] || 0));
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

function updatePromoteFeatureSetOptions(data) {
  if (!promoteFeatureSetEl) return;
  const options = data?.artifact_summary?.promotion_options || [];
  const selected = selectedPromotionOption(data);
  const previous = promoteFeatureSetEl.value;
  promoteFeatureSetEl.innerHTML = options.length
    ? renderPromotionOptions(options)
    : '<option value="">No trained model</option>';
  const allowedValues = new Set(options.map(row => String(row.feature_set || "")));
  promoteFeatureSetEl.value = allowedValues.has(previous) ? previous : String(selected?.feature_set || "");
  promoteFeatureSetEl.disabled = options.length === 0;
}

function selectedPromotionOption(data) {
  const options = data?.artifact_summary?.promotion_options || [];
  const requested = promoteFeatureSetEl?.value;
  return options.find(row => row.feature_set === requested) || data?.artifact_summary?.latest_promotable || options[0] || null;
}

function renderPromotionOptions(options) {
  return options.length
    ? options.map(row => `<option value="${escapeHtml(String(row.feature_set || ""))}">${escapeHtml(promotionOptionLabel(row))}</option>`).join("")
    : '<option value="">No trained model</option>';
}

function promotionOptionLabel(row) {
  const rank = row.rank ? `#${row.rank}` : "unranked";
  return `${row.feature_set || "model"} · ${rank} · F1 ${formatMetricPercent(row.macro_f1_mean)} · ${formatHumanDate(row.created_at)}`;
}

function renderTrainingInformationMetrics(data) {
  return `<div class="training-info-card"><b>Training Stats</b>
    <span class="meta training-info-text">
      ${renderTrainingLastRunLine(data)}
      ${renderTrainingArtifactsLine(data?.artifact_summary)}
      ${renderTrainingMetricsLine(data?.artifact_summary)}
      ${renderTrainingDynamicsLine(data?.metrics_history)}
    </span>
  </div>`;
}

function renderTrainingLastRunLine(data) {
  const combined = featureSummary(data?.artifact_summary, "combined");
  const artifact = data?.model_artifact || data?.artifact_summary?.latest_combined;
  const runDate = combined?.created_at || data?.last_trained_at;
  const modelText = combined
    ? `${combined.feature_set} model ${formatBytes(combined.model_bytes)}`
    : fileName(artifact) || "no combined model";
  return trainingInfoLine("Last run", `${formatHumanDate(runDate)} · labels ${formatLabelCounts(data?.last_trained || {})} · ${modelText}`);
}

function renderTrainingArtifactsLine(summary) {
  const features = summary?.by_feature || [];
  const combined = featureSummary(summary, "combined");
  const header = `${summary?.model_count || 0} models · ${summary?.metrics_count || 0} metrics · ${summary?.artifact_prefix || activeProfile.artifact_prefix || "profile"}`;
  const featureNames = features.map(row => String(row.feature_set || "").toUpperCase()).join(", ");
  const detail = features.length
    ? `${features.length} feature sets · latest combined ${combined?.created_at ? formatHumanDate(combined.created_at) : "none"} · ${featureNames}`
    : "no profile artifacts found";
  return trainingInfoLine("Artifacts", `${header} · ${detail}`);
}

function renderTrainingMetricsLine(summary) {
  const combined = featureSummary(summary, "combined") || (summary?.by_feature || [])[0];
  if (!combined) return trainingInfoLine("Metrics", "No metrics JSON has been written for this profile yet.");
  const values = [
    `accuracy ${formatMetricPercent(combined.accuracy_mean)}`,
    `F1 ${formatMetricPercent(combined.macro_f1_mean)}`,
    `precision ${formatMetricPercent(combined.positive_precision_mean)}`,
    `recall ${formatMetricPercent(combined.positive_recall_mean)}`,
    `${combined.trained_rows ?? "-"} rows`,
    `${combined.feature_count ?? "-"} features`
  ].join(" · ");
  return trainingInfoLine("Metrics", `${combined.feature_set} · ${values}`);
}

function renderTrainingDynamicsLine(history) {
  const latest = (history || [])[0];
  const previous = (history || [])[1];
  if (!latest) return trainingInfoLine("Dynamics", "Train a combined model to start the metrics history.");
  const trend = previous
    ? `accuracy ${formatMetricDelta(latest.accuracy_mean, previous.accuracy_mean)}, F1 ${formatMetricDelta(latest.macro_f1_mean, previous.macro_f1_mean)} vs previous run`
    : "first combined metrics snapshot";
  return trainingInfoLine(
    "Dynamics",
    `${trend} · latest ${formatHumanDate(latest.created_at)} · ${latest.trained_rows ?? "-"} rows · ${formatMetricPercent(latest.accuracy_mean)} acc · ${formatMetricPercent(latest.macro_f1_mean)} F1`
  );
}

function trainingInfoLine(label, text) {
  return `<span class="training-info-line"><b>${escapeHtml(label)}</b><span>${escapeHtml(text)}</span></span>`;
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
        <div class="meta track-path">${escapeHtml(track.path)}</div>
        <div class="meta feature-line">${trackStatusLine(track)}</div>
      </div>
      <div class="rhythm-media-block">
        <div class="meta genres-line"><span class="status-item"><b>GENRES</b></span><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>
        <audio controls preload="none" src="/media/${track.id}"></audio>
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
    button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
  });
  row.addEventListener("keydown", event => {
    const keys = { "0": "" };
    activeProfile.labels.forEach((label, index) => {
      if (index < 9) keys[String(index + 1)] = label.key;
    });
    if (keys[event.key] !== undefined) setLabel(track.id, keys[event.key]);
  });
  wireAudioPreview(row.querySelector("audio"));
}

async function toggleLike(track) {
  const response = await fetch(`/api/tracks/${track.id}/liked`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ liked: !track.liked })
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
      artifact_dir: document.getElementById("newProfileArtifactDir").value || null,
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
      artifact_dir: document.getElementById("profileArtifactDirInput").value,
      artifact_prefix: document.getElementById("profileArtifactPrefixInput").value,
      training_min_added: Number(document.getElementById("profileTrainingMinAddedInput").value || 50)
    })
  });
  const profile = await parseJsonResponse(response);
  await loadProfiles();
  await setActiveProfile(profile.classifier_key, { skipLoad: true });
  refreshCandidatesStatusEl.textContent = "profile saved";
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

async function archiveActiveProfile() {
  if (!activeProfile) return;
  if (!window.confirm(`Archive ${activeProfile.name}? Labels and predictions stay in the lab database.`)) return;
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/archive`, { method: "POST" });
  await parseJsonResponse(response);
  activeProfile = null;
  await loadProfiles();
  await loadActive({ reset: true });
}

async function parseRefreshResponse(response) {
  const data = await response.json();
  if (!response.ok) {
    refreshCandidatesStatusEl.textContent = data.detail || response.statusText;
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
  const title = track.title || track.path;
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
    predictionTypeStatus(track),
  ].filter(Boolean).join(" ");
}

function featuresReady(track) {
  return Boolean(track.feature_status.sonara && track.feature_status.mert && track.feature_status.maest);
}

function missingFeatures(track) {
  return ["sonara", "mert", "maest"]
    .filter(key => !track.feature_status[key])
    .map(key => key.toUpperCase());
}

function featuresIndicator(track) {
  const ready = featuresReady(track);
  const label = ready ? "Features ready: SONARA, MERT, MAEST" : `Missing features: ${missingFeatures(track).join(", ")}`;
  return `<span class="features-indicator ${ready ? "ready" : "missing"}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${ready ? "✓" : "!"}</span>`;
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

function predictionTypeStatus(track) {
  return track.predicted_label ? `<span class="status-item"><b>TYPE</b><span class="status-detail">${escapeHtml(track.feature_set)}</span></span>` : "";
}

function featureStatusBadge(name, value) {
  return `<span class="status-item"><b>${name}</b><span class="analysis-status-badge ${value ? "status-yes" : "status-no"}">${mark(value)}</span></span>`;
}

function showError(error) {
  refreshCandidatesStatusEl.textContent = error.message || String(error);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

init().catch(showError);
