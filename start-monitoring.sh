#!/bin/bash

# 🚀 启动完整的监控栈（支持 Docker 或本地 Python）

set -e

echo "=================================="
echo "🚀 启动 Prometheus 监控栈"
echo "=================================="

cd "$(dirname "$0")"

# 检查 Docker 是否可用
if command -v docker &> /dev/null && docker info &> /dev/null; then
    echo "📦 检测到 Docker，使用 Docker Compose..."

    # 尝试使用 docker compose（新版本）或 docker-compose（旧版本）
    if docker compose version &> /dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi

    # 启动 Prometheus 栈
    $COMPOSE_CMD up -d prometheus pushgateway alertmanager grafana

    echo ""
    echo "✅ Docker 栈启动完成！"
    echo ""
    echo "📊 服务地址："
    echo "  - Prometheus: http://localhost:9090"
    echo "  - PushGateway: http://localhost:9091"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo "  - AlertManager: http://localhost:9093"
    echo "  - 本地仪表板: http://localhost:8888"

else
    echo "⚠️  Docker 未安装，使用本地 Python 服务器..."
    echo ""
    echo "🚀 启动本地 Prometheus 服务器..."
    python tests/local_prometheus_server.py &
    PROMETHEUS_PID=$!

    echo ""
    echo "🚀 启动本地仪表板..."
    python tests/simple_dashboard.py &
    DASHBOARD_PID=$!

    echo ""
    echo "✅ 本地监控栈启动完成！"
    echo ""
    echo "📊 服务地址："
    echo "  - 仪表板: http://localhost:8888 ⭐"
    echo "  - PushGateway: http://localhost:9091"
    echo ""

    # 清理处理
    trap "kill $PROMETHEUS_PID $DASHBOARD_PID 2>/dev/null" EXIT
fi

echo ""
echo "🧪 在另一个终端运行压测:"
echo "  python tests/load_test_prometheus_export.py --channels 10 --messages 100 --concurrent 10 --prometheus localhost:9091"
echo ""
echo "📊 打开仪表板:"
echo "  http://localhost:8888"
echo ""
echo "🛑 停止服务: Ctrl+C"
echo ""

# 保持进程运行
wait

