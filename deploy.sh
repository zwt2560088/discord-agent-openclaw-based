#!/bin/bash
# NBA 2K26 Discord Bot 部署脚本

set -e

echo "🚀 开始部署 NBA 2K26 Discord Bot..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "⚠️ .env 文件不存在，正在创建模板..."
    cat > .env << 'EOF'
# Discord Bot
DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_GUILD_ID=your_guild_id

# AI API Keys
DEEPSEEK_API_KEY=sk-xxx
OPENAI_API_KEY=sk-xxx

# 管理员用户ID列表（逗号分隔）
ADMIN_USER_IDS=123456789,987654321

# Web 管理密码
ADMIN_PASSWORD=your_secure_password

# Grafana 密码
GRAFANA_PASSWORD=admin

# 代理（可选，中国网络可能需要）
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
EOF
    echo "✅ 已创建 .env 模板，请编辑后重新运行部署脚本"
    exit 1
fi

# 加载环境变量
export $(grep -v '^#' .env | xargs)

# 创建必要的目录
mkdir -p data knowledge grafana/provisioning/datasources grafana/provisioning/dashboards

# 创建 Grafana 数据源配置
cat > grafana/provisioning/datasources/prometheus.yml << 'EOF'
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
EOF

# 构建并启动容器
echo "🐳 构建 Docker 镜像..."
docker-compose build

echo "🚀 启动服务..."
docker-compose up -d

echo ""
echo "✅ 部署完成！"
echo ""
echo "📊 访问地址："
echo "   Discord Bot Web 管理: http://localhost:8081/admin"
echo "   Prometheus:           http://localhost:9090"
echo "   Grafana:              http://localhost:3000"
echo ""
echo "🔐 默认密码："
echo "   Web 管理: ${ADMIN_PASSWORD}"
echo "   Grafana:  admin / ${GRAFANA_PASSWORD:-admin}"
echo ""
echo "📝 查看日志: docker-compose logs -f discord-bot"

