# 分析层实现总结

## ✅ 已完成模块

### 1. Message Buffer（消息缓冲区）
**文件**: `src/analysis/message_buffer.py`

- ✅ 按Token分组存储消息
- ✅ 支持时间窗口查询
- ✅ Token摘要计算
- ✅ 消息过期清理

### 2. Message Parser（消息解析器）
**文件**: `src/analysis/message_parser.py`

- ✅ 解析聪明钱买入消息
- ✅ 解析市值(MC)消息
- ✅ 解析告警消息
- ✅ 支持中英文格式
- ✅ 数字单位转换（万、k、M等）

### 3. Window Manager（时间窗口管理器）
**文件**: `src/analysis/window_manager.py`

- ✅ 时间窗口管理（默认5分钟）
- ✅ 自动触发分析
- ✅ 窗口去重机制
- ✅ 可配置参数

### 4. Script Analyzer（脚本分析器）
**文件**: `src/analysis/script_analyzer.py`

- ✅ 默认分析逻辑（4种模式识别）
- ✅ 支持自定义Python脚本
- ✅ 异步执行
- ✅ 结果置信度计算

### 5. LLM Analyzer（LLM分析器 - 接口预留）
**文件**: `src/analysis/llm_analyzer.py`

- ✅ 接口定义完成
- ⏸️ 实现暂不执行（保留扩展窗口）
- ✅ 可配置启用/禁用

### 6. Strategy Generator（策略生成器）
**文件**: `src/analysis/strategy_generator.py`

- ✅ 从分析结果生成YAML策略
- ✅ 策略验证
- ✅ 策略持久化
- ✅ 活跃策略列表管理

### 7. Analysis Manager（分析管理器）
**文件**: `src/analysis/manager.py`

- ✅ 整合所有分析组件
- ✅ 统一接口
- ✅ 自动策略生成

## 🔄 集成流程

### 消息处理流程

```
1. Telegram消息到达
   ↓
2. Token提取（TokenExtractor）
   ↓
3. 消息解析（MemeMessageParser）
   - 识别消息类型（聪明钱/MC/告警）
   - 提取结构化数据
   ↓
4. 添加到Message Buffer
   ↓
5. Window Manager检查时间窗口
   - 每60秒检查一次
   - 如果窗口内消息 >= 2条，触发分析
   ↓
6. Script Analyzer执行分析
   - 提取指标（聪明钱总量、平均MC、告警次数等）
   - 识别模式（4种内置模式）
   ↓
7. Strategy Generator生成策略
   - 转换分析结果为YAML策略
   - 保存到 config/strategies/generated/
   ↓
8. 策略可手动启用
   - 通过 /set_strategy 命令启用
```

## 📊 内置模式识别

### 1. high_smart_money_with_alerts
- **条件**: 聪明钱 > 100万 且 告警 >= 3次
- **置信度**: 0.8
- **策略建议**: 设置聪明钱阈值和告警阈值

### 2. low_mc_high_smart_money
- **条件**: 市值 < 100万 且 聪明钱 > 50万
- **置信度**: 0.75
- **策略建议**: 设置市值上限和聪明钱下限

### 3. rapid_mc_growth
- **条件**: 市值增长 > 50%
- **置信度**: 0.7
- **策略建议**: 设置市值增长阈值

### 4. high_smart_money_ratio
- **条件**: 聪明钱占比高
- **置信度**: 0.65
- **策略建议**: 基于聪明钱占比

## 🎯 使用示例

### 消息示例

```
10:00:00 - PEPE 聪明钱买入 200万
10:01:30 - PEPE MC 800万
10:02:15 - PEPE 告警 x3
10:03:00 - PEPE 聪明钱买入 150万
```

### 分析结果

- **Token**: PEPE
- **时间窗口**: 10:00:00 - 10:03:00 (3分钟)
- **消息数**: 4条
- **聪明钱总量**: 350万
- **平均市值**: 800万
- **告警次数**: 3次
- **识别模式**: high_smart_money_with_alerts
- **置信度**: 0.8

### 生成的策略

```yaml
name: high_smart_money_with_alerts_PEPE_1234567890
description: 聪明钱大量买入且多次告警
mode: kline
enabled: false
confidence: 0.8
conditions:
  - field: smart_money_buy
    operator: ">"
    value: 2800000.0
    description: 聪明钱买入超过 280.0万 USDT
  - field: alert_count
    operator: ">="
    value: 3
    description: 告警次数 >= 3
```

## 🔧 配置说明

### 启用分析层

在 `main.py` 中默认启用：
```python
bot = SignalBot(bot_token, enable_analysis=True)
```

### 配置参数

在 `config/analysis_config.yaml` 中配置：
- 时间窗口大小
- 最少消息数
- 策略生成阈值
- 自定义脚本路径

## 📝 后续扩展

### LLM分析器实现

需要实现以下方法：
1. `_build_prompt()` - 构建LLM Prompt
2. `_call_llm_api()` - 调用LLM API
3. `_parse_llm_response()` - 解析响应

### 自定义分析脚本

参考 `scripts/analyze_meme_example.py` 创建自定义脚本。

## 🐛 已知限制

1. **LLM分析器未实现**：接口已预留，但功能未实现
2. **策略自动启用**：生成的策略默认不启用，需要手动启用
3. **消息格式依赖**：需要消息格式符合解析模式
4. **历史数据**：分析基于时间窗口内的消息，不包含历史数据

## 📚 相关文档

- [分析层设计文档](ANALYSIS_LAYER_DESIGN.md)
- [使用指南](ANALYSIS_LAYER_USAGE.md)
- [架构文档](ARCHITECTURE.md)

