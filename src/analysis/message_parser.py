"""
Meme消息解析器
解析Telegram群组中的Meme币推送消息
"""
import re
from typing import Optional
from datetime import datetime
from loguru import logger

from src.analysis.message_buffer import MemeMessage


class MemeMessageParser:
    """解析Meme币推送消息"""
    
    # 正则表达式模式
    PATTERNS = {
        "smart_money": [
            r"聪明钱.*?买入.*?(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"smart\s*money.*?buy.*?(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"whale.*?buy.*?(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"大户.*?买入.*?(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
        ],
        "mc": [
            r"MC[：:]\s*(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"市值[：:]\s*(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"market\s*cap[：:]\s*(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
            r"MC\s*=\s*(\d+(?:\.\d+)?)\s*(?:万|k|K|m|M)?",
        ],
        "alert": [
            r"告警\s*x?(\d+)",
            r"alert\s*x?(\d+)",
            r"警告\s*x?(\d+)",
            r"alerts?\s*x?(\d+)",
        ]
    }
    
    @classmethod
    def _normalize_number(cls, value_str: str, unit: str = None) -> float:
        """
        标准化数字（处理万、k、M等单位）
        
        Args:
            value_str: 数字字符串
            unit: 单位（万、k、K、m、M）
            
        Returns:
            float: 标准化后的数字
        """
        try:
            value = float(value_str)
            
            if unit:
                unit = unit.lower()
                if unit in ['万', 'w']:
                    value *= 10000
                elif unit == 'k':
                    value *= 1000
                elif unit in ['m', '百万']:
                    value *= 1000000
                elif unit in ['b', '十亿']:
                    value *= 1000000000
            
            return value
        except ValueError:
            return 0.0
    
    @classmethod
    def parse(cls, text: str, token: str) -> Optional[MemeMessage]:
        """
        解析消息
        
        Args:
            text: 原始消息文本
            token: Token符号
            
        Returns:
            Optional[MemeMessage]: 解析后的消息对象，失败返回None
        """
        text = text.strip()
        if not text:
            return None
        
        message_type = "other"
        smart_money_amount = None
        mc = None
        alert_count = None
        content = {}
        
        # 解析聪明钱买入
        for pattern in cls.PATTERNS["smart_money"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                # 尝试提取单位
                unit_match = re.search(r"(\d+(?:\.\d+)?)\s*(万|k|K|m|M|w|W)", text, re.IGNORECASE)
                unit = unit_match.group(2) if unit_match else None
                
                smart_money_amount = cls._normalize_number(value_str, unit)
                message_type = "smart_money"
                content["smart_money"] = smart_money_amount
                break
        
        # 解析市值
        for pattern in cls.PATTERNS["mc"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value_str = match.group(1)
                # 尝试提取单位
                unit_match = re.search(r"(\d+(?:\.\d+)?)\s*(万|k|K|m|M|w|W)", text, re.IGNORECASE)
                unit = unit_match.group(2) if unit_match else None
                
                mc = cls._normalize_number(value_str, unit)
                if message_type == "other":
                    message_type = "mc"
                content["mc"] = mc
                break
        
        # 解析告警
        for pattern in cls.PATTERNS["alert"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                alert_count = int(match.group(1))
                if message_type == "other":
                    message_type = "alert"
                content["alert_count"] = alert_count
                break
        
        # 如果没有解析到任何结构化数据，返回None
        if message_type == "other" and not content:
            return None
        
        return MemeMessage(
            token=token.upper(),
            message_type=message_type,
            content=content,
            timestamp=datetime.now(),
            raw_text=text,
            smart_money_amount=smart_money_amount,
            mc=mc,
            alert_count=alert_count
        )
    
    @classmethod
    def parse_batch(cls, texts: list[str], token: str) -> list[MemeMessage]:
        """
        批量解析消息
        
        Args:
            texts: 消息文本列表
            token: Token符号
            
        Returns:
            list[MemeMessage]: 解析后的消息列表
        """
        messages = []
        for text in texts:
            msg = cls.parse(text, token)
            if msg:
                messages.append(msg)
        return messages

