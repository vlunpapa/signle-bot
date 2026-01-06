"""
消息监听器
监听Telegram群组消息，提取Token并触发策略分析
集成分析层：消息 → 解析 → 分析层 → 策略执行
"""
import re
import asyncio
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode
from src.adapters.dexscreener import DexScreenerAdapter
from src.strategies.engine import StrategyEngine
from src.bot.notifier import Notifier
from src.analysis.manager import AnalysisManager
from src.analysis.message_parser import MemeMessageParser


class TokenExtractor:
    """Token提取器 - 从消息中提取$TICKER或合约地址"""
    
    # 正则表达式模式
    PATTERNS = [
        r'\$([A-Z0-9]{2,10})\b',  # $PEPE, $BTC
        r'0x[a-fA-F0-9]{40}',      # 以太坊地址
        r'[1-9A-HJ-NP-Za-km-z]{32,44}',  # Solana地址
    ]
    
    @classmethod
    def extract(cls, text: str) -> list[str]:
        """
        从文本中提取所有Token符号或地址
        
        Returns:
            list[str]: Token列表（去重）
        """
        tokens = []
        
        for pattern in cls.PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if isinstance(matches[0], tuple) if matches else False:
                # 如果匹配结果是元组（有捕获组），取第一个元素
                tokens.extend([m[0] if isinstance(m, tuple) else m for m in matches])
            else:
                tokens.extend(matches)
        
        # 去重并返回
        return list(set(tokens))


class MessageListener:
    """消息监听器"""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        analysis_manager: Optional[AnalysisManager] = None
    ):
        self.config = config_manager
        self.extractor = TokenExtractor()
        self.parser = MemeMessageParser()
        self.strategy_engine = StrategyEngine(config_manager)
        self.notifier = Notifier()
        self.analysis_manager = analysis_manager
        
        # 初始化数据源适配器
        self.adapters = {
            "dexscreener": DexScreenerAdapter()
        }
    
    async def handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理群组消息"""
        message = update.message
        if not message or not message.text:
            return
        
        # 提取Token
        tokens = self.extractor.extract(message.text)
        if not tokens:
            return
        
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        
        logger.info(f"检测到Token: {tokens} (用户: {user_id})")
        
        # 如果有分析层，先进行消息解析和存储
        if self.analysis_manager:
            for token in tokens:
                # 解析Meme消息
                meme_message = self.parser.parse(message.text, token)
                if meme_message:
                    # 添加到分析层缓冲区
                    await self.analysis_manager.add_message(meme_message)
                    logger.debug(f"Meme消息已添加到分析层: {token}, 类型={meme_message.message_type}")
        
        # 异步处理每个Token（不阻塞）
        # 注意：策略执行仍然保留，但分析层会先进行分析
        for token in tokens:
            asyncio.create_task(self._process_token(token, user_id, message.chat.id))
    
    async def _process_token(
        self,
        token: str,
        user_id: int,
        chat_id: int
    ):
        """处理单个Token"""
        try:
            # 获取用户配置
            mode = self.config.get_user_mode(user_id)
            
            # 选择数据源适配器
            adapter = self._select_adapter(token, mode)
            if not adapter:
                logger.warning(f"未找到可用适配器: {token}, mode={mode}")
                return
            
            # 获取数据
            logger.info(f"获取数据: {token}, mode={mode.value}")
            data = await adapter.get_data(
                token=token,
                mode=mode,
                intervals=["5m", "15m", "1h"] if mode == DataSourceMode.KLINE else None
            )
            
            if not data:
                logger.warning(f"未获取到数据: {token}")
                return
            
            # 执行策略
            signals = await self.strategy_engine.execute_strategies(
                token=token,
                data=data,
                user_id=user_id,
                mode=mode
            )
            
            # 发送通知
            for signal in signals:
                await self.notifier.send_signal(chat_id, signal)
            
        except Exception as e:
            logger.error(f"处理Token失败 {token}: {e}")
    
    def _select_adapter(self, token: str, mode: DataSourceMode):
        """选择合适的数据源适配器"""
        # 简化版：优先使用DexScreener
        # 实际应该根据token类型和可用性选择
        
        if mode == DataSourceMode.KLINE:
            return self.adapters.get("dexscreener")
        elif mode == DataSourceMode.ONCHAIN:
            # TODO: 返回链上适配器
            return None
        
        return None

