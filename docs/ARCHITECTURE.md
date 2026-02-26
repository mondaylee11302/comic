# Architecture

## 1. Current State

### Frontend

- 当前前端技术栈是 `Vite + 原生 JavaScript (ESM)`，不是 React/Vue/Next。
- 前端入口仍是 `frontend/index.html` + `frontend/main.js`。
- UI 渲染、状态管理、页面切换、API 请求封装（`fetch`）高度集中在 `frontend/main.js`。
- 前端当前是单文件主控模式，功能上已覆盖“漫画分镜智能体”工作台（拆分/任务/Studio/资产等）。

### Backend

- 当前后端技术栈是 `FastAPI + Uvicorn`。
- 后端入口与主要 API 路由集中在单文件 `scripts/run_react_workbench.py`。
- 该文件同时承担：
  - FastAPI app 创建
  - 大部分 API 路由定义
  - 运行任务状态管理
  - 文件读写与结果聚合
  - 前端静态资源挂载
  - 启动 CLI（`uvicorn.run(...)`）

### Business Logic

- 分镜相关核心逻辑主要位于以下目录/模块：
  - `comic_splitter/workflow/*`
  - `comic_splitter/script_agent.py`
  - `comic_splitter/stage1/*`
  - `comic_splitter/stage2/*`
- 配置主要在：
  - `config/storyboard.toml`
  - `config/panel_script.toml`

### State & Persistence

- 当前系统主要使用文件持久化与内存态，不是数据库驱动架构。
- 典型状态/产物落盘位置：
  - `output/_ui_state/*`
  - `output/*_pipeline_meta.json`
  - `output/*_panels_manifest.json`
  - `output/*_text_panel_unified_map.json`
- 服务运行期状态也保存在后端进程内（如内存中的 run registry、线程、取消事件等）。

## 2. Current Risks

- 前端单文件过大：`frontend/main.js` 同时承载视图、状态、请求、交互逻辑，维护成本高。
- 后端单文件路由过多：`scripts/run_react_workbench.py` 既是入口又是业务聚合点，修改风险集中。
- API、状态、视图耦合：前后端都存在“功能新增即继续堆叠”的趋势，边界不清晰。
- 没有明确的 agent 边界：当前“分镜智能体”相关逻辑虽能运行，但未形成清晰模块边界。
- 后续新增“编导智能体”容易把逻辑继续堆在一起：若沿用当前模式，前后端都可能进一步膨胀为更大的单文件/弱边界结构。

## 3. Target Architecture

目标架构以“贴合当前仓库、可渐进迁移”为原则，不做一次性重写。

### Frontend Target Structure

- `frontend/main.js` 先保留为入口（不立即废弃）。
- 后续逐步拆分为以下结构（渐进迁移，不要求一步到位）：
  - `frontend/src/app/`
  - `frontend/src/shared/`
  - `frontend/src/agents/storyboard/`
  - `frontend/src/agents/director/`

#### Frontend Layer Intent

- `frontend/main.js`
  - 过渡期入口文件
  - 逐步改为仅负责初始化与挂载
- `frontend/src/app/`
  - 应用级装配（页面框架、导航、启动流程、顶层状态组织）
- `frontend/src/shared/`
  - 与 agent 无关的通用能力（请求封装、通用 UI 工具、基础模型/常量）
- `frontend/src/agents/storyboard/`
  - “动漫分镜智能体”前端页面、状态、交互、API 调用适配
- `frontend/src/agents/director/`
  - “编导智能体”前端页面、状态、交互、API 调用适配

### Backend Target Structure

- 保留 `scripts/run_react_workbench.py` 作为启动入口（兼容现有命令与运行方式）。
- 后续逐步拆分为以下结构（渐进迁移）：
  - `app/shared/`
  - `app/agents/storyboard/`
  - `app/agents/director/`

#### Backend Layer Intent

- `scripts/run_react_workbench.py`（最终职责收敛）
  - 创建 FastAPI app
  - 注册路由
  - 挂静态资源
  - 启动服务
- `app/shared/`
  - 通用基础能力与跨 agent 公共模块
- `app/agents/storyboard/`
  - “动漫分镜智能体”后端路由、服务编排、DTO/校验、文件组织逻辑（与分镜业务相关）
- `app/agents/director/`
  - “编导智能体”后端路由、服务编排、DTO/校验、文件组织逻辑（与编导业务相关）

### Future Coexistence: Storyboard Agent + Director Agent

- “动漫分镜智能体”和“编导智能体”应作为并列 agent 存在，而不是主从嵌套关系。
- 前端表现为并列模块目录（`agents/storyboard` 与 `agents/director`）。
- 后端表现为并列模块目录（`app/agents/storyboard` 与 `app/agents/director`）。
- 两者共享基础设施，但业务流程、状态模型、接口语义保持独立演进。

## 4. Boundary Rules

### Core Boundary Rules

- `storyboard` 与 `director` 必须逻辑独立。
- 两者不能直接 `import` 对方代码。
- 两者只能依赖 `shared` 层。

### What Can Be Shared (shared)

- `config`
- `logging`
- `validator`
- 通用文件读写 / 工具函数
- 通用响应模型（如果后面需要）

### What Must Stay Independent (agent-specific)

- 各自的业务流程编排
- 各自的 API 路由与请求/响应语义
- 各自的页面状态与交互状态机
- 各自的领域模型（除非被明确抽象为通用模型）
- 各自的任务执行与结果组装逻辑

### Practical Rule for Migration Period

- 迁移期允许 `scripts/run_react_workbench.py` 暂时同时引用旧模块和新模块。
- 但新增功能应优先落在目标目录（`app/shared` / `app/agents/*`、`frontend/src/*`）而不是继续扩写原单文件。

## 5. Refactor Strategy

以下顺序要求“小步、可运行、可回退”，避免大爆炸式改造：

1. 写架构文档
2. 创建新目录骨架
3. 抽 `shared`（先 `config/logging/validator`）
4. 把 `storyboard` 的前端页面搬到 `agents/storyboard`
5. 把 `storyboard` 的后端路由/服务搬到 `app/agents/storyboard`
6. 新增 `director` 空壳模块
7. 再开始 `director` 的 Step0/Step1 功能开发

### Migration Notes

- 每一步都应保持现有启动命令不变。
- 每一步都应优先保证“分镜智能体”现有功能不回归。
- 优先做“搬迁 + 封装”而不是“算法重写”。

## 6. Non-Goals

当前这轮整理明确不做以下事项：

- 不改算法逻辑
- 不改分镜功能
- 不引入数据库
- 不重写前端框架
- 不一次性 TypeScript 化
- 不一次性拆完所有文件
