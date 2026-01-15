"""
Telegram Bot 命令系统
支持动态配置、策略管理等功能
"""
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from loguru import logger

from src.core.config import ConfigManager
from src.core.datasource import DataSourceMode


class BotCommands:
    """Bot命令处理器"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        # 内置策略列表（供展示和按钮选择使用）
        self._builtin_strategies: List[str] = [
            "量增价升",
            "缩量新高",
            "天量见顶",
            "5分钟交易量告警",
            # "外源性爆发二段告警",  # 隐藏策略，不对外公开
        ]
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """启动命令 - 显示欢迎信息"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "用户"

        logger.info(f"/start 命令收到，user_id={user_id}, username={username}")
        
        # 为避免 Markdown 兼容问题，先发送一条简单纯文本
        try:
            text = (
                "欢迎使用量价信号机器人！\n\n"
                f"用户: @{username}\n"
                f"ID: {user_id}\n\n"
                "你可以发送以下命令试试：\n"
                "/list_strategies - 查看可用策略\n"
                "/set_strategy - 通过按钮启用/禁用策略\n"
                "/status - 查看当前配置\n"
            )
            await update.message.reply_text(text)
            logger.info(f"/start 欢迎消息已发送给 user_id={user_id}")
        except Exception as e:
            logger.error(f"/start 回复失败: {e}")
    
    async def set_datasource(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """设置数据源模式（已简化，当前固定为 Helius K线模式）"""
        user_id = update.effective_user.id
        logger.info(f"/set_datasource 命令收到（已废弃配置，仅提示），user_id={user_id}")
        
        await update.message.reply_text(
            "📡 目前数据源模式已固定为 *Helius K线模式*（Solana 链上数据），无需手动切换。\n"
            "你只需要通过 `/set_strategy` 选择启用哪些策略即可。",
            parse_mode="Markdown"
        )
    
    async def list_strategies(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """列出所有可用策略"""
        user_id = update.effective_user.id
        # 数据源模式已固定，无需展示用户模式
        
        # 获取内置策略
        builtin_strategies = self._builtin_strategies
        
        # 获取YAML自定义策略
        yaml_strategies = self.config.get_yaml_strategies()
        
        text = f"📋 **可用策略列表**\n\n"
        text += f"当前数据源模式: `Helius K线（Solana）`\n\n"
        
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
        """启用/禁用策略
        
        - 无参数时：弹出按钮菜单，可点击多选
        - 带参数时：兼容旧用法，按名称切换
        """
        user_id = update.effective_user.id
        
        if not context.args:
            # 使用按钮方式选择策略
            await self._send_strategy_selection_menu(update, context, user_id)
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
    
    async def _send_strategy_selection_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int
    ):
        """发送策略选择菜单（可点击多选）"""
        # 所有可用策略 = 内置策略 + YAML策略
        builtin_strategies = self._builtin_strategies
        yaml_strategies = self.config.get_yaml_strategies()
        all_strategies: List[str] = builtin_strategies + yaml_strategies
        
        enabled = set(self.config.get_user_strategies(user_id))
        
        keyboard: List[List[InlineKeyboardButton]] = []
        row: List[InlineKeyboardButton] = []
        
        for name in all_strategies:
            is_enabled = name in enabled
            icon = "✅" if is_enabled else "⚪"
            button = InlineKeyboardButton(
                text=f"{icon} {name}",
                callback_data=f"toggle_strategy:{name}"
            )
            row.append(button)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        # 完成按钮
        keyboard.append([
            InlineKeyboardButton("完成选择 ✅", callback_data="strategy_done")
        ])
        
        await update.message.reply_text(
            "🧠 请选择要启用/禁用的策略（点击切换，多选）：",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_strategy_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理策略选择按钮回调"""
        query = update.callback_query
        if not query:
            return
        
        user_id = query.from_user.id
        data = query.data or ""
        
        try:
            if data.startswith("toggle_strategy:"):
                # 切换单个策略启用状态
                strategy_name = data.split(":", 1)[1]
                current = self.config.get_user_strategies(user_id)
                
                if strategy_name in current:
                    self.config.remove_user_strategy(user_id, strategy_name)
                    await query.answer(f"⚪ 已禁用策略：{strategy_name}", show_alert=False)
                else:
                    self.config.add_user_strategy(user_id, strategy_name)
                    await query.answer(f"✅ 已启用策略：{strategy_name}", show_alert=False)
            
            elif data == "strategy_done":
                strategies = self.config.get_user_strategies(user_id)
                text = (
                    "✅ 策略配置已更新。\n\n"
                    f"当前启用策略：{', '.join(strategies) if strategies else '无'}"
                )
                await query.edit_message_text(text=text)
                await query.answer()
        except Exception as e:
            logger.error(f"处理策略回调失败: {e}")
            try:
                await query.answer("❌ 处理失败，请稍后重试", show_alert=True)
            except Exception:
                pass
    
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
`/set_volume_mult <value>` - 设置成交量倍数阈值
`/set_template <template>` - 自定义消息模板（Jinja2）

**策略命令：**
`/list_strategies` - 查看所有可用策略
`/set_strategy` - 通过按钮启用/禁用策略
`/strategy_info <name>` - 查看策略详情

**查询命令：**
`/status` - 查看当前配置状态
`/test <token>` - 测试token数据获取

**其他：**
`/start` - 开始使用
`/help` - 显示此帮助

**示例：**
```
/set_volume_mult 2.0
/set_strategy
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
        
        strategies = self.config.get_user_strategies(user_id)
        volume_mult = self.config.get_user_param(user_id, "volume_mult", 1.5)
        
        status_text = f"""
📊 **当前配置状态**

👤 用户ID: `{user_id}`
📡 数据源模式: `Helius K线（Solana）`
🧠 启用策略: `{', '.join(strategies) if strategies else '无'}`
📈 成交量倍数: `{volume_mult}x`
        """
        
        await update.message.reply_text(status_text, parse_mode="Markdown")

