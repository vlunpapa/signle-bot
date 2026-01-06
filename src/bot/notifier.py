"""
通知发送器
格式化并发送策略信号
"""
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from loguru import logger

from src.strategies.engine import SignalResult


class Notifier:
    """通知发送器"""
    
    def __init__(self):
        self.bot: Bot = None
    
    def set_bot(self, bot: Bot):
        """设置Bot实例"""
        self.bot = bot
    
    async def send_signal(self, chat_id: int, signal: SignalResult):
        """发送策略信号"""
        if not self.bot:
            logger.warning("Bot实例未设置，无法发送通知")
            return
        
        try:
            # 格式化消息
            message = self._format_signal(signal)
            
            # 发送消息
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
            
            logger.info(f"信号已发送: {signal.strategy_name} - {signal.token}")
            
        except TelegramError as e:
            logger.error(f"发送通知失败: {e}")
    
    def _format_signal(self, signal: SignalResult) -> str:
        """格式化信号消息"""
        # 简化版：直接使用策略返回的消息
        # 实际应该使用Jinja2模板渲染
        
        message = f"""
{signal.message}

信号强度: {signal.signal_strength}/100
时间: {signal.timestamp}
        """
        
        return message.strip()

