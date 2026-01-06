"""
策略引擎
支持内置策略和YAML自定义策略
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from src.core.datasource import StandardKlineData, OnChainData, DataSourceMode


@dataclass
class SignalResult:
    """策略信号结果"""
    strategy_name: str
    token: str
    signal_strength: int  # 0-100
    message: str
    data: Dict[str, Any]  # 原始数据
    timestamp: str


class BuiltinStrategies:
    """内置策略集合"""
    
    @staticmethod
    async def volume_price_rise(
        data: StandardKlineData | OnChainData,
        volume_mult: float = 1.5
    ) -> Optional[SignalResult]:
        """
        量增价升策略
        
        Args:
            data: K线或链上数据
            volume_mult: 成交量倍数阈值
        """
        if isinstance(data, StandardKlineData):
            # K线模式
            volume = data.volume
            price_change = (data.close - data.open) / data.open if data.open > 0 else 0
            
            # 简化版：需要历史数据计算平均成交量
            # 实际应该从数据库获取24小时平均成交量
            avg_volume = volume / 2  # 临时估算
            
            if volume > avg_volume * volume_mult and price_change > 0:
                return SignalResult(
                    strategy_name="量增价升",
                    token=data.symbol,
                    signal_strength=min(100, int(price_change * 1000 + 50)),
                    message=f"🔔 量增价升信号: {data.symbol}\n价格: ${data.close:.8f}\n涨幅: {price_change*100:.2f}%",
                    data=data.to_dict(),
                    timestamp=data.timestamp.isoformat()
                )
        
        elif isinstance(data, OnChainData):
            # 链上模式
            buy_ratio = data.buy_volume / data.total_volume if data.total_volume > 0 else 0
            price_change = data.price_change_24h or 0
            
            if buy_ratio > 0.6 and price_change > 0:
                return SignalResult(
                    strategy_name="量增价升",
                    token=data.token_address,
                    signal_strength=min(100, int(price_change * 10 + buy_ratio * 50)),
                    message=f"🔔 量增价升信号: {data.token_address}\n价格: ${data.price:.8f}\n买入占比: {buy_ratio*100:.2f}%",
                    data=data.to_dict(),
                    timestamp=data.timestamp.isoformat()
                )
        
        return None
    
    @staticmethod
    async def low_volume_new_high(
        data: StandardKlineData | OnChainData
    ) -> Optional[SignalResult]:
        """缩量新高策略"""
        # 实现逻辑...
        return None
    
    @staticmethod
    async def high_volume_top(
        data: StandardKlineData | OnChainData
    ) -> Optional[SignalResult]:
        """天量见顶策略"""
        # 实现逻辑...
        return None


class StrategyEngine:
    """策略引擎 - 执行策略计算"""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.builtin = BuiltinStrategies()
    
    async def execute_strategies(
        self,
        token: str,
        data: StandardKlineData | OnChainData | List[StandardKlineData],
        user_id: int,
        mode: DataSourceMode
    ) -> List[SignalResult]:
        """
        执行所有启用的策略
        
        Args:
            token: Token符号或地址
            data: 数据（K线或链上）
            user_id: 用户ID
            mode: 数据源模式
            
        Returns:
            List[SignalResult]: 信号结果列表
        """
        strategies = self.config.get_user_strategies(user_id)
        if not strategies:
            return []
        
        results = []
        
        # 处理K线数据（可能是多个周期）
        if isinstance(data, list):
            # 使用最新周期的数据
            data = data[-1] if data else None
        
        if data is None:
            return []
        
        # 执行内置策略
        for strategy_name in strategies:
            try:
                if strategy_name == "量增价升":
                    volume_mult = self.config.get_user_param(user_id, "volume_mult", 1.5)
                    result = await self.builtin.volume_price_rise(data, volume_mult)
                    if result:
                        results.append(result)
                
                elif strategy_name == "缩量新高":
                    result = await self.builtin.low_volume_new_high(data)
                    if result:
                        results.append(result)
                
                elif strategy_name == "天量见顶":
                    result = await self.builtin.high_volume_top(data)
                    if result:
                        results.append(result)
                
                # TODO: 执行YAML策略
                
            except Exception as e:
                logger.error(f"策略执行失败 {strategy_name}: {e}")
        
        return results

