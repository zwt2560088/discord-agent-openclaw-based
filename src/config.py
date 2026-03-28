#!/usr/bin/env python3
"""
全局配置管理
统一管理所有环境变量和配置
"""

import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

class Config:
    """配置类"""

    # ==================== 运行模式 ====================
    # 'all': 同时运行 Discord Bot + WeCom 服务
    # 'discord': 仅运行 Discord Bot
    # 'wecom': 仅运行 WeCom 服务
    RUN_MODE = os.getenv("RUN_MODE", "all")

    # ==================== Discord 配置 ====================
    DISCORD_TOKEN: str = os.getenv("discord_token", "") or os.getenv("DISCORD_TOKEN", "")
    DISCORD_GUILD_ID: str = os.getenv("DISCORD_GUILD_ID", "")
    DISCORD_PROXY: str = os.getenv("HTTP_PROXY", "")

    # ==================== 企业微信配置 ====================
    WX_CORP_ID: str = os.getenv("WX_CORP_ID", "")
    WX_AGENT_ID: str = os.getenv("WX_AGENT_ID", "1000002")
    WX_SECRET: str = os.getenv("WX_SECRET", "")
    WX_TOKEN: str = os.getenv("WX_TOKEN", "")
    WX_AES_KEY: str = os.getenv("WX_AES_KEY", "")
    WX_ADMIN_USERID: str = os.getenv("WX_ADMIN_USERID", "admin")
    WX_ADMIN_ID: str = os.getenv("WX_ADMIN_ID", "")

    # ==================== 服务器配置 ====================
    PORT: int = int(os.getenv("PORT", 8080))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # ==================== AI Agent 配置 ====================
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ENABLE_AI_AGENT: bool = os.getenv("ENABLE_AI_AGENT", "true").lower() == "true"

    # ==================== 数据库配置 ====================
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///orders.db")
    DB_PATH: str = "orders.db"

    # ==================== 订单配置 ====================
    ORDER_PREFIX: str = "order"
    ORDER_SERVICE_DEFAULT: str = "2k26"

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "nba2k26.log")

    # ==================== 特性开关 ====================
    ENABLE_AUTO_RENAME: bool = True
    ENABLE_MESSAGE_LOGGING: bool = True
    ENABLE_ORDER_MAPPING: bool = True

    @staticmethod
    def validate() -> tuple[bool, str]:
        """验证必要的配置"""
        errors = []

        if Config.RUN_MODE in ["all", "discord"]:
            if not Config.DISCORD_TOKEN:
                errors.append("❌ DISCORD_TOKEN 未配置")

        if Config.RUN_MODE in ["all", "wecom"]:
            if not Config.WX_CORP_ID:
                errors.append("❌ WX_CORP_ID 未配置")
            if not Config.WX_SECRET:
                errors.append("❌ WX_SECRET 未配置")

        if errors:
            return False, "\n".join(errors)

        return True, "✅ 配置验证成功"

    @staticmethod
    def summary() -> str:
        """配置摘要"""
        return f"""
╔════════════════════════════════════════════════════════╗
║           NBA 2K26 业务系统 - 配置摘要                 ║
╚════════════════════════════════════════════════════════╝

运行模式: {Config.RUN_MODE}

Discord:
  Token: {'✅' if Config.DISCORD_TOKEN else '❌'}
  Guild: {Config.DISCORD_GUILD_ID or '当前服务器'}
  代理: {Config.DISCORD_PROXY or '无'}

企业微信:
  企业ID: {'✅' if Config.WX_CORP_ID else '❌'}
  应用ID: {Config.WX_AGENT_ID}
  密钥: {'✅' if Config.WX_SECRET else '❌'}

AI Agent:
  启用: {'✅' if Config.ENABLE_AI_AGENT else '❌'}
  OpenAI: {'✅' if Config.OPENAI_API_KEY else '❌'}

服务器:
  地址: {Config.HOST}:{Config.PORT}

数据库:
  路径: {Config.DB_PATH}
"""

# 配置单例
config = Config()

