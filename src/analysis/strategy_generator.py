"""
策略生成器
将分析结果转换为YAML策略并持久化
"""
import yaml
from pathlib import Path
from typing import Optional
from datetime import datetime
from loguru import logger

from src.analysis.script_analyzer import AnalysisResult
from src.analysis.llm_analyzer import LLMResult


class StrategyGenerator:
    """策略生成器"""
    
    def __init__(self, strategies_dir: str = "config/strategies/generated"):
        """
        初始化策略生成器
        
        Args:
            strategies_dir: 生成的策略保存目录
        """
        self.strategies_dir = Path(strategies_dir)
        self.strategies_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_from_analysis(
        self,
        analysis_result: AnalysisResult,
        llm_result: Optional[LLMResult] = None,
        auto_enable: bool = False,
        min_confidence: float = 0.7
    ) -> Optional[dict]:
        """
        从分析结果生成策略
        
        Args:
            analysis_result: 脚本分析结果
            llm_result: LLM分析结果（可选）
            auto_enable: 是否自动启用策略
            min_confidence: 最低置信度阈值
            
        Returns:
            Optional[dict]: 生成的策略配置，如果置信度不足则返回None
        """
        # 检查置信度
        if analysis_result.confidence < min_confidence:
            logger.info(
                f"策略生成跳过: token={analysis_result.token}, "
                f"置信度={analysis_result.confidence:.2f} < {min_confidence}"
            )
            return None
        
        # 如果没有识别到模式，不生成策略
        if not analysis_result.pattern:
            logger.info(f"策略生成跳过: token={analysis_result.token}, 未识别到模式")
            return None
        
        # 合并分析结果
        strategy_config = self._build_strategy_config(
            analysis_result,
            llm_result
        )
        
        # 验证策略
        if not self._validate_strategy(strategy_config):
            logger.warning(f"策略验证失败: {strategy_config.get('name')}")
            return None
        
        # 保存策略
        strategy_file = self._save_strategy(strategy_config)
        
        logger.info(
            f"策略生成成功: {strategy_config['name']}, "
            f"文件: {strategy_file}"
        )
        
        return strategy_config
    
    def _build_strategy_config(
        self,
        analysis_result: AnalysisResult,
        llm_result: Optional[LLMResult]
    ) -> dict:
        """构建策略配置"""
        token = analysis_result.token
        pattern = analysis_result.pattern
        
        # 生成策略名称
        strategy_name = f"{pattern}_{token}_{int(datetime.now().timestamp())}"
        
        # 基础配置
        strategy_config = {
            "name": strategy_name,
            "description": self._generate_description(analysis_result, llm_result),
            "mode": "kline",  # 默认K线模式
            "enabled": False,  # 默认不启用，需要手动启用
            "created_at": datetime.now().isoformat(),
            "source": "analysis_layer",
            "confidence": analysis_result.confidence,
        }
        
        # 构建条件
        conditions = []
        
        # 从分析结果提取条件
        if analysis_result.strategy_suggestions:
            suggestions = analysis_result.strategy_suggestions
            
            # 聪明钱阈值
            if "volume_threshold" in suggestions:
                conditions.append({
                    "field": "smart_money_buy",
                    "operator": ">",
                    "value": suggestions["volume_threshold"],
                    "description": f"聪明钱买入超过 {suggestions['volume_threshold']/10000:.1f}万 USDT"
                })
            
            # 市值阈值
            if "mc_threshold" in suggestions:
                conditions.append({
                    "field": "mc",
                    "operator": "<",
                    "value": suggestions["mc_threshold"],
                    "description": f"市值低于 {suggestions['mc_threshold']/10000:.1f}万 USDT"
                })
            
            # 告警阈值
            if "alert_threshold" in suggestions:
                conditions.append({
                    "field": "alert_count",
                    "operator": ">=",
                    "value": suggestions["alert_threshold"],
                    "description": f"告警次数 >= {suggestions['alert_threshold']}"
                })
            
            # 市值增长阈值
            if "mc_growth_threshold" in suggestions:
                conditions.append({
                    "field": "mc_growth",
                    "operator": ">",
                    "value": suggestions["mc_growth_threshold"],
                    "description": f"市值增长超过 {suggestions['mc_growth_threshold']*100:.1f}%"
                })
        
        # 如果没有条件，使用默认条件
        if not conditions:
            # 使用分析结果的指标作为条件
            metrics = analysis_result.metrics
            if metrics.get("smart_money_total", 0) > 0:
                conditions.append({
                    "field": "smart_money_buy",
                    "operator": ">",
                    "value": metrics["smart_money_total"] * 0.8,
                    "description": f"聪明钱买入超过 {metrics['smart_money_total']*0.8/10000:.1f}万 USDT"
                })
        
        strategy_config["conditions"] = conditions
        
        # 信号强度公式
        strategy_config["signal_strength"] = {
            "formula": "min(100, (smart_money_buy / 10000) * 10 + confidence * 50)"
        }
        
        # 消息模板
        strategy_config["message_template"] = self._generate_message_template(
            analysis_result,
            llm_result
        )
        
        return strategy_config
    
    def _generate_description(
        self,
        analysis_result: AnalysisResult,
        llm_result: Optional[LLMResult]
    ) -> str:
        """生成策略描述"""
        if llm_result and llm_result.insights:
            return llm_result.insights[0]
        elif analysis_result.insights:
            return analysis_result.insights[0]
        else:
            return f"基于{analysis_result.pattern}模式自动生成的策略"
    
    def _generate_message_template(
        self,
        analysis_result: AnalysisResult,
        llm_result: Optional[LLMResult]
    ) -> str:
        """生成消息模板"""
        template = f"""🔔 **{analysis_result.pattern}信号**

Token: {{{{ symbol }}}}
模式: {analysis_result.pattern}

"""
        
        if analysis_result.metrics.get("smart_money_total"):
            template += f"聪明钱买入: {{{{ smart_money_buy | format_number }}}} USDT\n"
        
        if analysis_result.metrics.get("avg_mc"):
            template += f"市值: {{{{ mc | format_number }}}} USDT\n"
        
        if analysis_result.metrics.get("total_alerts"):
            template += f"告警次数: {{{{ alert_count }}}}\n"
        
        template += f"\n置信度: {analysis_result.confidence*100:.0f}%"
        
        return template
    
    def _validate_strategy(self, strategy_config: dict) -> bool:
        """验证策略配置"""
        # 检查必需字段
        required_fields = ["name", "mode", "conditions"]
        for field in required_fields:
            if field not in strategy_config:
                logger.warning(f"策略缺少必需字段: {field}")
                return False
        
        # 检查条件
        if not strategy_config["conditions"]:
            logger.warning("策略没有条件")
            return False
        
        return True
    
    def _save_strategy(self, strategy_config: dict) -> Path:
        """保存策略到文件"""
        strategy_name = strategy_config["name"]
        filename = f"{strategy_name}.yaml"
        filepath = self.strategies_dir / filename
        
        # 保存为YAML
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(strategy_config, f, allow_unicode=True, default_flow_style=False)
        
        # 更新活跃策略列表
        self._update_active_strategies(strategy_name)
        
        return filepath
    
    def _update_active_strategies(self, strategy_name: str):
        """更新活跃策略列表"""
        active_file = self.strategies_dir / "active_strategies.yaml"
        
        if active_file.exists():
            with open(active_file, "r", encoding="utf-8") as f:
                active = yaml.safe_load(f) or {}
        else:
            active = {}
        
        if "strategies" not in active:
            active["strategies"] = []
        
        if strategy_name not in active["strategies"]:
            active["strategies"].append(strategy_name)
            active["updated_at"] = datetime.now().isoformat()
            
            with open(active_file, "w", encoding="utf-8") as f:
                yaml.dump(active, f, allow_unicode=True, default_flow_style=False)

