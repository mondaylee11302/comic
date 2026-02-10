from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from comic_splitter.script_agent import (
    DEFAULT_DOUBAO_18_MM_MODEL,
    ScriptAgentConfig,
    generate_panel_script,
    read_panel_text_jsonl,
    select_text_rows,
)
from comic_splitter.workflow.runtime import AgentRetryMatrix, run_agents_with_retry


@dataclass
class PanelScriptPaths:
    out_dir: Path
    prefix: str
    panel_id: str
    panel_image_path: Path | None = None
    panel_text_path: Path | None = None
    output_json_path: Path | None = None
    output_md_path: Path | None = None


@dataclass
class PanelScriptOptions:
    selected_text_ids: List[str] = field(default_factory=list)
    selected_text_contains: List[str] = field(default_factory=list)
    goal: str = "保留原文语义并增强戏剧性，输出可直接给创作团队使用的分镜脚本"
    temperature: float = 0.35
    max_tokens: int = 1200
    request_timeout_sec: float = 60.0
    model_retries: int = 2
    heartbeat_interval_sec: int = 8
    allow_local_fallback: bool = True
    enforce_doubao_18: bool = True
    model_endpoint: str = ""
    api_key: str = ""
    base_url: str = ""


@dataclass
class PanelScriptState:
    panel_image_path: Path | None = None
    panel_text_path: Path | None = None
    all_rows: List[Dict] = field(default_factory=list)
    selected_rows: List[Dict] = field(default_factory=list)
    script_result: Dict = field(default_factory=dict)


@dataclass
class PanelScriptContext:
    paths: PanelScriptPaths
    options: PanelScriptOptions
    state: PanelScriptState
    log: Callable[[str], None]


class PanelScriptAgent:
    name = "panel_script_agent"

    def run(self, ctx: PanelScriptContext) -> None:
        raise NotImplementedError


class ResolvePanelAgent(PanelScriptAgent):
    name = "resolve_panel_agent"

    def run(self, ctx: PanelScriptContext) -> None:
        if ctx.paths.panel_image_path and ctx.paths.panel_text_path:
            ctx.state.panel_image_path = ctx.paths.panel_image_path.expanduser()
            ctx.state.panel_text_path = ctx.paths.panel_text_path.expanduser()
            return

        manifest_path = ctx.paths.out_dir / f"{ctx.paths.prefix}_panels_manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"panels manifest not found: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        panels = payload.get("panels", []) if isinstance(payload, dict) else []
        for p in panels:
            if str(p.get("panel_id")) == str(ctx.paths.panel_id):
                img = Path(str(p.get("bbox_path", ""))).expanduser()
                txt = Path(str(p.get("txt_path", ""))).expanduser()
                if img.exists() and txt.exists():
                    ctx.state.panel_image_path = img
                    ctx.state.panel_text_path = txt
                    return
                break
        raise FileNotFoundError(
            f"failed to resolve panel files for panel_id={ctx.paths.panel_id}; "
            "you may pass explicit panel_image_path/panel_text_path"
        )


class SelectTextAgent(PanelScriptAgent):
    name = "select_text_agent"

    def run(self, ctx: PanelScriptContext) -> None:
        if ctx.state.panel_text_path is None:
            raise RuntimeError("select_text_agent requires resolved panel_text_path")
        ctx.state.all_rows = read_panel_text_jsonl(ctx.state.panel_text_path)
        ctx.state.selected_rows = select_text_rows(
            all_rows=ctx.state.all_rows,
            selected_text_ids=ctx.options.selected_text_ids,
            selected_texts=ctx.options.selected_text_contains,
        )
        if not ctx.state.selected_rows:
            raise ValueError("no selected texts after filtering")
        ctx.log(f"selected_text_count={len(ctx.state.selected_rows)}")


class GenerateScriptAgent(PanelScriptAgent):
    name = "generate_script_agent"

    def run(self, ctx: PanelScriptContext) -> None:
        if ctx.state.panel_image_path is None:
            raise RuntimeError("generate_script_agent requires resolved panel_image_path")
        model_endpoint = (ctx.options.model_endpoint or os.getenv("SCRIPT_AGENT_MODEL", "").strip() or DEFAULT_DOUBAO_18_MM_MODEL)
        api_key = (ctx.options.api_key or os.getenv("SCRIPT_AGENT_API_KEY", "").strip() or os.getenv("VOLC_API_KEY", "").strip())
        base_url = (ctx.options.base_url or os.getenv("SCRIPT_AGENT_BASE_URL", "").strip() or os.getenv("VOLC_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3").strip()).rstrip("/")
        for suffix in ("/embeddings/multimodal", "/chat/completions", "/v1/chat/completions"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break
        cfg = ScriptAgentConfig(
            api_key=api_key,
            model_endpoint=model_endpoint,
            base_url=base_url,
            temperature=float(ctx.options.temperature),
            max_tokens=int(ctx.options.max_tokens),
            allow_local_fallback=bool(ctx.options.allow_local_fallback),
            enforce_doubao_18=bool(ctx.options.enforce_doubao_18),
            request_timeout_sec=float(ctx.options.request_timeout_sec),
            model_retries=max(1, int(ctx.options.model_retries)),
            heartbeat_interval_sec=max(3, int(ctx.options.heartbeat_interval_sec)),
        )
        ctx.log(f"model={model_endpoint}")
        ctx.log(f"base_url={base_url}")
        ctx.state.script_result = generate_panel_script(
            panel_image_path=str(ctx.state.panel_image_path),
            selected_rows=ctx.state.selected_rows,
            user_goal=ctx.options.goal,
            cfg=cfg,
            verbose_hook=lambda msg: ctx.log(msg),
        )


class PersistScriptAgent(PanelScriptAgent):
    name = "persist_script_agent"

    def run(self, ctx: PanelScriptContext) -> None:
        if ctx.state.panel_image_path is None or ctx.state.panel_text_path is None:
            raise RuntimeError("persist_script_agent requires resolved panel paths")
        if not ctx.state.script_result:
            raise RuntimeError("persist_script_agent requires generated script_result")

        out_json = ctx.paths.output_json_path or ctx.state.panel_image_path.with_name(f"{ctx.state.panel_image_path.stem}_script.json")
        out_md = ctx.paths.output_md_path or ctx.state.panel_image_path.with_name(f"{ctx.state.panel_image_path.stem}_script.md")

        payload: Dict = {
            "panel_id": ctx.paths.panel_id,
            "panel_image_path": str(ctx.state.panel_image_path),
            "panel_text_path": str(ctx.state.panel_text_path),
            "selected_text_ids": [str(r.get("text_id", "")) for r in ctx.state.selected_rows],
            "selected_text_count": len(ctx.state.selected_rows),
            "goal": str(ctx.options.goal),
            "script": ctx.state.script_result,
        }
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        md = str(ctx.state.script_result.get("script_markdown", "")).strip()
        if not md:
            md = (
                f"# {ctx.paths.panel_id} 分镜脚本\n\n"
                f"- panel_image: {ctx.state.panel_image_path}\n"
                f"- selected_text_count: {len(ctx.state.selected_rows)}\n\n"
                "```json\n"
                f"{json.dumps(ctx.state.script_result, ensure_ascii=False, indent=2)}\n"
                "```\n"
            )
        out_md.write_text(md, encoding="utf-8")
        print(f"panel_image: {ctx.state.panel_image_path}")
        print(f"panel_text: {ctx.state.panel_text_path}")
        print(f"selected_text_count: {len(ctx.state.selected_rows)}")
        print(f"script_json: {out_json}")
        print(f"script_md: {out_md}")
        print(f"backend: {ctx.state.script_result.get('meta', {}).get('backend', 'unknown')}")
        if ctx.state.script_result.get("meta", {}).get("backend") == "local_fallback":
            print(f"fallback_reason: {ctx.state.script_result.get('meta', {}).get('fallback_reason', '')}")


class PanelScriptWorkflow:
    def __init__(
        self,
        paths: PanelScriptPaths,
        options: PanelScriptOptions,
        log: Callable[[str], None],
        retry_matrix: AgentRetryMatrix | None = None,
    ) -> None:
        self.ctx = PanelScriptContext(paths=paths, options=options, state=PanelScriptState(), log=log)
        self.agents: List[PanelScriptAgent] = [
            ResolvePanelAgent(),
            SelectTextAgent(),
            GenerateScriptAgent(),
            PersistScriptAgent(),
        ]
        self.retry_matrix = retry_matrix or AgentRetryMatrix()

    def run(self) -> PanelScriptState:
        run_agents_with_retry(
            agents=self.agents,
            run_one=lambda a: a.run(self.ctx),
            log=self.ctx.log,
            retry=self.retry_matrix,
        )
        return self.ctx.state
