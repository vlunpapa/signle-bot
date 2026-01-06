"""
分析层管理器
整合所有分析组件
"""
import asyncio
from typing import Optional
from loguru import logger

from src.analysis.message_buffer import MessageBuffer, MemeMessage, TokenSummary
from src.analysis.window_manager import WindowManager, AnalysisConfig
from src.analysis.script_analyzer import ScriptAnalyzer, AnalysisResult
from src.analysis.llm_analyzer import LLMAnalyzer, LLMResult
from src.analysis.strategy_generator import StrategyGenerator


class AnalysisManager:
    """分析层管理器"""
    
    def __init__(
        self,
        script_path: Optional[str] = None,
        config: Optional[AnalysisConfig] = None,
        auto_generate_strategy: bool = False,
        min_confidence: float = 0.7
    ):
        """
        初始化分析管理器
        
        Args:
            script_path: 自定义分析脚本路径
            config: 分析配置
            auto_generate_strategy: 是否自动生成策略
            min_confidence: 最低置信度阈值
        """
        self.buffer = MessageBuffer()
        self.config = config or AnalysisConfig()
        self.script_analyzer = ScriptAnalyzer(script_path)
        self.llm_analyzer = LLMAnalyzer(enabled=False)  # 暂不启用
        self.strategy_generator = StrategyGenerator()
        self.auto_generate_strategy = auto_generate_strategy
        self.min_confidence = min_confidence
        
        # 创建窗口管理器
        self.window_manager = WindowManager(
            message_buffer=self.buffer,
            config=self.config,
            analysis_callback=self._analysis_callback
        )
    
    async def start(self):
        """启动分析管理器"""
        await self.window_manager.start()
        logger.info("分析管理器已启动")
    
    async def stop(self):
        """停止分析管理器"""
        await self.window_manager.stop()
        logger.info("分析管理器已停止")
    
    async def add_message(self, message: MemeMessage):
        """
        添加消息到缓冲区
        
        Args:
            message: Meme消息对象
        """
        await self.buffer.add_message(message)
    
    async def _analysis_callback(self, token: str, messages: list[MemeMessage]):
        """
        分析回调函数
        
        Args:
            token: Token符号
            messages: 消息列表
        """
        try:
            # 获取Token摘要
            summary = await self.buffer.get_token_summary(
                token,
                self.config.window_size
            )
            
            # 执行脚本分析
            script_result = await self.script_analyzer.analyze(
                token=token,
                messages=messages,
                summary=summary
            )
            
            logger.info(
                f"脚本分析完成: token={token}, "
                f"模式={script_result.pattern}, "
                f"置信度={script_result.confidence:.2f}"
            )
            
            # LLM分析（暂不执行）
            llm_result = None
            # llm_result = await self.llm_analyzer.analyze(
            #     token=token,
            #     messages=messages,
            #     summary=summary,
            #     script_result=script_result
            # )
            
            # 生成策略
            if self.auto_generate_strategy:
                strategy_config = self.strategy_generator.generate_from_analysis(
                    analysis_result=script_result,
                    llm_result=llm_result,
                    auto_enable=False,
                    min_confidence=self.min_confidence
                )
                
                if strategy_config:
                    logger.info(f"策略生成成功: {strategy_config['name']}")
                else:
                    logger.debug(f"策略生成跳过: token={token}")
            
        except Exception as e:
            logger.error(f"分析回调执行失败: {e}", exc_info=True)
    
    async def trigger_analysis(self, token: str) -> Optional[AnalysisResult]:
        """
        手动触发分析
        
        Args:
            token: Token符号
            
        Returns:
            Optional[AnalysisResult]: 分析结果
        """
        messages = await self.window_manager.trigger_analysis(token)
        
        if not messages:
            return None
        
        summary = await self.buffer.get_token_summary(token, self.config.window_size)
        
        return await self.script_analyzer.analyze(
            token=token,
            messages=messages,
            summary=summary
        )
    
    async def get_summary(self, token: str) -> Optional[TokenSummary]:
        """获取Token摘要"""
        return await self.buffer.get_token_summary(token, self.config.window_size)

