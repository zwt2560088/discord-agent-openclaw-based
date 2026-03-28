#!/usr/bin/env python3
"""测试上下文加载是否正常"""
import asyncio
import os
import sys

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from discord_bot_final import context_manager

async def test_user_context():
    # 测试用户 ID (从数据库中提取的)
    test_user_id = "515199212548390922"

    print(f"🔍 测试用户 {test_user_id} 的上下文加载...")

    # 获取用户记忆
    memory = await context_manager.get_user_memory(test_user_id, limit=10)
    print(f"\n✅ 成功加载 {len(memory)} 条记忆:")
    for i, entry in enumerate(memory, 1):
        print(f"{i}. [{entry['role']}] {entry['content'][:60]}...")

    # 获取格式化摘要
    summary = await context_manager.get_user_memory_summary(test_user_id)
    print(f"\n📝 格式化摘要 (前500字符):\n{summary[:500]}")

    # 测试另一个用户
    test_user_id2 = "1346024374410412088"
    print(f"\n\n🔍 测试用户 {test_user_id2} 的上下文加载...")
    memory2 = await context_manager.get_user_memory(test_user_id2, limit=5)
    print(f"✅ 成功加载 {len(memory2)} 条记忆")
    summary2 = await context_manager.get_user_memory_summary(test_user_id2)
    print(f"📝 格式化摘要:\n{summary2[:500]}")

if __name__ == "__main__":
    asyncio.run(test_user_context())

