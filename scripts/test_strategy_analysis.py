"""
测试策略分析功能（使用Helius适配器）
用法: python scripts/test_strategy_analysis.py <CA地址>
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
from src.strategies.engine import StrategyEngine, BuiltinStrategies
from src.core.config import ConfigManager

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    colorize=False
)


async def test_strategy_analysis(ca_address: str):
    """测试策略分析"""
    logger.info(f"开始测试策略分析，CA地址: {ca_address}")
    logger.info("=" * 80)
    
    # 检查API密钥
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        logger.error("未配置HELIUS_API_KEY，请在.env文件中设置")
        return
    
    # 创建适配器
    adapter = HeliusAdapter()
    
    # 检查是否为Solana地址
    if not adapter._is_solana_address(ca_address):
        logger.warning(f"不是有效的Solana地址格式: {ca_address}")
        return
    
    logger.info("✅ Solana地址格式验证通过\n")
    
    try:
        # 步骤1: 获取K线数据
        logger.info("=" * 80)
        logger.info("步骤1: 获取K线数据")
        logger.info("=" * 80)
        
        intervals = ["1m", "5m", "15m"]
        klines = await adapter.get_data(
            token=ca_address,
            mode=DataSourceMode.KLINE,
            intervals=intervals
        )
        
        if not klines:
            logger.error("❌ 无法获取K线数据")
            return
        
        logger.info(f"✅ 成功获取 {len(klines)} 个周期的K线数据\n")
        
        # 显示K线数据详情
        for kline in klines:
            logger.info(f"周期: {kline.interval}")
            logger.info(f"  符号: {kline.symbol}")
            logger.info(f"  时间戳: {kline.timestamp}")
            logger.info(f"  开盘价: ${kline.open:,.10f}")
            logger.info(f"  最高价: ${kline.high:,.10f}")
            logger.info(f"  最低价: ${kline.low:,.10f}")
            logger.info(f"  收盘价: ${kline.close:,.10f}")
            logger.info(f"  成交量: {kline.volume:,.2f}")
            if kline.quote_volume:
                logger.info(f"  成交额: ${kline.quote_volume:,.2f}")
            if kline.market_cap:
                logger.info(f"  市值: ${kline.market_cap:,.2f}")
            logger.info("")
        
        # 步骤2: 执行策略分析
        logger.info("=" * 80)
        logger.info("步骤2: 执行策略分析")
        logger.info("=" * 80)
        
        config_manager = ConfigManager()
        strategy_engine = StrategyEngine(config_manager)
        
        # 获取1分钟K线数据用于策略分析
        kline_1m = next((k for k in klines if k.interval == "1m"), None)
        if not kline_1m:
            logger.warning("未找到1分钟K线数据，使用第一个周期的数据")
            kline_1m = klines[0]
        
        # 为了测试"外源性爆发二段告警"策略，我们需要多个K线数据点
        # 由于Helius当前只返回当前价格，我们创建一个序列用于测试
        # 实际使用中，连续监测会积累多个数据点
        kline_sequence = [kline_1m] * 10  # 模拟10个数据点
        
        logger.info(f"使用K线数据进行策略分析\n")
        logger.info(f"单个数据点策略: 使用1分钟K线数据")
        logger.info(f"序列策略: 使用10个数据点序列\n")
        
        results = []
        
        # 测试1: 量增价升策略
        logger.info("测试策略: 量增价升")
        try:
            result = await BuiltinStrategies.volume_price_rise(
                data=kline_1m,
                volume_mult=1.5
            )
            if result:
                results.append(("量增价升", result))
                logger.info(f"  ✅ 策略触发: 量增价升")
                logger.info(f"     信号强度: {result.signal_strength}")
                logger.info(f"     信号类型: {result.strategy_name}")
            else:
                logger.info(f"  ⚠️  策略未触发: 量增价升（需要成交量 > 平均成交量 * 1.5 且价格上涨）")
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: 量增价升, error={e}")
        logger.info("")
        
        # 测试2: 5分钟交易量告警
        logger.info("测试策略: 5分钟交易量告警")
        try:
            result = await BuiltinStrategies.volume_alert_5k(
                data=kline_1m,
                volume_threshold=5000.0
            )
            if result:
                results.append(("5分钟交易量告警", result))
                logger.info(f"  ✅ 策略触发: 5分钟交易量告警")
                logger.info(f"     信号强度: {result.signal_strength}")
                logger.info(f"     信号类型: {result.strategy_name}")
            else:
                logger.info(f"  ⚠️  策略未触发: 5分钟交易量告警（需要成交量 > 5000 USD）")
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: 5分钟交易量告警, error={e}")
        logger.info("")
        
        # 测试3: 外源性爆发二段告警
        logger.info("测试策略: 外源性爆发二段告警")
        try:
            result = await BuiltinStrategies.external_burst_phase2(
                klines=kline_sequence,
                m=3,
                k=1.8,
                min_volume_hits=1
            )
            if result:
                results.append(("外源性爆发二段告警", result))
                logger.info(f"  ✅ 策略触发: 外源性爆发二段告警")
                logger.info(f"     信号强度: {result.signal_strength}")
                logger.info(f"     信号类型: {result.strategy_name}")
            else:
                logger.info(f"  ⚠️  策略未触发: 外源性爆发二段告警")
                logger.info(f"     需要条件：连续3根K线收盘价上涨，且至少1根满足成交量条件")
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: 外源性爆发二段告警, error={e}")
        logger.info("")
        
        # 步骤3: 显示分析结果总结
        logger.info("=" * 80)
        logger.info("步骤3: 分析结果总结")
        logger.info("=" * 80)
        
        if results:
            logger.info(f"✅ 共触发 {len(results)} 个策略信号:\n")
            for strategy_name, result in results:
                logger.info(f"策略: {strategy_name}")
                logger.info(f"  信号强度: {result.signal_strength}")
                logger.info(f"  信号类型: {result.strategy_name}")
                logger.info(f"  消息: {result.message}")
                logger.info("")
        else:
            logger.info("⚠️  未触发任何策略信号")
            logger.info("提示：")
            logger.info("  - 策略需要满足特定条件才会触发")
            logger.info("  - 当前数据可能不满足策略阈值")
            logger.info("  - 连续监测会积累更多数据点，提高触发概率")
        
        # 步骤4: 数据质量评估
        logger.info("=" * 80)
        logger.info("步骤4: 数据质量评估")
        logger.info("=" * 80)
        
        logger.info(f"数据源: {adapter.get_source_name()}")
        logger.info(f"代币地址: {ca_address}")
        logger.info(f"K线周期数: {len(klines)}")
        logger.info(f"数据完整性: {'✅ 完整' if all(k.close > 0 for k in klines) else '⚠️ 部分缺失'}")
        logger.info(f"价格数据: {'✅ 有效' if kline_1m.close > 0 else '❌ 无效'}")
        logger.info(f"成交量数据: {'✅ 有效' if kline_1m.volume >= 0 else '❌ 无效'}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 测试完成")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await adapter.close()


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        logger.error("用法: python scripts/test_strategy_analysis.py <CA地址>")
        logger.info("示例: python scripts/test_strategy_analysis.py CfJxopGjVVPWsbaDM8izGbi3gL5U2C4tDYxeX32dpump")
        sys.exit(1)
    
    ca_address = sys.argv[1].strip()
    logger.info(f"测试CA地址: {ca_address}\n")
    
    await test_strategy_analysis(ca_address)


if __name__ == "__main__":
    asyncio.run(main())
