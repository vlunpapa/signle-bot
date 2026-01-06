# 分析层使用指南

## 功能概述

分析层在消息监听和策略执行之间，用于：
1. **消息聚合**：收集时间窗口内的所有相关消息
2. **模式识别**：通过脚本分析识别市场模式
3. **策略生成**：自动生成YAML策略配置

## 工作流程

```
消息 → Token提取 → 消息解析 → Message Buffer → 
Window Manager → Script Analyzer → Strategy Generator → 
策略文件保存
```

## 配置

### 基本配置

在 `config/analysis_config.yaml` 中配置：

```yaml
analysis:
  window:
    size: 300  # 5分钟时间窗口
    min_messages: 2  # 最少2条消息才触发分析
    max_messages: 50  # 最多分析50条消息
    check_interval: 60  # 每60秒检查一次
```

### 启用/禁用分析层

在 `main.py` 中：

```python
# 启用分析层（默认）
bot = SignalBot(bot_token, enable_analysis=True)

# 禁用分析层
bot = SignalBot(bot_token, enable_analysis=False)
```

## 消息格式

分析层支持解析以下格式的Meme币消息：

### 聪明钱买入
- `PEPE 聪明钱买入 100万`
- `PEPE smart money buy 100万`
- `PEPE 大户买入 50万`

### 市值
- `PEPE MC: 500万`
- `PEPE 市值: 800万`
- `PEPE market cap: 1000万`

### 告警
- `PEPE 告警 x3`
- `PEPE alert x5`
- `PEPE 警告 x2`

## 自定义分析脚本

### 创建脚本

1. 复制示例脚本：
```bash
cp scripts/analyze_meme_example.py scripts/analyze_meme.py
```

2. 修改分析逻辑

3. 在配置中指定路径：
```yaml
analysis:
  analyzers:
    script:
      enabled: true
      script_path: "scripts/analyze_meme.py"
```

### 脚本接口

```python
def analyze(
    token: str,
    messages: List[MemeMessage],
    summary: Optional[TokenSummary] = None
) -> AnalysisResult:
    # 你的分析逻辑
    return AnalysisResult(...)
```

## 生成的策略

### 策略位置

生成的策略保存在：
```
config/strategies/generated/
  ├── {pattern}_{token}_{timestamp}.yaml
  └── active_strategies.yaml
```

### 策略格式

```yaml
name: high_smart_money_with_alerts_PEPE_1234567890
description: 聪明钱大量买入且多次告警
mode: kline
enabled: false  # 默认不启用，需要手动启用
confidence: 0.8
conditions:
  - field: smart_money_buy
    operator: ">"
    value: 800000.0
    description: 聪明钱买入超过 80.0万 USDT
  - field: alert_count
    operator: ">="
    value: 3
    description: 告警次数 >= 3
```

### 启用生成的策略

1. 查看生成的策略：
```bash
ls config/strategies/generated/
```

2. 在Telegram中启用：
```
/set_strategy high_smart_money_with_alerts_PEPE_1234567890
```

## 内置模式

分析层内置识别以下模式：

1. **high_smart_money_with_alerts**
   - 条件：聪明钱 > 100万 且 告警 >= 3次
   - 置信度：0.8

2. **low_mc_high_smart_money**
   - 条件：市值 < 100万 且 聪明钱 > 50万
   - 置信度：0.75

3. **rapid_mc_growth**
   - 条件：市值增长 > 50%
   - 置信度：0.7

4. **high_smart_money_ratio**
   - 条件：聪明钱占比高
   - 置信度：0.65

## 监控和调试

### 查看日志

```bash
# 查看分析层日志
tail -f logs/bot.log | grep "分析"
```

### 手动触发分析

在代码中：
```python
result = await analysis_manager.trigger_analysis("PEPE")
```

### 查看Token摘要

```python
summary = await analysis_manager.get_summary("PEPE")
print(f"聪明钱总量: {summary.smart_money_total}")
print(f"平均市值: {summary.avg_mc}")
print(f"告警次数: {summary.total_alerts}")
```

## LLM分析（预留）

LLM分析器接口已预留，但暂未实现。后续实现时需要：

1. 配置API密钥：
```yaml
analysis:
  analyzers:
    llm:
      enabled: true
      provider: "openai"
      api_key: "${LLM_API_KEY}"
```

2. 实现 `src/analysis/llm_analyzer.py` 中的方法

## 性能优化

1. **调整时间窗口**：根据消息频率调整窗口大小
2. **限制消息数量**：设置 `max_messages` 避免分析过多消息
3. **异步处理**：分析任务异步执行，不阻塞消息接收
4. **缓存结果**：分析结果可缓存，避免重复分析

## 故障排查

### 策略未生成

- 检查置信度是否达到阈值（默认0.7）
- 查看日志确认是否识别到模式
- 检查消息是否被正确解析

### 分析不触发

- 检查时间窗口配置
- 确认消息数量是否达到 `min_messages`
- 查看Window Manager是否正常运行

### 消息解析失败

- 检查消息格式是否符合模式
- 查看日志中的解析错误
- 考虑添加自定义解析模式

