"""
智能 Agent 模块 — Supervisor 多 Agent 协作架构

架构:
    Supervisor Agent（路由决策层）
        ├── 客服 Agent（ReAct，处理咨询/下单/查单/售后）
        └── 支付审核 Agent（OCR + LLM + 规则引擎双引擎交叉验证）
"""
from .payment_review_agent import (
    PaymentReviewAgent,
    get_payment_review_agent,
    ReviewResult,
    ReviewVerdict,
)
from .react_agent import ReactAgent, get_agent
from .supervisor_agent import SupervisorAgent, get_supervisor, AgentRoute, RouteDecision
from .tools import (
    KnowledgeSearchTool,
    OrderCreateTool,
    PaymentConfirmTool,
    FulfillmentTool,
    OrderQueryTool
)

__all__ = [
    # ReAct Agent
    'ReactAgent',
    'get_agent',
    # Supervisor Agent
    'SupervisorAgent',
    'get_supervisor',
    'AgentRoute',
    'RouteDecision',
    # Payment Review Agent
    'PaymentReviewAgent',
    'get_payment_review_agent',
    'ReviewResult',
    'ReviewVerdict',
    # Tools
    'KnowledgeSearchTool',
    'OrderCreateTool',
    'PaymentConfirmTool',
    'FulfillmentTool',
    'OrderQueryTool',
]

