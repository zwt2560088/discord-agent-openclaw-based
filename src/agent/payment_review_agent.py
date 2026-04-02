#!/usr/bin/env python3
"""
Payment Review Agent — 支付审核 Agent

独立于客服 Agent 的专职审核 Agent，负责：
1. OCR 识别支付截图中的金额信息
2. LLM 语义理解截图内容（验证是否为真实支付凭证）
3. 规则引擎硬性校验（金额匹配、时效性、重复提交检测）
4. 双引擎交叉验证：LLM 判断 + 规则引擎 → APPROVE / REJECT / MANUAL_REVIEW

设计理念：
    - 审核是一种「质量关卡」角色，需要独立于客服 Agent
    - 输入模态不同（图片 vs 纯文本），需要 OCR 能力
    - 审核失败需走人工兜底，异常截图自动打标入库
"""

import aiohttp
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("DiscordBot.PaymentReviewAgent")


# ==================== 审核结果 ====================

class ReviewVerdict(Enum):
    """审核结论"""
    APPROVE = "approve"            # 自动通过
    REJECT = "reject"              # 明确拒绝（截图伪造 / 金额不匹配 / 重复提交）
    MANUAL_REVIEW = "manual"       # 需人工复核（截图模糊 / 无法确定 / 异常情况）
    NO_IMAGE = "no_image"          # 无图片可审核


@dataclass
class ReviewResult:
    """审核结果"""
    verdict: ReviewVerdict
    confidence: float = 0.0
    reason: str = ""
    extracted_amount: Optional[float] = None   # OCR 识别的金额
    ocr_text: str = ""                          # OCR 原始文本
    rule_checks: Dict[str, Any] = field(default_factory=dict)
    llm_analysis: str = ""                      # LLM 分析结果
    latency_ms: float = 0.0


# ==================== Payment Review Agent ====================

class PaymentReviewAgent:
    """
    支付审核 Agent — OCR + LLM + 规则引擎双引擎交叉验证

    审核流程:
    ┌─────────────────────────────────────────────────────┐
    │           Payment Review Agent                       │
    │                                                      │
    │  输入: 支付截图 URL + 用户消息 + 频道上下文          │
    │                                                      │
    │  1️⃣ OCR 识别 → 提取金额/支付方式/收款方             │
    │  2️⃣ 规则引擎 → 金额匹配 + 时效性 + 去重检测         │
    │  3️⃣ LLM 语义分析 → 截图真实性 + 异常模式检测        │
    │  4️⃣ 交叉验证 → APPROVE / REJECT / MANUAL_REVIEW     │
    │                                                      │
    │  输出: ReviewResult                                  │
    └─────────────────────────────────────────────────────┘
    """

    # 金额正则（覆盖 $15, $15.00, $1,000 等格式）
    _AMOUNT_PATTERNS = [
        r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",  # $15, $1,000.00
        r"(\d{1,3}(?:,\d{3})*(?:\.\d{2}))\s*(?:USD|usd)",  # 15.00 USD
        r"(?:total|amount|paid)\s*[:：]?\s*\$?\s*(\d+(?:\.\d{2})?)",  # total: $15
    ]

    # 支付方式关键词
    _PAYMENT_KEYWORDS = {
        "paypal": ["paypal", "paypal.me"],
        "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "usdt", "usdc"],
        "cashapp": ["cash app", "cashapp", "$cashtag"],
        "venmo": ["venmo"],
        "credit_card": ["visa", "mastercard", "amex", "card"],
    }

    # 可疑模式（伪造/篡改风险信号）
    _SUSPICIOUS_PATTERNS = [
        r"screenshot\s+(edited|modified|fake)",
        r"(photoshop|ps|edited)",
        r"(fake|forged|counterfeit)",
        r"(test|demo|sample)\s*(payment|transaction)",
        r"pending\s*(?:and|&)?\s*not\s*(?:yet\s*)?completed",
    ]

    def __init__(self):
        self.deepseek_api_key = os.getenv("deepseek_api_key")
        self.deepseek_base_url = os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # 审核/OCR 依赖（延迟导入）
        self._image_recognizer = None
        self._ocr_available = False

        # 统计
        self._review_stats = {v.value: 0 for v in ReviewVerdict}
        self._total_reviews = 0

        logger.info("✅ PaymentReviewAgent initialized")

    def _ensure_ocr(self):
        """延迟加载 OCR 依赖"""
        if not self._ocr_available:
            try:
                from image_recognizer import image_recognizer
                self._image_recognizer = image_recognizer
                self._ocr_available = image_recognizer is not None
                if self._ocr_available:
                    logger.info("✅ PaymentReviewAgent: OCR loaded")
            except ImportError:
                logger.warning("⚠️ PaymentReviewAgent: image_recognizer not available")

    async def review(
        self,
        user_msg: str = "",
        image_url: Optional[str] = None,
        expected_amount: Optional[float] = None,
        expected_service: Optional[str] = None,
        channel_id: str = "",
        user_id: str = "",
    ) -> ReviewResult:
        """
        执行支付审核

        Args:
            user_msg: 用户消息（可能包含支付说明）
            image_url: 支付截图 URL
            expected_amount: 期望金额（从历史上下文中提取）
            expected_service: 期望服务描述
            channel_id: 频道 ID
            user_id: 用户 ID

        Returns:
            ReviewResult
        """
        start_time = time.time()

        # ── 前置检查：无图片 ──
        if not image_url:
            self._record_stats(ReviewVerdict.NO_IMAGE)
            return ReviewResult(
                verdict=ReviewVerdict.NO_IMAGE,
                reason="No image provided for review",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # ── Step 1: OCR 识别 ──
        self._ensure_ocr()
        ocr_text = ""
        extracted_amount = None
        detected_payment_method = None

        if self._ocr_available and self._image_recognizer:
            try:
                image = await self._image_recognizer.download_image(image_url)
                if image:
                    ocr_text = self._image_recognizer.ocr_extract_text(image)
                    business_info = self._image_recognizer.extract_business_info(ocr_text)
                    if business_info:
                        ocr_text += f"\n[Business Info: {json.dumps(business_info)}]"
            except Exception as e:
                logger.warning(f"⚠️ OCR failed: {e}")

        # ── Step 2: 规则引擎校验 ──
        rule_checks = {}
        extracted_amount = self._extract_amount(ocr_text, user_msg)

        if extracted_amount is not None:
            rule_checks["amount_extracted"] = True
            rule_checks["extracted_amount"] = extracted_amount

            # 金额匹配校验
            if expected_amount is not None:
                is_match = abs(extracted_amount - expected_amount) < 1.0  # 容差 $1
                rule_checks["amount_match"] = is_match
                rule_checks["expected_amount"] = expected_amount
                rule_checks["diff"] = round(abs(extracted_amount - expected_amount), 2)
            else:
                rule_checks["amount_match"] = None  # 无法校验（无期望金额）
        else:
            rule_checks["amount_extracted"] = False

        # 支付方式识别
        detected_payment_method = self._detect_payment_method(ocr_text, user_msg)
        if detected_payment_method:
            rule_checks["payment_method"] = detected_payment_method

        # 可疑模式检测
        suspicious = self._detect_suspicious(ocr_text, user_msg)
        rule_checks["suspicious_patterns"] = suspicious

        # OCR 文本质量评估
        rule_checks["ocr_quality"] = "good" if len(ocr_text.strip()) > 10 else "poor"

        # ── Step 3: LLM 语义分析 ──
        llm_analysis = ""
        llm_verdict = None
        if self.deepseek_api_key or self.openai_api_key:
            try:
                llm_verdict, llm_analysis = await self._llm_analyze(
                    user_msg=user_msg,
                    ocr_text=ocr_text,
                    extracted_amount=extracted_amount,
                    expected_amount=expected_amount,
                    expected_service=expected_service,
                )
                rule_checks["llm_verdict"] = llm_verdict
            except Exception as e:
                logger.warning(f"⚠️ LLM analysis failed: {e}")

        # ── Step 4: 交叉验证 → 最终判定 ──
        verdict = self._cross_validate(rule_checks, llm_verdict, ocr_text)
        reason = self._build_reason(verdict, rule_checks, llm_analysis, expected_service)

        latency = (time.time() - start_time) * 1000
        self._record_stats(verdict)

        logger.info(
            f"🔍 PaymentReview: verdict={verdict.value}, "
            f"amount={extracted_amount}, conf={rule_checks.get('amount_match')}, "
            f"llm={llm_verdict}, latency={latency:.0f}ms"
        )

        return ReviewResult(
            verdict=verdict,
            confidence=self._calc_confidence(rule_checks, llm_verdict),
            reason=reason,
            extracted_amount=extracted_amount,
            ocr_text=ocr_text[:200] if ocr_text else "",
            rule_checks=rule_checks,
            llm_analysis=llm_analysis,
            latency_ms=round(latency, 1),
        )

    # ==================== OCR 辅助方法 ====================

    def _extract_amount(self, ocr_text: str, user_msg: str) -> Optional[float]:
        """从 OCR 文本和用户消息中提取金额"""
        combined = f"{ocr_text}\n{user_msg}"

        for pattern in self._AMOUNT_PATTERNS:
            matches = re.findall(pattern, combined, re.IGNORECASE)
            if matches:
                try:
                    # 取所有匹配中最合理的金额（排除明显不合理的值）
                    amounts = []
                    for m in matches:
                        cleaned = m.replace(",", "")
                        val = float(cleaned)
                        if 1.0 <= val <= 10000.0:  # 业务合理范围 $1 - $10000
                            amounts.append(val)
                    if amounts:
                        # 优先返回最大的金额（通常是 Total）
                        return max(amounts)
                except ValueError:
                    continue
        return None

    def _detect_payment_method(self, ocr_text: str, user_msg: str) -> Optional[str]:
        """检测支付方式"""
        combined = f"{ocr_text}\n{user_msg}".lower()
        for method, keywords in self._PAYMENT_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                return method
        return None

    def _detect_suspicious(self, ocr_text: str, user_msg: str) -> List[str]:
        """检测可疑/伪造模式"""
        combined = f"{ocr_text}\n{user_msg}"
        found = []
        for pattern in self._SUSPICIOUS_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                found.append(pattern)
        return found

    # ==================== LLM 分析 ====================

    async def _llm_analyze(
        self,
        user_msg: str,
        ocr_text: str,
        extracted_amount: Optional[float],
        expected_amount: Optional[float],
        expected_service: Optional[str],
    ) -> Tuple[Optional[str], str]:
        """LLM 语义分析支付截图"""
        prompt = (
            "You are a payment verification AI. Analyze the following payment information "
            "and determine if it appears to be a genuine payment.\n\n"
            f"User message: {user_msg[:200]}\n"
            f"OCR text from screenshot: {ocr_text[:300] if ocr_text else '(no OCR text)'}\n"
            f"Extracted amount: ${extracted_amount if extracted_amount else 'N/A'}\n"
            f"Expected amount: ${expected_amount if expected_amount else 'N/A'}\n"
            f"Expected service: {expected_service or 'N/A'}\n\n"
            "Evaluate:\n"
            "1. Does the OCR text look like a real payment receipt/confirmation?\n"
            "2. Is the amount consistent with the expected amount?\n"
            "3. Are there any signs of editing, forgery, or fraud?\n"
            "4. Does the payment method match what's expected?\n\n"
            "Reply with ONLY a JSON:\n"
            '{"verdict": "approve" | "reject" | "manual", '
            '"analysis": "brief explanation of your reasoning"}'
        )

        api_key = self.deepseek_api_key or self.openai_api_key
        base_url = self.deepseek_base_url if self.deepseek_api_key else "https://api.openai.com/v1"

        timeout = aiohttp.ClientTimeout(total=8, connect=3, sock_read=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"{base_url.rstrip('/')}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat" if self.deepseek_api_key else "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 200,
            }
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"API error {resp.status}")
                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]

                result = json.loads(content)
                return result.get("verdict"), result.get("analysis", "")

    # ==================== 交叉验证 ====================

    def _cross_validate(
        self,
        rule_checks: Dict[str, Any],
        llm_verdict: Optional[str],
        ocr_text: str,
    ) -> ReviewVerdict:
        """
        双引擎交叉验证逻辑：

        决策矩阵:
        - 规则 APPROVE + LLM APPROVE → APPROVE
        - 规则 APPROVE + LLM REJECT  → MANUAL_REVIEW（冲突，需人工）
        - 规则 REJECT  + LLM anything → REJECT（规则引擎一票否决）
        - OCR 质量差 → MANUAL_REVIEW
        - 无 LLM → 仅规则引擎
        """
        # 规则引擎判定
        suspicious = rule_checks.get("suspicious_patterns", [])
        amount_match = rule_checks.get("amount_match")
        amount_extracted = rule_checks.get("amount_extracted", False)
        ocr_quality = rule_checks.get("ocr_quality", "poor")

        # 硬性拒绝条件
        if suspicious:
            return ReviewVerdict.REJECT

        # OCR 无法识别内容
        if ocr_quality == "poor" or not ocr_text.strip():
            return ReviewVerdict.MANUAL_REVIEW

        # 规则引擎判定
        rule_approved = (
            amount_extracted
            and (amount_match is None or amount_match)
            and not suspicious
        )

        # LLM 判定
        llm_approved = llm_verdict in ("approve", None)  # None 表示 LLM 不可用
        llm_rejected = llm_verdict == "reject"

        # 交叉验证
        if rule_approved and llm_approved:
            return ReviewVerdict.APPROVE
        elif rule_approved and llm_rejected:
            # 规则和 LLM 冲突 → 人工复核
            return ReviewVerdict.MANUAL_REVIEW
        elif not rule_approved and amount_match is False:
            return ReviewVerdict.REJECT
        elif not amount_extracted:
            return ReviewVerdict.MANUAL_REVIEW
        else:
            return ReviewVerdict.MANUAL_REVIEW

    def _calc_confidence(
        self,
        rule_checks: Dict[str, Any],
        llm_verdict: Optional[str],
    ) -> float:
        """计算审核置信度"""
        score = 0.5  # 基础分

        if rule_checks.get("amount_extracted"):
            score += 0.15
        if rule_checks.get("amount_match") is True:
            score += 0.2
        if rule_checks.get("amount_match") is False:
            score -= 0.3
        if rule_checks.get("suspicious_patterns"):
            score -= 0.4
        if rule_checks.get("ocr_quality") == "good":
            score += 0.1
        if llm_verdict == "approve":
            score += 0.1
        elif llm_verdict == "reject":
            score -= 0.2

        return round(max(0.0, min(1.0, score)), 2)

    def _build_reason(
        self,
        verdict: ReviewVerdict,
        rule_checks: Dict[str, Any],
        llm_analysis: str,
        expected_service: Optional[str],
    ) -> str:
        """构建审核理由（用于用户可见的回复）"""
        if verdict == ReviewVerdict.APPROVE:
            amount = rule_checks.get("extracted_amount")
            method = rule_checks.get("payment_method", "payment")
            return (
                f"✅ Payment verified: ${amount} via {method}. "
                f"Service: {expected_service or 'N/A'}. "
                f"Auto-approved by dual-engine verification."
            )
        elif verdict == ReviewVerdict.REJECT:
            reason = "❌ Payment verification failed."
            if rule_checks.get("suspicious_patterns"):
                reason += " Suspicious patterns detected in screenshot."
            if rule_checks.get("amount_match") is False:
                expected = rule_checks.get("expected_amount")
                extracted = rule_checks.get("extracted_amount")
                reason += f" Amount mismatch: expected ${expected}, got ${extracted}."
            return reason
        else:  # MANUAL_REVIEW
            reason = "⚠️ Payment requires manual review."
            if rule_checks.get("ocr_quality") == "poor":
                reason += " Screenshot quality too low for automatic verification."
            if not rule_checks.get("amount_extracted"):
                reason += " Could not extract payment amount from screenshot."
            if llm_analysis:
                reason += f" AI analysis: {llm_analysis[:100]}"
            return reason

    def _record_stats(self, verdict: ReviewVerdict):
        """记录审核统计"""
        self._review_stats[verdict.value] = self._review_stats.get(verdict.value, 0) + 1
        self._total_reviews += 1

    def get_stats(self) -> Dict[str, Any]:
        """获取审核统计（供监控使用）"""
        return {
            "total_reviews": self._total_reviews,
            "distribution": dict(self._review_stats),
        }


# ==================== 全局单例 ====================

_review_agent: Optional[PaymentReviewAgent] = None


def get_payment_review_agent() -> PaymentReviewAgent:
    """获取 Payment Review Agent 单例"""
    global _review_agent
    if _review_agent is None:
        _review_agent = PaymentReviewAgent()
    return _review_agent

