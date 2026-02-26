"""
子曰工坊V2 — FastAPI Backend
Serves the frontend and provides REST API endpoints for the Picslit2 pipeline.

Usage:
    cd /Users/lishuai/Documents/python/Picslit2
    .venv/bin/python scripts/run_react_workbench.py --host 127.0.0.1 --port 7860
"""
from __future__ import annotations

# Load .env file before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import argparse
import csv
import io
import json
import os
import shutil
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import uvicorn

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Picslit2 Pipeline Workbench", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = ROOT / "output"
UI_STATE_DIR = OUTPUT_DIR / "_ui_state"
WORKBENCH_UI_DIR = UI_STATE_DIR / "_workbench"
WORKBENCH_UI_STATE_PATH = WORKBENCH_UI_DIR / "ui_state.json"
UPLOAD_DIR = OUTPUT_DIR / "_uploads"
FRONTEND_DIR = ROOT / "frontend"
CONFIG_PATH = ROOT / "config" / "storyboard.toml"

# In-memory run registry  { runId: { ... } }
_runs: Dict[str, Dict[str, Any]] = {}
_runs_lock = threading.Lock()
_run_threads: Dict[str, threading.Thread] = {}
_run_cancel_events: Dict[str, threading.Event] = {}


class RunCancelledError(RuntimeError):
    """Raised when a user requests to stop a running task."""
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    UI_STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKBENCH_UI_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _psd_to_png(psd_path: Path) -> Path:
    """Composite a PSD/PSB to PNG (saved alongside the PSD). Returns the PNG path."""
    png_path = psd_path.with_suffix(".png")
    if not png_path.exists():
        from psd_tools import PSDImage
        psd = PSDImage.open(str(psd_path))
        img = psd.composite()
        img.save(str(png_path), format="PNG")
    return png_path


def _find_uploaded_psd_from_preview_path(p: Path) -> Optional[Path]:
    """Recover original PSD/PSB path when frontend mistakenly passes preview PNG path."""
    if p.suffix.lower() in (".psd", ".psb"):
        return p if p.exists() else None
    if p.parent != UPLOAD_DIR:
        return None
    for ext in (".psd", ".psb"):
        cand = p.with_suffix(ext)
        if cand.exists():
            return cand
    return None


def _now_str() -> str:
    return datetime.now().strftime("%Y/%m/%d %H:%M")


def _now_short() -> str:
    return datetime.now().strftime("%m/%d %H:%M")


def _save_run_meta(run_id: str, meta: dict):
    """Persist run metadata to _ui_state."""
    run_dir = UI_STATE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    p = run_dir / "run_meta.json"
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_run_meta(run_id: str) -> Optional[dict]:
    p = UI_STATE_DIR / run_id / "run_meta.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _load_workbench_ui_state() -> dict:
    """Load persisted global workbench UI state."""
    if WORKBENCH_UI_STATE_PATH.exists():
        try:
            data = json.loads(WORKBENCH_UI_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_workbench_ui_state(state: dict) -> None:
    """Persist global workbench UI state under output/_ui_state/_workbench."""
    _ensure_dirs()
    if not isinstance(state, dict):
        state = {}
    WORKBENCH_UI_STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _normalize_loaded_run(run: dict, *, has_pipeline_meta: bool) -> dict:
    """Normalize persisted run states at startup to avoid phantom 'running' jobs."""
    if not isinstance(run, dict):
        return run
    normalized = dict(run)
    status = str(normalized.get("status", "") or "")
    if status != "running":
        return normalized
    if has_pipeline_meta:
        # Pipeline meta exists on disk => the run completed at least once.
        normalized["status"] = "success"
        normalized["error"] = ""
    else:
        # Server restart cannot resume the original thread; mark as interrupted.
        normalized["status"] = "error"
        if not normalized.get("error"):
            normalized["error"] = "任务在服务重启前处于运行中，已标记为中断"
    return normalized


def _scan_pipeline_metas() -> List[dict]:
    """Scan output directory for *_pipeline_meta.json files."""
    results = []
    if not OUTPUT_DIR.exists():
        return results
    for f in sorted(OUTPUT_DIR.glob("*_pipeline_meta.json")):
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
            prefix = f.stem.replace("_pipeline_meta", "")
            meta["_prefix"] = prefix
            meta["_meta_path"] = str(f)
            results.append(meta)
        except Exception:
            continue
    return results


def _delete_run_artifacts(run_id: str) -> dict:
    """Delete local artifacts for a run (best-effort, safe exact paths only)."""
    removed: List[str] = []
    missing: List[str] = []

    exact_paths = [
        UI_STATE_DIR / run_id,
        OUTPUT_DIR / f"{run_id}_pipeline_meta.json",
        OUTPUT_DIR / f"{run_id}_panels_manifest.json",
        OUTPUT_DIR / f"{run_id}_text_panel_unified_map.json",
        OUTPUT_DIR / f"{run_id}_panels",
    ]

    # Optional common outputs/debug files/directories (exact names only).
    exact_paths.extend([
        OUTPUT_DIR / f"{run_id}_ocr_lines.json",
        OUTPUT_DIR / f"{run_id}_ocr_raw.json",
        OUTPUT_DIR / f"{run_id}_text_panel_map.json",
        OUTPUT_DIR / f"{run_id}_texts.json",
        OUTPUT_DIR / "debug" / run_id,
        OUTPUT_DIR / "debug" / f"{run_id}_panels",
    ])

    for p in exact_paths:
        try:
            if p.is_dir():
                shutil.rmtree(p)
                removed.append(str(p))
            elif p.exists():
                p.unlink()
                removed.append(str(p))
            else:
                missing.append(str(p))
        except Exception as exc:
            # Keep going; frontend only needs task record removed reliably.
            print(f"[run:{run_id}] WARN delete artifact failed: {p} ({exc})", flush=True)

    # Clean global UI state pointer if it points to the deleted run.
    try:
        wb_state = _load_workbench_ui_state()
        if isinstance(wb_state, dict) and wb_state.get("studioRunId") == run_id:
            wb_state["studioRunId"] = None
            _save_workbench_ui_state(wb_state)
    except Exception as exc:
        print(f"[run:{run_id}] WARN clear ui state studioRunId failed: {exc}", flush=True)

    return {"removed": removed, "missing": missing}


def _pick_latest_run_for_psd(psd_file: str) -> Optional[str]:
    """Pick the latest successful run id for a PSD file, fallback to any known run."""
    metas = _scan_pipeline_metas()
    candidates: List[tuple[float, str]] = []
    for meta in metas:
        image_name = Path(str(meta.get("image", ""))).name
        prefix = str(meta.get("_prefix", "")).strip()
        if not prefix or image_name != psd_file:
            continue
        meta_path = Path(str(meta.get("_meta_path", "")))
        ts = meta_path.stat().st_mtime if meta_path.exists() else 0.0
        candidates.append((ts, prefix))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _scan_panel_manifests() -> Dict[str, dict]:
    """Scan output for *_panels_manifest.json, keyed by prefix."""
    result = {}
    if not OUTPUT_DIR.exists():
        return result
    for f in sorted(OUTPUT_DIR.glob("*_panels_manifest.json")):
        try:
            manifest = json.loads(f.read_text(encoding="utf-8"))
            prefix = f.stem.replace("_panels_manifest", "")
            manifest["_prefix"] = prefix
            result[prefix] = manifest
        except Exception:
            continue
    return result


def _build_run_from_pipeline_meta(meta: dict) -> dict:
    """Build a run dict from pipeline meta."""
    prefix = meta.get("_prefix", "unknown")
    image_path = meta.get("image", "")
    psd_file = Path(image_path).name if image_path else prefix + ".psd"
    panel_count = meta.get("panel_count", 0)
    text_count = meta.get("text_count", 0)
    split_mode = meta.get("split_mode", "bands")

    # Check UI state for saved meta
    ui_meta = _load_run_meta(prefix) or {}

    run = {
        "id": prefix,
        "file": psd_file,
        "status": ui_meta.get("status", "success"),
        "strategy": "advanced" if split_mode == "stage2" else "normal",
        "panels": panel_count,
        "texts": text_count,
        "time": ui_meta.get("time", ""),
        "error": ui_meta.get("error", ""),
        "imagePath": image_path,
        "ocrStatus": meta.get("preprocess", {}).get("ocr_status", ""),
    }
    normalized = _normalize_loaded_run(run, has_pipeline_meta=True)
    if ui_meta and (
        normalized.get("status") != ui_meta.get("status")
        or normalized.get("error", "") != ui_meta.get("error", "")
    ):
        try:
            _save_run_meta(prefix, {**ui_meta, "status": normalized.get("status"), "error": normalized.get("error", "")})
        except Exception:
            pass
    return normalized


def _init_runs_from_disk():
    """Load runs from disk at startup."""
    _ensure_dirs()
    metas = _scan_pipeline_metas()
    with _runs_lock:
        for meta in metas:
            prefix = meta.get("_prefix", "")
            if prefix and prefix not in _runs:
                _runs[prefix] = _build_run_from_pipeline_meta(meta)

        # Also load any runs that are only in _ui_state (e.g. failed runs)
        if UI_STATE_DIR.exists():
            for run_dir in UI_STATE_DIR.iterdir():
                if run_dir.is_dir() and run_dir.name not in _runs:
                    ui_meta = _load_run_meta(run_dir.name)
                    if ui_meta:
                        normalized = _normalize_loaded_run(ui_meta, has_pipeline_meta=False)
                        _runs[run_dir.name] = normalized
                        if (
                            normalized.get("status") != ui_meta.get("status")
                            or normalized.get("error", "") != ui_meta.get("error", "")
                        ):
                            try:
                                _save_run_meta(run_dir.name, {**ui_meta, "status": normalized.get("status"), "error": normalized.get("error", "")})
                            except Exception:
                                pass


# ---------------------------------------------------------------------------
# Run processing in background
# ---------------------------------------------------------------------------
def _run_workflow_bg(run_id: str, image_path: str, strategy: str):
    """Run StoryboardWorkflow in a background thread."""
    cancel_event = _run_cancel_events.get(run_id)
    try:
        from comic_splitter.workflow import (
            AgentRetryMatrix,
            StoryboardOptions,
            StoryboardPaths,
            StoryboardWorkflow,
            load_storyboard_config,
        )

        img = Path(image_path).expanduser()
        if not img.exists():
            raise FileNotFoundError(f"Image not found: {img}")

        out_dir = OUTPUT_DIR
        debug_dir = OUTPUT_DIR / "debug"

        default_paths = StoryboardPaths(
            image_path=img,
            out_dir=out_dir,
            debug_dir=debug_dir,
            prefix=run_id,
        )
        default_options = StoryboardOptions(
            strict_ocr=True,
            reuse_preprocess_cache=True,
            force_reprocess=False,
            split_mode="stage2" if strategy == "advanced" else "bands",
        )
        default_retry = AgentRetryMatrix()

        # Load config
        paths, options, retry = load_storyboard_config(
            config_path=CONFIG_PATH if CONFIG_PATH.exists() else None,
            default_paths=default_paths,
            default_options=default_options,
            default_retry=default_retry,
        )
        # Override with request params
        paths.image_path = img
        paths.prefix = run_id
        paths.out_dir = out_dir
        paths.debug_dir = debug_dir
        options.split_mode = "stage2" if strategy == "advanced" else "bands"

        def _log(msg: str):
            if cancel_event and cancel_event.is_set():
                raise RunCancelledError("用户请求停止任务")
            print(f"[run:{run_id}] {msg}", flush=True)

        if cancel_event and cancel_event.is_set():
            raise RunCancelledError("用户请求停止任务")
        workflow = StoryboardWorkflow(paths=paths, options=options, log=_log, retry_matrix=retry)
        state = workflow.run()
        if cancel_event and cancel_event.is_set():
            raise RunCancelledError("用户请求停止任务")

        # Update run status
        with _runs_lock:
            if run_id in _runs:
                _runs[run_id]["status"] = "success"
                _runs[run_id]["panels"] = len(state.panels_payload)
                _runs[run_id]["texts"] = len(state.texts_payload)

        # Persist
        _save_run_meta(run_id, _runs.get(run_id, {}))
        print(f"[run:{run_id}] completed successfully", flush=True)

    except RunCancelledError as e:
        print(f"[run:{run_id}] STOPPED: {e}", flush=True)
        with _runs_lock:
            if run_id in _runs:
                _runs[run_id]["status"] = "error"
                _runs[run_id]["error"] = "用户已停止任务"
        _save_run_meta(run_id, _runs.get(run_id, {}))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[run:{run_id}] FAILED: {e}\n{tb}", flush=True)
        with _runs_lock:
            if run_id in _runs:
                _runs[run_id]["status"] = "error"
                _runs[run_id]["error"] = str(e)
        _save_run_meta(run_id, _runs.get(run_id, {}))
    finally:
        with _runs_lock:
            _run_threads.pop(run_id, None)
            _run_cancel_events.pop(run_id, None)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok", "time": _now_str()}


@app.get("/api/ui/workbench-state")
def get_workbench_ui_state():
    """Load persisted global UI state for the workbench frontend."""
    return _load_workbench_ui_state()


@app.patch("/api/ui/workbench-state")
async def patch_workbench_ui_state(request: dict):
    """Persist global UI state for the workbench frontend."""
    if not isinstance(request, dict):
        raise HTTPException(400, "Request body must be a JSON object")
    allowed_keys = {
        "view",
        "tab",
        "agentTab",
        "statusFilter",
        "searchQ",
        "assetSearch",
        "selectedStrategy",
        "studioRunId",
        "uploadQueue",
        "updatedAt",
    }
    prev = _load_workbench_ui_state()
    next_state = dict(prev) if isinstance(prev, dict) else {}
    for k, v in request.items():
        if k in allowed_keys:
            next_state[k] = v
    next_state["updatedAt"] = _now_str()
    _save_workbench_ui_state(next_state)
    return {"status": "ok", "state": next_state}


@app.get("/api/runs")
def list_runs(status: Optional[str] = None, q: Optional[str] = None):
    with _runs_lock:
        runs = list(_runs.values())
    if status and status != "all":
        status_map = {"success": "success", "running": "running", "error": "error"}
        target = status_map.get(status, status)
        runs = [r for r in runs if r.get("status") == target]
    if q:
        ql = q.lower()
        runs = [r for r in runs if ql in r.get("id", "").lower() or ql in r.get("file", "").lower()]
    # Sort: running first, then by time descending
    order = {"running": 0, "error": 1, "success": 2}
    runs.sort(key=lambda r: (order.get(r.get("status", ""), 3), r.get("id", "")))
    return runs


@app.post("/api/runs")
async def create_run(
    file: Optional[UploadFile] = File(None),
    image_path: Optional[str] = Query(None),
    strategy: str = Query("normal"),
    prefix: Optional[str] = Query(None),
):
    """Create a new processing run.

    Can accept either:
    - file: uploaded PSD file
    - image_path: path to existing PSD file on disk
    """
    source_path = ""
    preview_path = ""
    psd_name = ""

    if file and file.filename:
        # Save uploaded file
        _ensure_dirs()
        safe_name = file.filename.replace("/", "_").replace("\\", "_")
        save_path = UPLOAD_DIR / safe_name
        content = await file.read()
        save_path.write_bytes(content)
        source_path = str(save_path)
        preview_path = str(save_path)
        psd_name = safe_name
        # Convert PSD to PNG immediately so the frontend can preview it
        if save_path.suffix.lower() in (".psd", ".psb"):
            try:
                png_path = _psd_to_png(save_path)
                preview_path = str(png_path)
            except Exception as exc:
                print(f"[warn] PSD→PNG conversion failed: {exc}", flush=True)
    elif image_path:
        req_path = Path(image_path).expanduser()
        recovered_psd = _find_uploaded_psd_from_preview_path(req_path)
        if recovered_psd is not None:
            source_p = recovered_psd
        else:
            source_p = req_path
        source_path = str(source_p)
        psd_name = source_p.name
        preview_path = image_path
        # Convert PSD to PNG for preview if needed
        if source_p.suffix.lower() in (".psd", ".psb") and source_p.exists():
            try:
                png_path = _psd_to_png(source_p)
                preview_path = str(png_path)
            except Exception as exc:
                print(f"[warn] PSD→PNG conversion failed: {exc}", flush=True)
        elif not source_p.exists():
            raise HTTPException(404, f"File not found: {image_path}")
        elif source_p.suffix.lower() not in (".psd", ".psb"):
            raise HTTPException(400, "image_path must be a PSD/PSB file path")
    else:
        raise HTTPException(400, "Must provide either file upload or image_path")

    run_id = prefix or Path(psd_name).stem or f"run_{uuid.uuid4().hex[:8]}"

    # Avoid duplicate run IDs
    with _runs_lock:
        if run_id in _runs and _runs[run_id].get("status") == "running":
            raise HTTPException(409, f"Run '{run_id}' is already running")
        orig_id = run_id
        counter = 1
        while run_id in _runs and _runs[run_id].get("status") == "success":
            run_id = f"{orig_id}_{counter}"
            counter += 1

    run_data = {
        "id": run_id,
        "file": psd_name,
        "status": "running",
        "strategy": strategy,
        "panels": None,
        "texts": None,
        "time": _now_short(),
        "error": "",
        "imagePath": preview_path or source_path,
        "sourceImagePath": source_path,
    }

    with _runs_lock:
        _runs[run_id] = run_data

    _save_run_meta(run_id, run_data)

    # Start background processing
    cancel_event = threading.Event()
    t = threading.Thread(target=_run_workflow_bg, args=(run_id, source_path, strategy), daemon=True)
    with _runs_lock:
        _run_cancel_events[run_id] = cancel_event
        _run_threads[run_id] = t
    t.start()

    return run_data


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with _runs_lock:
        run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return run


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    """Request cooperative stop for a running task."""
    with _runs_lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(404, f"Run '{run_id}' not found")
        if run.get("status") != "running":
            return {"status": "ok", "run": run, "alreadyStopped": True}
        evt = _run_cancel_events.get(run_id)
        if evt:
            evt.set()
        run["error"] = "停止请求已发送"
        run["stopRequested"] = True
        snapshot = dict(run)
    _save_run_meta(run_id, snapshot)
    return {"status": "ok", "run": snapshot, "stopRequested": True}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    """Delete a task record and its primary local artifacts."""
    with _runs_lock:
        run = _runs.get(run_id)
        if not run:
            raise HTTPException(404, f"Run '{run_id}' not found")
        if run.get("status") == "running":
            raise HTTPException(409, "任务仍在运行，请先停止")
        _runs.pop(run_id, None)
        _run_threads.pop(run_id, None)
        _run_cancel_events.pop(run_id, None)
    deleted = _delete_run_artifacts(run_id)
    return {"status": "ok", "runId": run_id, "deleted": deleted}


@app.get("/api/runs/{run_id}/result")
def get_run_result(run_id: str, strip_text_binding: bool = True):
    """Get full result for a run including panels, texts, clean image."""
    with _runs_lock:
        run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")

    result: Dict[str, Any] = {"run": run, "panels": [], "texts": [], "cleanImage": None}

    # Backward-compat: if imagePath is still a PSD, convert to PNG for preview
    image_path_str = run.get("imagePath", "")
    if image_path_str and Path(image_path_str).suffix.lower() in (".psd", ".psb"):
        try:
            png_path = _psd_to_png(Path(image_path_str))
            # Return a shallow copy of run with updated imagePath
            result["run"] = {**run, "imagePath": str(png_path)}
        except Exception as exc:
            print(f"[warn] PSD→PNG conversion failed for {image_path_str}: {exc}", flush=True)


    # Load pipeline meta
    meta_path = OUTPUT_DIR / f"{run_id}_pipeline_meta.json"
    if meta_path.exists():
        try:
            pipeline_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            result["pipelineMeta"] = pipeline_meta
            result["cleanImage"] = pipeline_meta.get("preprocess", {}).get("art_clean_path")
        except Exception:
            pass

    # Load panels manifest
    manifest_path = OUTPUT_DIR / f"{run_id}_panels_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            result["panels"] = manifest.get("panels", [])
        except Exception:
            pass

    # Load unified text-panel map
    unified_path = OUTPUT_DIR / f"{run_id}_text_panel_unified_map.json"
    if unified_path.exists():
        try:
            unified = json.loads(unified_path.read_text(encoding="utf-8"))
            text_items = unified.get("items", [])
            if strip_text_binding:
                # Studio view should treat OCR texts as an unbound pool by default.
                # Keep detected panel assignment as a hint field, but do not expose it
                # as the active binding relationship.
                normalized_items = []
                for item in text_items:
                    if not isinstance(item, dict):
                        continue
                    row = dict(item)
                    detected_panel_id = row.get("primary_panel_id") or row.get("panel_id")
                    if detected_panel_id is not None:
                        row["detected_panel_id"] = detected_panel_id
                    row["primary_panel_id"] = None
                    if "panel_id" in row:
                        row["panel_id"] = None
                    normalized_items.append(row)
                result["texts"] = normalized_items
            else:
                result["texts"] = text_items
        except Exception:
            pass

    # Optional UI-level bindings saved after script generation:
    # panel -> selected texts -> generated script metadata/result snapshot.
    ui_meta = _load_run_meta(run_id) or {}
    if isinstance(ui_meta.get("panelTextScriptBindings"), dict):
        result["panelTextScriptBindings"] = ui_meta.get("panelTextScriptBindings")

    return result


@app.get("/api/assets/psd")
def list_assets(q: Optional[str] = None):
    """List PSD assets aggregated from pipeline metadata."""
    metas = _scan_pipeline_metas()
    manifests = _scan_panel_manifests()

    # Group by PSD file
    psd_map: Dict[str, dict] = {}
    for meta in metas:
        psd_file = Path(meta.get("image", "")).name
        prefix = meta.get("_prefix", "")
        if not psd_file:
            continue

        if psd_file not in psd_map:
            psd_map[psd_file] = {
                "file": psd_file,
                "panels": 0,
                "coverage": 0,
                "updated": "",
                "notes": "",
                "imagePath": meta.get("image", ""),
                "previewRunId": prefix,
                "runs": [],
            }

        entry = psd_map[psd_file]
        panel_count = meta.get("panel_count", 0)
        text_count = meta.get("text_count", 0)
        entry["panels"] = max(entry["panels"], panel_count)

        # Script coverage approximation: texts with panel assignments
        if text_count > 0:
            unified_path = OUTPUT_DIR / f"{prefix}_text_panel_unified_map.json"
            assigned = 0
            if unified_path.exists():
                try:
                    unified = json.loads(unified_path.read_text(encoding="utf-8"))
                    for item in unified.get("items", []):
                        if item.get("panel_id"):
                            assigned += 1
                except Exception:
                    pass
            entry["coverage"] = int(100 * assigned / text_count) if text_count else 0

        # Get file modification time
        meta_path = Path(meta.get("_meta_path", ""))
        if meta_path.exists():
            mtime = meta_path.stat().st_mtime
            entry["updated"] = datetime.fromtimestamp(mtime).strftime("%Y/%m/%d %H:%M")

        # Load notes from UI state
        ui_meta = _load_run_meta(prefix)
        if ui_meta and ui_meta.get("assetNote"):
            entry["notes"] = ui_meta["assetNote"]

        entry["runs"].append({
            "id": prefix,
            "strategy": "advanced" if meta.get("split_mode") == "stage2" else "normal",
            "panels": panel_count,
            "texts": text_count,
        })
        # Prefer PNG preview path for frontend card display.
        img_path = Path(str(entry.get("imagePath") or ""))
        if img_path.suffix.lower() in (".psd", ".psb") and img_path.exists():
            try:
                entry["imagePath"] = str(_psd_to_png(img_path))
            except Exception:
                pass
        if not entry.get("previewRunId"):
            entry["previewRunId"] = prefix

    assets = list(psd_map.values())

    if q:
        ql = q.lower()
        assets = [a for a in assets if ql in a.get("file", "").lower()]

    return assets


@app.get("/api/assets/psd/detail")
def get_asset_detail(file: str = Query(..., description="PSD file name")):
    """Return asset detail with PSD image, panels, texts grouped by panel, scripts and per-panel notes."""
    run_id = _pick_latest_run_for_psd(file)
    if not run_id:
        raise HTTPException(404, f"No asset run found for PSD: {file}")

    # Assets page needs the original detected panel-text association from pipeline output.
    base = get_run_result(run_id, strip_text_binding=False)
    run = base.get("run", {}) or {}
    panels = base.get("panels", []) or []
    texts = base.get("texts", []) or []

    texts_by_panel: Dict[str, List[dict]] = {}
    for t in texts:
        pid = str(t.get("primary_panel_id") or "unassigned")
        texts_by_panel.setdefault(pid, []).append(t)

    # Load per-panel scripts from panel image sibling files if present.
    scripts_by_panel: Dict[str, dict] = {}
    script_bindings_by_panel: Dict[str, dict] = {}
    for p in panels:
        panel_id = str(p.get("panel_id", ""))
        bbox_path = Path(str(p.get("bbox_path", "")))
        if not panel_id or not bbox_path.exists():
            continue
        script_json = bbox_path.with_name(f"{bbox_path.stem}_script.json")
        script_md = bbox_path.with_name(f"{bbox_path.stem}_script.md")
        script_payload: Dict[str, Any] = {}
        if script_json.exists():
            try:
                script_payload = json.loads(script_json.read_text(encoding="utf-8"))
            except Exception:
                script_payload = {"raw": script_json.read_text(encoding="utf-8", errors="ignore")}
        elif script_md.exists():
            script_payload = {"script_text": script_md.read_text(encoding="utf-8", errors="ignore")}
        if script_payload:
            if isinstance(script_payload, dict):
                binding = script_payload.get("binding") or script_payload.get("panel_text_script_binding")
                if not binding and (script_payload.get("selected_text_ids") or script_payload.get("selected_texts")):
                    binding = {
                        "runId": run_id,
                        "panelId": panel_id,
                        "selectedTextIds": script_payload.get("selected_text_ids", []),
                        "selectedTexts": script_payload.get("selected_texts", []),
                        "updatedAt": script_payload.get("updated_at"),
                    }
                if binding:
                    script_bindings_by_panel[panel_id] = binding
            # Common schema normalization for frontend.
            normalized = script_payload.get("script", script_payload)
            scripts_by_panel[panel_id] = normalized if isinstance(normalized, dict) else {"raw": normalized}

    ui_meta = _load_run_meta(run_id) or {}
    panel_notes = ui_meta.get("assetPanelNotes", {}) if isinstance(ui_meta.get("assetPanelNotes"), dict) else {}
    ui_panel_bindings = ui_meta.get("panelTextScriptBindings", {}) if isinstance(ui_meta.get("panelTextScriptBindings"), dict) else {}

    # Provide a render-friendly panel projection.
    panel_cards = []
    for p in panels:
        panel_id = str(p.get("panel_id", ""))
        panel_cards.append({
            "panelId": panel_id,
            "imagePath": p.get("bbox_path"),
            "txtPath": p.get("txt_path"),
            "texts": texts_by_panel.get(panel_id, []),
            "script": scripts_by_panel.get(panel_id),
            "scriptBinding": script_bindings_by_panel.get(panel_id) or ui_panel_bindings.get(panel_id),
            "note": panel_notes.get(panel_id, ""),
            "raw": p,
        })

    return {
        "file": file,
        "runId": run_id,
        "run": run,
        "psdImagePath": run.get("imagePath") or base.get("cleanImage") or run.get("sourceImagePath"),
        "sourcePsdPath": run.get("sourceImagePath"),
        "panels": panel_cards,
        "unassignedTexts": texts_by_panel.get("unassigned", []),
        "panelCount": len(panel_cards),
    }


@app.patch("/api/assets/psd/panel-note")
async def update_asset_panel_note(request: dict):
    """Update per-panel note for an asset panel."""
    psd_file = str(request.get("file", "")).strip()
    panel_id = str(request.get("panelId", "")).strip()
    note = str(request.get("note", ""))
    if not psd_file or not panel_id:
        raise HTTPException(400, "file and panelId are required")

    run_id = _pick_latest_run_for_psd(psd_file)
    if not run_id:
        raise HTTPException(404, f"No asset run found for PSD: {psd_file}")

    ui_meta = _load_run_meta(run_id) or {"id": run_id}
    notes = ui_meta.get("assetPanelNotes")
    if not isinstance(notes, dict):
        notes = {}
    notes[panel_id] = note
    ui_meta["assetPanelNotes"] = notes
    _save_run_meta(run_id, ui_meta)
    return {"status": "ok", "runId": run_id, "panelId": panel_id, "note": note}


@app.patch("/api/assets/psd/{psd_id}/note")
async def update_asset_note(psd_id: str):
    """Update note for a PSD asset."""
    from starlette.requests import Request
    # Parse body manually since psd_id might have dots
    # This is a simplified approach
    return {"status": "ok"}


@app.post("/api/exports/excel")
def export_excel():
    """Export runs and assets as CSV."""
    _ensure_dirs()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Run ID", "PSD File", "Status", "Strategy", "Panels", "Texts", "Time"])

    with _runs_lock:
        for run in _runs.values():
            writer.writerow([
                run.get("id", ""),
                run.get("file", ""),
                run.get("status", ""),
                run.get("strategy", ""),
                run.get("panels", ""),
                run.get("texts", ""),
                run.get("time", ""),
            ])

    csv_content = output.getvalue()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"picslit_export_{timestamp}.csv"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(csv_content, encoding="utf-8-sig")

    return {"status": "ok", "filename": filename, "path": str(filepath)}


@app.get("/api/file")
def serve_file(path: str = Query(...)):
    """Serve a file from the output directory."""
    p = Path(path).expanduser().resolve()

    # Security: only serve files under project dir
    try:
        p.relative_to(ROOT.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")

    if not p.exists():
        raise HTTPException(404, f"File not found: {path}")

    return FileResponse(str(p))



@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a PSD file for later processing."""
    _ensure_dirs()
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    save_path = UPLOAD_DIR / safe_name
    content = await file.read()
    save_path.write_bytes(content)
    # Convert PSD to PNG immediately for preview
    source_path_str = str(save_path)
    preview_path_str = source_path_str
    if save_path.suffix.lower() in (".psd", ".psb"):
        try:
            png_path = _psd_to_png(save_path)
            preview_path_str = str(png_path)
        except Exception as exc:
            print(f"[warn] PSD→PNG conversion failed: {exc}", flush=True)
    return {
        "status": "ok",
        "filename": safe_name,
        "path": source_path_str,          # backward-compatible key, now always source PSD/PSB path
        "sourcePath": source_path_str,
        "previewPath": preview_path_str,
        "size": len(content),
    }


@app.get("/api/psd-files")
def list_psd_files():
    """List available PSD files (uploads + known image paths)."""
    files = []

    # From uploads
    if UPLOAD_DIR.exists():
        for f in sorted(UPLOAD_DIR.glob("*.psd")) + sorted(UPLOAD_DIR.glob("*.psb")):
            files.append({
                "name": f.name,
                "path": str(f),
                "source": "upload",
                "size": f.stat().st_size,
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y/%m/%d"),
            })

    # From pipeline outputs (deduplicate by name)
    seen = {f["name"] for f in files}
    metas = _scan_pipeline_metas()
    for meta in metas:
        image_path = meta.get("image", "")
        if image_path:
            p = Path(image_path)
            if p.name not in seen and p.exists():
                files.append({
                    "name": p.name,
                    "path": str(p),
                    "source": "existing",
                    "size": p.stat().st_size if p.exists() else 0,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y/%m/%d") if p.exists() else "",
                })
                seen.add(p.name)

    return files


@app.post("/api/script/generate")
async def generate_script(request: dict = None):
    """Generate a panel script using the Doubao model.

    Body JSON: { runId, panelId, selectedTextIds: [...], prompt }
    """
    from starlette.requests import Request as StarletteRequest
    import json as _json

    # Parse body
    if request is None:
        raise HTTPException(400, "Missing request body")

    run_id = request.get("runId", "")
    panel_id = request.get("panelId", "")
    selected_text_ids = request.get("selectedTextIds", [])
    user_prompt = request.get("prompt", "").strip() or "请根据分镜画面和选中的文字，生成分镜脚本"

    if not run_id or not panel_id:
        raise HTTPException(400, "runId and panelId are required")
    if not selected_text_ids:
        raise HTTPException(400, "Please select at least one text")

    # Find panel image
    panel_dir = OUTPUT_DIR / f"{run_id}_panels"
    panel_image_path = panel_dir / f"{panel_id}.png"
    if not panel_image_path.exists():
        raise HTTPException(404, f"Panel image not found: {panel_image_path}")

    # Load unified text map to get text rows
    unified_path = OUTPUT_DIR / f"{run_id}_text_panel_unified_map.json"
    if not unified_path.exists():
        raise HTTPException(404, f"Text map not found for run {run_id}")

    try:
        unified = _json.loads(unified_path.read_text(encoding="utf-8"))
        all_items = unified.get("items", [])
    except Exception as e:
        raise HTTPException(500, f"Failed to load text map: {e}")

    # Filter selected texts
    selected_rows = []
    for item in all_items:
        if item.get("text_id") in selected_text_ids:
            selected_rows.append({
                "text_id": item.get("text_id"),
                "text": item.get("text", ""),
                "panel_rel_bbox": item.get("panel_rel_bbox", [0, 0, 0, 0]),
                "canvas_bbox": item.get("canvas_bbox", [0, 0, 0, 0]),
            })

    if not selected_rows:
        raise HTTPException(400, "No matching texts found for the selected IDs")

    try:
        from comic_splitter.script_agent import ScriptAgentConfig, generate_panel_script
        import os

        cfg = ScriptAgentConfig(
            api_key=os.environ.get("SCRIPT_AGENT_API_KEY", os.environ.get("VOLC_API_KEY", "")),
            model_endpoint=os.environ.get("SCRIPT_AGENT_MODEL", "doubao-seed-1-8-251228"),
            base_url=os.environ.get("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            allow_local_fallback=True,
        )

        result = generate_panel_script(
            panel_image_path=str(panel_image_path),
            selected_rows=selected_rows,
            user_goal=user_prompt,
            cfg=cfg,
            verbose_hook=lambda msg: print(f"[script:{run_id}/{panel_id}] {msg}", flush=True),
        )

        normalized_text_ids = [str(row.get("text_id", "")) for row in selected_rows if row.get("text_id")]
        binding_payload = {
            "runId": run_id,
            "panelId": panel_id,
            "selectedTextIds": normalized_text_ids,
            "selectedTexts": selected_rows,
            "updatedAt": _now_str(),
        }

        # Persist panel-level script + binding relation next to panel image for assets page.
        try:
            panel_script_path = panel_image_path.with_name(f"{panel_image_path.stem}_script.json")
            panel_script_payload = {
                "version": 2,
                "panel_id": panel_id,
                "selected_text_ids": normalized_text_ids,
                "selected_texts": selected_rows,
                "binding": binding_payload,
                "script": result,
                "updated_at": binding_payload["updatedAt"],
            }
            panel_script_path.write_text(_json.dumps(panel_script_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as persist_err:
            print(f"[script:{run_id}/{panel_id}] WARN persist panel script failed: {persist_err}", flush=True)

        # Persist binding index in UI state for quick frontend retrieval and note/script linkage.
        try:
            ui_meta = _load_run_meta(run_id) or {"id": run_id}
            bindings = ui_meta.get("panelTextScriptBindings")
            if not isinstance(bindings, dict):
                bindings = {}
            bindings[panel_id] = {
                **binding_payload,
                "scriptMeta": result.get("meta", {}) if isinstance(result, dict) else {},
            }
            ui_meta["panelTextScriptBindings"] = bindings
            _save_run_meta(run_id, ui_meta)
        except Exception as persist_err:
            print(f"[script:{run_id}/{panel_id}] WARN persist run meta binding failed: {persist_err}", flush=True)

        return {"status": "ok", "script": result, "binding": binding_payload}

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[script:{run_id}/{panel_id}] ERROR: {e}\n{tb}", flush=True)
        raise HTTPException(500, f"Script generation failed: {e}")


@app.post("/api/script/bind-texts")
async def bind_panel_texts(request: dict = None):
    """Save panel-text binding without generating a script.

    Body JSON: { runId, panelId, selectedTextIds: [...] }
    """
    import json as _json

    if request is None:
        raise HTTPException(400, "Missing request body")

    run_id = str(request.get("runId", "")).strip()
    panel_id = str(request.get("panelId", "")).strip()
    selected_text_ids = request.get("selectedTextIds", [])
    clear_binding = bool(request.get("clear", False))

    if not run_id or not panel_id:
        raise HTTPException(400, "runId and panelId are required")
    if not isinstance(selected_text_ids, list):
        raise HTTPException(400, "selectedTextIds must be a list")

    panel_dir = OUTPUT_DIR / f"{run_id}_panels"
    panel_image_path = panel_dir / f"{panel_id}.png"
    if not panel_image_path.exists():
        raise HTTPException(404, f"Panel image not found: {panel_image_path}")

    binding_payload = None
    normalized_text_ids: List[str] = []
    selected_rows: List[Dict[str, Any]] = []
    if not clear_binding:
        if not selected_text_ids:
            raise HTTPException(400, "Please select at least one text")
        unified_path = OUTPUT_DIR / f"{run_id}_text_panel_unified_map.json"
        if not unified_path.exists():
            raise HTTPException(404, f"Text map not found for run {run_id}")

        try:
            unified = _json.loads(unified_path.read_text(encoding="utf-8"))
            all_items = unified.get("items", [])
        except Exception as e:
            raise HTTPException(500, f"Failed to load text map: {e}")

        selected_id_set = {str(x) for x in selected_text_ids}
        for item in all_items:
            tid = str(item.get("text_id", ""))
            if tid in selected_id_set:
                selected_rows.append({
                    "text_id": tid,
                    "text": item.get("text", ""),
                    "panel_rel_bbox": item.get("panel_rel_bbox", [0, 0, 0, 0]),
                    "canvas_bbox": item.get("canvas_bbox", [0, 0, 0, 0]),
                })

        if not selected_rows:
            raise HTTPException(400, "No matching texts found for the selected IDs")

        normalized_text_ids = [str(row.get("text_id", "")) for row in selected_rows if row.get("text_id")]
        binding_payload = {
            "runId": run_id,
            "panelId": panel_id,
            "selectedTextIds": normalized_text_ids,
            "selectedTexts": selected_rows,
            "updatedAt": _now_str(),
        }

    # Persist to run UI state first (used by studio and assets fallback).
    try:
        ui_meta = _load_run_meta(run_id) or {"id": run_id}
        bindings = ui_meta.get("panelTextScriptBindings")
        if not isinstance(bindings, dict):
            bindings = {}
        prev = bindings.get(panel_id, {}) if isinstance(bindings.get(panel_id), dict) else {}
        script_meta = prev.get("scriptMeta", {}) if isinstance(prev.get("scriptMeta"), dict) else {}
        if clear_binding:
            bindings.pop(panel_id, None)
        else:
            bindings[panel_id] = {**binding_payload, "scriptMeta": script_meta}
        ui_meta["panelTextScriptBindings"] = bindings
        _save_run_meta(run_id, ui_meta)
    except Exception as e:
        raise HTTPException(500, f"Failed to save binding: {e}")

    # If panel script file already exists, update its binding fields too (keep script content).
    try:
        panel_script_path = panel_image_path.with_name(f"{panel_image_path.stem}_script.json")
        if panel_script_path.exists():
            payload: Dict[str, Any] = {}
            try:
                payload = _json.loads(panel_script_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            payload["version"] = max(int(payload.get("version", 1) or 1), 2)
            payload["panel_id"] = panel_id
            payload["selected_text_ids"] = normalized_text_ids
            payload["selected_texts"] = selected_rows
            if clear_binding:
                payload.pop("binding", None)
                payload["updated_at"] = _now_str()
            else:
                payload["binding"] = binding_payload
                payload["updated_at"] = binding_payload["updatedAt"]
            panel_script_path.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[bind:{run_id}/{panel_id}] WARN sync panel script binding failed: {e}", flush=True)

    return {"status": "ok", "binding": binding_payload, "cleared": clear_binding}


# ---------------------------------------------------------------------------
# Static file serving (frontend)
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    _init_runs_from_disk()
    print(f"[workbench] output_dir={OUTPUT_DIR}")
    print(f"[workbench] ui_state_dir={UI_STATE_DIR}")
    print(f"[workbench] frontend_dir={FRONTEND_DIR}")
    print(f"[workbench] loaded {len(_runs)} runs from disk")


# Mount frontend static files LAST (catch-all)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Picslit2 Pipeline Workbench")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=7860, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    print(f"\n  Picslit2 Pipeline Workbench")
    print(f"  ➜  http://{args.host}:{args.port}/")
    print(f"  ➜  API: http://{args.host}:{args.port}/api/health\n")

    uvicorn.run(
        "scripts.run_react_workbench:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
