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

        # 订单映射表（扩展字段）
        c.execute('''CREATE TABLE IF NOT EXISTS order_mapping (
            order_id TEXT PRIMARY KEY,
            wx_chatid TEXT,
            discord_channel_id TEXT,
            discord_channel_name TEXT,
            handler_userid TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'active',
            amount REAL DEFAULT 0,
            service_desc TEXT DEFAULT '',
            confirmed_by TEXT DEFAULT '',
            consulting_channel_id TEXT DEFAULT '',
            updated_at TEXT
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

        # 订单序号计数表（用于生成不重复的序列号）
        c.execute('''CREATE TABLE IF NOT EXISTS order_sequence (
            date_key TEXT PRIMARY KEY,
            last_seq INTEGER DEFAULT 0
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
            c.execute("UPDATE order_mapping SET status = ?, updated_at = ? WHERE order_id = ?",
                     (status, datetime.now().isoformat(), order_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 更新订单状态失败: {e}")
            return False
        finally:
            conn.close()

    def generate_order_id(self) -> str:
        """
        生成订单号，格式 ORD-YYYYMMDD-XXXX
        使用数据库计数器保证同一天内不重复
        """
        conn = self.get_connection()
        c = conn.cursor()
        try:
            date_key = datetime.now().strftime("%Y%m%d")
            # 获取当天最后一个序列号
            c.execute("SELECT last_seq FROM order_sequence WHERE date_key = ?", (date_key,))
            row = c.fetchone()
            seq = (row["last_seq"] + 1) if row else 1
            # 更新序列号
            c.execute("INSERT OR REPLACE INTO order_sequence (date_key, last_seq) VALUES (?, ?)",
                     (date_key, seq))
            conn.commit()
            return f"ORD-{date_key}-{str(seq).zfill(4)}"
        except Exception as e:
            # 回退：使用时间戳
            print(f"⚠️ 订单号生成失败，使用回退方案: {e}")
            return f"ORD-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        finally:
            conn.close()

    def save_order_with_details(self, order_id: str, handler_userid: str,
                                amount: float, service_desc: str,
                                channel_id: str = "", channel_name: str = "",
                                confirmed_by: str = "", consulting_channel_id: str = "") -> bool:
        """保存完整订单信息（含金额、服务描述、状态）"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO order_mapping
                (order_id, handler_userid, discord_channel_id, discord_channel_name,
                 amount, service_desc, status, confirmed_by, consulting_channel_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            ''', (order_id, handler_userid, channel_id, channel_name,
                  amount, service_desc, confirmed_by, consulting_channel_id,
                  datetime.now().isoformat(), datetime.now().isoformat()))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ 保存订单失败: {e}")
            return False
        finally:
            conn.close()

    def update_order_channel(self, order_id: str, channel_id: str, channel_name: str) -> bool:
        """更新订单的履约频道信息"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("UPDATE order_mapping SET discord_channel_id = ?, discord_channel_name = ?, updated_at = ? WHERE order_id = ?",
                     (channel_id, channel_name, datetime.now().isoformat(), order_id))
            conn.commit()
            return True
        finally:
            conn.close()

    def get_orders_by_user(self, user_id: str) -> list:
        """获取指定用户的所有订单"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM order_mapping WHERE handler_userid = ? ORDER BY created_at DESC", (user_id,))
            return [dict(row) for row in c.fetchall()]
        finally:
            conn.close()

    def get_pending_orders(self) -> list:
        """获取所有待处理订单"""
        conn = self.get_connection()
        c = conn.cursor()
        try:
            c.execute("SELECT * FROM order_mapping WHERE status = 'pending' ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]
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

