"""
消息转发服务
使用Pyrogram监听源群组，将消息转发到中转群
这样Bot就能在中转群中接收所有消息（包括其他Bot的消息）
"""
import asyncio
from typing import List, Optional
from pyrogram import Client
from pyrogram.types import Message
from loguru import logger


class RelayService:
    """消息转发服务"""
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone_number: str,
        source_chat_ids: List[int],
        target_chat_id: int
    ):
        """
        初始化转发服务
        
        Args:
            api_id: Telegram API ID（从 https://my.telegram.org 获取）
            api_hash: Telegram API Hash
            phone_number: 手机号（用于登录）
            source_chat_ids: 源群组ID列表
            target_chat_id: 目标群组ID（中转群）
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.phone_number = phone_number
        self.source_chat_ids = source_chat_ids
        self.target_chat_id = target_chat_id
        
        self.client: Optional[Client] = None
    
    async def start(self):
        """启动转发服务"""
        try:
            # 创建Pyrogram客户端
            self.client = Client(
                "relay_service",
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone_number=self.phone_number
            )
            
            # 注册消息处理器
            @self.client.on_message()
            async def handle_message(client: Client, message: Message):
                await self._forward_message(message)
            
            # 启动客户端
            await self.client.start()
            logger.info("✅ 转发服务已启动")
            
            # 保持运行
            await self.client.idle()
            
        except Exception as e:
            logger.error(f"转发服务启动失败: {e}")
            raise
    
    async def stop(self):
        """停止转发服务"""
        if self.client:
            await self.client.stop()
            logger.info("转发服务已停止")
    
    async def _forward_message(self, message: Message):
        """转发消息"""
        try:
            # 检查消息是否来自源群组
            if not message.chat:
                return
            
            chat_id = message.chat.id
            if chat_id not in self.source_chat_ids:
                return
            
            # 检查是否有文本内容
            if not message.text and not message.caption:
                return
            
            # 获取消息内容
            text = message.text or message.caption or ""
            
            # 构建转发消息
            forward_text = f"📨 来自 {message.chat.title or '未知群组'}\n\n"
            
            # 添加发送者信息
            if message.from_user:
                sender_name = message.from_user.first_name or "未知用户"
                if message.from_user.username:
                    sender_name += f" (@{message.from_user.username})"
                if message.from_user.is_bot:
                    sender_name += " [Bot]"
                forward_text += f"👤 发送者: {sender_name}\n\n"
            
            # 添加消息内容
            forward_text += text
            
            # 如果有媒体，转发媒体
            if message.photo:
                await self.client.send_photo(
                    chat_id=self.target_chat_id,
                    photo=message.photo.file_id,
                    caption=forward_text
                )
            elif message.video:
                await self.client.send_video(
                    chat_id=self.target_chat_id,
                    video=message.video.file_id,
                    caption=forward_text
                )
            elif message.document:
                await self.client.send_document(
                    chat_id=self.target_chat_id,
                    document=message.document.file_id,
                    caption=forward_text
                )
            else:
                # 纯文本消息
                await self.client.send_message(
                    chat_id=self.target_chat_id,
                    text=forward_text
                )
            
            logger.info(
                f"✅ 已转发消息: 源群组={message.chat.title}, "
                f"发送者={message.from_user.first_name if message.from_user else 'Unknown'}, "
                f"内容={text[:50]}"
            )
            
        except Exception as e:
            logger.error(f"转发消息失败: {e}")

