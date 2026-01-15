"""
通知发送器
格式化并发送策略信号
"""
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from loguru import logger

from src.strategies.engine import SignalResult
from src.core.alert_tracker import get_alert_tracker


class Notifier:
    """通知发送器"""
    
    def __init__(self):
        self.bot: Bot = None
    
    def set_bot(self, bot: Bot):
        """设置Bot实例"""
        self.bot = bot
    
    async def send_signal(self, chat_id: int, signal: SignalResult, token: str = None):
        """
        发送策略信号
        
        Args:
            chat_id: 目标群组ID
            signal: 策略信号结果
            token: 代币地址（用于统计24小时告警次数）
        """
        if not self.bot:
            logger.warning("Bot实例未设置，无法发送通知")
            return
        
        try:
            # 格式化消息（包含24小时告警统计）
            message = self._format_signal(signal, token)
            
            # 先尝试使用原始ID
            chat_id_to_use = chat_id
            last_error = None
            
            # 尝试发送消息（先使用原始ID）
            try:
                await self.bot.send_message(
                    chat_id=chat_id_to_use,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False
                )
                logger.info(f"✅ 信号已发送: {signal.strategy_name} - {signal.token} (群组ID: {chat_id_to_use})")
                return
            except TelegramError as e:
                last_error = e
                error_msg = str(e)
                # 如果是Chat not found且ID是正数，尝试转换为负数格式
                if ("Chat not found" in error_msg or "chat not found" in error_msg.lower()) and chat_id > 0:
                    # 尝试转换为超级群组格式：-100 + 原ID
                    chat_id_to_use = int(f"-100{chat_id}")
                    logger.info(f"尝试使用超级群组格式: {chat_id} -> {chat_id_to_use}")
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id_to_use,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN,
                            disable_web_page_preview=False
                        )
                        logger.info(f"✅ 信号已发送: {signal.strategy_name} - {signal.token} (群组ID: {chat_id_to_use})")
                        return
                    except TelegramError as e2:
                        last_error = e2
                        logger.warning(f"使用转换后的ID也失败: {e2}")
            
            # 如果所有尝试都失败，抛出最后一个错误
            raise last_error
            
        except TelegramError as e:
            error_msg = str(e)
            logger.error(f"❌ 发送通知失败: {e}")
            logger.error(f"  群组ID: {chat_id}")
            logger.error(f"  策略: {signal.strategy_name}")
            logger.error(f"  Token: {signal.token}")
            
            # 如果是Chat not found错误，提供详细提示
            if "Chat not found" in error_msg or "chat not found" in error_msg.lower():
                logger.error("  ⚠️  群组未找到，可能的原因：")
                logger.error(f"     1. Bot未加入目标群组（{chat_id}）")
                logger.error("     2. 群组ID格式不正确")
                logger.error("     3. 请确认Bot已加入群组，并检查群组ID是否正确")
                logger.error("     提示：")
                logger.error("       - 确保Bot已加入目标群组")
                logger.error("       - 在群组中发送消息给Bot，确认Bot能收到消息")
                logger.error("       - 可以使用 @userinfobot 获取群组的正确ID")
            # 如果是403错误，提示可能是权限问题
            elif "403" in error_msg or "Forbidden" in error_msg:
                logger.error("  ⚠️  可能是Bot未加入群组或没有发送权限，请检查Bot是否已加入群组并具有发送消息权限")
    
    def _format_signal(self, signal: SignalResult, token: str = None) -> str:
        """
        格式化信号消息
        
        Args:
            signal: 策略信号结果
            token: 代币地址（用于统计24小时告警次数）
            
        Returns:
            str: 格式化后的消息
        """
        # 获取24小时告警次数
        alert_count_24h = 0
        if token:
            alert_tracker = get_alert_tracker()
            alert_count_24h = alert_tracker.get_24h_alert_count(token)
        
        # 构建消息
        message_parts = [signal.message]
        
        # 添加24小时告警统计
        if alert_count_24h > 0:
            message_parts.append(f"\n近24小时告警: {alert_count_24h}次")
        
        # 添加信号强度和时间
        message_parts.append(f"\n信号强度: {signal.signal_strength}/100")
        message_parts.append(f"时间: {signal.timestamp}")
        
        return "\n".join(message_parts).strip()

