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
import glob
import json
import logging
import os
import re
import sys
import time
from aiohttp import web
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
        logger_setup.warning(
            "⚠️ LangChain not installed. ReAct Agent features disabled. Install with: pip install langchain langchain-openai langchain-community")
# 添加 src/legacy 目录到 Python 路径以导入 RAG Agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "legacy"))

# 导入识图工具
try:
    from image_recognizer import init_image_recognizer

    IMAGE_RECOGNIZER_AVAILABLE = True
except ImportError:
    IMAGE_RECOGNIZER_AVAILABLE = False
    logger_setup = logging.getLogger("DiscordBot")
    logger_setup.warning("⚠️ Image recognizer not available. Install with: pip install pillow pytesseract")

# 导入监控模块
try:
    from monitoring.system_monitor import get_metrics_collector, MetricsCollector
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger_setup = logging.getLogger("DiscordBot")
    logger_setup.warning("⚠️ System monitor not available.")

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
if _ADMIN_IDS_RAW:
    for _aid in _ADMIN_IDS_RAW.split(","):
        _aid = _aid.strip()
        if _aid.isdigit():
            ADMIN_USER_IDS.add(int(_aid))
    logger.info(f"✅ Loaded ADMIN_USER_IDS: {ADMIN_USER_IDS}")
else:
    logger.warning(f"⚠️  admin_user_ids not configured in .env")

# ====================== Web 管理界面配置 ======================
KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge")  # 知识库目录（项目根目录下）
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")  # Web 管理密码
WEB_PORT = 8081  # Web 管理端口

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
        if any(x in service_lower for x in ["50x", "50 x"]) and any(
                x in service_lower for x in ["lvl40", "level 40", "level40", "lv40"]):
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
    def confirm_payment(order_details: str, user_id: str = "") -> str:
        """
        当管理员或用户确认已付款时，解析订单详情并返回汇总。
        返回结果包含金额和具体的 !confirm-payment 命令，供管理员执行。
        参数:
        - order_details: 订单内容描述，如 "rep grind", "50x rep sleeve", "250 all specialization + 50x"
        - user_id: 客户的 Discord 用户 ID（从对话上下文中的 CURRENT_USER_ID 获取）
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
        if any(x in details_lower for x in ["50x", "50 x"]) and any(
                x in details_lower for x in ["lvl40", "level 40", "level40", "lv40"]):
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
            # 使用真实 user_id 生成 mention（如果有的话）
            user_mention = f"<@{user_id}>" if user_id else "@USER"
            summary = (
                    f"✅ **Payment Confirmed!**\n\n"
                    f"**Order Summary:**\n" + "\n".join(f"• {item}" for item in items) +
                    f"\n\n**Total: ${total}**\n\n"
                    f"📋 **Admin, run this command to create order channel:**\n"
                    f"`!confirm-payment {user_mention} {total} \"{service_str}\"`"
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
    def add_knowledge(service_name: str, content: str, target_file: str = "") -> str:
        """
        将内容（如 G2G 链接、产品信息等）添加到知识库文件。
        参数:
        - service_name: 服务名称（如 "Taz Face Custom Build"）
        - content: 要添加的内容（如 G2G 链接、描述等）
        - target_file: 可选的目标文件路径（相对于 knowledge 目录），默认追加到 pricing/g2g-products.md
        """
        try:
            if not target_file:
                target_file = "pricing/g2g-products.md"
            # 确保 target_file 以 .md 结尾
            if not target_file.endswith(".md"):
                target_file += ".md"
            filepath = os.path.join(KNOWLEDGE_DIR, target_file)
            # 自动创建中间目录
            dirpath = os.path.dirname(filepath)
            if dirpath and not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            # 构建要添加的内容
            entry = f"\n## {service_name}\n{content}\n"
            # 如果文件存在，检查是否已经有同名条目
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    existing = f.read()
                if f"## {service_name}" in existing:
                    # 替换已有条目
                    import re
                    pattern = rf"(## {re.escape(service_name)}\n.*?)(?=\n## |\Z)"
                    new_content = re.sub(pattern, entry.strip() + "\n", existing, flags=re.DOTALL)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    return f"✅ Updated existing entry for '{service_name}' in {target_file}"
                else:
                    # 追加到文件末尾
                    with open(filepath, "a", encoding="utf-8") as f:
                        f.write(entry)
                    return f"✅ Added new entry for '{service_name}' to {target_file}"
            else:
                # 创建新文件
                header = f"# G2G Products & Links\n\nAuto-maintained by Legend's Agent.\n\n"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(header + entry)
                return f"✅ Created new file {target_file} and added entry for '{service_name}'"
        except Exception as e:
            return f"❌ Failed to add knowledge: {str(e)}"


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
        logger.info(
            f"AI Services: OpenAI={self._openai_enabled}, DeepSeek={self._deepseek_enabled}, ReAct={LANGCHAIN_AVAILABLE}")

        # 初始化 RAG Agent
        try:
            from rag_agent import RAGAgent
            knowledge_dir = KNOWLEDGE_DIR  # 使用项目根目录下的 knowledge 目录
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
            tools = [get_price, confirm_payment, query_knowledge, add_knowledge, check_order_status, send_payment_confirmation]

            # 创建 ReAct prompt
            react_prompt = PromptTemplate.from_template("""You are an intelligent NBA 2K26 customer service assistant with COMPLETE MEMORY of every user's past interactions.

IMPORTANT RULES:
1. NEVER confirm payment unless someone EXPLICITLY says they already sent money (e.g., "paid", "already paid", "sent the money", "payment confirmed", "已付", "已付款", "I paid", "money sent"). Admin providing a crypto address or payment info is NOT payment confirmation — it means payment hasn't happened yet.
2. If user asks about price/cost/wants to know pricing → Use get_price tool
3. If user asks about "my order", "order status", "track order", "where is my order" → Use check_order_status tool
4. If user says "do you know me", "who am I", "remember me" → Review USER HISTORY and summarize their past interactions
5. ALWAYS check the USER HISTORY section for order details BEFORE calling confirm_payment
6. When calling confirm_payment, include ALL relevant service details from the current message AND conversation history
7. Always be concise and friendly, include emojis
8. Messages tagged with [ADMIN] are from the shop owner — use as context but DO NOT address the admin directly
9. When user expresses clear purchase intent ("I want to buy", "let's do it", "order now", "I'll take it", "let's go") → After providing price with get_price, use send_payment_confirmation to send a payment confirmation button to admin
10. When using send_payment_confirmation, you MUST pass the user_id (from USER HISTORY), amount (total price), service_desc, and channel_id (current channel)
11. If user says they want to talk to admin/owner/real person, say briefly that the admin has been notified and stay quiet. Do NOT continue trying to sell or push orders.
12. Admin sending crypto addresses (Bitcoin, Ethereum, etc.), PayPal info, or payment instructions = WAITING for payment, NOT confirmed. Never treat this as payment received.

PAYMENT CONFIRMATION FLOW (CRITICAL — ONLY trigger on EXPLICIT payment confirmation):
⚠️ ONLY use confirm_payment when someone EXPLICITLY states money was sent/received.
❌ DO NOT trigger on: admin sending crypto address, admin appearing, user asking about payment methods, user saying they WANT to pay.
✅ DO trigger on: "he paid", "already paid", "sent the money", "payment confirmed", "已付", "I just paid".

When payment IS confirmed:
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
- Admin sends crypto address like "bc1q..." or "0x..." → This is PAYMENT INFO, NOT payment confirmation. Do NOT trigger confirm_payment. Just acknowledge.
- "i want to talk to admin" / "no bot" / "real person" → User wants human help. Say the admin has been notified and stop. Do NOT try to sell.
- "i want rep grind" → Order intent → get_price("rep grind")
- "how much for 99" → Price query → get_price("99 overall")

KNOWLEDGE BASE MANAGEMENT (add_knowledge tool):
- When admin asks you to "add link to knowledge base", "save this link", "put it on knowledge base", "remember this" with a URL → Use add_knowledge
- Parameters: service_name (what product/service the link is for), content (the link URL and any description), target_file (optional)
- Example: Admin says "put this link on knowledge base: https://g2g.com/.../G1774857930235UP for taz face custom build"
  → Action: add_knowledge, Action Input: service_name="Taz Face Custom Build", content="G2G Link: https://g2g.com/.../G1774857930235UP"
- Only admin/owner messages should trigger add_knowledge — NEVER add customer messages to knowledge base
- After adding, confirm what was saved and where

DISTINGUISHING CURRENT vs HISTORY ORDERS:
- If user just asked about a service (e.g., "50x"), and then says "paid" → This is a CURRENT order for 50x
- If user asks "status of my order" or "my previous order" → This is about HISTORY, use check_order_status
- If user has multiple past orders in history and says "paid" without specifics → Use the MOST RECENTLY DISCUSSED service

CRITICAL: Before using confirm_payment, verify the following:
1. Someone EXPLICITLY said they sent/received money (not just asking about payment or admin providing payment info)
2. Review the USER HISTORY for order details (e.g., "50x", "rep grind"). Include those in the Action Input.
3. If admin sent a crypto address or payment method info, payment has NOT been confirmed yet — wait for explicit confirmation.
4. ALWAYS pass the user_id from CURRENT_USER_ID in the context as the second argument to confirm_payment.

Examples:

Example 1 - Payment with history context:
Question: he already paid
Previous history shows user asked about 50x + lvl40
Thought: User mentions payment. History shows they wanted 50x + lvl40 ($25). I'll confirm with that info.
Action: confirm_payment
Action Input: 50x rep sleeve + level 40, <user_id from CURRENT_USER_ID>
Observation: ✅ Payment Confirmed! Order Summary: 50x Rep Sleeve + Level 40 ($25). Total: $25. Admin, run this command to create order channel: !confirm-payment <@user_id> 25 "50x Rep Sleeve + Level 40"
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
Action Input: 250 all specialization + 50x, <user_id from CURRENT_USER_ID>
Observation: ✅ Payment Confirmed! Total: $75. Admin, run: !confirm-payment <@user_id> 75 "250 Layers Challenge + All 5 Specialties + 50x Rep Sleeve"
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

Example 8 - Admin adds link to knowledge base:
Question: [ADMIN] put this link on knowledge base: https://www.g2g.com/cn/categories/nba-dunk-items/offer/G1774857930235UP?seller=LegendNBA2k this is for taz face custom build
Thought: Admin wants me to save a G2G link for "Taz Face Custom Build" to the knowledge base. I should use add_knowledge.
Action: add_knowledge
Action Input: service_name=Taz Face Custom Build, content=G2G Link: https://www.g2g.com/cn/categories/nba-dunk-items/offer/G1774857930235UP?seller=LegendNBA2k
Observation: ✅ Added new entry for 'Taz Face Custom Build' to pricing/g2g-products.md
Thought: I now know the final answer.
Final Answer: ✅ Saved! 📝 **Taz Face Custom Build** G2G link has been added to `pricing/g2g-products.md`. I'll reference it when customers ask about this service. 👍

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

Question: {input}
Thought: {agent_scratchpad}""")

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

    async def _call_react_agent(self, user_msg: str, channel_id: str, chat_history: List[Dict],
                                user_memory_summary: str = "", user_id: str = "") -> Tuple[str, bool]:
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

            # ========== 关键修复：确保支付确认时自动追加 ORDER_INFO 标记 ==========
            # 如果是支付确认场景，但回复中缺少 [ORDER_INFO:...] 标记，
            # 自动从回复文本中提取金额和服务信息并追加
            if is_payment_context and "[ORDER_INFO:" not in reply:
                extracted = _extract_order_info_from_reply(reply)
                if not extracted:
                    # 尝试从 AI 回复中解析 Total 和服务信息
                    extracted = _parse_payment_info_from_text(reply)
                if extracted:
                    reply += f"\n[ORDER_INFO:service={extracted['service']},amount={extracted['amount']}]"
                    logger.info(
                        f"💳 Auto-appended ORDER_INFO: service={extracted['service']}, amount={extracted['amount']}")

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

    async def chat(self, user_msg: str, channel_id: str, user_id: str = None) -> Tuple[
        str, bool, Optional[discord.ui.View]]:
        """
        智能对话处理流程
        返回: (回复内容, 是否有订单意图, 可选的按钮视图)
        user_id: 用户ID，用于加载完整历史记忆
        """
        # ========== 预加载用户完整历史记忆 ==========
        user_memory_summary = ""
        if user_id:
            try:
                user_memory_summary = await context_manager.get_user_memory_summary(user_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to load user memory: {e}")

        # ========== 第零步：付款意图快速检测 ==========
        # 如果用户消息包含付款关键词，尝试从历史中提取订单信息，直接返回按钮
        payment_keywords = ["paid", "sent", "payment sent", "money sent", "i paid", "已付"]
        user_msg_lower = user_msg.lower()
        if any(kw in user_msg_lower for kw in payment_keywords):
            try:
                history = await context_manager.get_context(channel_id)
                service_desc, amount = parse_order_from_history(history)
                if service_desc and amount:
                    view = PaymentConfirmView(service_desc=service_desc, amount=amount)
                    reply_text = f"✅ Payment detected for **{service_desc}** (${amount:.2f}). Admin, please click the button below to confirm and create the order."
                    try:
                        await context_manager.save_context(channel_id, user_msg, reply_text)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save context: {e}")
                    logger.info(f"💳 Payment quick-path: service={service_desc}, amount={amount}")
                    return reply_text, True, view
            except Exception as e:
                logger.warning(f"⚠️ Payment quick-path failed: {e}")

        # ========== 第零步补充：购买意向检测（非付款，但表达了想买的意愿）==========
        # 例如客户说 "I want to order", "yes im ready", "let's go" 等
        # 但不包含 "paid"/"sent"（那些已在上面处理）
        purchase_only_keywords = ["i want to order", "let's go", "yes im ready", "im ready", "i'm ready",
                                  "order now", "start order", "create order", "下单", "购买"]
        if any(kw in user_msg_lower for kw in purchase_only_keywords):
            try:
                history = await context_manager.get_context(channel_id)
                service_desc, amount = parse_order_from_history(history)
                if service_desc and amount:
                    view = CreateOrderView()
                    reply_text = (
                        f"✅ **Order ready!** Click the button below to create the fulfillment channel.\n\n"
                        f"**Service:** {service_desc}\n"
                        f"**Amount:** ${amount:.2f}"
                    )
                    try:
                        await context_manager.save_context(channel_id, user_msg, reply_text)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to save context: {e}")
                    logger.info(f"📦 Purchase intent quick-path: service={service_desc}, amount={amount}")
                    return reply_text, True, view
            except Exception as e:
                logger.warning(f"⚠️ Purchase intent quick-path failed: {e}")

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
            return reply, has_intent, None

        # ========== 第二步：ReAct Agent 处理（如果可用）==========
        # 优先尝试使用 LangChain ReAct Agent 处理复杂意图
        if self._agent_executor:
            try:
                history = await context_manager.get_context(channel_id)
            except Exception as e:
                logger.warning(f"⚠️ Failed to get context: {e}")
                history = []

            react_reply, react_intent = await self._call_react_agent(user_msg, channel_id, history,
                                                                     user_memory_summary=user_memory_summary,
                                                                     user_id=user_id)
            if react_reply:  # ReAct Agent 成功处理
                try:
                    await context_manager.save_context(channel_id, user_msg, react_reply)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save context: {e}")
                logger.info(f"✅ ReAct Agent handled: {user_msg[:30]}... -> {react_reply[:40]}...")
                return react_reply, react_intent, None

        # ========== 第三步：AI 处理 (<2s) ==========
        if not self._use_ai:
            default_reply = "I'm not sure. You can ask about prices (rep, 99, pass, mt, vc) or type !help"
            try:
                await context_manager.save_context(channel_id, user_msg, default_reply)
            except Exception as e:
                logger.warning(f"⚠️ Failed to save context: {e}")
            return default_reply, False, None

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
                            sleeve_match = knowledge_content[
                                           knowledge_content.find("## 👕 REP SLEEVE"):knowledge_content.find(
                                               "## 💰 OTHER SERVICES")]
                            if sleeve_match:
                                relevant_sections.append(sleeve_match)

                        # 匹配 "grind", "rep", "rookie", "starter" 等等级
                        if any(x in user_msg_lower for x in ["grind", "rookie", "starter", "veteran", "legend"]):
                            grind_match = knowledge_content[
                                          knowledge_content.find("## 👑 REPUTATION RANK GRINDS"):knowledge_content.find(
                                              "## 💎 FINISHED ACCOUNTS")]
                            if grind_match:
                                relevant_sections.append(grind_match)

                        # 匹配 "challenge", "99", "badge" 等服务
                        if any(x in user_msg_lower for x in ["challenge", "99", "badge", "overall"]):
                            other_match = knowledge_content[
                                          knowledge_content.find("## 🌟 OVERALL"):knowledge_content.find(
                                              "## 🔥 HOT DEALS")]
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
                return ai_reply, has_order_intent, None
            else:
                # AI 调用失败，返回友好的默认消息
                fallback_reply = "I'm temporarily busy. Try again or ask about pricing (rep, 99, pass, mt)!"
                logger.warning(f"⚠️ AI call returned empty, using fallback reply")
                return fallback_reply, False, None

        except Exception as e:
            logger.error(f"❌ Unexpected error in chat: {e}", exc_info=True)
            return "Sorry, I'm having trouble. Try again or type !help", False, None

    async def _call_openai(self, messages: List[Dict]) -> Tuple[str, bool]:
        """调用 OpenAI API（异步）"""
        start_time = time.time()
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

                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=8)) as resp:
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
        start_time = time.time()
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

                        # 监控埋点：LLM 调用成功
                        latency = time.time() - start_time
                        if METRICS_AVAILABLE:
                            get_metrics_collector().record_llm_call(latency)

                        return reply, has_intent
                    else:
                        body = await resp.text()
                        logger.error(f"❌ DeepSeek API error {resp.status}: {body[:200]}")
                        if METRICS_AVAILABLE:
                            get_metrics_collector().inc_error()
                        return "", False

        except asyncio.TimeoutError:
            logger.warning("⏱️ DeepSeek call timeout (>15s)")
            if METRICS_AVAILABLE:
                get_metrics_collector().inc_error()
            return "", False
        except aiohttp.ClientError as e:
            logger.error(f"❌ DeepSeek network error: {e}")
            if METRICS_AVAILABLE:
                get_metrics_collector().inc_error()
            return "", False
        except Exception as e:
            logger.error(f"❌ DeepSeek call failed: {e}", exc_info=True)
            if METRICS_AVAILABLE:
                get_metrics_collector().inc_error()
            return "", False


# AI 服务单例
ai_service = AIService()

# ====================== 第四层：高并发控制 + 限流 ======================
# 并发信号量：限制最大同时处理的请求
concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# 用户限流缓存：(user_id -> last_request_time)
user_rate_limit: Dict[int, float] = {}


# ====================== 知识库 Web 管理界面 ======================

def verify_auth(request):
    """验证请求认证（可选密码）"""
    if not ADMIN_PASSWORD:
        return True
    auth = request.headers.get("Authorization", "")
    return auth == f"Bearer {ADMIN_PASSWORD}"


async def admin_page(request):
    """管理界面 HTML"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")

    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Knowledge Base Manager</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); overflow: hidden; display: flex; height: 90vh; }
            .sidebar { width: 280px; background: #f8f9fa; border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; }
            .header { padding: 20px; background: #667eea; color: white; font-size: 18px; font-weight: bold; }
            .nav-links { display: flex; gap: 10px; padding: 10px 15px; background: #5568d3; flex-wrap: wrap; }
            .nav-links a { color: white; text-decoration: none; font-size: 12px; padding: 4px 8px; background: rgba(255,255,255,0.2); border-radius: 4px; }
            .nav-links a:hover { background: rgba(255,255,255,0.3); }
            .nav-links a.active { background: white; color: #667eea; }
            .file-list { flex: 1; overflow-y: auto; padding: 10px; }
            .file-item { padding: 10px; margin-bottom: 5px; cursor: pointer; border-radius: 6px; transition: all 0.2s; }
            .file-item:hover { background: #e0e7ff; }
            .file-item.active { background: #667eea; color: white; font-weight: bold; }
            .main { flex: 1; display: flex; flex-direction: column; }
            .toolbar { padding: 15px 20px; background: #f8f9fa; border-bottom: 1px solid #e0e0e0; display: flex; gap: 10px; align-items: center; }
            .toolbar button { padding: 8px 16px; border: none; border-radius: 6px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
            .toolbar button.primary { background: #667eea; color: white; }
            .toolbar button.primary:hover { background: #5568d3; }
            .toolbar button.success { background: #28a745; color: white; }
            .toolbar button.success:hover { background: #218838; }
            .toolbar button.danger { background: #dc3545; color: white; }
            .toolbar button.danger:hover { background: #c82333; }
            .editor { flex: 1; display: flex; flex-direction: column; padding: 20px; }
            .editor-header { margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
            .editor-header h3 { color: #333; }
            .editor-header .filename { color: #666; font-size: 14px; }
            textarea { flex: 1; font-family: "Monaco", "Courier New", monospace; font-size: 13px; padding: 12px; border: 1px solid #ddd; border-radius: 6px; resize: none; }
            .status { position: fixed; bottom: 20px; right: 20px; padding: 15px 20px; border-radius: 6px; display: none; max-width: 400px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); animation: slideIn 0.3s ease; }
            .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            .status.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
            @keyframes slideIn { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
            .spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid #f3f3f3; border-top: 2px solid #667eea; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 8px; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: #999; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="sidebar">
                <div class="header">📚 Knowledge Base</div>
                <div class="nav-links">
                    <a href="/admin" class="active">知识库</a>
                    <a href="/admin/history">对话历史</a>
                    <a href="/admin/dashboard">监控面板</a>
                </div>
                <div class="file-list" id="fileList"></div>
            </div>
            <div class="main">
                <div class="toolbar">
                    <button class="primary" id="rebuildBtn">🔄 Rebuild Vector Store</button>
                    <button class="success" id="saveBtn">💾 Save File</button>
                    <span id="statusIcon" style="display: none;"><span class="spinner"></span><span id="statusText"></span></span>
                </div>
                <div class="editor">
                    <div class="editor-header">
                        <h3>Edit Content</h3>
                        <span class="filename" id="filenameDisplay">Select a file to edit...</span>
                    </div>
                    <textarea id="editor" placeholder="Select a file from the left to start editing..."></textarea>
                </div>
            </div>
        </div>
        <div id="statusMsg" class="status"></div>
        <script>
            let currentFile = null;
            const password = prompt("Enter admin password:", "");
            const headers = password ? { 'Authorization': `Bearer ${password}` } : {};

            async function fetchJSON(url, options = {}) {
                const res = await fetch(url, { ...options, headers });
                if (res.status === 401) {
                    alert("❌ Unauthorized. Wrong password?");
                    return null;
                }
                if (!res.ok) {
                    const text = await res.text();
                    throw new Error(`${res.status}: ${text}`);
                }
                return await res.json();
            }

            async function loadFileList() {
                try {
                    const data = await fetchJSON('/admin/files');
                    if (data) {
                        const listDiv = document.getElementById('fileList');
                        listDiv.innerHTML = '';
                        if (data.length === 0) {
                            listDiv.innerHTML = '<div style="padding: 10px; color: #999;">No files found</div>';
                            return;
                        }
                        data.forEach(item => {
                            const div = document.createElement('div');
                            div.className = 'file-item';
                            // 显示文件夹图标 + 相对路径
                            const parts = item.name.split('/');
                            const basename = parts.pop();
                            const folder = parts.join('/');
                            div.innerHTML = folder
                                ? '<div style="font-size:12px;color:#999;">📁 ' + folder + '/</div><div>' + basename + '</div>'
                                : '<div>' + item.name + '</div>';
                            div.onclick = () => loadFile(item.name);
                            listDiv.appendChild(div);
                        });
                    }
                } catch (e) {
                    showStatus(`❌ Failed to load files: ${e.message}`, 'error');
                }
            }

            async function loadFile(filename) {
                try {
                    const data = await fetchJSON(`/admin/file/${encodeURIComponent(filename)}`);
                    if (data) {
                        currentFile = filename;
                        document.getElementById('editor').value = data.content;
                        document.getElementById('filenameDisplay').textContent = filename;
                        document.querySelectorAll('.file-item').forEach(el => {
                            // 获取文件名（最后一个 div 的文本内容）
                            const nameEl = el.querySelectorAll('div');
                            const name = nameEl.length > 1 ? nameEl[nameEl.length - 1].textContent : nameEl[0]?.textContent || '';
                            el.classList.toggle('active', name === filename.split('/').pop());
                        });
                    }
                } catch (e) {
                    showStatus(`❌ Failed to load file: ${e.message}`, 'error');
                }
            }

            async function saveFile() {
                if (!currentFile) {
                    showStatus("No file selected", "error");
                    return;
                }
                const content = document.getElementById('editor').value;
                showStatus("Saving...", "info");
                try {
                    const res = await fetch('/admin/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', ...headers },
                        body: JSON.stringify({ filename: currentFile, content })
                    });
                    if (res.ok) {
                        showStatus("✅ File saved successfully!", "success");
                    } else {
                        const text = await res.text();
                        showStatus(`❌ Save failed: ${text}`, "error");
                    }
                } catch (e) {
                    showStatus(`❌ Save error: ${e.message}`, "error");
                }
            }

            async function rebuild() {
                if (!confirm("⚠️  Rebuilding may take a while (typically 10-30s). Continue?")) return;
                showStatus("Rebuilding vector store...", "info");
                try {
                    const res = await fetch('/admin/rebuild', { method: 'POST', headers });
                    if (res.ok) {
                        showStatus("✅ Rebuild triggered! Vector store will update in background. New knowledge takes effect immediately!", "success");
                    } else {
                        showStatus("❌ Rebuild failed", "error");
                    }
                } catch (e) {
                    showStatus(`❌ Error: ${e.message}`, "error");
                }
            }

            function showStatus(msg, type) {
                const statusDiv = document.getElementById('statusMsg');
                statusDiv.textContent = msg;
                statusDiv.className = `status ${type}`;
                statusDiv.style.display = 'block';
                if (type === "success" || type === "error") {
                    setTimeout(() => { statusDiv.style.display = 'none'; }, 4000);
                }
            }

            document.getElementById('saveBtn').onclick = saveFile;
            document.getElementById('rebuildBtn').onclick = rebuild;
            loadFileList();
        </script>
    </body>
    </html>
    '''
    return web.Response(text=html, content_type='text/html')


async def list_files(request):
    """列出所有知识库文件（递归子目录）"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    files = []
    for ext in ["md", "txt"]:
        for path in glob.glob(os.path.join(KNOWLEDGE_DIR, f"**/*.{ext}"), recursive=True):
            # 返回相对于 KNOWLEDGE_DIR 的路径，如 "pricing/g2g-pricing.md"
            rel = os.path.relpath(path, KNOWLEDGE_DIR)
            size = os.path.getsize(path)
            files.append({"name": rel, "size": size})
    return web.json_response(sorted(files, key=lambda x: x["name"]))


async def get_file(request):
    """获取文件内容（支持子目录路径）"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    filename = request.match_info.get("filename", "")
    if not filename or ".." in filename or filename.startswith("/"):
        return web.Response(status=400, text="Invalid filename")
    filepath = os.path.join(KNOWLEDGE_DIR, filename)
    # 安全检查：确保路径在 KNOWLEDGE_DIR 内
    if not os.path.realpath(filepath).startswith(os.path.realpath(KNOWLEDGE_DIR)):
        return web.Response(status=400, text="Invalid path")
    if not os.path.exists(filepath):
        return web.Response(status=404, text="File not found")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return web.json_response({"filename": filename, "content": content})
    except Exception as e:
        return web.Response(status=500, text=str(e))


async def save_file(request):
    """保存文件内容（支持子目录路径，自动创建中间目录）"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    try:
        data = await request.json()
        filename = data.get("filename", "")
        content = data.get("content", "")
        if not filename or ".." in filename or filename.startswith("/"):
            return web.Response(status=400, text="Invalid filename")
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        # 安全检查：确保路径在 KNOWLEDGE_DIR 内
        if not os.path.realpath(filepath).startswith(os.path.realpath(KNOWLEDGE_DIR)):
            return web.Response(status=400, text="Invalid path")
        # 自动创建中间目录
        dirpath = os.path.dirname(filepath)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"✅ Web save: {filename} updated")
        return web.json_response({"status": "ok", "message": "File saved"})
    except Exception as e:
        logger.error(f"❌ Web save failed: {e}")
        return web.Response(status=500, text=str(e))


async def rebuild_vectorstore(request):
    """触发向量库重建（后台任务）"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    asyncio.create_task(_rebuild_background())
    return web.json_response({"status": "rebuilding", "message": "Vector store rebuild started in background."})


async def _rebuild_background():
    """后台重建向量库"""
    try:
        logger.info("🔄 Web rebuild: starting vector store rebuild...")
        if ai_service and ai_service._rag_agent:
            await ai_service._rag_agent.rebuild_knowledge_base()
            logger.info("✅ Web rebuild: vector store rebuilt successfully")
        else:
            logger.error("❌ Web rebuild: RAG agent not available")
    except Exception as e:
        logger.error(f"❌ Web rebuild failed: {e}", exc_info=True)


async def api_list_users(request):
    """API: 列出所有有记忆记录的用户"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_context.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT user_id, author_name, COUNT(*) as msg_count, MAX(timestamp) as last_active
            FROM user_memory
            GROUP BY user_id
            ORDER BY last_active DESC
            LIMIT 100
        """)
        rows = c.fetchall()
        conn.close()
        users = []
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(row[3]))
            users.append({
                "user_id": row[0],
                "name": row[1] or row[0],
                "msg_count": row[2],
                "last_active": ts,
                "last_ts": row[3]
            })
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def api_user_history(request):
    """API: 获取指定用户的完整对话历史"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    user_id = request.match_info.get("user_id", "")
    limit = int(request.query.get("limit", "100"))
    if not user_id:
        return web.json_response({"error": "user_id required"}, status=400)
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_context.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT role, content, author_name, channel_id, channel_name, timestamp
            FROM user_memory
            WHERE user_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
        """, (user_id, limit))
        rows = c.fetchall()
        conn.close()
        history = []
        for row in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(row[5]))
            history.append({
                "role": row[0],
                "content": row[1],
                "author_name": row[2],
                "channel_id": row[3],
                "channel_name": row[4],
                "timestamp": ts,
                "ts": row[5]
            })
        return web.json_response(history)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# ====================== 监控相关路由 ======================

async def metrics_endpoint(request):
    """Prometheus 格式的指标端点"""
    if METRICS_AVAILABLE:
        collector = get_metrics_collector()
        return web.Response(text=collector.to_prometheus(), content_type='text/plain')
    else:
        return web.Response(text="# Metrics not available", status=503, content_type='text/plain')


async def api_metrics(request):
    """返回最近 N 条指标数据（JSON 格式）"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")
    if not METRICS_AVAILABLE:
        return web.json_response({"error": "Metrics not available"}, status=503)

    try:
        limit = int(request.query.get('limit', 100))
        collector = get_metrics_collector()
        data = collector.get_recent(limit)
        return web.json_response(data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def dashboard_page(request):
    """监控仪表板 HTML"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")

    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>系统监控仪表板</title>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
        <style>
            * { box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 20px; }
            h1 { margin: 0 0 20px 0; font-size: 24px; }
            .nav { margin-bottom: 20px; }
            .nav a { color: #4cc9f0; text-decoration: none; margin-right: 20px; }
            .nav a:hover { text-decoration: underline; }
            .stats-row { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
            .stat-card { background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); border-radius: 12px; padding: 20px; flex: 1; min-width: 180px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            .stat-card h3 { margin: 0 0 10px 0; font-size: 14px; color: #888; }
            .stat-card .value { font-size: 32px; font-weight: bold; color: #4cc9f0; }
            .stat-card .unit { font-size: 14px; color: #666; margin-left: 5px; }
            .charts-row { display: flex; gap: 15px; margin-bottom: 20px; flex-wrap: wrap; }
            .chart-container { background: #16213e; border-radius: 12px; padding: 20px; flex: 1; min-width: 400px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
            .chart-container h3 { margin: 0 0 15px 0; font-size: 16px; color: #4cc9f0; }
            .chart { height: 250px; width: 100%; }
            .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
            .status-ok { color: #4ade80; }
            .status-warn { color: #fbbf24; }
            .status-error { color: #f87171; }
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/admin">📚 知识库管理</a>
            <a href="/admin/history">💬 对话历史</a>
            <a href="/admin/dashboard">📊 监控仪表板</a>
        </div>
        <h1>📊 NBA 2K26 Bot 系统监控</h1>

        <div class="stats-row" id="stats-row"></div>
        <div class="charts-row">
            <div class="chart-container"><h3>💻 CPU 使用率 (%)</h3><div id="cpu-chart" class="chart"></div></div>
            <div class="chart-container"><h3>🧠 内存使用 (MB)</h3><div id="memory-chart" class="chart"></div></div>
        </div>
        <div class="charts-row">
            <div class="chart-container"><h3>📈 消息处理量</h3><div id="messages-chart" class="chart"></div></div>
            <div class="chart-container"><h3>🤖 LLM 调用延迟 (ms)</h3><div id="llm-chart" class="chart"></div></div>
        </div>
        <div class="footer">自动刷新间隔: 30秒 | <a href="/metrics" target="_blank" style="color:#4cc9f0">Prometheus Metrics</a></div>

        <script>
            let cpuChart, memoryChart, messagesChart, llmChart;

            async function fetchMetrics() {
                const res = await fetch('/admin/api/metrics?limit=50');
                return await res.json();
            }

            function formatTime(iso) {
                const d = new Date(iso);
                return d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
            }

            function initCharts() {
                cpuChart = echarts.init(document.getElementById('cpu-chart'));
                memoryChart = echarts.init(document.getElementById('memory-chart'));
                messagesChart = echarts.init(document.getElementById('messages-chart'));
                llmChart = echarts.init(document.getElementById('llm-chart'));
            }

            function renderStats(data) {
                if (!data.length) return;
                const latest = data[data.length - 1];
                const first = data[0];
                const newMsgs = latest.messages_processed - (first.messages_processed || 0);
                const newLLM = latest.llm_calls - (first.llm_calls || 0);

                document.getElementById('stats-row').innerHTML = `
                    <div class="stat-card"><h3>💻 进程 CPU</h3><div class="value">${latest.process_cpu.toFixed(1)}<span class="unit">%</span></div></div>
                    <div class="stat-card"><h3>🧠 进程内存</h3><div class="value">${latest.process_memory_mb.toFixed(0)}<span class="unit">MB</span></div></div>
                    <div class="stat-card"><h3>💬 总消息数</h3><div class="value">${latest.messages_processed}<span class="unit"></span></div></div>
                    <div class="stat-card"><h3>🤖 LLM 调用</h3><div class="value">${latest.llm_calls}<span class="unit"></span></div></div>
                    <div class="stat-card"><h3>📦 订单创建</h3><div class="value">${latest.orders_created}<span class="unit"></span></div></div>
                    <div class="stat-card"><h3>⚠️ 错误数</h3><div class="value ${latest.errors_count > 0 ? 'status-error' : ''}">${latest.errors_count}</div></div>
                `;
            }

            function renderCharts(data) {
                const times = data.map(d => formatTime(d.timestamp));
                const cpu = data.map(d => d.process_cpu);
                const memory = data.map(d => d.process_memory_mb);
                const messages = data.map(d => d.messages_processed);
                const llm = data.map(d => d.llm_avg_latency_ms);

                const areaStyle = { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{offset:0,color:'rgba(76,201,240,0.3)'},{offset:1,color:'rgba(76,201,240,0.05)'}] } };
                const lineStyle = { color: '#4cc9f0', width: 2 };

                cpuChart.setOption({
                    tooltip: { trigger: 'axis', backgroundColor: '#16213e', borderColor: '#4cc9f0', textStyle:{color:'#eee'} },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
                    xAxis: { type: 'category', data: times, axisLine: {lineStyle:{color:'#333'}}, axisLabel:{color:'#888'} },
                    yAxis: { type: 'value', name: '%', axisLine: {lineStyle:{color:'#333'}}, splitLine:{lineStyle:{color:'#222'}}, axisLabel:{color:'#888'} },
                    series: [{ type: 'line', data: cpu, smooth: true, symbol: 'none', lineStyle, areaStyle }]
                });

                memoryChart.setOption({
                    tooltip: { trigger: 'axis', backgroundColor: '#16213e', borderColor: '#4cc9f0', textStyle:{color:'#eee'} },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
                    xAxis: { type: 'category', data: times, axisLine: {lineStyle:{color:'#333'}}, axisLabel:{color:'#888'} },
                    yAxis: { type: 'value', name: 'MB', axisLine: {lineStyle:{color:'#333'}}, splitLine:{lineStyle:{color:'#222'}}, axisLabel:{color:'#888'} },
                    series: [{ type: 'line', data: memory, smooth: true, symbol: 'none', lineStyle, areaStyle }]
                });

                messagesChart.setOption({
                    tooltip: { trigger: 'axis', backgroundColor: '#16213e', borderColor: '#4ade80', textStyle:{color:'#eee'} },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
                    xAxis: { type: 'category', data: times, axisLine: {lineStyle:{color:'#333'}}, axisLabel:{color:'#888'} },
                    yAxis: { type: 'value', name: '条', axisLine: {lineStyle:{color:'#333'}}, splitLine:{lineStyle:{color:'#222'}}, axisLabel:{color:'#888'} },
                    series: [{ type: 'bar', data: messages, itemStyle: { color: '#4ade80' } }]
                });

                llmChart.setOption({
                    tooltip: { trigger: 'axis', backgroundColor: '#16213e', borderColor: '#a78bfa', textStyle:{color:'#eee'} },
                    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
                    xAxis: { type: 'category', data: times, axisLine: {lineStyle:{color:'#333'}}, axisLabel:{color:'#888'} },
                    yAxis: { type: 'value', name: 'ms', axisLine: {lineStyle:{color:'#333'}}, splitLine:{lineStyle:{color:'#222'}}, axisLabel:{color:'#888'} },
                    series: [{ type: 'line', data: llm, smooth: true, symbol: 'none', lineStyle: { color: '#a78bfa', width: 2 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{offset:0,color:'rgba(167,139,250,0.3)'},{offset:1,color:'rgba(167,139,250,0.05)'}] } } }]
                });
            }

            async function refresh() {
                try {
                    const data = await fetchMetrics();
                    if (data.length) {
                        renderStats(data);
                        renderCharts(data);
                    }
                } catch (e) {
                    console.error('Failed to fetch metrics:', e);
                }
            }

            initCharts();
            refresh();
            setInterval(refresh, 30000);
        </script>
    </body>
    </html>
    '''
    return web.Response(text=html, content_type='text/html')


async def history_page(request):
    """用户对话历史管理界面"""
    if not verify_auth(request):
        return web.Response(status=401, text="Unauthorized")

    html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Conversation History</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #eee; min-height: 100vh; }
            .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; }
            .header h1 { font-size: 22px; }
            .header .nav { display: flex; gap: 10px; }
            .header a { color: white; text-decoration: none; padding: 8px 16px; background: rgba(255,255,255,0.2); border-radius: 6px; font-size: 14px; }
            .header a:hover { background: rgba(255,255,255,0.3); }
            .header a.active { background: white; color: #667eea; }
            .container { display: flex; height: calc(100vh - 70px); }
            .sidebar { width: 300px; background: #16213e; border-right: 1px solid #0f3460; overflow-y: auto; }
            .sidebar .search { padding: 12px; }
            .sidebar .search input { width: 100%; padding: 10px; border: 1px solid #0f3460; border-radius: 6px; background: #1a1a2e; color: #eee; font-size: 14px; }
            .user-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid #0f3460; transition: background 0.2s; }
            .user-item:hover { background: #0f3460; }
            .user-item.active { background: #667eea; }
            .user-item .name { font-weight: bold; font-size: 14px; }
            .user-item .meta { font-size: 12px; color: #aaa; margin-top: 4px; }
            .main { flex: 1; display: flex; flex-direction: column; background: #1a1a2e; }
            .main-header { padding: 16px 20px; background: #16213e; border-bottom: 1px solid #0f3460; }
            .main-header h2 { font-size: 18px; }
            .main-header .info { font-size: 13px; color: #aaa; margin-top: 4px; }
            .history { flex: 1; overflow-y: auto; padding: 16px 20px; }
            .msg { margin-bottom: 12px; display: flex; gap: 12px; }
            .msg-role { font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 12px; white-space: nowrap; height: fit-content; }
            .msg-role.user { background: #007bff; color: white; }
            .msg-role.admin { background: #28a745; color: white; }
            .msg-role.assistant { background: #667eea; color: white; }
            .msg-role.system { background: #6c757d; color: white; }
            .msg-bubble { background: #16213e; padding: 10px 14px; border-radius: 8px; flex: 1; max-width: 80%; }
            .msg-content { font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
            .msg-meta { font-size: 11px; color: #666; margin-top: 6px; }
            .empty-state { display: flex; align-items: center; justify-content: center; height: 100%; color: #666; font-size: 16px; }
            .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>💬 Conversation History</h1>
            <div class="nav">
                <a href="/admin">📚 知识库</a>
                <a href="/admin/history" class="active">💬 对话历史</a>
                <a href="/admin/dashboard">📊 监控面板</a>
            </div>
        </div>
        <div class="container">
            <div class="sidebar">
                <div class="search">
                    <input type="text" id="searchInput" placeholder="🔍 Search user ID or name..." oninput="filterUsers()">
                </div>
                <div id="userList"></div>
            </div>
            <div class="main">
                <div class="main-header" id="mainHeader" style="display:none;">
                    <h2 id="userName">-</h2>
                    <div class="info" id="userInfo">-</div>
                </div>
                <div class="history" id="historyDiv">
                    <div class="empty-state">
                        <div class="icon">💬</div>
                        <div>Select a user from the left to view conversation history</div>
                    </div>
                </div>
            </div>
        </div>
        <script>
            const password = localStorage.getItem('admin_pwd') || prompt("Enter admin password:", "");
            localStorage.setItem('admin_pwd', password);
            const headers = password ? { 'Authorization': `Bearer ${password}` } : {};
            let allUsers = [];
            let currentUserId = null;

            async function fetchJSON(url) {
                const res = await fetch(url, { headers });
                if (res.status === 401) { alert("Unauthorized"); return null; }
                if (!res.ok) throw new Error(`${res.status}`);
                return await res.json();
            }

            async function loadUsers() {
                try {
                    allUsers = await fetchJSON('/admin/api/users') || [];
                    renderUsers(allUsers);
                } catch (e) { console.error(e); }
            }

            function renderUsers(users) {
                const div = document.getElementById('userList');
                if (!users.length) { div.innerHTML = '<div style="padding:20px;color:#666;">No users found</div>'; return; }
                div.innerHTML = users.map(u => {
                    const shortId = u.user_id.length > 12 ? u.user_id.substring(0, 12) + '...' : u.user_id;
                    const displayName = u.name !== u.user_id ? u.name : shortId;
                    return `
                    <div class="user-item ${u.user_id === currentUserId ? 'active' : ''}" onclick="selectUser('${u.user_id}')">
                        <div class="name">${displayName}</div>
                        <div class="meta">🆔 ${u.user_id}</div>
                        <div class="meta">${u.msg_count} msgs · ${u.last_active}</div>
                    </div>`;
                }).join('');
            }

            function filterUsers() {
                const q = document.getElementById('searchInput').value.toLowerCase();
                const filtered = allUsers.filter(u =>
                    u.user_id.toLowerCase().includes(q) || u.name.toLowerCase().includes(q)
                );
                renderUsers(filtered);
            }

            async function selectUser(userId) {
                currentUserId = userId;
                renderUsers(allUsers.filter(u => {
                    const q = document.getElementById('searchInput').value.toLowerCase();
                    return !q || u.user_id.toLowerCase().includes(q) || u.name.toLowerCase().includes(q);
                }));
                document.getElementById('mainHeader').style.display = 'block';
                const user = allUsers.find(u => u.user_id === userId);
                document.getElementById('userName').textContent = user ? user.name : userId;
                document.getElementById('userInfo').textContent = `ID: ${userId} · ${user ? user.msg_count + ' messages' : ''}`;

                const historyDiv = document.getElementById('historyDiv');
                historyDiv.innerHTML = '<div class="empty-state"><div class="icon">⏳</div><div>Loading...</div></div>';

                try {
                    const msgs = await fetchJSON(`/admin/api/user/${encodeURIComponent(userId)}?limit=200`) || [];
                    if (!msgs.length) {
                        historyDiv.innerHTML = '<div class="empty-state"><div class="icon">📭</div><div>No conversation history</div></div>';
                        return;
                    }
                    historyDiv.innerHTML = msgs.map(m => {
                        const roleClass = m.role === 'admin' ? 'admin' : m.role === 'user' ? 'user' : m.role === 'assistant' ? 'assistant' : 'system';
                        const roleLabel = m.role === 'admin' ? '👤 Admin' : m.role === 'user' ? '💬 User' : m.role === 'assistant' ? '🤖 Bot' : '⚙️ System';
                        const channelInfo = m.channel_name ? `#${m.channel_name}` : '';
                        return `
                            <div class="msg">
                                <div class="msg-role ${roleClass}">${roleLabel}</div>
                                <div class="msg-bubble">
                                    <div class="msg-content">${escapeHtml(m.content)}</div>
                                    <div class="msg-meta">${m.timestamp} ${channelInfo} ${m.author_name ? '· ' + m.author_name : ''}</div>
                                </div>
                            </div>
                        `;
                    }).join('');
                    historyDiv.scrollTop = historyDiv.scrollHeight;
                } catch (e) {
                    historyDiv.innerHTML = `<div class="empty-state"><div class="icon">❌</div><div>Error: ${e.message}</div></div>`;
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            loadUsers();
        </script>
    </body>
    </html>
    '''
    return web.Response(text=html, content_type='text/html')


def start_web_server():
    """启动后台 Web 服务器"""
    app = web.Application()
    app.router.add_get('/admin', admin_page)
    app.router.add_get('/admin/files', list_files)
    app.router.add_get('/admin/file/{filename:.+}', get_file)
    app.router.add_post('/admin/save', save_file)
    app.router.add_post('/admin/rebuild', rebuild_vectorstore)
    app.router.add_get('/admin/history', history_page)
    app.router.add_get('/admin/api/users', api_list_users)
    app.router.add_get('/admin/api/user/{user_id}', api_user_history)
    # 监控相关路由
    app.router.add_get('/admin/dashboard', dashboard_page)
    app.router.add_get('/admin/api/metrics', api_metrics)
    app.router.add_get('/metrics', metrics_endpoint)  # Prometheus 端点

    async def run_web_server():
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', WEB_PORT)
        await site.start()
        logger.info(f"🌐 Knowledge base admin UI started at http://0.0.0.0:{WEB_PORT}/admin")

    asyncio.create_task(run_web_server())


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
        await interaction.response.edit_message(content=f"🔄 Order `{self.order_id}` marked as **In Progress**",
                                                embed=embed)
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
        await interaction.response.edit_message(content=f"✅ Order `{self.order_id}` marked as **Completed**",
                                                embed=embed)
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
        await interaction.response.edit_message(content=f"❌ Order `{self.order_id}` has been **Cancelled**",
                                                embed=embed)
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

        # ========== 4. 创建或获取 Orders 分类 ==========
        orders_category = discord.utils.get(guild.categories, name="Orders")
        if not orders_category:
            # 创建 Orders 分类
            orders_category = await guild.create_category("Orders")
            logger.info(f"✅ Created 'Orders' category")

        # ========== 5. 创建履约频道 ==========
        # 频道命名格式：nba2k-{customer}-{date}-{id}
        date_str = datetime.now().strftime('%Y%m%d')
        order_num = order_id.split('-')[-1] if '-' in order_id else order_id
        customer_name = customer.name.lower().replace(' ', '-')[:20]  # 限制长度避免超过 Discord 限制
        fulfillment_channel_name = f"nba2k-{customer_name}-{date_str}-{order_num}"

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
            category=orders_category,
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
            await migrate_history(consulting_channel, fulfillment_channel, limit=200)
        except Exception as e:
            logger.warning(f"⚠️ Failed to migrate history: {e}")

        # ========== 8. 在履约频道通知客户 ==========
        await fulfillment_channel.send(
            f"🚀 {customer.mention} Your service has been confirmed! Boost will start within 10 minutes."
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

    客户 ID 在按钮点击时从频道最近历史中自动识别（最近一条非 bot 消息的作者）
    """

    def __init__(self, service_desc: str, amount: float):
        super().__init__(timeout=7200)  # 2小时超时
        self.service_desc = service_desc
        self.amount = amount

    async def _get_customer_from_channel(self, channel: discord.TextChannel) -> Optional[discord.Member]:
        """
        从频道最近历史中识别客户
        1. 优先找非 bot、非管理员的用户（普通客户）
        2. 如果找不到（比如管理员自己在测试），回退到第一个非 bot 用户
        """
        fallback_member = None
        async for msg in channel.history(limit=20):
            if msg.author.bot:
                continue
            try:
                member = channel.guild.get_member(msg.author.id)
                if not member:
                    continue
                if member.id in ADMIN_USER_IDS:
                    # 记录第一个管理员作为回退
                    if not fallback_member:
                        fallback_member = member
                    continue
                # 找到非管理员用户
                return member
            except Exception:
                pass
        # 回退：如果频道中只有管理员消息，使用第一个非 bot 用户（管理员可能在测试）
        return fallback_member

    @discord.ui.button(label="✅ Confirm Payment & Create Order", style=discord.ButtonStyle.green,
                       custom_id="payment_received")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can confirm payments.", ephemeral=True)
            return

        # 禁用所有按钮
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"⏳ Creating order...",
            view=self
        )

        try:
            consulting_channel = interaction.channel
            # 从频道历史中自动识别客户
            customer = await self._get_customer_from_channel(consulting_channel)
            if not customer:
                await interaction.followup.send(
                    "❌ Could not identify the customer from recent messages. Please use `!confirm-payment @user <amount> \"service\"` instead.",
                    ephemeral=True)
                return

            result = await create_order_from_confirmation(
                guild=interaction.guild,
                customer_id=customer.id,
                amount=self.amount,
                service_desc=self.service_desc,
                admin=interaction.user,
                consulting_channel=consulting_channel
            )
            if result:
                order_id, fulfillment_channel, _ = result
                # 不重复发送，create_order_from_confirmation 已发送过
                logger.info(f"✅ Order {order_id} created successfully via PaymentConfirmView")
            else:
                await interaction.followup.send("❌ Failed to create order. Check logs.", ephemeral=True)
        except Exception as e:
            logger.error(f"❌ Error creating order from button: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to create order: {str(e)[:100]}")

    @discord.ui.button(label="❌ Payment Not Received", style=discord.ButtonStyle.red, custom_id="payment_not_received")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can operate.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="❌ **Payment not confirmed** — Customer has been notified.",
            view=self
        )

        customer = await self._get_customer_from_channel(interaction.channel)
        if customer:
            try:
                msg = (
                    f"⚠️ {customer.mention} Admin has not received your payment yet.\n"
                    f"Please check the following:\n"
                    f"1. 💰 Is your PayPal/G2G order completed?\n"
                    f"2. 📸 Please send a payment screenshot to admin\n"
                    f"3. 💬 Contact admin {interaction.user.mention} if you have questions\n\n"
                    f"Service: **{self.service_desc}** | Amount: **${self.amount:.2f}**"
                )
                await interaction.channel.send(msg)
            except Exception as e:
                logger.warning(f"⚠️ Failed to notify customer: {e}")


class OrderDetailsModal(discord.ui.Modal, title='Order Details'):
    """填写订单服务和金额的表单（客户已通过 Select 选定）"""
    service_input = discord.ui.TextInput(
        label='Service Description',
        placeholder='e.g. 99 Overall + Badge Unlock',
        required=True,
        max_length=200
    )
    amount_input = discord.ui.TextInput(
        label='Amount ($)',
        placeholder='e.g. 75',
        required=True,
        max_length=20
    )

    def __init__(self, channel: discord.TextChannel, customer: discord.Member):
        super().__init__()
        self.channel = channel
        self.customer = customer

    async def on_submit(self, interaction: discord.Interaction):
        guild = self.channel.guild

        # 解析金额
        amount_str = self.amount_input.value.strip().replace('$', '')
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                f"❌ Invalid amount: `{self.amount_input.value}`. Please enter a positive number.",
                ephemeral=True
            )
            return

        service_desc = self.service_input.value.strip()
        if not service_desc:
            await interaction.response.send_message("❌ Service description cannot be empty.", ephemeral=True)
            return

        # 确认信息
        confirm_embed = discord.Embed(
            title="📋 Order Summary",
            description="About to create fulfillment channel:",
            color=discord.Color.blue()
        )
        confirm_embed.add_field(name="Customer", value=self.customer.mention, inline=True)
        confirm_embed.add_field(name="Service", value=service_desc, inline=False)
        confirm_embed.add_field(name="Amount", value=f"${amount:.2f}", inline=True)

        await interaction.response.send_message(embed=confirm_embed)

        try:
            result = await create_order_from_confirmation(
                guild=guild,
                customer_id=self.customer.id,
                amount=amount,
                service_desc=service_desc,
                admin=interaction.user,
                consulting_channel=self.channel
            )
            if result:
                order_id, fulfillment_channel, _ = result
                # 不重复发送，create_order_from_confirmation 已发送过
                logger.info(f"✅ Order {order_id} created successfully via OrderDetailsModal")
            else:
                await interaction.followup.send("❌ Failed to create order. Check logs.", ephemeral=True)
        except Exception as e:
            logger.error(f"❌ Error creating order from OrderDetailsModal: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Failed to create order: {str(e)[:100]}")


class CustomerSelectView(discord.ui.View):
    """客户选择菜单"""

    def __init__(self, channel: discord.TextChannel, guild: discord.Guild):
        super().__init__(timeout=30)
        self.channel = channel
        self.guild = guild

    @discord.ui.select(
        placeholder='Choose a customer...',
        min_values=1,
        max_values=1,
        custom_id='customer_select'
    )
    async def customer_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 解析选中的 customer ID
        customer_id = int(select.values[0])
        customer = self.guild.get_member(customer_id)

        if not customer:
            await interaction.response.send_message("❌ Customer not found.", ephemeral=True)
            return

        # 尝试从频道历史预填充服务和金额
        service_desc = None
        amount = None

        service_keywords = {
            '250 challenge': '250 Layers Challenge',
            '200 challenge': '200 Layers Challenge',
            '150 challenge': '150 Layers Challenge',
            '100 challenge': '100 Layers Challenge',
            'all 5 specialties': 'All 5 Specialties',
            'all specialization': 'All 5 Specialties',
            '300x': '300x Rep Sleeve',
            '100x': '100x Rep Sleeve',
            '50x': '50x Rep Sleeve',
            '99 overall': '99 Overall',
            'badge': 'Badge Unlock',
            'rep grind': 'Rep Grind',
            'rep sleeve': 'Rep Sleeve',
            'season pass': 'Season Pass',
            'mt coin': 'MT Coins',
            'dma': 'DMA Mods',
            'account': 'Pre-built Account',
            'taz body': 'Taz Body',
            'custom build': 'Custom Build',
        }

        try:
            async for msg in self.channel.history(limit=25):
                if msg.author.bot:
                    continue
                content = msg.content
                if not content:
                    continue
                content_lower = content.lower()

                # 提取服务描述
                if not service_desc:
                    found = []
                    for kw, name in service_keywords.items():
                        if kw in content_lower and name not in found:
                            found.append(name)
                    if found:
                        service_desc = ' + '.join(found)

                # 提取金额
                if not amount:
                    match = re.search(r'\$(\d+(?:\.\d+)?)', content)
                    if match:
                        val = float(match.group(1))
                        if val >= 5:
                            amount = val

                if service_desc and amount:
                    break
        except Exception as e:
            logger.warning(f"⚠️ Failed to extract order info from channel: {e}")

        # 创建表单并预填充
        modal = OrderDetailsModal(channel=self.channel, customer=customer)
        if service_desc:
            modal.service_input.default = service_desc
        if amount:
            modal.amount_input.default = str(amount)

        await interaction.response.send_modal(modal)


class CreateOrderView(discord.ui.View):
    """
    管理员一键创建订单按钮视图
    - 永久有效（timeout=None），可固定在频道中
    - 点击时弹出客户选择菜单（Select），然后弹 Modal 填服务和金额
    - 不禁用按钮，管理员可反复使用（如追加订单）
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📦 Create Order Channel", style=discord.ButtonStyle.primary, custom_id="create_order")
    async def create_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only admins can create orders.", ephemeral=True)
            return

        guild = interaction.guild
        channel = interaction.channel

        # 获取对当前频道有权限的非 bot 成员
        try:
            all_members = [
                m for m in guild.members
                if not m.bot and channel.permissions_for(m).read_messages
            ]
        except Exception as e:
            logger.error(f"❌ Failed to fetch guild members: {e}")
            await interaction.response.send_message(
                "❌ Failed to fetch guild members. Please try again.",
                ephemeral=True
            )
            return

        if not all_members:
            await interaction.response.send_message(
                "❌ No members found with access to this channel (excluding bots).",
                ephemeral=True
            )
            return

        # 创建客户选择菜单
        view = CustomerSelectView(channel=channel, guild=guild)

        # 添加选项到 Select（最多 25 个）
        options = [
            discord.SelectOption(
                label=member.display_name[:100],  # Discord 限制 100 字符
                value=str(member.id),
                description=f"ID: {member.id}" if len(member.display_name) < 50 else None
            )
            for member in all_members[:25]
        ]

        if not options:
            await interaction.response.send_message(
                "❌ No members available for selection.",
                ephemeral=True
            )
            return

        view.customer_select.options = options

        await interaction.response.send_message(
            "👤 **Select the customer:**",
            view=view,
            ephemeral=True
        )


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


def _parse_payment_info_from_text(text: str) -> Optional[Dict]:
    """
    从 AI 回复文本中解析金额和服务信息（不依赖 [ORDER_INFO] 标记）。
    支持解析：
    - "Total: $75"
    - "Total: **$75**"
    - "!confirm-payment @user 75 \"service\""
    - 服务列表（如 "250 Layers Challenge + All 5 Specialties + 50x Rep Sleeve"）
    返回 {"service": "...", "amount": ...} 或 None
    """
    try:
        amount = None
        service = None

        # 1. 提取金额 — 匹配 "Total: $XX" 或 "Total: **$XX**"
        amount_match = re.search(r'Total[:\s]+\*{0,2}\$([\d.]+)\*{0,2}', text)
        if amount_match:
            amount = float(amount_match.group(1))

        # 2. 如果没找到 Total，尝试从 confirm-payment 命令中提取金额
        if amount is None:
            cmd_match = re.search(r'confirm-payment\s+@\S+\s+([\d.]+)', text)
            if cmd_match:
                amount = float(cmd_match.group(1))

        # 3. 提取服务名 — 从 confirm-payment 命令的引号中提取
        service_match = re.search(r'confirm-payment\s+@\S+\s+[\d.]+\s+"([^"]+)"', text)
        if service_match:
            service = service_match.group(1)

        # 4. 如果没有从命令中提取到服务名，尝试从 Order Summary 中构建
        if not service:
            summary_match = re.search(r'Order Summary[:\s]*\n((?:• .+\n?)+)', text)
            if summary_match:
                service_lines = summary_match.group(1).strip()
                service_parts = []
                for line in service_lines.split('\n'):
                    line = line.strip().lstrip('• ').strip()
                    name = re.sub(r'\s*\(\$[\d.]+\)\s*', '', line).strip()
                    if name:
                        service_parts.append(name)
                if service_parts:
                    service = ' + '.join(service_parts)

        if amount and service:
            return {"service": service, "amount": amount}

        # 5. 如果有金额但没有服务名，从文本中提取服务关键词
        if amount and not service:
            keywords_found = []
            service_keywords = {
                '250 challenge': '250 Layers Challenge',
                '200 challenge': '200 Layers Challenge',
                '150 challenge': '150 Layers Challenge',
                '100 challenge': '100 Layers Challenge',
                'all 5 specialties': 'All 5 Specialties',
                'all specialization': 'All 5 Specialties',
                'specialties': 'All 5 Specialties',
                '300x': '300x Rep Sleeve',
                '100x': '100x Rep Sleeve',
                '50x': '50x Rep Sleeve',
                '99 overall': '99 Overall',
                'badge': 'Badge Unlock',
                'rep grind': 'Rep Grind',
                'grind': 'Rep Grind',
                'season pass': 'Season Pass',
                'mt coin': 'MT Coins',
                'dma': 'DMA Mods',
            }
            text_lower = text.lower()
            for kw, name in service_keywords.items():
                if kw in text_lower and name not in keywords_found:
                    keywords_found.append(name)
            if keywords_found:
                service = ' + '.join(keywords_found)
                return {"service": service, "amount": amount}

    except Exception as e:
        logger.warning(f"⚠️ Failed to parse payment info from text: {e}")
    return None


async def _send_payment_buttons(channel: discord.TextChannel, service: str, amount: float):
    """发送收款确认按钮消息（仅管理员可操作）"""
    view = PaymentConfirmView(
        service_desc=service,
        amount=amount
    )
    embed = discord.Embed(
        title="💳 Payment Pending Confirmation",
        description=f"Admin, please confirm payment for this order:",
        color=discord.Color.orange()
    )
    embed.add_field(name="Service", value=service, inline=False)
    embed.add_field(name="Amount", value=f"${amount:.2f}", inline=True)
    embed.set_footer(text="⏰ Buttons expire in 2 hours | Admins only")
    await channel.send(embed=embed, view=view)
    return view


def parse_order_from_history(history: List[Dict]) -> Tuple[Optional[str], Optional[float]]:
    """
    从频道历史中提取最近的服务描述和金额
    返回: (service_desc, amount) 或 (None, None)
    """
    service_desc = None
    amount = None

    service_keywords = {
        '250 challenge': '250 Layers Challenge',
        '200 challenge': '200 Layers Challenge',
        '150 challenge': '150 Layers Challenge',
        '100 challenge': '100 Layers Challenge',
        'all 5 specialties': 'All 5 Specialties',
        'all specialization': 'All 5 Specialties',
        '300x': '300x Rep Sleeve',
        '100x': '100x Rep Sleeve',
        '50x': '50x Rep Sleeve',
        '99 overall': '99 Overall',
        'badge': 'Badge Unlock',
        'rep grind': 'Rep Grind',
        'rep sleeve': 'Rep Sleeve',
        'season pass': 'Season Pass',
        'mt coin': 'MT Coins',
        'dma': 'DMA Mods',
    }

    for msg in reversed(history[-15:]):
        content = msg.get("content", "")
        if not content:
            continue
        content_lower = content.lower()

        # 提取服务描述（优先匹配更长的关键词）
        if not service_desc:
            found = []
            for kw, name in service_keywords.items():
                if kw in content_lower and name not in found:
                    found.append(name)
            if found:
                service_desc = ' + '.join(found)

        # 提取金额（匹配 $数字）
        if not amount:
            match = re.search(r'\$(\d+(?:\.\d+)?)', content)
            if match:
                val = float(match.group(1))
                # 过滤掉明显不是价格的金额（太小的）
                if val >= 5:
                    amount = val

        if service_desc and amount:
            break

    return service_desc, amount


async def migrate_history(source: discord.TextChannel, target: discord.TextChannel, limit: int = 200):
    """
    将咨询频道的所有最近消息迁移到履约频道，方便打手了解完整上下文
    包含有意义的消息（Bot 回复、管理员、客户），过滤无意义的自动回复
    """
    # 无意义的 bot 消息关键词（模板化回复，不含有效信息）
    _noise_keywords = [
        "【Help Guide】", "!order - Create new order", "!status",
        "!pay", "!services", "!pricing", "!faq", "!support",
        "Available services:", "Player Upgrade", "Badge Unlock",
        "VC Boosting", "PC Mod", "Console Mod",
    ]

    def _is_noise(content: str) -> bool:
        """判断是否是无意义的 bot 自动回复"""
        if not content:
            return True
        return any(kw in content for kw in _noise_keywords)

    messages = []
    async for msg in source.history(limit=limit):
        # 过滤无意义的 bot 消息，但保留有实质内容的 bot 回复
        if msg.author.bot and _is_noise(msg.content):
            continue
        messages.append(msg)

    if not messages:
        return

    # 倒序（从旧到新）
    messages.reverse()
    await target.send("📋 **--- Previous Discussion ---**")
    for msg in messages:
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        content = msg.content if msg.content else "[Attachment/Embed]"
        if len(content) > 300:
            content = content[:300] + "..."
        author_name = msg.author.display_name
        # 标记消息类型
        if msg.author.bot:
            prefix = "🤖 Bot"
        elif msg.author.id in ADMIN_USER_IDS:
            prefix = "👤 Admin"
        else:
            prefix = f"💬 {author_name}"
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
    intents.members = True  # 必需：获取成员列表

    # 配置代理（支持中国网络，Discord.py 通过 connector 使用代理）
    connector = None
    if HTTP_PROXY:
        try:
            from aiohttp_socks import ProxyConnector
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
                        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                              manage_messages=True)
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

        # ========== 监控埋点：消息计数 ==========
        if METRICS_AVAILABLE:
            get_metrics_collector().inc_message()

        # ========== 身份识别：管理员 vs 客户 ==========
        is_admin = message.author.id in ADMIN_USER_IDS
        user_id = str(message.author.id)
        channel_id = str(message.channel.id)
        channel_name = message.channel.name
        author_name = message.author.name
        msg_content = message.content.strip()

        # 调试：记录所有消息的用户 ID
        logger.debug(
            f"🔍 DEBUG: User='{author_name}' ID={message.author.id} | ADMIN_USER_IDS={ADMIN_USER_IDS} | is_admin={is_admin}")

        # ========== 识图处理（如果消息包含图片）==========
        recognized_info = None
        if message.attachments and IMAGE_RECOGNIZER_AVAILABLE:
            first_attachment = message.attachments[0]
            if first_attachment.content_type and first_attachment.content_type.startswith("image/"):
                status_msg = await message.channel.send("🔍 Processing your image...")
                try:
                    from image_recognizer import image_recognizer
                    if image_recognizer:
                        recognized_info = await image_recognizer.recognize(first_attachment.url)
                        if recognized_info:
                            logger.info(f"🖼️ Image recognized: {recognized_info}")
                            # 拼接识别信息到消息
                            msg_content += f" [IMAGE_INFO: {json.dumps(recognized_info)}]"
                finally:
                    try:
                        await status_msg.delete()
                    except:
                        pass

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

        logger.info(
            f"🔄 [handle_message START] MsgID: {message.id} | User: {message.author.name} | Channel: {channel.name} | Content: '{user_msg[:50]}'")

        # ========== 第一步：立即响应 ==========
        # 防止 Discord "Interaction failed" 超时
        status_msg = await channel.send("🔍 Processing your request...")

        try:
            # ========== 第二步：异步处理（传入 user_id 以加载用户历史）==========
            ai_reply, has_order_intent, payment_view = await ai_service.chat(user_msg, channel_id, user_id=user_id)

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
                    (has_order_intent and any(re.search(r'\b' + re.escape(kw) + r'\b', user_msg_lower) for kw in
                                              ["rep", "99", "pass", "mt", "vc", "service", "boost"]))
            )

            if has_purchase_intent:
                logger.info(
                    f"📦 Purchase intent detected: explicit={has_explicit_order_request}, ai_intent={has_order_intent}")

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
                # 第一条消息编辑 status_msg，view 附加到最后一条
                await status_msg.edit(content=chunks[0])

                for i, chunk in enumerate(chunks[1:-1], 1):
                    await asyncio.sleep(0.3)
                    await channel.send(chunk)
                    logger.info(f"📤 Sent chunk {i + 1}/{len(chunks)}")

                # 最后一条消息（如果有 view 则附加）
                last_chunk = chunks[-1] if len(chunks) > 1 else None
                if last_chunk:
                    await asyncio.sleep(0.3)
                    await channel.send(last_chunk, view=payment_view)
                    logger.info(f"📤 Sent final chunk with view={payment_view is not None}")
                elif payment_view:
                    # 只有一条消息，直接编辑并附加 view
                    await status_msg.edit(content=ai_reply, view=payment_view)
            elif payment_view:
                # 短消息 + view：编辑 status_msg 并附加 view
                await status_msg.edit(content=ai_reply, view=payment_view)
            else:
                await status_msg.edit(content=ai_reply)

            logger.info(
                f"✅ [handle_message END] Reply sent successfully (total chars: {len(ai_reply)}) | MsgID: {message.id}")

        except Exception as e:
            logger.error(f"❌ Error handling message: {e}", exc_info=True)
            await status_msg.edit(content="⚠️ Sorry, something went wrong. Please try again or contact support.")

    # ====================== 订单频道创建 ======================
    async def create_order_channel(guild: discord.Guild, user: discord.User, service_desc: str) -> Optional[
        discord.TextChannel]:
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
        embed.add_field(name="AI Engines",
                        value=f"OpenAI={ai_service._openai_enabled}, DeepSeek={ai_service._deepseek_enabled}",
                        inline=True)
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

    @bot.command(name="panel")
    async def order_panel(ctx):
        """
        在当前频道发送订单管理面板（带永久按钮）
        管理员可固定此消息，随时点击创建履约频道
        用法: !panel
        """
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Only admins can use this command.")
            return

        embed = discord.Embed(
            title="📋 Order Management Panel",
            description=(
                "Click the button below to create a fulfillment channel.\n\n"
                "The bot will automatically detect:\n"
                "• 👤 **Customer** — from recent messages\n"
                "• 🎮 **Service** — from conversation keywords\n"
                "• 💰 **Amount** — from price mentions\n\n"
                "You can pin this message to keep it at the top!"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="📌 Right-click this message → Pin Message to keep it visible")

        view = CreateOrderView()
        msg = await ctx.send(embed=embed, view=view)

        # 尝试自动置顶
        try:
            await msg.pin()
            await ctx.send("✅ Panel pinned to the top of this channel!", delete_after=5)
        except discord.Forbidden:
            await ctx.send(
                "⚠️ I don't have permission to pin. Please **right-click** the panel message → **Pin Message**.",
                delete_after=10)
        except Exception as e:
            logger.warning(f"⚠️ Failed to pin panel message: {e}")

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

        # 金额校验
        try:
            float_amount = float(amount)
            if float_amount <= 0:
                raise ValueError
        except ValueError:
            await ctx.send(f"❌ Invalid amount: `{amount}`. Please use a number like `15` or `75.5`")
            return

        try:
            logger.info(
                f"💳 {ctx.author.name} confirmed payment for {user.name} | Amount: ${amount} | Project: {project}")

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

        except discord.ext.commands.errors.UserNotFound:
            await ctx.send(
                f"❌ User not found! Make sure you use a real @mention (not `@user`). Example: `!confirm-payment @username {amount} \"{project or 'service'}\"`")
        except Exception as e:
            logger.error(f"❌ Error confirming payment: {e}", exc_info=True)
            await ctx.send(f"❌ Error: {str(e)[:100]}")

    @confirm_payment_command.error
    async def confirm_payment_error(ctx, error):
        """处理 confirm-payment 命令的错误"""
        if isinstance(error, discord.ext.commands.errors.UserNotFound):
            await ctx.send(
                '❌ User not found! Please use a real @mention (click the username to mention them).\nExample: `!confirm-payment @username 15 "50x Rep Sleeve"`')
        elif isinstance(error, discord.ext.commands.errors.MissingRequiredArgument):
            await ctx.send(
                '❌ Missing arguments! Usage: `!confirm-payment @user <amount> "service description"`\nExample: `!confirm-payment @Legend2k26 15 "50x Rep Sleeve"`')
        elif isinstance(error, discord.ext.commands.errors.CheckFailure):
            await ctx.send("❌ This command is only for administrators!")
        else:
            await ctx.send(f"❌ Error: {str(error)[:100]}")

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

    # 初始化识图工具（如果可用）
    if IMAGE_RECOGNIZER_AVAILABLE:
        init_image_recognizer()

    # 启动指标收集定时任务
    if METRICS_AVAILABLE:
        collector = get_metrics_collector()
        async def metrics_collector_loop():
            """每 60 秒收集一次系统指标"""
            while True:
                try:
                    collector.collect()
                    # 每小时清理一次旧指标
                    collector.cleanup_old_metrics(days=7)
                except Exception as e:
                    logger.debug(f"Metrics collection error: {e}")
                await asyncio.sleep(60)
        asyncio.create_task(metrics_collector_loop())
        logger.info("📊 Metrics collector started (60s interval)")

    # 启动知识库管理 Web 服务
    logger.info("🌐 Starting Knowledge Base Admin UI...")
    start_web_server()

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
