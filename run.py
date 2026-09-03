# -*- coding: utf-8 -*-
"""一键启动入口。

用法:
    python run.py                 # 默认 http://127.0.0.1:8000
    python run.py --port 9000
    python run.py --no-browser    # 不自动打开浏览器
"""
from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="毕业设计前期准备 Agent 启动器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载（不建议日常使用）")
    args = parser.parse_args()

    if not args.no_browser and not args.reload:
        url = f"http://{args.host}:{args.port}"
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    import uvicorn

    print(f"* 毕业设计前期准备 Agent 启动中: {f'http://{args.host}:{args.port}' if not args.reload else '开发模式'}")
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
