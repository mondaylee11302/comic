from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from typing import NoReturn

import uvicorn

from app.shared.config import APP_NAME, load_runtime_dotenv
from scripts.run_react_workbench import app


def _pick_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, timeout_sec: float = 25.0) -> bool:
    deadline = time.time() + max(1.0, float(timeout_sec))
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= int(resp.status) < 300:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.2)
    return False


def _show_error_and_exit(message: str) -> NoReturn:
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)
    raise SystemExit(1)


def _run_server(server: uvicorn.Server) -> None:
    server.run()


def main() -> None:
    load_runtime_dotenv()

    host = "127.0.0.1"
    port = _pick_free_port(host)
    base_url = f"http://{host}:{port}"
    health_url = f"{base_url}/api/health"

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    server_thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    server_thread.start()

    if not _wait_for_health(health_url):
        server.should_exit = True
        _show_error_and_exit("Picslit2 启动失败，未能在本地打开工作台服务。")

    try:
        import webview
    except Exception:
        webbrowser.open(base_url)
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            server_thread.join(timeout=5)
        return

    webview.create_window(APP_NAME, base_url, width=1440, height=960, min_size=(1100, 760))
    try:
        webview.start()
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
