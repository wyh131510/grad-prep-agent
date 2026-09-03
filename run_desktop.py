# -*- coding: utf-8 -*-
"""桌面模式入口：启动本地服务，用原生窗口展示（无浏览器地址栏）。
- 直接运行：python run_desktop.py（需要 pip install pywebview）
- 打包后：GradPrepAgent.exe（PyInstaller onedir 产物，安装程序由 Inno Setup 生成）

注意：exe 以 --noconsole 打包时 sys.stdout/stderr 为 None，
uvicorn 默认日志配置会因 stderr.isatty() 崩溃 —— 因此必须传 log_config=None，
并把所有日志与 print 落到文件/加空指针防护。
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _safe_print(text: str) -> None:
    try:
        if sys.stdout is not None:
            print(text)
    except Exception:  # noqa: BLE001
        pass


def _setup_logging() -> None:
    """日志全部落文件（无控制台环境下 stderr 为 None，不能依赖控制台）。"""
    try:
        import logging

        from app.config import DATA_DIR
        from app.utils import ensure_dir

        ensure_dir(DATA_DIR)
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.INFO)
        fh = logging.FileHandler(str(DATA_DIR / "app.log"), encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(fh)
        # uvicorn 日志同样走根 logger 落文件，不触碰 stderr
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            lg.handlers.clear()
            lg.propagate = True
        logging.info("桌面模式启动")
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _setup_logging()
    port = int(os.environ.get("GRAD_PREP_PORT") or 0) or _free_port()

    import uvicorn

    from app.main import app

    # log_config=None：跳过 uvicorn 默认 dictConfig（其 formatter 依赖 stderr.isatty()，
    # 在 --noconsole 打包下会抛 AttributeError）。日志由上面的文件 handler 统一接管。
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False, log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    url = f"http://127.0.0.1:{port}"
    ready = False
    for _ in range(100):  # 等待服务就绪（最多 10 秒）
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            ready = True
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    if not ready:
        try:
            import logging

            logging.error("服务启动失败")
        except Exception:  # noqa: BLE001
            pass

    try:
        import webview

        webview.create_window(
            "毕业设计前期准备 Agent",
            url,
            width=1280,
            height=860,
            min_size=(1024, 700),
            background_color="#f5f7fc",
        )
        # webview.start() 阻塞主线程直到窗口关闭，服务线程随之退出
        webview.start()
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"桌面窗口不可用（{exc}），已用浏览器打开 {url}")
        webbrowser.open(url)
        try:
            input("按回车退出…")
        except Exception:  # noqa: BLE001
            time.sleep(600)


if __name__ == "__main__":
    main()
