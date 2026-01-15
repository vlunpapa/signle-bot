"""
获取Telegram群组ID的工具脚本

使用方法:
    python scripts/get_group_id.py <BOT_TOKEN>
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理消息，打印群组ID"""
    message = update.message
    
    print("\n" + "="*50)
    print("📨 收到新消息")
    print("="*50)
    
    # 聊天信息
    chat = message.chat
    print(f"\n📍 群组信息:")
    print(f"   群组ID: {chat.id}")
    print(f"   群组类型: {chat.type}")
    if chat.title:
        print(f"   群组名称: {chat.title}")
    if chat.username:
        print(f"   用户名: @{chat.username}")
    
    # 消息内容
    if message.text:
        print(f"\n📝 消息内容: {message.text[:100]}")
    
    # 回复提示
    await message.reply_text(
        f"✅ 信息已记录\n\n"
        f"群组ID: `{chat.id}`\n"
        f"群组名称: {chat.title or 'N/A'}",
        parse_mode="Markdown"
    )


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python scripts/get_group_id.py <BOT_TOKEN>")
        print("\n请从 @BotFather 获取 Bot Token")
        sys.exit(1)
    
    token = sys.argv[1]
    
    print("="*50)
    print("🔍 Telegram 群组ID 获取工具")
    print("="*50)
    print("\n使用说明:")
    print("1. 将此机器人添加到目标群组")
    print("2. 在群组中发送任意消息")
    print("3. 查看终端输出的群组ID")
    print("\n按 Ctrl+C 退出")
    print("="*50)
    
    # 创建应用
    application = Application.builder().token(token).build()
    
    # 添加消息处理器
    application.add_handler(
        MessageHandler(filters.ALL, handle_message)
    )
    
    # 启动
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # 保持运行
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())





