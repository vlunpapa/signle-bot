# 🤖 Telegram 驱动型多源量价信号机器人

一个支持K线模式和链上模式的智能量价信号检测与推送系统。

## ✨ 核心特性

- 📥 **多源数据采集**: DexScreener（新Meme）、Bybit（热门山寨）、Binance（主流）、**Helius（Solana链上）**
- 🔄 **智能数据源**: 自动选择Helius（Solana）或DexScreener（其他链）
- 🧠 **智能策略引擎**: 内置经典策略 + YAML自定义策略
- ⚙️ **动态配置**: 用户可通过命令切换策略、调整参数
- 📊 **实时推送**: Telegram消息推送
- 🔔 **告警去重**: 每个CA每10分钟只告警一次
- 📈 **24小时统计**: 告警消息中包含近24小时告警次数

## 🏗️ 系统架构

```
中转群（DEBOT推送消息）
  ↓
[Pyrogram用户账户] ← 监听中转群，接收所有消息
  ↓
[转发到处理群] ← 使用Pyrogram用户账户发送（信号Bot可接收）
  ↓
[信号Bot] ← 接收消息，提取Token
  ↓
[连续监测] ← 每分钟获取K线数据，检查累计交易量
  ↓
[触发信号] ← 累计交易量超过阈值，立即发送"交易信号1"
  ↓
[目标群组] ← 接收交易信号
```

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Telegram Bot Token
- Telegram API凭证（api_id, api_hash, phone_number）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# Bot配置
BOT_TOKEN=your_bot_token_here
RELAY_BOT_TOKEN=your_relay_bot_token_here  # 可选，推荐使用单独的转发Bot

# Pyrogram配置（用户账户）
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE_NUMBER=+1234567890  # 带国家代码

# 群组配置
RELAY_SOURCE_CHAT_ID=-1234567890  # 中转群ID（监听DEBOT消息）
RELAY_TARGET_CHAT_ID=-1234567890  # 处理群ID（信号Bot所在群组）
SIGNAL_CHAT_ID=-1001234567890     # 信号发送目标群组

# 代理配置（可选）
TG_PROXY_URL=http://127.0.0.1:7890

# 并发执行上限（可选，默认50，不超过API限制60）
MAX_CONCURRENT_TOKENS=50

# Helius API配置（可选，用于Solana链上数据）
HELIUS_API_KEY=your_helius_api_key_here
HELIUS_PROXY_URL=http://127.0.0.1:7890  # 可选，Helius API代理
```

### 3. 启动服务

#### 启动中继服务

```bash
python relay_main.py
```

或使用脚本：
```powershell
.\scripts\start_relay.ps1
```

#### 启动信号Bot

```bash
python main.py
```

或使用脚本：
```powershell
.\scripts\start_bot.ps1
```

## 📖 核心功能

### 1. 消息中继服务

- **功能**：监听中转群，接收DEBOT等Bot的消息，转发到处理群
- **技术**：使用Pyrogram用户账户监听，可以接收所有消息
- **配置**：`RELAY_SOURCE_CHAT_ID`（监听群组）、`RELAY_TARGET_CHAT_ID`（目标群组）

详细说明：`docs/RELAY_SERVICE.md`

### 2. 连续监测

- **功能**：获得CA后，自动启动连续监测（默认5分钟）
- **流程**：
  1. 每分钟获取一次1分钟K线数据
  2. 每分钟返回一次数据（记录到日志）
  3. 每次获取数据后立即检查累计交易量
  4. 如果累计交易量超过阈值，立即发送"交易信号1"并停止监测
  5. 如果监测时间内未触发，监测结束后停止

详细说明：`MONITORING_LOGIC.md`

### 3. 信号发送

- **目标群组**：配置 `SIGNAL_CHAT_ID` 指定信号发送的目标群组
- **信号格式**：交易信号1，包含Token、累计交易量、阈值等信息
- **告警去重**：每个CA每10分钟只告警一次
- **24小时统计**：告警消息中包含近24小时告警次数

详细说明：`SIGNAL_CHAT_CONFIG.md`

## 📊 策略说明

### 可用策略

- **量增价升**：检测价格上升且成交量放大
- **缩量新高**：检测缩量创新高
- **天量见顶**：检测天量见顶信号
- **5分钟交易量告警**：监测5分钟累计交易量，超过阈值告警

详细说明：`STRATEGIES_EXPLAINED.md`

### 策略配置

使用 `/set_strategy` 命令（不带参数）会弹出按钮菜单，可以点击选择多个策略。

## 🔧 配置说明

### 环境变量

| 变量名 | 说明 | 必需 |
|--------|------|------|
| `BOT_TOKEN` | 信号Bot的Token | ✅ |
| `RELAY_BOT_TOKEN` | 转发Bot的Token（推荐） | ⚠️ |
| `TELEGRAM_API_ID` | Telegram API ID | ✅ |
| `TELEGRAM_API_HASH` | Telegram API Hash | ✅ |
| `TELEGRAM_PHONE_NUMBER` | 手机号（带国家代码） | ✅ |
| `RELAY_SOURCE_CHAT_ID` | 中转群ID（监听群组） | ✅ |
| `RELAY_TARGET_CHAT_ID` | 处理群ID（信号Bot所在群组） | ✅ |
| `SIGNAL_CHAT_ID` | 信号发送目标群组ID | ⚠️ |
| `TG_PROXY_URL` | 代理URL（可选） | ❌ |
| `HELIUS_API_KEY` | Helius API密钥（Solana链上数据） | ⚠️ |
| `HELIUS_PROXY_URL` | Helius API代理（可选） | ❌ |
| `MAX_CONCURRENT_TOKENS` | 并发执行上限（默认50） | ❌ |

### 群组ID格式

- **普通群组**：负数，如 `-123456789`
- **超级群组**：负数，格式为 `-100` + 原始ID，如 `-1001234567890`
- **自动转换**：如果配置的是正数ID，系统会自动尝试转换

## 📝 日志

日志文件保存在 `logs/` 目录：

- `logs/bot.log` - 信号Bot日志
- `logs/relay.log` - 中继服务日志

### 查看日志

```powershell
# 查看信号Bot日志
Get-Content logs\bot.log -Tail 20

# 查看中继服务日志
Get-Content logs\relay.log -Tail 10

# 实时监控
Get-Content logs\bot.log -Wait -Tail 10
```

## 🐛 故障排查

### Bot无法接收消息

- 检查Bot是否已加入处理群
- 确认中继服务正在运行
- 查看中继服务日志，确认消息转发成功

### 信号未发送

- 检查 `SIGNAL_CHAT_ID` 配置是否正确
- 确认Bot已加入目标群组
- 查看信号Bot日志，确认监测任务是否触发

### 监测任务未启动

- 检查策略配置（应启用"5分钟交易量告警"）
- 查看日志，确认Token是否被正确提取
- 确认数据源适配器正常工作

## 📚 文档

- `docs/RELAY_SERVICE.md` - 消息中继服务说明
- `MONITORING_LOGIC.md` - 监测任务执行逻辑
- `SIGNAL_CHAT_CONFIG.md` - 信号发送目标群组配置
- `STRATEGIES_EXPLAINED.md` - 策略详解
- `docs/ARCHITECTURE.md` - 系统架构设计
- `docs/HELIUS_API_FEASIBILITY.md` - Helius API可行性分析
- `docs/HELIUS_SETUP.md` - Helius API配置指南
- `docs/OPTIMIZATION_SUMMARY.md` - 优化总结

## 📝 License

MIT
