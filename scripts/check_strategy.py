"""
检查CA地址是否达到策略阈值
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from loguru import logger

# 加载环境变量
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path, override=True)

from src.core.datasource import DataSourceMode
from src.adapters.dexscreener import DexScreenerAdapter
from src.strategies.engine import BuiltinStrategies


async def check_strategy(token_address: str):
    """检查CA地址的策略分析情况"""
    logger.info(f"开始检查CA地址: {token_address}")
    logger.info("=" * 60)
    
    # 初始化适配器
    adapter = DexScreenerAdapter()
    
    try:
        # 获取K线数据（需要1分钟K线数据用于策略分析）
        logger.info("正在获取K线数据...")
        klines = await adapter.get_data(
            token=token_address,
            mode=DataSourceMode.KLINE,
            intervals=["1m", "5m", "15m"]
        )
        
        if not klines:
            logger.error("[X] 未获取到K线数据，可能的原因：")
            logger.error("  1. Token地址不存在或无效")
            logger.error("  2. DexScreener API未找到该Token")
            logger.error("  3. 网络连接问题")
            return
        
        logger.info(f"[OK] 成功获取 {len(klines)} 个周期的K线数据")
        
        # 显示数据概览
        logger.info("")
        logger.info("数据概览：")
        for kline in klines:
            mc_str = f"{kline.market_cap:,.0f}" if kline.market_cap else "N/A"
            ca_str = kline.token_address or "N/A"
            logger.info(f"  {kline.interval}: 价格=${kline.close:.8f}, 成交量=${kline.volume:,.2f}, "
                       f"MC={mc_str}, CA={ca_str}")
        
        # 提取1分钟K线数据（策略需要）
        klines_1m = [k for k in klines if k.interval == "1m"]
        
        if not klines_1m:
            logger.warning("⚠️  未找到1分钟K线数据，尝试使用其他周期数据")
            # 如果没有1分钟数据，使用5分钟数据作为替代
            klines_1m = [k for k in klines if k.interval == "5m"]
        
        if not klines_1m:
            logger.error("❌ 无法获取足够的K线数据进行分析")
            return
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("执行策略分析：外源性爆发二段告警")
        logger.info("=" * 60)
        
        # 执行策略（需要至少10根K线数据）
        # 由于DexScreener API可能只返回当前数据，我们需要模拟一些历史数据
        # 或者使用现有的数据进行分析
        
        # 检查数据量
        if len(klines_1m) < 4:
            logger.warning(f"[!] K线数据不足（当前{len(klines_1m)}根，需要至少4根）")
            logger.warning("  策略需要至少4根K线数据才能进行分析")
            logger.warning("  建议：等待更多数据或使用历史数据API")
            
            # 显示当前数据详情
            logger.info("")
            logger.info("当前K线数据详情：")
            for i, kline in enumerate(klines_1m):
                logger.info(f"  [{i+1}] {kline.timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
                           f"价格=${kline.close:.8f}, 成交量=${kline.volume:,.2f}")
            
            return
        
        # 执行策略分析
        result = await BuiltinStrategies.external_burst_phase2(
            klines=klines_1m,
            m=3,
            k=1.8,
            min_volume_hits=1
        )
        
        logger.info("")
        if result:
            logger.info("[OK] 策略触发：外源性爆发二段告警")
            logger.info("")
            logger.info("告警信息：")
            logger.info(result.message)
            logger.info("")
            logger.info(f"信号强度: {result.signal_strength}/100")
            logger.info(f"策略数据: {result.data}")
        else:
            logger.info("[X] 策略未触发")
            logger.info("")
            logger.info("分析结果：")
            logger.info("  当前K线数据未满足以下条件之一：")
            logger.info("  1. 价格条件：连续3根K线收盘价递增")
            logger.info("  2. 成交量条件：至少1根K线成交量 > 前3根均量 × 1.8倍")
            logger.info("")
            logger.info("当前数据统计：")
            if len(klines_1m) >= 3:
                # 检查价格趋势
                prices = [k.close for k in klines_1m[-3:]]
                price_rising = all(prices[i] < prices[i+1] for i in range(len(prices)-1))
                logger.info(f"  最近3根K线价格: {[f'${p:.8f}' for p in prices]}")
                logger.info(f"  价格递增: {'[OK] 是' if price_rising else '[X] 否'}")
                
                # 检查成交量
                if len(klines_1m) >= 6:
                    volumes = [k.volume for k in klines_1m[-6:]]
                    recent_3 = volumes[-3:]
                    prev_3_avg = sum(volumes[-6:-3]) / 3 if len(volumes) >= 6 else 0
                    hits = sum(1 for v in recent_3 if v > prev_3_avg * 1.8)
                    logger.info(f"  最近3根K线成交量: {[f'${v:,.2f}' for v in recent_3]}")
                    logger.info(f"  前3根平均成交量: ${prev_3_avg:,.2f}")
                    logger.info(f"  成交量放大倍数: {[f'{v/prev_3_avg:.2f}x' if prev_3_avg > 0 else 'N/A' for v in recent_3]}")
                    logger.info(f"  满足放量条件(>1.8x): {hits}根")
        
        logger.info("")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"[X] 检查失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        await adapter.close()


if __name__ == "__main__":
    # 配置日志（避免Windows编码问题）
    import sys
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:HH:mm:ss} | {level: <8} | {message}",
        colorize=False
    )
    
    # 从命令行参数获取CA地址，或使用默认值
    if len(sys.argv) > 1:
        token_address = sys.argv[1]
    else:
        token_address = "0x95605f364d3d26974c38efd2657676cacf5a4444"
    
    logger.info(f"检查CA地址: {token_address}")
    logger.info("")
    
    # 运行检查
    asyncio.run(check_strategy(token_address))
