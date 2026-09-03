# 打包为 Windows 安装程序

目标产物：**`dist\installer\GradPrepAgent_Setup.exe`**
安装后：桌面快捷方式 + 独立原生窗口（无浏览器地址栏，基于系统自带 WebView2）。

## 前置条件（一次性）

1. **本机 Python 环境**：项目 `.venv` 已就绪（`setup_env.ps1` 装过核心依赖即可，可选依赖可跳过——打包时会自动排除 torch/BGE/OCR，安装版运行在降级模式，功能不受影响）。
2. **Inno Setup 6**（生成安装程序的工具，约 5MB）：
   - 官方下载：https://jrsoftware.org/isdl.php （选 `innosetup-6.x.x.exe`）
   - 安装时保持默认路径即可（脚本会找 `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`）。
   - 中文安装界面：`打包.bat` 会自动从 jsDelivr 下载中文语言文件到 `installer\`；下载失败时自动回退英文界面（不影响打包）。Inno Setup 6.5+ 版本自带中文。
3. 需要联网（安装 PyInstaller/pywebview 走清华镜像）。

## 打包步骤

双击 **`打包.bat`**（或命令行运行），它会依次：

1. 安装打包工具（`pyinstaller`、`pywebview`，清华镜像）；
2. 用 PyInstaller 构建 `dist\GradPrepAgent\GradPrepAgent.exe`：
   - onedir 模式、无控制台窗口、带图标；
   - 打包 `web/` 前端资源、jieba 词典、uvicorn 动态模块；
   - **完整功能版**：包含 BGE 向量检索（torch + sentence-transformers + transformers）与 OCR（rapidocr + onnxruntime），安装包体积较大（数百 MB），首次使用 BGE 时联网自动下载模型（默认 hf-mirror）。
3. 用 Inno Setup 编译安装程序 → `dist\installer\GradPrepAgent_Setup.exe`。

> 若第 3 步提示找不到 Inno Setup：先安装 Inno Setup 6 再重跑（第 2 步产物已就绪）。

## 安装行为说明

- **每用户安装**（无需管理员权限），安装目录：`%LOCALAPPDATA%\Programs\GradPrepAgent`；
- 安装完成后按选择**创建桌面快捷方式**与开始菜单项，并可直接启动；
- **应用数据**（设置/文献库/下载的 PDF/图片）存放于 **`%LOCALAPPDATA%\GradPrepAgent`**；
- **卸载**：开始菜单「卸载」或 设置 → 应用；**卸载时会询问是否同时删除用户数据**（选"是"彻底清除，选"否"保留以便重装继续使用；升级安装时自动保留）。

## 注意事项

- 完整功能版包含 BGE 向量检索与 OCR；**BGE/OCR 依赖本机可正常加载 torch**（如遇 `WinError 1114 c10.dll`，先修复 torch：`pip install --force-reinstall --no-deps "torch==2.7.1" --index-url https://mirrors.aliyun.com/pytorch-wheels/cpu/ --timeout 300` 后重新打包）。
- 桌面窗口依赖 **Microsoft Edge WebView2**（Win10/11 自带；极简系统可安装 WebView2 Runtime：https://developer.microsoft.com/microsoft-edge/webview2/）。
- 首次启动为控制台隐藏模式，如遇异常可查看 `%LOCALAPPDATA%\GradPrepAgent\app.log`。
- 图标想换：替换 `assets\icon.ico` 后重新打包。
