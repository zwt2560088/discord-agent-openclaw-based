#!/usr/bin/env python3
"""
数据库管理层
处理所有数据持久化操作
"""

import sqlite3
from datetime import datetime
from typing import Optional, Dict, List
from config import config

class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = "orders.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 订单映射表
        c.execute('''CREATE TABLE IF NOT EXISTS order_mapping (
            order_id TEXT PRIMARY KEY,
            wx_chatid TEXT,
            discord_channel_id TEXT,
            discord_channel_name TEXT,
            handler_userid TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'active'
        )''')

        # 消息日志表
        c.execute('''CREATE TABLE IF NOT EXISTS message_log (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            source TEXT,
            sender TEXT,
            content TEXT,
            timestamp TEXT
        )''')

        # 系统状态表
        c.execute('''CREATE TABLE IF NOT EXISTS system_status (
            id INTEGER PRIMARY KEY,
            service TEXT,
            status TEXT,
            last_check TEXT,
            error_msg TEXT
        )''')

        conn.commit()
        conn.close()

    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== 订单操作 ====================

    def save_order(self, order_id: str, wx_chatid: str = "",
                   discord_channel_id: str = "", discord_channel_name: str = "",
                   handler_userid: str = "") -> bool:
        """保存订单映射"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''INSERT OR REPLACE INTO order_mapping
                        (order_id, wx_chatid, discord_channel_id, discord_channel_name, handler_userid, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                    (order_id, wx_chatid, discord_channel_id, discord_channel_name,
                     handler_userid, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 保存订单失败: {e}")
            return False
        finally:
            conn.close()

    def get_order(self, order_id: str) -> Optional[Dict]:
        """获取订单映射"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM order_mapping WHERE order_id = ?", (order_id,))
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_orders(self) -> List[Dict]:
        """获取所有订单"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM order_mapping ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    def update_order_status(self, order_id: str, status: str) -> bool:
        """更新订单状态"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("UPDATE order_mapping SET status = ? WHERE order_id = ?",
                     (status, order_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 更新订单状态失败: {e}")
            return False
        finally:
            conn.close()

    # ==================== 消息操作 ====================

    def log_message(self, order_id: str, source: str, sender: str, content: str) -> bool:
        """记录消息"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''INSERT INTO message_log (order_id, source, sender, content, timestamp)
                        VALUES (?, ?, ?, ?, ?)''',
                    (order_id, source, sender, content, datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 记录消息失败: {e}")
            return False
        finally:
            conn.close()

    def get_messages(self, order_id: str, limit: int = 50) -> List[Dict]:
        """获取订单消息"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''SELECT * FROM message_log
                        WHERE order_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?''', (order_id, limit))
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    # ==================== 系统状态操作 ====================

    def update_service_status(self, service: str, status: str, error_msg: str = "") -> bool:
        """更新服务状态"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''INSERT OR REPLACE INTO system_status
                        (service, status, last_check, error_msg)
                        VALUES (?, ?, ?, ?)''',
                    (service, status, datetime.now().isoformat(), error_msg))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 更新服务状态失败: {e}")
            return False
        finally:
            conn.close()

    def get_service_status(self, service: str) -> Optional[Dict]:
        """获取服务状态"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM system_status WHERE service = ?", (service,))
            row = c.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_status(self) -> List[Dict]:
        """获取所有服务状态"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM system_status")
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

# 数据库单例
db = Database(config.DB_PATH)

