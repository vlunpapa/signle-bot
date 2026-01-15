# 文档索引

## 📚 核心文档

### 主要文档
- **README.md** - 项目主文档，包含快速开始、配置说明、核心功能等

### 功能文档
- **docs/RELAY_SERVICE.md** - 消息中继服务使用指南
- **MONITORING_LOGIC.md** - 5分钟连续监测任务执行逻辑说明
- **SIGNAL_CHAT_CONFIG.md** - 信号发送目标群组配置说明
- **STRATEGIES_EXPLAINED.md** - 策略详解（5分钟交易量告警等）

### 架构文档
- **docs/ARCHITECTURE.md** - 系统架构设计

## 🔧 使用说明

### 启动服务

1. **启动中继服务**：`python relay_main.py` 或 `.\scripts\start_relay.ps1`
2. **启动信号Bot**：`python main.py` 或 `.\scripts\start_bot.ps1`

### 配置要点

1. **环境变量**：在 `.env` 文件中配置所有必需的参数
2. **群组ID**：确保使用正确的群组ID格式（超级群组为 `-100` + 原始ID）
3. **Bot权限**：确保Bot已加入所有相关群组并具有发送权限

### 工作流程

1. 中继服务监听中转群，接收DEBOT等Bot的消息
2. 使用Pyrogram用户账户转发消息到处理群
3. 信号Bot接收消息，提取Token
4. 启动5分钟连续监测任务（并发执行）
5. 每分钟获取K线数据，检查累计交易量
6. 如果超过阈值，立即发送"交易信号1"到目标群组并停止监测

## 📊 日志查看

- `logs/bot.log` - 信号Bot日志
- `logs/relay.log` - 中继服务日志

## 🆘 故障排查

参考 README.md 中的故障排查章节。
