"""
5分钟连续监测任务管理器
在获得目标CA后，连续监测5分钟，每分钟返回一次K线数据
"""
import asyncio
from typing import Dict, Optional, Callable, Awaitable
from datetime import datetime, timedelta
from loguru import logger

from src.core.datasource import StandardKlineData, DataSourceAdapter, DataSourceMode


class MonitoringTask:
    """单个Token的监测任务"""
    
    def __init__(
        self,
        token: str,
        adapter: DataSourceAdapter,
        callback: Callable[[str, StandardKlineData, int], Awaitable[None]],  # token, data, minute
        alert_callback: Optional[Callable[[str, float], Awaitable[None]]] = None,  # token, total_volume
        duration_minutes: int = 5  # 监测时长（分钟）
    ):
        self.token = token
        self.adapter = adapter
        self.callback = callback  # 每分钟返回数据的回调
        self.alert_callback = alert_callback  # 5分钟累计交易量告警回调
        self.volume_threshold = 5000.0  # 5K USD阈值
        self.duration_minutes = duration_minutes  # 监测时长
        self.is_running = False
        self.minute_data: list[StandardKlineData] = []  # 存储每分钟的数据
        self.start_time: Optional[datetime] = None
        
    async def start(self):
        """启动5分钟监测任务"""
        if self.is_running:
            logger.warning(f"监测任务已在运行: {self.token}")
            return
        
        self.is_running = True
        self.start_time = datetime.now()
        self.minute_data = []
        
        logger.info(f"🚀 开始监测Token: {self.token}, 持续{self.duration_minutes}分钟")
        
        try:
            # 连续监测，每分钟获取一次数据
            for minute in range(1, self.duration_minutes + 1):  # 1到duration_minutes分钟
                if not self.is_running:
                    break
                
                # 等待到下一分钟（如果是第1分钟，立即获取）
                if minute > 1:
                    await asyncio.sleep(60)  # 等待60秒
                
                # 获取1分钟K线数据
                try:
                    data_list = await self.adapter.get_data(
                        token=self.token,
                        mode=DataSourceMode.KLINE,
                        intervals=["1m"]
                    )
                    
                    if data_list and isinstance(data_list, list) and len(data_list) > 0:
                        # 获取最新的1分钟K线数据
                        data_1m = data_list[0]
                        if isinstance(data_1m, StandardKlineData) and data_1m.interval == "1m":
                            self.minute_data.append(data_1m)
                            
                            # 调用回调函数，返回当前分钟的数据
                            logger.info(
                                f"📊 [{minute}/5] Token: {self.token}, "
                                f"1分钟交易量: ${data_1m.volume:,.2f}, "
                                f"价格: ${data_1m.close:.8f}"
                            )
                            
                            if self.callback:
                                await self.callback(self.token, data_1m, minute)
                            
                            # 立即检查累计交易量，如果超过阈值，立即触发告警并停止任务
                            total_volume = sum(data.volume for data in self.minute_data)
                            if total_volume > self.volume_threshold:
                                logger.warning(
                                    f"🔔 交易信号1触发（提前）: {self.token}, "
                                    f"累计交易量: ${total_volume:,.2f} > ${self.volume_threshold:,.2f}, "
                                    f"监测时长: {minute}分钟"
                                )
                                
                                # 立即触发告警
                                if self.alert_callback:
                                    await self.alert_callback(self.token, total_volume)
                                
                                # 停止监测任务
                                logger.info(f"⏹️  监测任务已停止（已触发信号）: {self.token}")
                                self.is_running = False
                                break  # 退出循环
                        else:
                            logger.warning(f"未获取到有效的1分钟K线数据: {self.token}, minute={minute}")
                    else:
                        logger.warning(f"未获取到数据: {self.token}, minute={minute}")
                        
                except Exception as e:
                    logger.error(f"获取K线数据失败: {self.token}, minute={minute}, error={e}")
            
            # 如果任务还在运行（没有提前触发信号），5分钟监测完成后检查累计交易量
            if self.is_running:
                await self._check_total_volume()
            
        except asyncio.CancelledError:
            logger.info(f"监测任务被取消: {self.token}")
        except Exception as e:
            logger.error(f"监测任务出错: {self.token}, error={e}")
        finally:
            self.is_running = False
            logger.info(f"✅ 监测任务完成: {self.token}")
    
    async def _check_total_volume(self):
        """检查5分钟累计交易量"""
        if not self.minute_data:
            logger.warning(f"没有监测数据: {self.token}")
            return
        
        # 计算5分钟累计交易量
        total_volume = sum(data.volume for data in self.minute_data)
        
        logger.info(
            f"📈 5分钟监测完成: {self.token}, "
            f"累计交易量: ${total_volume:,.2f}, "
            f"阈值: ${self.volume_threshold:,.2f}, "
            f"数据点数: {len(self.minute_data)}"
        )
        
        # 如果累计交易量超过阈值，触发告警
        if total_volume > self.volume_threshold:
            logger.warning(
                f"🔔 交易信号1触发: {self.token}, "
                f"5分钟累计交易量: ${total_volume:,.2f} > ${self.volume_threshold:,.2f}"
            )
            
            if self.alert_callback:
                await self.alert_callback(self.token, total_volume)
    
    def stop(self):
        """停止监测任务"""
        self.is_running = False
        logger.info(f"停止监测任务: {self.token}")


class MonitoringManager:
    """监测任务管理器 - 管理所有Token的监测任务"""
    
    def __init__(self):
        self.tasks: Dict[str, MonitoringTask] = {}  # token -> task
    
    async def start_monitoring(
        self,
        token: str,
        adapter: DataSourceAdapter,
        callback: Callable[[str, StandardKlineData, int], None],
        alert_callback: Optional[Callable[[str, float], None]] = None,
        duration_minutes: int = 5
    ):
        """
        启动Token的监测任务
        
        Args:
            token: Token地址或符号
            adapter: 数据源适配器
            callback: 每分钟数据回调 (token, data, minute)
            alert_callback: 告警回调 (token, total_volume)
            duration_minutes: 监测时长（分钟），默认5分钟
        """
        # 如果已有监测任务，先停止旧的
        if token in self.tasks:
            old_task = self.tasks[token]
            if old_task.is_running:
                old_task.stop()
        
        # 创建新任务
        task = MonitoringTask(token, adapter, callback, alert_callback, duration_minutes)
        self.tasks[token] = task
        
        # 异步启动任务（不阻塞）
        asyncio.create_task(task.start())
    
    def stop_monitoring(self, token: str):
        """停止指定Token的监测任务"""
        if token in self.tasks:
            self.tasks[token].stop()
            del self.tasks[token]
    
    def is_monitoring(self, token: str) -> bool:
        """检查Token是否正在监测"""
        return token in self.tasks and self.tasks[token].is_running
