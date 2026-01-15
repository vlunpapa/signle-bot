"""
消息中继服务主程序（简化版）
使用Pyrogram监听中转群，接收DEBOT等Bot的消息
然后通过Bot API发送到处理群，让信号Bot处理
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from src.forwarder.message_relay import MessageRelay

# 配置日志
logger.add(
    "logs/relay.log",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
    level="INFO"
)


async def main():
    """主函数"""
    # 加载环境变量（确保从项目根目录加载）
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        logger.error(f"❌ .env文件不存在: {env_path}")
        return
    
    # 先加载系统环境变量，再加载.env文件（覆盖）
    # 注意：.env 可能存在损坏（embedded null character），这里增加保护
    try:
        load_dotenv(override=True)
        load_dotenv(dotenv_path=env_path, override=True)
    except ValueError as e:
        logger.warning(f"加载 .env 失败（可能已损坏），将仅使用系统环境变量: {e}")
    except Exception as e:
        logger.warning(f"加载 .env 时出现异常，将仅使用系统环境变量: {e}")
    
    # 读取配置
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    phone_number = os.getenv("TELEGRAM_PHONE_NUMBER")
    source_chat_id = os.getenv("RELAY_SOURCE_CHAT_ID")  # 中转群ID（监听DEBOT消息）
    # 优先使用转发Bot的Token，如果没有则使用信号Bot的Token（向后兼容）
    relay_bot_token = os.getenv("RELAY_BOT_TOKEN")  # 转发Bot的Token（推荐）
    bot_token = relay_bot_token or os.getenv("BOT_TOKEN")  # 如果没有转发Bot，使用信号Bot的Token
    target_chat_id = os.getenv("RELAY_TARGET_CHAT_ID")  # 处理群ID（信号Bot所在的群组）
    proxy_url = os.getenv("TG_PROXY_URL") or os.getenv("RELAY_PROXY_URL")  # 代理URL（可选）
    
    # 调试：检查环境变量加载情况
    logger.debug(f"环境变量检查: BOT_TOKEN={'已设置' if bot_token else '未设置'}, API_ID={'已设置' if api_id else '未设置'}")
    
    # 验证配置
    if not api_id or not api_hash or not phone_number:
        logger.error("❌ 缺少Pyrogram配置！")
        logger.error("请在 .env 文件中配置：")
        logger.error("  TELEGRAM_API_ID=你的API_ID")
        logger.error("  TELEGRAM_API_HASH=你的API_HASH")
        logger.error("  TELEGRAM_PHONE_NUMBER=你的手机号（带国家代码，如+8613800138000）")
        logger.error("")
        logger.error("获取API凭证：")
        logger.error("  1. 访问 https://my.telegram.org")
        logger.error("  2. 登录后获取 api_id 和 api_hash")
        return
    
    if not source_chat_id:
        logger.error("❌ 缺少 RELAY_SOURCE_CHAT_ID（中转群ID，监听DEBOT消息的群组）")
        logger.error("  例如: RELAY_SOURCE_CHAT_ID=-1234567890")
        return
    
    if not bot_token:
        logger.error("❌ 缺少 Bot Token")
        logger.error("  请配置 RELAY_BOT_TOKEN（转发Bot的Token，推荐）")
        logger.error("  或者配置 BOT_TOKEN（信号Bot的Token，向后兼容）")
        return
    
    if relay_bot_token:
        logger.info(f"✅ 使用转发Bot Token: {relay_bot_token[:20]}...")
    else:
        logger.warning("⚠️  使用信号Bot Token进行转发（建议创建单独的转发Bot）")
    
    if not target_chat_id:
        logger.error("❌ 缺少 RELAY_TARGET_CHAT_ID（处理群ID，信号Bot所在的群组）")
        logger.error("  如果信号Bot也在中转群，可以设置为相同的ID")
        logger.error("  例如: RELAY_TARGET_CHAT_ID=-1234567890")
        return
    
    logger.info("=" * 60)
    logger.info("🚀 启动消息中继服务")
    logger.info("=" * 60)
    logger.info(f"监听群组（中转群）: {source_chat_id}")
    logger.info(f"目标群组（处理群）: {target_chat_id}")
    logger.info("")
    logger.info("说明：")
    logger.info("  - 使用Pyrogram（用户账户）监听中转群")
    logger.info("  - 可以接收所有消息，包括DEBOT等Bot的消息")
    logger.info("  - 将消息通过Bot API发送到处理群")
    logger.info("  - 信号Bot在处理群中接收并处理消息")
    logger.info("")
    
    # 创建中继服务
    relay = MessageRelay(
        api_id=int(api_id),
        api_hash=api_hash,
        phone_number=phone_number,
        source_chat_id=int(source_chat_id),
        bot_token=bot_token,
        target_chat_id=int(target_chat_id),
        proxy_url=proxy_url
    )
    
    try:
        # 启动服务
        await relay.start()
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
    except Exception as e:
        logger.exception(f"服务运行出错: {e}")
    finally:
        await relay.stop()


if __name__ == "__main__":
    asyncio.run(main())

