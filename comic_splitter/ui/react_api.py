from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Mapping, Sequence
from uuid import uuid4

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from comic_splitter.script_agent import DEFAULT_DOUBAO_18_MM_MODEL
from comic_splitter.workflow import (
    AgentRetryMatrix,
    PanelScriptOptions,
    PanelScriptPaths,
    PanelScriptWorkflow,
    StoryboardOptions,
    StoryboardPaths,
    StoryboardWorkflow,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "output"
DEFAULT_DEBUG_DIR = DEFAULT_OUT_DIR / "debug"
DEFAULT_WEB_DIR = REPO_ROOT / "web" / "react"


@dataclass
class PanelInfo:
    panel_id: str
    image_path: str
    txt_path: str
    bbox: List[int]
    text_count: int


class StoryboardRunRequest(BaseModel):
    image_path: str
    prefix: str = "storyboard_001"
    out_dir: str = str(DEFAULT_OUT_DIR)
    debug_dir: str = str(DEFAULT_DEBUG_DIR)
    strict_ocr: bool = True
    ocr_mode: Literal["pdf", "multilang"] = "pdf"
    ocr_lang: Literal["zh", "ko"] = "zh"
    split_mode: Literal["bands", "stage2"] = "bands"
    reuse_cache: bool = True
    force_reprocess: bool = False
    heartbeat_sec: int = 8
    verbose: bool = True


class MultiLangOcrRequest(BaseModel):
    image_path: str
    ocr_lang: Literal["zh", "ko"] = "zh"
    max_retries: int = 2


class ScriptGenerateRequest(BaseModel):
    out_dir: str = str(DEFAULT_OUT_DIR)
    prefix: str
    panel_id: str
    panel_image_path: str | None = None
    panel_text_path: str | None = None
    selected_text_ids: List[str] = Field(default_factory=list)
    goal: str = "保留原文语义并增强戏剧性，输出可直接给创作团队使用的分镜脚本"
    temperature: float = 0.35
    max_tokens: int = 1200
    request_timeout_sec: float = 60.0
    model_retries: int = 2
    heartbeat_sec: int = 8
    allow_local_fallback: bool = True
    model_endpoint: str = DEFAULT_DOUBAO_18_MM_MODEL
    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    verbose: bool = True


def _safe_json_load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_jsonl_rows(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    out: List[Dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s:
            continue
        try:
            row = json.loads(s)
        except Exception:
            continue
        if isinstance(row, Mapping):
            out.append(dict(row))
    return out


def _norm_path(raw: str | Path) -> Path:
    return Path(str(raw)).expanduser().resolve()


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", base)
    return cleaned or "upload.psd"


def _list_prefixes(out_dir: Path) -> List[str]:
    prefixes: set[str] = set()
    for p in out_dir.glob("*_pipeline_meta.json"):
        prefixes.add(p.name[: -len("_pipeline_meta.json")])
    for p in out_dir.glob("*_panels_manifest.json"):
        prefixes.add(p.name[: -len("_panels_manifest.json")])
    return sorted(prefixes)


def _load_panel_infos(out_dir: Path, prefix: str) -> tuple[List[PanelInfo], Dict[str, PanelInfo]]:
    panel_manifest_path = out_dir / f"{prefix}_panels_manifest.json"
    text_manifest_path = out_dir / f"{prefix}_panel_text_manifest.json"
    if not panel_manifest_path.exists():
        return [], {}

    panel_manifest = _safe_json_load(panel_manifest_path)
    if not isinstance(panel_manifest, Mapping):
        return [], {}
    panels = panel_manifest.get("panels", [])
    if not isinstance(panels, Sequence):
        panels = []

    text_count_map: Dict[str, int] = {}
    if text_manifest_path.exists():
        obj = _safe_json_load(text_manifest_path)
        if isinstance(obj, Sequence):
            for row in obj:
                if isinstance(row, Mapping):
                    pid = str(row.get("panel_id", "")).strip()
                    text_count_map[pid] = int(row.get("text_count", 0))

    infos: List[PanelInfo] = []
    for p in panels:
        if not isinstance(p, Mapping):
            continue
        panel_id = str(p.get("panel_id", "")).strip()
        if not panel_id:
            continue
        image_path = str(p.get("bbox_path", "")).strip()
        txt_path = str(p.get("txt_path", "")).strip()
        bbox_raw = p.get("bbox", [0, 0, 0, 0])
        if not isinstance(bbox_raw, Sequence):
            bbox_raw = [0, 0, 0, 0]
        bbox = [int(v) for v in list(bbox_raw)[:4]]
        while len(bbox) < 4:
            bbox.append(0)
        infos.append(
            PanelInfo(
                panel_id=panel_id,
                image_path=image_path,
                txt_path=txt_path,
                bbox=bbox,
                text_count=int(text_count_map.get(panel_id, 0)),
            )
        )
    return infos, {x.panel_id: x for x in infos}


def _load_unified_preview(out_dir: Path, prefix: str, limit: int = 200) -> List[Dict[str, str]]:
    path = out_dir / f"{prefix}_text_panel_unified_map.json"
    if not path.exists():
        return []
    payload = _safe_json_load(path)
    if not isinstance(payload, Mapping):
        return []
    items = payload.get("items", [])
    if not isinstance(items, Sequence):
        return []
    out: List[Dict[str, str]] = []
    for item in items[: max(0, int(limit))]:
        if not isinstance(item, Mapping):
            continue
        out.append(
            {
                "text_id": str(item.get("text_id", "")),
                "text": str(item.get("text", "")),
                "panel_id": str(item.get("primary_panel_id") or ""),
                "canvas_bbox": str(item.get("canvas_bbox", "")),
                "status": str(item.get("status", "")),
            }
        )
    return out


def _fmt_size(path: Path) -> str:
    size = float(path.stat().st_size)
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    return f"{size:.1f}{units[idx]}"


def _fmt_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def _build_psd_preview(psd_path: Path, out_dir: Path) -> Path | None:
    try:
        from psd_tools import PSDImage

        preview_dir = out_dir / "uploads" / "previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = preview_dir / f"{psd_path.stem}_{uuid4().hex[:8]}.png"
        psd = PSDImage.open(str(psd_path))
        comp = psd.composite()
        comp.save(str(preview_path))
        return preview_path
    except Exception:
        return None


def create_react_workbench_app(
    *,
    static_dir: Path | None = None,
    default_out_dir: Path | None = None,
    default_debug_dir: Path | None = None,
) -> FastAPI:
    out_default = _norm_path(default_out_dir or DEFAULT_OUT_DIR)
    debug_default = _norm_path(default_debug_dir or DEFAULT_DEBUG_DIR)
    web_dir = _norm_path(static_dir or DEFAULT_WEB_DIR)

    app = FastAPI(title="Storyboard React Workbench API")
    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health() -> Dict[str, bool]:
        return {"ok": True}

    @api.post("/upload-psd")
    async def upload_psd(
        file: UploadFile = File(...),
        out_dir: str = Form(str(out_default)),
    ) -> Dict:
        filename = _safe_filename(file.filename or "upload.psd")
        ext = Path(filename).suffix.lower()
        if ext not in {".psd", ".psb"}:
            raise HTTPException(status_code=400, detail="only .psd/.psb files are supported")
        base_out = _norm_path(out_dir)
        upload_dir = base_out / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}_{filename}"

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="empty upload file")
        path.write_bytes(content)

        preview_path = _build_psd_preview(path, base_out)
        return {
            "ok": True,
            "file_name": filename,
            "stored_path": str(path),
            "preview_path": str(preview_path) if preview_path else "",
            "size_bytes": len(content),
        }

    @api.post("/storyboard/run")
    def run_storyboard(payload: StoryboardRunRequest) -> Dict:
        logs: List[str] = []

        def _log(msg: str) -> None:
            line = str(msg)
            if payload.verbose:
                logs.append(line)
            print(f"[storyboard] {line}", flush=True)

        image_path = _norm_path(payload.image_path)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail=f"image not found: {image_path}")
        if image_path.suffix.lower() not in {".psd", ".psb"}:
            raise HTTPException(status_code=400, detail="storyboard only supports .psd/.psb")

        out_dir = _norm_path(payload.out_dir)
        debug_dir = _norm_path(payload.debug_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        debug_dir.mkdir(parents=True, exist_ok=True)
        prefix = str(payload.prefix).strip() or image_path.stem

        paths = StoryboardPaths(
            image_path=image_path,
            out_dir=out_dir,
            debug_dir=debug_dir,
            prefix=prefix,
        )
        options = StoryboardOptions(
            strict_ocr=bool(payload.strict_ocr),
            ocr_mode=str(payload.ocr_mode),
            ocr_lang=str(payload.ocr_lang),
            reuse_preprocess_cache=bool(payload.reuse_cache),
            force_reprocess=bool(payload.force_reprocess),
            split_mode=payload.split_mode,
            heartbeat_interval_sec=max(3, int(payload.heartbeat_sec)),
        )
        workflow = StoryboardWorkflow(
            paths=paths,
            options=options,
            log=_log,
            retry_matrix=AgentRetryMatrix(),
        )
        print(
            f"[storyboard] start image={image_path} prefix={prefix} out_dir={out_dir} "
            f"strict_ocr={bool(payload.strict_ocr)} ocr_mode={payload.ocr_mode} ocr_lang={payload.ocr_lang} "
            f"split_mode={payload.split_mode}",
            flush=True,
        )
        try:
            state = workflow.run()
        except Exception as exc:
            # Return a readable API error instead of raw 500 traceback.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        print(f"[storyboard] done prefix={prefix} text_count={len(state.texts_payload)}", flush=True)

        panels, _ = _load_panel_infos(out_dir, prefix)
        unified_preview = _load_unified_preview(out_dir, prefix)
        clean_path = str(state.preprocess_meta.get("art_clean_path", "")).strip()

        return {
            "ok": True,
            "prefix": prefix,
            "out_dir": str(out_dir),
            "debug_dir": str(debug_dir),
            "clean_image_path": clean_path if clean_path and Path(clean_path).exists() else "",
            "panel_count": len(panels),
            "panels": [asdict(p) for p in panels],
            "unified_preview": unified_preview,
            "text_count": len(state.texts_payload),
            "logs": logs[-120:],
        }

    @api.post("/ocr/multilang")
    def ocr_multilang(payload: MultiLangOcrRequest) -> Dict:
        image_path = _norm_path(payload.image_path)
        if not image_path.exists() or not image_path.is_file():
            raise HTTPException(status_code=404, detail=f"image not found: {image_path}")
        raw = image_path.read_bytes()
        if not raw:
            raise HTTPException(status_code=400, detail="empty image file")
        file_type = 0 if image_path.suffix.lower() == ".pdf" else 1
        try:
            from volc_imagex.ocr import ocr_ai_process_bytes

            res = ocr_ai_process_bytes(
                file_bytes=raw,
                scene="general",
                file_type=file_type,
                max_retries=max(1, int(payload.max_retries)),
                ocr_endpoint="multilang",
                lang_mode=str(payload.ocr_lang),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        rows = [
            {
                "text": str(t.text),
                "quad": [[float(p[0]), float(p[1])] for p in t.quad],
                "confidence": float(t.confidence) if t.confidence is not None else None,
            }
            for t in res.texts
        ]
        return {
            "ok": True,
            "request_id": res.request_id,
            "elapsed_ms": int(res.elapsed_ms),
            "ocr_lang": str(payload.ocr_lang),
            "text_count": len(rows),
            "texts": rows,
            "raw_output": res.raw_output,
        }

    @api.get("/panel/details")
    def panel_details(
        out_dir: str = Query(str(out_default)),
        prefix: str = Query(...),
        panel_id: str = Query(...),
    ) -> Dict:
        out = _norm_path(out_dir)
        _, panel_map = _load_panel_infos(out, prefix)
        info = panel_map.get(panel_id)
        if info is None:
            raise HTTPException(status_code=404, detail=f"panel not found: {panel_id}")
        rows = _safe_jsonl_rows(Path(info.txt_path)) if info.txt_path else []
        return {
            "ok": True,
            "panel": asdict(info),
            "texts": rows,
        }

    @api.post("/script/generate")
    def script_generate(payload: ScriptGenerateRequest) -> Dict:
        logs: List[str] = []

        def _log(msg: str) -> None:
            if payload.verbose:
                logs.append(str(msg))

        out_dir = _norm_path(payload.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        panel_image_path = Path(payload.panel_image_path).expanduser() if payload.panel_image_path else None
        panel_text_path = Path(payload.panel_text_path).expanduser() if payload.panel_text_path else None
        if panel_image_path is not None and not panel_image_path.exists():
            raise HTTPException(status_code=404, detail=f"panel image not found: {panel_image_path}")
        if panel_text_path is not None and not panel_text_path.exists():
            raise HTTPException(status_code=404, detail=f"panel text not found: {panel_text_path}")

        paths = PanelScriptPaths(
            out_dir=out_dir,
            prefix=str(payload.prefix).strip(),
            panel_id=str(payload.panel_id).strip(),
            panel_image_path=panel_image_path,
            panel_text_path=panel_text_path,
            output_json_path=None,
            output_md_path=None,
        )
        options = PanelScriptOptions(
            selected_text_ids=[x for x in payload.selected_text_ids if str(x).strip()],
            selected_text_contains=[],
            goal=str(payload.goal).strip() or "保留原文语义并增强戏剧性，输出可直接给创作团队使用的分镜脚本",
            temperature=float(payload.temperature),
            max_tokens=max(128, int(payload.max_tokens)),
            request_timeout_sec=max(5.0, float(payload.request_timeout_sec)),
            model_retries=max(1, int(payload.model_retries)),
            heartbeat_interval_sec=max(3, int(payload.heartbeat_sec)),
            allow_local_fallback=bool(payload.allow_local_fallback),
            enforce_doubao_18=True,
            model_endpoint=str(payload.model_endpoint).strip(),
            api_key=str(payload.api_key).strip(),
            base_url=str(payload.base_url).strip(),
        )

        wf = PanelScriptWorkflow(paths=paths, options=options, log=_log if payload.verbose else (lambda _msg: None), retry_matrix=AgentRetryMatrix())
        state = wf.run()

        result = dict(state.script_result)
        script_json_path = ""
        script_md_path = ""
        if state.panel_image_path is not None:
            script_json_path = str(state.panel_image_path.with_name(f"{state.panel_image_path.stem}_script.json"))
            script_md_path = str(state.panel_image_path.with_name(f"{state.panel_image_path.stem}_script.md"))
        return {
            "ok": True,
            "panel_id": payload.panel_id,
            "selected_text_count": len(options.selected_text_ids),
            "script": result,
            "script_markdown": str(result.get("script_markdown", "")),
            "backend": str(result.get("meta", {}).get("backend", "unknown")),
            "script_json_path": script_json_path,
            "script_md_path": script_md_path,
            "logs": logs[-120:],
        }

    @api.get("/assets/list")
    def assets_list(
        out_dir: str = Query(str(out_default)),
        prefix_filter: str = Query(""),
        keyword: str = Query(""),
        asset_type: Literal["all", "psd", "frame", "text", "script"] = Query("all"),
    ) -> Dict:
        root = _norm_path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
        prefixes = _list_prefixes(root)
        pf = str(prefix_filter).strip()
        if pf:
            prefixes = [p for p in prefixes if pf in p]

        items: List[Dict[str, str]] = []
        gallery: List[Dict[str, str]] = []
        script_paths: List[str] = []
        counts = {"psd": 0, "frame": 0, "text": 0, "script": 0}

        for prefix in prefixes:
            pipeline_meta_path = root / f"{prefix}_pipeline_meta.json"
            if pipeline_meta_path.exists():
                meta = _safe_json_load(pipeline_meta_path)
                if isinstance(meta, Mapping):
                    src = str(meta.get("image", "")).strip()
                    if src and Path(src).exists():
                        src_path = Path(src)
                        items.append(
                            {
                                "type": "psd",
                                "prefix": prefix,
                                "name": src_path.name,
                                "path": str(src_path),
                                "size": _fmt_size(src_path),
                                "mtime": _fmt_mtime(src_path),
                            }
                        )
                        counts["psd"] += 1

            panels, _ = _load_panel_infos(root, prefix)
            for panel in panels:
                image_path = Path(panel.image_path)
                txt_path = Path(panel.txt_path)
                if image_path.exists():
                    items.append(
                        {
                            "type": "frame",
                            "prefix": prefix,
                            "name": image_path.name,
                            "path": str(image_path),
                            "size": _fmt_size(image_path),
                            "mtime": _fmt_mtime(image_path),
                        }
                    )
                    counts["frame"] += 1
                    if len(gallery) < 40:
                        gallery.append(
                            {
                                "path": str(image_path),
                                "label": f"{prefix}/{panel.panel_id}",
                            }
                        )
                if txt_path.exists():
                    items.append(
                        {
                            "type": "text",
                            "prefix": prefix,
                            "name": txt_path.name,
                            "path": str(txt_path),
                            "size": _fmt_size(txt_path),
                            "mtime": _fmt_mtime(txt_path),
                        }
                    )
                    counts["text"] += 1

                for ext in ("json", "md"):
                    sp = image_path.with_name(f"{image_path.stem}_script.{ext}")
                    if sp.exists():
                        items.append(
                            {
                                "type": "script",
                                "prefix": prefix,
                                "name": sp.name,
                                "path": str(sp),
                                "size": _fmt_size(sp),
                                "mtime": _fmt_mtime(sp),
                            }
                        )
                        counts["script"] += 1
                        if sp.suffix == ".md":
                            script_paths.append(str(sp))

        q = str(keyword).strip().lower()
        if q:
            items = [r for r in items if q in " ".join(r.values()).lower()]
        if asset_type != "all":
            items = [r for r in items if r["type"] == asset_type]

        script_paths = sorted(set(script_paths))
        return {
            "ok": True,
            "counts": counts,
            "prefix_count": len(prefixes),
            "items": items,
            "gallery": gallery,
            "script_paths": script_paths,
        }

    @api.get("/script/preview")
    def script_preview(path: str = Query(...)) -> Dict[str, str | bool]:
        p = _norm_path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail=f"file not found: {p}")
        return {"ok": True, "content": p.read_text(encoding="utf-8")}

    @api.get("/file")
    def file_proxy(path: str = Query(...)) -> FileResponse:
        p = _norm_path(path)
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail=f"file not found: {p}")
        media_type, _ = mimetypes.guess_type(str(p))
        return FileResponse(str(p), media_type=media_type)

    app.include_router(api)

    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="react-web")
    else:
        @app.get("/")
        def root() -> PlainTextResponse:
            return PlainTextResponse(f"React static dir not found: {web_dir}")

    return app
