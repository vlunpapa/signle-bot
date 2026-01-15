# 启动消息中继服务
# 使用方法: .\scripts\start_relay.ps1

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath

Set-Location $projectRoot

Write-Host "=" * 60
Write-Host "启动消息中继服务"
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

# 检查必需的配置
$envContent = Get-Content ".env" -Raw
$requiredVars = @(
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_PHONE_NUMBER",
    "RELAY_SOURCE_CHAT_ID",
    "RELAY_TARGET_CHAT_ID",
    "BOT_TOKEN"
)

$missing = @()
foreach ($var in $requiredVars) {
    if ($envContent -notmatch "$var\s*=") {
        $missing += $var
    }
}

if ($missing.Count -gt 0) {
    Write-Host "❌ 缺少以下配置项："
    foreach ($var in $missing) {
        Write-Host "  - $var"
    }
    Write-Host ""
    Write-Host "请参考 SETUP_RELAY.md 进行配置"
    exit 1
}

Write-Host "✅ 配置检查通过"
Write-Host ""
Write-Host "正在启动中继服务..."
Write-Host ""

# 启动服务
.\venv\Scripts\python.exe relay_main.py

