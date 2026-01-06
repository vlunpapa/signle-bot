"""
时间窗口管理器
管理分析时间窗口，触发分析任务
"""
import asyncio
from typing import List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from loguru import logger

from src.analysis.message_buffer import MessageBuffer, MemeMessage, TokenSummary


@dataclass
class AnalysisConfig:
    """分析配置"""
    window_size: int = 300  # 时间窗口大小（秒），默认5分钟
    overlap: int = 60  # 窗口重叠（秒），默认1分钟
    min_messages: int = 2  # 最少消息数才触发分析
    max_messages: int = 50  # 最多分析消息数
    check_interval: int = 60  # 检查间隔（秒），默认1分钟


class WindowManager:
    """时间窗口管理器"""
    
    def __init__(
        self,
        message_buffer: MessageBuffer,
        config: AnalysisConfig = None,
        analysis_callback: Optional[Callable] = None
    ):
        """
        初始化窗口管理器
        
        Args:
            message_buffer: 消息缓冲区
            config: 分析配置
            analysis_callback: 分析回调函数 (token, messages) -> None
        """
        self.buffer = message_buffer
        self.config = config or AnalysisConfig()
        self.analysis_callback = analysis_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_windows: set = set()  # 已处理的窗口ID
    
    async def start(self):
        """启动窗口管理器"""
        if self._running:
            logger.warning("窗口管理器已在运行")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("窗口管理器已启动")
    
    async def stop(self):
        """停止窗口管理器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("窗口管理器已停止")
    
    async def _run_loop(self):
        """运行循环 - 定期检查时间窗口"""
        while self._running:
            try:
                await self._check_windows()
                await asyncio.sleep(self.config.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"窗口检查错误: {e}")
                await asyncio.sleep(self.config.check_interval)
    
    async def _check_windows(self):
        """检查所有Token的时间窗口"""
        tokens = await self.buffer.get_all_tokens()
        
        for token in tokens:
            await self._check_token_window(token)
    
    async def _check_token_window(self, token: str):
        """检查单个Token的时间窗口"""
        # 获取窗口内的消息
        messages = await self.buffer.get_window_messages(
            token,
            self.config.window_size
        )
        
        if len(messages) < self.config.min_messages:
            return
        
        # 限制消息数量
        if len(messages) > self.config.max_messages:
            messages = messages[-self.config.max_messages:]
        
        # 生成窗口ID（基于时间范围）
        window_id = self._generate_window_id(token, messages)
        
        # 检查是否已处理过
        if window_id in self._processed_windows:
            return
        
        # 标记为已处理
        self._processed_windows.add(window_id)
        
        # 清理旧的窗口ID（保留最近100个）
        if len(self._processed_windows) > 100:
            # 简单清理：保留最近处理的
            self._processed_windows = set(list(self._processed_windows)[-100:])
        
        # 触发分析
        logger.info(
            f"触发分析: token={token}, "
            f"消息数={len(messages)}, "
            f"窗口={self.config.window_size}s"
        )
        
        if self.analysis_callback:
            try:
                await self.analysis_callback(token, messages)
            except Exception as e:
                logger.error(f"分析回调执行失败: {e}")
    
    def _generate_window_id(self, token: str, messages: List[MemeMessage]) -> str:
        """生成窗口ID"""
        if not messages:
            return f"{token}_{datetime.now().timestamp()}"
        
        # 使用第一个和最后一个消息的时间戳
        first_time = messages[0].timestamp
        last_time = messages[-1].timestamp
        
        # 生成基于时间范围的ID
        window_start = int(first_time.timestamp() / self.config.window_size)
        return f"{token}_{window_start}"
    
    async def trigger_analysis(self, token: str) -> List[MemeMessage]:
        """
        手动触发分析
        
        Args:
            token: Token符号
            
        Returns:
            List[MemeMessage]: 窗口内的消息
        """
        messages = await self.buffer.get_window_messages(
            token,
            self.config.window_size
        )
        
        if messages and self.analysis_callback:
            await self.analysis_callback(token, messages)
        
        return messages
    
    async def get_window_summary(self, token: str) -> Optional[TokenSummary]:
        """获取窗口摘要"""
        return await self.buffer.get_token_summary(token, self.config.window_size)

