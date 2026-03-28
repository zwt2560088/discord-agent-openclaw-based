#!/usr/bin/env python3
"""
🚀 最终融合版 Discord 机器人
综合我的方案 + 豆包方案的所有优点
核心能力：
✅ 关键词秒回 (<500ms) + AI智能处理 (<2s)
✅ 多频道完全隔离，永不串话
✅ 高并发无阻塞，支持50+频道
✅ 全链路错误恢复，单点失败不影响整体
"""

import aiohttp
import asyncio
import discord
import json
import logging
import os
import re
import sys
import time
from aiohttp_socks import ProxyConnector
from collections import OrderedDict
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple

# 全局 bot 缓存（供工具函数访问 guild/channel）
_bot_cache = []

# 订单数据库
try:
    from database import Database as OrderDatabase
    _orders_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orders.db")
    order_db = OrderDatabase(_orders_db_path)
    ORDER_DB_AVAILABLE = True
except Exception as _e:
    order_db = None
    ORDER_DB_AVAILABLE = False
    logger_setup = logging.getLogger("DiscordBot")
    logger_setup.warning(f"⚠️ Order database not available: {_e}")

# LangChain ReAct Agent imports (兼容新版 langchain 1.0+)
try:
    from langchain.agents import create_react_agent, AgentExecutor
    from langchain.tools import tool
    from langchain.prompts import PromptTemplate
    from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        # 尝试旧版导入方式
        from langchain.agents import create_react_agent, AgentExecutor
        from langchain.tools import tool
        from langchain.prompts import PromptTemplate
        from langchain.chat_models import ChatOpenAI
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False
        logger_setup = logging.getLogger("DiscordBot")
        logger_setup.warning("⚠️ LangChain not installed. ReAct Agent features disabled. Install with: pip install langchain langchain-openai langchain-community")
# 添加 src/legacy 目录到 Python 路径以导入 RAG Agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "legacy"))

# ====================== 日志配置（生产级）======================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DiscordBot")

# 加载 .env 配置（优先 DOTENV_PATH 环境变量指定的路径）
_env_file = os.environ.get("DOTENV_PATH")
load_dotenv(_env_file) if _env_file else load_dotenv()

# ====================== 配置常量 ======================
DISCORD_TOKEN = os.getenv("discord_token")
OPENAI_API_KEY = os.getenv("openai_api_key")
DEEPSEEK_API_KEY = os.getenv("deepseek_api_key")
HTTP_PROXY = os.getenv("HTTP_PROXY")

# 管理员/店主 Discord 用户 ID（逗号分隔）
# 这些人的消息会被记录到上下文（作为补充信息），但不会触发 AI 回复
_ADMIN_IDS_RAW = os.getenv("admin_user_ids", "")
ADMIN_USER_IDS = set()
for _aid in _ADMIN_IDS_RAW.split(","):
    _aid = _aid.strip()
    if _aid.isdigit():
        ADMIN_USER_IDS.add(int(_aid))

# 高并发参数
MAX_CONCURRENT_TASKS = 20
USER_RATE_LIMIT_SECONDS = 1
MAX_CONTEXT_ROUNDS = 10
CONTEXT_EXPIRE_HOURS = 24

# ====================== 第一层：关键词快速匹配表（内存级，1ms响应）======================
QUICK_REPLY_KEYWORDS = {
    # 格式: "关键词" -> {"快速回复内容", "是否订单意图"}
    "rep grind": {
        "reply": "🎯 **Rep Grind - Full Price List**\n\n**Rookie**: 1-5 $35 | 5-Starter1 $15 | 1-Starter1 $42\n**Starter**: 1-2 $21 | 2-3 $28 | 3-4 $35 | 4-5 $46 | 5-Starter1 $40\n**Veteran**: 2-3 $30 | 3-4 $35 | 4-5 $35 | 5-Legend1 $40 | 1-2 $50\n**Legend**: 1-2 $50 | 2-3 $60\n\n**Long Grind**: Rookie1-Starter3 $70 | Rookie1-Starter5 $100 | Rookie1-Veteran2 $150\n✅ Hand-played, safe, account secure\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    # "rep" 被故意移除 - 让 AI 智能处理，询问是 Rep Grind 还是 Rep Sleeve
    "level": {
        "reply": "🎯 **Rep Grind - Full Price List**\n\n**Rookie**: 1-5 $35 | 5-Starter1 $15 | 1-Starter1 $42\n**Starter**: 1-2 $21 | 2-3 $28 | 3-4 $35 | 4-5 $46 | 5-Starter1 $40\n**Veteran**: 2-3 $30 | 3-4 $35 | 4-5 $35 | 5-Legend1 $40 | 1-2 $50\n**Legend**: 1-2 $50 | 2-3 $60\n\n**Long Grind**: Rookie1-Starter3 $70 | Rookie1-Starter5 $100 | Rookie1-Veteran2 $150\n✅ Hand-played, safe, account secure\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "99": {
        "reply": "🎯 **Player Upgrade - Max 99 Overall**\n💰 Price: $15\n✅ Full attributes maxed, fits all modes\n✅ Unlock 99 Overall (Bring Your Own VC)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "player upgrade": {
        "reply": "🎯 **Player Upgrade - Max 99 Overall**\n💰 Price: $15\n✅ Full attributes maxed, fits all modes\n✅ Unlock 99 Overall (Bring Your Own VC)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "upgrade": {
        "reply": "🎯 **Player Upgrade - Max 99 Overall**\n💰 Price: $15\n✅ Full attributes maxed, fits all modes\n✅ Unlock 99 Overall (Bring Your Own VC)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "price": {
        "reply": "📋 **NBA 2K26 FULL PRICE LIST (USD)**\n\n🏀 **CHALLENGES**: $10-40 | 🎯 **BADGES**: $15\n👕 **REP SLEEVE**: $15-30 | 🏆 **FINISHED ACCOUNTS**: $80-100\n🌟 **REP GRIND**: $15-150 | 🔥 **SEASON PASS**: $15\n💎 **SPECIALTY**: $15-20 | 🎯 **99 OVERALL**: $15\n💰 **MT COINS**: $10-80 | 🛡️ **PC MODS DMA**: $60-110\n\n👉 Ask for specific service or type command!",
        "order_intent": False,
        "embed_color": 0xffaa00
    },
    "cost": {
        "reply": "📋 **NBA 2K26 FULL PRICE LIST (USD)**\n\n🏀 **CHALLENGES**: $10-40 | 🎯 **BADGES**: $15\n👕 **REP SLEEVE**: $15-30 | 🏆 **FINISHED ACCOUNTS**: $80-100\n🌟 **REP GRIND**: $15-150 | 🔥 **SEASON PASS**: $15\n💎 **SPECIALTY**: $15-20 | 🎯 **99 OVERALL**: $15\n💰 **MT COINS**: $10-80 | 🛡️ **PC MODS DMA**: $60-110\n\n👉 Ask for specific service or type command!",
        "order_intent": False,
        "embed_color": 0xffaa00
    },
    "how much": {
        "reply": "📋 **NBA 2K26 FULL PRICE LIST (USD)**\n\n🏀 **CHALLENGES**: $10-40 | 🎯 **BADGES**: $15\n👕 **REP SLEEVE**: $15-30 | 🏆 **FINISHED ACCOUNTS**: $80-100\n🌟 **REP GRIND**: $15-150 | 🔥 **SEASON PASS**: $15\n💎 **SPECIALTY**: $15-20 | 🎯 **99 OVERALL**: $15\n💰 **MT COINS**: $10-80 | 🛡️ **PC MODS DMA**: $60-110\n\n👉 Which service interests you?",
        "order_intent": False,
        "embed_color": 0xffaa00
    },
    "pass": {
        "reply": "🎯 **Season Pass Completion**\n💰 Price: $15\n✅ Full season pass + all rewards\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "mt": {
        "reply": "🎯 **MT Coins Boost**\n💰 100K MT: $10 | 500K MT: $45 | 1M MT: $80\n✅ Safe & fast transfer, 100% no ban\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "sleeve": {
        "reply": "🎯 **Rep Sleeve Pricing**\n💰 50x Rep Sleeve: $15 | 50x Rep Sleeve + Level 40: $25\n💰 100x Rep Sleeve: $21.50 | 300x Rep Sleeve: $30\n✅ ETA: 10 mins | Login required\n✅ Sourced from G2G (World Leading Marketplace)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "season 5": {
        "reply": "🎯 **Rep Sleeve Pricing**\n💰 50x Rep Sleeve: $15 | 50x Rep Sleeve + Level 40: $25\n💰 100x Rep Sleeve: $21.50 | 300x Rep Sleeve: $30\n✅ ETA: 10 mins | Login required\n✅ Sourced from G2G (World Leading Marketplace)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "dma": {
        "reply": "🎯 **PC Mods DMA Protection**\n💰 $60/month | $110 permanent\n✅ Advanced anti-detection for PC mods\n✅ Lifetime updates included (permanent plan)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "mods": {
        "reply": "🎯 **PC Mods DMA Protection**\n💰 $60/month | $110 permanent\n✅ Advanced anti-detection for PC mods\n✅ Lifetime updates included (permanent plan)\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "challenge": {
        "reply": "🏀 **Lifetime Challenge Grinds**\n💰 250 Layers (2 Blacktop + 500K VC): $40\n💰 200 Layers (2 Blacktop + Boost Shoes): $20\n💰 150 Layers (1 Blacktop + Boost Shoes): $15\n💰 100 Layers (1 Blacktop + Go-Kart): $10\n✅ Hand-played, account secure\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "badge": {
        "reply": "🌟 **Badge Services**\n💰 Max Build Badges (All Gold/HOF): $15\n💰 Gym Rat Badge: $15\n💰 Legendary Prestige Reset: $15\n✅ All badges unlocked and maxed\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "specialty": {
        "reply": "🎯 **Build Specialty Challenges**\n💰 Single Specialty (2 Blacktop Wins): $15\n💰 All 5 Specialties (Full Completion): $20\n✅ All builds max specialties\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "account": {
        "reply": "💎 **Finished Accounts (Pre-Built)**\n💰 A1: 600K VC + 10 Blacktop + 5 Specialties: $100\n💰 A2: 100K VC + 8 Blacktop + 5 Specialties: $80\n✅ Ready to play immediately\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "rep account": {
        "reply": "🏆 **Rep Rank - Full Price List**\n\n**Rookie**: 1-5 $35 | 5-Starter1 $15 | 1-Starter1 $42\n**Starter**: 1-2 $21 | 2-3 $28 | 3-4 $35 | 4-5 $46 | 5-Starter1 $40\n**Veteran**: 2-3 $30 | 3-4 $35 | 4-5 $35 | 5-Legend1 $40 | 1-2 $50\n**Legend**: 1-2 $50 | 2-3 $60\n\n**Long Packages**: R1-S3 $70 | R1-S5 $100 | R1-V2 $150\n✅ Custom built to your rank\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "season": {
        "reply": "🔥 **Season Pass & Levels**\n💰 Season 40 Level Instant Boost: $15\n💰 Stage 30 Team - 4 Blacktop Wins (7 days): $15\n✅ Quick completion\n👉 Type 'order' to start!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "help": {
        "reply": "📚 **Available Commands**\n• challenge / specialty / badge\n• account / rep account\n• rep grind / sleeve / 99\n• season / mt / dma\n• Type 'price' for full list\n• Type 'order' to purchase\n• 24/7 support!",
        "order_intent": False,
        "embed_color": 0x0099ff
    },
    # Rep Sleeve 规格选项（用于快速识别"50x" "100x" "300x"）
    "50x": {
        "reply": "✅ **50x Rep Sleeve**\n💰 Options:\n• **50x Rep Sleeve**: $15\n• **50x Rep Sleeve + Level 40**: $25\n\n⏱️ ETA: 10 minutes | Login required\n✅ Sourced from G2G (World Leading Marketplace)\n\n👉 Type 'order' to proceed!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "100x": {
        "reply": "✅ **100x Rep Sleeve**\n💰 Price: **$21.50**\n\n⏱️ ETA: 10 minutes | Login required\n✅ Sourced from G2G (World Leading Marketplace)\n\n👉 Type 'order' to proceed!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    },
    "300x": {
        "reply": "✅ **300x Rep Sleeve**\n💰 Price: **$30**\n\n⏱️ ETA: 10 minutes | Login required\n✅ Sourced from G2G (World Leading Marketplace)\n\n👉 Type 'order' to proceed!",
        "order_intent": True,
        "embed_color": 0x00ffcc
    }
}

# ====================== 第二层：多频道上下文隔离 + 全量用户记忆管理器 ======================
class ContextManager:
    """
    双层记忆系统：
    1. 频道级上下文（channel_id）— 近期对话，用于当前会话
    2. 用户级全量记忆（user_id）— 所有历史互动，跨频道、跨时间
    记录用户与任何人（bot、管理员、其他用户）的所有互动
    """
    def __init__(self):
        self._cache: OrderedDict[str, Dict] = OrderedDict()  # channel_id -> context
        self._max_cache_size = 100  # 最多缓存 100 个频道的上下文
        self._db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_context.db")
        self._user_memory_cache: OrderedDict[str, List[Dict]] = OrderedDict()  # user_id -> memory
        self._max_user_cache_size = 500  # 最多缓存 500 个用户的记忆
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库（频道上下文 + 用户全量记忆）"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            # 频道级上下文（原有）
            c.execute("""
                CREATE TABLE IF NOT EXISTS contexts (
                    channel_id TEXT PRIMARY KEY,
                    history TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    expires_at REAL
                )
            """)
            # 用户级全量记忆（新增）
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    author_name TEXT,
                    channel_id TEXT,
                    channel_name TEXT,
                    order_id TEXT,
                    timestamp REAL NOT NULL
                )
            """)
            # 为 user_memory 创建索引加速查询
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_memory_user_id ON user_memory(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_user_memory_timestamp ON user_memory(timestamp)")
            conn.commit()
            conn.close()
            logger.info("✅ SQLite database initialized (contexts + user_memory)")
        except Exception as e:
            logger.warning(f"⚠️ SQLite initialization failed: {e}")

    async def get_context(self, channel_id: str) -> List[Dict]:
        """获取指定频道的对话上下文"""
        # 1. 优先从内存获取（热数据）
        if channel_id in self._cache:
            context_data = self._cache[channel_id]
            # 检查是否过期
            if context_data["expires_at"] > time.time():
                # 移到末尾（LRU）
                self._cache.move_to_end(channel_id)
                return context_data["history"]

        # 2. 从数据库加载（冷数据）
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("SELECT history FROM contexts WHERE channel_id = ? AND expires_at > ?",
                      (channel_id, time.time()))
            row = c.fetchone()
            conn.close()
            if row:
                history = json.loads(row[0])
                # 加载到内存缓存
                self._cache[channel_id] = {
                    "history": history,
                    "expires_at": time.time() + CONTEXT_EXPIRE_HOURS * 3600
                }
                return history
        except Exception as e:
            logger.warning(f"⚠️ Failed to load context from DB: {e}")

        # 3. 新建空上下文
        return []

    async def save_context(self, channel_id: str, user_msg: str, ai_reply: str):
        """保存对话上下文"""
        # 获取现有历史
        history = await self.get_context(channel_id)

        # 添加新消息
        history.append({"role": "user", "content": user_msg, "ts": time.time()})
        history.append({"role": "assistant", "content": ai_reply, "ts": time.time()})

        # 只保留最近 N 轮
        if len(history) > MAX_CONTEXT_ROUNDS * 2:
            history = history[-MAX_CONTEXT_ROUNDS * 2:]

        # 保存到内存缓存
        expires_at = time.time() + CONTEXT_EXPIRE_HOURS * 3600
        self._cache[channel_id] = {"history": history, "expires_at": expires_at}

        # 触发 LRU 淘汰
        if len(self._cache) > self._max_cache_size:
            old_key, old_data = self._cache.popitem(last=False)
            await self._persist_to_db(old_key, old_data["history"])

        # 异步持久化到 DB
        asyncio.create_task(self._persist_to_db(channel_id, history))

    async def _persist_to_db(self, channel_id: str, history: List[Dict]):
        """异步持久化到数据库"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO contexts
                (channel_id, history, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
            """, (channel_id, json.dumps(history), time.time(), time.time(),
                  time.time() + CONTEXT_EXPIRE_HOURS * 3600))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to persist context: {e}")

    async def clear_context(self, channel_id: str):
        """清空指定频道上下文（订单完成时调用）"""
        self._cache.pop(channel_id, None)
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("DELETE FROM contexts WHERE channel_id = ?", (channel_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear context: {e}")
        logger.info(f"✅ Context cleared for channel {channel_id}")

    # ====================== 用户全量记忆方法 ======================

    async def add_user_memory(self, user_id: str, role: str, content: str,
                              author_name: str = "", channel_id: str = None,
                              channel_name: str = None, order_id: str = None):
        """
        将一条消息记录到用户的长期记忆。
        role: 'user'（用户自己的消息）, 'admin'（管理员发的消息）, 'assistant'（bot 回复）, 'system'（系统事件）
        记录内容包含完整的元信息（频道、时间、作者名），让 AI 后续能理解完整上下文。
        """
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO user_memory (user_id, role, content, author_name, channel_id, channel_name, order_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, role, content, author_name, channel_id, channel_name, order_id, time.time()))
            conn.commit()
            conn.close()

            # 更新内存缓存
            memory_entry = {
                "role": role, "content": content, "author_name": author_name,
                "channel_id": channel_id, "channel_name": channel_name,
                "order_id": order_id, "ts": time.time()
            }
            if user_id in self._user_memory_cache:
                self._user_memory_cache[user_id].append(memory_entry)
                # 限制内存缓存条目数
                if len(self._user_memory_cache[user_id]) > 50:
                    self._user_memory_cache[user_id] = self._user_memory_cache[user_id][-50:]
            else:
                self._user_memory_cache[user_id] = [memory_entry]
                # LRU 淘汰
                if len(self._user_memory_cache) > self._max_user_cache_size:
                    self._user_memory_cache.popitem(last=False)

        except Exception as e:
            logger.warning(f"⚠️ Failed to add user memory for {user_id}: {e}")

    async def get_user_memory(self, user_id: str, limit: int = 30) -> List[Dict]:
        """
        获取用户的完整历史记忆（按时间倒序取最近 limit 条）。
        返回包含 role/content/author_name/channel_name/timestamp 的列表。
        """
        # 1. 优先从内存获取
        if user_id in self._user_memory_cache:
            memory = self._user_memory_cache[user_id]
            if len(memory) >= limit:
                return memory[-limit:]

        # 2. 从数据库加载
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("""
                SELECT role, content, author_name, channel_id, channel_name, order_id, timestamp
                FROM user_memory
                WHERE user_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (user_id, limit))
            rows = c.fetchall()
            conn.close()

            if rows:
                memory = [{
                    "role": r[0], "content": r[1], "author_name": r[2],
                    "channel_id": r[3], "channel_name": r[4],
                    "order_id": r[5], "ts": r[6]
                } for r in rows]
                # 更新内存缓存
                self._user_memory_cache[user_id] = memory[-50:]  # 最多缓存 50 条
                self._user_memory_cache.move_to_end(user_id)
                return memory
        except Exception as e:
            logger.warning(f"⚠️ Failed to load user memory for {user_id}: {e}")

        return []

    async def get_user_memory_summary(self, user_id: str) -> str:
        """
        获取用户记忆的格式化摘要，用于注入 AI 上下文。
        包含：用户身份、管理员互动、询价历史、订单相关信息。
        """
        memory = await self.get_user_memory(user_id, limit=30)
        if not memory:
            return ""

        lines = []
        for entry in memory:
            role = entry["role"].upper()
            author = entry.get("author_name", "")
            channel = entry.get("channel_name", "")
            content = entry["content"][:150]  # 截断过长内容

            # 格式化：[ROLE] (Author) content (in #channel)
            parts = [f"[{role}]"]
            if author and role != "USER":
                parts.append(f"({author})")
            parts.append(content)
            if channel:
                parts.append(f"[in #{channel}]")
            lines.append(" ".join(parts))

        return "\n".join(lines)

    async def flush_all(self):
        """将所有内存缓存持久化到数据库（关闭前调用）"""
        count = 0
        for channel_id, context_data in self._cache.items():
            try:
                await self._persist_to_db(channel_id, context_data["history"])
                count += 1
            except Exception as e:
                logger.warning(f"⚠️ Failed to flush context for {channel_id}: {e}")
        logger.info(f"💾 Flushed {count} channel contexts to database")

# 全局上下文管理器
context_manager = ContextManager()

# ====================== LangChain ReAct Agent 工具定义 ======================
if LANGCHAIN_AVAILABLE:
    @tool
    def get_price(service: str, details: str = "") -> str:
        """
        查询指定服务的价格信息。支持单个服务或组合服务。
        参数:
        - service: 服务名称 (rep sleeve, rep grind, 99, challenge, badge, specialty, mt, season pass, dma, account, combo, etc.)
        - details: 可选细节 (50x, 100x, 300x, lvl40, starter, legend, 250, etc.)
        """
        service_lower = (service + " " + details).lower()
        results = []

        # ========== 组合检测 ==========
        has_combo = any(x in service_lower for x in ["+", "combo", "both", "package", " and ", " with "])

        # ========== 50x Rep Sleeve + Level 40 ==========
        if any(x in service_lower for x in ["50x", "50 x"]) and any(x in service_lower for x in ["lvl40", "level 40", "level40", "lv40"]):
            results.append("50x Rep Sleeve + Level 40: **$25**")

        # ========== Rep Sleeve ==========
        if any(x in service_lower for x in ["50x", "50 x"]):
            if not any(x in service_lower for x in ["lvl40", "level 40", "level40"]):
                results.append("50x Rep Sleeve: **$15**")
        if any(x in service_lower for x in ["100x", "100 x"]):
            results.append("100x Rep Sleeve: **$21.50**")
        if any(x in service_lower for x in ["300x", "300 x"]):
            results.append("300x Rep Sleeve: **$30**")
        if any(x in service_lower for x in ["sleeve", "rep sleeve"]) and not results:
            results.append("Rep Sleeve: 50x $15 | 100x $21.50 | 300x $30 (50x+Lvl40: $25)")

        # ========== Rep Grind ==========
        if any(x in service_lower for x in ["rep grind", "grind", "rep rank", "level boost"]):
            if "legend" in service_lower:
                results.append("Rep Grind to Legend: **$50-60**")
            elif "veteran" in service_lower:
                results.append("Rep Grind to Veteran: **$30-50**")
            elif "starter" in service_lower:
                results.append("Rep Grind to Starter: **$21-46**")
            elif "rookie" in service_lower:
                results.append("Rep Grind Rookie: **$15-42**")
            elif "long" in service_lower:
                results.append("Long Grind: R1-S3 $70 | R1-S5 $100 | R1-V2 $150")
            else:
                results.append("Rep Grind: **$15-150** (Rookie→Legend)")

        # ========== Challenge ==========
        if any(x in service_lower for x in ["challenge", "layer"]):
            if "250" in service_lower:
                results.append("250 Layers Challenge: **$40**")
            elif "200" in service_lower:
                results.append("200 Layers Challenge: **$20**")
            elif "150" in service_lower:
                results.append("150 Layers Challenge: **$15**")
            elif "100" in service_lower:
                results.append("100 Layers Challenge: **$10**")
            else:
                results.append("Challenges: 250 $40 | 200 $20 | 150 $15 | 100 $10")

        # ========== 99 Overall ==========
        if any(x in service_lower for x in ["99 overall", "99 ovr", "max overall", "99"]):
            if not any(x in service_lower for x in ["100x", "300x", "50x"]):
                results.append("99 Overall: **$15**")

        # ========== Badge ==========
        if any(x in service_lower for x in ["badge", "badges"]):
            results.append("Badge Unlock: **$15**")

        # ========== Specialty ==========
        if any(x in service_lower for x in ["specialty", "specialities", "all 5", "all specialization"]):
            if any(x in service_lower for x in ["all 5", "all specialization", "specialties"]):
                results.append("All 5 Specialties: **$20**")
            else:
                results.append("Single Specialty: **$15**")

        # ========== MT Coins ==========
        if any(x in service_lower for x in ["mt coin", "mt "]):
            if "1m" in service_lower:
                results.append("1M MT Coins: **$80**")
            elif "500k" in service_lower:
                results.append("500K MT Coins: **$45**")
            elif "100k" in service_lower:
                results.append("100K MT Coins: **$10**")
            else:
                results.append("MT Coins: 100K $10 | 500K $45 | 1M $80")

        # ========== Season Pass ==========
        if any(x in service_lower for x in ["season pass", "season 40"]):
            results.append("Season Pass: **$15**")

        # ========== DMA ==========
        if "dma" in service_lower:
            results.append("DMA Mods: **$60/month** or **$110 permanent**")

        # ========== Account ==========
        if any(x in service_lower for x in ["account", "pre-built"]):
            results.append("Pre-built Account: **$80-100**")

        if results:
            if has_combo and len(results) > 1:
                total = 0
                for r in results:
                    # 从结果中提取价格数字
                    import re as _re
                    prices = _re.findall(r'\$(\d+(?:\.\d+)?)', r)
                    for p in prices:
                        try:
                            total += float(p)
                        except ValueError:
                            pass
                combo_reply = "🎯 **Combo Price:**\n" + "\n".join(f"• {r}" for r in results)
                if total > 0:
                    combo_reply += f"\n\n💰 **Combo Total: ${total}**"
                return combo_reply
            return " | ".join(results)

        return "Service not found. Try: rep sleeve, rep grind, 99 overall, challenge, badge, specialty, mt coins, season pass, dma, account"

    @tool
    def confirm_payment(order_details: str) -> str:
        """
        当管理员或用户确认已付款时，解析订单详情并返回汇总。
        返回结果包含金额和具体的 !confirm-payment 命令，供管理员执行。
        参数: order_details - 订单内容描述，如 "rep grind", "50x rep sleeve", "250 all specialization + 50x"
        """
        details_lower = order_details.lower()
        total = 0
        items = []

        # 解析订单项目
        # Challenge（按数字优先匹配更大的）
        if "250" in details_lower and any(x in details_lower for x in ["challenge", "layer", "250"]):
            items.append("250 Layers Challenge ($40)")
            total += 40
        elif "200" in details_lower and any(x in details_lower for x in ["challenge", "layer"]):
            items.append("200 Layers Challenge ($20)")
            total += 20
        elif "150" in details_lower and any(x in details_lower for x in ["challenge", "layer"]):
            items.append("150 Layers Challenge ($15)")
            total += 15
        elif "100" in details_lower and any(x in details_lower for x in ["challenge", "layer"]):
            items.append("100 Layers Challenge ($10)")
            total += 10

        # Specialty
        if any(x in details_lower for x in ["all 5", "all specialization", "specialties", "speciality"]):
            items.append("All 5 Specialties ($20)")
            total += 20
        elif any(x in details_lower for x in ["specialty", "specialisation"]):
            items.append("Single Specialty ($15)")
            total += 15

        # ========== 50x Rep Sleeve + Level 40 组合 ==========
        if any(x in details_lower for x in ["50x", "50 x"]) and any(x in details_lower for x in ["lvl40", "level 40", "level40", "lv40"]):
            items.append("50x Rep Sleeve + Level 40 ($25)")
            total += 25
        # ========== Rep Sleeve（独立） ==========
        elif "300x" in details_lower:
            items.append("300x Rep Sleeve ($30)")
            total += 30
        elif "100x" in details_lower:
            items.append("100x Rep Sleeve ($21.50)")
            total += 21.5
        elif "50x" in details_lower:
            items.append("50x Rep Sleeve ($15)")
            total += 15

        # 99 Overall
        if any(x in details_lower for x in ["99 overall", "99 ovr", "max overall"]):
            items.append("99 Overall ($15)")
            total += 15

        # Badge
        if any(x in details_lower for x in ["badge", "badges", "hof badge", "gold badge"]):
            items.append("Badge Unlock ($15)")
            total += 15

        # Rep Grind
        if any(x in details_lower for x in ["rep grind", "grind", "rep rank"]):
            if "legend" in details_lower:
                items.append("Rep Grind to Legend ($60)")
                total += 60
            elif "veteran" in details_lower:
                items.append("Rep Grind to Veteran ($40)")
                total += 40
            elif "starter" in details_lower:
                items.append("Rep Grind to Starter ($40)")
                total += 40
            elif "rookie" in details_lower:
                items.append("Rep Grind Rookie ($35)")
                total += 35
            else:
                items.append("Rep Grind ($40)")
                total += 40

        # Season Pass
        if any(x in details_lower for x in ["season pass", "season 40"]):
            items.append("Season Pass ($15)")
            total += 15

        # MT Coins
        if any(x in details_lower for x in ["mt coin", "mt "]):
            if "1m" in details_lower or "1m" in details_lower:
                items.append("1M MT Coins ($80)")
                total += 80
            elif "500k" in details_lower:
                items.append("500K MT Coins ($45)")
                total += 45
            elif "100k" in details_lower:
                items.append("100K MT Coins ($10)")
                total += 10
            else:
                items.append("MT Coins ($10-80)")
                total += 10  # 默认最低价

        # DMA
        if "dma" in details_lower:
            items.append("DMA Mods ($60-110)")
            total += 60

        # Account
        if any(x in details_lower for x in ["account", "pre-built"]):
            items.append("Pre-built Account ($80-100)")
            total += 80

        if items:
            service_str = " + ".join(item.split(" ($")[0] for item in items)
            summary = (
                f"✅ **Payment Confirmed!**\n\n"
                f"**Order Summary:**\n" + "\n".join(f"• {item}" for item in items) +
                f"\n\n**Total: ${total}**\n\n"
                f"📋 **Admin, run this command to create order channel:**\n"
                f"`!confirm-payment @USER {total} \"{service_str}\"`"
            )
            return summary

        return f"✅ Payment mentioned but no specific service matched in: \"{order_details}\". Admin please run: `!confirm-payment @USER <amount> \"<service>\"` with correct details."

    @tool
    def send_payment_confirmation(user_id: str, amount: float, service_desc: str, channel_id: str) -> str:
        """
        在咨询频道发送支付确认请求消息（带确认按钮），管理员点击后自动创建订单。
        当用户明确表达购买意图（如 "I want to buy", "order now", "let's go" 等）后调用此工具。
        参数:
        - user_id: 客户 Discord 用户 ID
        - amount: 订单金额（数字）
        - service_desc: 服务描述（如 "50x Rep Sleeve + Level 40"）
        - channel_id: 当前频道 ID
        """
        try:
            # 异步发送消息（在事件循环中调度）
            loop = asyncio.get_event_loop()

            async def _send():
                # 需要 bot 实例 — 从全局获取
                for g in _bot_cache:
                    ch = g.get_channel(int(channel_id))
                    if ch:
                        break
                else:
                    return "Channel not found."

                user = ch.guild.get_member(int(user_id))
                if not user:
                    return f"User {user_id} not found in this server."

                view = PaymentConfirmView(
                    customer_id=int(user_id),
                    service_desc=service_desc,
                    amount=float(amount)
                )
                embed = discord.Embed(
                    title="💳 Pending Payment Confirmation",
                    description=f"Admin: Please verify payment and confirm below.",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Customer", value=user.mention, inline=True)
                embed.add_field(name="Service", value=service_desc, inline=False)
                embed.add_field(name="Amount", value=f"${float(amount):.2f}", inline=True)
                embed.set_footer(text="⏰ Buttons expire in 2 hours | Admins only")
                await ch.send(embed=embed, view=view)
                return f"Sent payment confirmation request for {user.name} in {ch.mention}."

            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_send(), loop)
                return future.result(timeout=10)
            else:
                return loop.run_until_complete(_send())
        except Exception as e:
            return f"Failed to send payment confirmation: {str(e)}"

    @tool
    def query_knowledge(query: str) -> str:
        """
        从 RAG 知识库或本地文件查询信息。
        参数: query - 查询内容
        """
        try:
            knowledge_file = "./knowledge/NBA2K26_PRICING_STANDARD.md"
            if os.path.exists(knowledge_file):
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    content = f.read()
                return f"Knowledge base reference available. Query: {query}"
            return "Knowledge base not available."
        except Exception as e:
            return f"Knowledge query failed: {str(e)}"

    @tool
    def check_order_status(user_id: str = "", service_desc: str = "") -> str:
        """
        查询用户的订单状态。根据用户ID和服务描述查找活跃订单。
        如果提供了 service_desc，尝试匹配包含该描述的订单。
        参数:
        - user_id: 用户ID（Discord ID 字符串）
        - service_desc: 可选的服务描述（如 "50x rep sleeve", "rep grind"）
        """
        try:
            import sqlite3
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_context.db")
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            if not user_id:
                return "No user ID provided. Cannot check order status."

            # 从用户记忆中查找包含订单相关信息的历史条目
            # 查找包含支付确认、价格查询、订单创建等相关内容的记忆
            order_keywords = ["payment", "paid", "order", "$", "confirm", "buy", "fulfillment"]

            c.execute("""
                SELECT content, role, author_name, channel_name, timestamp
                FROM user_memory
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT 20
            """, (user_id,))
            rows = c.fetchall()
            conn.close()

            if not rows:
                return f"No history found for user {user_id}. This appears to be a new customer."

            # 分析记忆条目，提取订单相关信息
            results = []
            for row in rows:
                content = row[0].lower()
                role = row[1]
                author = row[2]
                channel = row[3]
                # 检查是否包含订单关键词
                if any(kw in content for kw in order_keywords) or ("$" in row[0]):
                    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(row[4]))
                    results.append(f"• [{role}] ({author}) {row[0][:120]} — {ts} [#{channel}]")

            if not results:
                return f"User {user_id} has interaction history but no order-related records found."

            # 如果提供了 service_desc，过滤相关结果
            if service_desc:
                filtered = [r for r in results if service_desc.lower() in r.lower()]
                if filtered:
                    results = filtered

            return f"**Order History for User {user_id}:**\n" + "\n".join(results[:5])

        except Exception as e:
            return f"Failed to check order status: {str(e)}"

# ====================== 第三层：异步 AI 处理服务 ======================
class AIService:
    """
    全异步 AI 服务
    1. 关键词快速回复 (<500ms)
    2. AI 智能处理 (<2s)
    支持 OpenAI + DeepSeek 双引擎
    """
    def __init__(self):
        self._openai_enabled = bool(OPENAI_API_KEY)
        self._deepseek_enabled = bool(DEEPSEEK_API_KEY)
        self._use_ai = self._openai_enabled or self._deepseek_enabled
        self._rag_agent = None
        self._react_agent = None
        self._agent_executor = None
        logger.info(f"AI Services: OpenAI={self._openai_enabled}, DeepSeek={self._deepseek_enabled}, ReAct={LANGCHAIN_AVAILABLE}")

        # 初始化 RAG Agent
        try:
            from rag_agent import RAGAgent
            knowledge_dir = "./knowledge"  # 使用 knowledge 目录
            self._rag_agent = RAGAgent(api_key=DEEPSEEK_API_KEY or "", knowledge_dir=knowledge_dir)
            logger.info("✅ RAG Agent initialized successfully")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize RAG Agent: {e}")
            logger.info("🔄 Will fall back to simple knowledge base queries")

        # 初始化 LangChain ReAct Agent（如果可用）
        if LANGCHAIN_AVAILABLE and (self._deepseek_enabled or self._openai_enabled):
            try:
                self._init_react_agent()
                logger.info("✅ LangChain ReAct Agent initialized successfully")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize ReAct Agent: {e}")
                logger.info("🔄 Will fall back to simple AI responses")

    def _init_react_agent(self):
        """初始化 LangChain ReAct Agent"""
        try:
            from langchain_openai import ChatOpenAI

            # 选择 LLM（优先 DeepSeek，次选 OpenAI）
            if self._deepseek_enabled:
                # DeepSeek 通过 OpenAI 兼容接口调用
                llm = ChatOpenAI(
                    model="deepseek-chat",
                    api_key=DEEPSEEK_API_KEY,
                    base_url="https://api.deepseek.com/v1",
                    temperature=0.3,
                    max_tokens=800
                )
                logger.info("🔧 ReAct Agent using DeepSeek")
            else:
                llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=OPENAI_API_KEY,
                    temperature=0.3,
                    max_tokens=800
                )
                logger.info("🔧 ReAct Agent using OpenAI")

            # 收集所有工具
            tools = [get_price, confirm_payment, query_knowledge, check_order_status, send_payment_confirmation]

            # 创建 ReAct prompt
            react_prompt = PromptTemplate.from_template("""You are an intelligent NBA 2K26 customer service assistant with COMPLETE MEMORY of every user's past interactions.

IMPORTANT RULES:
1. If ANYONE mentions "paid", "paid for", "already paid", "payment confirmed", "sent the money", "已付", "已付款" → MUST use confirm_payment tool
2. If user asks about price/cost/wants to know pricing → Use get_price tool
3. If user asks about "my order", "order status", "track order", "where is my order" → Use check_order_status tool
4. If user says "do you know me", "who am I", "remember me" → Review USER HISTORY and summarize their past interactions
5. ALWAYS check the USER HISTORY section for order details BEFORE calling confirm_payment
6. When calling confirm_payment, include ALL relevant service details from the current message AND conversation history
7. Always be concise and friendly, include emojis
8. Messages tagged with [ADMIN] are from the shop owner — use as context but DO NOT address the admin directly
9. When user expresses clear purchase intent ("I want to buy", "let's do it", "order now", "I'll take it", "let's go") → After providing price with get_price, use send_payment_confirmation to send a payment confirmation button to admin
10. When using send_payment_confirmation, you MUST pass the user_id (from USER HISTORY), amount (total price), service_desc, and channel_id (current channel)

PAYMENT CONFIRMATION FLOW (CRITICAL):
When someone says they paid or confirms payment:
Step 1: Review conversation history to find what service they ordered (e.g., "rep grind", "50x", etc.)
Step 2: Call confirm_payment tool with the service description found in history
Step 3: The tool returns the total and a command like: `!confirm-payment @USER <amount> "<service>"`
Step 4: Your Final Answer MUST include this command so the admin can execute it to create the fulfillment channel
Step 5: NEVER say "I can't create channels" or "I don't have ability" — the admin runs the command, not you
Step 6: After using confirm_payment tool, ALWAYS append [ORDER_INFO:service=<service name>,amount=<total price>] to your Final Answer — this triggers the payment confirmation buttons for admin

PURCHASE INTENT FLOW (when user wants to BUY but hasn't paid yet):
Step 1: Use get_price to provide the price
Step 2: If user confirms they want to proceed ("yes", "let's do it", "order now", "I'll take it"), use send_payment_confirmation with user_id, amount, service_desc, and channel_id
Step 3: This sends a message with payment confirmation buttons that admin can click
Step 4: Tell the user the admin will confirm and create their order channel

UNDERSTANDING USER INTENT:
- "50x + lvl40" → User wants to BUY 50x Rep Sleeve + Level 40 combo → Use get_price("50x rep sleeve", "lvl40")
- "50x" alone → User is asking about price → Use get_price("50x rep sleeve", "50x")
- "250 all specialization + 50x" → Combo order → Use get_price or confirm_payment
- "he already paid" / "i sent the money" → Payment confirmation → Check history first, then confirm_payment with service details
- "i want rep grind" → Order intent → get_price("rep grind")
- "how much for 99" → Price query → get_price("99 overall")

DISTINGUISHING CURRENT vs HISTORY ORDERS:
- If user just asked about a service (e.g., "50x"), and then says "paid" → This is a CURRENT order for 50x
- If user asks "status of my order" or "my previous order" → This is about HISTORY, use check_order_status
- If user has multiple past orders in history and says "paid" without specifics → Use the MOST RECENTLY DISCUSSED service

CRITICAL: Before using confirm_payment, review the USER HISTORY for order details (e.g., "50x", "rep grind"). Include those in the Action Input.

Examples:

Example 1 - Payment with history context:
Question: he already paid
Previous history shows user asked about 50x + lvl40
Thought: User mentions payment. History shows they wanted 50x + lvl40 ($25). I'll confirm with that info.
Action: confirm_payment
Action Input: 50x rep sleeve + level 40
Observation: ✅ Payment Confirmed! Order Summary: 50x Rep Sleeve + Level 40 ($25). Total: $25. Admin, run this command to create order channel: !confirm-payment @USER 25 "50x Rep Sleeve + Level 40"
Thought: I now know the final answer.
Final Answer: ✅ Payment confirmed! Total **$25** for 50x Rep Sleeve + Level 40.
Admin, please run this command to create the fulfillment channel:
`!confirm-payment @user 25 "50x Rep Sleeve + Level 40"`
[ORDER_INFO:service=50x Rep Sleeve + Level 40,amount=25]

Example 2 - Admin says they sent money for rep grind:
Question: i sent the money about rep grind
Thought: The admin/user confirms payment for rep grind. I should use confirm_payment.
Action: confirm_payment
Action Input: rep grind
Observation: ✅ Payment Confirmed! Order Summary: Rep Grind ($40). Total: $40. Admin, run this command to create order channel: !confirm-payment @USER 40 "Rep Grind"
Thought: I now know the final answer.
Final Answer: ✅ Payment confirmed for **Rep Grind** — **$40**
Admin, please run this command to create the fulfillment channel:
`!confirm-payment @user 40 "Rep Grind"`
[ORDER_INFO:service=Rep Grind,amount=40]

Example 3 - Combo payment:
Question: he already paid for 250 all specialization + 50x
Thought: User confirms payment for multiple services. Use confirm_payment with all details.
Action: confirm_payment
Action Input: 250 all specialization + 50x
Observation: ✅ Payment Confirmed! Total: $75. Admin, run: !confirm-payment @USER 75 "250 Layers Challenge + All 5 Specialties + 50x Rep Sleeve"
Thought: I now know the final answer.
Final Answer: ✅ Payment confirmed! Total **$75**.
Admin, please run: `!confirm-payment @user 75 "250 all specialization + 50x"`
[ORDER_INFO:service=250 all specialization + 50x,amount=75]

Example 4 - User asks about price:
Question: 50x + lvl40
Thought: User wants 50x Rep Sleeve + Level 40 combo. I should check the price.
Action: get_price
Action Input: 50x rep sleeve lvl40
Observation: 50x Rep Sleeve + Level 40: **$25**
Thought: I now know the final answer.
Final Answer: ✅ **50x Rep Sleeve + Level 40: $25** 🎯 ETA: 10 minutes | Login required. Type 'order' to proceed!

Example 5 - User identity check:
Question: do you know who I am
Thought: User wants to know if I remember them. I should check their history.
Action: check_order_status
Action Input: <user_id from history>
Observation: User has past interactions: asked about 50x rep sleeve, ordered badge service, etc.
Thought: I now know the final answer.
Final Answer: Of course! 🎮 You previously asked about 50x Rep Sleeve and ordered Badge Unlock. How can I help you today?

Example 6 - Purchase intent (user wants to buy):
Question: I want to buy 50x rep sleeve
Thought: User wants to purchase 50x rep sleeve. I should check the price first.
Action: get_price
Action Input: 50x rep sleeve
Observation: 50x Rep Sleeve: **$15**
Thought: I have the price ($15). The user wants to buy. I should send payment confirmation.
Action: send_payment_confirmation
Action Input: user_id=<user_id from history>, amount=15, service_desc="50x Rep Sleeve", channel_id=<current channel_id>
Observation: Sent payment confirmation request for User in #channel.
Thought: I now know the final answer.
Final Answer: ✅ **50x Rep Sleeve: $15** 🎯

I've sent a payment confirmation request! 💳 Please complete the payment, and the admin will confirm and create your order channel shortly.

🔗 G2G Store: https://www.g2g.com/cn/categories/nba-dunk-items?seller=LegendNBA2k

Example 7 - Combo purchase intent:
Question: let's do 250 challenge + all 5 specialties + 50x
Thought: User wants to buy a combo. I should check the total price first.
Action: get_price
Action Input: 250 challenge all 5 specialties 50x
Observation: 250 Layers Challenge: **$40** | All 5 Specialties: **$20** | 50x Rep Sleeve: **$15**
💰 Combo Total: $75
Thought: Total is $75. User confirmed purchase intent ("let's do"). I should send payment confirmation.
Action: send_payment_confirmation
Action Input: user_id=<user_id from history>, amount=75, service_desc="250 Layers Challenge + All 5 Specialties + 50x Rep Sleeve", channel_id=<current channel_id>
Observation: Sent payment confirmation request.
Thought: I now know the final answer.
Final Answer: ✅ **Combo Order: $75** 🎯
• 250 Layers Challenge: $40
• All 5 Specialties: $20
• 50x Rep Sleeve: $15

I've sent the payment confirmation! 💳 Complete payment and the admin will create your order channel.

Available tools:
{tools}

Use the following format:
Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

{chat_history}

Question: {{input}}
Thought:{{agent_scratchpad}}""")

            # 创建 ReAct Agent
            self._react_agent = create_react_agent(llm, tools, react_prompt)
            self._agent_executor = AgentExecutor(
                agent=self._react_agent,
                tools=tools,
                verbose=False,
                handle_parsing_errors=True,
                max_iterations=5
            )

        except Exception as e:
            logger.error(f"❌ ReAct Agent initialization failed: {e}", exc_info=True)
            self._react_agent = None
            self._agent_executor = None

    async def _call_react_agent(self, user_msg: str, channel_id: str, chat_history: List[Dict], user_memory_summary: str = "", user_id: str = "") -> Tuple[str, bool]:
        """
        使用 LangChain ReAct Agent 处理用户消息
        返回: (回复内容, 是否有订单意图)
        """
        if not self._agent_executor:
            return "", False

        try:
            # 构建历史上下文字符串（最近 6 条消息，完整内容）
            history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-6:]])

            # 注入当前用户 ID 和频道 ID（供 send_payment_confirmation 使用）
            if user_id:
                history_str = f"[CURRENT_USER_ID: {user_id}] [CURRENT_CHANNEL_ID: {channel_id}]\n\n{history_str}"

            # 如果有用户完整历史，附加到历史上下文
            if user_memory_summary:
                history_str = f"=== USER'S COMPLETE HISTORY (all channels, all interactions) ===\n{user_memory_summary}\n=== END OF USER HISTORY ===\n\nCurrent conversation:\n{history_str}"

            # 检查是否是支付确认的情景
            is_payment_context = any(
                keyword in user_msg.lower()
                for keyword in ["paid", "payment", "confirmed", "already", "just paid", "已付"]
            )

            logger.info(f"🤖 ReAct Agent processing: {user_msg[:30]}... (payment_context={is_payment_context})")

            # 同步方式运行 agent（在线程池中）
            result = await asyncio.to_thread(
                self._agent_executor.invoke,
                {
                    "input": user_msg,
                    "chat_history": history_str
                }
            )

            reply = result.get("output", "").strip()

            # 检查是否包含订单确认信息
            has_intent = (
                    "[ORDER_INTENT]" in reply or
                    "✅ Payment Confirmed" in reply or
                    is_payment_context
            )

            # 清理输出
            reply = reply.replace("[ORDER_INTENT]", "").strip()

            logger.info(f"✅ ReAct Agent reply: {reply[:50]}... (has_intent={has_intent})")
            return reply, has_intent

        except asyncio.TimeoutError:
            logger.warning("⏱️ ReAct Agent call timeout")
            return "", False
        except Exception as e:
            logger.error(f"❌ ReAct Agent error: {e}", exc_info=True)
            return "", False

    def _quick_reply(self, user_msg: str) -> Optional[Tuple[str, bool]]:
        """
        仅处理极少数固定命令提示，所有自然语言意图交给 AI/ReAct Agent 处理。
        返回: (回复内容, 是否有订单意图) 或 None
        """
        msg_lower = user_msg.lower()

        # 仅保留固定的命令引导提示
        if any(word in msg_lower for word in ["show me pricing", "show pricing", "price list", "all prices"]):
            return "📋 Use **!pricing** to see all prices or **!faq** for common questions!", False

        if any(word in msg_lower for word in ["show me faq", "show faq"]):
            return "❓ Use **!faq** to see frequently asked questions!", False

        # 所有其他消息交给 AI 处理
        return None

    async def chat(self, user_msg: str, channel_id: str, user_id: str = None) -> Tuple[str, bool]:
        """
        智能对话处理流程
        返回: (回复内容, 是否有订单意图)
        user_id: 用户ID，用于加载完整历史记忆
        """
        # ========== 预加载用户完整历史记忆 ==========
        user_memory_summary = ""
        if user_id:
            try:
                user_memory_summary = await context_manager.get_user_memory_summary(user_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load user memory: {e}")

        # ========== 第一步：关键词快速回复 (<500ms) ==========
        quick_result = self._quick_reply(user_msg)
        if quick_result:
            reply, has_intent = quick_result
            # 保存到上下文
            try:
                await context_manager.save_context(channel_id, user_msg, reply)
            except Exception as e:
                logger.warning(f"⚠️ Failed to save context: {e}")
            logger.info(f"⚡ Quick reply: {user_msg[:30]}... -> {reply[:30]}...")
            return reply, has_intent

        # ========== 第二步：ReAct Agent 处理（如果可用）==========
        # 优先尝试使用 LangChain ReAct Agent 处理复杂意图
        if self._agent_executor:
            try:
                history = await context_manager.get_context(channel_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to get context: {e}")
                history = []

            react_reply, react_intent = await self._call_react_agent(user_msg, channel_id, history, user_memory_summary=user_memory_summary, user_id=user_id)
            if react_reply:  # ReAct Agent 成功处理
                try:
                    await context_manager.save_context(channel_id, user_msg, react_reply)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save context: {e}")
                logger.info(f"✅ ReAct Agent handled: {user_msg[:30]}... -> {react_reply[:40]}...")
                return react_reply, react_intent

        # ========== 第三步：AI 处理 (<2s) ==========
        if not self._use_ai:
            default_reply = "I'm not sure. You can ask about prices (rep, 99, pass, mt, vc) or type !help"
            try:
                await context_manager.save_context(channel_id, user_msg, default_reply)
            except Exception as e:
                logger.warning(f"⚠️ Failed to save context: {e}")
            return default_reply, False

        try:
            # 获取上下文历史
            try:
                history = await context_manager.get_context(channel_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to get context: {e}")
                history = []

            # 系统提示词（基础版本，user_history 在下面动态注入）
            system_prompt = """You are a professional NBA 2K26 boosting service customer support agent.

IMPORTANT RULES:
1. Only answer about NBA 2K26 game services
2. Keep responses short (under 100 words)
3. Include [ORDER_INTENT] ONLY if user explicitly wants to buy/order
4. Use emojis to make it friendly
5. **CLARIFY AMBIGUOUS REQUESTS**: If user says "rep", ask "Do you want Rep Grind (level boost) or Rep Sleeve?"
6. **PAYMENT CONFIRMATION**: If user mentions "paid", "already paid", "sent the money", "payment confirmed", "已付" → Acknowledge payment warmly, summarize the order (check history for what service was discussed), and ALWAYS tell the admin to run: `!confirm-payment @user <amount> "<service>"`. NEVER say "I can't create channels". Add [ORDER_INTENT].
7. **CHECK HISTORY**: Review the USER HISTORY below AND the conversation history for relevant context (order details, previous questions, admin messages, etc.)
8. **ADMIN MESSAGES**: Messages tagged with [ADMIN] are from the shop owner — they provide supplementary context (e.g., confirming payment, clarifying process). Use this info to improve your response to the customer, but NEVER address or reply to the admin.
9. **DISTINGUISH HISTORY VS CURRENT**: If the user's history shows previous orders, and they mention payment NOW, they are likely paying for a CURRENT order (the one most recently discussed). If they ask about order STATUS or "my order", check their history for all past orders and list them.
10. **REMEMBER USER**: If the user has history, acknowledge it. If they say "do you know me" or "who am I", summarize their past interactions (services asked about, orders placed, etc.)

WHEN USER SAYS NUMBER + "x" (e.g., "50x", "100x", "300x"):
- This refers to Rep Sleeve quantities from G2G
- 50x Rep Sleeve: $15
- 100x Rep Sleeve: $21.50
- 300x Rep Sleeve: $30
- Provide the price immediately with order option

WHEN USER IS UNCLEAR:
- "rep" → Show BOTH: Rep Grind $35-150 AND Rep Sleeve $15-30, then ask "Which one?"
- "service" → Ask "What service? (rep grind, 99 overall, mt coins, badges, etc.)"
- "i want Nx" or "how much is Nx" → Show that Rep Sleeve price for N repetitions

Services & Prices:
- Rep Grind: $15-150 (Rookie 1-5 to Legend grinds)
- Rep Sleeve: $15-30 (50x-300x from G2G) - Numbers like 50x, 100x, 300x are quantities
- 99 Overall: $15
- Challenges: $10-40
- Badges: $15
- MT Coins: $10-80

Examples:
- "50x" or "i want 50x" or "how much is 50x" → "✅ **50x Rep Sleeve: $15**"
- "100x" → "✅ **100x Rep Sleeve: $21.50**"
- "rep" → "Do you want Rep Grind (level $35-150) or Rep Sleeve ($15-30)?"
- "I want rep grind to starter 3" → YES [ORDER_INTENT]
- "What's your pricing?" → NO [ORDER_INTENT] - show price list"""

            # ========== 注入用户完整历史到 system prompt ==========
            if user_memory_summary:
                system_prompt += f"\n\n---\nUSER'S COMPLETE HISTORY (all channels, all interactions — use this to remember the user, understand context, and distinguish current vs past orders):\n{user_memory_summary}\n---\n"

            # 构建消息链
            messages = [{"role": "system", "content": system_prompt}]

            # 添加历史消息（最多 6 条）
            for msg in history[-6:]:
                try:
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to add message to history: {e}")

            messages.append({"role": "user", "content": user_msg})

            # ========== 知识库查询（RAG）==========
            # 优先使用 RAG Agent，如果不可用则使用简单的关键词匹配
            knowledge_context = ""
            try:
                if self._rag_agent:
                    # 使用 RAG Agent 检索相关信息
                    logger.info(f"🔍 RAG retrieval for: {user_msg[:30]}...")
                    try:
                        # 调用 RAG 检索（不使用 think_and_act，只是检索）
                        docs = self._rag_agent.retriever.invoke(user_msg)
                        if docs:
                            retrieved_content = "\n\n".join([doc.page_content for doc in docs[:3]])
                            knowledge_context = f"\n\n---\nRELEVANT KNOWLEDGE BASE INFO:\n{retrieved_content}"
                            logger.info(f"📚 RAG retrieved {len(docs)} relevant documents")
                    except Exception as e:
                        logger.warning(f"⚠️ RAG retrieval failed: {e}")
                        knowledge_context = ""
                else:
                    # 回退：简单的知识库检索（读取 pricing 文件并按关键词匹配）
                    logger.info(f"📄 Fallback: using simple knowledge base query for: {user_msg[:30]}...")
                    knowledge_file = "./knowledge/NBA2K26_PRICING_STANDARD.md"
                    if os.path.exists(knowledge_file):
                        with open(knowledge_file, "r", encoding="utf-8") as f:
                            knowledge_content = f.read()

                        # 关键词匹配：提取相关的知识库内容
                        user_msg_lower = user_msg.lower()
                        relevant_sections = []

                        # 匹配 "50x", "100x", "300x" 等规格
                        if any(x in user_msg_lower for x in ["50x", "100x", "300x", "sleeve"]):
                            sleeve_match = knowledge_content[knowledge_content.find("## 👕 REP SLEEVE"):knowledge_content.find("## 💰 OTHER SERVICES")]
                            if sleeve_match:
                                relevant_sections.append(sleeve_match)

                        # 匹配 "grind", "rep", "rookie", "starter" 等等级
                        if any(x in user_msg_lower for x in ["grind", "rookie", "starter", "veteran", "legend"]):
                            grind_match = knowledge_content[knowledge_content.find("## 👑 REPUTATION RANK GRINDS"):knowledge_content.find("## 💎 FINISHED ACCOUNTS")]
                            if grind_match:
                                relevant_sections.append(grind_match)

                        # 匹配 "challenge", "99", "badge" 等服务
                        if any(x in user_msg_lower for x in ["challenge", "99", "badge", "overall"]):
                            other_match = knowledge_content[knowledge_content.find("## 🌟 OVERALL"):knowledge_content.find("## 🔥 HOT DEALS")]
                            if other_match:
                                relevant_sections.append(other_match)

                        if relevant_sections:
                            knowledge_context = "\n\n---\nRELEVANT PRICING INFO:\n" + "\n".join(relevant_sections)
                            logger.info(f"📚 Simple query matched {len(relevant_sections)} sections")

                # 将知识库信息添加到系统提示词
                if knowledge_context:
                    system_prompt += knowledge_context

            except Exception as e:
                logger.warning(f"⚠️ Knowledge base query failed: {e}")

            # 重新构建消息链（包含更新的系统提示词）
            messages = [{"role": "system", "content": system_prompt}]
            for msg in history[-3:]:
                try:
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to add message to history: {e}")
            messages.append({"role": "user", "content": user_msg})

            # ========== AI 调用（异步，不阻塞事件循环） ==========
            ai_reply = ""
            has_order_intent = False

            if self._deepseek_enabled:
                logger.info(f"🔄 Calling DeepSeek for: {user_msg[:30]}...")
                ai_reply, has_order_intent = await self._call_deepseek(messages)
            elif self._openai_enabled:
                logger.info(f"🔄 Calling OpenAI for: {user_msg[:30]}...")
                ai_reply, has_order_intent = await self._call_openai(messages)
            else:
                ai_reply = "AI services not available. Type !pricing for prices or !help for commands."

            # 保存到上下文（即使 AI 调用失败也要保存）
            if ai_reply:
                try:
                    await context_manager.save_context(channel_id, user_msg, ai_reply)
                    logger.info(f"✅ AI reply: {user_msg[:30]}... -> {ai_reply[:30]}...")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save AI response: {e}")
                return ai_reply, has_order_intent
            else:
                # AI 调用失败，返回友好的默认消息
                fallback_reply = "I'm temporarily busy. Try again or ask about pricing (rep, 99, pass, mt)!"
                logger.warning(f"⚠️ AI call returned empty, using fallback reply")
                return fallback_reply, False

        except Exception as e:
            logger.error(f"❌ Unexpected error in chat: {e}", exc_info=True)
            return "Sorry, I'm having trouble. Try again or type !help", False

    async def _call_openai(self, messages: List[Dict]) -> Tuple[str, bool]:
        """调用 OpenAI API（异步）"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 300
                }

                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data["choices"][0]["message"]["content"].strip()
                        has_intent = "[ORDER_INTENT]" in reply
                        reply = reply.replace("[ORDER_INTENT]", "").strip()
                        return reply, has_intent
                    else:
                        logger.error(f"OpenAI API error: {resp.status}")
                        return "", False

        except asyncio.TimeoutError:
            logger.warning("OpenAI call timeout")
            return "", False
        except Exception as e:
            logger.error(f"OpenAI call failed: {e}")
            return "", False

    async def _call_deepseek(self, messages: List[Dict]) -> Tuple[str, bool]:
        """调用 DeepSeek API（异步）"""
        if not DEEPSEEK_API_KEY:
            logger.warning("⚠️ DeepSeek API key not configured")
            return "", False

        try:
            # 创建 HTTP 客户端会话
            async with aiohttp.ClientSession() as session:
                url = "https://api.deepseek.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 400
                }

                logger.debug(f"📤 Sending to DeepSeek: {len(messages)} messages")

                # 设置 15 秒超时（连接 + 读取）
                timeout = aiohttp.ClientTimeout(total=15, connect=5, sock_read=10)

                async with session.post(url, json=payload, headers=headers, timeout=timeout) as resp:
                    logger.debug(f"📥 DeepSeek response status: {resp.status}")

                    if resp.status == 200:
                        data = await resp.json()

                        # 安全提取回复内容
                        if "choices" not in data or not data["choices"]:
                            logger.error(f"❌ Invalid DeepSeek response: {data}")
                            return "", False

                        reply = data["choices"][0]["message"]["content"].strip()
                        if not reply:
                            logger.warning("⚠️ DeepSeek returned empty content")
                            return "", False

                        has_intent = "[ORDER_INTENT]" in reply
                        reply = reply.replace("[ORDER_INTENT]", "").strip()

                        logger.info(f"✅ DeepSeek reply ({len(reply)} chars): {reply[:50]}...")
                        return reply, has_intent
                    else:
                        body = await resp.text()
                        logger.error(f"❌ DeepSeek API error {resp.status}: {body[:200]}")
                        return "", False

        except asyncio.TimeoutError:
            logger.warning("⏱️ DeepSeek call timeout (>15s)")
            return "", False
        except aiohttp.ClientError as e:
            logger.error(f"❌ DeepSeek network error: {e}")
            return "", False
        except Exception as e:
            logger.error(f"❌ DeepSeek call failed: {e}", exc_info=True)
            return "", False

# AI 服务单例
ai_service = AIService()

# ====================== 第四层：高并发控制 + 限流 ======================
# 并发信号量：限制最大同时处理的请求
concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# 用户限流缓存：(user_id -> last_request_time)
user_rate_limit: Dict[int, float] = {}

def check_rate_limit(user_id: int) -> bool:
    """检查用户是否超出限流，返回 True 表示允许通过"""
    now = time.time()
    last_request = user_rate_limit.get(user_id, 0)
    if now - last_request < USER_RATE_LIMIT_SECONDS:
        return False
    user_rate_limit[user_id] = now
    return True

# ====================== 订单管理组件（Discord UI + 持久化）======================
class OrderControlView(discord.ui.View):
    """
    订单控制面板 — 带按钮的可视化订单卡片
    按钮永久有效（timeout=None），管理员可随时更新订单状态
    """
    def __init__(self, order_id: str):
        super().__init__(timeout=None)
        self.order_id = order_id

    @discord.ui.button(label="✅ Mark In Progress", style=discord.ButtonStyle.blurple, custom_id="order_start")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can update order status.", ephemeral=True)
            return
        if order_db:
            order_db.update_order_status(self.order_id, "in_progress")
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.blurple()
        # 更新状态字段
        for field in embed.fields:
            if field.name == "Status":
                embed.set_field_at(0, name="Status", value="🔵 In Progress", inline=True)
                break
        await interaction.response.edit_message(content=f"🔄 Order `{self.order_id}` marked as **In Progress**", embed=embed)
        logger.info(f"📦 Order {self.order_id} status → in_progress (by {interaction.user.name})")

    @discord.ui.button(label="✅ Mark Completed", style=discord.ButtonStyle.green, custom_id="order_complete")
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can update order status.", ephemeral=True)
            return
        if order_db:
            order_db.update_order_status(self.order_id, "completed")
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        for field in embed.fields:
            if field.name == "Status":
                embed.set_field_at(0, name="Status", value="✅ Completed", inline=True)
                break
        await interaction.response.edit_message(content=f"✅ Order `{self.order_id}` marked as **Completed**", embed=embed)
        logger.info(f"📦 Order {self.order_id} status → completed (by {interaction.user.name})")

    @discord.ui.button(label="❌ Cancel Order", style=discord.ButtonStyle.red, custom_id="order_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can update order status.", ephemeral=True)
            return
        if order_db:
            order_db.update_order_status(self.order_id, "cancelled")
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        for field in embed.fields:
            if field.name == "Status":
                embed.set_field_at(0, name="Status", value="❌ Cancelled", inline=True)
                break
        await interaction.response.edit_message(content=f"❌ Order `{self.order_id}` has been **Cancelled**", embed=embed)
        logger.info(f"📦 Order {self.order_id} status → cancelled (by {interaction.user.name})")


async def create_order_from_confirmation(
    guild: discord.Guild,
    customer_id: int,
    amount: float,
    service_desc: str,
    admin: discord.Member,
    consulting_channel: discord.TextChannel
) -> Optional[Tuple[str, discord.TextChannel, discord.Member]]:
    """
    从支付确认创建订单的统一函数
    供 PaymentConfirmView 按钮和 !confirm-payment 命令共用
    返回: (order_id, fulfillment_channel, customer) 或 None
    """
    try:
        # ========== 1. 生成订单号 ==========
        if order_db:
            order_id = order_db.generate_order_id()
        else:
            order_id = f"ORD-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # ========== 2. 获取客户对象 ==========
        customer = guild.get_member(customer_id)
        if not customer:
            logger.error(f"❌ Customer not found: {customer_id}")
            return None

        # ========== 3. 保存订单到数据库 ==========
        if order_db:
            try:
                order_db.save_order_with_details(
                    order_id=order_id,
                    handler_userid=str(customer.id),
                    amount=amount,
                    service_desc=service_desc,
                    confirmed_by=str(admin.id),
                    consulting_channel_id=str(consulting_channel.id)
                )
                logger.info(f"💾 Order {order_id} saved to database")
            except Exception as e:
                logger.warning(f"⚠️ Failed to save order: {e}")

        # ========== 4. 创建履约频道 ==========
        fulfillment_channel_name = f"fulfillment-{order_id.lower()}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            customer: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            )
        }
        if admin.id != guild.owner_id:
            overwrites[admin] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            )
        booster_role = discord.utils.get(guild.roles, name="Booster")
        if booster_role:
            overwrites[booster_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        fulfillment_channel = await guild.create_text_channel(
            name=fulfillment_channel_name,
            overwrites=overwrites,
            topic=f"Order: {order_id} | User: {customer.name} | Amount: ${amount} | Status: In Progress"
        )
        logger.info(f"✅ Fulfillment channel created: {fulfillment_channel_name}")

        # ========== 5. 更新订单频道信息 ==========
        if order_db:
            order_db.update_order_channel(order_id, str(fulfillment_channel.id), fulfillment_channel_name)

        # ========== 6. 发送订单卡片（履约频道）==========
        order_embed = discord.Embed(
            title="📦 Order Details",
            description=f"Welcome {customer.mention}! Your service has been confirmed.",
            color=discord.Color.gold()
        )
        order_embed.add_field(name="Order ID", value=f"`{order_id}`", inline=True)
        order_embed.add_field(name="Status", value="🟡 Pending", inline=True)
        order_embed.add_field(name="Service", value=service_desc, inline=False)
        order_embed.add_field(name="Amount", value=f"${amount:.2f}", inline=True)
        order_embed.add_field(name="Customer", value=customer.mention, inline=True)
        order_embed.add_field(name="Confirmed By", value=admin.mention, inline=True)
        order_embed.add_field(
            name="Info",
            value=f"📝 Consulting Channel: {consulting_channel.mention}\n⏱️ Service starts within 10 minutes",
            inline=False
        )
        order_embed.timestamp = discord.utils.utcnow()
        order_embed.set_footer(text="Use the buttons below to update order status")
        order_control_view = OrderControlView(order_id)
        await fulfillment_channel.send(embed=order_embed, view=order_control_view)

        # ========== 7. 迁移咨询频道历史 ==========
        try:
            await migrate_history(consulting_channel, fulfillment_channel, limit=20)
        except Exception as e:
            logger.warning(f"⚠️ Failed to migrate history: {e}")

        # ========== 8. 在履约频道通知客户 ==========
        await fulfillment_channel.send(
            f"🚀 {customer.mention} 您的服务已确认！打手将在 10 分钟内开始。"
        )

        # ========== 9. 订单看板同步 ==========
        board_channel = discord.utils.get(guild.text_channels, name="order-board")
        if board_channel:
            try:
                board_embed = discord.Embed(
                    title=f"📦 {order_id}",
                    description=f"Service: {service_desc}",
                    color=discord.Color.gold()
                )
                board_embed.add_field(name="Customer", value=customer.mention, inline=True)
                board_embed.add_field(name="Amount", value=f"${amount:.2f}", inline=True)
                board_embed.add_field(name="Status", value="🟡 Pending", inline=True)
                board_embed.add_field(name="Confirmed By", value=admin.mention, inline=True)
                board_embed.add_field(name="Fulfillment", value=fulfillment_channel.mention, inline=True)
                board_embed.timestamp = discord.utils.utcnow()
                board_view = OrderControlView(order_id)
                board_msg = await board_channel.send(embed=board_embed, view=board_view)
                # 记录看板消息 ID，用于后续同步更新
                if order_db:
                    order_db.save_board_message(order_id, str(board_msg.id), str(board_channel.id))
                logger.info(f"📊 Order {order_id} posted to order-board")
            except Exception as e:
                logger.warning(f"⚠️ Failed to post to order board: {e}")

        # ========== 10. 在咨询频道通知 ==========
        try:
            await consulting_channel.send(
                f"✅ **Order created!**\n"
                f"📋 Order ID: `{order_id}`\n"
                f"📢 Fulfillment channel: {fulfillment_channel.mention}\n"
                f"📌 {customer.mention} — Please move to the fulfillment channel"
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to notify consulting channel: {e}")

        return (order_id, fulfillment_channel, customer)

    except Exception as e:
        logger.error(f"❌ Error in create_order_from_confirmation: {e}", exc_info=True)
        return None


class PaymentConfirmView(discord.ui.View):
    """
    收款确认面板 — 管理员在咨询频道中一键确认/拒绝收款
    管理员点击按钮后：
    - ✅ 已收款：自动创建履约频道、保存订单、拉人
    - ❌ 未到账：通知买家检查转账状态
    """
    def __init__(self, customer_id: int, service_desc: str, amount: float):
        super().__init__(timeout=7200)  # 2小时超时
        self.customer_id = customer_id
        self.service_desc = service_desc
        self.amount = amount

    @discord.ui.button(label="✅ 已收款 — 创建订单", style=discord.ButtonStyle.green, custom_id="payment_received")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 仅管理员可操作", ephemeral=True)
            return

        # 禁用所有按钮
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"⏳ 正在创建订单...",
            view=self
        )

        try:
            consulting_channel = interaction.channel
            result = await create_order_from_confirmation(
                guild=interaction.guild,
                customer_id=self.customer_id,
                amount=self.amount,
                service_desc=self.service_desc,
                admin=interaction.user,
                consulting_channel=consulting_channel
            )
            if result:
                order_id, fulfillment_channel, customer = result
                await interaction.followup.send(
                    f"✅ **订单已创建！**\n"
                    f"📋 订单号: `{order_id}`\n"
                    f"💰 金额: ${self.amount:.2f}\n"
                    f"🎮 服务: {self.service_desc}\n"
                    f"📢 履约频道: {fulfillment_channel.mention}\n"
                    f"📌 {customer.mention} — 请前往履约频道"
                )
            else:
                await interaction.followup.send("❌ 创建订单失败，请查看日志", ephemeral=True)
        except Exception as e:
            logger.error(f"❌ Error creating order from button: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 创建订单失败: {str(e)[:100]}")

    @discord.ui.button(label="❌ 未到账 — 通知买家", style=discord.ButtonStyle.red, custom_id="payment_not_received")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 仅管理员可操作", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="❌ **支付未确认** — 已通知买家检查转账状态",
            view=self
        )

        customer = interaction.guild.get_member(self.customer_id)
        if customer:
            try:
                msg = (
                    f"⚠️ {customer.mention} 管理员尚未收到您的付款。\n"
                    f"请检查以下内容：\n"
                    f"1. 💰 PayPal/G2G 订单是否已完成\n"
                    f"2. 📸 请提供付款截图发送给管理员\n"
                    f"3. 💬 如有问题请联系管理员 {interaction.user.mention}\n\n"
                    f"服务: **{self.service_desc}** | 金额: **${self.amount:.2f}**"
                )
                await interaction.channel.send(msg)
            except Exception as e:
                logger.warning(f"⚠️ Failed to notify customer: {e}")



def _extract_order_info_from_reply(reply: str) -> Optional[Dict]:
    """
    从 AI 回复中提取 [ORDER_INFO:service=...,amount=...] 标记
    返回 {"service": "...", "amount": ...} 或 None
    """
    match = re.search(r'\[ORDER_INFO:\s*(.+?)\s*\]', reply)
    if not match:
        return None
    try:
        info_str = match.group(1)
        # 解析 key=value 形式
        info = {}
        for pair in info_str.split(','):
            if '=' in pair:
                k, v = pair.strip().split('=', 1)
                k = k.strip().strip("'\"")
                v = v.strip().strip("'\"")
                try:
                    v = float(v) if '.' in v else int(v)
                except ValueError:
                    pass
                info[k] = v
        if 'service' in info and 'amount' in info:
            return info
    except Exception:
        pass
    return None


async def _send_payment_buttons(channel: discord.TextChannel, customer_id: int, service: str, amount: float):
    """发送收款确认按钮消息（仅管理员可操作）"""
    view = PaymentConfirmView(
        customer_id=customer_id,
        service_desc=service,
        amount=amount
    )
    embed = discord.Embed(
        title="💳 待确认收款",
        description=f"管理员请确认是否已收到以下订单的款项：",
        color=discord.Color.orange()
    )
    embed.add_field(name="服务", value=service, inline=False)
    embed.add_field(name="金额", value=f"${amount:.2f}", inline=True)
    embed.set_footer(text="⏰ 按钮将在 2 小时后失效 | 仅管理员可操作")
    await channel.send(embed=embed, view=view)


async def migrate_history(source: discord.TextChannel, target: discord.TextChannel, limit: int = 20):
    """
    将咨询频道的最近消息迁移到履约频道，方便打手了解上下文
    只迁移非 bot 的消息，从旧到新排列
    """
    messages = []
    async for msg in source.history(limit=limit):
        if msg.author.bot:
            continue
        messages.append(msg)

    if not messages:
        await target.send("📜 No previous discussion found.")
        return

    # 倒序（从旧到新）
    messages.reverse()
    header = await target.send("📋 **--- Previous Discussion ---**")
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        content = msg.content if msg.content else "[Attachment/Embed]"
        if len(content) > 300:
            content = content[:300] + "..."
        author_name = msg.author.display_name
        # 标记管理员消息
        is_admin = msg.author.id in ADMIN_USER_IDS
        prefix = "👤 Admin" if is_admin else f"💬 {author_name}"
        try:
            await target.send(f"**{prefix}** ({timestamp}): {content}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to migrate message: {e}")
    await target.send("📋 **--- End of Previous Discussion ---**")
    logger.info(f"📜 Migrated {len(messages)} messages from #{source.name} to #{target.name}")


# ====================== 第五层：Discord Bot 核心 =======================
def create_bot() -> commands.Bot:
    """创建并配置 Discord Bot"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    # 配置代理（支持中国网络）
    connector = None
    if HTTP_PROXY:
        try:
            connector = ProxyConnector.from_url(HTTP_PROXY)
            logger.info(f"🌐 Proxy configured: {HTTP_PROXY}")
        except Exception as e:
            logger.warning(f"⚠️ Proxy config failed: {e}")

    bot = commands.Bot(
        command_prefix="!",
        intents=intents,
        connector=connector,
        help_command=None
    )

    # ====================== Bot 事件监听 ======================
    # 已处理消息集合（防止 Discord 重发/编辑导致重复处理）
    _processed_message_ids = set()
    _processed_max_size = 5000  # 最多保留 5000 个消息 ID

    @bot.event
    async def on_ready():
        global _bot_cache
        _bot_cache = list(bot.guilds)
        logger.info(f"✅ Bot logged in as {bot.user}")
        logger.info(f"📊 Connected to {len(bot.guilds)} server(s)")
        activity = discord.Game(name="NBA 2K26 Boosting | !help")
        await bot.change_presence(activity=activity)
        # 尝试自动创建 order-board 频道（如果不存在）
        for guild in bot.guilds:
            board_exists = discord.utils.get(guild.text_channels, name="order-board")
            if not board_exists:
                try:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True)
                    }
                    # 给管理员角色发消息权限
                    for role in guild.roles:
                        if role.permissions.administrator:
                            overwrites[role] = discord.PermissionOverwrite(
                                view_channel=True, send_messages=False, read_message_history=True
                            )
                    await guild.create_text_channel(
                        name="order-board",
                        overwrites=overwrites,
                        topic="📊 Order Dashboard — All orders are tracked here automatically"
                    )
                    logger.info(f"📊 Created #order-board channel in {guild.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to create order-board: {e}")

    @bot.event
    async def on_message(message: discord.Message):
        """处理所有消息 — 全量记录用户记忆 + 去重"""
        # 过滤机器人自己的消息
        if message.author.bot:
            return

        # ========== 消息去重 ==========
        if message.id in _processed_message_ids:
            return
        _processed_message_ids.add(message.id)
        # 限制集合大小
        if len(_processed_message_ids) > _processed_max_size:
            # 移除最旧的一半
            to_remove = list(_processed_message_ids)[:_processed_max_size // 2]
            for mid in to_remove:
                _processed_message_ids.discard(mid)

        # 处理所有命令（!help, !pricing 等）
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        # ========== 身份识别：管理员 vs 客户 ==========
        is_admin = message.author.id in ADMIN_USER_IDS
        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        channel_name = message.channel.name
        author_name = message.author.name
        msg_content = message.content.strip()

        # ========== 全量用户记忆记录（不区分管理员/客户，所有消息都记录）==========
        # 记录发送者的消息到自己的记忆
        try:
            await context_manager.add_user_memory(
                user_id=user_id,
                role="admin" if is_admin else "user",
                content=msg_content,
                author_name=author_name,
                channel_id=channel_id,
                channel_name=channel_name
            )
        except Exception as e:
            logger.warning(f"⚠️ Failed to save user memory: {e}")

        # ========== 管理员消息处理 ==========
        # 管理员 @ bot 时正常回复；普通消息只记录到上下文，不触发 AI
        if is_admin:
            # 检查是否 @ 了 bot — 如果是，正常处理（让管理员也能测试 bot）
            if bot.user in message.mentions:
                logger.info(f"👔 Admin @{message.author.name} mentioned bot, processing normally")
                # 继续走下面的客户消息处理流程
            else:
                # 管理员消息已记录到用户记忆，同时记录到频道上下文
                if msg_content:
                    try:
                        await context_manager.save_context(
                            channel_id,
                            f"[Admin: {author_name}] {msg_content}",
                            ""  # 空回复，不产生 bot 回复
                        )
                        logger.info(f"👤 Admin message recorded: @{author_name}: {msg_content[:50]}...")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save admin context: {e}")
                return

        # ========== 以下是客户消息处理 ==========

        # ========== 消息过滤逻辑（简洁，不依赖正则） ==========
        # 触发条件（满足任一即可）：
        # 1. 消息提到了 Bot
        # 2. 在 order- 前缀的频道
        # 3. 在包含 service/bot/support/nba2k/ticket 的频道

        has_mention = bot.user in message.mentions
        is_order_channel = "order-" in message.channel.name.lower()
        is_service_channel = any(
            keyword in message.channel.name.lower()
            for keyword in ["service", "bot", "support", "nba2k", "ticket", "help", "legend"]
        )

        if not (has_mention or is_order_channel or is_service_channel):
            logger.debug(f"⊘ Ignoring message in {message.channel.name}: {message.content[:30]}")
            return

        # 限流检查
        if not check_rate_limit(message.author.id):
            try:
                await message.reply("⚠️ Please slow down! Try again in a moment.", delete_after=3)
            except Exception as e:
                logger.warning(f"⚠️ Failed to send rate limit message: {e}")
            return

        logger.info(f"✅ Message accepted: @{message.author.name} in #{message.channel.name}")
        logger.info(f"📌 Message ID: {message.id} | Content: '{message.content}'")

        # ========== 高并发控制：信号量隔离 ==========
        async with concurrency_semaphore:
            await handle_message(message)

    # ====================== 核心消息处理逻辑 ======================
    async def handle_message(message: discord.Message):
        """
        处理用户消息的核心逻辑
        1. 立即响应（防止 Discord 3s 超时）
        2. 异步处理 AI（不阻塞事件循环）
        3. 记录 bot 回复到用户记忆
        """
        channel = message.channel
        user_msg = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        channel_id = str(channel.id)
        user_id = str(message.author.id)
        author_name = message.author.name
        channel_name = channel.name

        logger.info(f"🔄 [handle_message START] MsgID: {message.id} | User: {message.author.name} | Channel: {channel.name} | Content: '{user_msg[:50]}'")

        # ========== 第一步：立即响应 ==========
        # 防止 Discord "Interaction failed" 超时
        status_msg = await channel.send("🔍 Processing your request...")

        try:
            # ========== 第二步：异步处理（传入 user_id 以加载用户历史）==========
            ai_reply, has_order_intent = await ai_service.chat(user_msg, channel_id, user_id=user_id)

            # ========== 第二步补充：记录 bot 回复到用户记忆 ==========
            if ai_reply:
                try:
                    await context_manager.add_user_memory(
                        user_id=user_id,
                        role="assistant",
                        content=ai_reply,
                        author_name="Legend's Agent",
                        channel_id=channel_id,
                        channel_name=channel_name
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save bot reply to user memory: {e}")

            # ========== 第三步：检查订单意图 ==========
            # ⚠️  重要: 不能自动创建订单，需要管理员确认支付后才创建
            # 流程: 用户表达意图 → Bot 显示价格 + 支付信息 → 管理员确认支付 → 创建订单

            user_msg_lower = user_msg.lower()
            explicit_order_keywords = ["order", "buy", "购买", "下单", "start order", "create order", "新建订单"]
            has_explicit_order_request = any(keyword in user_msg_lower for keyword in explicit_order_keywords)

            # 检查是否有订单意图（仅用于识别，不创建订单）
            # 使用词边界匹配避免 "pass" 误匹配 "password"
            has_purchase_intent = (
                    has_explicit_order_request or
                    (has_order_intent and any(re.search(r'\b' + re.escape(kw) + r'\b', user_msg_lower) for kw in ["rep", "99", "pass", "mt", "vc", "service", "boost"]))
            )

            if has_purchase_intent:
                logger.info(f"📦 Purchase intent detected: explicit={has_explicit_order_request}, ai_intent={has_order_intent}")

                # 添加订单信息到 AI 回复
                order_notice = "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n💳 **To proceed with your order:**\n1. Review the price above\n2. 🔗 Check our G2G store: https://www.g2g.com/cn/categories/nba-dunk-items?seller=LegendNBA2k\n3. Choose payment method (Crypto/PayPal/Bank)\n4. Contact admin to confirm payment\n5. Admin will create your order channel\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                ai_reply = ai_reply + order_notice if ai_reply else order_notice
                logger.info(f"📝 Added order notice to AI reply (awaiting payment confirmation)")

                # ⚠️  不自动创建订单，等待管理员确认

            # ========== 第四步：检查 [ORDER_INFO] 标记 → 发送收款确认按钮 ==========
            order_info = _extract_order_info_from_reply(ai_reply)
            if order_info:
                # 从 AI 回复中移除 [ORDER_INFO] 标记（不显示给用户）
                ai_reply = re.sub(r'\[ORDER_INFO:\s*.+?\s*\]', '', ai_reply).strip()
                logger.info(f"💳 ORDER_INFO detected: service={order_info['service']}, amount={order_info['amount']}")
                try:
                    await _send_payment_buttons(
                        channel=channel,
                        customer_id=int(user_id),
                        service=str(order_info['service']),
                        amount=float(order_info['amount'])
                    )
                    logger.info(f"✅ Payment confirmation buttons sent for {order_info['service']}")
                except Exception as e:
                    logger.error(f"❌ Failed to send payment buttons: {e}")

            # ========== 第五步：返回 AI 回复 ==========
            # 注意：ai_reply 可能已包含订单说明，确保不重复分割
            logger.info(f"📤 Sending reply ({len(ai_reply)} chars): {ai_reply[:50]}...")

            # 分割长消息（Discord 限制 2000 字符）
            if len(ai_reply) > 1900:
                # 按照 1900 字符分割，避免消息重复
                chunks = []
                remaining = ai_reply
                while remaining:
                    chunk = remaining[:1900]
                    chunks.append(chunk)
                    remaining = remaining[1900:]

                logger.info(f"📊 Splitting into {len(chunks)} messages")
                await status_msg.edit(content=chunks[0])

                for i, chunk in enumerate(chunks[1:], 1):
                    await asyncio.sleep(0.3)
                    await channel.send(chunk)
                    logger.info(f"📤 Sent chunk {i+1}/{len(chunks)}")
            else:
                await status_msg.edit(content=ai_reply)

            logger.info(f"✅ [handle_message END] Reply sent successfully (total chars: {len(ai_reply)}) | MsgID: {message.id}")

        except Exception as e:
            logger.error(f"❌ Error handling message: {e}", exc_info=True)
            await status_msg.edit(content="⚠️ Sorry, something went wrong. Please try again or contact support.")

    # ====================== 订单频道创建 ======================
    async def create_order_channel(guild: discord.Guild, user: discord.User, service_desc: str) -> Optional[discord.TextChannel]:
        """创建订单频道"""
        try:
            # 生成订单编号
            order_id = f"ORD{int(time.time())}"

            # 频道名称规则
            channel_name = f"{order_id}-2k26-{user.name.lower()}-pending"

            # 权限设置：仅用户和管理员可见
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True
                )
            }

            # 创建频道
            order_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Order {order_id} | User: {user.name} | Status: pending"
            )

            # 清空该用户的旧上下文（新订单开始）
            await context_manager.clear_context(str(order_channel.id))

            # 发送欢迎消息
            embed = discord.Embed(
                title=f"📦 Order {order_id} Created",
                description="Your order channel has been created! A representative will contact you shortly.",
                color=discord.Color.green()
            )
            embed.add_field(name="Status", value="⏳ Pending", inline=True)
            embed.add_field(name="Service", value=service_desc[:100], inline=True)
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.set_footer(text="All communications will be in this channel")

            await order_channel.send(content=f"Welcome {user.mention}!", embed=embed)

            logger.info(f"✅ Order channel created: {channel_name}")
            return order_channel

        except Exception as e:
            logger.error(f"❌ Failed to create order channel: {e}")
            return None

    # ====================== 管理命令 ======================
    @bot.command(name="stats")
    async def stats_command(ctx):
        """查看机器人性能统计"""
        embed = discord.Embed(
            title="🤖 Bot Performance Stats",
            color=discord.Color.blue()
        )
        embed.add_field(name="Max Concurrent", value=f"{MAX_CONCURRENT_TASKS} tasks", inline=True)
        embed.add_field(name="AI Engines", value=f"OpenAI={ai_service._openai_enabled}, DeepSeek={ai_service._deepseek_enabled}", inline=True)
        embed.add_field(name="Context Storage", value="SQLite + LRU Memory", inline=True)
        embed.add_field(name="Rate Limit", value=f"{USER_RATE_LIMIT_SECONDS}s per user", inline=True)
        await ctx.send(embed=embed)

    @bot.command(name="pricing")
    async def pricing_command(ctx):
        """显示完整价格表"""
        embed = discord.Embed(
            title="💰 NBA 2K26 Service Pricing",
            description="All prices in USD | 24/7 Support",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="🏀 Rep Leveling",
            value="1-50 Rep: $25\n1-99 Rep: $45\n✅ Hand-played, safe, 24hrs",
            inline=False
        )
        embed.add_field(
            name="🎯 Max 99 Overall",
            value="Complete Rebuild: $30\n✅ Full attributes maxed",
            inline=False
        )
        embed.add_field(
            name="🃏 Season Pass",
            value="Full Completion: $15\n✅ All rewards unlocked",
            inline=False
        )
        embed.add_field(
            name="💰 MT Coins",
            value="100K: $10 | 500K: $45 | 1M: $80\n✅ Safe & instant",
            inline=False
        )
        embed.add_field(
            name="⚡ VC Boosting",
            value="Custom packages available\n💬 Ask for details!",
            inline=False
        )
        embed.set_footer(text="React with ✅ to order or type 'order' in chat")
        await ctx.send(embed=embed)

    @bot.command(name="faq")
    async def faq_command(ctx):
        """显示常见问题"""
        embed = discord.Embed(
            title="❓ Frequently Asked Questions",
            description="Common questions about our services",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="🔒 Is it safe?",
            value="✅ YES! Hand-played services, no ban risk. 100% safe & secure.",
            inline=False
        )
        embed.add_field(
            name="⏱️ How long does it take?",
            value="⚡ Rep Leveling: 24-48 hours\n🎯 99 Overall: 48-72 hours\n🃏 Season Pass: 24 hours",
            inline=False
        )
        embed.add_field(
            name="💳 What payment methods?",
            value="💰 Crypto (preferred) | 💳 Paypal | 🏦 Bank Transfer",
            inline=False
        )
        embed.add_field(
            name="📞 Do you have support?",
            value="✅ 24/7 customer support available in Discord",
            inline=False
        )
        embed.add_field(
            name="🚀 What's included?",
            value="✅ All in-game rewards\n✅ Account security\n✅ Delivery guarantee",
            inline=False
        )
        embed.set_footer(text="Ask @bot for more details or type 'order' to start!")
        await ctx.send(embed=embed)

    @bot.command(name="help")
    async def help_command(ctx):
        """显示帮助"""
        embed = discord.Embed(
            title="🤖 NBA 2K26 Bot Commands",
            description="Complete list of available commands",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📋 User Commands",
            value="!pricing - Show all service prices\n!faq - Frequently asked questions\n!stats - Bot performance stats",
            inline=False
        )
        embed.add_field(
            name="💬 How to Order",
            value="1. Ask about services: `@bot what's the price for rep?`\n2. Tell us your interest: `@bot I want rep service`\n3. Review price & payment methods\n4. Contact admin to confirm payment\n5. Admin creates your order channel",
            inline=False
        )
        embed.add_field(
            name="🔑 Admin Commands",
            value="!createorder @user \"service description\"\n*Example:* `!createorder @Legend2k26 \"Rep Leveling $45\"`\n(After verifying payment, admin runs this to create order channel)",
            inline=False
        )
        embed.set_footer(text="Questions? Just @mention the bot anytime!")
        await ctx.send(embed=embed)

    @bot.command(name="confirm-payment")
    async def confirm_payment_command(ctx, user: discord.User, amount: str, *, project: str = ""):
        """
        财务命令：在咨询频道中确认支付，为客户开通履约频道
        ✅ 在咨询频道中运行

        用法: !confirm-payment @user <amount> <project name>
        例: !confirm-payment @Legend2k26 70 "Rep Grind to Starter 3"
             !confirm-payment @Legend2k26 15 "99 Overall"
        """
        # 检查权限（仅管理员/财务可用）
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ This command is only for administrators/finance!")
            return

        try:
            logger.info(f"💳 {ctx.author.name} confirmed payment for {user.name} | Amount: ${amount} | Project: {project}")

            # 在咨询频道发送确认消息
            embed = discord.Embed(
                title="⏳ Creating order...",
                description=f"Payment confirmed for {user.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Amount", value=f"${amount}", inline=True)
            embed.add_field(name="Service", value=project or "NBA 2K26 Service", inline=False)
            status_msg = await ctx.send(embed=embed)

            # 调用统一的订单创建函数
            result = await create_order_from_confirmation(
                guild=ctx.guild,
                customer_id=user.id,
                amount=float(amount),
                service_desc=project or "NBA 2K26 Service",
                admin=ctx.author,
                consulting_channel=ctx.channel
            )

            if result:
                order_id, fulfillment_channel, _ = result
                # 更新确认消息
                embed.title = "✅ Payment Confirmed!"
                embed.description = f"Order `{order_id}` has been created!"
                embed.add_field(name="Order ID", value=f"`{order_id}`", inline=True)
                embed.add_field(name="Customer", value=user.mention, inline=True)
                embed.add_field(name="Fulfillment", value=fulfillment_channel.mention, inline=True)
                embed.set_footer(text=f"Confirmed by: {ctx.author.name}")
                await status_msg.edit(embed=embed)
            else:
                await ctx.send(f"❌ Failed to create order for {user.name}")

        except Exception as e:
            logger.error(f"❌ Error confirming payment: {e}", exc_info=True)
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @bot.command(name="createorder")
    async def createorder_command(ctx, user: discord.User, *, service_desc: str = "Service"):
        """
        管理员命令：确认支付后创建订单频道
        用法: !createorder @username "service description"
        例: !createorder @Legend2k26 "Rep Leveling $45"
        """
        # 检查权限（仅管理员可用）
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ This command is only for administrators!")
            return

        try:
            logger.info(f"📋 Admin {ctx.author.name} creating order for {user.name}: {service_desc}")

            # 创建订单频道
            order_channel = await create_order_channel(ctx.guild, user, service_desc)

            if order_channel:
                embed = discord.Embed(
                    title="✅ Order Created by Admin",
                    description=f"Payment confirmed for {user.mention}",
                    color=discord.Color.green()
                )
                embed.add_field(name="Service", value=service_desc, inline=False)
                embed.add_field(name="User", value=user.mention, inline=True)
                embed.add_field(name="Channel", value=order_channel.mention, inline=True)
                embed.set_footer(text=f"Created by admin: {ctx.author.name}")

                await ctx.send(embed=embed)
                logger.info(f"✅ Order created successfully for {user.name}")
            else:
                await ctx.send(f"❌ Failed to create order channel for {user.name}")
                logger.error(f"❌ Failed to create order channel")

        except Exception as e:
            logger.error(f"❌ Error creating order: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    return bot

# ====================== 启动入口 ======================
async def main():
    """Bot 启动入口"""
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN not configured!")
        return

    logger.info("🚀 Starting Discord Bot (Final Optimized Version)...")
    bot = create_bot()

    try:
        await bot.start(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown signal received")
        # 关闭前将所有内存缓存的上下文持久化到数据库
        logger.info("💾 Saving all context to database before shutdown...")
        try:
            await context_manager.flush_all()
            logger.info("✅ All context saved to database")
        except Exception as e:
            logger.warning(f"⚠️ Failed to flush context: {e}")
        await bot.close()
    except Exception as e:
        logger.error(f"❌ Bot startup failed: {e}", exc_info=True)
        await bot.close()

if __name__ == "__main__":
    # 检查必要的依赖
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")

