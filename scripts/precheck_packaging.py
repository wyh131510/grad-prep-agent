# -*- coding: utf-8 -*-
"""验证：冻结路径逻辑 + run_desktop 服务端启动（不触发 webview/浏览器）。"""
import os
import subprocess
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1) 冻结路径模拟（独立进程，避免污染当前导入）
code = """
import sys, os, tempfile
sys.frozen = True
sys._MEIPASS = tempfile.mkdtemp()
os.makedirs(os.path.join(sys._MEIPASS, 'web'), exist_ok=True)
sys.path.insert(0, sys._MEIPASS)
from app.config import APP_DIR, DATA_DIR
print('frozen APP_DIR:', APP_DIR)
print('frozen DATA_DIR:', DATA_DIR)
assert str(APP_DIR) == sys._MEIPASS, 'APP_DIR 应为 _MEIPASS'
assert 'GradPrepAgent' in str(DATA_DIR), 'DATA_DIR 应指向 LOCALAPPDATA'
print('frozen path logic OK')
"""
r = subprocess.run(
    [os.path.join(PROJECT, ".venv", "Scripts", "python.exe"), "-c", code],
    capture_output=True, text=True, cwd=PROJECT,
)
print(r.stdout.strip() or r.stderr.strip()[:400])
if r.returncode != 0:
    print("FROZEN TEST FAILED")
    sys.exit(1)

# 2) 端口选择 + 服务线程启动 + 健康检查
code2 = """
import sys, os
sys.path.insert(0, os.getcwd())
from run_desktop import _free_port
port = _free_port()
print('free port:', port)
assert 1024 < port < 65535
import threading, time, urllib.request, uvicorn
from app.main import app
cfg = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)
srv = uvicorn.Server(cfg)
threading.Thread(target=srv.run, daemon=True).start()
url = 'http://127.0.0.1:%d' % port
ok = False
for _ in range(100):
    try:
        urllib.request.urlopen(url + '/api/health', timeout=1)
        ok = True
        break
    except Exception:
        time.sleep(0.1)
print('health ok:', ok)
assert ok, '服务未就绪'
srv.should_exit = True
print('desktop server-thread OK')
"""
r = subprocess.run(
    [os.path.join(PROJECT, ".venv", "Scripts", "python.exe"), "-c", code2],
    capture_output=True, text=True, cwd=PROJECT, timeout=120,
)
print(r.stdout.strip() or r.stderr.strip()[:400])
if r.returncode != 0:
    print("SERVER TEST FAILED")
    sys.exit(1)
print("ALL PACKAGING PRE-CHECKS PASSED")
