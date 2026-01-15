"""
Helius 数据源适配器
支持Solana链上数据获取，通过交易历史计算K线数据
"""
import asyncio
import os
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
import aiohttp
from loguru import logger

from src.core.datasource import (
    DataSourceAdapter,
    DataSourceMode,
    StandardKlineData,
    OnChainData
)
from src.core.rate_limiter import RateLimiter


# 全局Helius限流器实例
_helius_limiter: Optional[RateLimiter] = None


def get_helius_limiter() -> RateLimiter:
    """
    获取Helius API限流器（单例模式）
    
    注意：Helius免费计划限制：
    - RPC API: 10 req/s
    - DAS API: 2 req/s
    - 增强API: 2 req/s
    
    当前限流器设置为RPC限制（10 req/s），因为getAsset使用RPC端点
    
    Returns:
        RateLimiter: 限流器实例（每秒10次，RPC限制）
    """
    global _helius_limiter
    if _helius_limiter is None:
        # Helius免费计划RPC限制：每秒10次请求
        # 注意：DAS API和增强API限制为2 req/s，但getAsset使用RPC端点
        _helius_limiter = RateLimiter(max_calls=10, time_window=1.0)
        logger.info("初始化Helius API限流器：每秒10次请求（RPC限制）")
    return _helius_limiter


class HeliusAdapter(DataSourceAdapter):
    """Helius API 适配器（Solana链上数据）"""
    
    BASE_URL = "https://api.helius.xyz/v0"
    RPC_URL = "https://api.helius.xyz/v0/rpc"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化
        
        Args:
            api_key: Helius API密钥（从环境变量HELIUS_API_KEY读取）
        """
        self.api_key = api_key or os.getenv("HELIUS_API_KEY")
        if not self.api_key:
            logger.warning("未配置HELIUS_API_KEY，Helius适配器可能无法正常工作")
        
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(trust_env=True)
        return self.session
    
    @staticmethod
    def _is_solana_address(address: str) -> bool:
        """
        检查是否为Solana地址格式
        
        Solana地址特征：
        - 长度：32-44字符
        - 字符集：Base58编码（1-9A-HJ-NP-Za-km-z）
        """
        if not address or len(address) < 32 or len(address) > 44:
            return False
        # 简单检查：Base58字符集
        base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
        return all(c in base58_chars for c in address)
    
    async def get_data(
        self,
        token: str,
        mode: DataSourceMode,
        intervals: Optional[list[str]] = None
    ) -> Union[list[StandardKlineData], OnChainData]:
        """
        从Helius获取数据
        
        Args:
            token: Solana代币合约地址（mint address）
            mode: 数据源模式（支持KLINE和ONCHAIN）
            intervals: K线周期列表，默认 ["1m", "5m", "15m"]
            
        Returns:
            K线模式: list[StandardKlineData]
            链上模式: OnChainData
        """
        if not self.api_key:
            logger.error("Helius API密钥未配置")
            return [] if mode == DataSourceMode.KLINE else None
        
        # 检查是否为Solana地址
        if not self._is_solana_address(token):
            logger.warning(f"不是有效的Solana地址: {token}")
            return [] if mode == DataSourceMode.KLINE else None
        
        if intervals is None:
            intervals = ["1m", "5m", "15m"]
        
        if mode == DataSourceMode.KLINE:
            return await self._get_kline_data(token, intervals)
        elif mode == DataSourceMode.ONCHAIN:
            return await self._get_onchain_data(token)
        else:
            raise ValueError(f"不支持的模式: {mode}")
    
    async def _get_kline_data(
        self,
        token: str,
        intervals: List[str]
    ) -> List[StandardKlineData]:
        """
        获取K线数据（通过交易历史计算）
        
        优化：只返回1m K线，移除5m和15m
        
        Args:
            token: Solana代币合约地址
            intervals: K线周期列表（现在只支持1m）
            
        Returns:
            List[StandardKlineData]: K线数据列表（只包含1m）
        """
        # 只处理1m周期，忽略其他周期
        if "1m" not in intervals:
            logger.warning(f"Helius只支持1m K线，忽略其他周期: {intervals}")
            return []
        
        logger.info(f"Helius获取K线数据: {token}, 只返回1m周期")
        
        # 获取API限流器并等待可用令牌
        limiter = get_helius_limiter()
        wait_time = await limiter.acquire()
        if wait_time > 0:
            logger.debug(f"Helius API限流：等待 {wait_time:.2f}秒后继续")
        
        try:
            # 步骤1：获取代币元数据
            token_metadata = await self._get_token_metadata(token)
            if not token_metadata:
                logger.warning(f"无法获取代币元数据: {token}")
                return []
            
            symbol = token_metadata.get("symbol", "UNKNOWN")
            
            # 步骤2：获取当前价格（通过RPC查询）
            current_price = await self._get_current_price(token)
            if current_price is None or current_price == 0:
                logger.warning(f"无法获取代币价格: {token}")
                return []
            
            # 步骤3：获取交易历史（用于计算1m K线）
            # 获取最近10分钟的交易数据，用于构造10根1m K线
            transactions = await self._get_recent_transactions(token, minutes=10)
            
            if not transactions:
                logger.warning(f"未获取到交易历史数据，将使用当前价格作为占位: {token}")
                # 即使没有交易历史，也返回基于当前价格的K线数据
            
            # 步骤4：计算1m K线数据
            kline = self._calculate_kline(
                token=token,
                symbol=symbol,
                interval="1m",
                transactions=transactions,
                current_price=current_price
            )
            
            if kline:
                logger.info(f"Helius成功获取1m K线数据: {token}")
                return [kline]
            else:
                logger.warning(f"Helius计算K线数据失败: {token}")
                return []
            
        except Exception as e:
            logger.error(f"Helius获取K线数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    async def _get_onchain_data(self, token: str) -> Optional[OnChainData]:
        """
        获取链上数据
        
        注意：这是一个简化实现，实际需要：
        1. 获取交易历史
        2. 分析买卖方向
        3. 计算真实买卖量
        4. 识别大户地址
        """
        logger.info(f"Helius获取链上数据: {token}")
        
        # 获取API限流器
        limiter = get_helius_limiter()
        await limiter.acquire()
        
        try:
            # 获取最近24小时的交易数据
            transactions = await self._get_recent_transactions(token, minutes=24 * 60)
            
            # 分析交易数据
            buy_volume = 0.0
            sell_volume = 0.0
            total_volume = 0.0
            whale_addresses = []
            
            # 简化实现：假设所有交易都是买入（实际需要分析交易方向）
            for tx in transactions:
                volume = tx.get("volume", 0)
                total_volume += volume
                # 这里需要根据实际交易数据判断买卖方向
                # 暂时假设为买入
                buy_volume += volume
            
            # 获取当前价格
            current_price = await self._get_current_price(token)
            
            return OnChainData(
                token_address=token,
                timestamp=datetime.now(),
                buy_volume=buy_volume,
                sell_volume=sell_volume,
                total_volume=total_volume,
                price=current_price or 0.0,
                whale_addresses=whale_addresses,
                wash_trading_flag=False
            )
            
        except Exception as e:
            logger.error(f"Helius获取链上数据失败: {e}")
            return None
    
    async def _get_token_metadata(self, token: str) -> Optional[Dict[str, Any]]:
        """
        获取代币元数据（使用getAsset方法，同时获取元数据和价格）
        
        Args:
            token: Solana代币合约地址（mint address）
            
        Returns:
            dict: 代币元数据，包含symbol、name、price_info等信息
        """
        if not self.api_key:
            return None
        
        session = await self._get_session()
        # 使用mainnet RPC端点
        url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        
        proxy_url = os.getenv("HELIUS_PROXY_URL") or os.getenv("TG_PROXY_URL")
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getAsset",
                "params": {
                    "id": token,
                    "displayOptions": {
                        "showFungible": True
                    }
                }
            }
            
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    logger.warning(f"Helius代币元数据API错误: {response.status}")
                    return None
                
                data = await response.json()
                
                # 检查是否有错误
                if "error" in data:
                    logger.warning(f"Helius代币元数据查询错误: {data.get('error', {}).get('message', 'Unknown error')}")
                    return None
                
                result = data.get("result", {})
                if not result:
                    return None
                
                # 提取元数据信息
                token_info = result.get("token_info", {})
                content = result.get("content", {})
                metadata = content.get("metadata", {})
                
                # 构建元数据字典
                metadata_dict = {
                    "symbol": token_info.get("symbol") or metadata.get("symbol"),
                    "name": token_info.get("name") or metadata.get("name"),
                    "decimals": token_info.get("decimals"),
                    "supply": token_info.get("supply"),
                    "price_info": token_info.get("price_info"),
                }
                
                logger.debug(f"Helius获取代币元数据成功: {token}, symbol={metadata_dict.get('symbol')}")
                return metadata_dict
                
        except Exception as e:
            logger.error(f"获取代币元数据失败: {e}")
            return None
    
    async def _get_current_price(self, token: str) -> Optional[float]:
        """
        获取当前价格（通过Helius RPC getAsset方法）
        
        Args:
            token: Solana代币合约地址（mint address）
            
        Returns:
            float: 代币价格（USD），如果获取失败返回None
        """
        if not self.api_key:
            logger.warning("Helius API密钥未配置，无法获取价格")
            return None
        
        session = await self._get_session()
        # 使用mainnet RPC端点
        url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        
        proxy_url = os.getenv("HELIUS_PROXY_URL") or os.getenv("TG_PROXY_URL")
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getAsset",
                "params": {
                    "id": token,
                    "displayOptions": {
                        "showFungible": True
                    }
                }
            }
            
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    logger.warning(f"Helius价格查询API错误: {response.status}")
                    return None
                
                data = await response.json()
                
                # 检查是否有错误
                if "error" in data:
                    logger.warning(f"Helius价格查询错误: {data.get('error', {}).get('message', 'Unknown error')}")
                    return None
                
                # 解析价格信息
                result = data.get("result", {})
                token_info = result.get("token_info", {})
                price_info = token_info.get("price_info", {})
                
                if not price_info:
                    logger.debug(f"Helius未返回价格信息: {token}")
                    return None
                
                price_per_token = price_info.get("price_per_token")
                currency = price_info.get("currency", "USDC")
                
                if price_per_token is None:
                    logger.debug(f"Helius价格信息为空: {token}")
                    return None
                
                price = float(price_per_token)
                logger.debug(f"Helius获取价格成功: {token}, 价格={price} {currency}")
                
                # 如果价格单位不是USD，可能需要转换（当前假设USDC≈USD）
                # 实际项目中可能需要根据currency进行转换
                return price
                
        except asyncio.TimeoutError:
            logger.error(f"Helius价格查询超时: {token}")
            return None
        except Exception as e:
            logger.error(f"Helius获取价格失败: {token}, error={e}")
            return None
    
    async def _get_recent_transactions(
        self,
        token: str,
        minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取最近的交易历史（使用Enhanced Transactions API）
        
        优化：使用POST方式，正确的时间过滤，减少400错误
        
        Args:
            token: Solana代币合约地址（mint address）
            minutes: 获取最近多少分钟的交易历史（默认10分钟）
            
        Returns:
            List[Dict]: 交易历史列表，每个交易包含price和volume字段
        """
        if not self.api_key:
            logger.warning("Helius API密钥未配置，无法获取交易历史")
            return []
        
        session = await self._get_session()
        # 使用Enhanced Transactions API端点（GET方式）
        # 正确端点：/v0/addresses/{address}/transactions
        url = f"{self.BASE_URL}/addresses/{token}/transactions"
        
        proxy_url = os.getenv("HELIUS_PROXY_URL") or os.getenv("TG_PROXY_URL")
        
        try:
            # 计算时间范围（Unix时间戳，秒）
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=minutes)
            
            # Enhanced Transactions API使用GET方式，api-key作为查询参数
            params = {
                "api-key": self.api_key,
                "limit": 1000,  # 最大1000条
            }
            
            # 注意：Helius Enhanced Transactions API可能不支持直接的时间过滤
            # 我们会在获取后手动过滤时间范围
            
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),  # 缩短超时时间，快速失败
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status == 400:
                    # 400错误，可能是参数问题，fallback到RPC
                    logger.debug(f"Enhanced Transactions返回400，fallback到RPC方式")
                    return await self._get_transactions_via_rpc(token, minutes)
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.warning(
                        f"Helius交易历史API错误: {response.status}, "
                        f"响应: {error_text[:200]}, token={token}"
                    )
                    # 如果Enhanced失败，fallback到RPC（但记录警告）
                    logger.warning(f"Enhanced Transactions失败，fallback到RPC方式: {token}")
                    return await self._get_transactions_via_rpc(token, minutes)
                
                data = await response.json()
                
                # 解析交易数据
                transactions = data if isinstance(data, list) else data.get("transactions", [])
                
                # 过滤时间范围（API可能返回超出时间范围的交易）
                filtered_transactions = []
                for tx in transactions:
                    tx_time = self._parse_transaction_time_from_enhanced(tx)
                    if tx_time and start_time <= tx_time <= end_time:
                        parsed_tx = self._parse_transaction(tx, token)
                        if parsed_tx:
                            filtered_transactions.append(parsed_tx)
                
                logger.info(
                    f"Helius Enhanced Transactions成功: token={token}, "
                    f"原始交易数={len(transactions)}, "
                    f"过滤后={len(filtered_transactions)}, "
                    f"时间窗口={minutes}分钟"
                )
                return filtered_transactions
                
        except asyncio.TimeoutError:
            logger.error(f"Helius交易历史查询超时: {token}")
            # 超时也fallback到RPC
            return await self._get_transactions_via_rpc(token, minutes)
        except Exception as e:
            logger.error(f"获取交易历史失败: {e}, token={token}")
            import traceback
            logger.debug(traceback.format_exc())
            # 异常时fallback到RPC
            return await self._get_transactions_via_rpc(token, minutes)
    
    async def _get_recent_transactions_get(
        self,
        token: str,
        minutes: int = 10
    ) -> List[Dict[str, Any]]:
        """
        使用GET方式获取交易历史（兼容旧版本API）
        
        Args:
            token: Solana代币合约地址
            minutes: 获取最近多少分钟的交易历史
            
        Returns:
            List[Dict]: 交易历史列表
        """
        if not self.api_key:
            return []
        
        session = await self._get_session()
        url = f"{self.BASE_URL}/addresses/{token}/transactions"
        
        proxy_url = os.getenv("HELIUS_PROXY_URL") or os.getenv("TG_PROXY_URL")
        
        try:
            params = {
                "api-key": self.api_key,
                "limit": 1000,
            }
            
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    logger.debug(f"Enhanced Transactions GET返回{response.status}，fallback到RPC")
                    return await self._get_transactions_via_rpc(token, minutes)
                
                data = await response.json()
                transactions = data if isinstance(data, list) else data.get("transactions", [])
                
                # 过滤时间范围
                end_time = datetime.now()
                start_time = end_time - timedelta(minutes=minutes)
                filtered_transactions = []
                
                for tx in transactions:
                    tx_time = self._parse_transaction_time_from_enhanced(tx)
                    if tx_time and start_time <= tx_time <= end_time:
                        parsed_tx = self._parse_transaction(tx, token)
                        if parsed_tx:
                            filtered_transactions.append(parsed_tx)
                
                logger.info(
                    f"Helius Enhanced Transactions GET成功: token={token}, "
                    f"交易数={len(filtered_transactions)}"
                )
                return filtered_transactions
                
        except Exception as e:
            logger.debug(f"Enhanced Transactions GET失败: {e}，fallback到RPC")
            return await self._get_transactions_via_rpc(token, minutes)
    
    def _parse_transaction_time_from_enhanced(self, tx: Dict[str, Any]) -> Optional[datetime]:
        """
        从Enhanced Transactions API返回的交易数据中解析时间
        
        Args:
            tx: Enhanced Transactions API返回的交易数据
            
        Returns:
            datetime: 交易时间，如果解析失败返回None
        """
        try:
            # 尝试多种可能的时间字段
            timestamp = tx.get("timestamp") or tx.get("blockTime") or tx.get("time")
            
            if timestamp:
                if isinstance(timestamp, (int, float)):
                    # 判断是秒还是毫秒
                    if timestamp > 1e10:
                        timestamp = timestamp / 1000
                    return datetime.fromtimestamp(timestamp)
                elif isinstance(timestamp, str):
                    # ISO格式字符串
                    try:
                        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except:
                        pass
            
            return None
        except Exception:
            return None
    
    async def _get_transactions_via_rpc(
        self,
        token: str,
        minutes: int = 15
    ) -> List[Dict[str, Any]]:
        """
        通过RPC方式获取交易历史（备用方案）
        
        使用getSignaturesForAddress RPC方法获取交易签名，
        然后通过getTransaction获取交易详情
        """
        if not self.api_key:
            return []
        
        session = await self._get_session()
        rpc_url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        
        proxy_url = os.getenv("HELIUS_PROXY_URL") or os.getenv("TG_PROXY_URL")
        
        try:
            # 步骤1：获取交易签名列表
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getSignaturesForAddress",
                "params": [
                    token,
                    {
                        "limit": 1000
                    }
                ]
            }
            
            async with session.post(
                rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    logger.warning(f"RPC获取交易签名失败: {response.status}")
                    return []
                
                data = await response.json()
                if "error" in data:
                    logger.warning(f"RPC错误: {data.get('error', {}).get('message', 'Unknown error')}")
                    return []
                
                signatures = data.get("result", [])
                if not signatures:
                    logger.debug(f"未找到交易签名: {token}")
                    return []
                
                # 过滤时间范围
                end_time = datetime.now()
                start_time = end_time - timedelta(minutes=minutes)
                filtered_signatures = []
                
                for sig_info in signatures:
                    block_time = sig_info.get("blockTime")
                    if block_time:
                        tx_time = datetime.fromtimestamp(block_time)
                        if start_time <= tx_time <= end_time:
                            filtered_signatures.append(sig_info.get("signature"))
                
                if not filtered_signatures:
                    logger.debug(f"时间范围内无交易: {token}, 范围={minutes}分钟")
                    return []
                
                # 步骤2：获取交易详情（批量获取，限制数量）
                # 为了降低整体耗时，这里：
                # 1）只取最新的部分交易（例如前20条）
                # 2）并发请求交易详情，而不是串行逐个请求
                max_txs = min(len(filtered_signatures), 20)
                target_sigs = filtered_signatures[:max_txs]
                
                tasks = [
                    self._get_transaction_by_signature(session, rpc_url, sig, token, proxy_url)
                    for sig in target_sigs
                ]
                
                parsed_transactions: List[Dict[str, Any]] = []
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, dict) and res:
                            parsed_transactions.append(res)
                
                logger.info(
                    f"RPC方式获取交易记录: token={token}, "
                    f"签名数={len(filtered_signatures)}, 实际请求={max_txs}, 有效交易数={len(parsed_transactions)}"
                )
                return parsed_transactions
                
        except Exception as e:
            logger.error(f"RPC方式获取交易历史失败: {e}")
            return []
    
    async def _get_transaction_by_signature(
        self,
        session: aiohttp.ClientSession,
        rpc_url: str,
        signature: str,
        token: str,
        proxy_url: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """获取单个交易的详细信息"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "getTransaction",
                "params": [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0
                    }
                ]
            }
            
            async with session.post(
                rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=5),
                proxy=proxy_url if proxy_url else None,
            ) as response:
                if response.status != 200:
                    return None
                
                data = await response.json()
                if "error" in data or "result" not in data:
                    return None
                
                tx_result = data.get("result")
                if not tx_result:
                    return None
                
                # 解析交易数据，提取价格和交易量
                return self._parse_rpc_transaction(tx_result, token)
                
        except Exception as e:
            logger.debug(f"获取交易详情失败: {signature}, error={e}")
            return None
    
    def _parse_transaction(self, tx: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
        """
        解析Enhanced Transactions API返回的交易数据
        
        Args:
            tx: 交易数据字典
            token: 代币地址
            
        Returns:
            Dict: 包含price和volume的字典，如果解析失败返回None
        """
        try:
            # 从交易中提取价格和交易量
            # Enhanced Transactions API的格式可能因版本而异
            # 这里尝试多种可能的字段名
            
            # 解析时间戳（使用统一的时间解析方法）
            tx_time = self._parse_transaction_time_from_enhanced(tx)
            timestamp = tx_time.timestamp() if tx_time else 0
            
            # 尝试从tokenTransfers中提取
            token_transfers = tx.get("tokenTransfers", [])
            if token_transfers:
                for transfer in token_transfers:
                    if transfer.get("mint") == token:
                        amount = transfer.get("tokenAmount", 0)
                        # 计算交易量（需要结合价格）
                        return {
                            "price": 0.0,  # 需要从其他地方获取
                            "volume": float(amount),
                            "timestamp": timestamp,
                            "signature": tx.get("signature", ""),
                        }
            
            # 尝试从nativeTransfers中提取
            native_transfers = tx.get("nativeTransfers", [])
            if native_transfers:
                # 处理原生SOL转账
                total_amount = sum(t.get("amount", 0) for t in native_transfers)
                return {
                    "price": 0.0,
                    "volume": float(total_amount) / 1e9,  # SOL转换为单位
                    "timestamp": timestamp,
                    "signature": tx.get("signature", ""),
                }
            
            # 如果无法解析，返回None
            return None
            
        except Exception as e:
            logger.debug(f"解析交易数据失败: {e}")
            return None
    
    def _parse_rpc_transaction(self, tx_result: Dict[str, Any], token: str) -> Optional[Dict[str, Any]]:
        """
        解析RPC getTransaction返回的交易数据
        
        Args:
            tx_result: RPC返回的交易结果
            token: 代币地址
            
        Returns:
            Dict: 包含price和volume的字典
        """
        try:
            # 从meta中提取交易信息
            meta = tx_result.get("meta", {})
            if not meta:
                return None
            
            # 获取时间戳
            block_time = tx_result.get("blockTime")
            timestamp = block_time if block_time else 0
            
            # 尝试从postTokenBalances中提取代币转移信息
            post_token_balances = meta.get("postTokenBalances", [])
            pre_token_balances = meta.get("preTokenBalances", [])
            
            # 计算代币数量变化和价格
            volume = 0.0
            sol_amount = 0.0  # SOL转移量（用于计算价格）
            usdc_amount = 0.0  # USDC转移量（用于计算价格）
            
            # 查找目标代币的转移
            for post_balance in post_token_balances:
                mint = post_balance.get("mint")
                if mint == token:
                    post_amount = float(post_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                    # 找到对应的pre_balance
                    owner = post_balance.get("owner")
                    pre_amount = 0.0
                    for pre_balance in pre_token_balances:
                        if pre_balance.get("owner") == owner and pre_balance.get("mint") == token:
                            pre_amount = float(pre_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                            break
                    # 计算变化量（绝对值）
                    volume += abs(post_amount - pre_amount)
            
            # 查找SOL转移（用于计算价格）
            # USDC mint: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
            # 或者查找原生SOL转移
            for post_balance in post_token_balances:
                mint = post_balance.get("mint")
                if mint is None:  # 原生SOL
                    post_amount = float(post_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                    owner = post_balance.get("owner")
                    pre_amount = 0.0
                    for pre_balance in pre_token_balances:
                        if pre_balance.get("owner") == owner and pre_balance.get("mint") is None:
                            pre_amount = float(pre_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                            break
                    sol_amount += abs(post_amount - pre_amount)
                elif mint == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":  # USDC
                    post_amount = float(post_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                    owner = post_balance.get("owner")
                    pre_amount = 0.0
                    for pre_balance in pre_token_balances:
                        if pre_balance.get("owner") == owner and pre_balance.get("mint") == mint:
                            pre_amount = float(pre_balance.get("uiTokenAmount", {}).get("uiAmount", 0))
                            break
                    usdc_amount += abs(post_amount - pre_amount)
            
            # 计算价格
            price = 0.0
            if volume > 0:
                if usdc_amount > 0:
                    # 使用USDC计算价格
                    price = usdc_amount / volume
                elif sol_amount > 0:
                    # 使用SOL计算价格（需要SOL/USD价格，这里简化处理）
                    # 实际应用中需要获取当前SOL价格
                    sol_price_usd = 100.0  # 占位值，实际需要从API获取
                    price = (sol_amount * sol_price_usd) / volume
            
            if volume > 0:
                return {
                    "price": price,
                    "volume": volume,
                    "timestamp": timestamp,
                    "signature": tx_result.get("transaction", {}).get("signatures", [""])[0] if tx_result.get("transaction") else "",
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"解析RPC交易数据失败: {e}")
            return None
    
    def _calculate_kline(
        self,
        token: str,
        symbol: str,
        interval: str,
        transactions: List[Dict[str, Any]],
        current_price: float
    ) -> Optional[StandardKlineData]:
        """
        从交易历史计算K线数据
        
        Args:
            token: 代币地址
            symbol: 代币符号
            interval: K线周期（1m, 5m, 15m）
            transactions: 交易历史列表，每个交易包含price和volume字段
            current_price: 当前价格（作为fallback）
            
        Returns:
            StandardKlineData: K线数据
        """
        try:
            # 计算时间窗口（秒）
            interval_seconds = {
                "1m": 60,
                "5m": 300,
                "15m": 900,
            }.get(interval, 60)
            
            # 获取当前时间窗口的开始时间
            now = datetime.now()
            window_start = now - timedelta(seconds=interval_seconds)
            
            # 过滤该时间窗口内的交易
            window_transactions = []
            for tx in transactions:
                tx_time = self._parse_transaction_time(tx)
                if tx_time >= window_start:
                    window_transactions.append(tx)
            
            if not window_transactions:
                # 如果没有交易数据，使用当前价格作为占位
                logger.debug(f"时间窗口内无交易数据，使用当前价格: {interval}")
                return StandardKlineData(
                    symbol=symbol,
                    interval=interval,
                    timestamp=now,
                    open=current_price,
                    high=current_price,
                    low=current_price,
                    close=current_price,
                    volume=0.0,
                    quote_volume=0.0,
                    token_address=token
                )
            
            # 计算OHLC和交易量
            prices = []
            volumes = []
            quote_volumes = []  # 成交额（USD）
            
            for tx in window_transactions:
                # 获取交易价格（如果交易数据中没有价格，使用当前价格）
                price = tx.get("price", 0.0)
                if price <= 0:
                    price = current_price
                
                # 获取交易量（代币数量）
                volume = tx.get("volume", 0.0)
                
                if volume > 0:
                    prices.append(price)
                    volumes.append(volume)
                    # 计算成交额（USD）
                    quote_volume = volume * price
                    quote_volumes.append(quote_volume)
            
            if not prices:
                # 如果没有有效价格，使用当前价格
                open_price = high_price = low_price = close_price = current_price
                total_volume = 0.0
                total_quote_volume = 0.0
            else:
                # 按时间排序（假设transactions已经按时间排序）
                # 如果没有排序，这里需要先排序
                open_price = prices[0]
                close_price = prices[-1]
                high_price = max(prices)
                low_price = min(prices)
                total_volume = sum(volumes)
                total_quote_volume = sum(quote_volumes)
            
            logger.debug(f"计算K线数据: {interval}, 交易数={len(window_transactions)}, "
                        f"价格范围=[{low_price:.8f}, {high_price:.8f}], "
                        f"成交量={total_volume:.2f}, 成交额={total_quote_volume:.2f}")
            
            return StandardKlineData(
                symbol=symbol,
                interval=interval,
                timestamp=now,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=total_volume,
                quote_volume=total_quote_volume,
                token_address=token
            )
            
        except Exception as e:
            logger.error(f"计算K线数据失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _parse_transaction_time(self, tx: Dict[str, Any]) -> datetime:
        """
        解析交易时间戳
        
        支持多种时间戳格式：
        - Unix时间戳（秒）
        - Unix时间戳（毫秒）
        - ISO格式字符串
        """
        try:
            timestamp = tx.get("timestamp", 0)
            
            if isinstance(timestamp, (int, float)):
                # 判断是秒还是毫秒（毫秒通常大于1e10）
                if timestamp > 1e10:
                    timestamp = timestamp / 1000  # 毫秒转秒
                return datetime.fromtimestamp(timestamp)
            elif isinstance(timestamp, str):
                # 尝试解析ISO格式
                try:
                    return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                except:
                    pass
            
            # 如果无法解析，返回当前时间
            return datetime.now()
        except Exception:
            return datetime.now()
    
    async def is_available(self, token: str) -> bool:
        """检查token是否在Helius上可用（是否为有效的Solana地址）"""
        if not self._is_solana_address(token):
            return False
        
        try:
            metadata = await self._get_token_metadata(token)
            return metadata is not None
        except Exception:
            return False
    
    def get_source_name(self) -> str:
        return "Helius"
    
    def supports_mode(self, mode: DataSourceMode) -> bool:
        """Helius支持KLINE和ONCHAIN两种模式"""
        return mode in [DataSourceMode.KLINE, DataSourceMode.ONCHAIN]
    
    async def close(self):
        """关闭HTTP会话"""
        if self.session and not self.session.closed:
            await self.session.close()
