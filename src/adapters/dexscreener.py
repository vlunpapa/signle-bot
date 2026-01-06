"""
DexScreener 数据源适配器
支持新Meme币的K线数据获取
"""
import asyncio
from typing import Optional, list
from datetime import datetime
import aiohttp
from loguru import logger

from src.core.datasource import (
    DataSourceAdapter,
    DataSourceMode,
    StandardKlineData
)


class DexScreenerAdapter(DataSourceAdapter):
    """DexScreener API 适配器"""
    
    BASE_URL = "https://api.dexscreener.com/latest/dex"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化
        
        Args:
            api_key: API密钥（可选，DexScreener免费版不需要）
        """
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_data(
        self,
        token: str,
        mode: DataSourceMode,
        intervals: Optional[list[str]] = None
    ) -> list[StandardKlineData]:
        """
        从DexScreener获取K线数据
        
        Args:
            token: Token合约地址（Solana/以太坊等）
            mode: 数据源模式（仅支持KLINE）
            intervals: K线周期列表，默认 ["5m", "15m", "1h"]
            
        Returns:
            list[StandardKlineData]: 多个周期的K线数据
        """
        if mode != DataSourceMode.KLINE:
            raise ValueError(f"DexScreener仅支持KLINE模式，当前模式: {mode}")
        
        if intervals is None:
            intervals = ["5m", "15m", "1h"]
        
        session = await self._get_session()
        url = f"{self.BASE_URL}/tokens/{token}"
        
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
                if response.status != 200:
                    logger.warning(f"DexScreener API错误: {response.status}")
                    return []
                
                data = await response.json()
                pairs = data.get("pairs", [])
                
                if not pairs:
                    logger.warning(f"未找到token: {token}")
                    return []
                
                # 选择流动性最好的交易对
                pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
                
                # 转换DexScreener数据为标准K线格式
                klines = []
                for interval in intervals:
                    kline = self._convert_to_standard_kline(pair, interval)
                    if kline:
                        klines.append(kline)
                
                return klines
                
        except asyncio.TimeoutError:
            logger.error(f"DexScreener请求超时: {token}")
            return []
        except Exception as e:
            logger.error(f"DexScreener获取数据失败: {e}")
            return []
    
    def _convert_to_standard_kline(
        self,
        pair_data: dict,
        interval: str
    ) -> Optional[StandardKlineData]:
        """
        将DexScreener数据转换为标准K线格式
        
        DexScreener API 返回格式:
        {
            "pairAddress": "0x...",
            "baseToken": {"symbol": "PEPE", "address": "0x..."},
            "quoteToken": {"symbol": "USDT", "address": "0x..."},
            "priceUsd": "0.000001",
            "priceChange": {"h24": 10.5},
            "volume": {"h24": 1000000},
            "txns": {"h24": {"buys": 100, "sells": 50}},
            "liquidity": {"usd": 500000}
        }
        
        转换为:
        StandardKlineData(
            symbol="PEPE/USDT",
            interval="5m",
            timestamp=now(),
            open=price,
            high=price,
            low=price,
            close=price,
            volume=volume.h24,
            txns=txns.h24.buys + txns.h24.sells
        )
        """
        try:
            base_token = pair_data.get("baseToken", {})
            quote_token = pair_data.get("quoteToken", {})
            symbol = f"{base_token.get('symbol', 'UNKNOWN')}/{quote_token.get('symbol', 'USDT')}"
            
            price = float(pair_data.get("priceUsd", 0))
            if price == 0:
                return None
            
            volume_data = pair_data.get("volume", {})
            volume = float(volume_data.get("h24", 0))
            
            txns_data = pair_data.get("txns", {})
            h24_txns = txns_data.get("h24", {})
            txns = h24_txns.get("buys", 0) + h24_txns.get("sells", 0)
            
            # DexScreener不提供历史K线，使用当前价格作为OHLC
            # 实际项目中可以调用DexScreener的K线API获取历史数据
            return StandardKlineData(
                symbol=symbol,
                interval=interval,
                timestamp=datetime.now(),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                quote_volume=volume * price,
                txns=txns
            )
        except Exception as e:
            logger.error(f"转换DexScreener数据失败: {e}")
            return None
    
    async def is_available(self, token: str) -> bool:
        """检查token是否在DexScreener上可用"""
        try:
            klines = await self.get_data(token, DataSourceMode.KLINE, ["5m"])
            return len(klines) > 0
        except Exception:
            return False
    
    def get_source_name(self) -> str:
        return "DexScreener"
    
    def supports_mode(self, mode: DataSourceMode) -> bool:
        return mode == DataSourceMode.KLINE
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()

