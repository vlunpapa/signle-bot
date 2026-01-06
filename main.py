"""
Telegram 驱动型多源量价信号机器人 - 主程序入口
"""
import asyncio
import os
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from loguru import logger

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode
from src.bot.commands import BotCommands
from src.bot.listener import MessageListener
from src.adapters.dexscreener import DexScreenerAdapter
from src.analysis.manager import AnalysisManager
from src.analysis.window_manager import AnalysisConfig


# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
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
        
        self.listener = MessageListener(
            self.config,
            analysis_manager=self.analysis_manager
        )
        
        # 初始化数据源适配器
        self.adapters = {
            "dexscreener": DexScreenerAdapter()
        }
        
        self.application: Application = None
    
    async def start(self):
        """启动机器人"""
        # 创建Telegram应用
        self.application = (
            Application.builder()
            .token(self.bot_token)
            .build()
        )
        
        # 设置Notifier的Bot实例
        self.listener.notifier.set_bot(self.application.bot)
        
        # 注册命令处理器
        self._register_handlers()
        
        # 启动分析层
        if self.analysis_manager:
            await self.analysis_manager.start()
            logger.info("🧠 分析层已启动")
        
        # 初始化
        await self.application.initialize()
        await self.application.start()
        
        logger.info("🤖 信号机器人启动成功")
        
        # 开始轮询
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    
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
        # 命令处理器
        self.application.add_handler(CommandHandler("start", self.commands.start))
        self.application.add_handler(CommandHandler("help", self.commands.help))
        self.application.add_handler(CommandHandler("set_datasource", self.commands.set_datasource))
        self.application.add_handler(CommandHandler("list_strategies", self.commands.list_strategies))
        self.application.add_handler(CommandHandler("set_strategy", self.commands.set_strategy))
        self.application.add_handler(CommandHandler("set_volume_mult", self.commands.set_volume_mult))
        self.application.add_handler(CommandHandler("status", self.commands.status))
        
        # 消息监听器（处理群组消息）
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.listener.handle_message
            )
        )


async def main():
    """主函数"""
    # 获取Bot Token
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("❌ 请设置环境变量 BOT_TOKEN")
        logger.info("在 .env 文件中设置，或使用: export BOT_TOKEN=your_token")
        sys.exit(1)
    
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

