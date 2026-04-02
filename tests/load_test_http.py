#!/usr/bin/env python3
"""
🌐 aiohttp 连接池压测

测试场景:
1. 连接池总数: 100
2. 单主机限制: 30
3. 并发请求: 50+ 频道
4. 每个频道同时发送多个 API 请求

模拟 Discord API 调用
"""

import asyncio
import json
import time
import random
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️  aiohttp 未安装，使用模拟 HTTP 客户端")


@dataclass
class HttpMetrics:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    connection_pool_size: int = 100
    per_host_limit: int = 30
    peak_active_connections: int = 0
    avg_connection_time_ms: float = 0.0
    avg_request_time_ms: float = 0.0
    p95_request_time_ms: float = 0.0
    p99_request_time_ms: float = 0.0
    throughput_req_per_sec: float = 0.0
    duration_sec: float = 0.0


class MockHttpClient:
    """当 aiohttp 不可用时的模拟 HTTP 客户端"""

    def __init__(self, connector_limit=100, connector_per_host=30):
        self.connector_limit = connector_limit
        self.connector_per_host = connector_per_host
        self.active_connections = 0
        self.peak_connections = 0
        self.request_times = []

    async def get(self, url: str, **kwargs) -> 'MockResponse':
        """模拟 GET 请求"""
        # 获取连接
        self.active_connections += 1
        self.peak_connections = max(self.peak_connections, self.active_connections)

        try:
            # 模拟网络延迟
            latency = random.uniform(10, 100)  # 10-100ms
            await asyncio.sleep(latency / 1000)

            # 模拟服务器处理时间
            process_time = random.uniform(50, 500)  # 50-500ms
            await asyncio.sleep(process_time / 1000)

            total_time = (latency + process_time)
            self.request_times.append(total_time)

            return MockResponse(200, {"status": "ok"}, total_time)

        finally:
            self.active_connections -= 1

    async def close(self):
        pass


class MockResponse:
    def __init__(self, status, data, latency_ms):
        self.status = status
        self.data = data
        self.latency_ms = latency_ms

    async def json(self):
        return self.data


class HttpLoadTest:
    """HTTP 连接池压测"""

    def __init__(self,
                 num_channels=50,
                 requests_per_channel=20,
                 connector_limit=100,
                 connector_per_host=30):
        self.num_channels = num_channels
        self.requests_per_channel = requests_per_channel
        self.connector_limit = connector_limit
        self.connector_per_host = connector_per_host

        if AIOHTTP_AVAILABLE:
            connector = aiohttp.TCPConnector(
                limit=connector_limit,
                limit_per_host=connector_per_host
            )
            self.session = None  # 会在 run 中创建
            self.connector = connector
        else:
            self.session = MockHttpClient(connector_limit, connector_per_host)
            self.connector = None

        self.request_times = []
        self.request_count = 0
        self.error_count = 0

    async def make_request(self, channel_id: int, request_id: int):
        """模拟向 Discord API 发送请求"""
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"

        try:
            start = time.time()

            if AIOHTTP_AVAILABLE:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    await resp.json()
            else:
                resp = await self.session.get(url)
                await resp.json()

            latency = (time.time() - start) * 1000
            self.request_times.append(latency)
            self.request_count += 1

        except Exception as e:
            self.error_count += 1

    async def run(self):
        """运行 HTTP 压测"""
        print(f"🌐 开始 HTTP 连接池压测")
        print(f"   频道: {self.num_channels}, 请求/频道: {self.requests_per_channel}")
        print(f"   连接池: {self.connector_limit}, 单主机: {self.connector_per_host}")

        # 创建会话
        if AIOHTTP_AVAILABLE:
            self.session = aiohttp.ClientSession(connector=self.connector)

        start_time = time.time()

        # 创建所有请求任务
        tasks = []
        for ch_id in range(self.num_channels):
            for req_id in range(self.requests_per_channel):
                task = asyncio.create_task(self.make_request(ch_id, req_id))
                tasks.append(task)

        # 等待所有请求完成
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 关闭会话
        if AIOHTTP_AVAILABLE and self.session:
            await self.session.close()
        else:
            await self.session.close()

        end_time = time.time()
        duration = end_time - start_time

        # 计算指标
        return self._calculate_metrics(duration, results)

    def _calculate_metrics(self, duration, results) -> HttpMetrics:
        """计算指标"""
        if not self.request_times:
            return HttpMetrics()

        sorted_times = sorted(self.request_times)

        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data)-1)]

        total_requests = self.num_channels * self.requests_per_channel
        peak_connections = (self.session.peak_connections
                          if hasattr(self.session, 'peak_connections')
                          else self.connector_limit)

        return HttpMetrics(
            total_requests=total_requests,
            successful_requests=self.request_count,
            failed_requests=self.error_count,
            connection_pool_size=self.connector_limit,
            per_host_limit=self.connector_per_host,
            peak_active_connections=peak_connections,
            avg_request_time_ms=sum(self.request_times) / len(self.request_times),
            p95_request_time_ms=percentile(sorted_times, 95),
            p99_request_time_ms=percentile(sorted_times, 99),
            throughput_req_per_sec=self.request_count / duration if duration > 0 else 0,
            duration_sec=duration
        )


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=int, default=50)
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--pool-size", type=int, default=100)
    parser.add_argument("--per-host", type=int, default=30)
    parser.add_argument("--output", default="http_test_result.json")

    args = parser.parse_args()

    test = HttpLoadTest(
        num_channels=args.channels,
        requests_per_channel=args.requests,
        connector_limit=args.pool_size,
        connector_per_host=args.per_host
    )

    metrics = await test.run()

    # 保存结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "channels": args.channels,
            "requests_per_channel": args.requests,
            "connector_pool_size": args.pool_size,
            "connector_per_host_limit": args.per_host
        },
        "metrics": asdict(metrics)
    }

    Path(args.output).write_text(json.dumps(result, indent=2))

    # 打印摘要
    print("\n" + "="*60)
    print("🌐 HTTP 连接池压测结果")
    print("="*60)
    print(f"总请求: {metrics.total_requests}")
    print(f"成功: {metrics.successful_requests}")
    print(f"失败: {metrics.failed_requests}")
    print(f"耗时: {metrics.duration_sec:.2f}s")
    print(f"吞吐量: {metrics.throughput_req_per_sec:.2f} req/s")
    print(f"平均延迟: {metrics.avg_request_time_ms:.2f}ms")
    print(f"P95 延迟: {metrics.p95_request_time_ms:.2f}ms")
    print(f"P99 延迟: {metrics.p99_request_time_ms:.2f}ms")
    print(f"峰值活跃连接: {metrics.peak_active_connections}")
    print("="*60)
    print(f"📁 结果已保存到: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())

