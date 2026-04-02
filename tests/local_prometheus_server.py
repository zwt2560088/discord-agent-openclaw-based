#!/usr/bin/env python3
"""
🚀 本地 Prometheus 服务器 - 无需 Docker

直接在本机运行 Prometheus、Grafana 的数据接收层
"""

import http.server
import json
import socketserver
import threading
import time
from datetime import datetime
from typing import Dict


class PrometheusMetricsStorage:
    """Prometheus 指标存储"""

    def __init__(self):
        self.metrics: Dict[str, Dict] = {}
        self.last_update = time.time()

    def store_metrics(self, metrics_text: str):
        """存储 Prometheus 格式的指标"""
        self.metrics[datetime.now().isoformat()] = metrics_text
        self.last_update = time.time()

    def get_metrics(self) -> str:
        """获取最新的指标"""
        if not self.metrics:
            return "# 暂无数据\n"

        latest_time = max(self.metrics.keys())
        return self.metrics[latest_time]

    def get_json(self) -> Dict:
        """获取 JSON 格式的指标"""
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics_count": len(self.metrics),
            "last_update": self.last_update
        }


# 全局指标存储
metrics_storage = PrometheusMetricsStorage()


class MetricsHandler(http.server.SimpleHTTPRequestHandler):
    """处理 Prometheus 指标请求的 HTTP 处理器"""

    def do_GET(self):
        """处理 GET 请求"""
        if self.path == '/metrics' or self.path.startswith('/metrics/'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(metrics_storage.get_metrics().encode())

        elif self.path == '/api/v1/query':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = json.dumps(metrics_storage.get_json()).encode()
            self.wfile.write(response)

        elif self.path == '/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = json.dumps({
                "status": "running",
                "timestamp": datetime.now().isoformat(),
                "metrics_stored": len(metrics_storage.metrics)
            }).encode()
            self.wfile.write(response)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """处理 POST 请求（接收压测指标）"""
        # 支持多种 PushGateway 格式的路径
        if '/metrics/job/' in self.path or self.path == '/metrics':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode('utf-8')
                metrics_storage.store_metrics(body)

                print(f"✅ 收到压测数据 ({len(body)} bytes)")

            self.send_response(202)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = json.dumps({"status": "accepted"}).encode()
            self.wfile.write(response)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """抑制日志输出"""
        pass


class LocalPrometheusServer:
    """本地 Prometheus 服务器"""

    def __init__(self, port: int = 9091):
        self.port = port
        self.handler = MetricsHandler
        self.httpd = socketserver.TCPServer(("", port), self.handler)
        self.thread = None

    def start(self):
        """启动服务器"""
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        print(f"✅ 本地 Prometheus 服务器启动 (localhost:{self.port})")

    def stop(self):
        """停止服务器"""
        self.httpd.shutdown()


def start_local_server(port: int = 9091):
    """启动本地服务器"""
    server = LocalPrometheusServer(port=port)
    server.start()

    print(f"""
╔════════════════════════════════════════╗
║  📊 本地 Prometheus 监控服务启动完成    ║
╚════════════════════════════════════════╝

📡 服务地址:
  - PushGateway: http://localhost:{port}
  - Metrics: http://localhost:{port}/metrics
  - Status: http://localhost:{port}/status

🧪 接收压测数据:
  POST http://localhost:{port}/metrics/job/discord_bot_load_test

💡 使用方式:
  python tests/load_test_prometheus_export.py --prometheus localhost:{port}

📊 查看数据:
  curl http://localhost:{port}/metrics

🛑 停止服务: Ctrl+C

""")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 服务器已停止")
        server.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="本地 Prometheus 服务器")
    parser.add_argument("--port", type=int, default=9091, help="监听端口")

    args = parser.parse_args()

    start_local_server(args.port)

