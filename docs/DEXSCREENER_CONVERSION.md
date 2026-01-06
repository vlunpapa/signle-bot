# DexScreener → Standard K线 转换伪代码

## API 响应格式

DexScreener API 返回的数据结构：

```json
{
  "pairs": [
    {
      "chainId": "solana",
      "dexId": "raydium",
      "url": "https://dexscreener.com/solana/...",
      "pairAddress": "0x...",
      "baseToken": {
        "symbol": "PEPE",
        "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "name": "Pepe"
      },
      "quoteToken": {
        "symbol": "USDC",
        "address": "...",
        "name": "USD Coin"
      },
      "priceNative": "0.000001",
      "priceUsd": "0.000001",
      "txns": {
        "m5": {"buys": 10, "sells": 5},
        "h1": {"buys": 100, "sells": 50},
        "h6": {"buys": 500, "sells": 250},
        "h24": {"buys": 1000, "sells": 500}
      },
      "volume": {
        "m5": 10000,
        "h1": 100000,
        "h6": 500000,
        "h24": 2000000
      },
      "priceChange": {
        "m5": 5.2,
        "h1": 10.5,
        "h6": -2.3,
        "h24": 25.8
      },
      "liquidity": {
        "usd": 500000
      },
      "fdv": 10000000,
      "pairCreatedAt": 1234567890
    }
  ]
}
```

## 转换伪代码

```python
def convert_dexscreener_to_standard_kline(
    pair_data: dict,
    interval: str  # "5m", "15m", "1h"
) -> StandardKlineData:
    """
    将DexScreener数据转换为标准K线格式
    
    参数映射：
    - interval="5m"  -> 使用 m5 数据
    - interval="15m" -> 使用 h1 数据（近似）
    - interval="1h"  -> 使用 h1 数据
    """
    
    # 1. 提取基础信息
    base_token = pair_data["baseToken"]
    quote_token = pair_data["quoteToken"]
    symbol = f"{base_token['symbol']}/{quote_token['symbol']}"
    
    # 2. 根据周期选择数据源
    interval_map = {
        "5m": "m5",
        "15m": "h1",  # 近似使用1小时数据
        "1h": "h1"
    }
    data_key = interval_map.get(interval, "h1")
    
    # 3. 提取价格数据
    current_price = float(pair_data["priceUsd"])
    
    # 4. 计算价格变化（用于估算OHLC）
    price_change_pct = pair_data["priceChange"].get(data_key, 0) / 100
    
    # 估算开盘价（假设价格变化是相对于开盘价的）
    if price_change_pct > 0:
        open_price = current_price / (1 + price_change_pct)
    else:
        open_price = current_price / (1 + price_change_pct)
    
    # 估算最高/最低价（简化处理）
    high_price = max(current_price, open_price) * 1.02  # 假设2%波动
    low_price = min(current_price, open_price) * 0.98
    
    # 5. 提取成交量
    volume_data = pair_data["volume"]
    volume = float(volume_data.get(data_key, volume_data.get("h24", 0)))
    
    # 6. 提取交易笔数
    txns_data = pair_data["txns"]
    txn_period = txns_data.get(data_key, txns_data.get("h24", {}))
    txns = txn_period.get("buys", 0) + txn_period.get("sells", 0)
    
    # 7. 计算成交额
    quote_volume = volume * current_price
    
    # 8. 获取时间戳
    timestamp = datetime.now()  # 或使用 pairCreatedAt
    
    # 9. 构建标准K线数据
    return StandardKlineData(
        symbol=symbol,
        interval=interval,
        timestamp=timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=current_price,
        volume=volume,
        quote_volume=quote_volume,
        txns=txns
    )
```

## 实际实现（Python）

参考 `src/adapters/dexscreener.py` 中的 `_convert_to_standard_kline` 方法。

## 注意事项

1. **历史K线数据**: DexScreener免费API不提供历史K线，只能获取当前价格和24小时统计数据
2. **OHLC估算**: 由于缺少历史数据，OHLC值需要估算或使用当前价格
3. **周期映射**: 15分钟周期需要近似使用1小时数据
4. **实时性**: 建议使用WebSocket获取实时价格更新

## 改进方案

如果需要更准确的K线数据：

1. **使用DexScreener Pro API**: 提供历史K线数据
2. **直接查询链上数据**: 从Solana/Ethereum RPC获取交易历史
3. **使用其他数据源**: 如Birdeye、Jupiter等提供更详细的K线数据

