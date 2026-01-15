"""
测试Helius适配器数据获取功能
用法: python scripts/test_helius.py <CA地址>
"""
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
env_path = project_root / ".env"
try:
    load_dotenv(dotenv_path=env_path, override=True)
except Exception as e:
    print(f"警告: 加载.env文件失败: {e}，将使用环境变量")

from loguru import logger
from src.adapters.helius import HeliusAdapter
from src.core.datasource import DataSourceMode

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    colorize=False
)


async def test_helius_adapter(ca_address: str):
    """测试Helius适配器"""
    logger.info(f"开始测试Helius适配器，CA地址: {ca_address}")
    
    # 检查API密钥
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        logger.error("未配置HELIUS_API_KEY，请在.env文件中设置")
        return
    
    logger.info(f"Helius API密钥已配置: {api_key[:10]}...{api_key[-5:]}")
    
    # 创建适配器
    adapter = HeliusAdapter()
    
    # 检查是否为Solana地址
    if not adapter._is_solana_address(ca_address):
        logger.warning(f"不是有效的Solana地址格式: {ca_address}")
        logger.info("Solana地址特征：32-44字符，Base58编码")
        return
    
    logger.info("✅ Solana地址格式验证通过")
    
    try:
        # 测试1: 检查代币是否可用
        logger.info("\n" + "="*60)
        logger.info("测试1: 检查代币是否可用")
        logger.info("="*60)
        is_available = await adapter.is_available(ca_address)
        logger.info(f"代币可用性: {'✅ 可用' if is_available else '❌ 不可用'}")
        
        if not is_available:
            logger.warning("代币不可用，可能原因：")
            logger.warning("1. 代币地址不存在")
            logger.warning("2. Helius API未收录该代币")
            logger.warning("3. API密钥权限不足")
            return
        
        # 测试2: 获取代币元数据
        logger.info("\n" + "="*60)
        logger.info("测试2: 获取代币元数据")
        logger.info("="*60)
        metadata = await adapter._get_token_metadata(ca_address)
        if metadata:
            logger.info(f"代币符号 (Symbol): {metadata.get('symbol', 'N/A')}")
            logger.info(f"代币名称 (Name): {metadata.get('name', 'N/A')}")
            logger.info(f"小数位数 (Decimals): {metadata.get('decimals', 'N/A')}")
            logger.info(f"供应量 (Supply): {metadata.get('supply', 'N/A')}")
            price_info = metadata.get('price_info')
            if price_info:
                logger.info(f"价格信息: {price_info}")
        else:
            logger.warning("无法获取代币元数据")
        
        # 测试3: 获取当前价格
        logger.info("\n" + "="*60)
        logger.info("测试3: 获取当前价格")
        logger.info("="*60)
        price = await adapter._get_current_price(ca_address)
        if price:
            logger.info(f"当前价格: ${price:,.10f}")
            # 格式化显示
            if price >= 1:
                logger.info(f"格式化价格: ${price:,.4f}")
            elif price >= 0.0001:
                logger.info(f"格式化价格: ${price:,.6f}")
            else:
                logger.info(f"格式化价格: ${price:,.10f}")
        else:
            logger.warning("无法获取代币价格")
        
        # 测试4: 获取K线数据
        logger.info("\n" + "="*60)
        logger.info("测试4: 获取K线数据")
        logger.info("="*60)
        intervals = ["1m", "5m", "15m"]
        klines = await adapter.get_data(
            token=ca_address,
            mode=DataSourceMode.KLINE,
            intervals=intervals
        )
        
        if klines:
            logger.info(f"成功获取 {len(klines)} 个周期的K线数据")
            for kline in klines:
                logger.info(f"\n周期: {kline.interval}")
                logger.info(f"  符号: {kline.symbol}")
                logger.info(f"  时间戳: {kline.timestamp}")
                logger.info(f"  开盘价 (Open): ${kline.open:,.10f}")
                logger.info(f"  最高价 (High): ${kline.high:,.10f}")
                logger.info(f"  最低价 (Low): ${kline.low:,.10f}")
                logger.info(f"  收盘价 (Close): ${kline.close:,.10f}")
                logger.info(f"  成交量 (Volume): {kline.volume:,.2f}")
                if kline.quote_volume:
                    logger.info(f"  成交额 (Quote Volume): ${kline.quote_volume:,.2f}")
                if kline.market_cap:
                    logger.info(f"  市值 (Market Cap): ${kline.market_cap:,.2f}")
                if kline.token_address:
                    logger.info(f"  合约地址 (CA): {kline.token_address}")
        else:
            logger.warning("无法获取K线数据")
        
        # 测试5: 获取链上数据（可选）
        logger.info("\n" + "="*60)
        logger.info("测试5: 获取链上数据")
        logger.info("="*60)
        onchain_data = await adapter.get_data(
            token=ca_address,
            mode=DataSourceMode.ONCHAIN
        )
        
        if onchain_data:
            logger.info(f"链上数据:")
            logger.info(f"  合约地址: {onchain_data.token_address}")
            logger.info(f"  时间戳: {onchain_data.timestamp}")
            logger.info(f"  买入量: {onchain_data.buy_volume:,.2f}")
            logger.info(f"  卖出量: {onchain_data.sell_volume:,.2f}")
            logger.info(f"  总成交量: {onchain_data.total_volume:,.2f}")
            logger.info(f"  价格: ${onchain_data.price:,.10f}")
            logger.info(f"  大户地址数: {len(onchain_data.whale_addresses)}")
            logger.info(f"  刷量标记: {onchain_data.wash_trading_flag}")
        else:
            logger.warning("无法获取链上数据")
        
        logger.info("\n" + "="*60)
        logger.info("✅ 测试完成")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # 关闭适配器
        await adapter.close()


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        logger.error("用法: python scripts/test_helius.py <CA地址>")
        logger.info("示例: python scripts/test_helius.py So11111111111111111111111111111111111111112")
        sys.exit(1)
    
    ca_address = sys.argv[1].strip()
    logger.info(f"测试CA地址: {ca_address}")
    
    await test_helius_adapter(ca_address)


if __name__ == "__main__":
    asyncio.run(main())
