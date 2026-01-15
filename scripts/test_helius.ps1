# 测试Helius适配器数据获取功能
# 用法: .\scripts\test_helius.ps1 <CA地址>

param(
    [Parameter(Mandatory=$true)]
    [string]$CaAddress
)

$ErrorActionPreference = "Stop"

# 切换到项目根目录
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
Set-Location $projectRoot

Write-Host "项目根目录: $projectRoot" -ForegroundColor Green
Write-Host "测试CA地址: $CaAddress" -ForegroundColor Green
Write-Host ""

# 设置编码
$env:PYTHONIOENCODING = "utf-8"

# 检查虚拟环境
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "激活虚拟环境..." -ForegroundColor Yellow
    .\venv\Scripts\Activate.ps1
} else {
    Write-Host "未找到虚拟环境，使用系统Python" -ForegroundColor Yellow
}

# 运行测试脚本
Write-Host "开始测试Helius适配器..." -ForegroundColor Cyan
python scripts/test_helius.py $CaAddress

if ($LASTEXITCODE -ne 0) {
    Write-Host "测试失败，退出码: $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "测试完成！" -ForegroundColor Green
