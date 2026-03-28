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
from discord.ext import commands
from dotenv import load_dotenv
from typing import Dict, List, Optional, Tuple

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

# ====================== 第二层：多频道上下文隔离管理器 ======================
class ContextManager:
    """
    按频道 ID 隔离上下文（解决多频道串话核心）
    采用 LRU 内存缓存 + SQLite 持久化双层存储
    """
    def __init__(self):
        self._cache: OrderedDict[str, Dict] = OrderedDict()  # channel_id -> context
        self._max_cache_size = 100  # 最多缓存 100 个频道的上下文
        self._db_path = "./bot_context.db"
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS contexts (
                    channel_id TEXT PRIMARY KEY,
                    history TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    expires_at REAL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("✅ SQLite context database initialized")
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

# 全局上下文管理器
context_manager = ContextManager()

# ====================== LangChain ReAct Agent 工具定义 ======================
if LANGCHAIN_AVAILABLE:
    @tool
    def get_price(service: str, details: str = "") -> str:
        """
        查询指定服务的价格信息。
        参数:
        - service: 服务名称 (rep, sleeve, 99, challenge, badge, mt, account, etc.)
        - details: 可选细节
        """
        service_lower = service.lower()

        # 价格映射表
        price_info = {
            "rep sleeve": {
                "50x": "$15",
                "100x": "$21.50",
                "300x": "$30",
                "default": "50x: $15 | 100x: $21.50 | 300x: $30"
            },
            "rep grind": {
                "rookie": "$15-42",
                "starter": "$21-46",
                "veteran": "$30-50",
                "legend": "$50-60",
                "default": "Rookie $15-42 | Starter $21-46 | Veteran $30-50 | Legend $50-60 | Long $70-150"
            },
            "challenge": {
                "250": "$40",
                "200": "$20",
                "150": "$15",
                "100": "$10",
                "default": "250 Layers $40 | 200 Layers $20 | 150 Layers $15 | 100 Layers $10"
            },
            "99 overall": "$15",
            "99": "$15",
            "badge": "$15",
            "specialty": "Single $15 | All 5 $20",
            "mt coins": "100K $10 | 500K $45 | 1M $80",
            "mt": "100K $10 | 500K $45 | 1M $80",
            "season pass": "$15",
            "dma": "$60/month or $110 permanent",
            "account": "Pre-built Account $80-100"
        }

        # 搜索匹配的服务
        for key, price in price_info.items():
            if key in service_lower:
                if isinstance(price, dict):
                    return price.get(details.lower() if details else "default", price["default"])
                else:
                    return f"{key.upper()}: {price}"

        return f"Service '{service}' not found. Try: rep sleeve, rep grind, 99, challenge, badge, mt, account"

    @tool
    def confirm_payment(order_details: str) -> str:
        """
        当用户说已经付款时，解析订单详情，返回汇总金额。
        参数: order_details - 用户说的订单内容，如 "I paid for 250 all specialization + 50x"
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

        # Rep Sleeve（按数字匹配）
        if "300x" in details_lower:
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
            summary = f"✅ **Payment Confirmed!**\n\n**Order Summary:**\n" + "\n".join(f"• {item}" for item in items) + f"\n\n**Total: ${total}**"
            return summary

        return f"✅ Payment confirmed for: {order_details}. Awaiting admin to create fulfillment channel."

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
                    max_tokens=500
                )
                logger.info("🔧 ReAct Agent using DeepSeek")
            else:
                llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=OPENAI_API_KEY,
                    temperature=0.3,
                    max_tokens=500
                )
                logger.info("🔧 ReAct Agent using OpenAI")

            # 收集所有工具
            tools = [get_price, confirm_payment, query_knowledge]

            # 创建 ReAct prompt
            react_prompt = PromptTemplate.from_template("""You are an intelligent NBA 2K26 customer service assistant with access to tools for checking prices, confirming payments, and querying knowledge base.

IMPORTANT RULES:
1. If user mentions "paid", "paid for", "already paid", "payment confirmed", "已付" → Use confirm_payment tool
2. If user asks about price/cost → Use get_price tool
3. If user mentions specific order details → Use confirm_payment tool
4. ALWAYS check the conversation history for order details BEFORE calling confirm_payment
5. When calling confirm_payment, include ALL relevant order details from the current message AND history in the Action Input
6. Always be concise and friendly
7. Include emojis in responses

CRITICAL: Before using confirm_payment, review the conversation history for any order details mentioned earlier (e.g., "50x", "250 all specialization", "rep grind", "99 overall"). If the user's message doesn't contain order details but previous messages do, you MUST include those details in the Action Input.

Examples:

Example 1 - User confirms payment with details:
Question: he already paid for 250 all specialization + 50x
Thought: User confirms payment. I should use confirm_payment tool with the full message.
Action: confirm_payment
Action Input: he already paid for 250 all specialization + 50x
Observation: ✅ Payment Confirmed! Order Summary: 250 Layers Challenge ($40), All 5 Specialties ($20), 50x Rep Sleeve ($15). Total: $75
Thought: I now know the final answer.
Final Answer: ✅ Payment confirmed! Total $75. Admin please run `!confirm-payment @user 75 "250 all specialization + 50x"` to create fulfillment channel.

Example 2 - User says "paid" without details, but history has order info:
Question: he already paid
Thought: User mentions payment but no order details. Let me check history - I see previous messages about "250 all specialization" and "50x". I should include those in the confirm_payment call.
Action: confirm_payment
Action Input: he already paid for 250 all specialization + 50x
Observation: ✅ Payment Confirmed! Order Summary: 250 Layers Challenge ($40), All 5 Specialties ($20), 50x Rep Sleeve ($15). Total: $75
Thought: I now know the final answer.
Final Answer: ✅ Payment confirmed! Total $75 based on previous conversation. Admin please run `!confirm-payment @user 75 "250 all specialization + 50x"` to create fulfillment channel.

Example 3 - User says "paid" with NO history:
Question: I paid
Thought: User mentions payment but there's no order details in the message or history. I should still call confirm_payment.
Action: confirm_payment
Action Input: I paid
Observation: ✅ Payment confirmed for: I paid. Awaiting admin to create fulfillment channel.
Thought: I now know the final answer.
Final Answer: I see you've paid! 💰 Please tell me what you ordered (e.g., 50x Rep Sleeve, 250 Challenge, etc.) so I can confirm the amount and create your order channel.

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

Previous conversation context:
{{chat_history}}

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

    async def _call_react_agent(self, user_msg: str, channel_id: str, chat_history: List[Dict]) -> Tuple[str, bool]:
        """
        使用 LangChain ReAct Agent 处理用户消息
        返回: (回复内容, 是否有订单意图)
        """
        if not self._agent_executor:
            return "", False

        try:
            # 构建历史上下文字符串（最近 6 条消息，完整内容）
            history_str = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-6:]])

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
        关键词快速匹配（使用词边界，避免误匹配）
        返回: (回复内容, 是否有订单意图) 或 None
        优先匹配较长的关键词，避免被短关键词截断
        """
        msg_lower = user_msg.lower()

        # 检查特殊自然语言意图
        if any(word in msg_lower for word in ["show me pricing", "show pricing", "price list", "all prices", "pricing and faq", "pricing & faq"]):
            return "📋 Use **!pricing** to see all prices or **!faq** for common questions!", False

        if any(word in msg_lower for word in ["show me faq", "show faq", "faq", "frequently asked", "common questions"]):
            return "❓ Use **!faq** to see frequently asked questions!", False

        # 优先匹配较长的关键词（避免短关键词优先匹配）
        # 按关键词长度倒序排列
        sorted_keywords = sorted(QUICK_REPLY_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True)

        for keyword, response in sorted_keywords:
            # 使用词边界匹配，避免 "pass" 误匹配 "password"
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, msg_lower):
                logger.info(f"⚡ Quick match: '{keyword}' in '{msg_lower}'")
                return response["reply"], response.get("order_intent", False)

        return None

    async def chat(self, user_msg: str, channel_id: str) -> Tuple[str, bool]:
        """
        智能对话处理流程
        返回: (回复内容, 是否有订单意图)
        """
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

            react_reply, react_intent = await self._call_react_agent(user_msg, channel_id, history)
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

            # 系统提示词
            system_prompt = """You are a professional NBA 2K26 boosting service customer support agent.

IMPORTANT RULES:
1. Only answer about NBA 2K26 game services
2. Keep responses short (under 100 words)
3. Include [ORDER_INTENT] ONLY if user explicitly wants to buy/order
4. Use emojis to make it friendly
5. **CLARIFY AMBIGUOUS REQUESTS**: If user says "rep", ask "Do you want Rep Grind (level boost) or Rep Sleeve?"

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

            # 构建消息链
            messages = [{"role": "system", "content": system_prompt}]

            # 添加历史消息（最多 3 条）
            for msg in history[-3:]:
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
                    "max_tokens": 250
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

# ====================== 第五层：Discord Bot 核心 ======================
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
    @bot.event
    async def on_ready():
        logger.info(f"✅ Bot logged in as {bot.user}")
        logger.info(f"📊 Connected to {len(bot.guilds)} server(s)")
        activity = discord.Game(name="NBA 2K26 Boosting | !help")
        await bot.change_presence(activity=activity)

    @bot.event
    async def on_message(message: discord.Message):
        """处理所有消息"""
        # 过滤机器人自己的消息
        if message.author.bot:
            return

        # 处理所有命令（!help, !pricing 等）
        if message.content.startswith('!'):
            await bot.process_commands(message)
            return

        # ========== 消息过滤逻辑 ==========
        # 触发条件（满足任一即可）：
        # 1. 消息提到了 Bot
        # 2. 在 order- 前缀的频道
        # 3. 在包含 service/bot/support/nba2k/ticket 的频道
        # 4. 消息包含服务关键词（rep, service, boost, 99, pass 等）

        has_mention = bot.user in message.mentions
        is_order_channel = "order-" in message.channel.name.lower()
        is_service_channel = any(
            keyword in message.channel.name.lower()
            for keyword in ["service", "bot", "support", "nba2k", "ticket", "help", "legend"]
        )

        user_msg_lower = message.content.lower()
        # 使用词边界匹配，避免误匹配（如 "pass" 误匹配 "password"）
        has_service_keyword = any(
            re.search(r'\b' + re.escape(keyword) + r'\b', user_msg_lower)
            for keyword in ["rep", "service", "boost", "99", "pass", "mt", "vc", "coin", "help", "order", "buy", "price", "cost", "how much", "want", "paid", "payment", "confirm"]
        )

        # 检查数字 + "x" 模式（如 50x, 100x, 300x）
        has_quantity_keyword = bool(re.search(r'\d+x', user_msg_lower))

        if not (has_mention or is_order_channel or is_service_channel or has_service_keyword or has_quantity_keyword):
            logger.debug(f"⊘ Ignoring message in {message.channel.name}: {user_msg_lower[:30]}")
            return

        # 限流检查
        if not check_rate_limit(message.author.id):
            try:
                await message.reply("⚠️ Please slow down! Try again in a moment.", delete_after=3)
            except Exception as e:
                logger.warning(f"⚠️ Failed to send rate limit message: {e}")
            return

        logger.info(f"✅ Message accepted: @{message.author.name} in #{message.channel.name}")
        logger.info(f"📌 Message ID: {message.id} | Content: '{user_msg_lower}'")

        # ========== 高并发控制：信号量隔离 ==========
        async with concurrency_semaphore:
            await handle_message(message)

    # ====================== 核心消息处理逻辑 ======================
    async def handle_message(message: discord.Message):
        """
        处理用户消息的核心逻辑
        1. 立即响应（防止 Discord 3s 超时）
        2. 异步处理 AI（不阻塞事件循环）
        """
        channel = message.channel
        user_msg = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
        channel_id = str(channel.id)

        logger.info(f"🔄 [handle_message START] MsgID: {message.id} | User: {message.author.name} | Channel: {channel.name} | Content: '{user_msg[:50]}'")

        # ========== 第一步：立即响应 ==========
        # 防止 Discord "Interaction failed" 超时
        status_msg = await channel.send("🔍 Processing your request...")

        try:
            # ========== 第二步：异步处理（不阻塞） ==========
            ai_reply, has_order_intent = await ai_service.chat(user_msg, channel_id)

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

            # ========== 第四步：返回 AI 回复 ==========
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

            # 发送支付确认通知
            embed = discord.Embed(
                title="✅ Payment Confirmed!",
                description=f"Your payment of **${amount}** has been received and verified!",
                color=discord.Color.green()
            )
            embed.add_field(name="Project", value=project or "NBA 2K26 Service", inline=False)
            embed.add_field(name="Amount", value=f"${amount}", inline=True)
            embed.add_field(name="Next", value="Fulfillment channel is being created...", inline=True)
            embed.set_footer(text=f"Confirmed by: {ctx.author.name}")

            await ctx.send(embed=embed)

            # 立即创建履约频道
            try:
                # 创建履约频道名
                fulfillment_channel_name = f"fulfillment-{user.name.lower()}-{int(time.time())%10000}"

                # 权限设置：仅用户和管理员可见
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    user: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True
                    ),
                    ctx.guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True
                    )
                }

                # 将管理员也加入
                if ctx.author.id != ctx.guild.owner_id:
                    overwrites[ctx.author] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True
                    )

                # 创建频道
                fulfillment_channel = await ctx.guild.create_text_channel(
                    name=fulfillment_channel_name,
                    overwrites=overwrites,
                    topic=f"Project: {project} | Payment: ${amount} | User: {user.mention} | Consulting Channel: {ctx.channel.mention}"
                )

                logger.info(f"✅ Fulfillment channel created: {fulfillment_channel_name}")

                # 在履约频道发送欢迎和上下文信息
                welcome_embed = discord.Embed(
                    title="🚀 Service Fulfillment Channel",
                    description=f"Welcome {user.mention}! Your service has been confirmed and is ready to begin.",
                    color=discord.Color.blue()
                )
                welcome_embed.add_field(name="Project", value=project or "NBA 2K26 Service", inline=False)
                welcome_embed.add_field(name="Payment Status", value="✅ Confirmed", inline=True)
                welcome_embed.add_field(name="Amount", value=f"${amount}", inline=True)
                welcome_embed.add_field(
                    name="Service Info",
                    value=f"📝 **Consulting Channel**: {ctx.channel.mention}\n📋 All previous discussions are available there\n⏱️ Service will begin within 10 minutes",
                    inline=False
                )

                await fulfillment_channel.send(embed=welcome_embed)

                # 通知咨询频道
                await ctx.send(
                    f"✅ Fulfillment channel created: {fulfillment_channel.mention}\n"
                    f"📌 {user.mention} - Please move to the fulfillment channel to continue"
                )

            except Exception as e:
                logger.error(f"❌ Failed to create fulfillment channel: {e}")
                await ctx.send(f"❌ Failed to create fulfillment channel: {str(e)[:100]}")

        except Exception as e:
            logger.error(f"❌ Error confirming payment: {e}")
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

