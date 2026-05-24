from __future__ import annotations

import logging
from pathlib import Path
import subprocess

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from dj_track_similarity.dependencies import require_ffmpeg

from .lab_db import RHYTHM_LABELS, RhythmLabDatabase


LOGGER = logging.getLogger(__name__)
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}


class LabelRequest(BaseModel):
    label: str | None = None
    note: str | None = None


def create_app(db_path: str | Path) -> FastAPI:
    lab = RhythmLabDatabase(db_path)
    app = FastAPI(title="Rhythm Lab")

    @app.get("/")
    def index():
        return HTMLResponse(_index_html())

    @app.get("/api/summary")
    def summary():
        tracks = lab.library.list_tracks()
        return {
            "tracks": len(tracks),
            "labels": lab.label_counts(),
            "mert": len(lab.embedding_track_ids("mert")),
            "maest": len(lab.embedding_track_ids("maest")),
        }

    @app.get("/api/tracks")
    def tracks(
        q: str = "",
        syncopated: str = Query(default="all", pattern="^(all|yes|no)$"),
        label: str = Query(default="all", pattern="^(all|unlabeled|broken|straight|ambiguous)$"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        labels = lab.labels_by_track()
        mert_ids = lab.embedding_track_ids("mert")
        maest_ids = lab.embedding_track_ids("maest")
        needle = q.strip().casefold()
        rows = []
        for track in lab.library.list_tracks():
            current_label = labels.get(track.id)
            label_text = current_label.label if current_label else None
            if label == "unlabeled" and label_text is not None:
                continue
            if label not in {"all", "unlabeled"} and label_text != label:
                continue
            searchable = " ".join(str(value or "") for value in (track.artist, track.title, track.album, track.path)).casefold()
            if needle and needle not in searchable:
                continue
            metadata = track.metadata or {}
            has_syncopated_rhythm = metadata.get("maest_syncopated_rhythm") is True
            if syncopated == "yes" and not has_syncopated_rhythm:
                continue
            if syncopated == "no" and has_syncopated_rhythm:
                continue
            rows.append(
                {
                    "id": track.id,
                    "path": track.path,
                    "artist": track.artist,
                    "title": track.title,
                    "album": track.album,
                    "bpm": track.bpm,
                    "musical_key": track.musical_key,
                    "genres": track.genres,
                    "genre_scores": track.genre_scores,
                    "label": label_text,
                    "maest_syncopated_rhythm": has_syncopated_rhythm,
                    "feature_status": {
                        "sonara": isinstance(metadata.get("sonara_features"), dict),
                        "mert": track.id in mert_ids,
                        "maest": track.id in maest_ids,
                    },
                }
            )
        page = rows[offset : offset + limit]
        return {"items": page, "total": len(rows), "limit": limit, "offset": offset}

    @app.post("/api/tracks/{track_id}/label")
    def set_label(track_id: int, request: LabelRequest):
        try:
            label = lab.set_label(track_id, request.label, note=request.note)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"track_id": track_id, "label": label.label if label else None}

    @app.get("/media/{track_id}")
    def media(track_id: int):
        try:
            track = lab.library.get_track(track_id)
        except KeyError as error:
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
    button {{ cursor: pointer; }}
    button:hover {{ border-color: #888; }}
    button:disabled {{ cursor: default; opacity: 0.45; }}
    .active {{ outline: 2px solid #e0b84b; }}
    .pager {{ display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }}
    .track {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; padding: 12px 0; border-bottom: 1px solid #2b2b2b; }}
    .meta {{ color: #aaa; font-size: 13px; line-height: 1.35; }}
    .track-number {{ color: #888; font-variant-numeric: tabular-nums; margin-right: 6px; }}
    .feature-line {{ margin-top: 1px; }}
    .genres-line {{ margin: 5px 0 0; }}
    .genres {{ color: #e0b84b; font-size: 13px; font-weight: 700; }}
    .badge-row {{ display: flex; gap: 6px; align-items: center; margin-top: 5px; }}
    .syncopated-badge,
    .rhythm-label-badge {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 12px; line-height: 1.35; font-weight: 700; }}
    .syncopated-badge {{ background: #d7aa32; color: #141414; }}
    .rhythm-label-badge {{ background: #7d5cff; color: #fff; }}
    .badge-separator {{ color: #777; font-size: 12px; }}
    .actions {{ display: flex; gap: 6px; align-items: start; flex-wrap: wrap; justify-content: end; }}
    audio {{ width: min(520px, 100%); margin-top: 8px; }}
  </style>
</head>
<body>
  <header>
    <strong>Rhythm Lab</strong>
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
    const syncopatedEl = document.getElementById("syncopated");
    const labelEl = document.getElementById("label");
    const summaryEl = document.getElementById("summary");
    const pageSizeEl = document.getElementById("pageSize");
    const prevPageEl = document.getElementById("prevPage");
    const nextPageEl = document.getElementById("nextPage");
    const pageInfoEl = document.getElementById("pageInfo");
    let offset = 0;
    let total = 0;
    document.getElementById("load").addEventListener("click", () => loadTracks({{ reset: true }}));
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

    async function loadSummary() {{
      const data = await fetch("/api/summary").then(r => r.json());
      summaryEl.textContent = `${{data.tracks}} tracks | labels ${{formatLabelCounts(data.labels)}} | MERT ${{data.mert}} | MAEST ${{data.maest}}`;
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
          <strong><span class="track-number">#${{track.rowNumber}}</span>${{escapeHtml(track.artist || "")}} - ${{escapeHtml(track.title || track.path)}}</strong>
          <div class="meta track-path">${{escapeHtml(track.path)}}</div>
          <div class="meta feature-line">SONARA ${{mark(track.feature_status.sonara)}} · MERT ${{mark(track.feature_status.mert)}} · MAEST ${{mark(track.feature_status.maest)}} · label <b>${{track.label || "none"}}</b></div>
          <div class="genres-line"><span class="genres">${{(track.genres || []).map(escapeHtml).join(" · ")}}</span></div>
          ${{badgeRow(track)}}
          <audio controls preload="none" src="/media/${{track.id}}"></audio>
        </div>
        <div class="actions">
          <button data-label="broken">Broken</button>
          <button data-label="straight">Straight</button>
          <button data-label="ambiguous">Ambiguous</button>
          <button data-label="">Clear</button>
        </div>`;
      row.querySelectorAll("button").forEach(button => {{
        button.addEventListener("click", () => setLabel(track.id, button.dataset.label));
        if ((button.dataset.label || null) === track.label) button.classList.add("active");
      }});
      row.addEventListener("keydown", event => {{
        const keys = {{ "1": "broken", "2": "straight", "3": "ambiguous", "0": "" }};
        if (keys[event.key] !== undefined) setLabel(track.id, keys[event.key]);
      }});
      return row;
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
    function rhythmLabelBadge(track) {{ return track.label ? `<span class="rhythm-label-badge">${{escapeHtml(track.label)}}</span>` : ""; }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[ch]));
    }}
    loadTracks();
  </script>
</body>
</html>"""
