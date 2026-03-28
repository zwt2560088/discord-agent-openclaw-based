#!/usr/bin/env python3
"""
服务抽象层
统一管理 Discord 和 WeCom 服务
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional

from config import config


class BaseService(ABC):
    """基础服务类"""

    def __init__(self, name: str):
        self.name = name
        self.is_running = False

    @abstractmethod
    async def initialize(self) -> bool:
        """初始化服务"""
        pass

    @abstractmethod
    async def start(self) -> bool:
        """启动服务"""
        pass

    @abstractmethod
    async def shutdown(self) -> bool:
        """关闭服务"""
        pass

    async def health_check(self) -> bool:
        """健康检查"""
        return self.is_running

class DiscordService(BaseService):
    """Discord 服务"""

    def __init__(self):
        super().__init__("DiscordService")
        self.bot = None
        self.loop_task = None

    async def initialize(self) -> bool:
        """初始化 Discord 服务"""
        if not config.DISCORD_TOKEN:
            print("⚠️ Discord Token 未配置，跳过 Discord 服务")
            return False

        try:
            import discord
            from discord.ext import commands

            intents = discord.Intents.default()
            intents.message_content = True

            self.bot = commands.Bot(command_prefix='!', intents=intents)

            # 设置代理
            if config.DISCORD_PROXY:
                try:
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(config.DISCORD_PROXY)
                    self.bot.http.connector = connector
                    print(f"🌐 Discord 代理已配置: {config.DISCORD_PROXY}")
                except Exception as e:
                    print(f"⚠️ 代理配置失败: {e}")

            print("✅ Discord 服务已初始化")
            return True
        except Exception as e:
            print(f"❌ Discord 服务初始化失败: {e}")
            return False

    async def start(self) -> bool:
        """启动 Discord 服务"""
        if not self.bot:
            return False

        try:
            self.is_running = True
            print("🚀 启动 Discord Bot...")
            await self.bot.start(config.DISCORD_TOKEN)
        except Exception as e:
            print(f"❌ Discord 启动失败: {e}")
            self.is_running = False
            return False

    async def shutdown(self) -> bool:
        """关闭 Discord 服务"""
        if self.bot and self.bot.ws:
            await self.bot.close()
            self.is_running = False
            print("✅ Discord 服务已关闭")
        return True

class WeComService(BaseService):
    """企业微信服务"""

    def __init__(self):
        super().__init__("WeComService")
        self.app = None
        self.runner = None

    async def initialize(self) -> bool:
        """初始化企业微信服务"""
        if not config.WX_CORP_ID or not config.WX_SECRET:
            print("⚠️ 企业微信配置不完整，跳过 WeCom 服务")
            return False

        try:
            from aiohttp import web

            self.app = web.Application()
            self.app.router.add_post('/api/wecom/callback', self.handle_callback)
            self.app.router.add_get('/api/wecom/callback', self.handle_callback)
            self.app.router.add_get('/health', self.health_endpoint)

            print("✅ 企业微信服务已初始化")
            return True
        except Exception as e:
            print(f"❌ 企业微信服务初始化失败: {e}")
            return False

    async def start(self) -> bool:
        """启动企业微信服务"""
        if not self.app:
            return False

        try:
            from aiohttp import web

            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            site = web.TCPSite(self.runner, config.HOST, config.PORT)
            await site.start()

            self.is_running = True
            print(f"✅ 企业微信服务已启动 (监听 {config.HOST}:{config.PORT})")
            return True
        except Exception as e:
            print(f"❌ 企业微信服务启动失败: {e}")
            return False

    async def shutdown(self) -> bool:
        """关闭企业微信服务"""
        if self.runner:
            await self.runner.cleanup()
            self.is_running = False
            print("✅ 企业微信服务已关闭")
        return True

    async def handle_callback(self, request):
        """处理企业微信回调"""
        # 这里放入企业微信回调逻辑
        from aiohttp import web
        return web.Response(text="ok", status=200)

    async def health_endpoint(self, request):
        """健康检查端点"""
        from aiohttp import web
        return web.Response(text="OK", status=200)

class ServiceManager:
    """服务管理器"""

    def __init__(self):
        self.services = {}
        self.is_initialized = False

    async def initialize(self):
        """初始化所有服务"""
        print("\n" + "="*60)
        print("🚀 初始化服务")
        print("="*60 + "\n")

        if config.RUN_MODE in ["all", "discord"]:
            self.services["discord"] = DiscordService()
            await self.services["discord"].initialize()

        if config.RUN_MODE in ["all", "wecom"]:
            self.services["wecom"] = WeComService()
            await self.services["wecom"].initialize()

        self.is_initialized = True
        print("\n✅ 所有服务初始化完成\n")

    async def start_all(self):
        """启动所有服务"""
        print("\n" + "="*60)
        print("🚀 启动所有服务")
        print("="*60 + "\n")

        tasks = []
        for name, service in self.services.items():
            print(f"启动服务: {name}")
            tasks.append(asyncio.create_task(service.start()))

        # 等待所有任务
        await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown_all(self):
        """关闭所有服务"""
        print("\n🛑 关闭所有服务...")
        for name, service in self.services.items():
            await service.shutdown()
        print("✅ 所有服务已关闭\n")

    def get_service(self, name: str) -> Optional[BaseService]:
        """获取服务"""
        return self.services.get(name)

    def get_discord_service(self) -> Optional[DiscordService]:
        """获取 Discord 服务"""
        return self.services.get("discord")

    def get_wecom_service(self) -> Optional[WeComService]:
        """获取企业微信服务"""
        return self.services.get("wecom")

# 服务管理器单例
service_manager = ServiceManager()

