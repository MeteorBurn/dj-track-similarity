from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from dj_track_similarity.dependencies import require_ffmpeg

from .lab_db import RHYTHM_LABELS, RhythmLabDatabase
from .source_db import SourceDatabase


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


class SourceSwitchRequest(BaseModel):
    path: str


class SourceDatabaseState:
    def __init__(self, source_path: str | Path | None = None) -> None:
        self._lock = threading.RLock()
        self.path: Path | None = None
        self.source: SourceDatabase | None = None
        if source_path is not None and Path(source_path).expanduser().exists():
            self.switch(source_path)

    def current(self) -> dict[str, object]:
        with self._lock:
            return {
                "path": str(self.path) if self.path is not None else None,
                "selected": self.source is not None,
            }

    def switch(self, path: str | Path) -> dict[str, object]:
        selected = SourceDatabase(path)
        with self._lock:
            self.path = selected.path
            self.source = selected
            return self.current()

    def require_source(self) -> SourceDatabase:
        with self._lock:
            if self.source is None:
                raise ValueError("Source database is not selected")
            return self.source


def open_existing_database_file_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("Native database file dialog is unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose existing SQLite database",
            filetypes=[("SQLite database", "*.sqlite"), ("All files", "*.*")],
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


def create_app(source_db_path: str | Path | None = None, *, labels_db_path: str | Path) -> FastAPI:
    labels_db = RhythmLabDatabase(labels_db_path)
    source_state = SourceDatabaseState(source_db_path)
    app = FastAPI(title="Rhythm Lab")

    @app.get("/")
    def index():
        return HTMLResponse(_index_html())

    @app.get("/api/source/current")
    def current_source():
        return source_state.current()

    @app.post("/api/source/switch")
    def switch_source(request: SourceSwitchRequest):
        try:
            return source_state.switch(request.path)
        except (FileNotFoundError, ValueError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/source/dialog")
    def source_dialog():
        try:
            selected = open_existing_database_file_dialog()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if selected is None:
            return source_state.current()
        return {"path": str(selected.resolve(strict=False)), "selected": False}

    @app.get("/api/summary")
    def summary():
        source = source_state.source
        if source is None:
            return {"tracks": 0, "labels": labels_db.label_counts(), "mert": 0, "maest": 0, "source": source_state.current()}
        return {
            "tracks": source.count_tracks(),
            "labels": labels_db.label_counts(),
            "mert": source.count_embeddings("mert"),
            "maest": source.count_embeddings("maest"),
            "source": source_state.current(),
        }

    @app.get("/api/tracks")
    def tracks(
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = Query(default="all", pattern="^(all|unlabeled|broken|straight|ambiguous)$"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        source = source_state.source
        if source is None:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        try:
            return source.list_tracks_page(
                labels_db_path=labels_db.path,
                query=q,
                syncopated=syncopated,
                label=label,
                limit=limit,
                offset=offset,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/tracks/{track_id}/label")
    def set_label(track_id: int, request: LabelRequest):
        try:
            track = source_state.require_source().get_track(track_id)
            label = labels_db.set_label(track, request.label, note=request.note)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"track_id": track_id, "label": label.label if label else None}

    @app.get("/media/{track_id}")
    def media(track_id: int):
        try:
            track = source_state.require_source().get_track(track_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        path = Path(track.path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        if path.suffix.lower() in AIFF_PREVIEW_SUFFIXES:
            try:
                return _transcoded_wav_response(path, require_ffmpeg())
            except RuntimeError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error
        return FileResponse(path)

    return app


def _transcoded_wav_response(path: Path, ffmpeg_path: str) -> StreamingResponse:
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
        "pcm_s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def iter_wav_chunks():
        try:
            if process.stdout is None:
                return
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
            return_code = process.wait()
            if return_code != 0:
                LOGGER.warning("ffmpeg preview transcode failed path=%s return_code=%s", path, return_code)
        finally:
            if process.poll() is None:
                process.kill()

    return StreamingResponse(iter_wav_chunks(), media_type="audio/wav")


def _index_html() -> str:
    labels = ", ".join(RHYTHM_LABELS)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rhythm Lab</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; background: #111; color: #eee; }}
    header, main {{ max-width: 1200px; margin: 0 auto; padding: 16px; }}
    header {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; border-bottom: 1px solid #333; }}
    input, select, button {{ background: #1e1e1e; color: #eee; border: 1px solid #444; border-radius: 6px; padding: 8px; }}
    input.source-path {{ min-width: min(520px, 100%); flex: 1 1 360px; }}
    button {{ cursor: pointer; }}
    button:hover {{ border-color: #888; }}
    button:disabled {{ cursor: default; opacity: 0.45; }}
    .active {{ outline: 2px solid #e0b84b; }}
    .source-row {{ display: flex; gap: 6px; align-items: center; flex: 1 1 100%; }}
    .source-status {{ color: #aaa; font-size: 13px; min-width: 160px; }}
    .source-status.error {{ color: #ff8f8f; }}
    .pager {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
    .track {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; padding: 12px 0; border-bottom: 1px solid #2b2b2b; }}
    .track-main {{ display: flex; flex-direction: column; gap: 3px; }}
    .meta {{ color: #aaa; font-size: 13px; line-height: 1.42; }}
    .track-number {{ color: #888; font-variant-numeric: tabular-nums; margin-right: 6px; }}
    .feature-line {{ margin-top: 1px; }}
    .genres-line {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 5px 0 0; }}
    .rhythm-media-block {{ margin-top: 7px; }}
    .genres {{ color: #e0b84b; font-size: 13px; font-weight: 700; }}
    .badge-row {{ display: inline-flex; gap: 6px; align-items: center; }}
    .syncopated-badge,
    .rhythm-label-badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 12px; line-height: 1.35; font-weight: 700; }}
    .syncopated-badge {{ background: #d7aa32; color: #141414; }}
    .rhythm-label-badge {{ background: #7d5cff; color: #fff; }}
    .rhythm-label-badge.broken {{ background: #dc2626; color: #fff; }}
    .rhythm-label-badge.straight {{ background: #2563eb; color: #fff; }}
    .rhythm-label-badge.ambiguous {{ background: #7d5cff; color: #fff; }}
    .badge-separator {{ color: #777; font-size: 12px; }}
    .actions {{ display: flex; gap: 6px; align-items: start; flex-wrap: wrap; justify-content: end; }}
    audio {{ width: min(520px, 100%); height: 34px; margin-top: 6px; }}
  </style>
</head>
<body>
  <header>
    <strong>Rhythm Lab</strong>
    <div class="source-row">
      <input id="sourcePath" class="source-path" placeholder="C:\\db\\abstracted.sqlite" title="Existing dj-track-similarity SQLite database. Opened read-only." />
      <button id="chooseSource" title="Choose existing SQLite database">Browse</button>
      <button id="loadSource" title="Load selected source database">Load database</button>
      <span id="sourceStatus" class="source-status"></span>
    </div>
    <input id="query" placeholder="search path/title/artist" />
    <select id="syncopated">
      <option value="all">all rhythm</option>
      <option value="yes">syncopated rhythm</option>
      <option value="no">no syncopated rhythm</option>
    </select>
    <select id="label">
      <option value="all">all</option>
      <option value="unlabeled">unlabeled</option>
      <option value="broken">broken</option>
      <option value="straight">straight</option>
      <option value="ambiguous">ambiguous</option>
    </select>
    <button id="load">Load</button>
    <div class="pager">
      <button id="prevPage">Prev</button>
      <select id="pageSize">
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="200">200</option>
        <option value="500">500</option>
      </select>
      <button id="nextPage">Next</button>
      <span id="pageInfo" class="meta"></span>
    </div>
    <span id="summary"></span>
  </header>
  <main>
    <p class="meta">Labels: {labels}. Keyboard on focused row: 1 broken, 2 straight, 3 ambiguous, 0 clear.</p>
    <div id="tracks"></div>
  </main>
  <script>
    const tracksEl = document.getElementById("tracks");
    const queryEl = document.getElementById("query");
    const sourcePathEl = document.getElementById("sourcePath");
    const sourceStatusEl = document.getElementById("sourceStatus");
    const syncopatedEl = document.getElementById("syncopated");
    const labelEl = document.getElementById("label");
    const summaryEl = document.getElementById("summary");
    const pageSizeEl = document.getElementById("pageSize");
    const prevPageEl = document.getElementById("prevPage");
    const nextPageEl = document.getElementById("nextPage");
    const pageInfoEl = document.getElementById("pageInfo");
    let offset = 0;
    let total = 0;
    let activeAudio = null;
    document.getElementById("load").addEventListener("click", () => loadTracks({{ reset: true }}));
    document.getElementById("chooseSource").addEventListener("click", () => chooseSource().catch(console.error));
    document.getElementById("loadSource").addEventListener("click", () => switchSource(sourcePathEl.value).catch(console.error));
    sourcePathEl.addEventListener("keydown", event => {{ if (event.key === "Enter") switchSource(sourcePathEl.value).catch(console.error); }});
    queryEl.addEventListener("keydown", event => {{ if (event.key === "Enter") loadTracks({{ reset: true }}); }});
    syncopatedEl.addEventListener("change", () => loadTracks({{ reset: true }}));
    labelEl.addEventListener("change", () => loadTracks({{ reset: true }}));
    pageSizeEl.addEventListener("change", () => loadTracks({{ reset: true }}));
    prevPageEl.addEventListener("click", () => {{
      offset = Math.max(0, offset - pageLimit());
      loadTracks();
    }});
    nextPageEl.addEventListener("click", () => {{
      offset = Math.min(Math.max(0, total - 1), offset + pageLimit());
      loadTracks();
    }});

    async function loadSourceState() {{
      const data = await fetch("/api/source/current").then(r => r.json());
      applySourceState(data);
    }}

    async function chooseSource() {{
      clearSourceError();
      sourceStatusEl.textContent = "opening picker...";
      const response = await fetch("/api/source/dialog", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, body: JSON.stringify({{}}) }});
      const data = await parseJsonResponse(response);
      sourcePathEl.value = data.path || sourcePathEl.value || "";
      sourceStatusEl.textContent = data.path ? "path selected" : "no source database";
      sourceStatusEl.classList.remove("error");
    }}

    async function switchSource(path) {{
      clearSourceError();
      sourceStatusEl.textContent = "loading...";
      const response = await fetch("/api/source/switch", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ path }})
      }});
      const data = await parseJsonResponse(response);
      applySourceState(data);
      await loadTracks({{ reset: true }});
    }}

    function applySourceState(data) {{
      sourcePathEl.value = data.path || sourcePathEl.value || "";
      sourceStatusEl.textContent = data.selected ? "loaded read-only" : "no source database";
      sourceStatusEl.classList.remove("error");
    }}

    function clearSourceError() {{
      sourceStatusEl.classList.remove("error");
    }}

    async function parseJsonResponse(response) {{
      const data = await response.json();
      if (!response.ok) {{
        sourceStatusEl.textContent = data.detail || response.statusText;
        sourceStatusEl.classList.add("error");
        throw new Error(data.detail || response.statusText);
      }}
      return data;
    }}

    async function loadSummary() {{
      const data = await fetch("/api/summary").then(r => r.json());
      summaryEl.textContent = `${{data.tracks}} tracks | MAEST ${{data.maest}} | MERT ${{data.mert}} – Labels: ${{formatLabelCounts(data.labels)}}`;
    }}

    function formatLabelCounts(labels) {{
      const counts = labels || {{}};
      return [
        `broken ${{counts.broken || 0}}`,
        `straight ${{counts.straight || 0}}`,
        `ambiguous ${{counts.ambiguous || 0}}`
      ].join(" · ");
    }}

    async function loadTracks(options = {{}}) {{
      if (options.reset) offset = 0;
      const limit = pageLimit();
      const params = new URLSearchParams({{
        q: queryEl.value,
        syncopated: syncopatedEl.value,
        label: labelEl.value,
        limit: String(limit),
        offset: String(offset)
      }});
      const data = await fetch(`/api/tracks?${{params}}`).then(r => r.json());
      total = data.total;
      offset = data.offset;
      tracksEl.innerHTML = "";
      data.items.forEach((track, index) => {{
        track.rowNumber = data.offset + index + 1;
        tracksEl.appendChild(renderTrack(track));
      }});
      updatePager(data);
      await loadSummary();
    }}

    function pageLimit() {{
      return Number(pageSizeEl.value || 100);
    }}

    function updatePager(data) {{
      const shown = data.items.length;
      const first = shown ? data.offset + 1 : 0;
      const last = shown ? data.offset + shown : 0;
      pageInfoEl.textContent = `${{first}}-${{last}} / ${{data.total}}`;
      prevPageEl.disabled = data.offset <= 0;
      nextPageEl.disabled = data.offset + data.limit >= data.total;
    }}

    function renderTrack(track) {{
      const row = document.createElement("section");
      row.className = "track";
      row.tabIndex = 0;
      row.innerHTML = `
        <div>
          <div class="track-main">
            <strong><span class="track-number">#${{track.rowNumber}}</span>${{escapeHtml(displayTrackTitle(track))}}</strong>
          <div class="meta track-path">${{escapeHtml(track.path)}}</div>
          <div class="meta feature-line">SONARA ${{mark(track.feature_status.sonara)}} · MERT ${{mark(track.feature_status.mert)}} · MAEST ${{mark(track.feature_status.maest)}} · label <b>${{track.label || "none"}}</b></div>
          </div>
          <div class="rhythm-media-block">
            <div class="genres-line"><span class="genres">${{(track.genres || []).map(escapeHtml).join(" · ")}}</span>${{badgeRow(track)}}</div>
            <audio controls preload="none" src="/media/${{track.id}}"></audio>
          </div>
        </div>
        <div class="actions">
          <button data-label="broken">Broken</button>
          <button data-label="straight">Straight</button>
          <button data-label="ambiguous">Ambiguous</button>
          <button data-label="">Clear</button>
        </div>`;
      row.querySelectorAll("button").forEach(button => {{
        button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
        if ((button.dataset.label || null) === track.label) {{
          button.classList.add("active");
        }}
      }});
      row.addEventListener("keydown", event => {{
        const keys = {{ "1": "broken", "2": "straight", "3": "ambiguous", "0": "" }};
        if (keys[event.key] !== undefined) setLabel(track.id, keys[event.key]);
      }});
      wireAudioPreview(row.querySelector("audio"));
      return row;
    }}

    function wireAudioPreview(audio) {{
      if (!audio) return;
      audio.addEventListener("play", () => {{
        if (activeAudio && activeAudio !== audio) {{
          activeAudio.pause();
          activeAudio.currentTime = 0;
        }}
        activeAudio = audio;
      }});
      audio.addEventListener("ended", () => {{
        if (activeAudio === audio) activeAudio = null;
      }});
      audio.addEventListener("pause", () => {{
        if (activeAudio === audio && audio.currentTime === 0) activeAudio = null;
      }});
    }}

    async function setLabel(trackId, label) {{
      await fetch(`/api/tracks/${{trackId}}/label`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ label }})
      }});
      await loadTracks();
    }}

    function mark(value) {{ return value ? "yes" : "no"; }}
    function badgeRow(track) {{
      const badges = [syncopatedBadge(track), rhythmLabelBadge(track)].filter(Boolean);
      return badges.length ? `<div class="badge-row">${{badges.join('<span class="badge-separator">·</span>')}}</div>` : "";
    }}
    function syncopatedBadge(track) {{ return track.maest_syncopated_rhythm === true ? '<span class="syncopated-badge">syncopated rhythm</span>' : ""; }}
    function rhythmLabelBadge(track) {{ return track.label ? `<span class="rhythm-label-badge ${{escapeHtml(track.label)}} label-${{escapeHtml(track.label)}}">${{escapeHtml(track.label)}}</span>` : ""; }}
    function displayTrackTitle(track) {{
      const title = track.title || track.path;
      return track.artist ? `${{track.artist}} - ${{title}}` : title;
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}
    loadSourceState().then(() => loadTracks());
  </script>
</body>
</html>"""
