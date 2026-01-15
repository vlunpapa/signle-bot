# 并发执行上限配置说明

## 📋 概述

系统已实现并发执行上限控制，确保不超过 DexScreener API 限制（每分钟60次请求）。

## ⚙️ 配置方式

### 方式1：环境变量配置（推荐）

在 `.env` 文件中添加：

```bash
# 最大并发Token数量（默认50，不超过API限制60）
MAX_CONCURRENT_TOKENS=50
```

**推荐值**：
- **50**：推荐值，留10次/分钟的余量
- **60**：最大值，刚好达到API限制
- **不建议超过60**：会触发API限流等待

### 方式2：代码配置

在 `main.py` 中初始化 `MessageListener` 时传入：

```python
listener = MessageListener(
    config_manager,
    analysis_manager=analysis_manager,
    signal_chat_id=signal_chat_id,
    max_concurrent_tokens=50  # 设置并发上限
)
```

## 🔍 工作原理

### 1. 信号量控制

系统使用 `asyncio.Semaphore` 控制并发数量：

```python
# src/bot/listener.py
self.semaphore = asyncio.Semaphore(max_concurrent_tokens)

async def _process_token_with_limit(self, token, user_id, chat_id):
    async with self.semaphore:
        await self._process_token(token, user_id, chat_id)
```

### 2. API限流配合

- **并发控制**：限制同时执行的Token数量
- **API限流**：自动控制请求频率（每分钟60次）

两者配合，确保：
- 不会同时发起过多请求
- 不会超过API限制

## 📊 性能影响

| 并发上限 | API调用频率 | 性能影响 | 说明 |
|---------|------------|---------|------|
| 30      | 30次/分钟  | 无影响  | 保守配置，留有余量 |
| 50      | 50次/分钟  | 无影响  | **推荐配置** |
| 60      | 60次/分钟  | 无影响  | 最大配置，刚好达到限制 |
| 100     | 60次/分钟  | 有等待  | 超过限制，会触发限流等待 |

## ⚠️ 重要提示

1. **不要超过60**：超过API限制会导致请求被限流等待
2. **推荐值50**：留10次/分钟的余量，避免突发情况
3. **自动保护**：如果设置超过60，系统会自动调整为60

## 🔧 运行时检查

启动时会显示当前配置：

```
消息监听器初始化完成：最大并发Token数=50, API限流=60次/分钟
```

如果配置超过限制，会显示警告：

```
并发上限 100 超过API限制（60次/分钟），已自动调整为60
```

## 📝 示例配置

### 保守配置（推荐）

```bash
# .env
MAX_CONCURRENT_TOKENS=50
```

**适用场景**：
- 生产环境
- 需要稳定性能
- 避免API限流

### 最大性能配置

```bash
# .env
MAX_CONCURRENT_TOKENS=60
```

**适用场景**：
- 测试环境
- 需要最大吞吐量
- 可以接受接近限流边界

### 低并发配置

```bash
# .env
MAX_CONCURRENT_TOKENS=30
```

**适用场景**：
- 资源受限环境
- 需要更保守的配置
- 避免任何API风险

## 🚀 性能监控

系统会记录并发执行情况：

```
检测到Token: ['PEPE', 'DOGE'] (用户: 123456, 发送者: @user)
消息监听器初始化完成：最大并发Token数=50, API限流=60次/分钟
```

如果达到并发上限，后续Token会等待，直到有可用槽位。

## 📚 相关文档

- `docs/PERFORMANCE_SUMMARY.md`：性能分析总结
- `docs/PERFORMANCE_ANALYSIS.md`：详细性能分析
- `src/core/rate_limiter.py`：API限流器实现
