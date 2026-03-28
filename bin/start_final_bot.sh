#!/bin/bash

# 🚀 最终版 Discord Bot 一键启动脚本
# 用法: bash start_final_bot.sh

set -e  # 任何命令失败都退出

echo "════════════════════════════════════════════"
echo "🚀 启动最终版 Discord Bot"
echo "════════════════════════════════════════════"

# 检查 Python 版本
echo "🔍 检查 Python 版本..."
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✅ Python 版本: $python_version"

# 检查依赖
echo ""
echo "🔍 检查依赖..."
required_packages=("discord" "aiohttp" "dotenv")

for package in "${required_packages[@]}"; do
    if python3 -c "import ${package}" 2>/dev/null; then
        echo "✅ $package 已安装"
    else
        echo "⚠️  $package 未安装，正在安装..."
        pip3 install "$package" -q
        echo "✅ $package 安装完成"
    fi
done

# 检查 .env 文件
echo ""
echo "🔍 检查配置文件..."
if [ ! -f ".env" ]; then
    echo "⚠️  .env 文件不存在，创建默认配置..."
    cat > .env << 'EOF'
# Discord Bot 配置
discord_token=YOUR_DISCORD_TOKEN_HERE

# AI 模型选择（至少配置一个）
openai_api_key=YOUR_OPENAI_KEY_HERE
deepseek_api_key=YOUR_DEEPSEEK_KEY_HERE

# 网络配置（中国用户可选）
HTTP_PROXY=http://127.0.0.1:8890
EOF
    echo "✅ .env 文件已创建，请编辑并填写 TOKEN"
    echo "📝 编辑: nano .env"
    exit 1
else
    echo "✅ .env 文件存在"
fi

# 检查必要的 TOKEN
echo ""
echo "🔍 验证 TOKEN 配置..."
discord_token=$(grep -m 1 "discord_token" .env | cut -d'=' -f2 | xargs)
if [ -z "$discord_token" ] || [ "$discord_token" = "YOUR_DISCORD_TOKEN_HERE" ]; then
    echo "❌ 错误: discord_token 未配置!"
    echo "请编辑 .env 文件，填入你的 Discord Bot Token"
    exit 1
fi
echo "✅ discord_token 已配置"

ai_key=$(grep -E "openai_api_key|deepseek_api_key" .env | cut -d'=' -f2 | xargs | head -1)
if [ -z "$ai_key" ] || [ "$ai_key" = "YOUR_OPENAI_KEY_HERE" ] || [ "$ai_key" = "YOUR_DEEPSEEK_KEY_HERE" ]; then
    echo "⚠️  警告: AI API Key 未配置，机器人将以关键词模式运行（仅快速回复）"
else
    echo "✅ AI API Key 已配置"
fi

# 检查数据库/缓存目录
echo ""
echo "🔍 检查数据目录..."
mkdir -p ./data ./logs
echo "✅ 数据目录就绪"

# 显示性能指标
echo ""
echo "════════════════════════════════════════════"
echo "📊 性能指标（预期）:"
echo "════════════════════════════════════════════"
echo "关键词快速回复: <500ms ⚡"
echo "AI 智能回复: <2s"
echo "最大并发: 50+ 频道"
echo "内存占用: ~200-250MB"
echo "P95 延迟: <500ms"
echo ""

# 清理旧日志
echo "🧹 清理旧日志..."
find ./logs -name "*.log" -mtime +7 -delete 2>/dev/null || true
echo "✅ 清理完成"

# 启动 Bot
echo ""
echo "════════════════════════════════════════════"
echo "🚀 启动 Discord Bot..."
echo "════════════════════════════════════════════"
echo ""
echo "💡 提示:"
echo "  • 按 Ctrl+C 可停止 Bot"
echo "  • 在 Discord 中 @Bot 或在 order- 频道内发送消息"
echo "  • 查看日志: tail -f logs/*.log"
echo ""

# 启动 Bot（带日志）
log_file="./logs/bot_$(date +%Y%m%d_%H%M%S).log"
python3 src/discord_bot_final.py 2>&1 | tee "$log_file"

# 捕获退出
echo ""
echo "🛑 Bot 已停止"
echo "📋 日志已保存: $log_file"

