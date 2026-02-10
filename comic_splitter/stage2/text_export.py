from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Mapping


def _as_bbox(raw_bbox) -> List[int]:
    if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
        return [int(v) for v in raw_bbox]
    return [0, 0, 0, 0]


def text_bbox_from_payload(text_payload: Mapping) -> List[int]:
    quad = text_payload.get("quad")
    if isinstance(quad, list) and len(quad) == 4:
        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
        return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
    return _as_bbox(text_payload.get("bbox", [0, 0, 0, 0]))


def to_panel_rel_bbox(canvas_bbox: List[int], panel_bbox: List[int]) -> List[int]:
    cx1, cy1, cx2, cy2 = [int(v) for v in canvas_bbox]
    px1, py1, px2, py2 = [int(v) for v in panel_bbox]
    panel_w = max(0, px2 - px1)
    panel_h = max(0, py2 - py1)

    rx1 = max(0, min(panel_w, cx1 - px1))
    ry1 = max(0, min(panel_h, cy1 - py1))
    rx2 = max(0, min(panel_w, cx2 - px1))
    ry2 = max(0, min(panel_h, cy2 - py1))
    if rx2 <= rx1 or ry2 <= ry1:
        return [0, 0, 0, 0]
    return [int(rx1), int(ry1), int(rx2), int(ry2)]


def build_unified_text_panel_map(
    texts_payload: List[Mapping],
    mapping_v2_payload: List[Mapping],
    panels_payload_raw: List[Mapping],
) -> List[Dict]:
    mapping_by_text_id = {str(m.get("text_id")): m for m in mapping_v2_payload}
    panel_by_id = {str(p.get("panel_id")): p for p in panels_payload_raw}

    items: List[Dict] = []
    for t in texts_payload:
        text_id = str(t.get("text_id"))
        canvas_bbox = text_bbox_from_payload(t)
        mapping = mapping_by_text_id.get(text_id, {})
        primary_panel_id = mapping.get("primary_panel_id")
        if primary_panel_id is not None:
            primary_panel_id = str(primary_panel_id)
        panel = panel_by_id.get(primary_panel_id) if primary_panel_id else None
        panel_bbox = _as_bbox(panel.get("bbox", [0, 0, 0, 0])) if panel is not None else None
        panel_rel_bbox = to_panel_rel_bbox(canvas_bbox, panel_bbox) if panel_bbox is not None else None
        status = "assigned" if panel is not None else "unassigned"

        items.append(
            {
                "text_id": text_id,
                "text": str(t.get("text", "")),
                "canvas_bbox": canvas_bbox,
                "primary_panel_id": primary_panel_id if panel is not None else None,
                "panel_bbox": panel_bbox,
                "panel_rel_bbox": panel_rel_bbox,
                "assignment_score": float(mapping.get("assignment_score", 0.0)),
                "candidate_panels": mapping.get("candidate_panels", []),
                "status": status,
            }
        )
    return items


def _reading_key(item: Mapping) -> tuple:
    bbox = item.get("panel_rel_bbox") or item.get("canvas_bbox") or [0, 0, 0, 0]
    x1, y1, _, _ = [int(v) for v in bbox]
    return (y1, x1)


def build_panel_text_rows(unified_items: List[Mapping]) -> Dict[str, List[Dict]]:
    rows_by_panel: Dict[str, List[Dict]] = {}
    for item in unified_items:
        if str(item.get("status", "")) != "assigned":
            continue
        panel_id = item.get("primary_panel_id")
        if not panel_id:
            continue
        pid = str(panel_id)
        rows_by_panel.setdefault(pid, []).append(
            {
                "text_id": str(item.get("text_id", "")),
                "text": str(item.get("text", "")),
                "canvas_bbox": _as_bbox(item.get("canvas_bbox", [0, 0, 0, 0])),
                "panel_id": pid,
                "panel_bbox": _as_bbox(item.get("panel_bbox", [0, 0, 0, 0])),
                "panel_rel_bbox": _as_bbox(item.get("panel_rel_bbox", [0, 0, 0, 0])),
                "assignment_score": float(item.get("assignment_score", 0.0)),
            }
        )

    for panel_id, rows in rows_by_panel.items():
        rows.sort(key=_reading_key)
        rows_by_panel[panel_id] = rows
    return rows_by_panel


def write_panel_text_files(
    panels_payload_raw: List[Mapping],
    rows_by_panel: Dict[str, List[Mapping]],
    panel_dir: str | Path,
) -> Dict[str, str]:
    out_dir = Path(panel_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    txt_paths: Dict[str, str] = {}
    for p in panels_payload_raw:
        panel_id = str(p.get("panel_id"))
        rows = rows_by_panel.get(panel_id, [])
        txt_path = out_dir / f"{panel_id}.txt"
        with txt_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        txt_paths[panel_id] = str(txt_path)
    return txt_paths


def build_panel_text_manifest(
    panels_payload_raw: List[Mapping],
    txt_paths: Dict[str, str],
    rows_by_panel: Dict[str, List[Mapping]],
) -> List[Dict]:
    manifest: List[Dict] = []
    for p in panels_payload_raw:
        panel_id = str(p.get("panel_id"))
        manifest.append(
            {
                "panel_id": panel_id,
                "image_path": str(p.get("bbox_path", "")),
                "txt_path": txt_paths.get(panel_id, ""),
                "text_count": len(rows_by_panel.get(panel_id, [])),
                "bbox": _as_bbox(p.get("bbox", [0, 0, 0, 0])),
            }
        )
    return manifest
