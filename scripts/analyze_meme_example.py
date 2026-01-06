"""
自定义Meme分析脚本示例

使用方法：
1. 将此文件复制到 scripts/analyze_meme.py
2. 在配置中设置 script_path: "scripts/analyze_meme.py"
3. 自定义分析逻辑
"""
from typing import List, Optional
from src.analysis.message_buffer import MemeMessage, TokenSummary
from src.analysis.script_analyzer import AnalysisResult


def analyze(
    token: str,
    messages: List[MemeMessage],
    summary: Optional[TokenSummary] = None
) -> AnalysisResult:
    """
    分析函数
    
    Args:
        token: Token符号
        messages: 时间窗口内的消息列表
        summary: Token摘要（可选）
        
    Returns:
        AnalysisResult: 分析结果
    """
    # 提取数据
    smart_money_total = sum(
        m.smart_money_amount for m in messages
        if m.smart_money_amount is not None
    )
    
    mc_values = [m.mc for m in messages if m.mc is not None]
    alert_counts = [m.alert_count for m in messages if m.alert_count is not None]
    
    # 计算指标
    avg_mc = sum(mc_values) / len(mc_values) if mc_values else 0.0
    total_alerts = sum(alert_counts)
    max_mc = max(mc_values) if mc_values else 0.0
    min_mc = min(mc_values) if mc_values else 0.0
    
    metrics = {
        "smart_money_total": smart_money_total,
        "avg_mc": avg_mc,
        "total_alerts": total_alerts,
        "message_count": len(messages),
        "max_mc": max_mc,
        "min_mc": min_mc,
    }
    
    # 识别模式
    pattern = None
    insights = []
    confidence = 0.5
    strategy_suggestions = {}
    
    # 自定义模式识别逻辑
    if smart_money_total > 1000000 and total_alerts >= 3:
        pattern = "high_smart_money_with_alerts"
        insights.append(f"聪明钱大量买入({smart_money_total/10000:.1f}万)且多次告警({total_alerts}次)")
        confidence = 0.8
        strategy_suggestions = {
            "volume_threshold": smart_money_total * 0.8,
            "alert_threshold": total_alerts,
        }
    elif avg_mc > 0 and avg_mc < 1000000 and smart_money_total > 500000:
        pattern = "low_mc_high_smart_money"
        insights.append(f"低市值({avg_mc/10000:.1f}万)但聪明钱大量买入({smart_money_total/10000:.1f}万)")
        confidence = 0.75
        strategy_suggestions = {
            "mc_threshold": avg_mc * 2,
            "smart_money_threshold": smart_money_total * 0.7,
        }
    
    return AnalysisResult(
        token=token,
        pattern=pattern,
        metrics=metrics,
        confidence=confidence,
        insights=insights,
        strategy_suggestions=strategy_suggestions
    )

