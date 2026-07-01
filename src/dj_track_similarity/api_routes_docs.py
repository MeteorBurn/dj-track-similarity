from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


def register_docs_routes(app: FastAPI, package_path: Path) -> None:
    docs_candidates = [
        package_path.parents[2] / "docs" / "dj-track-similarity" / "site",
        package_path.parent.parent / "docs" / "dj-track-similarity" / "site",
    ]
    docs_dir = next((candidate for candidate in docs_candidates if candidate.exists()), None)
    if docs_dir is not None:
        app.mount("/docs", StaticFiles(directory=docs_dir, html=True), name="docs")
        return

    @app.get("/docs", include_in_schema=False)
    @app.get("/docs/{path:path}", include_in_schema=False)
    async def docs_not_built(path: str = ""):
        return HTMLResponse(
            """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Documentation is not built</title>
  </head>
  <body>
    <main>
      <h1>Documentation is not built</h1>
      <p>Run <code>npm run build</code> from <code>docs/dj-track-similarity</code>, then reload this page.</p>
    </main>
  </body>
</html>
""".strip(),
            status_code=503,
        )
