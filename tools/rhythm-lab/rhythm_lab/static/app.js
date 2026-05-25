const tracksEl = document.getElementById("tracks");
const queryEl = document.getElementById("query");
const sourcePathEl = document.getElementById("sourcePath");
const sourceStatusEl = document.getElementById("sourceStatus");
const profileSelectEl = document.getElementById("profileSelect");
const activeProfileNameEl = document.getElementById("activeProfileName");
const libraryTabEl = document.getElementById("libraryTab");
const candidatesTabEl = document.getElementById("candidatesTab");
const likedTabEl = document.getElementById("likedTab");
const trainingTabEl = document.getElementById("trainingTab");
const settingsTabEl = document.getElementById("settingsTab");
const commonFiltersEl = document.getElementById("commonFilters");
const candidateFiltersEl = document.getElementById("candidateFilters");
const syncopatedEl = document.getElementById("syncopated");
const labelEl = document.getElementById("label");
const candidatePredictedEl = document.getElementById("candidatePredicted");
const candidateMinBrokenEl = document.getElementById("candidateMinBroken");
const candidateMinPositiveEl = document.getElementById("candidateMinPositive");
const refreshCandidatesEl = document.getElementById("refreshCandidates");
const trainRefreshEl = document.getElementById("trainRefresh");
const archiveProfileEl = document.getElementById("archiveProfile");
const refreshCandidatesStatusEl = document.getElementById("refreshCandidatesStatus");
const summaryEl = document.getElementById("summary");
const pageSizeEl = document.getElementById("pageSize");
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
const viewOffsets = { library: 0, candidates: 0, liked: 0, training: 0, settings: 0 };
let loadSequence = 0;

document.getElementById("load").addEventListener("click", () => loadActive({ reset: true }));
document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(showError));
document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(showError));
document.getElementById("newProfile").addEventListener("click", () => profileDialogEl.showModal());
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
trainingTabEl.addEventListener("click", () => switchView("training"));
settingsTabEl.addEventListener("click", () => switchView("settings"));
sourcePathEl.addEventListener("keydown", event => { if (event.key === "Enter") switchSource(sourcePathEl.value).catch(showError); });
queryEl.addEventListener("keydown", event => { if (event.key === "Enter") loadActive({ reset: true }); });
syncopatedEl.addEventListener("change", () => loadActive({ reset: true }));
labelEl.addEventListener("change", () => loadActive({ reset: true }));
candidatePredictedEl.addEventListener("change", () => loadActive({ reset: true }));
candidateMinBrokenEl.addEventListener("change", () => loadActive({ reset: true }));
candidateMinPositiveEl.addEventListener("change", () => loadActive({ reset: true }));
refreshCandidatesEl.addEventListener("click", () => refreshCandidates().catch(showError));
trainRefreshEl.addEventListener("click", () => trainRefresh().catch(showError));
pageSizeEl.addEventListener("change", () => loadActive({ reset: true }));
prevPageEl.addEventListener("click", () => {
  offset = Math.max(0, offset - pageLimit());
  loadActive();
});
nextPageEl.addEventListener("click", () => {
  offset = Math.min(Math.max(0, total - 1), offset + pageLimit());
  loadActive();
});

async function init() {
  updateNewProfileTypeControls();
  await loadProfiles();
  await loadSourceState();
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
  renderProfileControls();
  offset = 0;
  viewOffsets.library = 0;
  viewOffsets.candidates = 0;
  viewOffsets.liked = 0;
  if (!options.skipLoad) await loadActive({ reset: true });
}

function clearActiveProfile() {
  activeProfile = null;
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
  refreshCandidatesEl.disabled = true;
  trainRefreshEl.disabled = true;
}

function renderProfileControls() {
  archiveProfileEl.disabled = false;
  refreshCandidatesEl.disabled = false;
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
}

function addOption(select, value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  select.appendChild(option);
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
  clearSourceError();
  sourceStatusEl.textContent = "opening picker...";
  const response = await fetch("/api/source/dialog", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  const data = await parseJsonResponse(response);
  sourcePathEl.value = data.path || sourcePathEl.value || "";
  sourceStatusEl.textContent = data.path ? "path selected" : "no source database";
}

async function switchSource(path) {
  clearSourceError();
  sourceStatusEl.textContent = "loading...";
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
  sourceStatusEl.textContent = data.selected ? "loaded read-only" : "no source database";
  sourceStatusEl.classList.remove("error");
}

function clearSourceError() {
  sourceStatusEl.classList.remove("error");
}

async function switchView(view) {
  viewOffsets[activeView] = offset;
  activeView = view;
  offset = viewOffsets[view] || 0;
  libraryTabEl.classList.toggle("active", view === "library");
  candidatesTabEl.classList.toggle("active", view === "candidates");
  likedTabEl.classList.toggle("active", view === "liked");
  trainingTabEl.classList.toggle("active", view === "training");
  settingsTabEl.classList.toggle("active", view === "settings");
  commonFiltersEl.hidden = view === "training" || view === "settings";
  candidateFiltersEl.hidden = view === "training" || view === "settings";
  candidateFiltersEl.classList.toggle("candidate-filters-placeholder", view !== "candidates");
  trainingPanelEl.hidden = view !== "training";
  settingsPanelEl.hidden = view !== "settings";
  tracksEl.hidden = view === "training" || view === "settings";
  await loadActive();
}

async function loadActive(options = {}) {
  if (!activeProfile) return;
  if (activeView === "candidates") return loadCandidates(options);
  if (activeView === "liked") return loadLikedTracks(options);
  if (activeView === "training") return loadTrainingView();
  if (activeView === "settings") return loadSettingsView();
  return loadTracks(options);
}

async function loadSummary(sequence = loadSequence) {
  const data = await fetch(`/api/profiles/${activeProfile.classifier_key}/summary`).then(parseJsonResponse);
  if (sequence !== loadSequence) return;
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
    coverageBadge("Liked", data.likes || 0, "liked")
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
  const trainingCountText = trainingLabels().map(label => `${escapeHtml(label.name)} ${counts[label.key] || 0}`).join(" · ");
  guidancePanelEl.innerHTML = `
    <div class="guidance-card"><b>${escapeHtml(activeProfile.name)}</b><span class="meta">${escapeHtml(activeProfile.description || "Profile ready for labeling.")}</span></div>
    <div class="guidance-card"><b>Training labels</b><span class="meta">${trainingCountText}</span></div>
    <div class="guidance-card"><b>Feature coverage</b><span class="meta">SONARA ${summary.sonara || 0} · MAEST ${summary.maest || 0} · MERT ${summary.mert || 0}</span></div>
    <div class="guidance-card"><b>Next step</b><span class="meta">${nextStepText(counts)}</span></div>`;
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

async function loadTracks(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.library = offset;
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    syncopated: syncopatedEl.value,
    label: labelEl.value,
    liked: "all",
    limit: String(limit),
    offset: String(offset)
  });
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
    syncopated: syncopatedEl.value,
    label: labelEl.value,
    liked: "yes",
    limit: String(limit),
    offset: String(offset)
  });
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

async function loadCandidates(options = {}) {
  const sequence = ++loadSequence;
  if (options.reset) offset = 0;
  viewOffsets.candidates = offset;
  const limit = pageLimit();
  const params = new URLSearchParams({
    q: queryEl.value,
    syncopated: syncopatedEl.value,
    label: labelEl.value,
    predicted: candidatePredictedEl.value,
    probability_focus: candidateMinBrokenEl.value,
    min_positive: candidateMinPositiveEl.value || "0",
    liked: "all",
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

async function refreshCandidates() {
  refreshCandidatesEl.disabled = true;
  refreshCandidatesStatusEl.textContent = "refreshing...";
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/predictions/refresh`, { method: "POST" });
    const data = await parseRefreshResponse(response);
    refreshCandidatesStatusEl.textContent = `updated ${data.predicted} · skipped ${data.skipped} · removed old ${data.deleted_old_predictions}`;
    await switchView("candidates");
    await loadCandidates({ reset: true });
  } finally {
    refreshCandidatesEl.disabled = false;
  }
}

async function trainRefresh() {
  if (trainRefreshEl.disabled) return;
  if (!window.confirm(`Train a new ${activeProfile.name} model, then refresh candidates?`)) return;
  trainRefreshEl.disabled = true;
  refreshCandidatesEl.disabled = true;
  refreshCandidatesStatusEl.textContent = "training...";
  try {
    const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/train-refresh`, { method: "POST" });
    const data = await parseRefreshResponse(response);
    refreshCandidatesStatusEl.textContent = `trained ${formatLabelCounts(data.training_counts)} · updated ${data.predicted} · skipped ${data.skipped}`;
    await switchView("candidates");
    await loadCandidates({ reset: true });
  } finally {
    refreshCandidatesEl.disabled = false;
    await loadTrainingReadiness();
  }
}

async function loadTrainingReadiness() {
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/training/readiness`);
  const data = await response.json();
  if (!response.ok) {
    trainRefreshEl.disabled = true;
    return;
  }
  trainRefreshEl.disabled = !data.ready;
  trainRefreshEl.title = data.ready
    ? "Train a new model, then refresh candidates"
    : `Need balanced new labels. Added: ${formatLabelCounts(data.added)}.`;
  return data;
}

async function loadTrainingView() {
  const data = await loadTrainingReadiness();
  await loadSummary();
  const planText = isMulticlassProfile()
    ? `Guided Logistic Regression across ${trainingLabels().map(label => escapeHtml(label.name)).join(", ")}. Each track contributes at most one class label.`
    : `Guided Logistic Regression on ${escapeHtml(labelByKey(activeProfile.positive_label).name)} vs ${escapeHtml(labelByKey(activeProfile.negative_label).name)}. Review-only labels stay out of fitting.`;
  trainingPanelEl.innerHTML = `
    <div class="guidance-card"><b>Readiness</b><span class="meta">${data?.ready ? "Ready to train" : "Not ready yet"}</span></div>
    <div class="guidance-card"><b>Current labels</b><span class="meta">${formatLabelCounts(data?.current || {})}</span></div>
    <div class="guidance-card"><b>New since last train</b><span class="meta">${formatLabelCounts(data?.added || {})}</span></div>
    <div class="guidance-card"><b>Required new labels</b><span class="meta">${formatLabelCounts(data?.required_added || {})}</span></div>
    <div class="guidance-card"><b>Training plan</b><span class="meta">${planText}</span></div>`;
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
        <strong class="track-heading"><span class="track-title-main"><span class="track-number">#${track.rowNumber}</span>${escapeHtml(displayTrackTitle(track))}</span>${likedIndicator(track)}${featuresIndicator(track)}</strong>
        <div class="meta track-path">${escapeHtml(track.path)}</div>
        <div class="meta feature-line">${trackStatusLine(track)}</div>
      </div>
      <div class="rhythm-media-block">
        <div class="meta genres-line"><span class="status-item"><b>GENRES</b></span><span class="genres">${(track.genres || []).map(escapeHtml).join(" · ")}</span>${badgeRow(track)}</div>
        <audio controls preload="none" src="/media/${track.id}"></audio>
      </div>
    </div>
    <div class="actions ${isMulticlassProfile() ? "multiclass-actions" : ""}">${renderLikeButton(track)}${renderLabelButtons(track)}</div>`;
}

function likedIndicator(track) {
  return track.liked ? '<span class="liked-indicator" title="Liked" aria-label="Liked">★</span>' : "";
}

function renderLikeButton(track) {
  const active = track.liked ? " active" : "";
  const title = track.liked ? "Remove from liked tracks" : "Add to liked tracks";
  return `<button type="button" class="like-button${active}" data-like="true" title="${title}" aria-label="${title}">★</button>`;
}

function renderLabelButtons(track) {
  const buttons = activeProfile.labels.map(label => {
    const active = track.label === label.key ? " active" : "";
    return `<button type="button" class="${active}" data-label="${escapeHtml(label.key)}">${escapeHtml(label.name)}</button>`;
  });
  buttons.push('<button type="button" data-label="">Clear</button>');
  return buttons.join("");
}

function wireTrackRow(row, track) {
  row.querySelectorAll("button").forEach(button => {
    if (button.dataset.like) {
      button.addEventListener("click", () => toggleLike(track.id, !track.liked));
    } else {
      button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
    }
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

async function toggleLike(trackId, liked) {
  const response = await fetch(`/api/profiles/${activeProfile.classifier_key}/tracks/${trackId}/like`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ liked })
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

function updatePager(data) {
  const shown = data.items.length;
  const first = shown ? data.offset + 1 : 0;
  const last = shown ? data.offset + shown : 0;
  pageInfoEl.textContent = `${first}-${last} / ${data.total}`;
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
