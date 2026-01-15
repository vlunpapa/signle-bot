"""
消息监听器
监听Telegram群组消息，提取Token并触发策略分析
集成分析层：消息 → 解析 → 分析层 → 策略执行
"""
import re
import asyncio
import os
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode, StandardKlineData
from src.core.alert_tracker import get_alert_tracker
from src.adapters.dexscreener import DexScreenerAdapter
from src.adapters.helius import HeliusAdapter
from src.strategies.engine import StrategyEngine, SignalResult
from src.strategies.monitor import MonitoringManager
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
            if matches:
                if isinstance(matches[0], tuple):
                    # 如果匹配结果是元组（有捕获组），取第一个元素
                    tokens.extend([m[0] if isinstance(m, tuple) else m for m in matches])
                else:
                    tokens.extend(matches)
        
        # 过滤：移除纯数字（除非是有效的合约地址格式）
        filtered_tokens = []
        for token in tokens:
            # 跳过纯数字（长度小于10的数字字符串，且不是以0x开头的）
            if token.isdigit() and len(token) < 10 and not token.startswith('0x'):
                logger.debug(f"过滤纯数字Token: {token}")
                continue
            filtered_tokens.append(token)
        
        # 去重并返回
        return list(set(filtered_tokens))


class MessageListener:
    """消息监听器"""
    
    def __init__(
        self,
        config_manager: ConfigManager,
        analysis_manager: Optional[AnalysisManager] = None,
        signal_chat_id: Optional[int] = None,
        max_concurrent_tokens: Optional[int] = None
    ):
        """
        初始化消息监听器
        
        Args:
            config_manager: 配置管理器
            analysis_manager: 分析管理器（可选）
            signal_chat_id: 信号发送的目标群组ID（可选）
            max_concurrent_tokens: 最大并发Token数量（可选，默认从环境变量读取或50）
        """
        self.config = config_manager
        self.extractor = TokenExtractor()
        self.parser = MemeMessageParser()
        self.strategy_engine = StrategyEngine(config_manager)
        self.notifier = Notifier()
        self.analysis_manager = analysis_manager
        self.signal_chat_id = signal_chat_id  # 信号发送的目标群组ID
        self.monitoring_manager = MonitoringManager()  # 监测任务管理器
        self.alert_tracker = get_alert_tracker()  # 告警追踪器（去重和统计）
        
        # 设置并发执行上限
        # 默认值：环境变量 MAX_CONCURRENT_TOKENS 或 50
        # 注意：Helius RPC限制为10 req/s（600次/分钟），DexScreener为60次/分钟
        # 为了兼容两个数据源，默认限制为50（不超过DexScreener限制）
        if max_concurrent_tokens is None:
            max_concurrent_tokens = int(os.getenv("MAX_CONCURRENT_TOKENS", "50"))
        
        # 确保不超过DexScreener API限制（60次/分钟）
        # Helius RPC限制更宽松（10 req/s = 600次/分钟），所以以DexScreener为准
        if max_concurrent_tokens > 60:
            logger.warning(
                f"并发上限 {max_concurrent_tokens} 超过DexScreener API限制（60次/分钟），"
                f"已自动调整为60"
            )
            max_concurrent_tokens = 60
        
        self.max_concurrent_tokens = max_concurrent_tokens
        self.semaphore = asyncio.Semaphore(max_concurrent_tokens)
        
        logger.info(
            f"消息监听器初始化完成："
            f"最大并发Token数={self.max_concurrent_tokens}, "
            f"数据源=Helius(Solana)/DexScreener(其他), "
            f"API限流=Helius(10 req/s)/DexScreener(60次/分钟)"
        )
        
        # 初始化数据源适配器
        self.adapters = {
            "dexscreener": DexScreenerAdapter(),
            "helius": HeliusAdapter()  # Helius适配器（Solana链上数据）
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
        
        # 获取发送者信息（允许Bot和匿名用户）
        from_user = message.from_user
        user_id = from_user.id if from_user else None
        username = from_user.username if from_user else "未知用户"
        is_bot = from_user.is_bot if from_user else False
        
        # 记录消息来源信息
        logger.info(
            f"收到消息: 发送者={username} (ID: {user_id}, Bot: {is_bot}), "
            f"群组={message.chat.title if message.chat.title else message.chat.id}, "
            f"Token={tokens}"
        )
        
        # 对于群组消息，如果无法获取user_id，使用群组ID作为标识
        # 或者使用默认的用户ID（用于配置存储）
        if not user_id:
            # 群组消息：使用群组ID的绝对值作为默认用户ID
            if message.chat.type in ['group', 'supergroup']:
                user_id = abs(message.chat.id)  # 使用群组ID作为标识
                logger.info(f"消息来自匿名用户或Bot，使用群组ID作为标识: {user_id}")
            else:
                # 私聊或其他情况，无法处理
                logger.warning(f"无法确定用户ID，跳过消息: {message.text[:50]}")
                return
        
        logger.info(f"检测到Token: {tokens} (用户: {user_id}, 发送者: {username})")
        
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
        # 使用信号量控制并发数量，避免超过API限制
        for token in tokens:
            asyncio.create_task(
                self._process_token_with_limit(token, user_id, message.chat.id)
            )
    
    async def _process_token_with_limit(
        self,
        token: str,
        user_id: int,
        chat_id: int
    ):
        """
        带并发限制的Token处理（包装器）
        
        使用信号量控制并发数量，避免超过API限制
        """
        async with self.semaphore:
            await self._process_token(token, user_id, chat_id)
    
    async def _process_token(
        self,
        token: str,
        user_id: int,
        chat_id: int
    ):
        """处理单个Token"""
        try:
            # 数据模式：现在统一使用K线模式（由Helius/DexScreener等适配器内部处理）
            from src.core.datasource import DataSourceMode
            mode = DataSourceMode.KLINE
            
            # 选择数据源适配器（Helius优先，DexScreener回退）
            adapter = self._select_adapter(token, mode)
            if not adapter:
                logger.warning(f"未找到可用适配器: {token}, mode={mode}")
                logger.warning(f"提示：Solana地址将使用Helius，其他地址使用DexScreener")
                return
            
            logger.info(f"使用数据源: {adapter.get_source_name()}, token={token}")
            
            # 获取数据
            logger.info(f"获取数据: {token}, mode={mode.value}, 数据源={adapter.get_source_name()}")
            # 根据用户策略选择K线周期
            # 如果启用了"5分钟交易量告警"，获取1m和5m数据
            user_strategies = self.config.get_user_strategies(user_id)
            # 如果没有启用策略，使用默认策略（5分钟交易量告警）
            if not user_strategies:
                user_strategies = ["5分钟交易量告警"]
            
            # 清理策略名称（移除可能的特殊字符）
            user_strategies = [s.strip().replace('<', '').replace('>', '') for s in user_strategies]
            logger.info(f"用户策略列表（清理后）: {user_strategies}")
            
            # 检查是否启用了需要连续监测的策略
            needs_monitoring = (
                "5分钟交易量告警" in user_strategies or 
                "volume_alert_5k" in user_strategies
                # "外源性爆发二段告警" in user_strategies  # 隐藏策略
            )
            
            if needs_monitoring:
                # 启动连续监测任务（用于积累K线数据）
                logger.info(f"🚀 启动连续监测: {token}, 策略={user_strategies}")
                
                # 存储积累的K线数据（用于外源性爆发二段告警策略）
                accumulated_klines: list[StandardKlineData] = []
                
                # 确定监测时长（隐藏策略已移除，固定为5分钟）
                duration_minutes = 5  # 原为10分钟（外源性爆发二段告警），现固定为5分钟
                
                # 每分钟数据回调
                async def minute_callback(t: str, data: StandardKlineData, minute: int):
                    """每分钟返回数据的回调"""
                    logger.info(
                        f"📊 [{minute}/{duration_minutes}] {t}: "
                        f"1分钟交易量=${data.volume:,.2f}, "
                        f"价格=${data.close:.8f}, "
                        f"时间={data.timestamp.strftime('%H:%M:%S')}"
                    )
                    
                    # 积累K线数据（保留用于未来扩展）
                    accumulated_klines.append(data)
                    
                    # 隐藏策略：外源性爆发二段告警（代码已注释，不对外公开）
                    # if "外源性爆发二段告警" in user_strategies and len(accumulated_klines) >= 4:
                    #     logger.info(f"🔍 执行外源性爆发二段告警策略: {t}, 已积累{len(accumulated_klines)}根K线")
                    #     try:
                    #         result = await self.strategy_engine.builtin.external_burst_phase2(
                    #             klines=accumulated_klines,
                    #             m=3,
                    #             k=1.8,
                    #             min_volume_hits=1
                    #         )
                    #         ...
                    #     except Exception as e:
                    #         logger.error(f"执行外源性爆发二段告警策略失败: {t}, error={e}")
                
                # 告警回调（5分钟累计交易量超过阈值）
                async def alert_callback(t: str, total_volume: float):
                    """5分钟累计交易量告警回调"""
                    volume_threshold = self.config.get_user_param(user_id, "volume_threshold_5k", 5000.0)
                    
                    # 获取Token信息（从最近的数据中）
                    # 尝试获取Token的symbol和CA地址
                    try:
                        # 获取最新数据以提取symbol和CA
                        latest_data = await adapter.get_data(
                            token=t,
                            mode=DataSourceMode.KLINE,
                            intervals=["1m"]
                        )
                        if latest_data and len(latest_data) > 0:
                            kline_data = latest_data[0]
                            token_symbol = kline_data.symbol.split("/")[0] if "/" in kline_data.symbol else kline_data.symbol
                            token_address = kline_data.token_address or t
                            market_cap = kline_data.market_cap
                            
                            # 格式化市值
                            if market_cap:
                                if market_cap >= 1_000_000_000:
                                    mc_str = f"${market_cap/1_000_000_000:.2f}B"
                                elif market_cap >= 1_000_000:
                                    mc_str = f"${market_cap/1_000_000:.2f}M"
                                elif market_cap >= 1_000:
                                    mc_str = f"${market_cap/1_000:.2f}K"
                                else:
                                    mc_str = f"${market_cap:,.2f}"
                            else:
                                mc_str = "N/A"
                        else:
                            token_symbol = t
                            token_address = t
                            mc_str = "N/A"
                    except Exception as e:
                        logger.warning(f"获取Token信息失败: {e}")
                        token_symbol = t
                        token_address = t
                        mc_str = "N/A"
                    
                    # 格式化CA地址（使用Telegram代码格式，可点击复制）
                    ca_display = f"`{token_address}`" if token_address != "N/A" else "N/A"
                    
                    # 创建"交易信号1"告警
                    from datetime import datetime
                    signal = SignalResult(
                        strategy_name="交易信号1",
                        token=t,
                        signal_strength=min(100, int((total_volume / volume_threshold) * 20)),
                        message=f"🔔 交易信号1\n"
                               f"Symbol: {token_symbol}\n"
                               f"CA: {ca_display}\n"
                               f"5分钟累计交易量: ${total_volume:,.2f}\n"
                               f"阈值: ${volume_threshold:,.2f}\n"
                               f"超过阈值: ${total_volume - volume_threshold:,.2f}\n"
                               f"代币当前MC: {mc_str}",
                        data={"total_volume": total_volume, "threshold": volume_threshold},
                        timestamp=datetime.now().isoformat()
                    )
                    
                    # 检查是否应该告警（10分钟去重）
                    should_alert, time_since_last = self.alert_tracker.should_alert(t)
                    
                    if should_alert:
                        # 记录告警
                        self.alert_tracker.record_alert(
                            token=t,
                            strategy_name=signal.strategy_name,
                            signal_strength=signal.signal_strength
                        )
                        # 发送信号到目标群组（会包含24小时统计）
                        # 优先使用配置的信号目标群组，否则使用消息来源群组
                        target_chat_id = self.signal_chat_id if self.signal_chat_id else chat_id
                        logger.info(
                            f"🔔 发送交易信号1: {t}, "
                            f"累计交易量=${total_volume:,.2f}, "
                            f"目标群组={target_chat_id} (signal_chat_id={self.signal_chat_id}, chat_id={chat_id})"
                        )
                        await self.notifier.send_signal(target_chat_id, signal, token=t)
                    else:
                        logger.info(
                            f"⏭️  交易信号1已忽略（去重）: {t}, "
                            f"距离上次告警={time_since_last:.1f}秒"
                        )
                
                # 启动监测任务（duration_minutes已在上面定义）
                await self.monitoring_manager.start_monitoring(
                    token=token,
                    adapter=adapter,
                    callback=minute_callback,
                    alert_callback=alert_callback,
                    duration_minutes=duration_minutes
                )
                
                # 不执行传统策略，直接返回（监测任务会异步执行）
                return
            
            # 其他策略：使用传统方式
            # 优化：只使用1m K线，移除5m和15m
            if mode == DataSourceMode.KLINE:
                intervals = ["1m"]  # 只使用1分钟K线
            else:
                intervals = None
            
            data = await adapter.get_data(
                token=token,
                mode=mode,
                intervals=intervals
            )
            
            if not data:
                logger.warning(f"未获取到数据: {token}")
                return
            
            logger.info(f"成功获取数据: {token}, 数据量={len(data) if isinstance(data, list) else 1}")
            
            # 执行策略
            logger.info(f"开始执行策略分析: {token}")
            signals = await self.strategy_engine.execute_strategies(
                token=token,
                data=data,
                user_id=user_id,
                mode=mode
            )
            
            logger.info(f"策略分析完成: {token}, 信号数量={len(signals)}")
            
            # 发送通知（带去重和统计）
            # 如果配置了信号目标群组，发送到目标群组；否则发送到消息来源群组
            target_chat_id = self.signal_chat_id if self.signal_chat_id else chat_id
            for signal in signals:
                # 检查是否应该告警（10分钟去重）
                should_alert, time_since_last = self.alert_tracker.should_alert(token)
                
                if should_alert:
                    # 记录告警
                    self.alert_tracker.record_alert(
                        token=token,
                        strategy_name=signal.strategy_name,
                        signal_strength=signal.signal_strength
                    )
                    logger.info(
                        f"发送信号通知: {token}, 策略={signal.strategy_name}, "
                        f"强度={signal.signal_strength}, 目标群组={target_chat_id}"
                    )
                    await self.notifier.send_signal(target_chat_id, signal, token=token)
                else:
                    logger.info(
                        f"⏭️  信号已忽略（去重）: {token}, 策略={signal.strategy_name}, "
                        f"距离上次告警={time_since_last:.1f}秒"
                    )
            
        except Exception as e:
            logger.error(f"处理Token失败 {token}: {e}")
    
    def _select_adapter(self, token: str, mode: DataSourceMode):
        """
        选择合适的数据源适配器
        
        选择逻辑（已集成Helius作为主要数据源）：
        1. 如果是Solana地址，优先使用Helius（主要数据源）
        2. 非Solana地址或Helius不可用，使用DexScreener（回退数据源）
        """
        # 检查是否为Solana地址（Helius适配器支持）
        helius_adapter = self.adapters.get("helius")
        if helius_adapter and HeliusAdapter._is_solana_address(token):
            # Solana地址，使用Helius作为主要数据源
            logger.info(f"✅ 检测到Solana地址，使用Helius适配器（主要数据源）: {token}")
            return helius_adapter
        
        # 非Solana地址或Helius不可用，使用DexScreener作为回退
        if mode == DataSourceMode.KLINE:
            dexscreener_adapter = self.adapters.get("dexscreener")
            if dexscreener_adapter:
                logger.debug(f"使用DexScreener适配器（回退数据源）: {token}")
            return dexscreener_adapter
        elif mode == DataSourceMode.ONCHAIN:
            # 链上模式：如果是Solana地址，使用Helius；否则返回None
            if helius_adapter and HeliusAdapter._is_solana_address(token):
                return helius_adapter
            return None
        
        return None

