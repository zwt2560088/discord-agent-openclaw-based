"""
启动脚本 - 同时运行 Discord Bot 和订单监控面板
"""
import os
import sys
import threading
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def run_discord_bot():
    """运行 Discord Bot"""
    print("🤖 Starting Discord Bot...")
    os.system(f"cd {os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))} && python simple_bot.py")


def run_monitor_server():
    """运行订单监控服务器"""
    print("📊 Starting Order Monitor Server...")
    from src.orders.monitor_server import run_server
    run_server(port=8081)


def run_pricing_server():
    """运行定价服务器"""
    print("💰 Starting Pricing Server...")
    from src.pricing.pricing_server import run_server
    run_server(port=8080)


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 NBA2K26 Business System Starting...")
    print("=" * 50)

    # 启动监控服务器 (后台线程)
    monitor_thread = threading.Thread(target=run_monitor_server, daemon=True)
    monitor_thread.start()
    time.sleep(1)

    # 启动定价服务器 (后台线程)
    pricing_thread = threading.Thread(target=run_pricing_server, daemon=True)
    pricing_thread.start()
    time.sleep(1)

    print("")
    print("📊 Order Monitor: http://localhost:8081")
    print("💰 Pricing Admin: http://localhost:8080")
    print("")

    # 主线程运行 Discord Bot
    run_discord_bot()

