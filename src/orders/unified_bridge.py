"""
Unified Bridge - Discord ↔ OpenClaw ↔ Feishu 全链路打通

核心功能：
1. Discord 客户消息 → 翻译 → 发到飞书群
2. 飞书打手回复 → 翻译 → 发到 Discord 客户频道
3. 订单状态双向同步
4. 匿名沟通（客户看不到打手，打手看不到客户信息）

架构：
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Discord   │ ←→  │  OpenClaw   │ ←→  │   Feishu    │
│  (客户英文)  │     │ (翻译+中转)  │     │ (打手中文)   │
└─────────────┘     └─────────────┘     └─────────────┘
"""
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Callable, Any

from .order_bridge import OrderManager, OrderStatus, MessageType, Order
from .feishu_bridge import FeishuClient, FeishuConfig, SimpleTranslationBridge
from .openclaw_integration import OpenClawClient, OpenClawConfig


@dataclass
class BridgeMapping:
    """桥接映射 - 记录 Discord 频道 ↔ 飞书群的对应关系"""
    order_id: str
    discord_customer_channel_id: str  # Discord 客户频道 ID
    discord_worker_channel_id: str    # Discord 打手频道 ID (可选)
    feishu_chat_id: str               # 飞书群聊 ID
    openclaw_task_id: str             # OpenClaw 任务 ID (可选)
    created_at: datetime = field(default_factory=datetime.now)


class UnifiedBridge:
    """
    统一桥接器 - 实现 Discord ↔ OpenClaw ↔ 飞书 全链路沟通

    工作流程：
    1. 客户在 Discord 下单 → 创建订单 + 创建飞书群 + 创建 Discord 私密频道
    2. 客户发消息 → 翻译 → 发到飞书群
    3. 打手在飞书回复 → 翻译 → 发到 Discord 客户频道
    4. 订单状态变更 → 同步到所有端
    """

    def __init__(
        self,
        order_manager: OrderManager = None,
        feishu_client: FeishuClient = None,
        openclaw_client: OpenClawClient = None,
        translation_bridge: SimpleTranslationBridge = None
    ):
        self.order_manager = order_manager or OrderManager()
        self.feishu = feishu_client
        self.openclaw = openclaw_client
        self.translation = translation_bridge or SimpleTranslationBridge()

        # 映射表
        self.mappings: Dict[str, BridgeMapping] = {}  # order_id -> BridgeMapping
        self.discord_to_order: Dict[str, str] = {}    # discord_channel_id -> order_id
        self.feishu_to_order: Dict[str, str] = {}     # feishu_chat_id -> order_id

        # Discord 回调函数（用于发送消息到 Discord）
        self.discord_send_callback: Optional[Callable] = None

        # 加载现有映射
        self._load_mappings()

    def _load_mappings(self):
        """从数据库加载现有映射"""
        orders = self.order_manager.get_all_orders()
        for order in orders:
            if order.customer_channel_id:
                self._add_mapping_to_memory(order)

    def _add_mapping_to_memory(self, order: Order):
        """添加映射到内存"""
        mapping = BridgeMapping(
            order_id=order.id,
            discord_customer_channel_id=order.customer_channel_id or "",
            discord_worker_channel_id=order.worker_channel_id or "",
            feishu_chat_id=getattr(order, 'feishu_chat_id', ""),
            openclaw_task_id=getattr(order, 'openclaw_task_id', "")
        )
        self.mappings[order.id] = mapping
        if order.customer_channel_id:
            self.discord_to_order[order.customer_channel_id] = order.id
        if order.worker_channel_id:
            self.discord_to_order[order.worker_channel_id] = order.id

    def set_discord_callback(self, callback: Callable):
        """设置 Discord 消息发送回调函数"""
        self.discord_send_callback = callback

    # ==================== 订单创建 ====================

    async def create_order_bridge(
        self,
        order: Order,
        discord_customer_channel_id: str,
        discord_worker_channel_id: str = None
    ) -> BridgeMapping:
        """
        创建订单桥接

        Args:
            order: 订单对象
            discord_customer_channel_id: Discord 客户频道 ID
            discord_worker_channel_id: Discord 打手频道 ID（可选）

        Returns:
            BridgeMapping 桥接映射
        """
        # 1. 创建飞书群聊
        feishu_chat_id = ""
        if self.feishu:
            try:
                feishu_chat_id = await self._create_feishu_chat(order)
            except Exception as e:
                print(f"⚠️ 创建飞书群失败: {e}")

        # 2. 创建 OpenClaw 任务
        openclaw_task_id = ""
        if self.openclaw:
            try:
                openclaw_task_id = await self._create_openclaw_task(order)
            except Exception as e:
                print(f"⚠️ 创建 OpenClaw 任务失败: {e}")

        # 3. 保存映射
        mapping = BridgeMapping(
            order_id=order.id,
            discord_customer_channel_id=discord_customer_channel_id,
            discord_worker_channel_id=discord_worker_channel_id or "",
            feishu_chat_id=feishu_chat_id,
            openclaw_task_id=openclaw_task_id
        )

        self.mappings[order.id] = mapping
        self.discord_to_order[discord_customer_channel_id] = order.id
        if discord_worker_channel_id:
            self.discord_to_order[discord_worker_channel_id] = order.id
        if feishu_chat_id:
            self.feishu_to_order[feishu_chat_id] = order.id

        # 4. 更新订单
        self.order_manager.set_channels(
            order.id,
            discord_customer_channel_id,
            discord_worker_channel_id or ""
        )

        return mapping

    async def _create_feishu_chat(self, order: Order) -> str:
        """为订单创建飞书群聊"""
        result = await self.feishu.create_chat(
            name=f"订单 #{order.id} - {order.service_type}"
        )

        if result.get("code") == 0:
            chat_id = result["data"]["chat_id"]

            # 发送订单信息卡片
            await self.feishu.send_card(
                receive_id=chat_id,
                title=f"🔔 新订单 #{order.id}",
                content=f"""服务类型: {order.service_type}
当前等级: {order.current_level}
目标等级: {order.target_level}
价格: ${order.price}
平台: {order.platform}
状态: 等待接单

---
📌 接单后请在此群回复客户消息，系统会自动翻译并发送给客户。
客户全程使用英文，你的中文回复会自动翻译成英文。"""
            )

            return chat_id

        raise Exception(f"创建飞书群失败: {result}")

    async def _create_openclaw_task(self, order: Order) -> str:
        """创建 OpenClaw 任务"""
        result = await self.openclaw.create_task(order.to_dict())

        if result.get("success"):
            return result.get("task_id", "")

        raise Exception(f"创建 OpenClaw 任务失败: {result}")

    # ==================== Discord → 飞书 ====================

    async def handle_discord_message(
        self,
        discord_channel_id: str,
        message: str,
        sender_id: str,
        sender_name: str = "Customer"
    ) -> bool:
        """
        处理来自 Discord 的消息

        Args:
            discord_channel_id: Discord 频道 ID
            message: 原始消息（英文）
            sender_id: 发送者 ID
            sender_name: 发送者名称

        Returns:
            是否处理成功
        """
        # 查找订单
        order_id = self.discord_to_order.get(discord_channel_id)
        if not order_id:
            return False

        mapping = self.mappings.get(order_id)
        if not mapping or not mapping.feishu_chat_id:
            return False

        # 翻译：英文 → 中文
        translated = await self.translation.translate(message, "en", "zh")

        # 发送到飞书
        if self.feishu:
            await self.feishu.send_message(
                receive_id=mapping.feishu_chat_id,
                content=f"👤 [客户 {sender_name}]\n原文: {message}\n翻译: {translated}"
            )

        # 记录消息
        await self.order_manager.process_message(
            order_id, MessageType.CUSTOMER, message, sender_id
        )

        return True

    # ==================== 飞书 → Discord ====================

    async def handle_feishu_message(
        self,
        feishu_chat_id: str,
        message: str,
        sender_id: str,
        sender_name: str = "Support"
    ) -> bool:
        """
        处理来自飞书的消息

        Args:
            feishu_chat_id: 飞书群聊 ID
            message: 原始消息（中文）
            sender_id: 发送者 ID
            sender_name: 发送者名称

        Returns:
            是否处理成功
        """
        # 查找订单
        order_id = self.feishu_to_order.get(feishu_chat_id)
        if not order_id:
            return False

        mapping = self.mappings.get(order_id)
        if not mapping or not mapping.discord_customer_channel_id:
            return False

        # 翻译：中文 → 英文
        translated = await self.translation.translate(message, "zh", "en")

        # 通过回调发送到 Discord
        if self.discord_send_callback:
            await self.discord_send_callback(
                channel_id=mapping.discord_customer_channel_id,
                message=f"🎮 **[Support]** {translated}",
                original=message
            )

        # 记录消息
        await self.order_manager.process_message(
            order_id, MessageType.WORKER, message, sender_id
        )

        return True

    # ==================== 状态同步 ====================

    async def sync_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        message: str = ""
    ) -> bool:
        """
        同步订单状态到所有端

        Args:
            order_id: 订单 ID
            status: 新状态
            message: 状态消息

        Returns:
            是否同步成功
        """
        mapping = self.mappings.get(order_id)
        if not mapping:
            return False

        # 更新数据库
        self.order_manager.update_status(order_id, status)

        # 同步到飞书
        if self.feishu and mapping.feishu_chat_id:
            status_zh = {
                OrderStatus.PENDING: "⏳ 等待付款",
                OrderStatus.PAID: "💰 已付款",
                OrderStatus.ASSIGNED: "👤 已分配打手",
                OrderStatus.IN_PROGRESS: "🔄 进行中",
                OrderStatus.COMPLETED: "✅ 已完成",
                OrderStatus.DELIVERED: "📦 已交付",
                OrderStatus.AFTER_SALES: "🔧 售后处理中",
                OrderStatus.CANCELLED: "❌ 已取消"
            }.get(status, status.value)

            await self.feishu.send_message(
                receive_id=mapping.feishu_chat_id,
                content=f"📢 **订单状态更新**\n状态: {status_zh}\n{message}"
            )

        # 同步到 OpenClaw
        if self.openclaw and mapping.openclaw_task_id:
            await self.openclaw.update_task_status(
                mapping.openclaw_task_id,
                status.value,
                message
            )

        return True

    # ==================== 接单处理 ====================

    async def assign_worker(
        self,
        order_id: str,
        worker_id: str,
        worker_name: str
    ) -> bool:
        """
        分配打手

        Args:
            order_id: 订单 ID
            worker_id: 打手 ID
            worker_name: 打手名称

        Returns:
            是否分配成功
        """
        mapping = self.mappings.get(order_id)
        if not mapping:
            return False

        # 更新订单
        self.order_manager.assign_worker(order_id, worker_id, worker_name)

        # 同步状态
        await self.sync_order_status(
            order_id,
            OrderStatus.ASSIGNED,
            f"打手 {worker_name} 已接单"
        )

        # 同步到 OpenClaw
        if self.openclaw and mapping.openclaw_task_id:
            await self.openclaw.assign_task(mapping.openclaw_task_id, worker_id)

        return True

    # ==================== 订单完成 ====================

    async def complete_order(self, order_id: str) -> bool:
        """
        完成订单

        Args:
            order_id: 订单 ID

        Returns:
            是否完成成功
        """
        await self.sync_order_status(
            order_id,
            OrderStatus.COMPLETED,
            "订单已完成，感谢使用！"
        )

        return True

    # ==================== Webhook 处理 ====================

    def get_feishu_webhook_handler(self) -> Callable:
        """获取飞书 Webhook 处理函数"""
        async def handler(request):
            body = await request.json()

            # 首次验证
            if body.get("type") == "url_verification":
                return {"challenge": body.get("challenge")}

            # 消息事件
            if body.get("type") == "event_callback":
                event = body.get("event", {})

                if event.get("type") == "message":
                    # 解析消息
                    chat_id = event.get("message", {}).get("chat_id")
                    content = json.loads(
                        event.get("message", {}).get("content", "{}")
                    )
                    text = content.get("text", "")
                    sender_id = event.get("sender", {}).get("sender_id", {}).get("user_id", "")
                    sender_name = event.get("sender", {}).get("sender_id", {}).get("user_name", "Support")

                    # 处理消息
                    if text and not event.get("message", {}).get("mentions"):
                        # 忽略机器人自己的消息
                        await self.handle_feishu_message(
                            chat_id, text, sender_id, sender_name
                        )

            return {"success": True}

        return handler

    def get_openclaw_webhook_handler(self) -> Callable:
        """获取 OpenClaw Webhook 处理函数"""
        async def handler(request):
            body = await request.json()

            event_type = body.get("event_type")
            data = body.get("data", {})

            if event_type == "task.completed":
                order_id = data.get("order_id")
                if order_id:
                    await self.complete_order(order_id)

            elif event_type == "worker.assigned":
                order_id = data.get("order_id")
                worker_id = data.get("worker_id")
                worker_name = data.get("worker_name", "Unknown")
                if order_id and worker_id:
                    await self.assign_worker(order_id, worker_id, worker_name)

            return {"success": True}

        return handler


# ==================== 全局实例 ====================

_unified_bridge: Optional[UnifiedBridge] = None


def get_unified_bridge() -> UnifiedBridge:
    """获取统一桥接器实例"""
    global _unified_bridge

    if _unified_bridge is None:
        # 初始化飞书客户端
        feishu_config = FeishuConfig.from_env()
        feishu_client = None
        if feishu_config.app_id and feishu_config.app_secret:
            feishu_client = FeishuClient(feishu_config)

        # 初始化 OpenClaw 客户端
        openclaw_config = OpenClawConfig.from_env()
        openclaw_client = None
        if openclaw_config.enabled:
            openclaw_client = OpenClawClient(openclaw_config)

        _unified_bridge = UnifiedBridge(
            feishu_client=feishu_client,
            openclaw_client=openclaw_client
        )

    return _unified_bridge


def init_unified_bridge(
    feishu_app_id: str = None,
    feishu_app_secret: str = None,
    openclaw_api_url: str = None,
    openclaw_api_key: str = None
) -> UnifiedBridge:
    """
    初始化统一桥接器

    Args:
        feishu_app_id: 飞书应用 ID
        feishu_app_secret: 飞书应用密钥
        openclaw_api_url: OpenClaw API 地址
        openclaw_api_key: OpenClaw API 密钥
    """
    global _unified_bridge

    # 飞书配置
    feishu_config = FeishuConfig(
        app_id=feishu_app_id or os.getenv("FEISHU_APP_ID", ""),
        app_secret=feishu_app_secret or os.getenv("FEISHU_APP_SECRET", "")
    )
    feishu_client = None
    if feishu_config.app_id and feishu_config.app_secret:
        feishu_client = FeishuClient(feishu_config)

    # OpenClaw 配置
    openclaw_config = OpenClawConfig(
        api_url=openclaw_api_url or os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:18789"),
        api_key=openclaw_api_key or os.getenv("openclaw_api_key", ""),
        enabled=True
    )
    openclaw_client = OpenClawClient(openclaw_config)

    _unified_bridge = UnifiedBridge(
        feishu_client=feishu_client,
        openclaw_client=openclaw_client
    )

    return _unified_bridge

