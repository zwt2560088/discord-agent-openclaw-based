"""
订单管理系统
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import sqlite3
import logging
from dataclasses import dataclass, asdict
import heapq

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderStatus(Enum):
    """订单状态枚举"""
    PENDING = "pending"           # 待支付
    PAID = "paid"                # 已支付
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"      # 已完成
    DELIVERED = "delivered"      # 已交付
    CANCELLED = "cancelled"      # 已取消

class ServiceType(Enum):
    """服务类型枚举"""
    LEVEL_UP = "level_up"        # 球员升级
    BADGES = "badges"           # 徽章获取
    VC_FARM = "vc_farm"         # VC农场
    MYTEAM = "myteam"           # MyTeam服务
    PC_MOD = "pc_mod"           # PC修改器
    CONSOLE_MOD = "console_mod" # 主机修改器

class Platform(Enum):
    """销售平台枚举"""
    DISCORD = "discord"
    G2G = "g2g"
    U7BUY = "u7buy"

@dataclass
class Order:
    """订单数据类"""
    id: str
    customer_id: str
    service_type: ServiceType
    details: Dict[str, Any]
    amount: float
    status: OrderStatus
    platform: Platform
    created_at: datetime
    updated_at: datetime
    assigned_to: Optional[str] = None
    estimated_completion: Optional[datetime] = None
    actual_completion: Optional[datetime] = None
    priority_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """从字典创建订单"""
        # 转换枚举类型
        data['service_type'] = ServiceType(data['service_type'])
        data['status'] = OrderStatus(data['status'])
        data['platform'] = Platform(data['platform'])
        
        # 转换时间字符串
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        if data.get('estimated_completion'):
            data['estimated_completion'] = datetime.fromisoformat(data['estimated_completion'])
        if data.get('actual_completion'):
            data['actual_completion'] = datetime.fromisoformat(data['actual_completion'])
        
        return cls(**data)

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建订单表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    service_type TEXT NOT NULL,
                    details TEXT NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    assigned_to TEXT,
                    estimated_completion TEXT,
                    actual_completion TEXT,
                    priority_score REAL DEFAULT 0.0
                )
            ''')
            
            # 创建客户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY,
                    discord_id TEXT,
                    username TEXT,
                    email TEXT,
                    level INTEGER DEFAULT 1,
                    total_spent REAL DEFAULT 0.0,
                    order_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_order_at TEXT
                )
            ''')
            
            # 创建代练员表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    skills TEXT NOT NULL,
                    current_orders INTEGER DEFAULT 0,
                    max_orders INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'available',
                    rating REAL DEFAULT 5.0,
                    created_at TEXT NOT NULL
                )
            ''')
            
            conn.commit()
    
    def save_order(self, order: Order):
        """保存订单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO orders 
                (id, customer_id, service_type, details, amount, status, platform, 
                 created_at, updated_at, assigned_to, estimated_completion, 
                 actual_completion, priority_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order.id,
                order.customer_id,
                order.service_type.value,
                json.dumps(order.details),
                order.amount,
                order.status.value,
                order.platform.value,
                order.created_at.isoformat(),
                order.updated_at.isoformat(),
                order.assigned_to,
                order.estimated_completion.isoformat() if order.estimated_completion else None,
                order.actual_completion.isoformat() if order.actual_completion else None,
                order.priority_score
            ))
            
            conn.commit()
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                data['details'] = json.loads(data['details'])
                return Order.from_dict(data)
            
            return None
    
    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        """获取客户的所有订单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC', (customer_id,))
            rows = cursor.fetchall()
            
            orders = []
            for row in rows:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                data['details'] = json.loads(data['details'])
                orders.append(Order.from_dict(data))
            
            return orders
    
    def get_orders_by_status(self, status: OrderStatus) -> List[Order]:
        """根据状态获取订单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM orders WHERE status = ? ORDER BY priority_score DESC', (status.value,))
            rows = cursor.fetchall()
            
            orders = []
            for row in rows:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                data['details'] = json.loads(data['details'])
                orders.append(Order.from_dict(data))
            
            return orders
    
    def save_customer(self, customer_data: Dict[str, Any]):
        """保存客户信息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO customers 
                (id, discord_id, username, email, level, total_spent, order_count, 
                 created_at, last_order_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                customer_data['id'],
                customer_data.get('discord_id'),
                customer_data.get('username'),
                customer_data.get('email'),
                customer_data.get('level', 1),
                customer_data.get('total_spent', 0.0),
                customer_data.get('order_count', 0),
                customer_data.get('created_at', datetime.now().isoformat()),
                customer_data.get('last_order_at')
            ))
            
            conn.commit()

class OrderScheduler:
    """订单调度器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.order_queue = []
    
    def calculate_priority(self, order: Order) -> float:
        """计算订单优先级"""
        priority = 0.0
        
        # 紧急程度权重 (40%)
        if order.details.get('urgent', False):
            priority += 40
        
        # 支付金额权重 (30%)
        max_amount = 1000  # 假设最大金额
        priority += (order.amount / max_amount) * 30
        
        # 等待时间权重 (20%)
        wait_time = (datetime.now() - order.created_at).total_seconds() / 3600
        max_wait = 24  # 最大等待时间（小时）
        priority += min(wait_time / max_wait * 20, 20)
        
        # 客户等级权重 (10%)
        customer_level = self.get_customer_level(order.customer_id)
        priority += customer_level * 10
        
        return priority
    
    def get_customer_level(self, customer_id: str) -> int:
        """获取客户等级"""
        # 这里可以从数据库获取客户等级
        # 简化实现，返回默认等级
        return 1
    
    def add_order(self, order: Order):
        """添加订单到队列"""
        order.priority_score = self.calculate_priority(order)
        heapq.heappush(self.order_queue, (-order.priority_score, order))
        
        # 保存到数据库
        self.db_manager.save_order(order)
    
    def get_next_order(self) -> Optional[Order]:
        """获取下一个订单"""
        if self.order_queue:
            _, order = heapq.heappop(self.order_queue)
            return order
        return None
    
    def assign_orders(self, available_workers: List[str]):
        """分配订单给代练员"""
        while self.order_queue and available_workers:
            order = self.get_next_order()
            if order:
                worker = available_workers.pop(0)
                order.assigned_to = worker
                order.status = OrderStatus.IN_PROGRESS
                order.estimated_completion = datetime.now() + timedelta(hours=self.estimate_completion_time(order))
                
                # 更新数据库
                self.db_manager.save_order(order)

class OrderManager:
    """订单管理器"""
    
    def __init__(self):
        from src.config import config
        self.db_manager = DatabaseManager(config.DATABASE_URL)
        self.scheduler = OrderScheduler(self.db_manager)
        
        # 初始化代练员
        self.init_workers()
    
    def init_workers(self):
        """初始化代练员"""
        # 这里可以添加默认代练员
        pass
    
    def create_order(self, customer_id: str, service_type: ServiceType, 
                    details: Dict[str, Any], platform: Platform) -> Order:
        """创建新订单"""
        # 生成订单ID
        order_id = str(uuid.uuid4())
        
        # 计算价格
        amount = self.calculate_price(service_type, details)
        
        # 创建订单
        order = Order(
            id=order_id,
            customer_id=customer_id,
            service_type=service_type,
            details=details,
            amount=amount,
            status=OrderStatus.PENDING,
            platform=platform,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # 添加到调度队列
        self.scheduler.add_order(order)
        
        logger.info(f"Created order {order_id} for customer {customer_id}")
        
        return order
    
    def calculate_price(self, service_type: ServiceType, details: Dict[str, Any]) -> float:
        """计算订单价格"""
        # 基础价格表
        base_prices = {
            ServiceType.LEVEL_UP: {
                '1-70': 80,
                '71-85': 120,
                '86-95': 200,
                '96-99': 350
            },
            ServiceType.BADGES: {
                'single': 20,
                'pack_10': 150,
                'pack_30': 400
            },
            ServiceType.VC_FARM: {
                '100k': 50,
                '500k': 200,
                '1m': 350,
                '5m': 1500
            },
            ServiceType.PC_MOD: {
                'basic': 99,
                'pro': 199,
                'lifetime': 399
            },
            ServiceType.CONSOLE_MOD: {
                'ps': 299,
                'xbox': 299,
                'switch': 399,
                'all': 699
            }
        }
        
        # 获取基础价格
        if service_type in base_prices:
            service_prices = base_prices[service_type]
            
            # 根据详细信息确定价格
            if service_type == ServiceType.LEVEL_UP:
                level_range = details.get('level_range', '1-70')
                return service_prices.get(level_range, 80)
            
            elif service_type == ServiceType.BADGES:
                badge_type = details.get('badge_type', 'single')
                return service_prices.get(badge_type, 20)
            
            elif service_type == ServiceType.VC_FARM:
                vc_amount = details.get('vc_amount', '100k')
                return service_prices.get(vc_amount, 50)
            
            elif service_type == ServiceType.PC_MOD:
                mod_version = details.get('mod_version', 'basic')
                return service_prices.get(mod_version, 99)
            
            elif service_type == ServiceType.CONSOLE_MOD:
                platform = details.get('platform', 'ps')
                return service_prices.get(platform, 299)
        
        # 默认价格
        return 100
    
    def estimate_completion_time(self, order: Order) -> int:
        """预估完成时间（小时）"""
        # 基础完成时间
        base_times = {
            ServiceType.LEVEL_UP: 4,
            ServiceType.BADGES: 2,
            ServiceType.VC_FARM: 2,
            ServiceType.MYTEAM: 3,
            ServiceType.PC_MOD: 1,
            ServiceType.CONSOLE_MOD: 1
        }
        
        return base_times.get(order.service_type, 2)
    
    def get_order_status(self, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单状态"""
        order = self.db_manager.get_order(order_id)
        if order:
            return {
                'order_id': order.id,
                'status': order.status.value,
                'service_type': order.service_type.value,
                'amount': order.amount,
                'created_at': order.created_at.isoformat(),
                'estimated_completion': order.estimated_completion.isoformat() if order.estimated_completion else None,
                'assigned_to': order.assigned_to
            }
        return None
    
    def update_order_status(self, order_id: str, status: OrderStatus):
        """更新订单状态"""
        order = self.db_manager.get_order(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.now()
            
            if status == OrderStatus.COMPLETED:
                order.actual_completion = datetime.now()
            
            self.db_manager.save_order(order)
            logger.info(f"Updated order {order_id} status to {status.value}")
    
    def get_pending_orders(self) -> List[Order]:
        """获取待处理订单"""
        return self.db_manager.get_orders_by_status(OrderStatus.PAID)
    
    def get_in_progress_orders(self) -> List[Order]:
        """获取进行中订单"""
        return self.db_manager.get_orders_by_status(OrderStatus.IN_PROGRESS)
    
    def process_pending_orders(self):
        """处理待处理订单"""
        pending_orders = self.get_pending_orders()
        
        # 按优先级排序
        pending_orders.sort(key=lambda x: x.priority_score, reverse=True)
        
        # 分配订单
        for order in pending_orders:
            if order.status == OrderStatus.PAID:
                order.status = OrderStatus.IN_PROGRESS
                order.estimated_completion = datetime.now() + timedelta(hours=self.estimate_completion_time(order))
                self.db_manager.save_order(order)
                
                logger.info(f"Started processing order {order.id}")

# 全局订单管理器实例
order_manager = None

def get_order_manager() -> OrderManager:
    """获取订单管理器实例"""
    global order_manager
    
    if order_manager is None:
        order_manager = OrderManager()
    
    return order_manager