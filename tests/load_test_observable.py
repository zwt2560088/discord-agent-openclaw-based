#!/usr/bin/env python3
"""
🔍 完全可观测的压测工具 - 每个细节都可见

实时显示:
1. 队列状态 (深度、等待中的消息)
2. 并发状态 (当前/峰值/平均)
3. 延迟实时分布 (直方图)
4. 吞吐量趋势 (滚动平均)
5. 工作线程状态 (每个 worker 处理数)
6. 缓存效率 (命中率变化)
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


# 彩色输出
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

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


class ObservableLoadTest:
    """完全可观测的压测"""

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

        # 详细的事件日志
        self.events = []
        self.worker_stats = {}

        # 实时指标
        self.last_printed = time.time()
        self.print_interval = 2  # 每 2 秒打印一次状态

    async def message_processor(self, message: Dict):
        """处理单条消息"""
        msg_id = message['message_id']
        channel = message['channel']
        start_time = time.time()

        # 缓存查询
        cache_key = f"{channel}:latest"
        if cache_key in self.cache:
            self.cache_hits += 1
            await asyncio.sleep(0.01)
            cache_time = (time.time() - start_time) * 1000

            self.events.append({
                'time': datetime.now().isoformat(),
                'type': 'CACHE_HIT',
                'msg_id': msg_id,
                'channel': channel,
                'latency_ms': cache_time
            })

            logger.info(f"{Colors.OKGREEN}✓ CACHE_HIT{Colors.ENDC} | {msg_id:15s} | {cache_time:.2f}ms")
            return

        # AI 处理
        base_time = random.expovariate(1.0 / 500)
        proc_time = max(50, min(base_time, 3000)) / 1000

        logger.info(f"{Colors.OKCYAN}⏳ PROCESSING{Colors.ENDC} | {msg_id:15s} | AI will take {proc_time*1000:.0f}ms")
        await asyncio.sleep(proc_time)
        proc_ms = proc_time * 1000
        self.latencies.append(proc_ms)

        # 数据库写入
        db_start = time.time()
        await asyncio.sleep(0.01)
        db_time = (time.time() - db_start) * 1000
        self.db_times.append(db_time)

        # 更新缓存
        self.cache[cache_key] = message

        total_time = (time.time() - start_time) * 1000

        self.events.append({
            'time': datetime.now().isoformat(),
            'type': 'MESSAGE_PROCESSED',
            'msg_id': msg_id,
            'channel': channel,
            'ai_time_ms': proc_ms,
            'db_time_ms': db_time,
            'total_latency_ms': total_time
        })

        logger.info(f"{Colors.OKGREEN}✓ DONE{Colors.ENDC} | {msg_id:15s} | AI:{proc_ms:7.2f}ms | DB:{db_time:5.2f}ms | Total:{total_time:7.2f}ms")

    async def worker(self, worker_id: int):
        """工作线程"""
        logger.info(f"{Colors.HEADER}👷 Worker {worker_id} started{Colors.ENDC}")
        self.worker_stats[worker_id] = {'processed': 0, 'errors': 0}
        msg_count = 0

        while True:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break

            async with self.semaphore:
                self.concurrent_count += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)
                self.total_concurrent_sum += self.concurrent_count
                self.concurrent_samples += 1
                msg_count += 1

                try:
                    logger.debug(f"👷 Worker {worker_id}: concurrent={self.concurrent_count}")
                    await self.message_processor(message)
                    self.worker_stats[worker_id]['processed'] += 1
                except Exception as e:
                    logger.error(f"{Colors.FAIL}❌ ERROR{Colors.ENDC} | {message['message_id']} | {e}")
                    self.worker_stats[worker_id]['errors'] += 1
                finally:
                    self.concurrent_count -= 1

            self.queue.task_done()

        logger.info(f"{Colors.HEADER}👷 Worker {worker_id} finished (processed {msg_count}){Colors.ENDC}")

    def print_status(self):
        """打印当前状态"""
        now = time.time()
        if now - self.last_printed < self.print_interval:
            return

        self.last_printed = now

        queue_size = self.queue.qsize()
        processed_so_far = len(self.latencies)

        print(f"\n{Colors.BOLD}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}📊 实时状态 (已处理: {processed_so_far}/{self.total_messages}){Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}")

        # 队列状态
        print(f"\n{Colors.OKCYAN}【队列状态】{Colors.ENDC}")
        print(f"  队列深度: {queue_size}")
        print(f"  缓存大小: {len(self.cache)}")

        # 并发状态
        print(f"\n{Colors.OKCYAN}【并发状态】{Colors.ENDC}")
        print(f"  当前: {self.concurrent_count}/{self.concurrent_limit}")
        print(f"  峰值: {self.peak_concurrent}")
        avg_con = self.total_concurrent_sum / max(1, self.concurrent_samples)
        print(f"  平均: {avg_con:.2f}")

        # 吞吐量
        if processed_so_far > 0:
            print(f"\n{Colors.OKGREEN}【吞吐量】{Colors.ENDC}")
            print(f"  已处理: {processed_so_far} 条消息")
            print(f"  缓存命中: {self.cache_hits} ({self.cache_hits/max(1,processed_so_far)*100:.1f}%)")
            print(f"  完整处理: {len(self.latencies)} 条")

        # 延迟分布
        if self.latencies:
            sorted_lat = sorted(self.latencies)
            print(f"\n{Colors.WARNING}【延迟分布】{Colors.ENDC}")
            print(f"  平均: {sum(self.latencies)/len(self.latencies):.2f}ms")
            print(f"  最小: {min(self.latencies):.2f}ms")
            print(f"  最大: {max(self.latencies):.2f}ms")
            if len(sorted_lat) >= 20:
                p95_idx = int(len(sorted_lat) * 0.95)
                p99_idx = int(len(sorted_lat) * 0.99)
                print(f"  P95: {sorted_lat[p95_idx]:.2f}ms")
                print(f"  P99: {sorted_lat[p99_idx]:.2f}ms")

        # Worker 状态
        if self.worker_stats:
            print(f"\n{Colors.HEADER}【Worker 状态】{Colors.ENDC}")
            total_proc = sum(w['processed'] for w in self.worker_stats.values())
            total_err = sum(w['errors'] for w in self.worker_stats.values())
            for worker_id, stats in sorted(self.worker_stats.items()):
                print(f"  Worker {worker_id}: ✓{stats['processed']:4d} ❌{stats['errors']:3d}")
            print(f"  总计:          ✓{total_proc:4d} ❌{total_err:3d}")

        print(f"{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

    async def run(self):
        """运行压测"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}🔍 完全可观测压测开始{Colors.ENDC}{Colors.ENDC}")
        print(f"{Colors.BOLD}频道: {self.num_channels}, 消息/频道: {self.msgs_per_channel}, 并发: {self.concurrent_limit}{Colors.ENDC}\n")

        start_time = time.time()

        # 启动 Worker
        num_workers = min(self.concurrent_limit, 10)
        logger.info(f"启动 {num_workers} 个 Worker...")
        workers = [asyncio.create_task(self.worker(i)) for i in range(num_workers)]

        # 生成消息
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

                if msg_id % 50 == 0:
                    await asyncio.sleep(0.01)

                # 定期打印状态
                self.print_status()

        logger.info(f"✅ 已提交 {self.total_messages} 条消息到队列")
        logger.info("等待处理完成...")

        # 等待完成
        await self.queue.join()
        await asyncio.gather(*workers)

        end_time = time.time()
        duration = end_time - start_time

        # 最后打印状态
        self.print_status()

        return self._calculate_metrics(duration)

    def _calculate_metrics(self, duration) -> Metrics:
        if not self.latencies:
            return Metrics()

        sorted_latencies = sorted(self.latencies)

        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data)-1)]

        avg_concurrent = self.total_concurrent_sum / self.concurrent_samples if self.concurrent_samples > 0 else 0

        return Metrics(
            total_sent=self.total_messages,
            total_processed=len(self.latencies) + self.cache_hits,
            total_errors=0,
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
    parser.add_argument("--channels", type=int, default=10)
    parser.add_argument("--messages", type=int, default=50)
    parser.add_argument("--concurrent", type=int, default=5)

    args = parser.parse_args()

    test = ObservableLoadTest(
        num_channels=args.channels,
        msgs_per_channel=args.messages,
        concurrent_limit=args.concurrent
    )

    metrics = await test.run()

    # 最终报告
    print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*80}{Colors.ENDC}{Colors.ENDC}")
    print(f"{Colors.BOLD}📊 最终结果{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.OKGREEN}{'='*80}{Colors.ENDC}{Colors.ENDC}\n")

    print(f"总消息: {metrics.total_sent}")
    print(f"成功: {metrics.total_processed}")
    print(f"吞吐量: {metrics.throughput:.2f} msg/s")
    print(f"平均延迟: {metrics.avg_latency_ms:.2f}ms")
    print(f"P95 延迟: {metrics.p95_latency_ms:.2f}ms")
    print(f"P99 延迟: {metrics.p99_latency_ms:.2f}ms")
    print(f"峰值并发: {metrics.peak_concurrent}")
    print(f"缓存命中率: {metrics.cache_hit_ratio*100:.1f}%")
    print(f"总耗时: {metrics.duration_sec:.2f}s\n")


if __name__ == "__main__":
    asyncio.run(main())

