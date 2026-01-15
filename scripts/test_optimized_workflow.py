"""
优化后的工作流测试脚本
测试：
1. Enhanced Transactions API优化
2. 只使用1m K线
3. 告警去重（10分钟窗口）
4. 24小时告警统计
"""
import asyncio
import sys
import os
import time
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
from src.strategies.engine import BuiltinStrategies
from src.core.alert_tracker import get_alert_tracker
from src.core.config import ConfigManager

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    colorize=False
)


async def test_enhanced_transactions(ca_address: str):
    """测试1: Enhanced Transactions API优化"""
    logger.info("=" * 80)
    logger.info("测试1: Enhanced Transactions API优化")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    start_time = time.time()
    
    # 获取最近10分钟交易历史
    logger.info(f"\n获取最近10分钟交易历史: {ca_address}")
    transactions = await adapter._get_recent_transactions(ca_address, minutes=10)
    
    elapsed = time.time() - start_time
    
    logger.info(f"✅ 获取完成")
    logger.info(f"  交易记录数: {len(transactions)}")
    logger.info(f"  耗时: {elapsed:.2f}秒")
    
    if transactions:
        # 显示前几条交易的时间信息
        logger.info(f"\n前5条交易时间信息:")
        for i, tx in enumerate(transactions[:5]):
            tx_time = adapter._parse_transaction_time(tx)
            logger.info(f"  {i+1}. 时间: {tx_time}, 成交量: {tx.get('volume', 0):,.2f}")
    
    await adapter.close()
    return elapsed < 2.0  # 目标：2秒内完成


async def test_1m_kline_only(ca_address: str):
    """测试2: 只使用1m K线"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2: 只使用1m K线（移除5m和15m）")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    
    # 只请求1m K线
    logger.info(f"\n获取1m K线数据: {ca_address}")
    klines = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m"]  # 只请求1m
    )
    
    logger.info(f"✅ 获取完成")
    logger.info(f"  K线数量: {len(klines)}")
    logger.info(f"  预期: 1根（只有1m）")
    
    if klines:
        kline = klines[0]
        logger.info(f"\nK线详情:")
        logger.info(f"  周期: {kline.interval}")
        logger.info(f"  符号: {kline.symbol}")
        logger.info(f"  价格: ${kline.close:.10f}")
        logger.info(f"  成交量: {kline.volume:,.2f}")
        if kline.quote_volume:
            logger.info(f"  成交额: ${kline.quote_volume:,.2f}")
    
    await adapter.close()
    return len(klines) == 1 and klines[0].interval == "1m"


async def test_alert_dedup(ca_address: str):
    """测试3: 告警去重（10分钟窗口）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3: 告警去重（10分钟窗口）")
    logger.info("=" * 80)
    
    tracker = get_alert_tracker()
    
    # 第一次告警
    logger.info(f"\n【测试3.1】第一次告警: {ca_address}")
    should_alert_1, time_since_1 = tracker.should_alert(ca_address)
    logger.info(f"  应该告警: {should_alert_1}, 距离上次: {time_since_1:.1f}秒")
    
    if should_alert_1:
        tracker.record_alert(ca_address, "外源性爆发二段告警", 80)
        logger.info(f"  ✅ 记录告警成功")
    
    # 立即再次检查（应该被去重）
    logger.info(f"\n【测试3.2】立即再次检查（应该被去重）")
    should_alert_2, time_since_2 = tracker.should_alert(ca_address)
    logger.info(f"  应该告警: {should_alert_2}, 距离上次: {time_since_2:.1f}秒")
    
    if not should_alert_2:
        logger.info(f"  ✅ 去重成功（在10分钟窗口内）")
    else:
        logger.warning(f"  ⚠️  去重失败（应该被去重）")
    
    return not should_alert_2


async def test_24h_statistics(ca_address: str):
    """测试4: 24小时告警统计"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4: 24小时告警统计")
    logger.info("=" * 80)
    
    tracker = get_alert_tracker()
    
    # 记录几次告警
    logger.info(f"\n【测试4.1】记录多次告警")
    for i in range(3):
        tracker.record_alert(ca_address, f"测试策略{i+1}", 70 + i * 10)
        logger.info(f"  记录告警 {i+1}: 策略=测试策略{i+1}")
    
    # 查询24小时统计
    logger.info(f"\n【测试4.2】查询24小时告警次数")
    count_24h = tracker.get_24h_alert_count(ca_address)
    logger.info(f"  近24小时告警次数: {count_24h}")
    logger.info(f"  预期: >= 3次（包含刚才记录的3次）")
    
    # 测试其他token（应该为0）
    logger.info(f"\n【测试4.3】测试其他token统计")
    other_token = "OtherToken123"
    count_other = tracker.get_24h_alert_count(other_token)
    logger.info(f"  {other_token} 近24小时告警次数: {count_other}")
    logger.info(f"  预期: 0次（从未告警过）")
    
    return count_24h >= 3 and count_other == 0


async def test_full_workflow(ca_address: str):
    """测试5: 完整工作流（CA -> 数据获取 -> 策略分析 -> 告警）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5: 完整工作流性能测试")
    logger.info("=" * 80)
    
    adapter = HeliusAdapter()
    tracker = get_alert_tracker()
    
    # 记录开始时间
    t0 = time.time()
    
    # 步骤1: 获取1m K线数据
    logger.info(f"\n【步骤1】获取1m K线数据")
    t1 = time.time()
    klines = await adapter.get_data(
        token=ca_address,
        mode=DataSourceMode.KLINE,
        intervals=["1m"]
    )
    t2 = time.time()
    logger.info(f"  耗时: {t2 - t1:.2f}秒")
    
    if not klines:
        logger.error("  ❌ 无法获取K线数据")
        await adapter.close()
        return False
    
    # 步骤2: 构造10根K线序列（用于外源性二段策略）
    logger.info(f"\n【步骤2】构造K线序列（模拟10根）")
    kline_1m = klines[0]
    kline_sequence = [kline_1m] * 10
    logger.info(f"  K线序列长度: {len(kline_sequence)}")
    
    # 步骤3: 执行策略分析
    logger.info(f"\n【步骤3】执行外源性爆发二段告警策略")
    t3 = time.time()
    result = await BuiltinStrategies.external_burst_phase2(
        klines=kline_sequence,
        m=3,
        k=1.8,
        min_volume_hits=1
    )
    t4 = time.time()
    logger.info(f"  策略执行耗时: {t4 - t3:.3f}秒")
    
    # 步骤4: 检查去重和统计
    logger.info(f"\n【步骤4】检查告警去重和统计")
    should_alert, time_since = tracker.should_alert(ca_address)
    count_24h = tracker.get_24h_alert_count(ca_address)
    
    logger.info(f"  应该告警: {should_alert}")
    logger.info(f"  距离上次告警: {time_since:.1f}秒")
    logger.info(f"  近24小时告警次数: {count_24h}")
    
    # 如果策略触发且应该告警，记录告警
    if result and should_alert:
        tracker.record_alert(
            token=ca_address,
            strategy_name=result.strategy_name,
            signal_strength=result.signal_strength
        )
        logger.info(f"  ✅ 告警已记录")
    
    t5 = time.time()
    total_time = t5 - t0
    
    logger.info(f"\n【性能总结】")
    logger.info(f"  数据获取: {t2 - t1:.2f}秒")
    logger.info(f"  策略分析: {t4 - t3:.3f}秒")
    logger.info(f"  去重检查: {t5 - t4:.3f}秒")
    logger.info(f"  总耗时: {total_time:.2f}秒")
    logger.info(f"  目标: < 2秒")
    
    await adapter.close()
    return total_time < 2.0


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        logger.error("用法: python scripts/test_optimized_workflow.py <CA地址>")
        logger.info("示例: python scripts/test_optimized_workflow.py EYqur2HYSHkpzFpwTt8rD97JhFE7YL3LTa3Yue2hpump")
        sys.exit(1)
    
    ca_address = sys.argv[1].strip()
    
    logger.info("=" * 80)
    logger.info("优化后的工作流测试")
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
        # 测试1: Enhanced Transactions优化
        results["Enhanced Transactions优化"] = await test_enhanced_transactions(ca_address)
        
        # 测试2: 只使用1m K线
        results["只使用1m K线"] = await test_1m_kline_only(ca_address)
        
        # 测试3: 告警去重
        results["告警去重"] = await test_alert_dedup(ca_address)
        
        # 测试4: 24小时统计
        results["24小时统计"] = await test_24h_statistics(ca_address)
        
        # 测试5: 完整工作流
        results["完整工作流性能"] = await test_full_workflow(ca_address)
        
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
        logger.info("✅ 所有测试通过！优化成功")
    else:
        logger.warning("⚠️  部分测试未通过，请检查日志")
    logger.info("=" * 80)
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
