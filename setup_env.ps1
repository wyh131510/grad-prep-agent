# ============================================================
# 一键环境安装脚本（PowerShell）
#   1. 创建虚拟环境 .venv
#   2. 安装核心依赖（默认清华镜像，失败自动换阿里云）
#   3. 尝试安装可选依赖（BGE 向量检索 + OCR，约 500MB）
# 用法:  powershell -ExecutionPolicy Bypass -File setup_env.ps1
# 自定义镜像: $env:PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"; .\setup_env.ps1
# ============================================================
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot

$PIP_MIRROR = if ($env:PIP_MIRROR) { $env:PIP_MIRROR } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$ALI_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"
# 慢网络下的下载参数：读超时 300 秒，自动重试 5 次
$PIP_ARGS = @("-i", $PIP_MIRROR, "--timeout", "300", "--retries", "5")

Write-Host "== [1/4] 创建虚拟环境 ==" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "创建虚拟环境失败" -ForegroundColor Red; exit 1 }
} else {
    Write-Host "虚拟环境已存在，跳过。"
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "== [2/4] 安装核心依赖（镜像：$PIP_MIRROR）==" -ForegroundColor Cyan
& $py -m pip install -U pip @PIP_ARGS -q
& $py -m pip install -r requirements.txt @PIP_ARGS
if ($LASTEXITCODE -ne 0) {
    Write-Host "当前镜像安装失败，自动切换到阿里云镜像重试…" -ForegroundColor Yellow
    & $py -m pip install -r requirements.txt -i $ALI_MIRROR --timeout 300 --retries 5
    if ($LASTEXITCODE -ne 0) { Write-Host "核心依赖安装失败，请检查网络" -ForegroundColor Red; exit 1 }
}

Write-Host "== [3/4] 安装可选依赖（CPU 版 PyTorch + BGE + OCR）==" -ForegroundColor Cyan
& $py -m pip install torch --index-url https://mirrors.aliyun.com/pytorch-wheels/cpu/ --timeout 300 --retries 5
if ($LASTEXITCODE -ne 0) {
    Write-Host "阿里云 PyTorch 镜像失败，尝试官方源…" -ForegroundColor Yellow
    & $py -m pip install torch --index-url https://download.pytorch.org/whl/cpu --timeout 300 --retries 5
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyTorch 安装失败（可跳过：向量检索将自动降级为 BM25+LLM 精排）" -ForegroundColor Yellow
} else {
    & $py -m pip install -r requirements-optional.txt @PIP_ARGS
    if ($LASTEXITCODE -ne 0) {
        Write-Host "可选依赖部分失败（可跳过，相关能力将自动降级）" -ForegroundColor Yellow
    } else {
        Write-Host "可选依赖安装完成：完整的三重混合检索 + OCR 已可用" -ForegroundColor Green
    }
}

Write-Host "== [4/4] 验证安装 ==" -ForegroundColor Cyan
& $py -c "import fastapi, uvicorn, pymupdf, rank_bm25, openai, bs4; print('核心依赖 OK')"
if ($LASTEXITCODE -ne 0) { Write-Host "核心依赖验证失败" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "环境准备完成！启动方式:" -ForegroundColor Green
Write-Host "  .venv\Scripts\python.exe run.py    （然后浏览器访问 http://127.0.0.1:8000）"
Write-Host "  或双击 start.bat"
Write-Host ""
Write-Host "提示：首次使用向量检索时会自动下载 BGE 模型（默认走 hf-mirror.com 国内镜像）。"
