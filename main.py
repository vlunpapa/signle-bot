"""
Telegram 驱动型多源量价信号机器人 - 主程序入口
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from loguru import logger

# 加载.env文件（从项目根目录）
# 注意：之前出现过 ValueError: embedded null character，这里增加保护
env_path = Path(__file__).parent / ".env"
try:
    load_dotenv(dotenv_path=env_path, override=True)
except ValueError as e:
    # .env 可能已损坏或包含非法字符，忽略该错误，继续使用环境变量
    print(f"[WARN] 加载 .env 失败（可能已损坏），将仅使用系统环境变量: {e}")
except Exception as e:
    # 其他异常也仅记录，不中断主程序
    print(f"[WARN] 加载 .env 时出现异常，将仅使用系统环境变量: {e}")

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode
from src.bot.commands import BotCommands
from src.bot.listener import MessageListener
from src.adapters.dexscreener import DexScreenerAdapter
from src.adapters.helius import HeliusAdapter
from src.analysis.manager import AnalysisManager
from src.analysis.window_manager import AnalysisConfig


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
    colorize=False  # 避免Windows控制台编码问题
)
logger.add(
    "logs/bot.log",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8"
)


class SignalBot:
    """信号机器人主类"""
    
    def __init__(self, bot_token: str, enable_analysis: bool = True):
        self.bot_token = bot_token
        self.config = ConfigManager()
        self.commands = BotCommands(self.config)
        
        # 初始化分析层（可选）
        self.analysis_manager = None
        if enable_analysis:
            analysis_config = AnalysisConfig(
                window_size=300,  # 5分钟
                min_messages=2,
                max_messages=50,
                check_interval=60
            )
            self.analysis_manager = AnalysisManager(
                script_path=None,  # 使用默认分析
                config=analysis_config,
                auto_generate_strategy=True,  # 自动生成策略
                min_confidence=0.7
            )
        
        # 读取信号发送目标群组ID（从环境变量）
        signal_chat_id = os.getenv("SIGNAL_CHAT_ID")
        if signal_chat_id:
            try:
                signal_chat_id = int(signal_chat_id)
                logger.info(f"信号将发送到目标群组: {signal_chat_id}")
            except ValueError:
                logger.warning(f"无效的SIGNAL_CHAT_ID: {signal_chat_id}，将发送到消息来源群组")
                signal_chat_id = None
        else:
            logger.info("未配置SIGNAL_CHAT_ID，信号将发送到消息来源群组")
            signal_chat_id = None
        
        # 读取并发执行上限（从环境变量）
        max_concurrent_tokens = os.getenv("MAX_CONCURRENT_TOKENS")
        if max_concurrent_tokens:
            try:
                max_concurrent_tokens = int(max_concurrent_tokens)
                logger.info(f"并发执行上限: {max_concurrent_tokens}个Token")
            except ValueError:
                logger.warning(f"无效的MAX_CONCURRENT_TOKENS: {max_concurrent_tokens}，使用默认值50")
                max_concurrent_tokens = None
        else:
            logger.info("未配置MAX_CONCURRENT_TOKENS，使用默认值50（不超过API限制60）")
            max_concurrent_tokens = None
        
        self.listener = MessageListener(
            self.config,
            analysis_manager=self.analysis_manager,
            signal_chat_id=signal_chat_id,
            max_concurrent_tokens=max_concurrent_tokens
        )
        
        # 初始化数据源适配器
        # Helius作为Solana链上数据的主要数据源，DexScreener作为回退
        self.adapters = {
            "helius": HeliusAdapter(),  # Helius适配器（Solana链上数据，主要数据源）
            "dexscreener": DexScreenerAdapter()  # DexScreener适配器（回退数据源）
        }
        logger.info("数据源适配器已初始化：Helius(Solana主要数据源) + DexScreener(回退数据源)")
        
        self.application: Application = None
    
    async def start(self):
        """启动机器人"""
        try:
            # 创建Telegram应用
            logger.info("正在创建Telegram应用...")
            builder = Application.builder().token(self.bot_token)

            # 可选：使用代理（例如本机 Clash），从环境变量 TG_PROXY_URL 读取
            proxy_url = os.getenv("TG_PROXY_URL")
            if proxy_url:
                builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
                logger.info(f"使用代理连接 Telegram: {proxy_url}")

            self.application = builder.build()
            
            # 设置Notifier的Bot实例
            self.listener.notifier.set_bot(self.application.bot)
            
            # 注册命令处理器
            self._register_handlers()
            
            # 启动分析层
            if self.analysis_manager:
                await self.analysis_manager.start()
                logger.info("🧠 分析层已启动")
            
            # 初始化（带重试）
            logger.info("正在初始化Bot...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    await self.application.initialize()
                    await self.application.start()
                    logger.info("✅ Bot初始化成功")
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"初始化失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(5)
                    else:
                        raise
            
            logger.info("🤖 信号机器人启动成功")
            
            # 开始轮询
            logger.info("开始轮询消息...")
            await self.application.updater.start_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False  # 改为False，不丢弃待处理的更新
            )
            logger.info("✅ 轮询已启动，等待消息...")
            logger.info(f"📊 Bot信息: @{self.application.bot.username} (ID: {self.application.bot.id})")
            # logger.info(f"📊 监听群组: {chat_id}")  # 隐藏具体群组ID
            
        except Exception as e:
            logger.exception(f"启动失败: {e}")
            raise
    
    async def stop(self):
        """停止机器人"""
        logger.info("正在停止机器人...")
        
        # 停止分析层
        if self.analysis_manager:
            await self.analysis_manager.stop()
        
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        # 关闭适配器
        for adapter in self.adapters.values():
            if hasattr(adapter, 'close'):
                await adapter.close()
        
        logger.info("机器人已停止")
    
    def _register_handlers(self):
        """注册消息处理器"""
        # 调试用：记录所有收到的更新
        async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat = getattr(update, "effective_chat", None)
            user = getattr(update, "effective_user", None)
            message = getattr(update, "message", None)
            
            # 获取消息发送者信息（可能是Bot）
            from_user = None
            is_bot = False
            if message and hasattr(message, "from_user") and message.from_user:
                from_user = message.from_user
                is_bot = getattr(from_user, "is_bot", False)
            
            text = None
            if message:
                # 增强日志：记录所有文本消息，特别是群组消息
                # 监听指定群组（配置从环境变量读取）
                # if message.text and chat and chat.id == int(os.getenv("MONITOR_CHAT_ID", "0")):
                    logger.info(
                        f"📨 DEBUG收到群组消息: chat_id={chat.id}, "
                        f"from_user={from_user.username if from_user else 'None'}, "
                        f"from_user_id={from_user.id if from_user else None}, "
                        f"is_bot={is_bot}, "
                        f"text_preview={message.text[:100]}"
                    )
                    # 特别标记转发Bot的消息
                    if is_bot and from_user:
                        logger.warning(
                            f"🤖 收到Bot消息: username={from_user.username}, "
                            f"id={from_user.id}, text_preview={message.text[:50]}"
                        )
            if message:
                text = message.text
            elif getattr(update, "edited_message", None):
                text = update.edited_message.text
            
            # 详细记录更新信息
            logger.info(
                f"📨 收到更新: chat_id={getattr(chat, 'id', None)}, "
                f"chat_type={getattr(chat, 'type', None)}, "
                f"effective_user_id={getattr(user, 'id', None)}, "
                f"effective_username={getattr(user, 'username', None)}, "
                f"from_user_id={getattr(from_user, 'id', None) if from_user else None}, "
                f"from_username={getattr(from_user, 'username', None) if from_user else None}, "
                f"is_bot={is_bot}, "
                f"text={text[:100] if text else None}"
            )
            
            # 特别标记Bot消息
            if is_bot:
                logger.warning(f"🤖 检测到Bot消息: from_user={getattr(from_user, 'username', 'Unknown')}, text={text[:50] if text else None}")

            # 简单兜底：如果命令系统有问题，手动处理 /start，确保你能看到欢迎消息
            if chat and text and str(chat.id) == str(user.id):
                # 仅在私聊中处理 /start
                if text.strip().lower() == "/start":
                    welcome = (
                        "欢迎使用量价信号机器人！\n\n"
                        f"用户: @{getattr(user, 'username', '用户')}\n"
                        f"ID: {getattr(user, 'id', None)}\n\n"
                        "你可以发送以下命令试试：\n"
                        "/set_datasource kline - 切换到K线模式\n"
                        "/set_datasource onchain - 切换到链上模式\n"
                        "/list_strategies - 查看可用策略\n"
                        "/status - 查看当前配置\n"
                    )
                    try:
                        await context.bot.send_message(chat_id=chat.id, text=welcome)
                        logger.info(f"log_update 兜底发送 /start 欢迎消息给 user_id={user.id}")
                    except Exception as e:
                        logger.error(f"log_update 兜底发送 /start 失败: {e}")
        
        # 全局错误处理器
        async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
            """全局错误处理"""
            error = context.error
            logger.error(f"处理更新时出错: {error}")
            
            # 处理网络错误
            from telegram.error import NetworkError, TimedOut, RetryAfter
            if isinstance(error, RetryAfter):
                delay = min(30, int(getattr(error, "retry_after", 1)) + 1)
                logger.warning(f"遇到限流，等待 {delay} 秒")
                await asyncio.sleep(delay)
            elif isinstance(error, (NetworkError, TimedOut)):
                logger.warning("网络超时，稍后重试")
                await asyncio.sleep(3)
            else:
                logger.exception(f"未处理的错误: {error}")
        
        self.application.add_error_handler(error_handler)
        
        # 命令处理器
        self.application.add_handler(CommandHandler("start", self.commands.start))
        self.application.add_handler(CommandHandler("help", self.commands.help))
        self.application.add_handler(CommandHandler("set_datasource", self.commands.set_datasource))
        self.application.add_handler(CommandHandler("list_strategies", self.commands.list_strategies))
        self.application.add_handler(CommandHandler("set_strategy", self.commands.set_strategy))
        self.application.add_handler(CommandHandler("set_volume_mult", self.commands.set_volume_mult))
        self.application.add_handler(CommandHandler("status", self.commands.status))
        
        # 回调查询处理器（策略按钮选择）
        self.application.add_handler(
            CallbackQueryHandler(
                self.commands.handle_strategy_callback,
                pattern=r"^(toggle_strategy:|strategy_done)"
            )
        )
        
        # 先注册调试日志处理器（捕获所有更新，包括Bot消息）
        # 注意：必须在其他处理器之前注册，以便记录所有消息
        # 使用最低优先级，确保所有消息都被记录
        self.application.add_handler(
            MessageHandler(filters.ALL, log_update),
            group=-1  # 最低优先级，确保最先处理
        )
        
        # 消息监听器（处理群组消息）
        # 注意：filters.TEXT 会过滤掉非文本消息，但不会过滤Bot消息
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.listener.handle_message
            )
        )
        
        logger.info("✅ 所有处理器已注册")


async def main():
    """主函数"""
    # 获取Bot Token（优先从环境变量，其次从.env文件）
    bot_token = os.getenv("BOT_TOKEN")
    
    # 如果环境变量没有，尝试从.env文件读取
    if not bot_token:
        env_file = Path(__file__).parent / ".env"
        if env_file.exists():
            try:
                with open(env_file, "r", encoding="utf-8-sig") as f:  # utf-8-sig自动处理BOM
                    content = f.read()
                    for line in content.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, value = line.split("=", 1)
                            if key.strip() == "BOT_TOKEN":
                                bot_token = value.strip().strip('"').strip("'")
                                logger.info(f"从.env文件读取BOT_TOKEN成功")
                                break
            except Exception as e:
                logger.error(f"读取.env文件失败: {e}")
    
    if not bot_token:
        logger.error("请设置环境变量 BOT_TOKEN")
        logger.info("在 .env 文件中设置，或使用: export BOT_TOKEN=your_token")
        sys.exit(1)
    
    logger.info(f"Bot Token已加载: {bot_token[:20]}...")
    
    # 创建日志目录
    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    
    # 创建并启动机器人
    bot = SignalBot(bot_token)
    
    try:
        await bot.start()
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.exception(f"运行时错误: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())

