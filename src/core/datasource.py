"""
数据源适配器接口定义
统一 K线 / 链上两种数据模式的接口
"""
from typing import Protocol, Optional, Union
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod


class DataSourceMode(Enum):
    """数据源模式"""
    KLINE = "kline"      # K线优先模式
    ONCHAIN = "onchain"  # 链上优先模式


@dataclass
class StandardKlineData:
    """标准K线数据结构（模式A）"""
    symbol: str
    interval: str  # 1m, 5m, 15m
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: Optional[float] = None  # 成交额
    txns: Optional[int] = None  # 交易笔数（DexScreener特有）
    trades: Optional[int] = None  # 交易次数（Binance/Bybit）
    price_change_24h: Optional[float] = None  # 24小时价格变化百分比（DexScreener提供）
    market_cap: Optional[float] = None  # 市值（Market Cap）
    token_address: Optional[str] = None  # Token合约地址（CA）
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "txns": self.txns,
            "trades": self.trades,
            "price_change_24h": self.price_change_24h,
            "market_cap": self.market_cap,
            "token_address": self.token_address
        }


@dataclass
class OnChainData:
    """链上数据结构（模式B）"""
    token_address: str
    timestamp: datetime
    buy_volume: float  # 真实买入量
    sell_volume: float  # 真实卖出量
    total_volume: float
    price: float
    price_change_24h: Optional[float] = None
    whale_addresses: list[str] = None  # 大户地址列表
    wash_trading_flag: bool = False  # 刷量标记
    unique_buyers: Optional[int] = None
    unique_sellers: Optional[int] = None
    
    def __post_init__(self):
        if self.whale_addresses is None:
            self.whale_addresses = []
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "token_address": self.token_address,
            "timestamp": self.timestamp.isoformat(),
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "total_volume": self.total_volume,
            "price": self.price,
            "price_change_24h": self.price_change_24h,
            "whale_addresses": self.whale_addresses,
            "wash_trading_flag": self.wash_trading_flag,
            "unique_buyers": self.unique_buyers,
            "unique_sellers": self.unique_sellers
        }


class DataSourceAdapter(ABC):
    """
    数据源适配器抽象基类
    所有数据源（DexScreener/Bybit/Binance/Helius）必须实现此接口
    """
    
    @abstractmethod
    async def get_data(
        self,
        token: str,
        mode: DataSourceMode,
        intervals: Optional[list[str]] = None
    ) -> Union[StandardKlineData, OnChainData, list[StandardKlineData]]:
        """
        获取数据
        
        Args:
            token: Token符号或合约地址
            mode: 数据源模式
            intervals: K线周期列表（仅K线模式需要）
            
        Returns:
            K线模式: list[StandardKlineData] (多个周期)
            链上模式: OnChainData
        """
        pass
    
    @abstractmethod
    async def is_available(self, token: str) -> bool:
        """
        检查数据源是否可用（该token是否在该数据源存在）
        
        Args:
            token: Token符号或合约地址
            
        Returns:
            bool: 是否可用
        """
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """获取数据源名称"""
        pass
    
    @abstractmethod
    def supports_mode(self, mode: DataSourceMode) -> bool:
        """检查是否支持指定模式"""
        pass


class DataSourceAdapterProtocol(Protocol):
    """
    Protocol 定义（用于类型检查）
    与 DataSourceAdapter 功能相同，但使用 Protocol 更灵活
    """
    
    async def get_data(
        self,
        token: str,
        mode: DataSourceMode,
        intervals: Optional[list[str]] = None
    ) -> Union[StandardKlineData, OnChainData, list[StandardKlineData]]:
        """获取数据"""
        ...
    
    async def is_available(self, token: str) -> bool:
        """检查是否可用"""
        ...
    
    def get_source_name(self) -> str:
        """获取数据源名称"""
        ...
    
    def supports_mode(self, mode: DataSourceMode) -> bool:
        """检查是否支持指定模式"""
        ...

