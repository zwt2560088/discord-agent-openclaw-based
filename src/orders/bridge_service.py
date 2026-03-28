"""
Discord ↔ OpenClaw ↔ 飞书 全链路桥接服务

完整架构:
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Discord   │ ←→  │  OpenClaw   │ ←→  │   Feishu    │
│  (客户英文)  │     │ (翻译+中转)  │     │ (打手中文)   │
└─────────────┘     └─────────────┘     └─────────────┘

核心功能:
1. Discord 客户消息 → 翻译(英→中) → 发到飞书群
2. 飞书打手回复 → 翻译(中→英) → 发到 Discord 客户频道
3. 订单状态双向同步
4. 匿名沟通（客户看不到打手，打手看不到客户信息）
5. 支持多订单并行处理
"""
import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Callable, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("BridgeService")

# 配置
@dataclass
class BridgeConfig:
    """桥接服务配置"""
    # Discord 配置
    discord_token: str = ""
    discord_guild_id: int = 0

    # 飞书配置
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_webhook_url: str = ""  # 飞书机器人 Webhook

    # OpenClaw 配置
    openclaw_api_url: str = "http://127.0.0.1:18789"
    openclaw_api_key: str = ""

    # 翻译配置
    translation_api_key: str = ""  # DeepSeek 或 OpenAI API Key
    translation_api_url: str = "https://api.deepseek.com/v1"

    # 分类频道
    orders_category_name: str = "📦 Orders"

    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        return cls(
            discord_token=os.getenv("discord_token", ""),
            discord_guild_id=int(os.getenv("DISCORD_GUILD_ID", "0")),
            feishu_app_id=os.getenv("FEISHU_APP_ID", ""),
            feishu_app_secret=os.getenv("FEISHU_APP_SECRET", ""),
            feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL", ""),
            openclaw_api_url=os.getenv("OPENCLAW_API_URL", "http://127.0.0.1:18789"),
            openclaw_api_key=os.getenv("openclaw_api_key", ""),
            translation_api_key=os.getenv("deepseek_api_key", ""),
            translation_api_url=os.getenv("deepseek_base_url", "https://api.deepseek.com/v1")
        )


@dataclass
class OrderMapping:
    """订单映射 - 记录 Discord 频道 ↔ 飞书群的对应关系"""
    order_id: str
    discord_customer_channel_id: int  # Discord 客户频道 ID
    discord_worker_channel_id: int    # Discord 打手频道 ID
    feishu_chat_id: str               # 飞书群聊 ID
    openclaw_task_id: str             # OpenClaw 任务 ID
    customer_id: str                  # Discord 客户 ID
    worker_id: str = ""               # 打手 ID
    status: str = "pending"           # 订单状态
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "order_id": self.order_id,
            "discord_customer_channel_id": str(self.discord_customer_channel_id),
            "discord_worker_channel_id": str(self.discord_worker_channel_id),
            "feishu_chat_id": self.feishu_chat_id,
            "openclaw_task_id": self.openclaw_task_id,
            "customer_id": self.customer_id,
            "worker_id": self.worker_id,
            "status": self.status,
            "created_at": self.created_at.isoformat()
        }


class TranslationEngine:
    """专业游戏翻译引擎 - 中英互译"""

    # NBA2K 游戏术语词典
    GAME_GLOSSARY = {
        "en_to_zh": {
            # 等级/段位
            "rookie": "新秀",
            "starter": "先发",
            "veteran": "老将",
            "all-star": "全明星",
            "superstar": "超级巨星",
            "legend": "传奇",

            # 属性
            "overall": "总评",
            "rating": "评分",
            "badge": "徽章",
            "attribute": "属性",
            "vc": "VC币",
            "mt": "MT币",

            # 服务类型
            "boosting": "代练",
            "leveling": "升级",
            "grinding": "刷分",
            "farming": "刷币",
            "reputation": "声望",

            # 常用短语
            "how much": "多少钱",
            "price": "价格",
            "discount": "折扣",
            "order": "订单",
            "account": "账号",
            "platform": "平台",
            "progress": "进度",
            "complete": "完成",
            "start": "开始",
            "safe": "安全",
            "ban": "封号",
        },
        "zh_to_en": {
            # 等级/段位
            "新秀": "Rookie",
            "先发": "Starter",
            "老将": "Veteran",
            "全明星": "All-Star",
            "超级巨星": "Superstar",
            "传奇": "Legend",

            # 属性
            "总评": "Overall",
            "评分": "Rating",
            "徽章": "Badge",
            "属性": "Attribute",
            "代练": "Boosting",
            "升级": "Level Up",
            "刷分": "Grinding",
            "刷币": "Farming",
            "声望": "Reputation",

            # 常用短语
            "多少钱": "how much",
            "价格": "price",
            "折扣": "discount",
            "订单": "order",
            "账号": "account",
            "平台": "platform",
            "进度": "progress",
            "完成": "complete",
            "开始": "start",
            "安全": "safe",
            "封号": "ban",
        }
    }

    def __init__(self, api_key: str = None, api_url: str = None):
        self.api_key = api_key
        self.api_url = api_url
        self.session = None

    async def _get_session(self):
        """获取 HTTP session"""
        if self.session is None or self.session.closed:
            import aiohttp
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭连接"""
        if self.session and not self.session.closed:
            await self.session.close()

    def _preprocess(self, text: str, source: str, target: str) -> str:
        """预处理：游戏术语替换"""
        glossary = self.GAME_GLOSSARY.get(f"{source}_to_{target}", {})
        processed = text
        for orig, trans in glossary.items():
            processed = processed.replace(orig, trans)
        return processed

    async def translate(self, text: str, source: str, target: str) -> str:
        """
        翻译文本

        Args:
            text: 原文
            source: 源语言 (en/zh)
            target: 目标语言 (en/zh)

        Returns:
            翻译后的文本
        """
        if source == target:
            return text

        # 预处理：游戏术语
        preprocessed = self._preprocess(text, source, target)

        # 如果有 API，使用 API 翻译
        if self.api_key:
            try:
                return await self._translate_with_api(preprocessed, source, target)
            except Exception as e:
                logger.warning(f"API translation failed: {e}, using fallback")

        # 回退：简单关键词替换
        return self._simple_translate(preprocessed, source, target)

    async def _translate_with_api(self, text: str, source: str, target: str) -> str:
        """使用 DeepSeek/OpenAI API 翻译"""

        lang_pair = "Chinese to English" if source == "zh" else "English to Chinese"

        prompt = f"""You are a professional NBA2K game service translator. Translate the following text from {lang_pair}.

Rules:
1. Keep gaming terminology natural and accurate
2. Preserve the tone (casual/polite)
3. Don't translate proper nouns, numbers, or codes
4. Only output the translated text, no explanations

Text: {text}"""

        session = await self._get_session()

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
            else:
                raise Exception(f"API error: {response.status}")

    def _simple_translate(self, text: str, source: str, target: str) -> str:
        """简单翻译（关键词替换）"""
        # 已经在预处理中替换过了
        return text


class FeishuBridgeClient:
    """飞书客户端 - 用于订单群聊和消息推送"""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.access_token = None
        self.token_expires = 0
        self.session = None

    async def _get_session(self):
        """获取 HTTP session"""
        if self.session is None or self.session.closed:
            import aiohttp
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_access_token(self) -> str:
        """获取飞书 access_token"""
        if self.access_token and datetime.now().timestamp() < self.token_expires:
            return self.access_token

        session = await self._get_session()
        base_url = "https://open.feishu.cn/open-apis"

        async with session.post(
            f"{base_url}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self.config.feishu_app_id,
                "app_secret": self.config.feishu_app_secret
            }
        ) as response:
            if response.status == 200:
                data = await response.json()
                self.access_token = data.get("tenant_access_token")
                self.token_expires = datetime.now().timestamp() + data.get("expire", 7200) - 300
                return self.access_token
            else:
                raise Exception(f"Failed to get feishu token: {await response.text()}")

    async def send_webhook_message(self, content: str) -> bool:
        """
        通过 Webhook 发送消息（简单通知）

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        if not self.config.feishu_webhook_url:
            logger.warning("Feishu webhook URL not configured")
            return False

        session = await self._get_session()

        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }

        try:
            async with session.post(
                self.config.feishu_webhook_url,
                json=payload
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send webhook message: {e}")
            return False

    async def send_webhook_card(self, title: str, content: str) -> bool:
        """
        通过 Webhook 发送卡片消息

        Args:
            title: 卡片标题
            content: 卡片内容

        Returns:
            是否发送成功
        """
        if not self.config.feishu_webhook_url:
            return False

        session = await self._get_session()

        payload = {
            "msg_type": "interactive",
            "card": {
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{title}**\n\n{content}"
                    }
                }]
            }
        }

        try:
            async with session.post(
                self.config.feishu_webhook_url,
                json=payload
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send webhook card: {e}")
            return False

    async def create_chat(self, name: str, user_ids: List[str] = None) -> Optional[str]:
        """
        创建飞书群聊

        Args:
            name: 群名
            user_ids: 成员 ID 列表

        Returns:
            群聊 ID
        """
        token = await self.get_access_token()
        session = await self._get_session()
        base_url = "https://open.feishu.cn/open-apis"

        try:
            async with session.post(
                f"{base_url}/im/v1/chats",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "name": name,
                    "user_id_list": user_ids or []
                }
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == 0:
                        return data["data"]["chat_id"]
                return None
        except Exception as e:
            logger.error(f"Failed to create feishu chat: {e}")
            return None

    async def send_message(self, chat_id: str, content: str) -> bool:
        """
        发送消息到飞书群

        Args:
            chat_id: 群聊 ID
            content: 消息内容
        """
        token = await self.get_access_token()
        session = await self._get_session()
        base_url = "https://open.feishu.cn/open-apis"

        try:
            async with session.post(
                f"{base_url}/im/v1/messages",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                params={"receive_id_type": "chat_id"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": content})
                }
            ) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send feishu message: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self.session and not self.session.closed:
            await self.session.close()


class DiscordBridge:
    """
    Discord 桥接器 - 处理 Discord 侧的消息和频道管理

    作为 Discord Bot 运行，监听订单频道消息并转发
    """

    def __init__(self, config: BridgeConfig, bridge_service):
        self.config = config
        self.bridge_service = bridge_service  # 引用主桥接服务
        self.bot = None
        self.guild = None

        # 映射表
        self.channel_to_order: Dict[int, str] = {}  # Discord channel_id -> order_id

        # 消息回调
        self.on_customer_message: Optional[Callable] = None
        self.on_worker_message: Optional[Callable] = None

    async def start(self):
        """启动 Discord Bot"""
        import discord
        from discord.ext import commands

        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        # 支持代理
        proxy = os.getenv("HTTP_PROXY")
        if proxy:
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(proxy)
            self.bot = commands.Bot(
                command_prefix="/",
                intents=intents,
                connector=connector
            )
        else:
            self.bot = commands.Bot(command_prefix="/", intents=intents)

        @self.bot.event
        async def on_ready():
            logger.info(f"Discord Bot ready: {self.bot.user}")
            self.guild = self.bot.get_guild(self.config.discord_guild_id)
            if self.guild:
                logger.info(f"Connected to guild: {self.guild.name}")

        @self.bot.event
        async def on_message(message):
            if message.author.bot:
                return

            await self._handle_message(message)

        # 注册斜杠命令
        @self.bot.slash_command(name="order", description="Create a new order")
        async def create_order(ctx, service: str, current: str, target: str, price: float):
            await self.bridge_service.handle_discord_order_command(
                ctx, service, current, target, price
            )

        @self.bot.slash_command(name="accept", description="Accept an order (Booster only)")
        async def accept_order(ctx, order_id: str):
            await self.bridge_service.handle_discord_accept_command(ctx, order_id)

        @self.bot.slash_command(name="complete", description="Mark order as completed")
        async def complete_order(ctx, order_id: str):
            await self.bridge_service.handle_discord_complete_command(ctx, order_id)

        # 启动 Bot
        await self.bot.start(self.config.discord_token)

    async def _handle_message(self, message):
        """处理 Discord 消息"""
        channel_id = message.channel.id

        # 检查是否是订单频道
        order_id = self.channel_to_order.get(channel_id)
        if not order_id:
            return

        # 获取映射
        mapping = self.bridge_service.get_order_mapping(order_id)
        if not mapping:
            return

        # 判断是客户频道还是打手频道
        if channel_id == mapping.discord_customer_channel_id:
            # 客户消息 → 转发到飞书
            if self.on_customer_message:
                await self.on_customer_message(order_id, message.content, str(message.author.id))

        elif channel_id == mapping.discord_worker_channel_id:
            # 打手消息 → 转发到客户（翻译后）
            if self.on_worker_message:
                await self.on_worker_message(order_id, message.content, str(message.author.id))

    async def create_order_channels(
        self,
        order_id: str,
        customer_id: str,
        service_type: str
    ) -> tuple:
        """
        为订单创建 Discord 频道

        Args:
            order_id: 订单 ID
            customer_id: 客户 Discord ID
            service_type: 服务类型

        Returns:
            (customer_channel_id, worker_channel_id)
        """
        if not self.guild:
            logger.error("Guild not available")
            return None, None

        # 获取或创建订单分类
        category = discord.utils.get(self.guild.categories, name=self.config.orders_category_name)
        if not category:
            category = await self.guild.create_category(self.config.orders_category_name)

        # 获取客户成员
        customer_member = self.guild.get_member(int(customer_id))

        # 创建客户频道（英文 - 客户可见）
        customer_overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
        }
        if customer_member:
            customer_overwrites[customer_member] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )

        customer_channel = await self.guild.create_text_channel(
            name=f"order-{order_id}",
            category=category,
            overwrites=customer_overwrites,
            topic=f"Order #{order_id} - Customer Support Channel"
        )

        # 创建打手频道（中文 - 仅打手可见）
        worker_channel = await self.guild.create_text_channel(
            name=f"履约-{order_id}",
            category=category,
            overwrites={
                self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                self.guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
            },
            topic=f"订单 #{order_id} - 打手沟通频道"
        )

        # 更新映射
        self.channel_to_order[customer_channel.id] = order_id
        self.channel_to_order[worker_channel.id] = order_id

        return customer_channel.id, worker_channel.id

    async def send_to_customer(self, channel_id: int, message: str):
        """发送消息到客户频道"""
        if not self.bot:
            return

        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(message)

    async def send_to_worker(self, channel_id: int, message: str):
        """发送消息到打手频道"""
        if not self.bot:
            return

        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(message)

    async def grant_worker_access(self, worker_id: str, channel_id: int):
        """给打手分配频道访问权限"""
        if not self.guild:
            return

        channel = self.bot.get_channel(channel_id)
        worker_member = self.guild.get_member(int(worker_id))

        if channel and worker_member:
            await channel.set_permissions(
                worker_member,
                view_channel=True,
                send_messages=True
            )


class BridgeService:
    """
    全链路桥接服务 - 协调 Discord ↔ 翻译 ↔ 飞书

    这是核心服务，管理所有订单的消息转发和状态同步
    """

    def __init__(self, config: BridgeConfig = None):
        self.config = config or BridgeConfig.from_env()

        # 组件
        self.translation = TranslationEngine(
            api_key=self.config.translation_api_key,
            api_url=self.config.translation_api_url
        )
        self.feishu = FeishuBridgeClient(self.config)
        self.discord_bridge: Optional[DiscordBridge] = None

        # 订单映射
        self.order_mappings: Dict[str, OrderMapping] = {}  # order_id -> OrderMapping

        # 统计
        self.stats = {
            "total_orders": 0,
            "messages_translated": 0,
            "en_to_zh": 0,
            "zh_to_en": 0
        }

    async def start(self):
        """启动桥接服务"""
        logger.info("Starting Bridge Service...")

        # 初始化 Discord 桥接器
        self.discord_bridge = DiscordBridge(self.config, self)

        # 设置消息回调
        self.discord_bridge.on_customer_message = self._handle_customer_message
        self.discord_bridge.on_worker_message = self._handle_worker_message

        # 启动 Discord Bot（这会阻塞）
        await self.discord_bridge.start()

    # ==================== 订单管理 ====================

    async def create_order(
        self,
        customer_id: str,
        service_type: str,
        current_level: str,
        target_level: str,
        price: float,
        platform: str = "PC"
    ) -> OrderMapping:
        """
        创建新订单

        Args:
            customer_id: Discord 客户 ID
            service_type: 服务类型
            current_level: 当前等级
            target_level: 目标等级
            price: 价格
            platform: 平台

        Returns:
            OrderMapping 订单映射
        """
        # 生成订单 ID
        order_id = str(uuid.uuid4())[:8]

        logger.info(f"Creating order {order_id} for customer {customer_id}")

        # 1. 创建 Discord 频道
        customer_channel_id, worker_channel_id = await self.discord_bridge.create_order_channels(
            order_id, customer_id, service_type
        )

        # 2. 创建飞书群聊
        feishu_chat_id = ""
        if self.config.feishu_app_id and self.config.feishu_app_secret:
            feishu_chat_id = await self.feishu.create_chat(
                name=f"订单 #{order_id} - {service_type}"
            )

        # 3. 发送飞书通知
        await self.feishu.send_webhook_card(
            title=f"🔔 新订单 #{order_id}",
            content=f"""服务: {service_type}
当前: {current_level}
目标: {target_level}
价格: ${price}
平台: {platform}
状态: ⏳ 等待接单

---
📌 接单后请在飞书群回复客户消息，系统会自动翻译并发送给客户。"""
        )

        # 4. 创建映射
        mapping = OrderMapping(
            order_id=order_id,
            discord_customer_channel_id=customer_channel_id,
            discord_worker_channel_id=worker_channel_id,
            feishu_chat_id=feishu_chat_id or "",
            openclaw_task_id="",
            customer_id=customer_id,
            status="pending"
        )

        self.order_mappings[order_id] = mapping
        self.stats["total_orders"] += 1

        # 5. 发送 Discord 欢迎消息
        await self.discord_bridge.send_to_customer(
            customer_channel_id,
            f"✅ **订单已创建**\n\n"
            f"订单号: `{order_id}`\n"
            f"服务: {service_type}\n"
            f"价格: ${price}\n\n"
            f"💬 这是您的专属沟通频道，所有消息将自动翻译。"
        )

        await self.discord_bridge.send_to_worker(
            worker_channel_id,
            f"🔔 **新订单**\n\n"
            f"订单号: `{order_id}`\n"
            f"服务: {service_type}\n"
            f"当前: {current_level}\n"
            f"目标: {target_level}\n"
            f"价格: ${price}\n\n"
            f"📝 接单后在此频道沟通，消息会自动翻译给客户。"
        )

        logger.info(f"Order {order_id} created successfully")
        return mapping

    def get_order_mapping(self, order_id: str) -> Optional[OrderMapping]:
        """获取订单映射"""
        return self.order_mappings.get(order_id)

    # ==================== Discord 命令处理 ====================

    async def handle_discord_order_command(self, ctx, service: str, current: str, target: str, price: float):
        """处理 Discord 订单命令"""
        customer_id = str(ctx.author.id)

        mapping = await self.create_order(
            customer_id=customer_id,
            service_type=service,
            current_level=current,
            target_level=target,
            price=price
        )

        await ctx.respond(f"✅ 订单已创建！订单号: `{mapping.order_id}`")

    async def handle_discord_accept_command(self, ctx, order_id: str):
        """处理 Discord 接单命令"""
        mapping = self.get_order_mapping(order_id)
        if not mapping:
            await ctx.respond(f"❌ 订单 `{order_id}` 不存在")
            return

        if mapping.status != "pending":
            await ctx.respond(f"❌ 订单状态为 `{mapping.status}`，无法接单")
            return

        worker_id = str(ctx.author.id)
        mapping.worker_id = worker_id
        mapping.status = "in_progress"

        # 给打手分配权限
        await self.discord_bridge.grant_worker_access(worker_id, mapping.discord_worker_channel_id)

        # 通知客户
        await self.discord_bridge.send_to_customer(
            mapping.discord_customer_channel_id,
            "🎮 **打手已分配**\n\n您的订单已开始处理，您可以在此与打手沟通。"
        )

        # 通知打手频道
        await self.discord_bridge.send_to_worker(
            mapping.discord_worker_channel_id,
            f"✅ **{ctx.author.display_name}** 已接单，开始履约！"
        )

        # 通知飞书
        await self.feishu.send_webhook_message(
            f"订单 #{order_id} 已被 {ctx.author.display_name} 接单"
        )

        await ctx.respond(f"✅ 你已接单 `{order_id}`")

    async def handle_discord_complete_command(self, ctx, order_id: str):
        """处理 Discord 完成订单命令"""
        mapping = self.get_order_mapping(order_id)
        if not mapping:
            await ctx.respond(f"❌ 订单 `{order_id}` 不存在")
            return

        mapping.status = "completed"

        # 通知客户
        await self.discord_bridge.send_to_customer(
            mapping.discord_customer_channel_id,
            "🎉 **订单已完成**\n\n感谢使用！如有问题请联系客服。"
        )

        # 通知飞书
        await self.feishu.send_webhook_message(
            f"✅ 订单 #{order_id} 已完成"
        )

        await ctx.respond(f"✅ 订单 `{order_id}` 已完成")

    # ==================== 消息处理（核心） ====================

    async def _handle_customer_message(self, order_id: str, message: str, sender_id: str):
        """
        处理客户消息（Discord → 飞书）

        流程: Discord 英文消息 → 翻译成中文 → 发到飞书群
        """
        mapping = self.get_order_mapping(order_id)
        if not mapping:
            return

        logger.info(f"Customer message for order {order_id}: {message[:50]}...")

        # 翻译: 英文 → 中文
        translated = await self.translation.translate(message, "en", "zh")

        self.stats["messages_translated"] += 1
        self.stats["en_to_zh"] += 1

        # 发送到飞书群
        if mapping.feishu_chat_id:
            await self.feishu.send_message(
                mapping.feishu_chat_id,
                f"👤 [客户]\n原文: {message}\n翻译: {translated}"
            )

        # 发送到 Discord 打手频道
        await self.discord_bridge.send_to_worker(
            mapping.discord_worker_channel_id,
            f"👤 **[客户]** {translated}\n_原文: {message}_"
        )

    async def _handle_worker_message(self, order_id: str, message: str, sender_id: str):
        """
        处理打手消息（Discord 打手频道 → 客户频道）

        流程: 打手中文消息 → 翻译成英文 → 发到客户频道（匿名）
        """
        mapping = self.get_order_mapping(order_id)
        if not mapping:
            return

        logger.info(f"Worker message for order {order_id}: {message[:50]}...")

        # 翻译: 中文 → 英文
        translated = await self.translation.translate(message, "zh", "en")

        self.stats["messages_translated"] += 1
        self.stats["zh_to_en"] += 1

        # 发送到客户频道（匿名）
        await self.discord_bridge.send_to_customer(
            mapping.discord_customer_channel_id,
            f"🎮 **[Support]** {translated}"
        )

    # ==================== 飞书消息处理 ====================

    async def handle_feishu_message(self, feishu_chat_id: str, message: str, sender_id: str):
        """
        处理飞书消息（飞书 → Discord）

        流程: 飞书中文消息 → 翻译成英文 → 发到 Discord 客户频道
        """
        # 找到对应的订单
        mapping = None
        for m in self.order_mappings.values():
            if m.feishu_chat_id == feishu_chat_id:
                mapping = m
                break

        if not mapping:
            return

        logger.info(f"Feishu message for order {mapping.order_id}: {message[:50]}...")

        # 翻译: 中文 → 英文
        translated = await self.translation.translate(message, "zh", "en")

        self.stats["messages_translated"] += 1
        self.stats["zh_to_en"] += 1

        # 发送到 Discord 客户频道
        await self.discord_bridge.send_to_customer(
            mapping.discord_customer_channel_id,
            f"🎮 **[Support]** {translated}"
        )

    # ==================== 清理 ====================

    async def close(self):
        """关闭所有连接"""
        await self.translation.close()
        await self.feishu.close()


# ==================== 主入口 ====================

async def main():
    """主函数"""
    config = BridgeConfig.from_env()

    # 验证配置
    if not config.discord_token:
        logger.error("Discord token not configured")
        return

    # 创建服务
    service = BridgeService(config)

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())

