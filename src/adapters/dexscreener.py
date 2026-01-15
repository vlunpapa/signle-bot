"""
DexScreener 数据源适配器
支持新Meme币的K线数据获取
"""
import asyncio
import os
from typing import Optional, List
from datetime import datetime
import aiohttp
from loguru import logger

from src.core.datasource import (
    DataSourceAdapter,
    DataSourceMode,
    StandardKlineData
)
from src.core.rate_limiter import get_dexscreener_limiter


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
            # 使用 trust_env=True 以兼容系统级代理（如有）
            self.session = aiohttp.ClientSession(trust_env=True)
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
            intervals: K线周期列表，默认 ["1m", "5m", "15m"]
            
        Returns:
            list[StandardKlineData]: 多个周期的K线数据
        """
        if mode != DataSourceMode.KLINE:
            raise ValueError(f"DexScreener仅支持KLINE模式，当前模式: {mode}")
        
        if intervals is None:
            intervals = ["1m", "5m", "15m"]
        
        # 获取API限流器并等待可用令牌
        limiter = get_dexscreener_limiter()
        wait_time = await limiter.acquire()
        if wait_time > 0:
            logger.debug(f"DexScreener API限流：等待 {wait_time:.2f}秒后继续")
        
        session = await self._get_session()
        url = f"{self.BASE_URL}/tokens/{token}"
        
        # 读取代理配置：优先 DEX_PROXY_URL，其次 TG_PROXY_URL
        proxy_url = os.getenv("DEX_PROXY_URL") or os.getenv("TG_PROXY_URL")
        if proxy_url:
            logger.debug(f"DexScreener 通过代理请求: {proxy_url}")
        
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=8),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    logger.warning(f"DexScreener API错误: {response.status}")
                    return []
                
                data = await response.json()
                pairs = data.get("pairs", [])
                
                if not pairs:
                    logger.warning(f"未找到token: {token}")
                    return []
                
                logger.info(f"DexScreener找到 {len(pairs)} 个交易对: {token}")
                
                # 选择流动性最好的交易对
                pair = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
                logger.debug(f"选择交易对: {pair.get('baseToken', {}).get('symbol', 'N/A')}/{pair.get('quoteToken', {}).get('symbol', 'N/A')}, 流动性: ${pair.get('liquidity', {}).get('usd', 0):,.0f}")
                
                # 详细记录原始数据（特别是volume和txns）
                volume_raw = pair.get("volume", {})
                txns_raw = pair.get("txns", {})
                logger.info(f"DexScreener原始数据 - volume: {volume_raw}, txns: {txns_raw}, priceChange: {pair.get('priceChange', {})}")
                
                # 转换DexScreener数据为标准K线格式
                klines = []
                for interval in intervals:
                    kline = self._convert_to_standard_kline(pair, interval)
                    if kline:
                        klines.append(kline)
                        logger.debug(f"成功转换K线数据: {interval}, 价格={kline.close}, 成交量={kline.volume}")
                    else:
                        logger.warning(f"K线转换失败: {interval}, token={token}")
                
                logger.info(f"DexScreener成功获取 {len(klines)}/{len(intervals)} 个周期的K线数据: {token}")
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
            
            price_str = pair_data.get("priceUsd", "0")
            price = float(price_str) if price_str else 0
            if price == 0:
                logger.warning(f"价格为0，无法转换: {symbol}")
                return None
            
            # DexScreener的volume可能是对象或直接值
            # 根据interval选择对应的数据：1m -> m1, 5m -> m5, 15m -> h1
            volume_data = pair_data.get("volume", {})
            price_change_data = pair_data.get("priceChange", {})
            
            # 映射interval到DexScreener的数据键
            interval_map = {
                "1m": "m1",  # 1分钟数据
                "5m": "m5",  # 5分钟数据
                "15m": "h1",  # 15分钟数据（使用1小时数据作为近似）
            }
            data_key = interval_map.get(interval, "h24")
            
            # 对于1分钟数据，如果m1不存在，回退到m5
            fallback_key = "m5" if interval == "1m" else "h24"
            
            if isinstance(volume_data, dict):
                volume = float(volume_data.get(data_key, volume_data.get(fallback_key, volume_data.get("h24", 0))) or 0)
                if interval == "1m" and data_key not in volume_data and fallback_key in volume_data:
                    logger.debug(f"1分钟K线数据使用m5回退: interval={interval}, data_key={data_key}, fallback={fallback_key}")
                logger.info(f"从DexScreener提取交易量: interval={interval}, data_key={data_key}, volume={volume}, 原始volume_data={volume_data}")
            else:
                volume = float(volume_data or 0)
                logger.info(f"从DexScreener提取交易量: interval={interval}, volume={volume} (非字典格式)")
            
            # 获取价格变化
            price_change_24h = None
            if isinstance(price_change_data, dict):
                price_change_24h = float(price_change_data.get(data_key, price_change_data.get(fallback_key, price_change_data.get("h24", 0))) or 0)
            
            # 处理交易笔数
            txns_data = pair_data.get("txns", {})
            txns = 0
            if isinstance(txns_data, dict):
                period_txns = txns_data.get(data_key, txns_data.get(fallback_key, txns_data.get("h24", {})))
                if isinstance(period_txns, dict):
                    buys = int(period_txns.get("buys", 0) or 0)
                    sells = int(period_txns.get("sells", 0) or 0)
                    txns = buys + sells
            
            # 提取Token合约地址（CA）
            token_address = base_token.get("address")
            
            # 提取市值（Market Cap）
            # DexScreener API可能包含fdv（Fully Diluted Valuation）或marketCap字段
            market_cap = None
            if "fdv" in pair_data:
                market_cap = float(pair_data.get("fdv", 0) or 0)
            elif "marketCap" in pair_data:
                market_cap = float(pair_data.get("marketCap", 0) or 0)
            elif base_token.get("marketCap"):
                market_cap = float(base_token.get("marketCap", 0) or 0)
            
            logger.debug(f"转换K线数据: {symbol}, 价格={price}, 成交量={volume}, 交易笔数={txns}, 周期={interval}, CA={token_address}, MC={market_cap}")
            
            # DexScreener不提供历史K线，使用当前价格作为OHLC
            # 实际项目中可以调用DexScreener的K线API获取历史数据
            kline = StandardKlineData(
                symbol=symbol,
                interval=interval,
                timestamp=datetime.now(),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                quote_volume=volume * price,
                txns=txns,
                price_change_24h=price_change_24h,
                market_cap=market_cap,
                token_address=token_address
            )
            logger.debug(f"K线数据转换成功: {symbol}, {interval}")
            return kline
        except Exception as e:
            logger.error(f"转换DexScreener数据失败: {e}, pair_data keys={list(pair_data.keys()) if isinstance(pair_data, dict) else 'N/A'}")
            import traceback
            logger.error(traceback.format_exc())
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

