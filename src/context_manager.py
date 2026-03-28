"""
多频道上下文管理系统 - 高性能、分布式就绪
支持多用户、多频道、持久化存储和快速检索
"""
import json
import time
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, OrderedDict
import hashlib

class SessionContext:
    """用户会话上下文"""
    def __init__(self, user_id: str, channel_id: str, username: str = ""):
        self.user_id = user_id
        self.channel_id = channel_id
        self.username = username
        self.messages: List[Dict] = []  # 最近消息历史
        self.metadata: Dict = {}  # 用户偏好、状态等
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.token_count = 0  # 用于分词计数

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """添加消息到历史"""
        msg = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        self.messages.append(msg)
        self.last_accessed = time.time()
        # 保留最近 10 条消息
        if len(self.messages) > 10:
            self.messages = self.messages[-10:]

    def get_context_window(self, max_messages: int = 5) -> str:
        """获取上下文窗口用于 LLM"""
        context = []
        for msg in self.messages[-max_messages:]:
            context.append(f"{msg['role'].upper()}: {msg['content']}")
        return "\n".join(context)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "username": self.username,
            "messages": self.messages,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed
        }


class ContextManager:
    """
    多频道上下文管理器
    - 内存缓存：热数据快速访问
    - SQLite 持久化：长期存储
    - 自动过期：清理旧会话
    """

    def __init__(self, db_path: str = "./context.db", cache_size: int = 1000, ttl_hours: int = 24):
        self.db_path = db_path
        self.cache_size = cache_size
        self.ttl_seconds = ttl_hours * 3600

        # 内存缓存 - LRU 结构
        self.context_cache: OrderedDict[str, SessionContext] = OrderedDict()
        self.lock = threading.RLock()  # 线程安全

        # 快速查询索引
        self.user_channels: Dict[str, set] = defaultdict(set)  # user_id -> channels
        self.channel_users: Dict[str, set] = defaultdict(set)   # channel_id -> users

        # 初始化数据库
        self._init_db()
        print("✅ Context Manager initialized")

    def _init_db(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS contexts (
                session_key TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                username TEXT,
                data TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                expires_at REAL NOT NULL,
                INDEX idx_user (user_id),
                INDEX idx_channel (channel_id),
                INDEX idx_expires (expires_at)
            )
        ''')
        conn.commit()
        conn.close()

    def _get_session_key(self, user_id: str, channel_id: str) -> str:
        """生成会话键"""
        return hashlib.md5(f"{user_id}:{channel_id}".encode()).hexdigest()

    def get_context(self, user_id: str, channel_id: str) -> SessionContext:
        """获取或创建会话上下文"""
        session_key = self._get_session_key(user_id, channel_id)

        with self.lock:
            # 1. 优先从内存缓存获取
            if session_key in self.context_cache:
                context = self.context_cache[session_key]
                # 移到末尾（LRU）
                self.context_cache.move_to_end(session_key)
                return context

            # 2. 从数据库加载
            context = self._load_from_db(session_key)
            if context:
                self._add_to_cache(session_key, context)
                return context

            # 3. 创建新上下文
            context = SessionContext(user_id, channel_id)
            self._add_to_cache(session_key, context)
            self.user_channels[user_id].add(channel_id)
            self.channel_users[channel_id].add(user_id)
            return context

    def _add_to_cache(self, session_key: str, context: SessionContext):
        """添加到内存缓存"""
        self.context_cache[session_key] = context
        # LRU 淘汰
        if len(self.context_cache) > self.cache_size:
            old_key, old_context = self.context_cache.popitem(last=False)
            self._save_to_db(old_key, old_context)

    def save_context(self, user_id: str, channel_id: str, context: SessionContext):
        """保存上下文"""
        session_key = self._get_session_key(user_id, channel_id)
        with self.lock:
            self._add_to_cache(session_key, context)
            self._save_to_db(session_key, context)

    def _save_to_db(self, session_key: str, context: SessionContext):
        """持久化到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            data = json.dumps(context.to_dict())
            expires_at = time.time() + self.ttl_seconds
            c.execute('''
                INSERT OR REPLACE INTO contexts
                (session_key, user_id, channel_id, username, data, created_at, last_accessed, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_key, context.user_id, context.channel_id, context.username,
                  data, context.created_at, context.last_accessed, expires_at))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ DB save error: {e}")

    def _load_from_db(self, session_key: str) -> Optional[SessionContext]:
        """从数据库加载"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT data FROM contexts WHERE session_key = ? AND expires_at > ?',
                     (session_key, time.time()))
            row = c.fetchone()
            conn.close()
            if row:
                data = json.loads(row[0])
                ctx = SessionContext(data['user_id'], data['channel_id'], data['username'])
                ctx.messages = data['messages']
                ctx.metadata = data['metadata']
                ctx.created_at = data['created_at']
                ctx.last_accessed = data['last_accessed']
                return ctx
        except Exception as e:
            print(f"⚠️ DB load error: {e}")
        return None

    def get_channel_users(self, channel_id: str) -> set:
        """获取频道中的所有用户"""
        with self.lock:
            return self.channel_users.get(channel_id, set()).copy()

    def get_user_channels(self, user_id: str) -> set:
        """获取用户所在的所有频道"""
        with self.lock:
            return self.user_channels.get(user_id, set()).copy()

    def cleanup_expired(self):
        """清理过期会话"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('DELETE FROM contexts WHERE expires_at < ?', (time.time(),))
            deleted = c.rowcount
            conn.commit()
            conn.close()
            if deleted > 0:
                print(f"🧹 Cleaned up {deleted} expired contexts")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.lock:
            return {
                "cache_size": len(self.context_cache),
                "unique_users": len(self.user_channels),
                "unique_channels": len(self.channel_users),
                "total_conversations": sum(len(users) for users in self.channel_users.values())
            }


class FastResponseCache:
    """快速响应缓存 - 减少重复计算"""

    def __init__(self, ttl_seconds: int = 300, max_size: int = 5000):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self.cache: Dict[str, Tuple[str, float]] = {}
        self.lock = threading.Lock()

    def get(self, query: str) -> Optional[str]:
        """获取缓存响应"""
        key = hashlib.md5(query.encode()).hexdigest()
        with self.lock:
            if key in self.cache:
                response, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return response
                del self.cache[key]
        return None

    def set(self, query: str, response: str):
        """缓存响应"""
        key = hashlib.md5(query.encode()).hexdigest()
        with self.lock:
            self.cache[key] = (response, time.time())
            # 简单的大小限制
            if len(self.cache) > self.max_size:
                # 移除最旧的 10%
                sorted_keys = sorted(self.cache.keys(),
                                    key=lambda k: self.cache[k][1])
                for k in sorted_keys[:len(self.cache) // 10]:
                    del self.cache[k]

    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()

