/* One transport survives every workspace render. A queue retains the request
 * that produced the selected row, including its library, recipe and ordering. */
function createRhythmPlayer({ onChange }) {
  let audio = document.getElementById("playerAudio");
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
  let selection = null;
  let stream = null;

  function identity(item) {
    return item ? `${item.catalog_uuid}:${item.track_id}:${item.track_uuid}` : "";
  }

  function time(value) {
    const seconds = Number.isFinite(value) && value > 0 ? Math.floor(value) : 0;
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  function update(forceRows = false) {
    const length = selection?.duration || 0;
    const elapsed = stream ? stream.start + stream.elapsed : 0;
    const playing = Boolean(track && stream?.playing);
    title.textContent = track ? track.title || String(track.file_path || "").split(/[\\/]/).pop() || "Untitled track" : "No track playing";
    artist.textContent = track ? track.artist || "Unknown Artist" : "Select a track from the library";
    toggle.disabled = !track || pending;
    toggle.dataset.playing = String(playing);
    toggle.setAttribute("aria-label", playing ? "Pause" : "Play");
    toggle.title = playing ? "Pause" : "Play";
    toggle.innerHTML = !playing
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="m8 5 11 7-11 7z"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6 5h4v14H6zm8 0h4v14h-4z"/></svg>';
    previous.disabled = !queue || position <= 0 || pending;
    next.disabled = !queue || position >= queue.total - 1 || pending;
    seek.disabled = !track || length <= 0;
    seek.max = String(length || 1);
    seek.value = String(Math.min(length, elapsed));
    seek.style.setProperty("--range-progress", `${length ? (Math.min(length, elapsed) / length) * 100 : 0}%`);
    currentTime.textContent = time(length ? Math.min(length, elapsed) : elapsed);
    duration.textContent = time(length);
    volume.style.setProperty("--range-progress", `${audio.volume * 100}%`);
    const rowState = `${identity(track)}:${playing}`;
    if (rowState !== lastRowState || forceRows === true) {
      lastRowState = rowState;
      onChange?.({ track, playing });
    }
  }

  function fail(reason) {
    error.textContent = reason?.message || String(reason);
    error.hidden = false;
    update();
  }

  function release(source) {
    source.pause();
    source.removeAttribute("src");
    source.load();
  }

  function updatePosition(value) {
    if (stream !== value || value.failed) return;
    value.elapsed = Number.isFinite(value.audio.currentTime) ? Math.max(0, value.audio.currentTime) : 0;
    update();
  }

  function failPlayback(value, reason) {
    if (stream !== value || value.failed) return;
    updatePosition(value);
    value.failed = true;
    value.playing = false;
    release(value.audio);
    fail(selection?.metadataError || reason);
  }

  async function play(value = stream) {
    if (!value || stream !== value || !value.playing) return;
    try {
      await value.audio.play();
    } catch (reason) {
      if (stream === value && value.playing && reason.name !== "AbortError") failPlayback(value, reason);
    }
  }

  function startStream(start, playing) {
    const previousAudio = audio;
    // A fresh element isolates queued media events from the previous stream.
    audio = previousAudio.cloneNode(false);
    audio.removeAttribute("src");
    audio.volume = previousAudio.volume;
    const value = { audio, start, elapsed: 0, playing, ended: false, failed: false };
    stream = value;
    release(previousAudio);
    previousAudio.replaceWith(audio);
    if (selection.duration > 0 && start >= selection.duration) {
      value.ended = true;
      value.playing = false;
      update();
      return;
    }
    audio.addEventListener("timeupdate", () => updatePosition(value));
    audio.addEventListener("play", () => {
      if (stream !== value || !value.playing) value.audio.pause();
      else update();
    });
    audio.addEventListener("pause", () => {
      if (stream !== value || !value.audio.paused || value.audio.ended || value.failed) return;
      value.playing = false;
      updatePosition(value);
    });
    audio.addEventListener("ended", () => {
      if (stream !== value || value.failed) return;
      value.ended = true;
      value.playing = false;
      updatePosition(value);
    });
    audio.addEventListener("error", () => failPlayback(value, "Audio preview could not load. Check that the track is available in this library."));
    audio.addEventListener("volumechange", () => { if (stream === value) update(); });
    audio.src = `/media/${encodeURIComponent(track.track_id)}?start=${start}`;
    audio.load();
    void play(value);
    update();
  }

  function togglePlayback() {
    if (!stream) return;
    error.hidden = true;
    if (stream.playing) {
      stream.playing = false;
      audio.pause();
    } else if (stream.ended || stream.failed) {
      startStream(stream.ended ? 0 : stream.start + stream.elapsed, true);
    } else {
      stream.playing = true;
      void play();
    }
    update();
  }

  async function loadDuration(item, selected) {
    try {
      const response = await fetch(`/api/tracks/${encodeURIComponent(item.track_id)}/preview-info`, { signal: selected.controller.signal });
      const data = await response.json();
      if (selection !== selected) return;
      if (!response.ok) throw new Error(data.detail || response.statusText);
      selected.duration = Number.isFinite(data.duration_seconds) ? Math.max(0, data.duration_seconds) : 0;
      update();
    } catch (reason) {
      if (selection !== selected || reason.name === "AbortError") return;
      selected.metadataError = reason.message || String(reason);
      fail(stream?.failed ? selected.metadataError : `Could not determine track duration: ${selected.metadataError}`);
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
      togglePlayback();
    } else {
      selection?.controller.abort();
      selection = { duration: 0, metadataError: null, controller: new AbortController() };
      startStream(0, true);
      void loadDuration(item, selection);
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
    selection?.controller.abort();
    selection = null;
    stream = null;
    track = null;
    queue = null;
    pending = false;
    release(audio);
    error.hidden = true;
    update();
  }

  toggle.addEventListener("click", togglePlayback);
  previous.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));
  seek.addEventListener("input", () => {
    const seconds = Number(seek.value);
    if (stream && selection.duration > 0 && Number.isFinite(seconds)) {
      startStream(Math.min(selection.duration, Math.max(0, seconds)), stream.playing);
    }
  });
  volume.addEventListener("input", () => { audio.volume = Math.max(0, Math.min(1, Number(volume.value))); update(); });
  audio.volume = Math.max(0, Math.min(1, Number(volume.value || 0.7)));
  update();
  return { select, reset, update: () => update(true), identity, current: () => track };
}
