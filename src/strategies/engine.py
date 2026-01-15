"""
策略引擎
支持内置策略和YAML自定义策略
"""
import asyncio
from typing import List, Dict, Any, Optional, Sequence
from dataclasses import dataclass
from loguru import logger

from src.core.datasource import StandardKlineData, OnChainData, DataSourceMode


@dataclass
class SignalResult:
    """策略信号结果"""
    strategy_name: str
    token: str
    signal_strength: int  # 0-100
    message: str
    data: Dict[str, Any]  # 原始数据
    timestamp: str


class BuiltinStrategies:
    """内置策略集合"""
    
    @staticmethod
    async def volume_price_rise(
        data: StandardKlineData | OnChainData,
        volume_mult: float = 1.5
    ) -> Optional[SignalResult]:
        """
        量增价升策略
        
        Args:
            data: K线或链上数据
            volume_mult: 成交量倍数阈值
        """
        if isinstance(data, StandardKlineData):
            # K线模式
            volume = data.volume
            price_change = (data.close - data.open) / data.open if data.open > 0 else 0
            
            # 简化版：需要历史数据计算平均成交量
            # 实际应该从数据库获取24小时平均成交量
            avg_volume = volume / 2  # 临时估算
            
            if volume > avg_volume * volume_mult and price_change > 0:
                # 提取信息
                token_symbol = data.symbol.split("/")[0] if "/" in data.symbol else data.symbol
                token_address = data.token_address or "N/A"
                market_cap = data.market_cap
                
                # 格式化市值
                if market_cap:
                    if market_cap >= 1_000_000_000:
                        mc_str = f"${market_cap/1_000_000_000:.2f}B"
                    elif market_cap >= 1_000_000:
                        mc_str = f"${market_cap/1_000_000:.2f}M"
                    elif market_cap >= 1_000:
                        mc_str = f"${market_cap/1_000:.2f}K"
                    else:
                        mc_str = f"${market_cap:,.2f}"
                else:
                    mc_str = "N/A"
                
                # 格式化CA地址（使用Telegram代码格式，可点击复制）
                ca_display = f"`{token_address}`" if token_address != "N/A" else "N/A"
                
                return SignalResult(
                    strategy_name="量增价升",
                    token=data.symbol,
                    signal_strength=min(100, int(price_change * 1000 + 50)),
                    message=f"🔔 量增价升信号\n"
                           f"Symbol: {token_symbol}\n"
                           f"CA: {ca_display}\n"
                           f"价格: ${data.close:.8f}\n"
                           f"涨幅: {price_change*100:.2f}%\n"
                           f"代币当前MC: {mc_str}",
                    data=data.to_dict(),
                    timestamp=data.timestamp.isoformat()
                )
        
        elif isinstance(data, OnChainData):
            # 链上模式
            buy_ratio = data.buy_volume / data.total_volume if data.total_volume > 0 else 0
            price_change = data.price_change_24h or 0
            
            if buy_ratio > 0.6 and price_change > 0:
                return SignalResult(
                    strategy_name="量增价升",
                    token=data.token_address,
                    signal_strength=min(100, int(price_change * 10 + buy_ratio * 50)),
                    message=f"🔔 量增价升信号: {data.token_address}\n价格: ${data.price:.8f}\n买入占比: {buy_ratio*100:.2f}%",
                    data=data.to_dict(),
                    timestamp=data.timestamp.isoformat()
                )
        
        return None
    
    @staticmethod
    async def low_volume_new_high(
        data: StandardKlineData | OnChainData
    ) -> Optional[SignalResult]:
        """缩量新高策略"""
        # 实现逻辑...
        return None
    
    @staticmethod
    async def high_volume_top(
        data: StandardKlineData | OnChainData
    ) -> Optional[SignalResult]:
        """天量见顶策略"""
        # 实现逻辑...
        return None
    
    @staticmethod
    async def external_burst_phase2(
        klines: Sequence[StandardKlineData],
        m: int = 3,
        k: float = 1.8,
        min_volume_hits: int = 1,
    ) -> Optional[SignalResult]:
        """
        外源性爆发二段告警

        基于最近若干根连续K线，寻找「价格连续上涨 + 成交量放大」的结构：
        - 价格条件：出现连续3根K线收盘价 > 前一根收盘价
        - 成交量条件：对这3根中的每一根，比较「当前成交量」与「其前 M 根K线成交量均值」，
          若当前成交量 > 均值 × K，则记为一次有效放量；要求至少满足 min_volume_hits 次
        - 默认参数：M=3，K=1.8，min_volume_hits=1（只需一根满足成交量条件）

        说明：
        - 要求 klines 已按时间从旧到新排序
        - 若历史数据不足以支撑 M 和 3 根连续K线，将直接返回 None
        """
        klines = [k for k in klines if isinstance(k, StandardKlineData)]
        if len(klines) < max(m + 3, 4):
            logger.info(
                f"外源性爆发二段告警：数据不足，长度={len(klines)}, "
                f"需要至少 {max(m + 3, 4)} 根K线"
            )
            return None

        # 按时间排序（防止上游返回顺序不稳定）
        klines = sorted(klines, key=lambda x: x.timestamp)

        best_window = None  # (start_idx, end_idx, hits, ref_kline)

        # 从第1根开始，寻找 3 根连续收盘价递增的窗口
        for i in range(1, len(klines) - 1):
            k0 = klines[i - 1]
            k1 = klines[i]
            k2 = klines[i + 1]

            # 价格条件：3 连阳（收盘价严格递增）
            if not (k0.close < k1.close < k2.close):
                continue

            # 对这3根K线分别做成交量二段放大检测
            hits = 0
            for idx in (i - 1, i, i + 1):
                # 需要有 idx 之前的 m 根K线
                if idx - m < 0:
                    continue
                prev_segment = klines[idx - m:idx]
                if len(prev_segment) < m:
                    continue

                avg_volume = sum(p.volume for p in prev_segment) / m
                cur_volume = klines[idx].volume

                if avg_volume > 0 and cur_volume > avg_volume * k:
                    hits += 1

            if hits >= min_volume_hits:
                # 以窗口最后一根K线作为代表
                ref = k2
                best_window = (i - 1, i + 1, hits, ref)
                break

        if not best_window:
            return None

        _, _, hits, ref_kline = best_window

        from datetime import datetime

        # 提取信息
        token_symbol = ref_kline.symbol.split("/")[0] if "/" in ref_kline.symbol else ref_kline.symbol
        token_address = ref_kline.token_address or "N/A"
        market_cap = ref_kline.market_cap
        
        # 格式化市值
        if market_cap:
            if market_cap >= 1_000_000_000:
                mc_str = f"${market_cap/1_000_000_000:.2f}B"
            elif market_cap >= 1_000_000:
                mc_str = f"${market_cap/1_000_000:.2f}M"
            elif market_cap >= 1_000:
                mc_str = f"${market_cap/1_000:.2f}K"
            else:
                mc_str = f"${market_cap:,.2f}"
        else:
            mc_str = "N/A"
        
        # 格式化CA地址（使用Telegram代码格式，可点击复制）
        ca_display = f"`{token_address}`" if token_address != "N/A" else "N/A"

        message = (
            f"🚀 外源性爆发二段告警\n"
            f"Symbol: {token_symbol}\n"
            f"CA: {ca_display}\n"
            f"价格出现连续3根上涨K线（收盘价递增）\n"
            f"成交量在3根K线中有 {hits} 根显著放大（>{m} 根均量的 {k} 倍）\n"
            f"代币当前MC: {mc_str}\n"
            f"参考时间: {ref_kline.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        return SignalResult(
            strategy_name="外源性爆发二段告警",
            token=token_symbol,
            signal_strength=min(100, 60 + hits * 10),  # 依据放量段数粗略给出强度
            message=message,
            data={
                "m": m,
                "k": k,
                "min_volume_hits": min_volume_hits,
                "window_size": 3,
                "used_klines": len(klines),
            },
            timestamp=datetime.now().isoformat(),
        )

    @staticmethod
    async def volume_alert_5k(
        data: StandardKlineData | OnChainData,
        volume_threshold: float = 5000.0
    ) -> Optional[SignalResult]:
        """
        5分钟交易量告警策略（测试策略）
        只检测最近5分钟的交易量是否大于阈值
        
        Args:
            data: K线或链上数据
            volume_threshold: 交易量阈值（默认5K USD）
        """
        if isinstance(data, StandardKlineData):
            # 只处理5分钟K线数据
            logger.info(f"策略检查: interval={data.interval}, volume={data.volume}, threshold={volume_threshold}")
            if data.interval != "5m":
                logger.warning(f"跳过非5分钟K线数据: interval={data.interval}, 期望5m")
                return None
            
            volume = data.volume
            logger.info(f"5分钟交易量检查: volume={volume:,.2f} USD, threshold={volume_threshold:,.2f} USD, 是否触发: {volume > volume_threshold}")
            
            # 检查5分钟交易量是否大于阈值
            if volume > volume_threshold:
                # 提取信息
                token_symbol = data.symbol.split("/")[0] if "/" in data.symbol else data.symbol
                token_address = data.token_address or "N/A"
                market_cap = data.market_cap
                
                # 格式化市值
                if market_cap:
                    if market_cap >= 1_000_000_000:
                        mc_str = f"${market_cap/1_000_000_000:.2f}B"
                    elif market_cap >= 1_000_000:
                        mc_str = f"${market_cap/1_000_000:.2f}M"
                    elif market_cap >= 1_000:
                        mc_str = f"${market_cap/1_000:.2f}K"
                    else:
                        mc_str = f"${market_cap:,.2f}"
                else:
                    mc_str = "N/A"
                
                # 格式化CA地址（使用Telegram代码格式，可点击复制）
                ca_display = f"`{token_address}`" if token_address != "N/A" else "N/A"
                
                return SignalResult(
                    strategy_name="5分钟交易量告警",
                    token=data.symbol,
                    signal_strength=min(100, int((volume / volume_threshold) * 20)),
                    message=f"🔔 交易量告警\n"
                           f"Symbol: {token_symbol}\n"
                           f"CA: {ca_display}\n"
                           f"最近5分钟交易量: ${volume:,.2f}\n"
                           f"阈值: ${volume_threshold:,.2f}\n"
                           f"代币当前MC: {mc_str}",
                    data=data.to_dict(),
                    timestamp=data.timestamp.isoformat()
                )
        
        elif isinstance(data, OnChainData):
            # 链上模式：暂不支持5分钟精确统计，跳过
            logger.debug("链上模式暂不支持5分钟交易量检测")
            return None
        
        return None


class StrategyEngine:
    """策略引擎 - 执行策略计算"""
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.builtin = BuiltinStrategies()
    
    async def execute_strategies(
        self,
        token: str,
        data: StandardKlineData | OnChainData | List[StandardKlineData],
        user_id: int,
        mode: DataSourceMode
    ) -> List[SignalResult]:
        """
        执行所有启用的策略
        
        Args:
            token: Token符号或地址
            data: 数据（K线或链上）
            user_id: 用户ID
            mode: 数据源模式
            
        Returns:
            List[SignalResult]: 信号结果列表
        """
        strategies = self.config.get_user_strategies(user_id)
        if not strategies:
            logger.warning(f"用户 {user_id} 未启用任何策略，使用默认策略")
            # 默认启用"5分钟交易量告警"策略（测试用）
            strategies = ["5分钟交易量告警"]
        
        logger.info(f"执行策略: {token}, 用户={user_id}, 策略列表={strategies}")
        
        results = []
        raw_kline_list: Optional[List[StandardKlineData]] = None
        
        # 处理K线数据（可能是多个周期）
        if isinstance(data, list):
            raw_kline_list = [d for d in data if isinstance(d, StandardKlineData)]
            intervals_list = [d.interval for d in raw_kline_list]
            logger.info(f"收到K线数据列表: {token}, 数据量={len(data)}, 周期列表={intervals_list}, 策略列表={strategies}")
            
            # 对于"5分钟交易量告警"策略，优先使用5分钟数据
            if "5分钟交易量告警" in strategies or "volume_alert_5k" in strategies:
                logger.info(f"策略需要5分钟数据，开始查找...")
                # 查找5分钟数据 - 遍历所有数据，确保能找到
                data_5m = None
                for d in raw_kline_list:
                    logger.debug(f"检查数据项: interval={d.interval}, type={type(d).__name__}")
                    if d.interval == "5m":
                        data_5m = d
                        break
                
                if data_5m:
                    data = data_5m
                    logger.info(f"✅ 找到5分钟K线数据: {token}, volume={data.volume:,.2f}, interval={data.interval}")
                else:
                    # 如果没有5分钟数据，使用最新周期的数据
                    logger.warning(
                        f"❌ 未找到5分钟K线数据: {token}, 可用周期={intervals_list}, "
                        f"数据详情: {[(d.interval, type(d).__name__) for d in raw_kline_list]}"
                    )
                    data = raw_kline_list[-1] if raw_kline_list else None
            else:
                # 其他策略使用最新周期的数据
                logger.info(f"策略不需要5分钟数据，使用最新周期数据")
                data = raw_kline_list[-1] if raw_kline_list else None
        
        if data is None:
            logger.warning(f"数据为空，无法执行策略: {token}")
            return []
        
        logger.info(f"使用数据执行策略: {token}, 数据类型={type(data).__name__}, interval={getattr(data, 'interval', 'N/A')}, volume={getattr(data, 'volume', 'N/A')}")
        
        # 执行内置策略
        for strategy_name in strategies:
            try:
                if strategy_name == "量增价升":
                    volume_mult = self.config.get_user_param(user_id, "volume_mult", 1.5)
                    result = await self.builtin.volume_price_rise(data, volume_mult)
                    if result:
                        results.append(result)
                
                elif strategy_name == "缩量新高":
                    result = await self.builtin.low_volume_new_high(data)
                    if result:
                        results.append(result)
                
                elif strategy_name == "天量见顶":
                    result = await self.builtin.high_volume_top(data)
                    if result:
                        results.append(result)
                
                elif strategy_name == "5分钟交易量告警" or strategy_name == "volume_alert_5k":
                    volume_threshold = self.config.get_user_param(user_id, "volume_threshold_5k", 5000.0)
                    result = await self.builtin.volume_alert_5k(data, volume_threshold)
                    if result:
                        results.append(result)

                elif strategy_name == "外源性爆发二段告警":
                    # 该策略需要一段连续K线数据（建议为1分钟K线），优先使用原始K线列表
                    if raw_kline_list and len(raw_kline_list) >= 4:
                        result = await self.builtin.external_burst_phase2(raw_kline_list)
                        if result:
                            results.append(result)
                    else:
                        logger.info(
                            f"外源性爆发二段告警：可用K线数据不足，token={token}, "
                            f"raw_kline_list_len={len(raw_kline_list) if raw_kline_list else 0}"
                        )
                
                # TODO: 执行YAML策略
                
            except Exception as e:
                logger.error(f"策略执行失败 {strategy_name}: {e}")
        
        return results

