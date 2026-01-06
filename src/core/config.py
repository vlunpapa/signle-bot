"""
配置管理器
支持用户配置持久化（SQLite/JSON）
"""
import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
from loguru import logger

from src.core.datasource import DataSourceMode


class ConfigManager:
    """配置管理器 - 使用SQLite持久化"""
    
    def __init__(self, db_path: str = "data/config.db"):
        """
        初始化配置管理器
        
        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 用户配置表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_configs (
                user_id INTEGER PRIMARY KEY,
                datasource_mode TEXT NOT NULL DEFAULT 'kline',
                strategies TEXT,  -- JSON数组
                params TEXT,      -- JSON对象
                updated_at TEXT
            )
        """)
        
        # YAML策略缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS yaml_strategies (
                name TEXT PRIMARY KEY,
                config TEXT,  -- JSON对象
                updated_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"配置数据库初始化完成: {self.db_path}")
    
    def get_user_mode(self, user_id: int) -> DataSourceMode:
        """获取用户数据源模式"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT datasource_mode FROM user_configs WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return DataSourceMode(result[0])
        return DataSourceMode.KLINE  # 默认K线模式
    
    def set_user_mode(self, user_id: int, mode: DataSourceMode):
        """设置用户数据源模式"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_configs 
            (user_id, datasource_mode, updated_at)
            VALUES (?, ?, ?)
        """, (user_id, mode.value, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info(f"用户 {user_id} 数据源模式已设置为: {mode.value}")
    
    def get_user_strategies(self, user_id: int) -> List[str]:
        """获取用户启用的策略列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT strategies FROM user_configs WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            return json.loads(result[0])
        return []
    
    def add_user_strategy(self, user_id: int, strategy_name: str):
        """添加用户策略"""
        strategies = self.get_user_strategies(user_id)
        if strategy_name not in strategies:
            strategies.append(strategy_name)
            self._update_user_strategies(user_id, strategies)
    
    def remove_user_strategy(self, user_id: int, strategy_name: str):
        """移除用户策略"""
        strategies = self.get_user_strategies(user_id)
        if strategy_name in strategies:
            strategies.remove(strategy_name)
            self._update_user_strategies(user_id, strategies)
    
    def _update_user_strategies(self, user_id: int, strategies: List[str]):
        """更新用户策略列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_configs 
            (user_id, strategies, updated_at)
            VALUES (?, ?, ?)
        """, (user_id, json.dumps(strategies), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_user_param(self, user_id: int, param_name: str, default: Any = None) -> Any:
        """获取用户参数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT params FROM user_configs WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            params = json.loads(result[0])
            return params.get(param_name, default)
        return default
    
    def set_user_param(self, user_id: int, param_name: str, value: Any):
        """设置用户参数"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT params FROM user_configs WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        
        if result and result[0]:
            params = json.loads(result[0])
        else:
            params = {}
        
        params[param_name] = value
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_configs 
            (user_id, params, updated_at)
            VALUES (?, ?, ?)
        """, (user_id, json.dumps(params), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_yaml_strategies(self) -> List[str]:
        """获取所有YAML策略名称"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM yaml_strategies")
        results = cursor.fetchall()
        conn.close()
        
        return [row[0] for row in results]
    
    def load_yaml_strategy(self, name: str) -> Optional[Dict]:
        """加载YAML策略配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT config FROM yaml_strategies WHERE name = ?",
            (name,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return json.loads(result[0])
        return None
    
    def save_yaml_strategy(self, name: str, config: Dict):
        """保存YAML策略配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO yaml_strategies 
            (name, config, updated_at)
            VALUES (?, ?, ?)
        """, (name, json.dumps(config), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()

