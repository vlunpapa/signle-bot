"""
Telegram Bot 命令系统
支持动态配置、策略管理等功能
"""
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from loguru import logger

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode


class BotCommands:
    """Bot命令处理器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """启动命令 - 显示欢迎信息"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "用户"
        
        welcome_text = f"""
🤖 **欢迎使用量价信号机器人！**

👤 用户: @{username}
🆔 ID: `{user_id}`

**核心功能：**
• 📊 多源数据采集（DexScreener/Bybit/Binance/链上）
• 🧠 智能策略引擎（内置+YAML自定义）
• 🔔 实时信号推送
• 📈 深度图展示

**快速开始：**
`/set_datasource kline` - 切换到K线模式
`/set_datasource onchain` - 切换到链上模式
`/list_strategies` - 查看可用策略
`/set_strategy <name>` - 启用策略
`/help` - 查看完整帮助

**当前配置：**
数据源模式: `{self.config.get_user_mode(user_id)}`
启用策略: `{', '.join(self.config.get_user_strategies(user_id))}`
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown"
        )
    
    async def set_datasource(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """设置数据源模式"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "❌ 请指定数据源模式：\n"
                "`/set_datasource kline` - K线优先模式\n"
                "`/set_datasource onchain` - 链上优先模式",
                parse_mode="Markdown"
            )
            return
        
        mode_str = context.args[0].lower()
        
        try:
            if mode_str == "kline":
                mode = DataSourceMode.KLINE
                desc = "K线优先模式（DexScreener/Bybit/Binance）"
            elif mode_str == "onchain":
                mode = DataSourceMode.ONCHAIN
                desc = "链上优先模式（Helius Webhook + RPC）"
            else:
                await update.message.reply_text(
                    f"❌ 未知模式: `{mode_str}`\n"
                    "支持的模式: `kline`, `onchain`",
                    parse_mode="Markdown"
                )
                return
            
            self.config.set_user_mode(user_id, mode)
            
            await update.message.reply_text(
                f"✅ 数据源模式已切换为: **{desc}**\n\n"
                f"模式: `{mode.value}`\n"
                f"延迟目标: {'≤8s' if mode == DataSourceMode.KLINE else '≤3s'}",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"设置数据源模式失败: {e}")
            await update.message.reply_text(f"❌ 设置失败: {e}")
    
    async def list_strategies(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """列出所有可用策略"""
        user_id = update.effective_user.id
        current_mode = self.config.get_user_mode(user_id)
        
        # 获取内置策略
        builtin_strategies = [
            "量增价升",
            "缩量新高",
            "天量见顶"
        ]
        
        # 获取YAML自定义策略
        yaml_strategies = self.config.get_yaml_strategies()
        
        text = f"📋 **可用策略列表**\n\n"
        text += f"当前模式: `{current_mode.value}`\n\n"
        
        text += "**内置策略：**\n"
        for strategy in builtin_strategies:
            enabled = strategy in self.config.get_user_strategies(user_id)
            status = "✅" if enabled else "⚪"
            text += f"{status} `{strategy}`\n"
        
        if yaml_strategies:
            text += "\n**自定义策略（YAML）：**\n"
            for strategy in yaml_strategies:
                enabled = strategy in self.config.get_user_strategies(user_id)
                status = "✅" if enabled else "⚪"
                text += f"{status} `{strategy}`\n"
        
        text += "\n使用 `/set_strategy <name>` 启用/禁用策略"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def set_strategy(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """启用/禁用策略"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "❌ 请指定策略名称\n"
                "使用 `/list_strategies` 查看可用策略",
                parse_mode="Markdown"
            )
            return
        
        strategy_name = " ".join(context.args)
        current_strategies = self.config.get_user_strategies(user_id)
        
        if strategy_name in current_strategies:
            # 禁用策略
            self.config.remove_user_strategy(user_id, strategy_name)
            await update.message.reply_text(
                f"⚪ 策略 `{strategy_name}` 已禁用",
                parse_mode="Markdown"
            )
        else:
            # 启用策略
            self.config.add_user_strategy(user_id, strategy_name)
            await update.message.reply_text(
                f"✅ 策略 `{strategy_name}` 已启用",
                parse_mode="Markdown"
            )
    
    async def set_volume_mult(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """设置成交量倍数阈值"""
        user_id = update.effective_user.id
        
        if not context.args:
            current = self.config.get_user_param(user_id, "volume_mult", 1.5)
            await update.message.reply_text(
                f"当前成交量倍数阈值: `{current}`\n\n"
                "使用 `/set_volume_mult <value>` 设置\n"
                "例如: `/set_volume_mult 2.0`",
                parse_mode="Markdown"
            )
            return
        
        try:
            value = float(context.args[0])
            if value <= 0:
                raise ValueError("倍数必须大于0")
            
            self.config.set_user_param(user_id, "volume_mult", value)
            
            await update.message.reply_text(
                f"✅ 成交量倍数阈值已设置为: `{value}`",
                parse_mode="Markdown"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ 无效数值: {e}")
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """帮助命令"""
        help_text = """
📖 **命令帮助**

**配置命令：**
`/set_datasource <kline|onchain>` - 切换数据源模式
`/set_volume_mult <value>` - 设置成交量倍数阈值
`/set_template <template>` - 自定义消息模板（Jinja2）

**策略命令：**
`/list_strategies` - 查看所有可用策略
`/set_strategy <name>` - 启用/禁用策略
`/strategy_info <name>` - 查看策略详情

**查询命令：**
`/status` - 查看当前配置状态
`/test <token>` - 测试token数据获取

**其他：**
`/start` - 开始使用
`/help` - 显示此帮助

**示例：**
```
/set_datasource kline
/set_volume_mult 2.0
/set_strategy 量增价升
/test PEPE
```
        """
        
        await update.message.reply_text(help_text, parse_mode="Markdown")
    
    async def status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """查看当前状态"""
        user_id = update.effective_user.id
        
        mode = self.config.get_user_mode(user_id)
        strategies = self.config.get_user_strategies(user_id)
        volume_mult = self.config.get_user_param(user_id, "volume_mult", 1.5)
        
        status_text = f"""
📊 **当前配置状态**

👤 用户ID: `{user_id}`
📡 数据源模式: `{mode.value}`
🧠 启用策略: `{', '.join(strategies) if strategies else '无'}`
📈 成交量倍数: `{volume_mult}x`

**数据源延迟：**
• K线模式: ≤8s
• 链上模式: ≤3s
        """
        
        await update.message.reply_text(status_text, parse_mode="Markdown")

