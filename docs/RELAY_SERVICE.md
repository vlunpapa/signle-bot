# 消息中继服务使用指南

## 问题说明

**Telegram Bot API限制**：Bot无法接收其他Bot发送的消息。

**你的情况**：
- DEBOT直接在中转群推送消息
- 你的信号Bot无法接收DEBOT的消息
- 需要让信号Bot能够处理DEBOT的消息

## 解决方案

使用**消息中继服务**：
1. 使用Pyrogram（用户账户）监听中转群
2. 可以接收所有消息，包括DEBOT等Bot的消息
3. 将消息通过Pyrogram用户账户发送到处理群（这样信号Bot可以正常接收）
4. 信号Bot在处理群中接收并处理消息

## 架构

```
中转群（有DEBOT推送）
    ↓
[Pyrogram用户账户] ← 可以接收所有消息（包括Bot消息）
    ↓
[Bot API发送消息]
    ↓
处理群（信号Bot在这里）
    ↓
[信号Bot处理消息]
```

**注意**：如果信号Bot也在中转群，可以将处理群设置为中转群（同一个群组）。

## 配置步骤

### 1. 获取Telegram API凭证

1. 访问 https://my.telegram.org
2. 使用手机号登录
3. 进入 "API development tools"
4. 创建应用，获取：
   - `api_id`
   - `api_hash`

### 2. 安装依赖

```bash
pip install pyrogram tgcrypto
```

或使用requirements.txt：
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

在 `.env` 文件中添加：

```env
# Pyrogram配置（用户账户）
TELEGRAM_API_ID=你的API_ID
TELEGRAM_API_HASH=你的API_HASH
TELEGRAM_PHONE_NUMBER=+8613800138000  # 带国家代码

# 中继服务配置
RELAY_SOURCE_CHAT_ID=-1234567890  # 中转群ID（监听DEBOT消息的群组）
RELAY_TARGET_CHAT_ID=-1234567890  # 处理群ID（信号Bot所在的群组，可以是同一个）

# Bot Token（信号Bot的Token）
BOT_TOKEN=your_bot_token_here
```

### 4. 获取群组ID

如果不知道群组ID，可以使用：
```bash
python scripts/get_group_id.py
```

或使用你的信号Bot的 `/status` 命令查看。

### 5. 启动中继服务

```bash
python relay_main.py
```

首次运行会要求输入验证码（Telegram会发送到你的手机）。

## 使用方式

### 方式1：信号Bot也在中转群（推荐）

如果信号Bot也在中转群，配置：
```env
   RELAY_SOURCE_CHAT_ID=-1234567890  # 中转群
   RELAY_TARGET_CHAT_ID=-1234567890  # 也是中转群（同一个）
```

这样：
- Pyrogram监听中转群的所有消息（包括DEBOT）
- 将消息通过Bot API发送到中转群
- 信号Bot在中转群接收并处理

### 方式2：创建单独的处理群

如果不想在中转群处理，可以：
1. 创建一个新的处理群
2. 将信号Bot添加到处理群
3. 配置：
   ```env
   RELAY_SOURCE_CHAT_ID=-1234567890  # 中转群
   RELAY_TARGET_CHAT_ID=-1001234567890  # 处理群
   ```

## 工作原理

1. **Pyrogram监听**：使用用户账户监听中转群，可以接收所有消息
2. **消息过滤**：只处理文本消息（包含Token的消息）
3. **消息转发**：通过Bot API将消息发送到处理群
4. **信号Bot处理**：信号Bot在处理群中接收消息并执行策略

## 注意事项

1. **需要手机号**：Pyrogram需要用户账户，必须使用手机号登录
2. **验证码**：首次运行需要输入Telegram发送的验证码
3. **2FA**：如果账户启用了2FA，需要输入密码
4. **运行两个服务**：
   - `relay_main.py` - 中继服务（监听中转群）
   - `main.py` - 信号Bot（处理消息）

## 测试

1. 启动中继服务：
   ```bash
   python relay_main.py
   ```

2. 启动信号Bot：
   ```bash
   python main.py
   ```

3. 在中转群中，让DEBOT发送一条包含Token的消息

4. 查看日志：
   - `logs/relay.log` - 中继服务日志
   - `logs/bot.log` - 信号Bot日志

5. 应该看到：
   - 中继服务：`📨 收到消息: 发送者=DEBOT, Bot=True`
   - 中继服务：`✅ 已中继消息到处理群`
   - 信号Bot：`收到消息: 发送者=你的Bot, Bot=False`
   - 信号Bot：`检测到Token: ['xxx']`

## 常见问题

### Q: 为什么需要两个服务？

A: 因为：
- Pyrogram（用户账户）可以接收所有消息，但无法直接调用Bot的处理逻辑
- Bot API可以处理消息，但无法接收其他Bot的消息
- 所以需要中继服务作为桥梁

### Q: 可以合并成一个服务吗？

A: 可以，但需要重构代码，让Pyrogram直接调用策略引擎，而不是通过Bot API。这需要较大的代码改动。

### Q: 中继服务会重复发送消息吗？

A: 不会。中继服务只监听中转群，不会监听处理群。如果处理群和中转群是同一个，中继服务会忽略自己发送的消息（通过Bot API发送的）。

### Q: 性能如何？

A: 中继服务很轻量，只是转发消息，延迟通常在1-2秒内。

