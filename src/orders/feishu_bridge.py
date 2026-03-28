"""
Feishu (Lark) Integration for Workers
飞书机器人 - 打手端沟通桥梁

工作流程：
1. Discord 客户发消息 → 翻译 → 发到飞书群
2. 飞书打手回复 → 翻译 → 发到 Discord 客户频道
"""
import json
import os
import asyncio
import aiohttp
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any, Callable


@dataclass
class FeishuConfig:
    """飞书配置"""
    app_id: str = ""
    app_secret: str = ""
    base_url: str = "https://open.feishu.cn/open-apis"

    @classmethod
    def from_env(cls):
        """从环境变量加载"""
        return cls(
            app_id=os.getenv("FEISHU_APP_ID", ""),
            app_secret=os.getenv("FEISHU_APP_SECRET", "")
        )


class FeishuClient:
    """飞书 API 客户端"""

    def __init__(self, config: FeishuConfig = None):
        self.config = config or FeishuConfig.from_env()
        self.access_token = None
        self.token_expires = 0
        self.session = None

    async def _get_session(self):
        """获取 HTTP session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_access_token(self) -> str:
        """获取 access_token"""
        if self.access_token and datetime.now().timestamp() < self.token_expires:
            return self.access_token

        session = await self._get_session()

        async with session.post(
            f"{self.config.base_url}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret
            }
        ) as response:
            if response.status == 200:
                data = await response.json()
                self.access_token = data.get("tenant_access_token")
                self.token_expires = datetime.now().timestamp() + data.get("expire", 7200) - 300
                return self.access_token
            else:
                raise Exception(f"Failed to get token: {await response.text()}")

    async def send_message(self, receive_id: str, content: str, receive_id_type: str = "chat_id") -> Dict:
        """
        发送消息到飞书

        Args:
            receive_id: 接收者 ID (chat_id / user_id / open_id)
            content: 消息内容
            receive_id_type: ID 类型
        """
        token = await self.get_access_token()
        session = await self._get_session()

        async with session.post(
            f"{self.config.base_url}/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": content})
            }
        ) as response:
            return await response.json()

    async def send_card(self, receive_id: str, title: str, content: str, receive_id_type: str = "chat_id") -> Dict:
        """
        发送卡片消息

        Args:
            receive_id: 接收者 ID
            title: 卡片标题
            content: 卡片内容
        """
        token = await self.get_access_token()
        session = await self._get_session()

        card = {
            "type": "template",
            "data": {
                "template_id": "AAqk8JfJcBpWi",  # 默认卡片模板
                "template_variable": {
                    "title": title,
                    "content": content
                }
            }
        }

        async with session.post(
            f"{self.config.base_url}/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            params={"receive_id_type": receive_id_type},
            json={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card)
            }
        ) as response:
            return await response.json()

    async def create_chat(self, name: str, user_ids: list = None) -> Dict:
        """
        创建群聊

        Args:
            name: 群名
            user_ids: 成员 ID 列表
        """
        token = await self.get_access_token()
        session = await self._get_session()

        async with session.post(
            f"{self.config.base_url}/im/v1/chats",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "name": name,
                "user_id_list": user_ids or []
            }
        ) as response:
            return await response.json()

    async def close(self):
        """关闭连接"""
        if self.session and not self.session.closed:
            await self.session.close()


class FeishuOrderBridge:
    """
    飞书订单沟通桥梁

    将 Discord 客户消息转发到飞书，并将飞书打手回复转发回 Discord
    """

    def __init__(self, feishu_client: FeishuClient = None, order_manager=None, translation_bridge=None):
        self.feishu = feishu_client or FeishuClient()
        self.order_manager = order_manager
        self.translation_bridge = translation_bridge
        self.order_chats: Dict[str, str] = {}  # order_id -> feishu_chat_id
        self.message_handlers: Dict[str, Callable] = {}  # 回调函数

    def set_discord_callback(self, order_id: str, callback: Callable):
        """设置 Discord 回调函数"""
        self.message_handlers[order_id] = callback

    async def create_order_chat(self, order_id: str, order_info: Dict) -> str:
        """
        为订单创建飞书群聊

        Args:
            order_id: 订单 ID
            order_info: 订单信息

        Returns:
            飞书群聊 ID
        """
        # 创建群聊
        result = await self.feishu.create_chat(
            name=f"订单 #{order_id}",
            user_ids=[]
        )

        if result.get("code") == 0:
            chat_id = result["data"]["chat_id"]
            self.order_chats[order_id] = chat_id

            # 发送订单信息
            await self.feishu.send_card(
                receive_id=chat_id,
                title=f"🔔 新订单 #{order_id}",
                content=f"""服务: {order_info.get('service_type', 'Unknown')}
价格: ${order_info.get('price', 0)}
客户: {order_info.get('customer_name', 'Unknown')}
平台: {order_info.get('platform', 'PC')}
状态: 等待接单

---
接单后请在此群回复客户消息，系统会自动翻译并发送给客户。"""
            )

            return chat_id
        else:
            raise Exception(f"Failed to create chat: {result}")

    async def forward_to_feishu(self, order_id: str, message: str, is_translated: bool = True) -> bool:
        """
        将 Discord 消息转发到飞书

        Args:
            order_id: 订单 ID
            message: 消息内容
            is_translated: 是否已翻译
        """
        chat_id = self.order_chats.get(order_id)
        if not chat_id:
            return False

        # 如果需要翻译
        if not is_translated and self.translation_bridge:
            message = await self.translation_bridge.translate(message, "en", "zh")

        # 发送到飞书
        result = await self.feishu.send_message(
            receive_id=chat_id,
            content=f"👤 [客户] {message}"
        )

        return result.get("code") == 0

    async def handle_feishu_message(self, event: Dict):
        """
        处理飞书消息事件（Webhook 回调）

        Args:
            event: 飞书事件数据
        """
        message = event.get("message", {})
        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "")
        chat_id = message.get("chat_id")

        # 找到对应的订单
        order_id = None
        for oid, cid in self.order_chats.items():
            if cid == chat_id:
                order_id = oid
                break

        if not order_id:
            return

        # 翻译消息
        translated = text
        if self.translation_bridge:
            translated = await self.translation_bridge.translate(text, "zh", "en")

        # 调用 Discord 回调发送消息
        callback = self.message_handlers.get(order_id)
        if callback:
            await callback(order_id, translated, text)

        return {
            "order_id": order_id,
            "original": text,
            "translated": translated
        }

    def get_webhook_handler(self):
        """获取 Webhook 处理函数（用于 FastAPI/Flask）"""
        async def handler(request):
            # 验证签名等
            body = await request.json()

            # 处理事件
            event_type = body.get("type")

            if event_type == "url_verification":
                # 首次验证
                return {"challenge": body.get("challenge")}

            elif event_type == "event_callback":
                # 消息事件
                event = body.get("event", {})
                if event.get("type") == "message":
                    result = await self.handle_feishu_message(event)
                    return {"success": True, "result": result}

            return {"success": True}

        return handler


class SimpleTranslationBridge:
    """简单翻译桥（用于测试）"""

    def __init__(self, use_api: bool = True):
        self.use_api = use_api
        self.api_key = os.getenv("deepseek_api_key")
        self.api_url = os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")

    async def translate(self, text: str, source: str, target: str) -> str:
        """翻译文本"""
        if source == target:
            return text

        if self.use_api and self.api_key:
            return await self._translate_with_api(text, source, target)

        return self._simple_translate(text, source, target)

    async def _translate_with_api(self, text: str, source: str, target: str) -> str:
        """使用 DeepSeek API 翻译"""
        import aiohttp

        lang_pair = "Chinese to English" if source == "zh" else "English to Chinese"

        prompt = f"""You are a professional game service translator. Translate the following text from {lang_pair}.
Keep gaming terminology natural.
Only output the translated text.

Text: {text}"""

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()

        return text

    def _simple_translate(self, text: str, source: str, target: str) -> str:
        """简单翻译（关键词替换）"""
        # 常用游戏服务短语
        phrases = {
            "en_to_zh": {
                "hello": "你好",
                "hi": "嗨",
                "ok": "好的",
                "yes": "是的",
                "no": "不是",
                "price": "价格",
                "order": "订单",
                "service": "服务",
                "boosting": "代练",
                "level": "等级",
                "badge": "徽章",
                "account": "账号",
                "password": "密码",
                "platform": "平台",
                "pc": "PC",
                "ps5": "PS5",
                "xbox": "Xbox",
                "how long": "多久",
                "how much": "多少钱",
                "when": "什么时候",
                "finish": "完成",
                "start": "开始",
                "thank": "谢谢",
                "please": "请",
                "help": "帮助",
                "problem": "问题",
                "issue": "问题",
                "safe": "安全",
                "fast": "快",
                "slow": "慢",
                "good": "好",
                "bad": "坏"
            },
            "zh_to_en": {
                "你好": "Hello",
                "嗨": "Hi",
                "好的": "OK",
                "是的": "Yes",
                "不是": "No",
                "价格": "price",
                "订单": "order",
                "服务": "service",
                "代练": "boosting",
                "等级": "level",
                "徽章": "badge",
                "账号": "account",
                "密码": "password",
                "平台": "platform",
                "多久": "how long",
                "多少钱": "how much",
                "什么时候": "when",
                "完成": "finish",
                "开始": "start",
                "谢谢": "thank you",
                "请": "please",
                "帮助": "help",
                "问题": "problem",
                "安全": "safe",
                "快": "fast",
                "慢": "slow",
                "好": "good",
                "坏": "bad",
                "收到": "Got it",
                "明白了": "Understood",
                "正在进行": "In progress",
                "已完成": "Completed"
            }
        }

        mapping = phrases["en_to_zh"] if source == "en" else phrases["zh_to_en"]
        result = text

        for orig, trans in mapping.items():
            result = result.replace(orig, trans)

        return result


# 全局实例
_feishu_bridge = None


def get_feishu_bridge() -> FeishuOrderBridge:
    """获取飞书桥实例"""
    global _feishu_bridge
    if _feishu_bridge is None:
        _feishu_bridge = FeishuOrderBridge(
            translation_bridge=SimpleTranslationBridge()
        )
    return _feishu_bridge

