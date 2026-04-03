# Picslit2

Picslit2 是一个漫画分镜/文本处理工作台项目，后端基于 FastAPI，前端位于 `frontend/`。

## 目录说明

- `app/`: 后端业务模块
- `comic_splitter/`: 漫画处理流水线核心逻辑
- `scripts/`: 启动与工具脚本
- `frontend/`: 前端静态资源与开发工程
- `output/`: 运行产物
- `doc/`: 项目文档目录

## 环境要求

- Python `>=3.12`
- Node.js `>=18`（仅前端独立开发时需要）

## 如何启动项目

### 1. 安装 Python 依赖

在项目根目录执行：

```bash
# 方式 A：使用 uv（推荐）
uv sync

# 方式 B：使用 pip
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install fastapi uvicorn python-dotenv numpy opencv-python psd-tools python-multipart requests scikit-image "volcengine-python-sdk[ark]"
```

### 2. 启动 FastAPI 工作台（推荐方式）

```bash
python scripts/run_react_workbench.py --host 127.0.0.1 --port 7860
```

启动后访问：

- 页面地址: `http://127.0.0.1:7860/`
- 健康检查: `http://127.0.0.1:7860/api/health`

### 3. 可选：开启自动重载（开发调试）

```bash
python scripts/run_react_workbench.py --host 127.0.0.1 --port 7860 --reload
```

## 前端单独开发（可选）

如果你需要单独调试前端（Vite）：

```bash
cd frontend
npm install
npm run dev
```

前端打包命令：

```bash
cd frontend
npm run build
npm run preview
```

## 常见问题

- 端口被占用：修改 `--port` 参数，例如 `--port 7870`
- 模块找不到：确认在项目根目录执行命令，且虚拟环境已激活

## 打包为 Windows 桌面应用

项目已经提供了桌面启动入口 `scripts/picslit_desktop.py`，它会在本机启动 FastAPI 工作台，并以内嵌窗口形式打开界面。适合打包成给最终用户双击启动的 `.exe`。

注意：

- `exe` 需要在 Windows 环境构建，不能在 macOS 直接产出 Windows 可执行文件
- 打包后的运行数据会写到用户目录，而不是安装目录
- `frontend/` 和 `config/` 会作为只读资源一起打包
- 如需配置 API Key，可将 `.env` 放到 `%LOCALAPPDATA%\Picslit2\.env`

### Windows 构建步骤

在 Windows 机器或 Windows CI 中执行：

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -U pip
pip install pyinstaller pywebview
pip install fastapi uvicorn python-dotenv numpy opencv-python psd-tools python-multipart requests scikit-image "volcengine-python-sdk[ark]"
python scripts/build_windows_app.py
```

构建完成后，可执行文件位于：

```text
dist/Picslit2/Picslit2.exe
```

用户只需要双击 `Picslit2.exe` 即可启动本地应用。

如果需要分发给外部用户，建议继续加一层安装器（例如 Inno Setup），把整个 `dist/Picslit2/` 目录封装成安装包。
