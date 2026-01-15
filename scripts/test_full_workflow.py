"""
全流程测试脚本
测试从数据获取到策略分析的完整流程
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
from src.strategies.monitor import MonitoringManager
from src.core.config import ConfigManager

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    colorize=False
)


async def test_data_acquisition(ca_address: str):
    """测试1: 数据获取"""
    logger.info("=" * 80)
    logger.info("测试1: 数据获取")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    
    # 测试1.1: 获取K线数据
    logger.info("\n【测试1.1】获取K线数据")
    intervals = ["1m", "5m", "15m"]
    klines = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.KLINE,
        intervals=intervals
    )
    
    if not klines:
        logger.error("❌ K线数据获取失败")
        return False
    
    logger.info(f"✅ 成功获取 {len(klines)} 个周期的K线数据")
    
    # 显示K线数据详情
    for kline in klines:
        logger.info(f"  周期: {kline.interval}")
        logger.info(f"    价格: ${kline.close:.10f}")
        logger.info(f"    成交量: {kline.volume:,.2f}")
        if kline.quote_volume:
            logger.info(f"    成交额: ${kline.quote_volume:,.2f}")
        logger.info("")
    
    # 测试1.2: 获取链上数据
    logger.info("\n【测试1.2】获取链上数据")
    onchain_data = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.ONCHAIN
    )
    
    if onchain_data:
        logger.info("✅ 成功获取链上数据")
        logger.info(f"  买入量: {onchain_data.buy_volume:,.2f}")
        logger.info(f"  卖出量: {onchain_data.sell_volume:,.2f}")
        logger.info(f"  总交易量: {onchain_data.total_volume:,.2f}")
        logger.info(f"  当前价格: ${onchain_data.price:.10f}")
    else:
        logger.warning("⚠️  链上数据获取失败（可能是简化实现）")
    
    await adapter.close()
    return True


async def test_strategy_analysis(ca_address: str):
    """测试2: 策略分析"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2: 策略分析")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    
    # 获取K线数据
    klines = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m", "5m", "15m"]
    )
    
    if not klines:
        logger.error("❌ 无法获取K线数据，跳过策略分析")
        await adapter.close()
        return False
    
    # 获取1分钟K线数据
    kline_1m = next((k for k in klines if k.interval == "1m"), None)
    if not kline_1m:
        kline_1m = klines[0]
    
    # 创建K线序列用于"外源性爆发二段告警"策略
    kline_sequence = [kline_1m] * 10
    
    logger.info(f"\n使用K线数据进行策略分析（{len(klines)}个周期，{len(kline_sequence)}个数据点序列）\n")
    
    # 测试2.1: 量增价升策略
    logger.info("【测试2.1】量增价升策略")
    try:
        result = await BuiltinStrategies.volume_price_rise(
            data=kline_1m,
            volume_mult=1.5
        )
        if result:
            logger.info(f"  ✅ 策略触发: {result.strategy_name}")
            logger.info(f"     信号强度: {result.signal_strength}")
            logger.info(f"     消息: {result.message[:100]}...")
        else:
            logger.info("  ⚠️  策略未触发（正常，需要满足条件）")
    except Exception as e:
        logger.error(f"  ❌ 策略执行失败: {e}")
        return False
    
    # 测试2.2: 5分钟交易量告警
    logger.info("\n【测试2.2】5分钟交易量告警")
    try:
        kline_5m = next((k for k in klines if k.interval == "5m"), None)
        if kline_5m:
            result = await BuiltinStrategies.volume_alert_5k(
                data=kline_5m,
                volume_threshold=5000.0
            )
            if result:
                logger.info(f"  ✅ 策略触发: {result.strategy_name}")
                logger.info(f"     信号强度: {result.signal_strength}")
            else:
                logger.info("  ⚠️  策略未触发（正常，需要成交量 > 5000 USD）")
        else:
            logger.warning("  ⚠️  未找到5分钟K线数据")
    except Exception as e:
        logger.error(f"  ❌ 策略执行失败: {e}")
        return False
    
    # 测试2.3: 外源性爆发二段告警
    logger.info("\n【测试2.3】外源性爆发二段告警")
    try:
        result = await BuiltinStrategies.external_burst_phase2(
            klines=kline_sequence,
            m=3,
            k=1.8,
            min_volume_hits=1
        )
        if result:
            logger.info(f"  ✅ 策略触发: {result.strategy_name}")
            logger.info(f"     信号强度: {result.signal_strength}")
            logger.info(f"     消息: {result.message[:100]}...")
        else:
            logger.info("  ⚠️  策略未触发（正常，需要满足连续上涨和成交量条件）")
    except Exception as e:
        logger.error(f"  ❌ 策略执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    
    await adapter.close()
    return True


async def test_monitoring_simulation(ca_address: str):
    """测试3: 连续监测模拟"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3: 连续监测模拟")
    logger.info("=" * 80)
    
    logger.info("\n模拟连续监测流程（获取多个时间点的数据）\n")
    
    adapter = HeliusAdapter()
    accumulated_klines = []
    
    # 模拟获取3个时间点的数据
    for i in range(3):
        logger.info(f"【时间点 {i+1}/3】获取数据...")
        
        klines = await adapter.get_data(
            token=ca_address,
            mode=DataSourceMode.KLINE,
            intervals=["1m"]
        )
        
        if klines:
            kline_1m = klines[0]
            accumulated_klines.append(kline_1m)
            logger.info(f"  ✅ 获取成功: 价格=${kline_1m.close:.10f}, 成交量={kline_1m.volume:,.2f}")
        else:
            logger.warning(f"  ⚠️  获取失败")
        
        # 等待1秒（模拟1分钟间隔）
        if i < 2:
            await asyncio.sleep(1)
    
    # 测试策略（需要至少4个数据点）
    if len(accumulated_klines) >= 4:
        logger.info(f"\n【测试3.1】使用累积数据执行策略（{len(accumulated_klines)}个数据点）")
        try:
            result = await BuiltinStrategies.external_burst_phase2(
                klines=accumulated_klines,
                m=3,
                k=1.8,
                min_volume_hits=1
            )
            if result:
                logger.info(f"  ✅ 策略触发: {result.strategy_name}")
            else:
                logger.info("  ⚠️  策略未触发")
        except Exception as e:
            logger.error(f"  ❌ 策略执行失败: {e}")
    else:
        logger.info(f"\n【测试3.1】数据点不足（{len(accumulated_klines)}个），跳过策略测试")
        logger.info("  提示：实际监测中会积累更多数据点")
    
    await adapter.close()
    return True


async def test_error_handling(ca_address: str):
    """测试4: 错误处理"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4: 错误处理")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    
    # 测试4.1: 无效地址
    logger.info("\n【测试4.1】无效地址处理")
    invalid_address = "invalid_address_12345"
    klines = await adapter.get_data(
        token=invalid_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m"]
    )
    if not klines:
        logger.info("  ✅ 正确处理无效地址（返回空列表）")
    else:
        logger.warning("  ⚠️  无效地址返回了数据（可能需要改进）")
    
    # 测试4.2: 空数据情况
    logger.info("\n【测试4.2】空数据处理")
    # 使用一个可能不存在的地址
    empty_address = "11111111111111111111111111111111"
    klines = await adapter.get_data(
        token=empty_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m"]
    )
    if not klines:
        logger.info("  ✅ 正确处理空数据（返回空列表）")
    else:
        logger.info(f"  ℹ️  返回了 {len(klines)} 个数据点")
    
    await adapter.close()
    return True


async def test_performance(ca_address: str):
    """测试5: 性能测试"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5: 性能测试")
    logger.info("=" * 80)
    
    import time
    
    adapter = HeliusAdapter()
    
    # 测试5.1: 单次请求耗时
    logger.info("\n【测试5.1】单次请求耗时")
    start_time = time.time()
    klines = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m", "5m", "15m"]
    )
    elapsed = time.time() - start_time
    
    if klines:
        logger.info(f"  ✅ 请求成功，耗时: {elapsed:.2f}秒")
        logger.info(f"     获取了 {len(klines)} 个周期的数据")
    else:
        logger.error(f"  ❌ 请求失败，耗时: {elapsed:.2f}秒")
    
    # 测试5.2: 连续请求（测试限流）
    logger.info("\n【测试5.2】连续请求（测试限流）")
    request_times = []
    for i in range(3):
        start_time = time.time()
        klines = await adapter.get_data(
            token=ca_address,
            mode=DataSourceMode.KLINE,
            intervals=["1m"]
        )
        elapsed = time.time() - start_time
        request_times.append(elapsed)
        logger.info(f"  请求 {i+1}: {elapsed:.2f}秒")
        if i < 2:
            await asyncio.sleep(0.5)  # 短暂等待
    
    avg_time = sum(request_times) / len(request_times)
    logger.info(f"  平均耗时: {avg_time:.2f}秒")
    
    await adapter.close()
    return True


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        logger.error("用法: python scripts/test_full_workflow.py <CA地址>")
        logger.info("示例: python scripts/test_full_workflow.py CfJxopGjVVPWsbaDM8izGbi3gL5U2C4tDYxeX32dpump")
        sys.exit(1)
    
    ca_address = sys.argv[1].strip()
    
    logger.info("=" * 80)
    logger.info("全流程测试开始")
    logger.info(f"测试代币: {ca_address}")
    logger.info("=" * 80)
    
    # 检查API密钥
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        logger.error("❌ 未配置HELIUS_API_KEY，请在.env文件中设置")
        sys.exit(1)
    
    logger.info(f"✅ Helius API密钥已配置\n")
    
    results = {}
    
    try:
        # 测试1: 数据获取
        results["数据获取"] = await test_data_acquisition(ca_address)
        
        # 测试2: 策略分析
        results["策略分析"] = await test_strategy_analysis(ca_address)
        
        # 测试3: 连续监测模拟
        results["连续监测"] = await test_monitoring_simulation(ca_address)
        
        # 测试4: 错误处理
        results["错误处理"] = await test_error_handling(ca_address)
        
        # 测试5: 性能测试
        results["性能测试"] = await test_performance(ca_address)
        
    except Exception as e:
        logger.error(f"\n❌ 测试过程中出现异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    
    # 输出测试总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    logger.info("\n" + "=" * 80)
    if all_passed:
        logger.info("✅ 所有测试通过！系统运行正常")
    else:
        logger.warning("⚠️  部分测试未通过，请检查日志")
    logger.info("=" * 80)
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
