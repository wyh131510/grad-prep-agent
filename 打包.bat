@echo off
setlocal
cd /d "%~dp0"
title GradPrepAgent - Build Installer

echo ============================================
echo  Step 1/3: install build tools (PyInstaller + pywebview)
echo ============================================
".venv\Scripts\python.exe" -m pip install -U pyinstaller pywebview -i https://pypi.tuna.tsinghua.edu.cn/simple --timeout 300 --retries 5 > build.log 2>&1 || (type build.log & goto :err)

echo ============================================
echo  Step 2/3: build exe (PyInstaller, onedir, FULL features)
echo ============================================
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onedir --noconsole ^
  --name GradPrepAgent ^
  --icon assets\icon.ico ^
  --add-data "web;web" ^
  --collect-data jieba ^
  --collect-submodules uvicorn ^
  --hidden-import uvicorn.logging --hidden-import uvicorn.loops --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols --hidden-import uvicorn.protocols.http --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan --hidden-import uvicorn.lifespan.on ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --collect-data sentence_transformers ^
  run_desktop.py >> build.log 2>&1 || (type build.log & goto :err)

echo ============================================
echo  Step 3/3: build installer (Inno Setup 6 required)
echo ============================================
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
  echo   [3a] ensure Chinese language file...
  powershell -NoProfile -ExecutionPolicy Bypass -File installer\download_isl.ps1
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\grad_prep_agent.iss >> build.log 2>&1 || (type build.log & goto :err)
) else (
  echo.
  echo [WARN] Inno Setup 6 not found at default path.
  echo        Download it from https://jrsoftware.org/isdl.php and install first.
  echo        Then re-run this script. The exe has already been built at dist\GradPrepAgent\.
  goto :end
)

echo.
echo DONE. Installer: dist\installer\GradPrepAgent_Setup.exe
goto :end

:err
echo.
echo [ERROR] Build failed. Full log saved to build.log - please share its content.
pause
exit /b 1

:end
pause
