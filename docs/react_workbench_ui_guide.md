# React Workbench 使用指南（Picslit2）

## 1. 功能概览

当前工作台前端已覆盖：

- `#/runs`：Run 工作台（列表、筛选、跳转）
- `#/runs/new`：新建任务（上传/资产库选择 + 启动处理）
- `#/runs/:runId`：Run 结果页（纯净画面 / 文本列表 / 分镜列表）
- `#/studio/:runId`：Script Studio（三栏编辑器，绑定与脚本版本保存）
- `#/assets`：资产视图（PSD 主表 + Panel 子表 + 导出弹窗）
- `#/settings`：默认参数设置

说明：当前前端使用 **Hash 路由**，所以地址形态是 `#/runs`，不是 `/runs`。

## 2. 启动方式

说明（重要）：

- 当前已支持两种前端来源：
  - `web/react/dist`（Vite 构建产物，优先）
  - `web/react`（源码回退页，CDN + Babel）
- 后端静态服务会优先使用 **完整的** `web/react/dist`（必须包含 `/assets/*.js` bundle）
- 如果 `dist` 不完整，会自动回退到源码页（避免命中过期/半成品构建）

### 推荐（使用项目虚拟环境）

```bash
cd /Users/lishuai/Documents/python/Picslit2
.venv/bin/python scripts/run_react_workbench.py --host 127.0.0.1 --port 7860
```

打开浏览器：

- `http://127.0.0.1:7860/#/runs`

### 可选（使用 uv）

```bash
cd /Users/lishuai/Documents/python/Picslit2
uv run python scripts/run_react_workbench.py --host 127.0.0.1 --port 7860
```

如果 `7860` 被占用，换端口，例如 `7861`。

### 2.0 Vite 构建（推荐）

当前 Vite 前端源码结构：

- `/Users/lishuai/Documents/python/Picslit2/web/react/src/main.jsx`
- `/Users/lishuai/Documents/python/Picslit2/web/react/src/app.jsx`
- `/Users/lishuai/Documents/python/Picslit2/web/react/src/pages/*.jsx`
- `/Users/lishuai/Documents/python/Picslit2/web/react/index.vite.html`

构建配置：

- `/Users/lishuai/Documents/python/Picslit2/web/react/package.json`
- `/Users/lishuai/Documents/python/Picslit2/web/react/vite.config.js`

联网环境下可执行：

```bash
cd /Users/lishuai/Documents/python/Picslit2/web/react
npm install
npm run build
```

构建完成后会生成：

- `/Users/lishuai/Documents/python/Picslit2/web/react/dist`

说明：

- Vite 构建原始 HTML 输出为 `dist/index.vite.html`
- `npm run build` 中已包含 `postbuild`，会自动复制生成 `dist/index.html`
- 后端使用 `dist/index.html` 作为入口（因此必须使用 `npm run build`，不要只单独跑 `vite build`）

随后按上面的后端启动命令运行即可。后端会自动优先服务 `dist`。

## 2.1 一键冒烟检查（推荐先跑）

在启动前或改完前后端后，先跑一次应用级冒烟检查：

```bash
cd /Users/lishuai/Documents/python/Picslit2
uv run python scripts/smoke_react_workbench.py
```

会验证：

- 静态入口与 HTML 中引用的前端资源可访问（兼容源码模式 / dist 模式）
- 核心 API（runs/result/assets/export）可用
- 导出接口能返回下载链接

## 3. 使用流程（推荐顺序）

### A. 新建 Run

1. 打开 `#/runs`
2. 点击“新建任务”进入 `#/runs/new`
3. 选择输入源：
   - 上传 PSD/PSB
   - 或从资产库选择（会扫描 `out_dir`）
4. 设置 `Run ID / Prefix`（当前前端将 `prefix` 作为 `runId`）
5. 选择策略（普通/高级）
6. 点击“开始处理”

处理完成后会自动跳转到结果页。

### B. 查看结果

在 `#/runs/:runId`：

- `TabA 纯净画面`：查看/下载 clean image
- `TabB 全量文字列表`：可编辑内容、标签、备注（失焦后会写入后端 UI 状态）
- `TabC 分镜列表`：查看分镜并跳转到 Studio

### C. Studio 脚本编辑

在 `#/studio/:runId`：

- 左栏：分镜列表
- 中栏：当前分镜预览
- 右栏：
  - 全量文字池
  - 本镜文字篮（选择/排序/类型）
  - 脚本区（生成脚本、编辑草稿、保存版本）

关键按钮：

- “保存文字分配” -> `POST /api/bindings`
- “生成脚本” -> `POST /api/script/generate`
- “保存脚本版本” -> `POST /api/scripts`

### D. 资产视图与导出

在 `#/assets`：

- 主表展示按 `prefix(runId)` 聚合的 PSD 行
- 可展开 Panel 子表
- 备注列失焦会写入后端 note
- 导出弹窗调用 `POST /api/exports/excel`（当前服务端生成 CSV 文件并返回下载链接）

## 4. 数据与状态保存位置

### 核心产物（你原有逻辑生成）

默认输出目录：

- `/Users/lishuai/Documents/python/Picslit2/output`

典型文件：

- `*_pipeline_meta.json`
- `*_panels_manifest.json`
- `*_panel_text_manifest.json`
- `*_text_panel_unified_map.json`
- panel png / txt / script md/json

### UI 持久化状态（新增）

前端调用后端后会写入：

- `output/_ui_state/<runId>/run_meta.json`
- `output/_ui_state/<runId>/text_edits.json`
- `output/_ui_state/<runId>/bindings.json`
- `output/_ui_state/<runId>/scripts.json`

用途：

- 工作台 run 元信息补全
- 结果页文本编辑持久化
- Studio 文字分配与脚本版本持久化
- 资产页备注（写入 `run_meta.json` 的 `assetNote`）

### 浏览器本地缓存（localStorage）

前端仍保留部分本地缓存用于体验优化（例如 UI 草稿状态、展开态等）。

## 5. 常用 API（前端已接入）

- `GET /api/health`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{runId}`
- `GET /api/runs/{runId}/result`
- `PATCH /api/runs/{runId}/texts/{textId}`
- `GET /api/bindings`
- `POST /api/bindings`
- `GET /api/scripts`
- `POST /api/scripts`
- `POST /api/script/generate`
- `GET /api/assets/psd`
- `GET /api/assets/psd/{psdId}`
- `PATCH /api/assets/psd/{psdId}/note`
- `POST /api/exports/excel`
- `GET /api/file`

## 6. 已完成的运行验证（当前开发环境）

已验证：

- FastAPI `react_api` 单测通过（含 runs/bindings/scripts/assets/export）
- 应用级 `TestClient` 冒烟通过（兼容源码模式 / Vite dist 模式）：
  - `/`
  - HTML 中引用的静态资源（自动解析校验）
  - `/api/health`
  - `/api/runs`
  - `/api/assets/psd`
  - `/api/exports/excel`

说明：当前沙箱环境对本地端口绑定权限不稳定，导致无法稳定完成浏览器自动化（Playwright）端到端验证；在本机正常终端环境启动后可直接使用浏览器访问进行最终 UI 点测。

## 7. 常见问题排查

### 端口被占用

报错类似：`address already in use`

处理：

- 更换端口，例如 `--port 7861`

### 页面空白或控制台报 CDN 错误

当前 `web/react/index.html` 使用 CDN 加载 React / ReactDOM / Babel：

- `unpkg.com`

如果网络受限，会导致前端无法执行。

处理：

- 确保可访问 CDN
- 或使用已接入的 Vite 构建方案（见上文 `2.0 Vite 构建`）
- 构建完成后后端会优先使用 `web/react/dist`，可避免运行时依赖 CDN

### 历史 run 在结果页缺少完整文字/纯净图

原因：

- 历史产物可能只有 panel 文件，缺少统一映射或 clean image 路径

处理：

- 重新执行一次 run（新接口 `POST /api/runs`）
- 或补齐对应 manifest / meta 文件

## 8. 下一步建议（可选）

- 增加 `/api/exports/excel` 真正 xlsx 输出
- 将 `ScriptStudio` 脚本编辑器升级为结构化 `content` 编辑与 diff
- 加入 Playwright 本地 E2E 冒烟脚本（在可绑定端口的环境中执行）
