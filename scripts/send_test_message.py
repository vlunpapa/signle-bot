import asyncio

from telegram import Bot


async def main():
    import os
    bot_token = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    bot = Bot(bot_token)
    chat_id = int(os.getenv("TEST_CHAT_ID", "0"))  # 从环境变量读取
    try:
        msg = await bot.send_message(chat_id=chat_id, text="测试消息：你能看到这条吗？")
        print("已发送，message_id:", msg.message_id)
    except Exception as e:
        print("发送失败:", repr(e))


if __name__ == "__main__":
    asyncio.run(main())




