"""
Discord ↔ OpenClaw ↔ 飞书 全链路桥接服务 - 主入口

这是整合了所有功能的主启动脚本：
- Discord Bot（接收客户消息）
- Webhook Server（接收飞书回调）
- 翻译引擎（中英互译）
- 订单管理（创建/分配/完成）

使用方法:
    python run_bridge.py

环境变量:
    见 .env.bridge.example
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/bridge.log', encoding='utf-8')
    ]
)
logger = logging.getLogger("Main")

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def main():
    """主函数"""
    from src.orders.bridge_service import BridgeService, BridgeConfig
    from src.orders.webhook_server import WebhookServer

    # 加载配置
    config = BridgeConfig.from_env()

    # 验证必要配置
    if not config.discord_token:
        logger.error("❌ Discord Token 未配置！请设置环境变量 discord_token")
        return

    logger.info("=" * 50)
    logger.info("Discord ↔ OpenClaw ↔ 飞书 全链路桥接服务")
    logger.info("=" * 50)
    logger.info("")
    logger.info("架构:")
    logger.info("  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐")
    logger.info("  │   Discord   │ ←→  │  OpenClaw   │ ←→  │   Feishu    │")
    logger.info("  │  (客户英文)  │     │ (翻译+中转)  │     │ (打手中文)   │")
    logger.info("  └─────────────┘     └─────────────┘     └─────────────┘")
    logger.info("")

    # 创建桥接服务
    bridge = BridgeService(config)

    # 创建 Webhook 服务
    webhook_port = int(os.getenv("WEBHOOK_PORT", "8080"))
    webhook = WebhookServer(bridge, port=webhook_port)

    # 注册 OpenClaw 事件处理器
    async def on_task_completed(data):
        order_id = data.get("order_id")
        logger.info(f"📝 OpenClaw 任务完成: {order_id}")

    async def on_worker_assigned(data):
        order_id = data.get("order_id")
        worker_name = data.get("worker_name", "Unknown")
        logger.info(f"👤 OpenClaw 打手分配: {order_id} -> {worker_name}")

    webhook.register_openclaw_handler("task.completed", on_task_completed)
    webhook.register_openclaw_handler("worker.assigned", on_worker_assigned)

    try:
        # 启动 Webhook 服务（后台）
        await webhook.start()
        logger.info(f"✅ Webhook 服务已启动，端口 {webhook_port}")
        logger.info(f"   - 飞书回调: http://your-server:{webhook_port}/webhook/feishu")
        logger.info(f"   - OpenClaw回调: http://your-server:{webhook_port}/webhook/openclaw")

        # 启动 Discord Bot（前台，会阻塞）
        logger.info("🚀 启动 Discord Bot...")
        await bridge.start()

    except KeyboardInterrupt:
        logger.info("⏹️ 收到停止信号")
    except Exception as e:
        logger.error(f"❌ 服务错误: {e}")
        raise
    finally:
        # 清理
        logger.info("🧹 清理资源...")
        await webhook.stop()
        await bridge.close()
        logger.info("✅ 服务已停止")


if __name__ == "__main__":
    # 确保日志目录存在
    os.makedirs("logs", exist_ok=True)

    # 运行主程序
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

