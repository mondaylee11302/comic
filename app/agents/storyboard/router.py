from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

STORYBOARD_ROUTE_TAG = "storyboard"


def is_storyboard_route_path(path: str) -> bool:
    if path.startswith("/api/runs"):
        return True
    return path in {
        "/api/script/generate",
        "/api/script/bind-texts",
    }


def register_storyboard_routes(app: FastAPI) -> None:
    """
    Minimal router shell for storyboard routes.

    Current handlers still live in scripts/run_react_workbench.py.
    This function only marks/collects storyboard-related routes after they are registered,
    so future migration has a stable module entry point without changing behavior.
    """
    matched_paths: list[str] = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not is_storyboard_route_path(route.path):
            continue

        tags = list(route.tags or [])
        if STORYBOARD_ROUTE_TAG not in tags:
            tags.append(STORYBOARD_ROUTE_TAG)
            route.tags = tags
        matched_paths.append(route.path)

    # Lightweight marker for future migration/debugging; does not affect routing behavior.
    app.state.storyboard_route_paths = sorted(set(matched_paths))
