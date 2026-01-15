"""
API限流器
实现令牌桶算法，控制API请求频率
"""
import asyncio
import time
from typing import Optional
from collections import deque
from loguru import logger


class RateLimiter:
    """
    令牌桶限流器（固定窗口）
    用于控制API请求频率，避免超过API限制
    """
    
    def __init__(self, max_calls: int, time_window: float = 60.0):
        """
        初始化限流器
        
        Args:
            max_calls: 时间窗口内最大请求数
            time_window: 时间窗口（秒），默认60秒
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls: deque = deque()  # 存储请求时间戳
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> float:
        """
        获取令牌，如果超过限制则等待
        
        Returns:
            float: 等待时间（秒），如果为0表示无需等待
        """
        async with self.lock:
            now = time.time()
            
            # 清理过期的时间戳（超出时间窗口）
            while self.calls and self.calls[0] < now - self.time_window:
                self.calls.popleft()
            
            # 如果未超过限制，直接允许
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return 0.0
            
            # 超过限制，计算需要等待的时间
            oldest_call = self.calls[0]
            wait_time = self.time_window - (now - oldest_call)
            
            if wait_time > 0:
                logger.debug(f"API限流：需要等待 {wait_time:.2f}秒")
                # 等待到可以发送请求
                await asyncio.sleep(wait_time)
                # 清理过期时间戳
                while self.calls and self.calls[0] < time.time() - self.time_window:
                    self.calls.popleft()
            
            # 添加新的请求时间戳
            self.calls.append(time.time())
            return wait_time
    
    def get_remaining_calls(self) -> int:
        """获取当前时间窗口内剩余的可用请求数"""
        now = time.time()
        # 清理过期时间戳
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()
        return max(0, self.max_calls - len(self.calls))
    
    def reset(self):
        """重置限流器（清空所有记录）"""
        async def _reset():
            async with self.lock:
                self.calls.clear()
        asyncio.create_task(_reset())


# 全局DexScreener限流器实例
_dexscreener_limiter: Optional[RateLimiter] = None


def get_dexscreener_limiter() -> RateLimiter:
    """
    获取DexScreener API限流器（单例模式）
    
    Returns:
        RateLimiter: 限流器实例（每分钟60次）
    """
    global _dexscreener_limiter
    if _dexscreener_limiter is None:
        # DexScreener API限制：每分钟60次
        _dexscreener_limiter = RateLimiter(max_calls=60, time_window=60.0)
        logger.info("初始化DexScreener API限流器：每分钟60次请求")
    return _dexscreener_limiter
