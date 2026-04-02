#!/usr/bin/env python3
"""
简单的监控仪表板 — 直接从 Bot 的 /metrics 端点读取数据，无需 Prometheus/Grafana
访问: http://localhost:3000
"""

import aiohttp
import asyncio
import logging
from aiohttp import web
from collections import deque
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SimpleDashboard")

# 数据缓存（保留最近 100 个样本）
metrics_history = deque(maxlen=100)
BOT_METRICS_URL = "http://localhost:8081/metrics"

async def fetch_bot_metrics():
    """从 Bot 的 /metrics 端点获取数据"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BOT_METRICS_URL, timeout=5) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    return parse_prometheus_metrics(text)
    except Exception as e:
        logger.warning(f"Failed to fetch metrics: {e}")
    return {}

def parse_prometheus_metrics(text: str) -> dict:
    """解析 Prometheus 格式的指标"""
    metrics = {}
    for line in text.split('\n'):
        if line.startswith('#') or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            metric_name = parts[0]
            metric_value = parts[1]
            try:
                metrics[metric_name] = float(metric_value)
            except ValueError:
                pass
    return metrics

async def metrics_collector_loop():
    """每 5 秒收集一次指标"""
    while True:
        try:
            metrics = await fetch_bot_metrics()
            if metrics:
                metrics['timestamp'] = datetime.now().isoformat()
                metrics_history.append(metrics)
                logger.debug(f"Collected metrics: {len(metrics)} values")
        except Exception as e:
            logger.debug(f"Collection error: {e}")
        await asyncio.sleep(5)

async def dashboard_handler(request):
    """返回 Dashboard HTML"""
    html = '''
    <!DOCTYPE html>
    <html lang="zh">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>NBA 2K26 Bot 监控仪表板</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            .header {
                color: white;
                margin-bottom: 30px;
                text-align: center;
            }
            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .header p {
                font-size: 1.1em;
                opacity: 0.9;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .card {
                background: white;
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                transition: transform 0.3s, box-shadow 0.3s;
            }
            .card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 50px rgba(0,0,0,0.3);
            }
            .card-title {
                font-size: 0.9em;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
                font-weight: 600;
            }
            .card-value {
                font-size: 2.2em;
                font-weight: bold;
                color: #333;
                margin-bottom: 5px;
            }
            .card-unit {
                font-size: 0.9em;
                color: #999;
            }
            .card.cpu { border-left: 5px solid #FF6B6B; }
            .card.memory { border-left: 5px solid #4ECDC4; }
            .card.disk { border-left: 5px solid #FFE66D; }
            .card.messages { border-left: 5px solid #95E1D3; }
            .card.errors { border-left: 5px solid #F38181; }
            .card.llm { border-left: 5px solid #A8D8EA; }
            .card.cache { border-left: 5px solid #AA96DA; }
            .card.uptime { border-left: 5px solid #FCBAD3; }

            .gauge {
                width: 100%;
                height: 150px;
                position: relative;
                margin-top: 15px;
            }

            .status-bar {
                width: 100%;
                height: 8px;
                background: #eee;
                border-radius: 4px;
                overflow: hidden;
                margin-top: 10px;
            }

            .status-bar-fill {
                height: 100%;
                background: linear-gradient(90deg, #4ECDC4 0%, #44A08D 100%);
                transition: width 0.3s;
            }

            .status-bar-fill.high {
                background: linear-gradient(90deg, #FFE66D 0%, #FF6B6B 100%);
            }

            .refresh-time {
                color: #999;
                font-size: 0.85em;
                margin-top: 10px;
            }

            .chart-container {
                background: white;
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            }

            .chart-title {
                font-size: 1.3em;
                margin-bottom: 20px;
                color: #333;
                font-weight: 600;
            }

            canvas {
                max-width: 100%;
            }

            .footer {
                text-align: center;
                color: white;
                margin-top: 30px;
                opacity: 0.8;
                font-size: 0.9em;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 NBA 2K26 Bot 监控仪表板</h1>
                <p>实时系统和应用指标</p>
            </div>

            <div class="grid" id="metrics-grid">
                <div class="card cpu">
                    <div class="card-title">Process CPU</div>
                    <div class="card-value" id="process-cpu">-</div>
                    <div class="card-unit">%</div>
                    <div class="status-bar">
                        <div class="status-bar-fill" id="process-cpu-bar" style="width: 0%"></div>
                    </div>
                    <div class="refresh-time">自动更新中...</div>
                </div>

                <div class="card memory">
                    <div class="card-title">Process Memory</div>
                    <div class="card-value" id="process-memory">-</div>
                    <div class="card-unit">MB</div>
                    <div class="status-bar">
                        <div class="status-bar-fill" id="process-memory-bar" style="width: 0%"></div>
                    </div>
                </div>

                <div class="card disk">
                    <div class="card-title">System CPU</div>
                    <div class="card-value" id="system-cpu">-</div>
                    <div class="card-unit">%</div>
                    <div class="status-bar">
                        <div class="status-bar-fill" id="system-cpu-bar" style="width: 0%"></div>
                    </div>
                </div>

                <div class="card messages">
                    <div class="card-title">Messages Processed</div>
                    <div class="card-value" id="messages">-</div>
                    <div class="card-unit">total</div>
                </div>

                <div class="card llm">
                    <div class="card-title">LLM Calls</div>
                    <div class="card-value" id="llm-calls">-</div>
                    <div class="card-unit">calls</div>
                </div>

                <div class="card llm">
                    <div class="card-title">LLM Avg Latency</div>
                    <div class="card-value" id="llm-latency">-</div>
                    <div class="card-unit">ms</div>
                </div>

                <div class="card cache">
                    <div class="card-title">Cache Hits</div>
                    <div class="card-value" id="cache-hits">-</div>
                    <div class="card-unit">hits</div>
                </div>

                <div class="card uptime">
                    <div class="card-title">Bot Uptime</div>
                    <div class="card-value" id="uptime">-</div>
                    <div class="card-unit">seconds</div>
                </div>

                <div class="card errors">
                    <div class="card-title">Total Errors</div>
                    <div class="card-value" id="errors">-</div>
                    <div class="card-unit">errors</div>
                </div>
            </div>

            <div class="chart-container">
                <div class="chart-title">📈 CPU 使用率趋势</div>
                <canvas id="cpu-chart" style="max-height: 300px;"></canvas>
            </div>
        </div>

        <div class="footer">
            <p>每 5 秒自动刷新一次 | 实时数据来自 Bot 的 /metrics 端点</p>
        </div>

        <script>
            let cpuHistory = [];

            async function updateMetrics() {
                try {
                    const response = await fetch('/api/metrics');
                    const data = await response.json();

                    if (!data || Object.keys(data).length === 0) {
                        console.warn('No metrics data received');
                        return;
                    }

                    // 更新 CPU
                    const processCpu = data.discord_bot_process_cpu_percent || 0;
                    document.getElementById('process-cpu').textContent = processCpu.toFixed(1);
                    document.getElementById('process-cpu-bar').style.width = Math.min(processCpu, 100) + '%';

                    // 更新内存
                    const processMem = data.discord_bot_process_memory_mb || 0;
                    document.getElementById('process-memory').textContent = processMem.toFixed(1);
                    document.getElementById('process-memory-bar').style.width = Math.min(processMem / 500 * 100, 100) + '%';

                    // 更新系统 CPU
                    const systemCpu = data.discord_bot_system_cpu_percent || 0;
                    document.getElementById('system-cpu').textContent = systemCpu.toFixed(1);
                    document.getElementById('system-cpu-bar').style.width = Math.min(systemCpu, 100) + '%';

                    // 更新计数器
                    document.getElementById('messages').textContent = data.discord_bot_messages_total || 0;
                    document.getElementById('llm-calls').textContent = data.discord_bot_llm_calls_total || 0;
                    document.getElementById('llm-latency').textContent = (data.discord_bot_llm_avg_latency_ms || 0).toFixed(0);
                    document.getElementById('cache-hits').textContent = data.discord_bot_cache_hits_total || 0;
                    document.getElementById('uptime').textContent = Math.round(data.discord_bot_uptime_seconds || 0);
                    document.getElementById('errors').textContent = data.discord_bot_errors_total || 0;

                    // 更新 CPU 历史图表
                    cpuHistory.push(processCpu);
                    if (cpuHistory.length > 60) cpuHistory.shift();
                    drawChart();

                } catch (error) {
                    console.error('Failed to update metrics:', error);
                }
            }

            function drawChart() {
                const canvas = document.getElementById('cpu-chart');
                const ctx = canvas.getContext('2d');
                const rect = canvas.getBoundingClientRect();

                // 设置 Canvas 大小
                canvas.width = rect.width;
                canvas.height = 250;

                const width = canvas.width;
                const height = canvas.height;
                const padding = 40;

                // 清空 Canvas
                ctx.fillStyle = '#f5f5f5';
                ctx.fillRect(0, 0, width, height);

                // 绘制网格
                ctx.strokeStyle = '#ddd';
                ctx.lineWidth = 1;
                for (let i = 0; i <= 5; i++) {
                    const y = padding + (height - 2*padding) * i / 5;
                    ctx.beginPath();
                    ctx.moveTo(padding, y);
                    ctx.lineTo(width - padding, y);
                    ctx.stroke();
                }

                // 绘制坐标轴
                ctx.strokeStyle = '#333';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(padding, padding);
                ctx.lineTo(padding, height - padding);
                ctx.lineTo(width - padding, height - padding);
                ctx.stroke();

                // 绘制 Y 轴标签
                ctx.fillStyle = '#666';
                ctx.font = '12px Arial';
                ctx.textAlign = 'right';
                for (let i = 0; i <= 5; i++) {
                    const y = padding + (height - 2*padding) * i / 5;
                    const label = (100 - i * 20);
                    ctx.fillText(label + '%', padding - 10, y + 4);
                }

                // 绘制曲线
                if (cpuHistory.length > 1) {
                    ctx.strokeStyle = '#667eea';
                    ctx.lineWidth = 3;
                    ctx.beginPath();

                    for (let i = 0; i < cpuHistory.length; i++) {
                        const x = padding + (width - 2*padding) * i / (cpuHistory.length - 1);
                        const y = height - padding - (height - 2*padding) * cpuHistory[i] / 100;

                        if (i === 0) {
                            ctx.moveTo(x, y);
                        } else {
                            ctx.lineTo(x, y);
                        }
                    }
                    ctx.stroke();

                    // 绘制数据点
                    ctx.fillStyle = '#667eea';
                    for (let i = 0; i < cpuHistory.length; i++) {
                        const x = padding + (width - 2*padding) * i / (cpuHistory.length - 1);
                        const y = height - padding - (height - 2*padding) * cpuHistory[i] / 100;
                        ctx.beginPath();
                        ctx.arc(x, y, 3, 0, 2*Math.PI);
                        ctx.fill();
                    }
                }
            }

            // 初始化和定期更新
            updateMetrics();
            setInterval(updateMetrics, 5000);
        </script>
    </body>
    </html>
    '''
    return web.Response(text=html, content_type='text/html')

async def api_metrics_handler(request):
    """返回最新的指标数据（JSON）"""
    if metrics_history:
        latest = dict(metrics_history[-1])
        # 移除 timestamp，只返回指标值
        latest.pop('timestamp', None)
        return web.json_response(latest)
    return web.json_response({})

async def main():
    """启动简单 Dashboard 服务"""
    app = web.Application()

    # 路由
    app.router.add_get('/', dashboard_handler)
    app.router.add_get('/api/metrics', api_metrics_handler)

    # 启动指标收集任务
    asyncio.create_task(metrics_collector_loop())

    # 启动 HTTP 服务器
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 3000)
    await site.start()

    logger.info("✅ Simple Dashboard started at http://localhost:3000")
    logger.info("📊 Fetching metrics from http://localhost:8081/metrics")

    # 保持运行
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dashboard stopped")

