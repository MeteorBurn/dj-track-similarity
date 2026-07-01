from __future__ import annotations

import importlib
from pathlib import Path


ROUTE_MODULES = {
    "dj_track_similarity.api_routes_analysis": "register_analysis_routes",
    "dj_track_similarity.api_routes_database": "register_database_routes",
    "dj_track_similarity.api_routes_audio_dedup": "register_audio_dedup_routes",
    "dj_track_similarity.api_routes_audio_doctor": "register_audio_doctor_routes",
    "dj_track_similarity.api_routes_docs": "register_docs_routes",
    "dj_track_similarity.api_routes_evaluation": "register_evaluation_routes",
    "dj_track_similarity.api_routes_library": "register_library_routes",
    "dj_track_similarity.api_routes_rhythm_lab": "register_rhythm_lab_routes",
    "dj_track_similarity.api_routes_search": "register_search_routes",
    "dj_track_similarity.api_routes_server": "register_server_routes",
    "dj_track_similarity.api_routes_tags_export": "register_tags_export_routes",
}


def test_api_routes_are_split_into_registration_modules() -> None:
    for module_name, function_name in ROUTE_MODULES.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, function_name))


def test_api_app_factory_does_not_define_route_handlers_inline() -> None:
    source = Path("src/dj_track_similarity/api.py").read_text(encoding="utf-8")

    assert "@app.get" not in source
    assert "@app.post" not in source
