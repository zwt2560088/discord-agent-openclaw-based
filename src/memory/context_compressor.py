#!/usr/bin/env python3
"""
上下文摘要/压缩模块

使用场景：
1. 履约频道创建时，压缩原始咨询频道的对话历史
2. 长对话窗口自动压缩，避免上下文过长
3. 用户长期记忆压缩，只保留关键信息
"""

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ConversationTurn:
    """对话轮次"""
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSummary:
    """上下文摘要"""
    original_channel_id: str
    original_channel_name: str
    user_id: str
    created_at: str
    compressed_at: str

    # 核心信息提取
    service_interest: str = ""  # 用户感兴趣的服务
    pricing_discussed: str = ""  # 讨论过的价格
    decisions_made: List[str] = field(default_factory=list)  # 已确认的决策
    open_questions: List[str] = field(default_factory=list)  # 待解答问题
    user_preferences: Dict[str, Any] = field(default_factory=dict)  # 用户偏好

    # 摘要文本
    summary_text: str = ""

    # 统计
    original_turns: int = 0
    compressed_turns: int = 0  # 压缩后等价轮次


class ContextCompressor:
    """
    上下文压缩器

    三层压缩策略：
    1. 快速规则压缩（关键词提取）
    2. 模板压缩（结构化信息提取）
    3. LLM 压缩（高质量摘要，可选）
    """

    # 关键信息模式
    SERVICE_PATTERNS = [
        r'(\d+)\s*x?\s*(Rep Sleeve|Sleeve)',
        r'(\d+)\s*(overall|ovr)',
        r'(badge|badges).*?(grind|farm)',
        r'(level).*?(\d+)',
        r'(vc).*?(buy|purchase)',
        r'(mt).*?(service)',
        r'(max|99|97)\s*(overall|ovr)',
    ]

    PRICING_PATTERNS = [
        r'\$(\d+)',
        r'(\d+)\s*dollars?',
        r'total.*?(\$?\d+)',
        r'price.*?(\$?\d+)',
    ]

    DECISION_PATTERNS = [
        r'(i\'ll|i will|i want|i\'d like|sure|yes|ok)',
        r'(buy|order|purchase|get)',
        r'(confirm|confirmed)',
    ]

    def __init__(self, llm_client=None, db_path: str = None):
        """
        Args:
            llm_client: 可选的 LLM 客户端（用于高质量摘要）
            db_path: SQLite 数据库路径
        """
        self.llm_client = llm_client
        self.db_path = db_path or os.path.join(
            Path(__file__).parent.parent, "data", "context_summaries.db"
        )
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS context_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def compress_for_fulfillment(
        self,
        conversations: List[ConversationTurn],
        original_channel_id: str,
        original_channel_name: str,
        user_id: str,
        use_llm: bool = False
    ) -> ContextSummary:
        """
        为履约频道压缩对话历史

        Args:
            conversations: 原始对话列表
            original_channel_id: 原频道 ID
            original_channel_name: 原频道名称
            user_id: 用户 ID
            use_llm: 是否使用 LLM 生成高质量摘要

        Returns:
            ContextSummary: 压缩后的上下文摘要
        """
        now = datetime.now().isoformat()

        summary = ContextSummary(
            original_channel_id=original_channel_id,
            original_channel_name=original_channel_name,
            user_id=user_id,
            created_at=conversations[0].timestamp if conversations else now,
            compressed_at=now,
            original_turns=len(conversations)
        )

        # ===== 第一层：快速规则压缩 =====
        all_text = "\n".join([f"{c.role}: {c.content}" for c in conversations])

        # 提取服务兴趣
        services_found = []
        for pattern in self.SERVICE_PATTERNS:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            services_found.extend(matches)
        summary.service_interest = ", ".join([str(s) for s in services_found[:5]]) if services_found else "General inquiry"

        # 提取价格讨论
        prices_found = []
        for pattern in self.PRICING_PATTERNS:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            prices_found.extend(matches)
        summary.pricing_discussed = ", ".join([f"${p}" for p in prices_found[:3]]) if prices_found else "Not discussed"

        # 提取决策
        decisions = []
        for i, turn in enumerate(conversations):
            if turn.role == "user":
                for pattern in self.DECISION_PATTERNS:
                    if re.search(pattern, turn.content, re.IGNORECASE):
                        decisions.append(f"Turn {i+1}: User expressed intent")
                        break
        summary.decisions_made = decisions[:5]

        # ===== 第二层：结构化模板压缩 =====
        # 提取用户问题
        questions = []
        for turn in conversations:
            if turn.role == "user" and "?" in turn.content:
                questions.append(turn.content[:100])
        summary.open_questions = questions[:3]

        # ===== 第三层：LLM 压缩（可选） =====
        if use_llm and self.llm_client:
            summary.summary_text = self._llm_summarize(all_text)
        else:
            summary.summary_text = self._template_summarize(summary, all_text)

        summary.compressed_turns = 1  # 压缩后等价于 1 轮对话

        # 持久化
        self._save_summary(summary)

        logger.info(f"📝 上下文压缩完成: {original_channel_name} → {summary.original_turns} turns 压缩为摘要")
        return summary

    def _template_summarize(self, summary: ContextSummary, all_text: str) -> str:
        """模板化摘要生成"""
        lines = [
            f"📋 **客户咨询摘要** (原频道: {summary.original_channel_name})",
            "",
            f"**感兴趣的服务**: {summary.service_interest}",
            f"**讨论价格**: {summary.pricing_discussed}",
        ]

        if summary.decisions_made:
            lines.append(f"**客户决策**: {'; '.join(summary.decisions_made)}")

        if summary.open_questions:
            lines.append(f"**待确认问题**: {'; '.join(summary.open_questions[:2])}")

        # 提取最后几轮关键对话
        lines.append("")
        lines.append("**关键对话片段**:")
        lines.append(all_text[-500:] if len(all_text) > 500 else all_text)

        return "\n".join(lines)

    def _llm_summarize(self, all_text: str) -> str:
        """使用 LLM 生成摘要"""
        if not self.llm_client:
            return ""

        try:
            prompt = f"""请将以下客服对话压缩为简洁的摘要，重点提取：
1. 客户想要购买的服务
2. 讨论过的价格
3. 客户的决策或倾向
4. 待确认的问题

对话内容：
{all_text[:2000]}

请用 2-3 句话概括："""

            # 假设 llm_client 有 chat 方法
            response = self.llm_client.chat(prompt)
            return response
        except Exception as e:
            logger.error(f"LLM 摘要失败: {e}")
            return ""

    def _save_summary(self, summary: ContextSummary):
        """保存摘要到数据库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO context_summaries (original_channel_id, user_id, summary_json)
                    VALUES (?, ?, ?)
                ''', (
                    summary.original_channel_id,
                    summary.user_id,
                    json.dumps({
                        "original_channel_name": summary.original_channel_name,
                        "service_interest": summary.service_interest,
                        "pricing_discussed": summary.pricing_discussed,
                        "decisions_made": summary.decisions_made,
                        "open_questions": summary.open_questions,
                        "summary_text": summary.summary_text,
                        "original_turns": summary.original_turns,
                        "compressed_at": summary.compressed_at
                    }, ensure_ascii=False)
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"保存摘要失败: {e}")

    def get_summary_for_channel(self, channel_id: str) -> Optional[ContextSummary]:
        """获取频道的压缩摘要"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT original_channel_id, user_id, summary_json
                    FROM context_summaries
                    WHERE original_channel_id = ?
                    ORDER BY created_at DESC LIMIT 1
                ''', (channel_id,))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[2])
                    return ContextSummary(
                        original_channel_id=row[0],
                        original_channel_name=data.get("original_channel_name", ""),
                        user_id=row[1],
                        created_at="",
                        compressed_at=data.get("compressed_at", ""),
                        service_interest=data.get("service_interest", ""),
                        pricing_discussed=data.get("pricing_discussed", ""),
                        decisions_made=data.get("decisions_made", []),
                        open_questions=data.get("open_questions", []),
                        summary_text=data.get("summary_text", ""),
                        original_turns=data.get("original_turns", 0)
                    )
        except Exception as e:
            logger.error(f"获取摘要失败: {e}")
        return None

    def compress_long_conversation(
        self,
        conversations: List[ConversationTurn],
        max_turns: int = 20,
        keep_recent: int = 5
    ) -> Tuple[List[ConversationTurn], str]:
        """
        压缩长对话，保留最近 N 轮 + 历史摘要

        Args:
            conversations: 原始对话
            max_turns: 触发压缩的阈值
            keep_recent: 保留最近 N 轮

        Returns:
            (压缩后的对话列表, 历史摘要文本)
        """
        if len(conversations) <= max_turns:
            return conversations, ""

        # 保留最近的对话
        recent = conversations[-keep_recent:]
        to_compress = conversations[:-keep_recent]

        # 压缩历史
        history_text = "\n".join([f"{c.role}: {c.content}" for c in to_compress])
        summary = f"📚 **历史对话摘要** ({len(to_compress)} 轮):\n"

        # 提取关键信息
        for pattern in self.SERVICE_PATTERNS:
            matches = re.findall(pattern, history_text, re.IGNORECASE)
            if matches:
                summary += f"- 服务意向: {matches[0]}\n"
                break

        for pattern in self.PRICING_PATTERNS:
            matches = re.findall(pattern, history_text, re.IGNORECASE)
            if matches:
                summary += f"- 价格讨论: ${matches[0]}\n"
                break

        logger.info(f"📊 长对话压缩: {len(conversations)} → {keep_recent} turns + summary")
        return recent, summary


# ===== 集成到 discord_bot_final.py 的辅助函数 =====

async def create_fulfillment_context(
    original_channel_id: str,
    original_channel_name: str,
    user_id: str,
    channel_history: List[Dict[str, Any]],
    llm_client=None
) -> str:
    """
    创建履约频道时，生成上下文摘要

    Args:
        original_channel_id: 原频道 ID
        original_channel_name: 原频道名称
        user_id: 用户 ID
        channel_history: 频道历史记录 [{"role": "user/assistant", "content": "..."}, ...]
        llm_client: 可选 LLM 客户端

    Returns:
        格式化的摘要文本，用于注入履约频道上下文
    """
    compressor = ContextCompressor(llm_client=llm_client)

    # 转换格式
    conversations = [
        ConversationTurn(
            role=h.get("role", "user"),
            content=h.get("content", ""),
            timestamp=h.get("timestamp", "")
        )
        for h in channel_history
    ]

    summary = compressor.compress_for_fulfillment(
        conversations=conversations,
        original_channel_id=original_channel_id,
        original_channel_name=original_channel_name,
        user_id=user_id,
        use_llm=(llm_client is not None)
    )

    return summary.summary_text


# ===== 测试代码 =====
if __name__ == "__main__":
    # 模拟对话
    test_conversations = [
        ConversationTurn(role="user", content="Hi, I'm interested in your services"),
        ConversationTurn(role="assistant", content="Hello! We offer Rep Sleeves, Level boosts, and more. What are you looking for?"),
        ConversationTurn(role="user", content="How much for 50x Rep Sleeves?"),
        ConversationTurn(role="assistant", content="50x Rep Sleeves would be $15. We can also do 100x for $25."),
        ConversationTurn(role="user", content="I'll take the 100x option. Also need Level 40 boost"),
        ConversationTurn(role="assistant", content="Great! Level 40 boost is $10. Total would be $35 for both."),
        ConversationTurn(role="user", content="Sounds good, I'll pay now. What payment methods?"),
        ConversationTurn(role="assistant", content="We accept PayPal, Crypto, and CashApp. Which do you prefer?"),
        ConversationTurn(role="user", content="PayPal works. Let me send the payment."),
    ]

    compressor = ContextCompressor()
    summary = compressor.compress_for_fulfillment(
        conversations=test_conversations,
        original_channel_id="123456789",
        original_channel_name="inquiry-john",
        user_id="987654321"
    )

    print("\n" + "=" * 60)
    print(summary.summary_text)
    print("=" * 60)
    print(f"Original turns: {summary.original_turns}")
    print(f"Service interest: {summary.service_interest}")
    print(f"Pricing discussed: {summary.pricing_discussed}")
    print(f"Decisions: {summary.decisions_made}")

