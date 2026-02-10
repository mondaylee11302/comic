# Multi-Agent Workflow Architecture

This project now keeps business logic unchanged while reorganizing orchestration into explicit agents.

## 1) Storyboard Pipeline

Entry: `/Users/lishuai/Documents/python/Picslit2/scripts/run_storyboard_job.py`
Config: `/Users/lishuai/Documents/python/Picslit2/config/storyboard.toml`

Workflow class: `comic_splitter.workflow.StoryboardWorkflow`

Agents (execution order):

1. `preprocess_agent`
   - PSD preprocess
   - OCR/text extraction merge
   - clean art generation
   - preprocess cache load/save
2. `split_agent`
   - stage1 split
   - optional stage2 graph-rag split
   - panel crop export
3. `text_packaging_agent`
   - text-panel mapping v1/v2
   - unified mapping output
   - panel txt output
   - manifests/meta output

## 2) Panel Script Pipeline

Entry: `/Users/lishuai/Documents/python/Picslit2/scripts/run_panel_script_agent.py`
Config: `/Users/lishuai/Documents/python/Picslit2/config/panel_script.toml`

Workflow class: `comic_splitter.workflow.PanelScriptWorkflow`

Agents (execution order):

1. `resolve_panel_agent`
2. `select_text_agent`
3. `generate_script_agent`
4. `persist_script_agent`

Model requirement: Doubao 1.8 multimodal (enforced in code).

## 3) Design Rules

- Orchestration and state flow live in `comic_splitter/workflow/`.
- Core algorithm modules remain unchanged:
  - `comic_splitter/psd_preprocess.py`
  - `comic_splitter/stage1/*`
  - `comic_splitter/stage2/*`
  - `comic_splitter/script_agent.py`
- Script files in `/scripts` are thin adapters only (config + workflow call).
- Existing output file names and formats remain compatible.

## 4) Retry Matrix

Both workflows support agent-level retry matrix in TOML:

- `[retry]` global defaults
  - `enabled`
  - `default_max_attempts`
  - `default_backoff_sec`
  - `backoff_multiplier`
  - `max_backoff_sec`
- `[retry.per_agent_max_attempts]` per-agent override

Non-retryable errors are treated as immediate fail-fast:

- `ValueError`
- `FileNotFoundError`
- `PermissionError`
- `NotImplementedError`

## 5) Config Priority

Runtime priority is:

1. hardcoded defaults (script)
2. TOML config
3. CLI explicit arguments (highest)
