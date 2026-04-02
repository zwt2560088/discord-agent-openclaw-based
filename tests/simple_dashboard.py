#!/usr/bin/env python3
"""
📊 简单的本地仪表板 - 不需要 Grafana

在浏览器中实时显示压测数据的 HTML 仪表板
"""

import http.server
import json
import re
import socketserver
import threading
import time
from datetime import datetime
from typing import Dict


class SimpleDashboard:
    """简单仪表板"""

    def __init__(self, port: int = 8888):
        self.port = port
        self.metrics_data: Dict = {}
        self.handler = self._create_handler()

    def _create_handler(self):
        """创建 HTTP 处理器"""
        dashboard = self

        class DashboardHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    html = dashboard.generate_html()
                    self.wfile.write(html.encode())

                elif self.path == '/api/metrics':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    response = json.dumps(dashboard.parse_metrics()).encode()
                    self.wfile.write(response)

                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        return DashboardHandler

    def update_metrics(self, metrics_text: str):
        """更新指标"""
        self.metrics_data['raw'] = metrics_text
        self.metrics_data['timestamp'] = datetime.now().isoformat()

    def parse_metrics(self) -> Dict:
        """解析 Prometheus 格式的指标"""
        result = {
            "timestamp": self.metrics_data.get('timestamp'),
            "metrics": {}
        }

        if 'raw' not in self.metrics_data:
            return result

        text = self.metrics_data['raw']

        # 提取关键指标
        patterns = {
            'throughput': r'discord_bot_throughput_msg_per_sec\s+([\d.]+)',
            'cache_hit_ratio': r'discord_bot_cache_hit_ratio\s+([\d.]+)',
            'concurrent_current': r'discord_bot_concurrent_messages_current\s+([\d.]+)',
            'concurrent_peak': r'discord_bot_concurrent_messages_peak\s+([\d.]+)',
            'cache_hits': r'discord_bot_cache_hits_total\s+([\d.]+)',
            'llm_calls_success': r'discord_bot_llm_calls_total{.*status="success".*}\s+([\d.]+)',
            'llm_calls_error': r'discord_bot_llm_calls_total{.*status="error".*}\s+([\d.]+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                result['metrics'][key] = float(match.group(1))

        return result

    def generate_html(self) -> str:
        """生成 HTML 仪表板"""
        metrics = self.parse_metrics()

        throughput = metrics['metrics'].get('throughput', 0)
        cache_ratio = metrics['metrics'].get('cache_hit_ratio', 0) * 100
        concurrent = metrics['metrics'].get('concurrent_current', 0)
        peak_concurrent = metrics['metrics'].get('concurrent_peak', 0)
        llm_success = metrics['metrics'].get('llm_calls_success', 0)
        llm_error = metrics['metrics'].get('llm_calls_error', 0)

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NBA 2K26 Bot 系统监控</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #333;
            padding: 20px;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .header {{
            text-align: center;
            color: white;
            margin-bottom: 40px;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}

        .header p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .card {{
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }}

        .card-title {{
            font-size: 0.9em;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
            font-weight: 600;
        }}

        .card-value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #2a5298;
            margin-bottom: 10px;
        }}

        .card-unit {{
            font-size: 0.9em;
            color: #999;
        }}

        .card-bar {{
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
            overflow: hidden;
            margin-top: 15px;
        }}

        .card-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #4CAF50, #45a049);
            transition: width 0.3s ease;
        }}

        .status {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
        }}

        .status-item {{
            display: flex;
            align-items: center;
            font-size: 0.9em;
        }}

        .status-indicator {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 10px;
        }}

        .status-ok {{
            background-color: #4CAF50;
        }}

        .status-warning {{
            background-color: #FFC107;
        }}

        .status-error {{
            background-color: #F44336;
        }}

        .chart {{
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}

        .chart-title {{
            font-size: 1.2em;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }}

        .timestamp {{
            text-align: center;
            color: #999;
            font-size: 0.9em;
            margin-top: 20px;
        }}

        .refresh {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #2a5298;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 0.9em;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            transition: background 0.3s ease;
        }}

        .refresh:hover {{
            background: #1e3c72;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏀 NBA 2K26 Bot 系统监控</h1>
            <p>实时性能仪表板</p>
        </div>

        <div class="grid">
            <div class="card">
                <div class="card-title">吞吐量</div>
                <div class="card-value">{throughput:.2f}</div>
                <div class="card-unit">msg/s</div>
                <div class="card-bar">
                    <div class="card-bar-fill" style="width: {{min(100, {throughput}/15*100)}}%"></div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">缓存命中率</div>
                <div class="card-value">{cache_ratio:.1f}%</div>
                <div class="card-unit">Cache Hit Ratio</div>
                <div class="card-bar">
                    <div class="card-bar-fill" style="width: {cache_ratio}%"></div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">当前并发</div>
                <div class="card-value">{concurrent:.0f}</div>
                <div class="card-unit">/ {peak_concurrent:.0f} 峰值</div>
                <div class="card-bar">
                    <div class="card-bar-fill" style="width: {{min(100, {concurrent}/{peak_concurrent}*100 if {peak_concurrent} > 0 else 0)}}%"></div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">LLM 调用</div>
                <div class="card-value">{llm_success:.0f}</div>
                <div class="card-unit">成功 / {llm_error:.0f} 失败</div>
                <div class="status">
                    <div class="status-item">
                        <div class="status-indicator status-ok"></div>
                        成功: {llm_success:.0f}
                    </div>
                    <div class="status-item">
                        <div class="status-indicator {('status-error' if llm_error > 0 else 'status-ok')}"></div>
                        失败: {llm_error:.0f}
                    </div>
                </div>
            </div>
        </div>

        <div class="chart">
            <div class="chart-title">📊 实时指标汇总</div>
            <div style="padding: 20px; background: #f5f5f5; border-radius: 8px; font-family: monospace;">
                <p>✓ 吞吐量: <strong>{throughput:.2f} msg/s</strong></p>
                <p>✓ 缓存命中率: <strong>{cache_ratio:.1f}%</strong></p>
                <p>✓ 当前并发: <strong>{concurrent:.0f}</strong></p>
                <p>✓ 峰值并发: <strong>{peak_concurrent:.0f}</strong></p>
                <p>✓ LLM 成功: <strong>{llm_success:.0f}</strong></p>
                <p>✓ 最后更新: <strong>{metrics.get('timestamp', 'N/A')}</strong></p>
            </div>
        </div>

        <div class="timestamp">
            自动刷新中... 每 5 秒更新一次
        </div>
    </div>

    <button class="refresh" onclick="location.reload()">🔄 刷新</button>

    <script>
        // 每 5 秒自动刷新
        setTimeout(() => location.reload(), 5000);
    </script>
</body>
</html>
"""
        return html

    def start(self):
        """启动仪表板服务器"""
        httpd = socketserver.TCPServer(("", self.port), self.handler)
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()

        print(f"""
╔════════════════════════════════════════╗
║  📊 本地仪表板启动完成                  ║
╚════════════════════════════════════════╝

🌐 打开浏览器:
  http://localhost:{self.port}

📡 数据来源:
  http://localhost:9091/metrics

💡 在另一个终端运行压测:
  python tests/load_test_prometheus_export.py --channels 10 --messages 100 --concurrent 10 --prometheus localhost:9091

🛑 停止服务: Ctrl+C

""")

        return httpd


def start_dashboard(port: int = 8888, metrics_server_url: str = "http://localhost:9091"):
    """启动本地仪表板"""
    import urllib.request

    dashboard = SimpleDashboard(port=port)
    httpd = dashboard.start()

    try:
        while True:
            try:
                # 定期从 Prometheus 获取数据
                with urllib.request.urlopen(f"{metrics_server_url}/metrics", timeout=5) as response:
                    metrics_text = response.read().decode('utf-8')
                    dashboard.update_metrics(metrics_text)
            except Exception as e:
                # 无法连接到 Prometheus，使用空数据
                dashboard.update_metrics("# 等待压测数据...\n")

            time.sleep(2)
    except KeyboardInterrupt:
        print("\n🛑 仪表板已停止")
        httpd.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="简单的本地仪表板")
    parser.add_argument("--port", type=int, default=8888, help="仪表板端口")
    parser.add_argument("--prometheus", type=str, default="http://localhost:9091", help="Prometheus 服务器地址")

    args = parser.parse_args()

    start_dashboard(args.port, args.prometheus)

