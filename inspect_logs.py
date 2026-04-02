#!/usr/bin/env python3
"""
快速查询日志中心数据库的脚本
"""

import sqlite3
import sys
from datetime import datetime
from tabulate import tabulate

def get_db():
    """连接数据库"""
    try:
        conn = sqlite3.connect("orders.db")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"❌ 无法连接数据库: {e}")
        sys.exit(1)

def print_recent_messages(limit=20):
    """打印最近的消息"""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT id, order_id, sender, content, timestamp
        FROM message_log
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))

    rows = c.fetchall()
    if not rows:
        print("❌ 没有消息记录")
        return

    data = []
    for row in rows:
        data.append([
            row["id"],
            row["order_id"][:15] + "..." if len(row["order_id"]) > 15 else row["order_id"],
            row["sender"][:12],
            row["content"][:40] + "..." if len(row["content"]) > 40 else row["content"],
            row["timestamp"].split("T")[0] if "T" in row["timestamp"] else row["timestamp"]
        ])

    print(f"\n📋 最近 {len(rows)} 条消息:\n")
    print(tabulate(data, headers=["ID", "Order ID", "Sender", "Content", "Date"], tablefmt="grid"))
    conn.close()

def print_sender_stats():
    """打印按 sender 分类的统计"""
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT sender, COUNT(*) as count
        FROM message_log
        GROUP BY sender
        ORDER BY count DESC
    """)

    rows = c.fetchall()
    if not rows:
        print("❌ 没有消息记录")
        return

    data = [[row["sender"], row["count"]] for row in rows]
    total = sum(row["count"] for row in rows)

    print(f"\n📊 按 Sender 统计 (总共 {total} 条):\n")
    print(tabulate(data, headers=["Sender", "Count"], tablefmt="grid"))
    conn.close()

def print_user_messages(user_id):
    """打印某个用户的消息"""
    conn = get_db()
    c = conn.cursor()

    order_id = f"user_{user_id}"
    c.execute("""
        SELECT id, sender, content, timestamp
        FROM message_log
        WHERE order_id = ?
        ORDER BY timestamp ASC
    """, (order_id,))

    rows = c.fetchall()
    if not rows:
        print(f"❌ 用户 {user_id} 没有消息记录")
        return

    print(f"\n👤 用户 {user_id} 的消息 (共 {len(rows)} 条):\n")
    for i, row in enumerate(rows, 1):
        time = row["timestamp"].split(".")[0] if "." in row["timestamp"] else row["timestamp"]
        sender_emoji = "👤" if "user_" in row["sender"] else "🤖"
        print(f"{i}. [{time}] {sender_emoji} {row['sender']}:")
        print(f"   {row['content'][:80]}")
        if len(row['content']) > 80:
            print(f"   ...")
        print()

    conn.close()

def print_today_messages():
    """打印今天的消息"""
    conn = get_db()
    c = conn.cursor()

    today = datetime.now().date().isoformat()
    c.execute("""
        SELECT id, order_id, sender, content, timestamp
        FROM message_log
        WHERE date(timestamp) = ?
        ORDER BY timestamp DESC
    """, (today,))

    rows = c.fetchall()
    if not rows:
        print(f"❌ 今天 ({today}) 没有消息记录")
        return

    data = []
    for row in rows:
        time = row["timestamp"].split(".")[0] if "." in row["timestamp"] else row["timestamp"]
        data.append([
            row["id"],
            row["order_id"][:12],
            row["sender"][:10],
            row["content"][:30] + "..." if len(row["content"]) > 30 else row["content"],
            time.split(" ")[1] if " " in time else time
        ])

    print(f"\n📅 今天的消息 (共 {len(rows)} 条):\n")
    print(tabulate(data, headers=["ID", "Order ID", "Sender", "Content", "Time"], tablefmt="grid"))
    conn.close()

def print_channel_messages(channel_id):
    """打印某个频道的消息"""
    conn = get_db()
    c = conn.cursor()

    order_id = f"channel_{channel_id}"
    c.execute("""
        SELECT id, sender, content, timestamp
        FROM message_log
        WHERE order_id = ?
        ORDER BY timestamp DESC
        LIMIT 50
    """, (order_id,))

    rows = c.fetchall()
    if not rows:
        print(f"❌ 频道 {channel_id} 没有消息记录")
        return

    data = []
    for row in rows:
        time = row["timestamp"].split(".")[0] if "." in row["timestamp"] else row["timestamp"]
        data.append([
            row["id"],
            row["sender"],
            row["content"][:40] + "..." if len(row["content"]) > 40 else row["content"],
            time
        ])

    print(f"\n#️⃣  频道 {channel_id} 的消息 (最近 {len(rows)} 条):\n")
    print(tabulate(data, headers=["ID", "Sender", "Content", "Timestamp"], tablefmt="grid"))
    conn.close()

def print_help():
    """打印帮助信息"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              📝 日志中心数据库查询工具                          ║
╚═══════════════════════════════════════════════════════════════╝

用法:
  python3 inspect_logs.py [命令] [参数]

命令:
  stats              - 显示 sender 统计
  recent [limit]     - 显示最近的消息 (默认20条)
  today              - 显示今天的消息
  user <user_id>     - 显示某个用户的消息
  channel <ch_id>    - 显示某个频道的消息

例子:
  python3 inspect_logs.py stats
  python3 inspect_logs.py recent 50
  python3 inspect_logs.py today
  python3 inspect_logs.py user 123456789
  python3 inspect_logs.py channel 987654321

数据库位置: orders.db
    """)

def main():
    if len(sys.argv) < 2:
        print_help()
        return

    cmd = sys.argv[1].lower()

    if cmd == "stats":
        print_sender_stats()
    elif cmd == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        print_recent_messages(limit)
    elif cmd == "today":
        print_today_messages()
    elif cmd == "user":
        if len(sys.argv) < 3:
            print("❌ 请指定 user_id")
            print("用法: python3 inspect_logs.py user <user_id>")
            return
        print_user_messages(sys.argv[2])
    elif cmd == "channel":
        if len(sys.argv) < 3:
            print("❌ 请指定 channel_id")
            print("用法: python3 inspect_logs.py channel <channel_id>")
            return
        print_channel_messages(sys.argv[2])
    else:
        print(f"❌ 未知命令: {cmd}")
        print_help()

if __name__ == "__main__":
    main()

