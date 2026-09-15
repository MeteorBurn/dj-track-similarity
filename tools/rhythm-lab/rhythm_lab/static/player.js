/* One transport survives every workspace render. A queue retains the request
 * that produced the selected row, including its library, recipe and ordering. */
function createRhythmPlayer({ onChange }) {
  const audio = document.getElementById("playerAudio");
  const title = document.getElementById("playerTitle");
  const artist = document.getElementById("playerArtist");
  const previous = document.getElementById("playerPrevious");
  const toggle = document.getElementById("playerToggle");
  const next = document.getElementById("playerNext");
  const seek = document.getElementById("playerSeek");
  const currentTime = document.getElementById("playerCurrentTime");
  const duration = document.getElementById("playerDuration");
  const volume = document.getElementById("playerVolume");
  const error = document.getElementById("playerError");
  let track = null;
  let queue = null;
  let position = 0;
  let generation = 0;
  let pending = false;
  let request = null;
  let lastRowState = null;

  function identity(item) {
    return item ? `${item.catalog_uuid}:${item.track_id}:${item.track_uuid}` : "";
  }

  function time(value) {
    const seconds = Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function update(forceRows = false) {
    const length = Number.isFinite(audio.duration) ? audio.duration : 0;
    title.textContent = track ? track.title || String(track.file_path || "").split(/[\\/]/).pop() || "Untitled track" : "No track playing";
    artist.textContent = track ? track.artist || "Unknown Artist" : "Select a track from the library";
    toggle.disabled = !track || pending;
    toggle.dataset.playing = String(Boolean(track && !audio.paused));
    toggle.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
    toggle.title = audio.paused ? "Play" : "Pause";
    toggle.innerHTML = audio.paused
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m8 5 11 7-11 7z"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';
    previous.disabled = !queue || position <= 0 || pending;
    next.disabled = !queue || position >= queue.total - 1 || pending;
    seek.disabled = !track || length <= 0;
    seek.max = String(length || 1);
    seek.value = String(Math.min(length, audio.currentTime || 0));
    seek.style.setProperty("--range-progress", `${length ? (audio.currentTime / length) * 100 : 0}%`);
    currentTime.textContent = time(audio.currentTime);
    duration.textContent = time(length);
    volume.style.setProperty("--range-progress", `${audio.volume * 100}%`);
    const rowState = `${identity(track)}:${!audio.paused}`;
    if (rowState !== lastRowState || forceRows === true) {
      lastRowState = rowState;
      onChange?.({ track, playing: Boolean(track && !audio.paused) });
    }
  }

  function fail(reason) {
    error.textContent = reason?.message || String(reason);
    error.hidden = false;
    update();
  }

  async function play() {
    const token = generation;
    try {
      if (audio.ended) audio.currentTime = 0;
      await audio.play();
    } catch (reason) {
      if (token === generation && reason.name !== "AbortError") fail(reason);
    }
  }

  async function select(item, context, index) {
    generation += 1;
    request?.abort();
    request = null;
    pending = false;
    const sameTrack = identity(track) === identity(item);
    queue = { ...context, items: [...context.items] };
    position = index;
    track = item;
    error.hidden = true;
    error.textContent = "";
    if (sameTrack) {
      if (audio.paused) await play();
      else audio.pause();
    } else {
      audio.pause();
      audio.src = `/media/${encodeURIComponent(item.track_id)}`;
      audio.load();
      await play();
    }
    update();
  }

  async function move(delta) {
    if (!queue || pending) return;
    const target = position + delta;
    if (target < 0 || target >= queue.total) return;
    const token = ++generation;
    pending = true;
    update();
    try {
      let context = queue;
      let item = context.items[target - context.offset];
      if (!item) {
        request = new AbortController();
        const params = new URLSearchParams(context.params);
        params.set("offset", String(Math.floor(target / context.limit) * context.limit));
        const response = await fetch(`${context.endpoint}?${params}`, { signal: request.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || response.statusText);
        if (token !== generation) return;
        context = { ...context, items: data.items, offset: data.offset, total: data.total };
        item = context.items[target - context.offset];
      }
      if (token !== generation) return;
      if (!item) {
        queue = context;
        throw new Error("This track is no longer in the playback list. Select a track to refresh the sequence.");
      }
      await select(item, context, target);
    } catch (reason) {
      if (token === generation && reason.name !== "AbortError") fail(reason);
    } finally {
      if (token === generation) pending = false;
      update();
    }
  }

  function reset() {
    generation += 1;
    request?.abort();
    request = null;
    track = null;
    queue = null;
    pending = false;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    error.hidden = true;
    update();
  }

  toggle.addEventListener("click", () => audio.paused ? play() : audio.pause());
  previous.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));
  seek.addEventListener("input", () => {
    if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration, Math.max(0, Number(seek.value)));
    update();
  });
  volume.addEventListener("input", () => { audio.volume = Math.max(0, Math.min(1, Number(volume.value))); });
  ["play", "pause", "ended", "timeupdate", "durationchange", "loadedmetadata", "volumechange"].forEach(event => audio.addEventListener(event, update));
  audio.addEventListener("error", () => { if (track) fail("Audio preview could not load. Check that the track is available in this library."); });
  audio.volume = Math.max(0, Math.min(1, Number(volume.value || 0.7)));
  update();
  return { select, reset, update: () => update(true), identity, current: () => track };
}
