"""
告警追踪器
用于记录告警历史、去重和统计
"""
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict
from dataclasses import dataclass
from loguru import logger


@dataclass
class AlertRecord:
    """告警记录"""
    token: str
    strategy_name: str
    timestamp: datetime
    signal_strength: int


class AlertTracker:
    """
    告警追踪器
    
    功能：
    1. 记录每个CA的告警历史
    2. 检查是否在10分钟内已告警过（去重）
    3. 统计近24小时的告警次数
    """
    
    def __init__(self, dedup_window_minutes: int = 10):
        """
        初始化告警追踪器
        
        Args:
            dedup_window_minutes: 去重时间窗口（分钟），默认10分钟
        """
        self.dedup_window_minutes = dedup_window_minutes
        # token -> List[AlertRecord]：记录每个token的所有告警
        self.alert_history: Dict[str, List[AlertRecord]] = defaultdict(list)
        # token -> last_alert_time：记录每个token最后一次告警时间（用于快速去重检查）
        self.last_alert_time: Dict[str, float] = {}
    
    def should_alert(self, token: str) -> Tuple[bool, float]:
        """
        检查是否应该发送告警（去重逻辑）
        
        Args:
            token: 代币地址或符号
            
        Returns:
            Tuple[bool, float]: (是否应该告警, 距离上次告警的秒数)
        """
        now = time.time()
        last_time = self.last_alert_time.get(token, 0)
        
        if last_time == 0:
            # 从未告警过，可以告警
            return True, 0.0
        
        time_diff = now - last_time
        window_seconds = self.dedup_window_minutes * 60
        
        if time_diff >= window_seconds:
            # 超过去重窗口，可以告警
            return True, time_diff
        else:
            # 在去重窗口内，不告警
            remaining = window_seconds - time_diff
            logger.debug(
                f"告警去重: token={token}, "
                f"上次告警={time_diff:.1f}秒前, "
                f"还需等待{remaining:.1f}秒"
            )
            return False, time_diff
    
    def record_alert(self, token: str, strategy_name: str, signal_strength: int):
        """
        记录一次告警
        
        Args:
            token: 代币地址或符号
            strategy_name: 策略名称
            signal_strength: 信号强度
        """
        now = datetime.now()
        record = AlertRecord(
            token=token,
            strategy_name=strategy_name,
            timestamp=now,
            signal_strength=signal_strength
        )
        
        self.alert_history[token].append(record)
        self.last_alert_time[token] = time.time()
        
        # 清理过期记录（只保留最近24小时的）
        self._cleanup_old_records(token)
    
    def get_24h_alert_count(self, token: str) -> int:
        """
        获取指定token近24小时的告警次数
        
        Args:
            token: 代币地址或符号
            
        Returns:
            int: 近24小时的告警次数
        """
        if token not in self.alert_history:
            return 0
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        records = self.alert_history[token]
        
        # 统计24小时内的告警次数
        count = sum(1 for record in records if record.timestamp >= cutoff_time)
        return count
    
    def _cleanup_old_records(self, token: str):
        """
        清理指定token的过期记录（超过24小时）
        
        Args:
            token: 代币地址或符号
        """
        if token not in self.alert_history:
            return
        
        cutoff_time = datetime.now() - timedelta(hours=24)
        records = self.alert_history[token]
        
        # 只保留24小时内的记录
        self.alert_history[token] = [
            record for record in records
            if record.timestamp >= cutoff_time
        ]
        
        # 如果清理后没有记录了，也清理last_alert_time（但保留，因为去重窗口可能还在）
        # 这里不清理last_alert_time，因为去重窗口可能还在生效
    
    def get_all_tokens_24h_stats(self) -> Dict[str, int]:
        """
        获取所有token的近24小时告警统计
        
        Returns:
            Dict[str, int]: token -> 告警次数
        """
        stats = {}
        for token in self.alert_history.keys():
            stats[token] = self.get_24h_alert_count(token)
        return stats


# 全局告警追踪器实例
_alert_tracker: AlertTracker = None


def get_alert_tracker() -> AlertTracker:
    """获取全局告警追踪器实例（单例模式）"""
    global _alert_tracker
    if _alert_tracker is None:
        _alert_tracker = AlertTracker(dedup_window_minutes=10)
        logger.info("初始化告警追踪器：去重窗口=10分钟")
    return _alert_tracker
