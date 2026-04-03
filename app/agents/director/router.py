from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.agents.director.mock_payloads import (
    build_beats_payload,
    build_blueprint_payload,
    build_deliverables_payload,
    build_draft_payload,
    build_project_payload,
    build_rewrite_payload,
    build_review_payload,
    build_scenes_payload,
    build_seed_payload,
)

router = APIRouter(prefix="/api/director", tags=["director"])


@router.get("/health")
def director_health():
    return {"ok": True, "agent": "director"}


def _body_dict(payload: dict | None) -> dict:
    return payload if isinstance(payload, dict) else {}


def _require_selected_indices(data: dict) -> tuple[int, int]:
    try:
        return int(data["selected_logline_index"]), int(data["selected_mode_index"])
    except Exception as exc:  # pragma: no cover - simple input guard
        raise HTTPException(400, "selected_logline_index and selected_mode_index are required integers") from exc


@router.post("/projects")
def create_director_project(payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    return build_project_payload(
        movie_name=str(data.get("movie_name", "") or ""),
        type_value=str(data.get("type", "") or ""),
        duration=str(data.get("duration", "") or ""),
        tone=str(data.get("tone", "") or ""),
        reference_ip=str(data.get("reference_ip", "") or ""),
    )


@router.post("/projects/{project_id}/seed")
def generate_director_seed(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    return build_seed_payload(
        seed=str(data.get("seed", "") or ""),
        protagonist=str(data.get("protagonist", "") or ""),
        antagonist=str(data.get("antagonist", "") or ""),
        core_synopsis=str(data.get("core_synopsis", "") or ""),
        key_setting=str(data.get("key_setting", "") or ""),
    )


@router.post("/projects/{project_id}/blueprint")
def generate_director_blueprint(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)
    return build_blueprint_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        audience=str(data.get("audience", "") or ""),
        narrative_focus=str(data.get("narrative_focus", "") or ""),
        ending_tendency=str(data.get("ending_tendency", "") or ""),
    )


@router.post("/projects/{project_id}/beats")
def generate_director_beats(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)
    return build_beats_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        segment_granularity=str(data.get("segment_granularity", "") or ""),
        action_ratio=str(data.get("action_ratio", "") or ""),
        character_ratio=str(data.get("character_ratio", "") or ""),
    )


@router.post("/projects/{project_id}/scenes")
def generate_director_scenes(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)
    return build_scenes_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        target_scene_count=str(data.get("target_scene_count", "") or ""),
        scene_constraints=str(data.get("scene_constraints", "") or ""),
        language_style=str(data.get("language_style", "") or ""),
    )


@router.post("/projects/{project_id}/draft")
def generate_director_draft(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)
    return build_draft_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        writing_tendency=str(data.get("writing_tendency", "") or ""),
        dialogue_density=str(data.get("dialogue_density", "") or ""),
        rating_intensity=str(data.get("rating_intensity", "") or ""),
    )


@router.post("/projects/{project_id}/review")
def review_director_draft(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)
    raw_dimensions = data.get("review_dimensions", [])
    review_dimensions = [str(x) for x in raw_dimensions] if isinstance(raw_dimensions, list) else []
    return build_review_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        review_dimensions=review_dimensions,
        rewrite_preference=str(data.get("rewrite_preference", "") or ""),
    )


@router.post("/projects/{project_id}/rewrite")
def rewrite_director_draft(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    selected_logline_index, selected_mode_index = _require_selected_indices(data)

    raw_tasks = data.get("accepted_tasks", [])
    accepted_tasks: list[dict[str, str]] = []
    if isinstance(raw_tasks, list):
        for item in raw_tasks:
            if not isinstance(item, dict):
                continue
            accepted_tasks.append(
                {
                    "task_id": str(item.get("task_id", "") or ""),
                    "action": str(item.get("action", "") or ""),
                }
            )

    return build_rewrite_payload(
        selected_logline_index=selected_logline_index,
        selected_mode_index=selected_mode_index,
        accepted_tasks=accepted_tasks,
        rewrite_scope=str(data.get("rewrite_scope", "") or ""),
        strengthen_metrics=str(data.get("strengthen_metrics", "") or ""),
    )


@router.post("/projects/{project_id}/deliverables")
def generate_director_deliverables(project_id: str, payload: dict | None = Body(default=None)):
    data = _body_dict(payload)
    raw_export_items = data.get("export_items", [])
    export_items = [str(x) for x in raw_export_items] if isinstance(raw_export_items, list) else []
    return build_deliverables_payload(
        selected_version=str(data.get("selected_version", "") or ""),
        asset_filter=str(data.get("asset_filter", "") or ""),
        export_format=str(data.get("export_format", "") or ""),
        export_items=export_items,
    )
