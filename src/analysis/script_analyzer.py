"""
脚本分析器
执行Python脚本进行规则化分析
"""
import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from src.analysis.message_buffer import MemeMessage, TokenSummary


@dataclass
class AnalysisResult:
    """分析结果"""
    token: str
    pattern: Optional[str] = None  # 识别的模式名称
    metrics: Dict[str, Any] = None  # 计算的指标
    confidence: float = 0.0  # 置信度 0-1
    insights: list[str] = None  # 洞察列表
    strategy_suggestions: Dict[str, Any] = None  # 策略建议
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
        if self.insights is None:
            self.insights = []
        if self.strategy_suggestions is None:
            self.strategy_suggestions = {}


class ScriptAnalyzer:
    """脚本分析器"""
    
    def __init__(self, script_path: Optional[str] = None):
        """
        初始化脚本分析器
        
        Args:
            script_path: 分析脚本路径，如果为None则使用默认分析逻辑
        """
        self.script_path = script_path
        self.analyze_func = None
        
        if script_path:
            self._load_script(script_path)
    
    def _load_script(self, script_path: str):
        """加载分析脚本"""
        try:
            path = Path(script_path)
            if not path.exists():
                logger.warning(f"分析脚本不存在: {script_path}，使用默认分析")
                return
            
            spec = importlib.util.spec_from_file_location("analyze_script", path)
            module = importlib.util.module_from_spec(spec)
            sys.modules["analyze_script"] = module
            spec.loader.exec_module(module)
            
            # 获取分析函数
            if hasattr(module, "analyze"):
                self.analyze_func = module.analyze
                logger.info(f"分析脚本加载成功: {script_path}")
            else:
                logger.warning(f"分析脚本缺少analyze函数: {script_path}")
                
        except Exception as e:
            logger.error(f"加载分析脚本失败: {e}")
    
    async def analyze(
        self,
        token: str,
        messages: list[MemeMessage],
        summary: Optional[TokenSummary] = None
    ) -> AnalysisResult:
        """
        分析消息
        
        Args:
            token: Token符号
            messages: 消息列表
            summary: Token摘要（可选）
            
        Returns:
            AnalysisResult: 分析结果
        """
        if self.analyze_func:
            # 使用自定义脚本
            try:
                result = await self._run_custom_script(token, messages, summary)
                return result
            except Exception as e:
                logger.error(f"自定义脚本执行失败: {e}，使用默认分析")
        
        # 使用默认分析逻辑
        return self._default_analyze(token, messages, summary)
    
    async def _run_custom_script(
        self,
        token: str,
        messages: list[MemeMessage],
        summary: Optional[TokenSummary]
    ) -> AnalysisResult:
        """运行自定义脚本"""
        if asyncio.iscoroutinefunction(self.analyze_func):
            result = await self.analyze_func(token, messages, summary)
        else:
            result = self.analyze_func(token, messages, summary)
        
        # 确保返回AnalysisResult对象
        if isinstance(result, dict):
            return AnalysisResult(token=token, **result)
        elif isinstance(result, AnalysisResult):
            return result
        else:
            raise ValueError(f"分析函数返回类型错误: {type(result)}")
    
    def _default_analyze(
        self,
        token: str,
        messages: list[MemeMessage],
        summary: Optional[TokenSummary]
    ) -> AnalysisResult:
        """默认分析逻辑"""
        if summary is None:
            # 计算摘要
            smart_money_total = sum(
                m.smart_money_amount for m in messages
                if m.smart_money_amount is not None
            )
            mc_values = [m.mc for m in messages if m.mc is not None]
            alert_counts = [m.alert_count for m in messages if m.alert_count is not None]
            
            avg_mc = sum(mc_values) / len(mc_values) if mc_values else 0.0
            total_alerts = sum(alert_counts)
        else:
            smart_money_total = summary.smart_money_total
            avg_mc = summary.avg_mc
            total_alerts = summary.total_alerts
        
        # 计算指标
        metrics = {
            "smart_money_total": smart_money_total,
            "avg_mc": avg_mc,
            "total_alerts": total_alerts,
            "message_count": len(messages),
            "max_mc": max([m.mc for m in messages if m.mc], default=0.0),
            "min_mc": min([m.mc for m in messages if m.mc], default=0.0),
        }
        
        # 识别模式
        pattern = None
        insights = []
        confidence = 0.5
        strategy_suggestions = {}
        
        # 模式1: 高聪明钱 + 多次告警
        if smart_money_total > 1000000 and total_alerts >= 3:
            pattern = "high_smart_money_with_alerts"
            insights.append(f"聪明钱大量买入({smart_money_total/10000:.1f}万)且多次告警({total_alerts}次)")
            confidence = 0.8
            strategy_suggestions = {
                "volume_threshold": smart_money_total * 0.8,
                "alert_threshold": total_alerts,
                "conditions": [
                    "smart_money_buy > volume_threshold",
                    "alert_count >= alert_threshold"
                ]
            }
        
        # 模式2: 低市值 + 高聪明钱
        elif avg_mc > 0 and avg_mc < 1000000 and smart_money_total > 500000:
            pattern = "low_mc_high_smart_money"
            insights.append(f"低市值({avg_mc/10000:.1f}万)但聪明钱大量买入({smart_money_total/10000:.1f}万)")
            confidence = 0.75
            strategy_suggestions = {
                "mc_threshold": avg_mc * 2,
                "smart_money_threshold": smart_money_total * 0.7,
                "conditions": [
                    "mc < mc_threshold",
                    "smart_money_buy > smart_money_threshold"
                ]
            }
        
        # 模式3: 市值快速增长
        elif metrics["max_mc"] > 0 and metrics["min_mc"] > 0:
            mc_growth = (metrics["max_mc"] - metrics["min_mc"]) / metrics["min_mc"]
            if mc_growth > 0.5:  # 增长超过50%
                pattern = "rapid_mc_growth"
                insights.append(f"市值快速增长({mc_growth*100:.1f}%)")
                confidence = 0.7
                strategy_suggestions = {
                    "mc_growth_threshold": mc_growth * 0.8,
                    "conditions": [
                        "mc_growth > mc_growth_threshold"
                    ]
                }
        
        # 模式4: 高聪明钱但低市值
        elif smart_money_total > avg_mc * 0.5 and avg_mc > 0:
            pattern = "high_smart_money_ratio"
            insights.append(f"聪明钱买入占比高({smart_money_total/avg_mc*100:.1f}%)")
            confidence = 0.65
        
        if not insights:
            insights.append("未识别到明显模式")
            confidence = 0.3
        
        return AnalysisResult(
            token=token,
            pattern=pattern,
            metrics=metrics,
            confidence=confidence,
            insights=insights,
            strategy_suggestions=strategy_suggestions
        )

