"""
工单派单系统 - 核心模块
与OpenClaw Discord机器人集成
"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TicketStatus(Enum):
    """工单状态"""
    PENDING = "pending"           # 待处理
    ASSIGNED = "assigned"         # 已分配
    IN_PROGRESS = "in_progress"   # 处理中
    COMPLETED = "completed"       # 已完成
    CLOSED = "closed"            # 已关闭
    CANCELLED = "cancelled"      # 已取消

class TicketPriority(Enum):
    """工单优先级"""
    LOW = 1      # 低
    NORMAL = 2   # 正常
    HIGH = 3     # 高
    URGENT = 4   # 紧急

class TicketType(Enum):
    """工单类型"""
    LEVEL_UP = "level_up"        # 球员升级
    BADGES = "badges"           # 徽章获取
    VC_FARM = "vc_farm"         # VC农场
    MYTEAM = "myteam"           # MyTeam服务
    PC_MOD = "pc_mod"           # PC修改器
    CONSOLE_MOD = "console_mod" # 主机修改器
    SUPPORT = "support"         # 技术支持
    OTHER = "other"            # 其他

class Ticket:
    """工单类"""
    def __init__(self, 
                 ticket_id: str,
                 customer_id: str,
                 customer_name: str,
                 ticket_type: TicketType,
                 title: str,
                 description: str,
                 priority: TicketPriority = TicketPriority.NORMAL,
                 status: TicketStatus = TicketStatus.PENDING,
                 assigned_to: Optional[str] = None,
                 created_at: Optional[datetime] = None,
                 updated_at: Optional[datetime] = None,
                 completed_at: Optional[datetime] = None,
                 metadata: Optional[Dict] = None):
        
        self.ticket_id = ticket_id
        self.customer_id = customer_id
        self.customer_name = customer_name
        self.ticket_type = ticket_type
        self.title = title
        self.description = description
        self.priority = priority
        self.status = status
        self.assigned_to = assigned_to
        self.created_at = created_at or datetime.now()
        self.updated_at = updated_at or datetime.now()
        self.completed_at = completed_at
        self.metadata = metadata or {}
        self.comments = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'ticket_id': self.ticket_id,
            'customer_id': self.customer_id,
            'customer_name': self.customer_name,
            'ticket_type': self.ticket_type.value,
            'title': self.title,
            'description': self.description,
            'priority': self.priority.value,
            'status': self.status.value,
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'metadata': self.metadata,
            'comments': self.comments
        }

class Worker:
    """工作人员/代练员类"""
    def __init__(self,
                 worker_id: str,
                 name: str,
                 skills: List[str],
                 max_tickets: int = 5,
                 current_tickets: int = 0,
                 rating: float = 5.0,
                 is_active: bool = True):
        
        self.worker_id = worker_id
        self.name = name
        self.skills = skills
        self.max_tickets = max_tickets
        self.current_tickets = current_tickets
        self.rating = rating
        self.is_active = is_active
        self.created_at = datetime.now()
    
    def can_take_more(self) -> bool:
        """是否可以接受更多工单"""
        return self.is_active and self.current_tickets < self.max_tickets
    
    def has_skill(self, ticket_type: TicketType) -> bool:
        """是否具备处理某类工单的技能"""
        return ticket_type.value in self.skills or 'all' in self.skills

class TicketDatabase:
    """工单数据库"""
    
    def __init__(self, db_path: str = "tickets.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 工单表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    ticket_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    assigned_to TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata TEXT
                )
            ''')
            
            # 工作人员表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    skills TEXT NOT NULL,
                    max_tickets INTEGER DEFAULT 5,
                    current_tickets INTEGER DEFAULT 0,
                    rating REAL DEFAULT 5.0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # 评论表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    comment_id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets (ticket_id)
                )
            ''')
            
            conn.commit()
    
    def save_ticket(self, ticket: Ticket):
        """保存工单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO tickets 
                (ticket_id, customer_id, customer_name, ticket_type, title, description,
                 priority, status, assigned_to, created_at, updated_at, completed_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticket.ticket_id,
                ticket.customer_id,
                ticket.customer_name,
                ticket.ticket_type.value,
                ticket.title,
                ticket.description,
                ticket.priority.value,
                ticket.status.value,
                ticket.assigned_to,
                ticket.created_at.isoformat(),
                ticket.updated_at.isoformat(),
                ticket.completed_at.isoformat() if ticket.completed_at else None,
                json.dumps(ticket.metadata)
            ))
            
            conn.commit()
    
    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """获取工单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM tickets WHERE ticket_id = ?', (ticket_id,))
            row = cursor.fetchone()
            
            if row:
                return self._row_to_ticket(row)
            return None
    
    def get_tickets_by_status(self, status: TicketStatus) -> List[Ticket]:
        """根据状态获取工单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM tickets 
                WHERE status = ? 
                ORDER BY priority DESC, created_at ASC
            ''', (status.value,))
            
            rows = cursor.fetchall()
            return [self._row_to_ticket(row) for row in rows]
    
    def get_tickets_by_customer(self, customer_id: str) -> List[Ticket]:
        """获取客户的所有工单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM tickets 
                WHERE customer_id = ? 
                ORDER BY created_at DESC
            ''', (customer_id,))
            
            rows = cursor.fetchall()
            return [self._row_to_ticket(row) for row in rows]
    
    def get_all_tickets(self) -> List[Ticket]:
        """获取所有工单"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM tickets ORDER BY created_at DESC')
            rows = cursor.fetchall()
            return [self._row_to_ticket(row) for row in rows]
    
    def _row_to_ticket(self, row) -> Ticket:
        """将数据库行转换为Ticket对象"""
        return Ticket(
            ticket_id=row[0],
            customer_id=row[1],
            customer_name=row[2],
            ticket_type=TicketType(row[3]),
            title=row[4],
            description=row[5],
            priority=TicketPriority(row[6]),
            status=TicketStatus(row[7]),
            assigned_to=row[8],
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
            completed_at=datetime.fromisoformat(row[11]) if row[11] else None,
            metadata=json.loads(row[12]) if row[12] else {}
        )
    
    def save_worker(self, worker: Worker):
        """保存工作人员"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO workers 
                (worker_id, name, skills, max_tickets, current_tickets, rating, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                worker.worker_id,
                worker.name,
                json.dumps(worker.skills),
                worker.max_tickets,
                worker.current_tickets,
                worker.rating,
                1 if worker.is_active else 0,
                worker.created_at.isoformat()
            ))
            
            conn.commit()
    
    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """获取工作人员"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM workers WHERE worker_id = ?', (worker_id,))
            row = cursor.fetchone()
            
            if row:
                return Worker(
                    worker_id=row[0],
                    name=row[1],
                    skills=json.loads(row[2]),
                    max_tickets=row[3],
                    current_tickets=row[4],
                    rating=row[5],
                    is_active=bool(row[6])
                )
            return None
    
    def get_all_workers(self) -> List[Worker]:
        """获取所有工作人员"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM workers WHERE is_active = 1')
            rows = cursor.fetchall()
            
            return [Worker(
                worker_id=row[0],
                name=row[1],
                skills=json.loads(row[2]),
                max_tickets=row[3],
                current_tickets=row[4],
                rating=row[5],
                is_active=bool(row[6])
            ) for row in rows]

class TicketDispatcher:
    """工单派单器"""
    
    def __init__(self, db: TicketDatabase):
        self.db = db
    
    def create_ticket(self, 
                     customer_id: str,
                     customer_name: str,
                     ticket_type: TicketType,
                     title: str,
                     description: str,
                     priority: TicketPriority = TicketPriority.NORMAL,
                     metadata: Optional[Dict] = None) -> Ticket:
        """创建新工单"""
        
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        
        ticket = Ticket(
            ticket_id=ticket_id,
            customer_id=customer_id,
            customer_name=customer_name,
            ticket_type=ticket_type,
            title=title,
            description=description,
            priority=priority,
            status=TicketStatus.PENDING,
            metadata=metadata
        )
        
        self.db.save_ticket(ticket)
        logger.info(f"创建工单: {ticket_id}")
        
        return ticket
    
    def assign_ticket(self, ticket_id: str, worker_id: str) -> bool:
        """分配工单给工作人员"""
        ticket = self.db.get_ticket(ticket_id)
        worker = self.db.get_worker(worker_id)
        
        if not ticket or not worker:
            return False
        
        if not worker.can_take_more():
            logger.warning(f"工作人员 {worker.name} 无法接受更多工单")
            return False
        
        # 更新工单
        ticket.status = TicketStatus.ASSIGNED
        ticket.assigned_to = worker_id
        ticket.updated_at = datetime.now()
        self.db.save_ticket(ticket)
        
        # 更新工作人员
        worker.current_tickets += 1
        self.db.save_worker(worker)
        
        logger.info(f"工单 {ticket_id} 分配给 {worker.name}")
        return True
    
    def auto_assign(self, ticket_id: str) -> Optional[str]:
        """自动分配工单"""
        ticket = self.db.get_ticket(ticket_id)
        if not ticket:
            return None
        
        # 获取所有可用工作人员
        workers = self.db.get_all_workers()
        available_workers = [
            w for w in workers 
            if w.can_take_more() and w.has_skill(ticket.ticket_type)
        ]
        
        if not available_workers:
            logger.warning(f"没有可用工作人员处理工单 {ticket_id}")
            return None
        
        # 选择最合适的工作人员（当前工单最少且评分最高）
        best_worker = min(available_workers, 
                         key=lambda w: (w.current_tickets, -w.rating))
        
        if self.assign_ticket(ticket_id, best_worker.worker_id):
            return best_worker.name
        
        return None
    
    def complete_ticket(self, ticket_id: str, notes: Optional[str] = None) -> bool:
        """完成工单"""
        ticket = self.db.get_ticket(ticket_id)
        if not ticket:
            return False
        
        # 更新工单状态
        ticket.status = TicketStatus.COMPLETED
        ticket.completed_at = datetime.now()
        ticket.updated_at = datetime.now()
        
        if notes:
            ticket.metadata['completion_notes'] = notes
        
        self.db.save_ticket(ticket)
        
        # 释放工作人员
        if ticket.assigned_to:
            worker = self.db.get_worker(ticket.assigned_to)
            if worker:
                worker.current_tickets = max(0, worker.current_tickets - 1)
                self.db.save_worker(worker)
        
        logger.info(f"工单 {ticket_id} 已完成")
        return True
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        pending = self.db.get_tickets_by_status(TicketStatus.PENDING)
        in_progress = self.db.get_tickets_by_status(TicketStatus.IN_PROGRESS)
        workers = self.db.get_all_workers()
        
        return {
            'pending_count': len(pending),
            'in_progress_count': len(in_progress),
            'available_workers': len([w for w in workers if w.can_take_more()]),
            'total_workers': len(workers),
            'high_priority_pending': len([t for t in pending if t.priority in [TicketPriority.HIGH, TicketPriority.URGENT]])
        }

# 全局实例
ticket_db = None
ticket_dispatcher = None

def get_ticket_dispatcher() -> TicketDispatcher:
    """获取工单派单器实例"""
    global ticket_db, ticket_dispatcher
    
    if ticket_dispatcher is None:
        ticket_db = TicketDatabase()
        ticket_dispatcher = TicketDispatcher(ticket_db)
    
    return ticket_dispatcher