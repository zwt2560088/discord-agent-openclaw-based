"""
Webhook Server - 处理飞书和 OpenClaw 的回调

提供 HTTP 服务端点：
- /webhook/feishu - 飞书事件回调
- /webhook/openclaw - OpenClaw 任务状态回调
- /health - 健康检查
"""
import asyncio
import json
import logging
from aiohttp import web
from typing import Optional, Callable, Dict

logger = logging.getLogger("WebhookServer")


class WebhookServer:
    """
    Webhook 服务端

    处理来自飞书和 OpenClaw 的回调请求
    """

    def __init__(self, bridge_service, port: int = 8080):
        """
        Args:
            bridge_service: BridgeService 实例
            port: 监听端口
        """
        self.bridge = bridge_service
        self.port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None

        # 事件处理器
        self.feishu_handlers: Dict[str, Callable] = {}
        self.openclaw_handlers: Dict[str, Callable] = {}

    def register_feishu_handler(self, event_type: str, handler: Callable):
        """注册飞书事件处理器"""
        self.feishu_handlers[event_type] = handler

    def register_openclaw_handler(self, event_type: str, handler: Callable):
        """注册 OpenClaw 事件处理器"""
        self.openclaw_handlers[event_type] = handler

    async def start(self):
        """启动 Webhook 服务"""
        self.app = web.Application()

        # 注册路由
        self.app.router.add_post("/webhook/feishu", self._handle_feishu_webhook)
        self.app.router.add_post("/webhook/openclaw", self._handle_openclaw_webhook)
        self.app.router.add_get("/health", self._health_check)

        # 启动服务
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"Webhook server started on port {self.port}")
        logger.info(f"  - Feishu webhook: http://your-server:{self.port}/webhook/feishu")
        logger.info(f"  - OpenClaw webhook: http://your-server:{self.port}/webhook/openclaw")

    async def stop(self):
        """停止服务"""
        if self.runner:
            await self.runner.cleanup()

    async def _health_check(self, request: web.Request) -> web.Response:
        """健康检查"""
        return web.json_response({
            "status": "healthy",
            "service": "bridge-webhook",
            "stats": self.bridge.stats if hasattr(self, 'bridge') else {}
        })

    async def _handle_feishu_webhook(self, request: web.Request) -> web.Response:
        """
        处理飞书 Webhook 回调

        飞书事件格式：
        {
            "type": "url_verification" | "event_callback",
            "challenge": "...",  // 仅验证时
            "event": {...}       // 仅事件回调时
        }
        """
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        logger.info(f"Received Feishu webhook: {body.get('type')}")

        # 首次验证
        if body.get("type") == "url_verification":
            challenge = body.get("challenge", "")
            logger.info(f"Feishu URL verification: {challenge}")
            return web.json_response({"challenge": challenge})

        # 事件回调
        if body.get("type") == "event_callback":
            event = body.get("event", {})
            event_type = event.get("type", "")

            # 消息事件
            if event_type == "message":
                return await self._handle_feishu_message(event)

            # 其他事件
            handler = self.feishu_handlers.get(event_type)
            if handler:
                result = await handler(event)
                return web.json_response(result or {"success": True})

        return web.json_response({"success": True})

    async def _handle_feishu_message(self, event: Dict) -> web.Response:
        """
        处理飞书消息事件

        消息格式：
        {
            "message": {
                "chat_id": "...",
                "content": "{\"text\": \"...\"}",
                ...
            },
            "sender": {
                "sender_id": {"user_id": "..."},
                ...
            }
        """
        message = event.get("message", {})
        chat_id = message.get("chat_id", "")

        # 解析消息内容
        try:
            content = json.loads(message.get("content", "{}"))
        except json.JSONDecodeError:
            content = {}

        text = content.get("text", "")

        # 跳过机器人消息
        if event.get("sender", {}).get("sender_id", {}).get("user_id") == "cli_xxx":
            return web.json_response({"success": True, "reason": "bot message ignored"})

        # 获取发送者信息
        sender_id = event.get("sender", {}).get("sender_id", {}).get("user_id", "")
        sender_name = event.get("sender", {}).get("sender_id", {}).get("user_name", "Support")

        # 转发消息到桥接服务
        if text and chat_id:
            logger.info(f"Feishu message from {sender_name}: {text[:50]}...")

            try:
                await self.bridge.handle_feishu_message(chat_id, text, sender_id)
            except Exception as e:
                logger.error(f"Error handling Feishu message: {e}")

        return web.json_response({"success": True})

    async def _handle_openclaw_webhook(self, request: web.Request) -> web.Response:
        """
        处理 OpenClaw Webhook 回调

        OpenClaw 事件格式：
        {
            "event_type": "task.completed" | "worker.assigned" | ...,
            "data": {...}
        }
        """
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        event_type = body.get("event_type", "")
        data = body.get("data", {})

        logger.info(f"Received OpenClaw webhook: {event_type}")

        # 任务完成
        if event_type == "task.completed":
            order_id = data.get("order_id")
            if order_id:
                mapping = self.bridge.get_order_mapping(order_id)
                if mapping:
                    mapping.status = "completed"
                    logger.info(f"Order {order_id} completed via OpenClaw")

        # 打手分配
        elif event_type == "worker.assigned":
            order_id = data.get("order_id")
            worker_id = data.get("worker_id")
            worker_name = data.get("worker_name", "Unknown")

            if order_id and worker_id:
                mapping = self.bridge.get_order_mapping(order_id)
                if mapping:
                    mapping.worker_id = worker_id
                    mapping.status = "in_progress"
                    logger.info(f"Order {order_id} assigned to {worker_name}")

        # 自定义处理器
        handler = self.openclaw_handlers.get(event_type)
        if handler:
            result = await handler(data)
            return web.json_response(result or {"success": True})

        return web.json_response({"success": True})


# ==================== 快速启动 ====================

async def run_webhook_server(bridge_service, port: int = 8080):
    """
    启动 Webhook 服务

    Args:
        bridge_service: BridgeService 实例
        port: 监听端口

    Usage:
        server = WebhookServer(bridge, port=8080)
        await server.start()
    """
    server = WebhookServer(bridge_service, port)
    await server.start()
    return server


if __name__ == "__main__":
    # 独立运行测试
    async def test():
        from bridge_service import BridgeService

        bridge = BridgeService()
        server = WebhookServer(bridge, port=8080)

        print("Starting webhook server...")
        await server.start()

        print("Press Ctrl+C to stop")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await server.stop()

    asyncio.run(test())

