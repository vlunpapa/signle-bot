"""
消息中继服务（简化版）
使用Pyrogram监听中转群，接收DEBOT等Bot的消息
然后将消息内容通过Bot API发送到处理群，让信号Bot处理
"""
import asyncio
import hashlib
from typing import Optional, Set
from datetime import datetime, timedelta
from pyrogram import Client
from pyrogram.types import Message
from loguru import logger
import aiohttp
import signal


class MessageRelay:
    """消息中继服务 - 监听中转群，转发到处理群"""
    
    def __init__(
        self,
        # Pyrogram配置（用户账户）
        api_id: int,
        api_hash: str,
        phone_number: str,
        # 监听的中转群ID
        source_chat_id: int,
        # Bot API配置（用于发送消息到处理群）
        bot_token: str,
        target_chat_id: int,
        # 代理配置（可选）
        proxy_url: Optional[str] = None
    ):
        """
        初始化消息中继
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            phone_number: 手机号
            source_chat_id: 中转群ID（监听DEBOT消息的群组）
            bot_token: Bot Token（用于发送消息到处理群）
            target_chat_id: 处理群ID（信号Bot所在的群组）
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.source_chat_id = source_chat_id
        self.bot_token = bot_token
        self.target_chat_id = target_chat_id
        self.proxy_url = proxy_url
        
        self.client: Optional[Client] = None
        self._stop_event = asyncio.Event()
        
        # 去重机制：记录已处理的消息
        self._processed_messages: Set[int] = set()  # 使用消息ID去重
        self._message_hashes: Set[str] = set()  # 使用消息内容哈希去重（备用）
        self._dedup_window = timedelta(minutes=5)  # 去重时间窗口
        self._last_cleanup = datetime.now()
    
    async def start(self):
        """启动中继服务"""
        try:
            # 配置代理（如果提供）
            proxy_config = None
            if self.proxy_url:
                from urllib.parse import urlparse
                parsed = urlparse(self.proxy_url)
                proxy_config = {
                    "scheme": parsed.scheme or "http",
                    "hostname": parsed.hostname or "127.0.0.1",
                    "port": parsed.port or 7890
                }
                logger.info(f"使用代理: {self.proxy_url}")
            
            # 创建Pyrogram客户端（用户账户）
            self.client = Client(
                "message_relay",
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone_number=self.phone_number,
                proxy=proxy_config
            )
            
            # 注册消息处理器
            @self.client.on_message()
            async def handle_message(client: Client, message: Message):
                await self._relay_message(message)
            
            # 启动客户端
            await self.client.start()
            logger.info(f"✅ 消息中继服务已启动，监听群组: {self.source_chat_id}")
            
            # 保持运行（Pyrogram 2.0不再有idle方法，使用Event保持运行）
            try:
                await self._stop_event.wait()
            except KeyboardInterrupt:
                logger.info("收到停止信号")
            
        except Exception as e:
            logger.error(f"中继服务启动失败: {e}")
            raise
    
    async def stop(self):
        """停止中继服务"""
        # 设置停止事件
        self._stop_event.set()
        
        if self.client:
            await self.client.stop()
            logger.info("中继服务已停止")
    
    async def _relay_message(self, message: Message):
        """中继消息到处理群"""
        try:
            # 只处理来自中转群的消息
            if not message.chat or message.chat.id != self.source_chat_id:
                return
            
            # 只处理文本消息
            if not message.text and not message.caption:
                return
            
            # 获取消息内容
            text = message.text or message.caption or ""
            
            # 去重检查1：使用消息ID（最可靠）
            if message.id in self._processed_messages:
                logger.debug(f"跳过重复消息（消息ID）: {message.id}")
                return
            
            # 去重检查2：过滤掉自己转发的消息（通过内容哈希）
            # 如果消息内容匹配最近转发的，说明是我们自己转发的，跳过
            message_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            if message_hash in self._message_hashes:
                logger.debug(f"跳过重复消息（内容哈希，可能是自己转发的）: {message_hash[:8]}")
                # 注意：这里可能会过滤掉我们刚发送的消息，但这是正常的去重逻辑
                return
            
            # 记录已处理的消息
            self._processed_messages.add(message.id)
            message_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            self._message_hashes.add(message_hash)
            
            # 定期清理旧的记录（避免内存泄漏）
            now = datetime.now()
            if (now - self._last_cleanup).total_seconds() > 300:  # 每5分钟清理一次
                # 清理逻辑：保留最近的消息ID（简单实现：限制集合大小）
                if len(self._processed_messages) > 1000:
                    # 保留最新的500个
                    self._processed_messages = set(list(self._processed_messages)[-500:])
                if len(self._message_hashes) > 1000:
                    self._message_hashes = set(list(self._message_hashes)[-500:])
                self._last_cleanup = now
            
            # 记录消息来源
            sender_info = "未知用户"
            is_bot = False
            if message.from_user:
                sender_name = message.from_user.first_name or ""
                if message.from_user.username:
                    sender_name += f" (@{message.from_user.username})"
                sender_info = sender_name
                is_bot = message.from_user.is_bot
            
            logger.info(
                f"📨 收到消息: 发送者={sender_info}, "
                f"Bot={is_bot}, 内容={text[:100]}"
            )
            
            # 检查客户端是否已初始化
            if not self.client:
                logger.error("❌ Pyrogram客户端未初始化，无法发送消息")
                return
            
            # 使用Pyrogram客户端直接发送消息（而不是Bot API）
            # 这样发送的消息会被视为用户消息，信号Bot可以正常接收
            try:
                logger.debug(f"尝试使用Pyrogram发送消息到群组: {self.target_chat_id}")
                # Pyrogram需要字符串格式的chat_id，如果是负数需要转换为字符串
                chat_id_str = str(self.target_chat_id)
                result = await self.client.send_message(
                    chat_id=chat_id_str,
                    text=text
                )
                logger.info(f"✅ 已中继消息到处理群（Pyrogram）: {text[:50]}")
                logger.debug(f"Pyrogram发送成功，消息ID: {result.id if result else 'N/A'}")
            except Exception as e:
                logger.error(f"❌ 中继消息失败（Pyrogram）: {type(e).__name__}: {e}")
                logger.error(f"目标群组ID: {self.target_chat_id}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                # 如果Pyrogram发送失败，尝试使用Bot API作为备用方案
                logger.warning("尝试使用Bot API作为备用方案...")
                timeout = aiohttp.ClientTimeout(total=10)
                if self.proxy_url:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                            json={
                                "chat_id": self.target_chat_id,
                                "text": text,
                                "parse_mode": "HTML"
                            },
                            proxy=self.proxy_url
                        ) as response:
                            response_text = await response.text()
                            if response.status == 200:
                                logger.info(f"✅ 已中继消息到处理群（Bot API备用）: {text[:50]}")
                            else:
                                logger.error(f"❌ Bot API备用方案也失败: {response.status}, {response_text}")
                else:
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        async with session.post(
                            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                            json={
                                "chat_id": self.target_chat_id,
                                "text": text,
                                "parse_mode": "HTML"
                            }
                        ) as response:
                            response_text = await response.text()
                            if response.status == 200:
                                logger.info(f"✅ 已中继消息到处理群（Bot API备用）: {text[:50]}")
                            else:
                                logger.error(f"❌ Bot API备用方案也失败: {response.status}, {response_text}")
            
        except Exception as e:
            logger.error(f"中继消息出错: {e}")

