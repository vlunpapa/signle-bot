# 信号Bot分析策略详解

## 📊 当前启用的策略

### 默认策略：**5分钟交易量告警**（volume_alert_5k）

**位置**：`src/strategies/monitor.py` 和 `src/bot/listener.py`

**策略逻辑**：
1. **监测方式**：连续监测5分钟，每分钟获取一次1分钟K线数据
2. **触发条件**：累计交易量 > 阈值（默认5000 USD）
3. **提前触发**：每次获取数据后立即检查，如果超过阈值，立即发送信号并停止监测
4. **并发执行**：多个不同CA采用并发方式执行，互不阻塞
5. **信号名称**：`交易信号1`
6. **消息格式**：
   ```
   🔔 交易信号1: {token}
   5分钟累计交易量: ${total_volume:,.2f}
   阈值: ${threshold:,.2f}
   超过阈值: ${excess:,.2f}
   ```

**配置参数**：
- `volume_threshold_5k`：交易量阈值（默认5000.0 USD）
- 可通过用户配置修改：`/set_volume_threshold_5k <value>`

**代码位置**：
```python
# src/strategies/engine.py:92-133
@staticmethod
async def volume_alert_5k(
    data: StandardKlineData | OnChainData,
    volume_threshold: float = 5000.0
) -> Optional[SignalResult]:
```

**执行位置**：
```python
# src/strategies/engine.py:226-230
elif strategy_name == "5分钟交易量告警" or strategy_name == "volume_alert_5k":
    volume_threshold = self.config.get_user_param(user_id, "volume_threshold_5k", 5000.0)
    result = await self.builtin.volume_alert_5k(data, volume_threshold)
    if result:
        results.append(result)
```

---

## 🔧 其他可用策略（已实现但可能未启用）

### 1. **外源性爆发二段告警**

**位置**：`src/strategies/engine.py` 中 `BuiltinStrategies.external_burst_phase2`

**通用有效信号模板**（适用于本策略）：

在 N 根连续 K 线中，同时满足：

1. **价格条件**：每根K线收盘价 > 前一根收盘价
2. **成交量条件**：每根K线成交量 > 过去 M 根K线成交量均值 × K 倍
3. **持续性过滤**：N ≥ 2（短周期）或 N ≥ 3（稳健型）

**本策略（外源性爆发二段）具体定义：**

- **数据窗口**：最近若干根 1 分钟 K 线（推荐使用最近 10 根）
- **价格条件**：出现连续 3 根 K 线满足：
  - 第2根收盘价 > 第1根收盘价
  - 第3根收盘价 > 第2根收盘价
- **成交量条件**：
  - M = 3，K = 1.8
  - 对这 3 根K线中的每一根，计算其"前 3 根 K 线的成交量均值"
  - 若当前成交量 > 均值 × 1.8，则记为一次"有效放量"
  - 要求在这 3 根中，**至少有 1 根**满足上述放量条件
- **触发条件**：
  - 一旦在窗口中找到满足"3 连阳 + 至少 1 段放量"的结构，即触发告警
- **信号名称**：`外源性爆发二段告警`

**消息格式示例**：

```
🚀 外源性爆发二段告警: {token}
价格出现连续3根上涨K线（收盘价递增）
成交量在3根K线中有 {hits} 根显著放大(> 前3根均量的 1.8 倍)
当前价格: ${price:.8f}
参考时间: {timestamp}
```

> 说明：当前实现依赖于上游数据源提供的连续 K 线数据（建议为 1 分钟 K 线）。
> 若可用历史 K 线数量不足，将不会触发该信号，并在日志中提示“数据不足”。

---

### 2. **量增价升**（volume_price_rise）

**位置**：`src/strategies/engine.py` 第28-73行

**策略逻辑**：
- **K线模式**：
  - 成交量 > 平均成交量 × 倍数（默认1.5倍）
  - 价格涨幅 > 0
  - 信号强度：`min(100, price_change * 1000 + 50)`
  
- **链上模式**：
  - 买入占比 > 60%
  - 24小时价格涨幅 > 0
  - 信号强度：`min(100, price_change * 10 + buy_ratio * 50)`

**配置参数**：
- `volume_mult`：成交量倍数阈值（默认1.5）

**代码位置**：
```python
# src/strategies/engine.py:28-73
@staticmethod
async def volume_price_rise(
    data: StandardKlineData | OnChainData,
    volume_mult: float = 1.5
) -> Optional[SignalResult]:
```

---

### 3. **缩量新高**（low_volume_new_high）

**位置**：`src/strategies/engine.py` 第75-81行

**状态**：⚠️ **未实现**（只有接口定义）

**预期逻辑**：
- 价格创新高
- 成交量相对较低（缩量）
- 可能表示上涨动能减弱

---

### 4. **天量见顶**（high_volume_top）

**位置**：`src/strategies/engine.py` 第83-89行

**状态**：⚠️ **未实现**（只有接口定义）

**预期逻辑**：
- 成交量异常放大（天量）
- 价格可能见顶
- 可能表示主力出货

---

## 🔄 策略执行流程

### 1. 策略选择逻辑

**位置**：`src/strategies/engine.py` 第162-166行

```python
strategies = self.config.get_user_strategies(user_id)
if not strategies:
    logger.warning(f"用户 {user_id} 未启用任何策略，使用默认策略")
    # 默认启用"5分钟交易量告警"策略（测试用）
    strategies = ["5分钟交易量告警"]
```

**说明**：
- 如果用户未配置策略，默认使用"5分钟交易量告警"
- 用户策略存储在SQLite数据库：`data/config.db`

### 2. 数据选择逻辑

**位置**：`src/strategies/engine.py` 第172-199行

```python
# 对于"5分钟交易量告警"策略，优先使用5分钟数据
if "5分钟交易量告警" in strategies or "volume_alert_5k" in strategies:
    # 查找5分钟数据
    data_5m = next((d for d in data if isinstance(d, StandardKlineData) and d.interval == "5m"), None)
    if data_5m:
        data = data_5m
    else:
        data = data[-1] if data else None
```

**说明**：
- "5分钟交易量告警"策略会专门查找5分钟K线数据
- 如果找不到5分钟数据，使用最新周期的数据（可能触发警告）

### 3. 策略执行循环

**位置**：`src/strategies/engine.py` 第207-235行

```python
# 执行内置策略
for strategy_name in strategies:
    try:
        if strategy_name == "量增价升":
            volume_mult = self.config.get_user_param(user_id, "volume_mult", 1.5)
            result = await self.builtin.volume_price_rise(data, volume_mult)
            if result:
                results.append(result)
        
        elif strategy_name == "5分钟交易量告警" or strategy_name == "volume_alert_5k":
            volume_threshold = self.config.get_user_param(user_id, "volume_threshold_5k", 5000.0)
            result = await self.builtin.volume_alert_5k(data, volume_threshold)
            if result:
                results.append(result)
        
        # TODO: 执行YAML策略
        
    except Exception as e:
        logger.error(f"策略执行失败 {strategy_name}: {e}")
```

---

## 📍 关键代码位置总结

### 策略定义
- **文件**：`src/strategies/engine.py`
- **类**：`BuiltinStrategies`（第24-133行）
- **方法**：
  - `volume_alert_5k()` - 第92-133行 ✅ 已实现
  - `volume_price_rise()` - 第28-73行 ✅ 已实现
  - `low_volume_new_high()` - 第75-81行 ⚠️ 未实现
  - `high_volume_top()` - 第83-89行 ⚠️ 未实现

### 策略引擎
- **文件**：`src/strategies/engine.py`
- **类**：`StrategyEngine`（第136-237行）
- **方法**：`execute_strategies()` - 第143-237行

### 策略调用
- **文件**：`src/bot/listener.py`
- **方法**：`_process_token()` - 第141-204行
- **调用位置**：第189-194行

```python
signals = await self.strategy_engine.execute_strategies(
    token=token,
    data=data,
    user_id=user_id,
    mode=mode
)
```

### 策略配置
- **文件**：`src/core/config.py`
- **方法**：
  - `get_user_strategies()` - 第89-103行
  - `get_user_param()` - 第133-150行
  - `add_user_strategy()` - 第105-110行

### 数据获取
- **文件**：`src/bot/listener.py`
- **方法**：`_process_token()` - 第175-179行

```python
data = await adapter.get_data(
    token=token,
    mode=mode,
    intervals=["5m"]  # 对于5分钟交易量告警策略
)
```

---

## 🎯 当前配置状态

### 默认策略
- **策略名称**：`5分钟交易量告警`
- **阈值**：5000 USD
- **数据周期**：5分钟K线
- **触发条件**：5分钟交易量 > 5000 USD

### 用户配置
- **存储位置**：SQLite数据库 `data/config.db`
- **表名**：`user_configs`
- **字段**：
  - `user_id`：用户ID
  - `strategies`：JSON数组，存储启用的策略列表
  - `params`：JSON对象，存储策略参数

---

## 📝 使用示例

### 查看当前策略
```bash
# 查看日志
tail -f logs/bot.log | grep "执行策略"
```

### 修改策略阈值
通过Bot命令（如果已实现）：
```
/set_volume_threshold_5k 10000
```

或直接修改数据库：
```python
from src.core.config import ConfigManager
config = ConfigManager()
config.set_user_param(user_id, "volume_threshold_5k", 10000.0)
```

---

## 🔍 调试信息

### 策略执行日志
```
执行策略: {token}, 用户={user_id}, 策略列表={strategies}
收到K线数据列表: {token}, 数据量={len(data)}, 周期列表={intervals}
✅ 找到5分钟K线数据: {token}, volume={volume}, interval=5m
策略检查: interval=5m, volume={volume}, threshold={threshold}
5分钟交易量检查: volume={volume}, threshold={threshold}, 是否触发: {result}
策略分析完成: {token}, 信号数量={len(signals)}
```

### 信号发送日志
```
发送信号通知: {token}, 策略=5分钟交易量告警, 强度={strength}, 目标群组={chat_id}
信号已发送: 5分钟交易量告警 - {token}
```
