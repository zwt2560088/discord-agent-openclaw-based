"""
企业微信 → Discord 反向转发服务

接收企业微信机器人回调，将消息转发到 Discord
"""
import json
import logging
from aiohttp import web
from typing import Optional, Dict

logger = logging.getLogger("WeChatWebhook")


class WeChatToDiscordBridge:
    """企业微信到 Discord 的消息桥接"""

    def __init__(self, discord_bot=None, order_manager=None):
        self.bot = discord_bot
        self.order_manager = order_manager
        # 映射: 企业微信用户 -> (订单ID, Discord频道ID)
        self.user_mapping: Dict[str, tuple] = {}

    def register_user(self, wechat_user_id: str, order_id: str, discord_channel_id: int):
        """注册用户映射"""
        self.user_mapping[wechat_user_id] = (order_id, discord_channel_id)

    async def handle_wechat_message(self, user_id: str, message: str) -> bool:
        """
        处理企业微信消息

        Args:
            user_id: 企业微信用户 ID
            message: 消息内容（中文）

        Returns:
            是否处理成功
        """
        if not self.bot:
            logger.warning("Discord bot not available")
            return False

        # 查找映射
        mapping = self.user_mapping.get(user_id)
        if not mapping:
            logger.warning(f"No mapping for WeChat user: {user_id}")
            return False

        order_id, channel_id = mapping

        # 获取 Discord 频道
        try:
            import discord
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"Discord channel not found: {channel_id}")
                return False

            # 发送消息到 Discord（中文原文）
            await channel.send(f"🎮 **[打手/客服]** {message}")
            logger.info(f"Forwarded WeChat message to Discord: {order_id}")
            return True

        except Exception as e:
            logger.error(f"Error forwarding to Discord: {e}")
            return False


class WeChatWebhookServer:
    """企业微信 Webhook 服务端"""

    def __init__(self, bridge: WeChatToDiscordBridge, port: int = 8080):
        self.bridge = bridge
        self.port = port
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None

    async def start(self):
        """启动服务"""
        self.app = web.Application()

        # 注册路由
        self.app.router.add_post("/wechat/callback", self._handle_callback)
        self.app.router.add_get("/health", self._health_check)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await site.start()

        logger.info(f"WeChat webhook server started on port {self.port}")
        logger.info(f"Callback URL: http://your-server:{self.port}/wechat/callback")

    async def stop(self):
        """停止服务"""
        if self.runner:
            await self.runner.cleanup()

    async def _health_check(self, request: web.Request) -> web.Response:
        """健康检查"""
        return web.json_response({"status": "healthy"})

    async def _handle_callback(self, request: web.Request) -> web.Response:
        """
        处理企业微信回调

        企业微信回调格式（需要配置企业微信机器人的回调地址）
        """
        try:
            body = await request.json()
            logger.info(f"Received WeChat callback: {body}")

            # 企业微信回调格式
            msg_type = body.get("MsgType", "")

            if msg_type == "text":
                # 文本消息
                user_id = body.get("FromUserName", "")
                content = body.get("Content", "")

                if content:
                    await self.bridge.handle_wechat_message(user_id, content)

            elif msg_type == "image":
                # 图片消息
                user_id = body.get("FromUserName", "")
                pic_url = body.get("PicUrl", "")

                if pic_url:
                    # 转发图片链接
                    await self.bridge.handle_wechat_message(user_id, f"📷 图片: {pic_url}")

            return web.json_response({"success": True})

        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            return web.json_response({"error": str(e)}, status=500)


# ==================== 简化版：通过企业微信 API 主动拉取消息 ====================

class WeChatMessagePoller:
    """
    企业微信消息轮询器

    通过企业微信 API 主动获取群消息（需要配置企业微信应用）
    """

    def __init__(self, corp_id: str, agent_id: str, secret: str, bridge: WeChatToDiscordBridge):
        self.corp_id = corp_id
        self.agent_id = agent_id
        self.secret = secret
        self.bridge = bridge
        self.access_token = None
        self.session = None

    async def _get_session(self):
        if self.session is None or self.session.closed:
            import aiohttp
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_access_token(self) -> str:
        """获取企业微信 access_token"""
        if self.access_token:
            return self.access_token

        session = await self._get_session()
        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corp_id}&corpsecret={self.secret}"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("errcode") == 0:
                    self.access_token = data.get("access_token")
                    return self.access_token

        raise Exception("Failed to get access token")

    async def poll_messages(self):
        """轮询获取消息"""
        import asyncio
        while True:
            try:
                token = await self.get_access_token()
                session = await self._get_session()

                # 获取消息（企业微信 API）
                url = f"https://qyapi.weixin.qq.com/cgi-bin/message/list?access_token={token}"

                # 这里需要根据企业微信 API 文档实现
                # 企业微信的消息获取需要配置回调地址

            except Exception as e:
                logger.error(f"Error polling messages: {e}")

            await asyncio.sleep(5)  # 每5秒轮询一次


# ==================== 全局实例 ====================

_wechat_bridge: Optional[WeChatToDiscordBridge] = None
_wechat_webhook: Optional[WeChatWebhookServer] = None


def get_wechat_bridge(discord_bot=None, order_manager=None) -> WeChatToDiscordBridge:
    """获取企业微信桥接实例"""
    global _wechat_bridge
    if _wechat_bridge is None:
        _wechat_bridge = WeChatToDiscordBridge(discord_bot, order_manager)
    return _wechat_bridge


async def start_wechat_webhook(bot, order_manager, port: int = 8080):
    """启动企业微信 Webhook 服务"""
    global _wechat_bridge, _wechat_webhook

    _wechat_bridge = WeChatToDiscordBridge(bot, order_manager)
    _wechat_webhook = WeChatWebhookServer(_wechat_bridge, port)

    await _wechat_webhook.start()
    return _wechat_webhook

