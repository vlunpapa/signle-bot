# 🏗️ Telegram 驱动型多源量价信号机器人 - 架构设计

## 📊 系统架构图

```mermaid
graph TB
    subgraph Input["📥 输入层"]
        TG1["Telegram 群组1<br/>Meme币讨论"]
        TG2["Telegram 群组2<br/>山寨币分析"]
        TG3["Telegram 群组3<br/>链上监控"]
    end

    subgraph Listener["👂 监听层"]
        MSG_LISTENER["Message Listener<br/>异步消息监听"]
        EXTRACTOR["Token Extractor<br/>提取 $TICKER / 地址"]
    end

    subgraph Config["⚙️ 配置层"]
        USER_CONFIG["User Config<br/>SQLite/JSON<br/>数据源模式/策略参数"]
        STRATEGY_YAML["Strategy YAML<br/>自定义策略定义"]
    end

    subgraph DataSource["📊 数据源层 (Adapter Pattern)"]
        ADAPTER["DataSource Adapter<br/>统一接口 Protocol"]
        
        subgraph ModeA["模式A: K线优先"]
            DEX["DexScreener API<br/>新Meme币"]
            BYBIT["Bybit API<br/>热门山寨"]
            BINANCE["Binance API<br/>主流币"]
        end
        
        subgraph ModeB["模式B: 链上优先"]
            HELIUS["Helius Webhook<br/>实时交易流"]
            RPC["Solana RPC<br/>Fallback查询"]
        end
        
        ADAPTER --> DEX
        ADAPTER --> BYBIT
        ADAPTER --> BINANCE
        ADAPTER --> HELIUS
        ADAPTER --> RPC
    end

    subgraph Strategy["🧠 策略引擎"]
        BUILTIN["内置策略<br/>量增价升/缩量新高/天量见顶"]
        YAML_ENGINE["YAML策略解析器<br/>条件表达式执行"]
        STRATEGY_EXEC["Strategy Executor<br/>异步无阻塞计算"]
    end

    subgraph Output["📤 输出层"]
        NOTIFIER["Notifier<br/>消息格式化"]
        JINJA2["Jinja2 模板引擎<br/>自定义消息模板"]
        TG_BOT["Telegram Bot<br/>推送 + 深度图"]
    end

    TG1 --> MSG_LISTENER
    TG2 --> MSG_LISTENER
    TG3 --> MSG_LISTENER
    
    MSG_LISTENER --> EXTRACTOR
    EXTRACTOR --> USER_CONFIG
    EXTRACTOR --> ADAPTER
    
    USER_CONFIG --> ADAPTER
    USER_CONFIG --> STRATEGY
    STRATEGY_YAML --> YAML_ENGINE
    
    ADAPTER --> STRATEGY
    STRATEGY --> BUILTIN
    STRATEGY --> YAML_ENGINE
    BUILTIN --> STRATEGY_EXEC
    YAML_ENGINE --> STRATEGY_EXEC
    
    STRATEGY_EXEC --> NOTIFIER
    NOTIFIER --> JINJA2
    JINJA2 --> TG_BOT
    
    style ModeA fill:#e1f5ff
    style ModeB fill:#fff4e1
    style ADAPTER fill:#f0f0f0
    style STRATEGY fill:#e8f5e9
```

## 🔄 数据流图

```mermaid
sequenceDiagram
    participant TG as Telegram群组
    participant Listener as Message Listener
    participant Extractor as Token Extractor
    participant Config as User Config
    participant Adapter as DataSource Adapter
    participant DexScreener as DexScreener API
    participant Strategy as Strategy Engine
    participant Notifier as Notifier
    participant Bot as Telegram Bot

    TG->>Listener: 新消息: "$PEPE 要起飞了！"
    Listener->>Extractor: 提取Token
    Extractor->>Extractor: 正则匹配: $PEPE / 0x...
    Extractor->>Config: 查询用户数据源模式
    Config-->>Extractor: mode: "kline"
    
    Extractor->>Adapter: get_data(token, mode="kline")
    Adapter->>DexScreener: fetch_klines(token, intervals=[1m,5m,15m])
    DexScreener-->>Adapter: OHLCV + txns数据
    Adapter->>Adapter: 转换为标准K线格式
    Adapter-->>Strategy: StandardKlineData
    
    Strategy->>Strategy: 执行内置策略
    Strategy->>Strategy: 执行YAML策略
    Strategy-->>Notifier: SignalResult
    
    Notifier->>Notifier: Jinja2渲染模板
    Notifier->>Bot: 发送消息+深度图
    Bot->>TG: 推送信号通知
```

## 🎯 模式切换点

```mermaid
graph LR
    A[用户命令<br/>/set_datasource] --> B{模式选择}
    B -->|kline| C[模式A: K线优先]
    B -->|onchain| D[模式B: 链上优先]
    
    C --> E[DexScreener<br/>Bybit<br/>Binance]
    D --> F[Helius Webhook<br/>Solana RPC]
    
    E --> G[StandardKlineData]
    F --> H[OnChainData]
    
    G --> I[Strategy Adapter]
    H --> I
    
    I --> J[统一策略执行]
```

## 📦 模块职责

| 模块 | 职责 | 延迟要求 |
|------|------|----------|
| **Listener** | 监听Telegram消息，异步处理 | < 1s |
| **Extractor** | 提取Token/地址，支持多种格式 | < 0.5s |
| **DataSource Adapter** | 统一数据接口，模式切换 | K线: ≤8s, 链上: ≤3s |
| **Strategy Engine** | 策略计算，支持内置+YAML | 异步无阻塞 |
| **Notifier** | 消息格式化，模板渲染 | < 1s |
| **Config Manager** | 配置持久化，用户设置管理 | 内存缓存 |

## 🔌 接口定义

### DataSource Adapter Protocol

```python
from typing import Protocol, Optional
from datetime import datetime
from enum import Enum

class DataSourceMode(Enum):
    KLINE = "kline"
    ONCHAIN = "onchain"

class StandardKlineData:
    """标准K线数据结构"""
    symbol: str
    interval: str  # 1m, 5m, 15m
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    txns: Optional[int]  # 交易笔数

class OnChainData:
    """链上数据结构"""
    token_address: str
    timestamp: datetime
    buy_volume: float
    sell_volume: float
    total_volume: float
    price: float
    whale_addresses: list[str]
    wash_trading_flag: bool

class DataSourceAdapter(Protocol):
    """数据源适配器接口"""
    
    async def get_data(
        self,
        token: str,
        mode: DataSourceMode,
        intervals: list[str] = None
    ) -> StandardKlineData | OnChainData:
        """获取数据，返回统一格式"""
        ...
    
    async def is_available(self, token: str) -> bool:
        """检查数据源是否可用"""
        ...
```

## 🚀 性能指标

| 指标 | 目标值 |
|------|--------|
| K线模式延迟 | ≤ 8s |
| 链上模式延迟 | ≤ 3s (Webhook) |
| 策略计算时间 | < 100ms |
| 消息推送延迟 | < 1s |
| 并发处理能力 | 100+ tokens/min |

