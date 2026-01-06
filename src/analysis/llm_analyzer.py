"""
LLM分析器（接口保留，暂不实现）
为后续扩展预留接口
"""
from typing import Optional, List
from dataclasses import dataclass
from loguru import logger

from src.analysis.message_buffer import MemeMessage, TokenSummary
from src.analysis.script_analyzer import AnalysisResult


@dataclass
class LLMResult:
    """LLM分析结果"""
    token: str
    pattern: Optional[str] = None
    insights: List[str] = None
    risk_level: str = "medium"  # low, medium, high
    opportunity_score: int = 50  # 0-100
    strategy_suggestions: dict = None
    
    def __post_init__(self):
        if self.insights is None:
            self.insights = []
        if self.strategy_suggestions is None:
            self.strategy_suggestions = {}


class LLMAnalyzer:
    """
    LLM分析器（接口保留）
    
    后续实现时，需要：
    1. 配置LLM提供商（OpenAI/Anthropic/Gemini等）
    2. 实现Prompt构建
    3. 实现API调用
    4. 实现结果解析
    """
    
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        enabled: bool = False
    ):
        """
        初始化LLM分析器
        
        Args:
            provider: LLM提供商
            model: 模型名称
            api_key: API密钥
            enabled: 是否启用（默认False，暂不实现）
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.enabled = enabled
        
        if enabled:
            logger.warning("LLM分析器暂未实现，请使用脚本分析器")
            self.enabled = False
    
    async def analyze(
        self,
        token: str,
        messages: List[MemeMessage],
        summary: Optional[TokenSummary] = None,
        script_result: Optional[AnalysisResult] = None
    ) -> Optional[LLMResult]:
        """
        使用LLM分析消息
        
        Args:
            token: Token符号
            messages: 消息列表
            summary: Token摘要
            script_result: 脚本分析结果（可选）
            
        Returns:
            Optional[LLMResult]: LLM分析结果，如果未启用则返回None
        """
        if not self.enabled:
            logger.debug("LLM分析器未启用，跳过分析")
            return None
        
        # TODO: 实现LLM分析
        # 1. 构建Prompt
        # 2. 调用LLM API
        # 3. 解析返回结果
        # 4. 返回LLMResult
        
        logger.warning("LLM分析功能暂未实现")
        return None
    
    def _build_prompt(
        self,
        token: str,
        messages: List[MemeMessage],
        summary: Optional[TokenSummary]
    ) -> str:
        """
        构建LLM Prompt
        
        TODO: 实现Prompt构建逻辑
        """
        # 后续实现
        return ""
    
    async def _call_llm_api(self, prompt: str) -> str:
        """
        调用LLM API
        
        TODO: 实现API调用逻辑
        """
        # 后续实现
        return ""
    
    def _parse_llm_response(self, response: str) -> LLMResult:
        """
        解析LLM响应
        
        TODO: 实现响应解析逻辑
        """
        # 后续实现
        return LLMResult(token="", insights=[])

