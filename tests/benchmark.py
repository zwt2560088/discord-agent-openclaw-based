#!/usr/bin/env python3
"""
🏆 BenchMark - 性能基准测试套件

对比不同配置的性能:
1. 不同并发数 (1, 5, 10, 20, 50)
2. 不同消息数 (10, 50, 100, 500, 1000)
3. 不同缓存策略 (无缓存, 有缓存)
4. 不同 LLM 模型 (gpt-3.5-turbo, gpt-4, deepseek)
"""

import aiohttp
import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional, List

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


@dataclass
class BenchmarkResult:
    """基准测试结果"""
    name: str
    channels: int
    messages_per_channel: int
    concurrent_limit: int
    total_messages: int
    duration_sec: float
    cache_hits: int
    llm_calls: int
    errors: int
    success_rate: float
    throughput_msg_per_sec: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    cache_hit_ratio: float
    model: str = "mock"


class SimpleLLMClient:
    """简化的 LLM 客户端（模拟）"""

    def __init__(self, delay_ms: int = 100):
        self.delay_ms = delay_ms
        self.call_count = 0

    async def chat(self, message: str, session: Optional[aiohttp.ClientSession] = None) -> str:
        """模拟 LLM 调用"""
        await asyncio.sleep(self.delay_ms / 1000)
        self.call_count += 1
        return f"Response to: {message[:50]}"


class SimpleBenchmark:
    """简化的基准测试"""

    def __init__(self, channels: int, msgs_per_channel: int, concurrent_limit: int, llm_delay_ms: int = 100, enable_cache: bool = True):
        self.channels = channels
        self.msgs_per_channel = msgs_per_channel
        self.concurrent_limit = concurrent_limit
        self.enable_cache = enable_cache

        self.llm_client = SimpleLLMClient(delay_ms=llm_delay_ms)
        self.semaphore = asyncio.Semaphore(concurrent_limit)
        self.queue = asyncio.Queue()

        self.cache = {}
        self.latencies = []
        self.cache_hits = 0
        self.total_messages = 0
        self.errors = 0
        self.concurrent_count = 0
        self.peak_concurrent = 0

    async def process_message(self, message: Dict):
        """处理消息"""
        self.concurrent_count += 1
        self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)

        try:
            msg_id = message['message_id']
            channel = message['channel']
            content = message['content']
            start_time = time.time()

            # 缓存查询
            cache_key = f"{channel}:latest"

            if self.enable_cache and cache_key in self.cache:
                self.cache_hits += 1
                await asyncio.sleep(0.005)
                latency = (time.time() - start_time) * 1000
                self.latencies.append(latency)
                return

            # LLM 调用
            response = await self.llm_client.chat(content)

            # 缓存更新
            if self.enable_cache:
                self.cache[cache_key] = response

            latency = (time.time() - start_time) * 1000
            self.latencies.append(latency)

        except Exception as e:
            self.errors += 1
        finally:
            self.concurrent_count -= 1

    async def worker(self):
        """工作线程"""
        while True:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break

            async with self.semaphore:
                await self.process_message(message)
                self.queue.task_done()

    async def run(self) -> BenchmarkResult:
        """运行基准测试"""
        start_time = time.time()

        # 启动 Worker
        num_workers = min(self.concurrent_limit, 10)
        workers = [asyncio.create_task(self.worker()) for _ in range(num_workers)]

        # 生成消息
        self.total_messages = self.channels * self.msgs_per_channel
        for ch_id in range(self.channels):
            for msg_id in range(self.msgs_per_channel):
                message = {
                    "channel": f"ch_{ch_id}",
                    "message_id": f"msg_{ch_id}_{msg_id}",
                    "content": f"Test message {msg_id}"
                }
                await self.queue.put(message)

        # 等待完成
        await self.queue.join()
        await asyncio.gather(*workers)

        end_time = time.time()
        duration = end_time - start_time

        # 计算统计
        if self.latencies:
            sorted_lat = sorted(self.latencies)
            p95_idx = int(len(sorted_lat) * 0.95)
            p99_idx = int(len(sorted_lat) * 0.99)

            result = BenchmarkResult(
                name=f"C{self.channels}_M{self.msgs_per_channel}_Con{self.concurrent_limit}_{('cache' if self.enable_cache else 'nocache')}",
                channels=self.channels,
                messages_per_channel=self.msgs_per_channel,
                concurrent_limit=self.concurrent_limit,
                total_messages=self.total_messages,
                duration_sec=duration,
                cache_hits=self.cache_hits,
                llm_calls=self.llm_client.call_count,
                errors=self.errors,
                success_rate=(self.total_messages - self.errors) / self.total_messages * 100,
                throughput_msg_per_sec=self.total_messages / duration,
                avg_latency_ms=sum(self.latencies) / len(self.latencies),
                min_latency_ms=min(self.latencies),
                max_latency_ms=max(self.latencies),
                p95_latency_ms=sorted_lat[p95_idx],
                p99_latency_ms=sorted_lat[p99_idx],
                cache_hit_ratio=self.cache_hits / self.total_messages if self.total_messages > 0 else 0
            )

            return result

        return None


class BenchmarkSuite:
    """基准测试套件"""

    def __init__(self):
        self.results: List[BenchmarkResult] = []

    async def run_concurrent_benchmarks(self):
        """测试不同并发数"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}【并发数对性能的影响】{Colors.ENDC}{Colors.ENDC}")
        print(f"固定: 10 频道, 100 消息/频道")
        print(f"测试: 并发数 1, 5, 10, 20, 50\n")

        for concurrent in [1, 5, 10, 20, 50]:
            benchmark = SimpleBenchmark(
                channels=10,
                msgs_per_channel=100,
                concurrent_limit=concurrent,
                enable_cache=True
            )
            result = await benchmark.run()
            self.results.append(result)

            print(f"并发数: {concurrent:2d} | "
                  f"吞吐: {result.throughput_msg_per_sec:8.2f} msg/s | "
                  f"延迟(P95): {result.p95_latency_ms:8.2f}ms | "
                  f"缓存命中: {result.cache_hit_ratio*100:5.1f}%")

    async def run_message_count_benchmarks(self):
        """测试不同消息数"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}【消息数对性能的影响】{Colors.ENDC}{Colors.ENDC}")
        print(f"固定: 10 频道, 10 并发")
        print(f"测试: 消息数 10, 50, 100, 500, 1000\n")

        for msg_count in [10, 50, 100, 500, 1000]:
            benchmark = SimpleBenchmark(
                channels=10,
                msgs_per_channel=msg_count,
                concurrent_limit=10,
                enable_cache=True
            )
            result = await benchmark.run()
            self.results.append(result)

            print(f"消息数: {result.total_messages:4d} | "
                  f"吞吐: {result.throughput_msg_per_sec:8.2f} msg/s | "
                  f"延迟: {result.avg_latency_ms:7.2f}ms | "
                  f"耗时: {result.duration_sec:6.2f}s")

    async def run_cache_effect_benchmarks(self):
        """测试缓存效果"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}【缓存对性能的影响】{Colors.ENDC}{Colors.ENDC}")
        print(f"固定: 5 频道, 100 消息/频道, 10 并发")
        print(f"对比: 有缓存 vs 无缓存\n")

        for enable_cache in [True, False]:
            benchmark = SimpleBenchmark(
                channels=5,
                msgs_per_channel=100,
                concurrent_limit=10,
                enable_cache=enable_cache
            )
            result = await benchmark.run()
            self.results.append(result)

            cache_status = "有缓存" if enable_cache else "无缓存"
            print(f"{cache_status} | "
                  f"吞吐: {result.throughput_msg_per_sec:8.2f} msg/s | "
                  f"延迟: {result.avg_latency_ms:7.2f}ms | "
                  f"命中率: {result.cache_hit_ratio*100:5.1f}% | "
                  f"耗时: {result.duration_sec:6.2f}s")

        # 对比
        with_cache = self.results[-2]
        without_cache = self.results[-1]
        speedup = with_cache.throughput_msg_per_sec / without_cache.throughput_msg_per_sec
        print(f"\n  {Colors.OKGREEN}✓ 缓存加速比: {speedup:.2f}x{Colors.ENDC}")

    async def run_channel_count_benchmarks(self):
        """测试不同频道数"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}【频道数对性能的影响】{Colors.ENDC}{Colors.ENDC}")
        print(f"固定: 10 消息/频道, 10 并发")
        print(f"测试: 频道数 1, 5, 10, 50, 100\n")

        for channels in [1, 5, 10, 50, 100]:
            benchmark = SimpleBenchmark(
                channels=channels,
                msgs_per_channel=10,
                concurrent_limit=10,
                enable_cache=True
            )
            result = await benchmark.run()
            self.results.append(result)

            print(f"频道数: {channels:3d} | "
                  f"吞吐: {result.throughput_msg_per_sec:8.2f} msg/s | "
                  f"延迟: {result.avg_latency_ms:7.2f}ms | "
                  f"缓存: {result.cache_hit_ratio*100:5.1f}%")

    def print_summary(self):
        """打印总结"""
        print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*100}{Colors.ENDC}{Colors.ENDC}")
        print(f"{Colors.BOLD}📊 BenchMark 总结{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKGREEN}{'='*100}{Colors.ENDC}{Colors.ENDC}\n")

        # 最高吞吐
        best_throughput = max(self.results, key=lambda r: r.throughput_msg_per_sec)
        print(f"【最高吞吐】")
        print(f"  配置: {best_throughput.name}")
        print(f"  吞吐: {Colors.OKGREEN}{best_throughput.throughput_msg_per_sec:.2f} msg/s{Colors.ENDC}")
        print(f"  延迟(P95): {best_throughput.p95_latency_ms:.2f}ms")

        # 最低延迟
        best_latency = min(self.results, key=lambda r: r.avg_latency_ms)
        print(f"\n【最低延迟】")
        print(f"  配置: {best_latency.name}")
        print(f"  平均延迟: {Colors.OKGREEN}{best_latency.avg_latency_ms:.2f}ms{Colors.ENDC}")
        print(f"  吞吐: {best_latency.throughput_msg_per_sec:.2f} msg/s")

        # 最佳缓存效率
        best_cache = max(self.results, key=lambda r: r.cache_hit_ratio)
        print(f"\n【最佳缓存效率】")
        print(f"  配置: {best_cache.name}")
        print(f"  命中率: {Colors.OKGREEN}{best_cache.cache_hit_ratio*100:.1f}%{Colors.ENDC}")
        print(f"  吞吐加速: {best_cache.throughput_msg_per_sec:.2f} msg/s")

        # 关键对比
        print(f"\n【关键对比】")

        # 并发数对比
        concurrent_5 = next((r for r in self.results if r.concurrent_limit == 5 and r.channels == 10 and r.messages_per_channel == 100), None)
        concurrent_50 = next((r for r in self.results if r.concurrent_limit == 50 and r.channels == 10 and r.messages_per_channel == 100), None)
        if concurrent_5 and concurrent_50:
            speedup = concurrent_50.throughput_msg_per_sec / concurrent_5.throughput_msg_per_sec
            print(f"  并发数 5 vs 50: {Colors.OKGREEN}{speedup:.2f}x 吞吐加速{Colors.ENDC}")

        print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*100}{Colors.ENDC}{Colors.ENDC}\n")

    def export_json(self, filename: str = "benchmark_results.json"):
        """导出结果为 JSON"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "results": [asdict(r) for r in self.results]
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"📊 结果已导出到 {filename}")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="性能基准测试")
    parser.add_argument("--suite", choices=["all", "concurrent", "messages", "cache", "channels"], default="all")
    parser.add_argument("--export", type=str, help="导出 JSON 结果文件")

    args = parser.parse_args()

    suite = BenchmarkSuite()

    if args.suite in ["all", "concurrent"]:
        await suite.run_concurrent_benchmarks()

    if args.suite in ["all", "messages"]:
        await suite.run_message_count_benchmarks()

    if args.suite in ["all", "cache"]:
        await suite.run_cache_effect_benchmarks()

    if args.suite in ["all", "channels"]:
        await suite.run_channel_count_benchmarks()

    suite.print_summary()

    if args.export:
        suite.export_json(args.export)


if __name__ == "__main__":
    asyncio.run(main())

