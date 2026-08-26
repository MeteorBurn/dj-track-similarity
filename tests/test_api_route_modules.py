from __future__ import annotations

import importlib

from dj_track_similarity.api import create_app


ROUTE_MODULES = {
    "dj_track_similarity.api_routes_analysis": "register_analysis_routes",
    "dj_track_similarity.api_routes_database": "register_database_routes",
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


def test_every_registered_route_comes_from_a_route_module() -> None:
    app = create_app()

    endpoint_modules = {
        route.endpoint.__module__
        for route in app.routes
        if getattr(route, "endpoint", None) is not None
    }
    project_modules = {
        name for name in endpoint_modules if name.startswith("dj_track_similarity.")
    }

    assert project_modules
    assert all(
        name.startswith("dj_track_similarity.api_routes_") for name in project_modules
    )
