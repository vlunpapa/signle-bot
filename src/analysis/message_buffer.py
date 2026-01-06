"""
消息缓冲区
按Token分组存储消息，支持时间窗口查询
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger


@dataclass
class MemeMessage:
    """Meme币推送消息结构"""
    token: str
    message_type: str  # "smart_money", "mc", "alert", "other"
    content: dict  # 结构化数据
    timestamp: datetime
    raw_text: str  # 原始消息文本
    
    # 结构化字段
    smart_money_amount: Optional[float] = None  # 聪明钱买入数量（USDT）
    mc: Optional[float] = None  # 市值（USDT）
    alert_count: Optional[int] = None  # 告警次数
    price: Optional[float] = None  # 价格（如有）
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "token": self.token,
            "message_type": self.message_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "raw_text": self.raw_text,
            "smart_money_amount": self.smart_money_amount,
            "mc": self.mc,
            "alert_count": self.alert_count,
            "price": self.price
        }


@dataclass
class TokenSummary:
    """Token消息摘要"""
    token: str
    message_count: int
    smart_money_total: float
    mc_values: List[float]
    alert_counts: List[int]
    first_message_time: datetime
    last_message_time: datetime
    
    @property
    def avg_mc(self) -> float:
        """平均市值"""
        return sum(self.mc_values) / len(self.mc_values) if self.mc_values else 0.0
    
    @property
    def total_alerts(self) -> int:
        """总告警次数"""
        return sum(self.alert_counts)
    
    @property
    def max_mc(self) -> float:
        """最大市值"""
        return max(self.mc_values) if self.mc_values else 0.0
    
    @property
    def min_mc(self) -> float:
        """最小市值"""
        return min(self.mc_values) if self.mc_values else 0.0


class MessageBuffer:
    """消息缓冲区 - 内存存储，按Token分组"""
    
    def __init__(self, max_messages_per_token: int = 1000):
        """
        初始化消息缓冲区
        
        Args:
            max_messages_per_token: 每个Token最多保存的消息数
        """
        self.buffer: Dict[str, List[MemeMessage]] = defaultdict(list)
        self.max_messages_per_token = max_messages_per_token
        self._lock = asyncio.Lock()
    
    async def add_message(self, message: MemeMessage):
        """
        添加消息到缓冲区
        
        Args:
            message: Meme消息对象
        """
        async with self._lock:
            token = message.token.upper()
            messages = self.buffer[token]
            
            # 添加消息
            messages.append(message)
            
            # 限制消息数量（保留最新的）
            if len(messages) > self.max_messages_per_token:
                messages[:] = messages[-self.max_messages_per_token:]
            
            logger.debug(f"消息已添加到缓冲区: {token}, 当前消息数: {len(messages)}")
    
    async def get_window_messages(
        self,
        token: str,
        window_seconds: int = 300
    ) -> List[MemeMessage]:
        """
        获取时间窗口内的消息
        
        Args:
            token: Token符号
            window_seconds: 时间窗口（秒）
            
        Returns:
            List[MemeMessage]: 窗口内的消息列表
        """
        async with self._lock:
            token = token.upper()
            if token not in self.buffer:
                return []
            
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            messages = [
                msg for msg in self.buffer[token]
                if msg.timestamp >= window_start
            ]
            
            # 按时间排序
            messages.sort(key=lambda x: x.timestamp)
            
            logger.debug(
                f"获取窗口消息: {token}, "
                f"窗口={window_seconds}s, "
                f"消息数={len(messages)}"
            )
            
            return messages
    
    async def get_token_summary(
        self,
        token: str,
        window_seconds: int = 300
    ) -> TokenSummary:
        """
        获取Token消息摘要
        
        Args:
            token: Token符号
            window_seconds: 时间窗口（秒）
            
        Returns:
            TokenSummary: 消息摘要
        """
        messages = await self.get_window_messages(token, window_seconds)
        
        if not messages:
            return TokenSummary(
                token=token,
                message_count=0,
                smart_money_total=0.0,
                mc_values=[],
                alert_counts=[],
                first_message_time=datetime.now(),
                last_message_time=datetime.now()
            )
        
        smart_money_total = sum(
            msg.smart_money_amount for msg in messages
            if msg.smart_money_amount is not None
        )
        
        mc_values = [
            msg.mc for msg in messages
            if msg.mc is not None
        ]
        
        alert_counts = [
            msg.alert_count for msg in messages
            if msg.alert_count is not None
        ]
        
        timestamps = [msg.timestamp for msg in messages]
        
        return TokenSummary(
            token=token,
            message_count=len(messages),
            smart_money_total=smart_money_total,
            mc_values=mc_values,
            alert_counts=alert_counts,
            first_message_time=min(timestamps),
            last_message_time=max(timestamps)
        )
    
    async def clear_old_messages(self, max_age_hours: int = 24):
        """
        清理过期消息
        
        Args:
            max_age_hours: 最大保留时间（小时）
        """
        async with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            for token in list(self.buffer.keys()):
                messages = self.buffer[token]
                self.buffer[token] = [
                    msg for msg in messages
                    if msg.timestamp >= cutoff_time
                ]
                
                # 如果Token没有消息了，删除
                if not self.buffer[token]:
                    del self.buffer[token]
            
            logger.info(f"清理过期消息完成，保留时间: {max_age_hours}小时")
    
    async def get_all_tokens(self) -> List[str]:
        """获取所有有消息的Token列表"""
        async with self._lock:
            return list(self.buffer.keys())
    
    async def get_token_message_count(self, token: str) -> int:
        """获取Token的消息数量"""
        async with self._lock:
            token = token.upper()
            return len(self.buffer.get(token, []))

