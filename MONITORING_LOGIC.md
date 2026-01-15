# 监测任务执行逻辑说明

## ✅ 当前实现

### 1. 并发执行

**多个不同CA采用并发方式执行**

- 在 `src/bot/listener.py` 第143行，使用 `asyncio.create_task()` 为每个Token创建独立的任务
- 每个Token的监测任务都是异步执行的，不会相互阻塞
- 可以同时监测多个不同的CA

```python
# 异步处理每个Token（不阻塞）
for token in tokens:
    asyncio.create_task(self._process_token(token, user_id, message.chat.id))
```

### 2. 提前触发和停止

**同个地址在5分钟监测时间内，一旦发现触及交易信号，就直接发布消息，并且中止任务**

- 修改了 `src/strategies/monitor.py` 的监测逻辑
- 每次获取1分钟数据后，立即检查累计交易量
- 如果累计交易量超过阈值（5K USD），立即：
  1. 触发告警回调，发送"交易信号1"
  2. 停止监测任务（`self.is_running = False`）
  3. 退出循环，不再继续监测

### 3. 执行流程

```
收到消息 → 提取多个Token
  ↓
为每个Token创建异步任务（并发执行）
  ↓
每个Token的监测任务：
  ├─ 第1分钟：获取数据 → 检查累计交易量
  │   ├─ 如果超过阈值 → 触发告警 → 停止任务 ✅
  │   └─ 如果未超过 → 继续
  ├─ 等待60秒
  ├─ 第2分钟：获取数据 → 检查累计交易量
  │   ├─ 如果超过阈值 → 触发告警 → 停止任务 ✅
  │   └─ 如果未超过 → 继续
  ├─ ... (最多5分钟)
  └─ 如果5分钟都未触发，最后检查一次
```

## 📊 关键代码

### 并发执行
```python
# src/bot/listener.py:143
for token in tokens:
    asyncio.create_task(self._process_token(token, user_id, message.chat.id))
```

### 提前触发和停止
```python
# src/strategies/monitor.py:77-95
# 每次获取数据后立即检查
total_volume = sum(data.volume for data in self.minute_data)
if total_volume > self.volume_threshold:
    # 立即触发告警
    await self.alert_callback(self.token, total_volume)
    # 停止监测任务
    self.is_running = False
    break  # 退出循环
```

## ✅ 验证

- ✅ 多个Token并发执行：使用 `asyncio.create_task()`
- ✅ 提前触发信号：每次获取数据后立即检查
- ✅ 立即停止任务：触发信号后设置 `is_running = False` 并 `break`

## 📝 日志示例

### 提前触发的情况：
```
📊 [1/5] Token: xxx, 1分钟交易量=$6,000.00
🔔 交易信号1触发（提前）: xxx, 累计交易量=$6,000.00 > $5,000.00, 监测时长=1分钟
⏹️  监测任务已停止（已触发信号）: xxx
```

### 正常完成5分钟的情况：
```
📊 [1/5] Token: xxx, 1分钟交易量=$1,000.00
📊 [2/5] Token: xxx, 1分钟交易量=$1,200.00
📊 [3/5] Token: xxx, 1分钟交易量=$1,500.00
📊 [4/5] Token: xxx, 1分钟交易量=$1,800.00
📊 [5/5] Token: xxx, 1分钟交易量=$2,000.00
📈 5分钟监测完成: xxx, 累计交易量=$7,500.00 > $5,000.00
🔔 交易信号1触发: xxx
```
