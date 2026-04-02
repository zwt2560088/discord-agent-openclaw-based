#!/usr/bin/env python3
"""
验证日志中心实现是否完整的脚本
"""

import os
import re
from pathlib import Path

def check_implementation():
    """检查 discord_bot_final.py 中的所有调用点"""

    file_path = Path("src/discord_bot_final.py")
    if not file_path.exists():
        print("❌ 找不到 src/discord_bot_final.py")
        return False

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    print("=" * 70)
    print("🔍 日志中心实现验证")
    print("=" * 70)

    # 定义要检查的调用点
    check_points = [
        {
            "name": "付款检测 (Payment Detector)",
            "pattern": r"sender=[\"']payment_detector[\"']",
            "description": "当用户说 'paid' / 'sent' 时"
        },
        {
            "name": "购买检测 (Purchase Detector)",
            "pattern": r"sender=[\"']purchase_detector[\"']",
            "description": "当用户说 'order' / 'let's go' 时"
        },
        {
            "name": "缓存命中 (Cache Hit)",
            "pattern": r"sender=[\"']cache[\"']",
            "description": "从缓存直接返回时"
        },
        {
            "name": "快速回复 (Quick Reply)",
            "pattern": r"sender=[\"']quick_reply[\"']",
            "description": "自动命令 (!pricing, !faq)"
        },
        {
            "name": "ReAct Agent",
            "pattern": r"sender=[\"']agent[\"']",
            "description": "复杂 AI 推理时"
        },
        {
            "name": "AI 调用 (Bot)",
            "pattern": r"sender=[\"']bot[\"']",
            "description": "OpenAI / DeepSeek 调用"
        }
    ]

    results = []
    for cp in check_points:
        found = bool(re.search(cp["pattern"], content))
        results.append({
            "name": cp["name"],
            "found": found,
            "description": cp["description"],
            "pattern": cp["pattern"]
        })

        status = "✅" if found else "❌"
        print(f"\n{status} {cp['name']}")
        print(f"   {cp['description']}")
        print(f"   Pattern: {cp['pattern']}")

    # 检查必要的条件检查
    print("\n" + "=" * 70)
    print("🛡️  安全检查")
    print("=" * 70)

    safety_checks = [
        {
            "name": "ORDER_DB_AVAILABLE 检查",
            "pattern": r"ORDER_DB_AVAILABLE",
            "description": "确保数据库可用后才记录"
        },
        {
            "name": "try/except 异常处理",
            "pattern": r"except Exception as e:.*log_message",
            "description": "异常不会中断消息处理",
            "multiline": True
        },
        {
            "name": "logger.debug 调试日志",
            "pattern": r"logger\.debug.*Failed to log",
            "description": "记录失败时输出调试信息"
        }
    ]

    for sc in safety_checks:
        if sc.get("multiline"):
            # 需要多行匹配
            pattern = sc["pattern"]
            found = bool(re.search(pattern, content, re.DOTALL))
        else:
            found = bool(re.search(sc["pattern"], content))

        status = "✅" if found else "⚠️" if "多行" not in sc["description"] else "⚠️"
        print(f"\n{status} {sc['name']}")
        print(f"   {sc['description']}")

    # 统计
    print("\n" + "=" * 70)
    print("📊 统计")
    print("=" * 70)

    total = len(results)
    found_count = sum(1 for r in results if r["found"])

    print(f"\n实现的调用点: {found_count}/{total}")

    if found_count == total:
        print("\n🎉 所有实现点都已完成！")
        return True
    else:
        print(f"\n⚠️  还有 {total - found_count} 个点需要实现")
        print("\n缺少的点:")
        for r in results:
            if not r["found"]:
                print(f"  - {r['name']}")
        return False

def check_database():
    """检查数据库是否存在且包含消息"""

    print("\n" + "=" * 70)
    print("🗄️  数据库检查")
    print("=" * 70)

    db_path = Path("orders.db")
    if not db_path.exists():
        print("⚠️  orders.db 不存在 (首次运行时会自动创建)")
        return False

    try:
        import sqlite3
        conn = sqlite3.connect("orders.db")
        c = conn.cursor()

        # 检查表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_log'")
        if not c.fetchone():
            print("❌ message_log 表不存在")
            conn.close()
            return False

        # 检查消息数
        c.execute("SELECT COUNT(*) FROM message_log")
        count = c.fetchone()[0]

        print(f"✅ 数据库存在，包含 {count} 条消息")

        # 检查 sender 分布
        c.execute("SELECT sender, COUNT(*) FROM message_log GROUP BY sender ORDER BY COUNT(*) DESC")
        rows = c.fetchall()

        if rows:
            print("\n📊 Sender 分布:")
            for sender, cnt in rows:
                print(f"  - {sender}: {cnt} 条")

        conn.close()
        return count > 0

    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")
        return False

def check_inspect_script():
    """检查查询脚本是否存在"""

    print("\n" + "=" * 70)
    print("🔧 工具检查")
    print("=" * 70)

    script_path = Path("inspect_logs.py")
    if not script_path.exists():
        print("❌ inspect_logs.py 不存在")
        return False

    if not os.access(script_path, os.X_OK):
        print("⚠️  inspect_logs.py 不是可执行的")
        return False

    print("✅ inspect_logs.py 存在且可执行")
    return True

def main():
    """运行所有检查"""

    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "🚀 日志中心实现完整性验证" + " " * 25 + "║")
    print("╚" + "═" * 68 + "╝")

    impl_ok = check_implementation()
    db_ok = check_database()
    script_ok = check_inspect_script()

    print("\n" + "=" * 70)
    print("📋 最终结果")
    print("=" * 70)

    print(f"\n{'✅' if impl_ok else '❌'} 代码实现: {'完整' if impl_ok else '不完整'}")
    print(f"{'✅' if db_ok else '⚠️'} 数据库: {'有消息' if db_ok else '为空或不存在'}")
    print(f"{'✅' if script_ok else '❌'} 查询工具: {'可用' if script_ok else '缺失'}")

    if impl_ok and script_ok:
        status = "🟢 生产就绪" if db_ok else "🟡 准备就绪（等待消息）"
    else:
        status = "🔴 需要修复"

    print(f"\n总体状态: {status}")

    if not impl_ok:
        print("\n💡 提示: 请确保所有 6 个调用点都已添加到 chat() 函数中")

    return impl_ok and script_ok

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

