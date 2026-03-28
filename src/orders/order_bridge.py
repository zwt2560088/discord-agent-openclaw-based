"""
Order Communication Bridge
Anonymous Chinese-English translation bridge for customer-worker communication
"""
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class OrderStatus(Enum):
    """Order status"""
    PENDING = "pending"              # Awaiting payment
    PAID = "paid"                    # Paid, awaiting assignment
    ASSIGNED = "assigned"            # Assigned to worker
    IN_PROGRESS = "in_progress"      # Worker is processing
    COMPLETED = "completed"          # Completed
    DELIVERED = "delivered"          # Delivered to customer
    AFTER_SALES = "after_sales"      # After-sales issue
    CANCELLED = "cancelled"          # Cancelled


class MessageType(Enum):
    """Message type"""
    CUSTOMER = "customer"    # From customer (English)
    WORKER = "worker"        # From worker (Chinese)
    SYSTEM = "system"        # System message
    ADMIN = "admin"          # Admin message


@dataclass
class OrderMessage:
    """Order message"""
    id: str
    order_id: str
    msg_type: MessageType
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    timestamp: datetime
    from_id: str
    to_id: Optional[str] = None


@dataclass
class Order:
    """Order data"""
    id: str
    customer_id: str
    customer_name: str
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    service_type: str = ""
    current_level: str = ""
    target_level: str = ""
    current_percent: float = 0.0
    target_percent: float = 0.0
    platform: str = "PC"
    price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    urgent: bool = False
    live_stream: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    customer_channel_id: Optional[str] = None
    worker_channel_id: Optional[str] = None
    messages: List[OrderMessage] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "worker_id": self.worker_id,
            "worker_name": self.worker_name,
            "service_type": self.service_type,
            "current_level": self.current_level,
            "target_level": self.target_level,
            "price": self.price,
            "status": self.status.value,
            "platform": self.platform,
            "urgent": self.urgent,
            "live_stream": self.live_stream,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "customer_channel_id": self.customer_channel_id,
            "worker_channel_id": self.worker_channel_id
        }


class TranslationBridge:
    """Chinese-English translation bridge"""

    def __init__(self, use_deepseek: bool = True):
        self.use_deepseek = use_deepseek
        self.deepseek_api_key = os.getenv("deepseek_api_key")
        self.deepseek_base_url = os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translate text between Chinese and English

        Args:
            text: Text to translate
            source_lang: Source language (zh/en)
            target_lang: Target language (zh/en)

        Returns:
            Translated text
        """
        if source_lang == target_lang:
            return text

        # Try DeepSeek first
        if self.use_deepseek and self.deepseek_api_key:
            try:
                return await self._translate_with_deepseek(text, source_lang, target_lang)
            except Exception as e:
                print(f"DeepSeek translation failed: {e}")

        # Fallback to simple translation
        return self._simple_translate(text, source_lang, target_lang)

    async def _translate_with_deepseek(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate using DeepSeek API"""
        import aiohttp

        lang_pair = "Chinese to English" if source_lang == "zh" else "English to Chinese"

        prompt = f"""You are a professional game service translator. Translate the following text from {lang_pair}.
Keep the gaming terminology and tone natural.
Only output the translated text, nothing else.

Text: {text}"""

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    raise Exception(f"API error: {response.status}")

    def _simple_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Simple translation with common phrases"""
        # Common game service phrases
        phrases_zh_to_en = {
            "好的": "OK",
            "收到": "Got it",
            "开始": "Starting",
            "完成": "Completed",
            "稍等": "Please wait",
            "谢谢": "Thank you",
            "没问题": "No problem",
            "正在进行": "In progress",
            "预计": "Estimated",
            "小时": "hours",
            "分钟": "minutes",
            "代练": "boosting",
            "声望": "reputation",
            "等级": "level",
            "徽章": "badge",
            "账号": "account",
            "密码": "password",
            "安全": "safe",
            "快速": "fast",
            "便宜": "cheap"
        }

        phrases_en_to_zh = {v: k for k, v in phrases_zh_to_en.items()}

        phrases = phrases_zh_to_en if source_lang == "zh" else phrases_en_to_zh

        result = text
        for orig, trans in phrases.items():
            result = result.replace(orig, trans)

        return result


class OrderManager:
    """Order management system with anonymous communication bridge"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "data", "orders", "orders.db"
            )
        self.db_path = db_path
        self.translation_bridge = TranslationBridge()
        self._init_db()

    def _init_db(self):
        """Initialize database"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                customer_name TEXT,
                worker_id TEXT,
                worker_name TEXT,
                service_type TEXT,
                current_level TEXT,
                target_level TEXT,
                current_percent REAL,
                target_percent REAL,
                platform TEXT,
                price REAL,
                status TEXT,
                urgent INTEGER,
                live_stream INTEGER,
                customer_channel_id TEXT,
                worker_channel_id TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                msg_type TEXT NOT NULL,
                original_text TEXT,
                translated_text TEXT,
                source_lang TEXT,
                target_lang TEXT,
                from_id TEXT,
                to_id TEXT,
                timestamp TEXT,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_order(
        self,
        customer_id: str,
        customer_name: str,
        service_type: str = "",
        current_level: str = "",
        target_level: str = "",
        current_percent: float = 0.0,
        target_percent: float = 0.0,
        platform: str = "PC",
        price: float = 0.0,
        urgent: bool = False,
        live_stream: bool = False
    ) -> Order:
        """Create a new order"""
        order_id = str(uuid.uuid4())[:8]

        order = Order(
            id=order_id,
            customer_id=customer_id,
            customer_name=customer_name,
            service_type=service_type,
            current_level=current_level,
            target_level=target_level,
            current_percent=current_percent,
            target_percent=target_percent,
            platform=platform,
            price=price,
            urgent=urgent,
            live_stream=live_stream,
            status=OrderStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # Save to database
        self._save_order(order)

        return order

    def _save_order(self, order: Order):
        """Save order to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order.id,
            order.customer_id,
            order.customer_name,
            order.worker_id,
            order.worker_name,
            order.service_type,
            order.current_level,
            order.target_level,
            order.current_percent,
            order.target_percent,
            order.platform,
            order.price,
            order.status.value,
            1 if order.urgent else 0,
            1 if order.live_stream else 0,
            order.customer_channel_id,
            order.worker_channel_id,
            order.created_at.isoformat(),
            order.updated_at.isoformat()
        ))

        conn.commit()
        conn.close()

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_order(row)
        return None

    def get_orders_by_customer(self, customer_id: str) -> List[Order]:
        """Get all orders by customer"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_order(row) for row in rows]

    def get_orders_by_worker(self, worker_id: str) -> List[Order]:
        """Get all orders by worker"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM orders WHERE worker_id = ? ORDER BY created_at DESC", (worker_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_order(row) for row in rows]

    def get_all_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get all orders, optionally filtered by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status:
            cursor.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (status.value,))
        else:
            cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_order(row) for row in rows]

    def _row_to_order(self, row) -> Order:
        """Convert database row to Order object"""
        return Order(
            id=row[0],
            customer_id=row[1],
            customer_name=row[2],
            worker_id=row[3],
            worker_name=row[4],
            service_type=row[5],
            current_level=row[6],
            target_level=row[7],
            current_percent=row[8],
            target_percent=row[9],
            platform=row[10],
            price=row[11],
            status=OrderStatus(row[12]),
            urgent=bool(row[13]),
            live_stream=bool(row[14]),
            customer_channel_id=row[15],
            worker_channel_id=row[16],
            created_at=datetime.fromisoformat(row[17]),
            updated_at=datetime.fromisoformat(row[18])
        )

    def assign_worker(self, order_id: str, worker_id: str, worker_name: str) -> bool:
        """Assign order to worker"""
        order = self.get_order(order_id)
        if not order:
            return False

        order.worker_id = worker_id
        order.worker_name = worker_name
        order.status = OrderStatus.ASSIGNED
        order.updated_at = datetime.now()

        self._save_order(order)
        return True

    def update_status(self, order_id: str, status: OrderStatus) -> bool:
        """Update order status"""
        order = self.get_order(order_id)
        if not order:
            return False

        order.status = status
        order.updated_at = datetime.now()

        self._save_order(order)
        return True

    def set_channels(self, order_id: str, customer_channel_id: str, worker_channel_id: str) -> bool:
        """Set communication channels"""
        order = self.get_order(order_id)
        if not order:
            return False

        order.customer_channel_id = customer_channel_id
        order.worker_channel_id = worker_channel_id
        order.updated_at = datetime.now()

        self._save_order(order)
        return True

    async def process_message(
        self,
        order_id: str,
        msg_type: MessageType,
        text: str,
        from_id: str
    ) -> OrderMessage:
        """
        Process message with translation

        Args:
            order_id: Order ID
            msg_type: Message type (customer/worker)
            text: Original text
            from_id: Sender ID

        Returns:
            OrderMessage with translation
        """
        order = self.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Determine translation direction
        if msg_type == MessageType.CUSTOMER:
            # Customer sends English → Translate to Chinese for worker
            source_lang = "en"
            target_lang = "zh"
        else:
            # Worker sends Chinese → Translate to English for customer
            source_lang = "zh"
            target_lang = "en"

        # Translate
        translated = await self.translation_bridge.translate(text, source_lang, target_lang)

        # Create message
        message = OrderMessage(
            id=str(uuid.uuid4())[:8],
            order_id=order_id,
            msg_type=msg_type,
            original_text=text,
            translated_text=translated,
            source_lang=source_lang,
            target_lang=target_lang,
            timestamp=datetime.now(),
            from_id=from_id
        )

        # Save message
        self._save_message(message)

        return message

    def _save_message(self, message: OrderMessage):
        """Save message to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            message.order_id,
            message.msg_type.value,
            message.original_text,
            message.translated_text,
            message.source_lang,
            message.target_lang,
            message.from_id,
            message.to_id,
            message.timestamp.isoformat()
        ))

        conn.commit()
        conn.close()

    def get_messages(self, order_id: str) -> List[OrderMessage]:
        """Get all messages for an order"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM messages WHERE order_id = ? ORDER BY timestamp",
            (order_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            messages.append(OrderMessage(
                id=row[0],
                order_id=row[1],
                msg_type=MessageType(row[2]),
                original_text=row[3],
                translated_text=row[4],
                source_lang=row[5],
                target_lang=row[6],
                timestamp=datetime.fromisoformat(row[9]),
                from_id=row[7],
                to_id=row[8]
            ))

        return messages

    def get_stats(self) -> Dict[str, int]:
        """Get order statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        # Total orders
        cursor.execute("SELECT COUNT(*) FROM orders")
        stats['total'] = cursor.fetchone()[0]

        # By status
        for status in OrderStatus:
            cursor.execute("SELECT COUNT(*) FROM orders WHERE status = ?", (status.value,))
            stats[status.value] = cursor.fetchone()[0]

        # Today's orders
        cursor.execute(
            "SELECT COUNT(*) FROM orders WHERE date(created_at) = date('now')"
        )
        stats['today'] = cursor.fetchone()[0]

        conn.close()
        return stats


# Global instance
_order_manager = None


def get_order_manager() -> OrderManager:
    """Get global order manager instance"""
    global _order_manager
    if _order_manager is None:
        _order_manager = OrderManager()
    return _order_manager

