#!/usr/bin/env python3
"""
Supervisor Agent — 多 Agent 路由决策层

基于 Supervisor 模式实现多 Agent 协作架构：
    Supervisor（本模块）→ 客服 Agent（含订单/售后） / 支付审核 Agent

设计原则：
    - 按输入模态和职责边界拆分，而非按业务类型硬拆
    - 客服/订单/售后本质都是「理解意图 → 选工具 → 执行」的同构流程，合一处理
    - 支付审核独立：需要图片输入(OCR) + 规则引擎交叉验证 + 触发自动建频道工作流
    - Supervisor 用 DeepSeek 轻量路由，下游 Agent 按需选模型
"""

import aiohttp
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DiscordBot.SupervisorAgent")


class AgentRoute(Enum):
    """Agent 路由目标"""
    QUICK_REPLY = "quick_reply"     # 关键词快速回复 / 缓存命中（不调 LLM）
    CUSTOMER_SERVICE = "cs"          # 客服 Agent（RAG 检索 + 咨询 + 下单 + 查单 + 售后）
    PAYMENT_REVIEW = "payment"       # 支付审核 Agent（OCR + LLM + 规则双引擎交叉验证）
    GENERAL = "general"              # 通用 LLM 兜底


@dataclass
class RouteDecision:
    """Supervisor 路由决策结果"""
    route: AgentRoute
    confidence: float = 0.0
    reason: str = ""
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    image_url: Optional[str] = None  # 仅 PAYMENT_REVIEW 时有值


class SupervisorAgent:
    """
    Supervisor Agent — 多 Agent 协作的路由决策层

    架构:
    ┌──────────────────────────────────────────────┐
    │              Supervisor Agent                 │
    │  (意图分析 → 复杂度评估 → 路由分发)          │
    └──────┬──────────────────┬────────────────────┘
           │                  │
     ┌─────▼─────┐     ┌──────▼──────────┐
     │  客服 Agent │     │ 支付审核 Agent   │
     │ (文本意图)  │     │ (图片+文本)     │
     │ 咨询/下单  │     │ OCR+LLM+规则    │
     │ 查单/售后  │     │ 双引擎交叉验证  │
     └───────────┘     └─────────────────┘
    """

    # 路由规则 — 按优先级排列
    _ROUTE_RULES: List[Dict[str, Any]] = [
        {
            "route": AgentRoute.PAYMENT_REVIEW,
            "keywords": [
                "paid", "already paid", "sent the money", "payment sent",
                "money sent", "i paid", "已付", "payment screenshot",
                "proof of payment", "receipt", "payment confirmed",
            ],
            "min_confidence": 0.7,
        },
        {
            "route": AgentRoute.CUSTOMER_SERVICE,
            "keywords": [
                # 咨询
                "price", "pricing", "cost", "how much", "cheap", "expensive",
                "service", "boosting", "boost", "level", "badge", "vc",
                "safe", "ban", "risk", "security", "faq", "help",
                "what do you offer", "available", "rep", "sleeve", "mods", "dma",
                "99", "overall", "upgrade", "challenge", "mt", "coins",
                # 下单
                "order", "buy", "purchase", "want to order", "place order",
                "create order", "i want", "need", "get me", "order now",
                "start order", "let's go", "im ready", "i'm ready",
                # 查单
                "status", "track", "my order", "check order",
                # 售后
                "refund", "cancel", "complaint", "progress", "how long",
                "when will", "delayed", "didn't receive",
            ],
            "min_confidence": 0.5,
        },
    ]

    def __init__(self):
        self.deepseek_api_key = os.getenv("deepseek_api_key")
        self.deepseek_base_url = os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self._route_stats = {r.value: 0 for r in AgentRoute}
        self._total_routes = 0

        logger.info("✅ SupervisorAgent initialized")

    async def route(
        self,
        user_msg: str,
        has_image: bool = False,
        image_url: Optional[str] = None,
    ) -> RouteDecision:
        """
        分析用户消息并决定路由

        Args:
            user_msg: 用户消息文本
            has_image: 消息是否包含图片
            image_url: 图片 URL

        Returns:
            RouteDecision
        """
        msg_lower = user_msg.lower().strip()

        # ── 纯图片消息 → 支付审核 Agent ──
        if has_image and (not msg_lower or len(msg_lower) < 10):
            return self._record_route(RouteDecision(
                route=AgentRoute.PAYMENT_REVIEW,
                confidence=0.9,
                reason="Image-only message, routing to Payment Review Agent",
                image_url=image_url,
            ))

        if not msg_lower and not has_image:
            return self._record_route(RouteDecision(
                route=AgentRoute.GENERAL, confidence=0.0, reason="Empty message"
            ))

        # ── 规则引擎：关键词匹配 ──
        for rule in self._ROUTE_RULES:
            matched_keywords = [kw for kw in rule["keywords"] if kw in msg_lower]
            if matched_keywords:
                # 置信度 = 匹配关键词数量 / 该规则总关键词数 × 基础系数
                confidence = min(len(matched_keywords) / max(len(rule["keywords"]), 1) * 2.0, 1.0)
                confidence = max(confidence, rule["min_confidence"])

                entities = {}
                if rule["route"] == AgentRoute.PAYMENT_REVIEW and has_image:
                    entities["has_image"] = True
                    confidence = min(confidence + 0.15, 1.0)  # 有图片的付款意图更可信

                return self._record_route(RouteDecision(
                    route=rule["route"],
                    confidence=round(confidence, 2),
                    reason=f"Keyword match: {matched_keywords[:3]}",
                    extracted_entities=entities,
                    image_url=image_url if rule["route"] == AgentRoute.PAYMENT_REVIEW else None,
                ))

        # ── LLM 路由：关键词未匹配的模糊意图 ──
        if self.deepseek_api_key or self.openai_api_key:
            try:
                llm_decision = await self._llm_route(user_msg, has_image, image_url)
                return self._record_route(llm_decision)
            except Exception as e:
                logger.warning(f"⚠️ LLM route failed, fallback: {e}")

        return self._record_route(RouteDecision(
            route=AgentRoute.GENERAL, confidence=0.3, reason="No match, fallback"
        ))

    async def _llm_route(
        self,
        user_msg: str,
        has_image: bool,
        image_url: Optional[str] = None,
    ) -> RouteDecision:
        """LLM 辅助路由 — 仅在关键词无法匹配时调用"""
        prompt = (
            "You are a routing classifier for a NBA 2K26 game service Discord bot.\n"
            "Classify the user message into ONE of these categories:\n"
            "- 'cs': Customer service (pricing inquiry, service info, general questions, order creation, order status, after-sales)\n"
            "- 'payment': User is confirming they made a payment or sending a payment screenshot\n"
            "- 'general': Off-topic or unclear message\n\n"
            f"User message: {user_msg}\n"
            f"Has image: {has_image}\n\n"
            "Reply with ONLY a JSON: {\"route\": \"cs\"|\"payment\"|\"general\", \"confidence\": 0.0-1.0, \"reason\": \"brief explanation\"}"
        )

        api_key = self.deepseek_api_key or self.openai_api_key
        base_url = self.deepseek_base_url if self.deepseek_api_key else "https://api.openai.com/v1"

        timeout = aiohttp.ClientTimeout(total=5, connect=2, sock_read=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat" if self.deepseek_api_key else "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 100,
            }
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"API error {resp.status}")
                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # 解析 JSON（兼容 markdown 代码块包裹）
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]

                result = json.loads(content)
                route_map = {
                    "cs": AgentRoute.CUSTOMER_SERVICE,
                    "payment": AgentRoute.PAYMENT_REVIEW,
                    "general": AgentRoute.GENERAL,
                }
                route = route_map.get(result.get("route", "general"), AgentRoute.GENERAL)

                return RouteDecision(
                    route=route,
                    confidence=float(result.get("confidence", 0.5)),
                    reason=result.get("reason", "LLM classified"),
                    image_url=image_url if route == AgentRoute.PAYMENT_REVIEW else None,
                )

    def _record_route(self, decision: RouteDecision) -> RouteDecision:
        """记录路由统计"""
        self._route_stats[decision.route.value] = self._route_stats.get(decision.route.value, 0) + 1
        self._total_routes += 1
        logger.info(
            f"🔀 Supervisor route: {decision.route.value} "
            f"(conf={decision.confidence:.2f}, reason={decision.reason})"
        )
        return decision

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计（供监控使用）"""
        return {
            "total_routes": self._total_routes,
            "distribution": dict(self._route_stats),
        }


# ==================== 全局单例 ====================

_supervisor: Optional[SupervisorAgent] = None


def get_supervisor() -> SupervisorAgent:
    """获取 Supervisor Agent 单例"""
    global _supervisor
    if _supervisor is None:
        _supervisor = SupervisorAgent()
    return _supervisor

