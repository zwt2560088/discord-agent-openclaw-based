"""
OpenClaw (龙虾) Integration
自动履约系统集成 - 将订单同步到 OpenClaw 平台
"""
import aiohttp
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class OpenClawConfig:
    """OpenClaw 配置"""
    api_url: str = "http://127.0.0.1:18789"
    api_key: str = ""  # 从环境变量读取
    enabled: bool = True

    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        return cls(
            api_url=os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:18789"),
            api_key=os.getenv("openclaw_api_key", ""),
            enabled=os.getenv("OPENCLAW_ENABLED", "true").lower() == "true"
        )


class OpenClawClient:
    """OpenClaw API 客户端"""

    def __init__(self, config: OpenClawConfig = None):
        self.config = config or OpenClawConfig.from_env()
        self.session = None

    async def _get_session(self):
        """获取 aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭 session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def create_task(self, order_data: Dict) -> Dict:
        """
        创建履约任务

        Args:
            order_data: 订单数据

        Returns:
            API 响应
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        # 构建 OpenClaw 任务数据
        task_data = {
            "task_type": "nba2k_boosting",
            "order_id": order_data.get("id"),
            "customer_id": order_data.get("customer_id"),
            "service_type": order_data.get("service_type"),
            "details": {
                "current_level": order_data.get("current_level"),
                "target_level": order_data.get("target_level"),
                "platform": order_data.get("platform", "PC"),
                "price": order_data.get("price"),
                "urgent": order_data.get("urgent", False),
                "live_stream": order_data.get("live_stream", False)
            },
            "created_at": datetime.now().isoformat()
        }

        try:
            async with session.post(
                f"{self.config.api_url}/api/tasks",
                json=task_data,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}",
                        "message": await response.text()
                    }
        except aiohttp.ClientError as e:
            return {"success": False, "error": str(e), "message": f"Connection error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e), "message": f"Unknown error: {e}"}

    async def get_task_status(self, task_id: str) -> Dict:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        try:
            async with session.get(
                f"{self.config.api_url}/api/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_task_status(self, task_id: str, status: str, message: str = "") -> Dict:
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            message: 状态消息

        Returns:
            更新结果
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        try:
            async with session.patch(
                f"{self.config.api_url}/api/tasks/{task_id}",
                json={"status": status, "message": message},
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_workers(self) -> Dict:
        """
        获取可用打手列表

        Returns:
            打手列表
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        try:
            async with session.get(
                f"{self.config.api_url}/api/workers",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def assign_task(self, task_id: str, worker_id: str) -> Dict:
        """
        将任务分配给打手

        Args:
            task_id: 任务 ID
            worker_id: 打手 ID

        Returns:
            分配结果
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        try:
            async with session.post(
                f"{self.config.api_url}/api/tasks/{task_id}/assign",
                json={"worker_id": worker_id},
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_to_wechat(self, message: str, order_id: str = None, image_url: str = None) -> Dict:
        """
        发送消息到企业微信群机器人

        Args:
            message: 消息内容
            order_id: 订单 ID（可选）
            image_url: 图片 URL（可选）

        Returns:
            发送结果
        """
        # 企业微信 Webhook URL
        webhook_url = os.getenv("WECHAT_WEBHOOK_URL", "")
        if not webhook_url:
            return {"success": False, "message": "WeChat webhook URL not configured"}

        session = await self._get_session()

        try:
            # 如果有图片，先发送图片
            if image_url:
                # 下载图片
                async with session.get(image_url) as img_response:
                    if img_response.status == 200:
                        img_data = await img_response.read()
                        import base64
                        img_base64 = base64.b64encode(img_data).decode('utf-8')

                        # 发送图片消息
                        img_payload = {
                            "msgtype": "image",
                            "image": {
                                "base64": img_base64,
                                "md5": self._get_md5(img_data)
                            }
                        }
                        await session.post(webhook_url, json=img_payload)

            # 发送文本消息
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": message
                }
            }

            async with session.post(webhook_url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("errcode") == 0:
                        return {"success": True}
                    else:
                        return {"success": False, "error": result.get("errmsg", "Unknown error")}
                else:
                    return {
                        "success": False,
                        "error": f"HTTP error: {response.status}"
                    }
        except aiohttp.ClientError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_md5(self, data: bytes) -> str:
        """计算 MD5"""
        import hashlib
        return hashlib.md5(data).hexdigest()

    async def send_to_feishu(self, message: str, order_id: str = None, chat_id: str = None) -> Dict:
        """
        发送消息到飞书/企业微信（兼容旧接口）

        Args:
            message: 消息内容
            order_id: 订单 ID（可选）
            chat_id: 群 ID（可选）

        Returns:
            发送结果
        """
        # 优先使用企业微信
        return await self.send_to_wechat(message, order_id)

    async def translate_message(self, text: str, source: str = "en", target: str = "zh") -> Dict:
        """
        通过 OpenClaw 翻译消息

        Args:
            text: 原文
            source: 源语言
            target: 目标语言

        Returns:
            翻译结果
        """
        if not self.config.enabled:
            return {"success": False, "message": "OpenClaw integration disabled"}

        session = await self._get_session()

        try:
            async with session.post(
                f"{self.config.api_url}/api/translate",
                json={"text": text, "source": source, "target": target},
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {
                        "success": False,
                        "error": f"API error: {response.status}"
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}


# OpenClaw Webhook 处理
class OpenClawWebhookHandler:
    """处理来自 OpenClaw 的 Webhook 回调"""

    def __init__(self, order_manager=None):
        self.order_manager = order_manager
        self.openclaw_client = OpenClawClient()

    async def handle_webhook(self, event_type: str, data: Dict) -> Dict:
        """
        处理 Webhook 事件

        Args:
            event_type: 事件类型
            data: 事件数据

        Returns:
            处理结果
        """
        handlers = {
            "task.started": self._handle_task_started,
            "task.progress": self._handle_task_progress,
            "task.completed": self._handle_task_completed,
            "task.failed": self._handle_task_failed,
            "worker.assigned": self._handle_worker_assigned
        }

        handler = handlers.get(event_type)
        if handler:
            return await handler(data)
        else:
            return {"success": False, "message": f"Unknown event type: {event_type}"}

    async def _handle_task_started(self, data: Dict) -> Dict:
        """任务开始"""
        if self.order_manager:
            from .order_bridge import OrderStatus
            order_id = data.get("order_id")
            if order_id:
                self.order_manager.update_status(order_id, OrderStatus.IN_PROGRESS)
        return {"success": True}

    async def _handle_task_progress(self, data: Dict) -> Dict:
        """任务进度更新"""
        # 可以发送进度通知到 Discord
        return {"success": True}

    async def _handle_task_completed(self, data: Dict) -> Dict:
        """任务完成"""
        if self.order_manager:
            from .order_bridge import OrderStatus
            order_id = data.get("order_id")
            if order_id:
                self.order_manager.update_status(order_id, OrderStatus.COMPLETED)
        return {"success": True}

    async def _handle_task_failed(self, data: Dict) -> Dict:
        """任务失败"""
        if self.order_manager:
            from .order_bridge import OrderStatus
            order_id = data.get("order_id")
            if order_id:
                self.order_manager.update_status(order_id, OrderStatus.AFTER_SALES)
        return {"success": True}

    async def _handle_worker_assigned(self, data: Dict) -> Dict:
        """打手分配"""
        if self.order_manager:
            order_id = data.get("order_id")
            worker_id = data.get("worker_id")
            worker_name = data.get("worker_name", "Unknown")
            if order_id and worker_id:
                self.order_manager.assign_worker(order_id, worker_id, worker_name)
        return {"success": True}


# 全局实例
_openclaw_client = None
_webhook_handler = None


def get_openclaw_client() -> OpenClawClient:
    """获取 OpenClaw 客户端"""
    global _openclaw_client
    if _openclaw_client is None:
        _openclaw_client = OpenClawClient()
    return _openclaw_client


def get_webhook_handler(order_manager=None) -> OpenClawWebhookHandler:
    """获取 Webhook 处理器"""
    global _webhook_handler
    if _webhook_handler is None:
        _webhook_handler = OpenClawWebhookHandler(order_manager)
    return _webhook_handler

