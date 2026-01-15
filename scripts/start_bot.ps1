# 启动信号Bot
# 使用方法: .\scripts\start_bot.ps1

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath

Set-Location $projectRoot

Write-Host "=" * 60
Write-Host "启动信号Bot"
Write-Host "=" * 60
Write-Host ""

# 检查虚拟环境
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "❌ 虚拟环境不存在，请先创建虚拟环境"
    exit 1
}

# 检查配置文件
if (-not (Test-Path ".env")) {
    Write-Host "❌ .env文件不存在，请先配置"
    exit 1
}

Write-Host "正在启动信号Bot..."
Write-Host ""

# 启动Bot
.\venv\Scripts\python.exe main.py

