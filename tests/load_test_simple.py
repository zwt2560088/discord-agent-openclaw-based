#!/usr/bin/env python3
"""
🔥 Discord Bot 完整并发压测 - 简化版

快速开始:
    python tests/load_test_simple.py --channels 50 --messages 100
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict

# 配置详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


@dataclass
class Metrics:
    total_sent: int = 0
    total_processed: int = 0
    total_errors: int = 0
    peak_concurrent: int = 0
    throughput: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    cache_hit_ratio: float = 0.0
    db_p95_ms: float = 0.0
    duration_sec: float = 0.0


class LoadTest:
    def __init__(self, num_channels=50, msgs_per_channel=100, concurrent_limit=20):
        self.num_channels = num_channels
        self.msgs_per_channel = msgs_per_channel
        self.concurrent_limit = concurrent_limit

        self.semaphore = asyncio.Semaphore(concurrent_limit)
        self.queue = asyncio.Queue()
        self.concurrent_count = 0
        self.peak_concurrent = 0
        self.concurrent_samples = 0
        self.total_concurrent_sum = 0

        self.cache = {}
        self.latencies = []
        self.db_times = []
        self.cache_hits = 0
        self.total_messages = 0

    async def message_processor(self, message: Dict):
        """处理单条消息"""
        msg_id = message['message_id']
        channel = message['channel']
        start_time = time.time()

        # 1️⃣ 尝试缓存命中
        cache_key = f"{channel}:latest"
        if cache_key in self.cache:
            self.cache_hits += 1
            await asyncio.sleep(0.01)  # 缓存查找 10ms
            cache_time = (time.time() - start_time) * 1000
            logger.info(f"✓ {msg_id:15s} | 缓存命中 ({cache_time:.2f}ms)")
            return

        # 2️⃣ 模拟 AI 处理 (Poisson 分布)
        base_time = random.expovariate(1.0 / 500)  # 平均 500ms
        proc_time = max(50, min(base_time, 3000)) / 1000  # 转为秒，范围 50-3000ms
        await asyncio.sleep(proc_time)
        proc_ms = proc_time * 1000
        self.latencies.append(proc_ms)

        # 3️⃣ 模拟数据库写入
        db_start = time.time()
        await asyncio.sleep(0.01)  # 数据库写入 ~10ms
        db_time = (time.time() - db_start) * 1000
        self.db_times.append(db_time)

        # 4️⃣ 更新缓存
        self.cache[cache_key] = message

        total_time = (time.time() - start_time) * 1000
        logger.info(f"✓ {msg_id:15s} | {channel:8s} | AI:{proc_ms:7.2f}ms | DB:{db_time:5.2f}ms | 总:{total_time:7.2f}ms")

    async def worker(self, worker_id: int):
        """工作线程 - 从队列处理消息"""
        logger.info(f"👷 Worker {worker_id} 启动")
        msg_count = 0

        while True:
            try:
                message = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                break

            # 获取信号量（核心限流）
            async with self.semaphore:
                self.concurrent_count += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)
                self.total_concurrent_sum += self.concurrent_count
                self.concurrent_samples += 1

                msg_count += 1
                logger.debug(f"👷 Worker {worker_id} 处理消息 {msg_count}, 当前并发: {self.concurrent_count}/{self.semaphore._value+self.concurrent_count}")

                try:
                    await self.message_processor(message)
                except Exception as e:
                    logger.error(f"❌ {message['message_id']} 处理失败: {e}")
                finally:
                    self.concurrent_count -= 1

            self.queue.task_done()

        logger.info(f"👷 Worker {worker_id} 完成 (处理了 {msg_count} 条消息)")

    async def run(self):
        """运行压测"""
        logger.info("=" * 70)
        logger.info(f"🚀 开始压测: {self.num_channels} 频道, {self.msgs_per_channel} 条/频道")
        logger.info(f"   并发限制: {self.concurrent_limit}, 总消息: {self.num_channels * self.msgs_per_channel}")
        logger.info("=" * 70)

        start_time = time.time()

        # 启动工作线程
        num_workers = min(self.concurrent_limit, 10)
        logger.info(f"启动 {num_workers} 个工作线程...")
        workers = [
            asyncio.create_task(self.worker(i))
            for i in range(num_workers)
        ]

        # 生成并提交消息
        self.total_messages = self.num_channels * self.msgs_per_channel
        logger.info(f"生成 {self.total_messages} 条消息...")

        for ch_id in range(self.num_channels):
            for msg_id in range(self.msgs_per_channel):
                message = {
                    "channel": f"ch_{ch_id}",
                    "message_id": f"msg_{ch_id}_{msg_id}",
                    "content": f"Test {msg_id}"
                }
                await self.queue.put(message)

                # 控制提交速率
                if msg_id % 50 == 0:
                    await asyncio.sleep(0.01)

        logger.info(f"✅ 已提交 {self.total_messages} 条消息到队列")
        logger.info("等待处理完成...")

        # 等待处理完成
        await self.queue.join()

        # 等待工作线程完成
        await asyncio.gather(*workers)

        end_time = time.time()
        duration = end_time - start_time

        # 计算指标
        metrics = self._calculate_metrics(duration)

        logger.info("=" * 70)
        logger.info("✅ 压测完成!")
        logger.info("=" * 70)

        return metrics

    def _calculate_metrics(self, duration) -> Metrics:
        """计算性能指标"""
        if not self.latencies:
            return Metrics()

        sorted_latencies = sorted(self.latencies)

        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data)-1)]

        avg_concurrent = self.total_concurrent_sum / self.concurrent_samples if self.concurrent_samples > 0 else 0

        return Metrics(
            total_sent=self.total_messages,
            total_processed=len(self.latencies),
            total_errors=self.total_messages - len(self.latencies),
            peak_concurrent=self.peak_concurrent,
            throughput=len(self.latencies) / duration if duration > 0 else 0,
            avg_latency_ms=sum(self.latencies) / len(self.latencies) if self.latencies else 0,
            p95_latency_ms=percentile(sorted_latencies, 95),
            p99_latency_ms=percentile(sorted_latencies, 99),
            cache_hit_ratio=self.cache_hits / self.total_messages if self.total_messages > 0 else 0,
            db_p95_ms=percentile(sorted(self.db_times), 95) if self.db_times else 0,
            duration_sec=duration
        )


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=int, default=50)
    parser.add_argument("--messages", type=int, default=100)
    parser.add_argument("--concurrent", type=int, default=20)
    parser.add_argument("--output", default="load_test_result.json")

    args = parser.parse_args()

    test = LoadTest(
        num_channels=args.channels,
        msgs_per_channel=args.messages,
        concurrent_limit=args.concurrent
    )

    metrics = await test.run()

    # 保存结果
    result = {
        "timestamp": datetime.now().isoformat(),
        "config": {
            "channels": args.channels,
            "messages_per_channel": args.messages,
            "concurrent_limit": args.concurrent
        },
        "metrics": asdict(metrics)
    }

    Path(args.output).write_text(json.dumps(result, indent=2))

    # 打印摘要
    print("\n" + "="*60)
    print("📊 压测结果")
    print("="*60)
    print(f"总消息: {metrics.total_sent}")
    print(f"成功: {metrics.total_processed}")
    print(f"失败: {metrics.total_errors}")
    print(f"耗时: {metrics.duration_sec:.2f}s")
    print(f"吞吐量: {metrics.throughput:.2f} msg/s")
    print(f"平均延迟: {metrics.avg_latency_ms:.2f}ms")
    print(f"P95 延迟: {metrics.p95_latency_ms:.2f}ms")
    print(f"P99 延迟: {metrics.p99_latency_ms:.2f}ms")
    print(f"峰值并发: {metrics.peak_concurrent}")
    print(f"缓存命中: {metrics.cache_hit_ratio*100:.1f}%")
    print(f"DB P95: {metrics.db_p95_ms:.2f}ms")
    print("="*60)
    print(f"📁 结果已保存到: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())

