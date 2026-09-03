# ============================================================
# 下载 Inno Setup 简体中文语言文件（打包.bat 调用）
# 失败不影响打包：installer/grad_prep_agent.iss 会自动回退英文界面
# ============================================================
$ErrorActionPreference = "Continue"
$out = Join-Path $PSScriptRoot "ChineseSimplified.isl"
if (Test-Path $out) {
    Write-Host "ChineseSimplified.isl exists, skip."
    exit 0
}
$urls = @(
    "https://cdn.jsdelivr.net/gh/jrsoftware/issrc@main/Files/Languages/ChineseSimplified.isl",
    "https://ghproxy.net/https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl"
)
foreach ($u in $urls) {
    try {
        Invoke-WebRequest -Uri $u -OutFile $out -TimeoutSec 60 -UseBasicParsing
        if ((Test-Path $out) -and (Get-Item $out).Length -gt 2000) {
            Write-Host "ChineseSimplified.isl downloaded OK ($((Get-Item $out).Length) bytes)"
            exit 0
        }
    } catch {
        Write-Host "download failed from $u : $($_.Exception.Message)"
    }
}
Write-Host "Chinese download failed - installer will fallback to English UI."
exit 0
