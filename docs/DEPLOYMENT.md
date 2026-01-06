# 🚀 部署指南

## Docker 部署（推荐）

### 1. 准备环境

```bash
# 确保已安装 Docker 和 Docker Compose
docker --version
docker-compose --version
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件
nano .env
```

必须配置：
- `BOT_TOKEN`: Telegram Bot Token（从 @BotFather 获取）

可选配置：
- 各数据源API密钥
- Redis配置

### 3. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f signal-bot

# 查看所有服务状态
docker-compose ps
```

### 4. 验证运行

在Telegram中向Bot发送 `/start` 命令，如果收到欢迎消息，说明部署成功。

### 5. 停止服务

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

## 本地开发部署

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 设置环境变量
export BOT_TOKEN=your_bot_token_here

# 或创建 .env 文件
echo "BOT_TOKEN=your_bot_token_here" > .env
```

### 3. 运行

```bash
python main.py
```

## 生产环境部署

### 使用 Systemd（Linux）

创建服务文件 `/etc/systemd/system/signal-bot.service`:

```ini
[Unit]
Description=Telegram Signal Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/telegram-signal-bot
Environment="BOT_TOKEN=your_token"
ExecStart=/usr/bin/python3 /opt/telegram-signal-bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl enable signal-bot
sudo systemctl start signal-bot
sudo systemctl status signal-bot
```

## 监控与日志

### 查看日志

```bash
# Docker
docker-compose logs -f signal-bot

# 本地
tail -f logs/bot.log
```

### 健康检查

Bot会自动响应 `/status` 命令，返回当前配置状态。

## 故障排查

### Bot无法连接

1. 检查 `BOT_TOKEN` 是否正确
2. 确认网络可以访问 `api.telegram.org`
3. 查看日志中的错误信息

### 数据获取失败

1. 检查API密钥配置（如需要）
2. 确认网络连接正常
3. 查看适配器日志

### 策略不触发

1. 使用 `/list_strategies` 查看可用策略
2. 使用 `/set_strategy` 启用策略
3. 检查策略条件是否满足

