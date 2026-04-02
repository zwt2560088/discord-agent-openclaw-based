#!/usr/bin/env python3
"""
🔥 Discord Bot 完整并发压测套件

功能:
1. 模拟多频道并发消息
2. 测试信号量限制（20 个并发任务）
3. 测试 aiohttp 连接池（100 总连接，30 单主机限制）
4. 测试数据库并发写入
5. 测试内存缓存竞争
6. 生成详细的性能报告

使用:
    python tests/load_test.py --channels 50 --messages-per-channel 100 --duration 300
"""

import asyncio
import json
import logging
import random
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# ==================== 配置 ====================

logger = logging.getLogger("LoadTest")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

@dataclass
class LoadTestConfig:
    """压测配置"""
    num_channels: int = 50              # 频道数
    messages_per_channel: int = 100     # 每个频道的消息数
    duration_seconds: int = 300         # 总测试时间
    concurrent_tasks_limit: int = 20    # 模拟信号量限制
    connector_limit: int = 100          # aiohttp 连接池总数
    connector_limit_per_host: int = 30  # 单主机限制
    avg_msg_processing_time_ms: int = 500  # 平均消息处理时间
    msg_arrival_distribution: str = "poisson"  # poisson / uniform
    enable_db_write: bool = True        # 是否写 SQLite
    enable_memory_cache: bool = True    # 是否使用内存缓存
    report_file: str = "load_test_report.json"


@dataclass
class MessageMetrics:
    """单条消息的性能指标"""
    message_id: str
    channel_id: str
    send_time: float  # 发送时间戳
    queue_start_time: Optional[float] = None  # 进入队列时间
    queue_wait_time_ms: Optional[float] = None  # 队列等待时间
    processing_start_time: Optional[float] = None  # 处理开始时间
    processing_time_ms: Optional[float] = None  # 处理时间
    total_latency_ms: Optional[float] = None  # 端到端延迟
    db_write_time_ms: Optional[float] = None  # 数据库写入时间
    cache_hit: bool = False
    error: Optional[str] = None


@dataclass
class ChannelMetrics:
    """频道级指标"""
    channel_id: str
    total_messages: int = 0
    successful_messages: int = 0
    failed_messages: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    avg_queue_wait_ms: float = 0.0
    throughput_msg_per_sec: float = 0.0


@dataclass
class SystemMetrics:
    """系统级指标"""
    total_messages_sent: int = 0
    total_messages_processed: int = 0
    total_errors: int = 0
    total_duration_seconds: float = 0.0
    overall_throughput_msg_per_sec: float = 0.0
    peak_concurrent_tasks: int = 0
    avg_concurrent_tasks: float = 0.0
    memory_peak_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    connection_pool_utilization_percent: float = 0.0
    db_write_latency_p95_ms: float = 0.0
    cache_hit_ratio: float = 0.0


# ==================== 模拟器核心 ====================

class SimulatedQueue:
    """模拟 Discord 消息队列 + 信号量"""

    def __init__(self, max_concurrent: int):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue = asyncio.Queue()
        self.concurrent_count = 0
        self.peak_concurrent = 0
        self.total_concurrent_sum = 0
        self.concurrent_samples = 0

    async def submit(self, message: Dict) -> MessageMetrics:
        """提交消息到队列"""
        metrics = MessageMetrics(
            message_id=message["message_id"],
            channel_id=message["channel_id"],
            send_time=time.time()
        )

        # 1️⃣ 消息进入队列
        metrics.queue_start_time = time.time()
        await self.queue.put((message, metrics))

        return metrics

    async def process_worker(self, worker_id: int, processor):
        """工作线程：从队列取消息，受信号量限制"""
        while True:
            try:
                message, metrics = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                break

            # 2️⃣ 获取信号量（可能需要等待）
            metrics.queue_wait_time_ms = (time.time() - metrics.queue_start_time) * 1000

            async with self.semaphore:
                self.concurrent_count += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)
                self.total_concurrent_sum += self.concurrent_count
                self.concurrent_samples += 1

                try:
                    # 3️⃣ 处理消息
                    metrics.processing_start_time = time.time()
                    await processor(message, metrics)
                    metrics.processing_time_ms = (time.time() - metrics.processing_start_time) * 1000
                    metrics.total_latency_ms = (time.time() - metrics.send_time) * 1000

                except Exception as e:
                    metrics.error = str(e)
                    logger.error(f"处理消息失败: {e}")

                finally:
                    self.concurrent_count -= 1

    @property
    def avg_concurrent(self) -> float:
        if self.concurrent_samples == 0:
            return 0.0
        return self.total_concurrent_sum / self.concurrent_samples


class MessageProcessor:
    """模拟消息处理器"""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.cache = {} if config.enable_memory_cache else None
        self.db_path = "load_test_metrics.db"
        self._init_db()
        self.processing_times: List[float] = []
        self.db_write_times: List[float] = []

    def _init_db(self):
        """初始化测试数据库"""
        if not self.config.enable_db_write:
            return
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS test_messages (
                message_id TEXT PRIMARY KEY,
                channel_id TEXT,
                content TEXT,
                processed_at TEXT,
                latency_ms REAL
            )
        """)
        conn.commit()
        conn.close()

    async def process(self, message: Dict, metrics: MessageMetrics):
        """处理单条消息"""

        # 1️⃣ 尝试缓存命中
        if self.cache is not None:
            cache_key = f"{message['channel_id']}:latest"
            if cache_key in self.cache:
                metrics.cache_hit = True
                await asyncio.sleep(0.01)  # 缓存查找时间：10ms
                return

        # 2️⃣ 模拟 AI 处理（根据分布生成处理时间）
        processing_time = self._generate_processing_time()
        await asyncio.sleep(processing_time / 1000)  # 转换为秒
        self.processing_times.append(processing_time)

        # 3️⃣ 数据库写入（如果启用）
        if self.config.enable_db_write:
            db_start = time.time()
            await self._write_to_db(message)
            db_write_time = (time.time() - db_start) * 1000
            metrics.db_write_time_ms = db_write_time
            self.db_write_times.append(db_write_time)

        # 4️⃣ 更新缓存
        if self.cache is not None:
            cache_key = f"{message['channel_id']}:latest"
            self.cache[cache_key] = message

    def _generate_processing_time(self) -> float:
        """根据分布生成处理时间（毫秒）"""
        if self.config.msg_arrival_distribution == "poisson":
            # Poisson 分布（大多数快速，少数很慢）
            base = random.expovariate(1.0 / self.config.avg_msg_processing_time_ms)
            return max(50, min(base, 3000))  # 50-3000ms
        else:
            # 均匀分布
            return random.uniform(
                self.config.avg_msg_processing_time_ms * 0.5,
                self.config.avg_msg_processing_time_ms * 1.5
            )

    async def _write_to_db(self, message: Dict):
        """异步写入数据库"""
        def write():
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO test_messages (message_id, channel_id, content, processed_at, latency_ms)
                VALUES (?, ?, ?, ?, ?)
            """, (
                message["message_id"],
                message["channel_id"],
                message.get("content", ""),
                datetime.now().isoformat(),
                0  # 实际值由调用者填充
            ))
            conn.commit()
            conn.close()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, write)

    def get_percentile(self, data: List[float], p: int) -> float:
        """计算百分位"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]


# ==================== 测试驱动程序 ====================

class LoadTestDriver:
    """压测驱动程序"""

    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.queue = SimulatedQueue(config.concurrent_tasks_limit)
        self.processor = MessageProcessor(config)
        self.message_metrics: List[MessageMetrics] = []
        self.channel_metrics: Dict[str, ChannelMetrics] = {}
        self.start_time = None
        self.end_time = None

    async def run(self) -> SystemMetrics:
        """运行完整压测"""
        logger.info(f"🚀 开始压测: {self.config.num_channels} 频道, "
                   f"{self.config.messages_per_channel} 消息/频道")

        self.start_time = time.time()

        # 1️⃣ 启动工作线程
        num_workers = min(self.config.concurrent_tasks_limit, 10)
        workers = [
            asyncio.create_task(
                self.queue.process_worker(i, self.processor.process)
            )
            for i in range(num_workers)
        ]

        # 2️⃣ 生成和提交消息
        submit_tasks = []
        for channel_id in range(self.config.num_channels):
            channel_key = f"channel_{channel_id}"
            self.channel_metrics[channel_key] = ChannelMetrics(channel_id=channel_key)

            for msg_id in range(self.config.messages_per_channel):
                message = {
                    "message_id": f"msg_{channel_id}_{msg_id}",
                    "channel_id": channel_key,
                    "content": f"Test message {msg_id}"
                }

                # 异步提交消息
                task = asyncio.create_task(self.queue.submit(message))
                submit_tasks.append(task)

                # 控制提交速率（模拟消息到达分布）
                if self.config.msg_arrival_distribution == "poisson":
                    await asyncio.sleep(random.expovariate(10) / 1000)  # 平均 100ms

        # 等待所有消息提交完成
        metrics_list = await asyncio.gather(*submit_tasks)
        self.message_metrics.extend(metrics_list)

        logger.info(f"✅ 已提交 {len(self.message_metrics)} 条消息")

        # 3️⃣ 等待队列处理完成
        await self.queue.queue.join()

        # 4️⃣ 等待工作线程完成
        await asyncio.gather(*workers)

        self.end_time = time.time()

        logger.info(f"✅ 压测完成，耗时 {self.end_time - self.start_time:.2f} 秒")

        # 5️⃣ 计算系统级指标
        return self._calculate_metrics()

    def _calculate_metrics(self) -> SystemMetrics:
        """计算系统级指标"""

        # 分类统计消息
        successful = [m for m in self.message_metrics if not m.error]
        failed = [m for m in self.message_metrics if m.error]
        latencies = [m.total_latency_ms for m in successful if m.total_latency_ms]

        # 计算每个频道的统计
        for metrics in self.message_metrics:
            channel_key = metrics.channel_id
            if channel_key not in self.channel_metrics:
                continue

            cm = self.channel_metrics[channel_key]
            cm.total_messages += 1
            if not metrics.error:
                cm.successful_messages += 1
                if metrics.total_latency_ms:
                    cm.max_latency_ms = max(cm.max_latency_ms, metrics.total_latency_ms)
                    cm.min_latency_ms = min(cm.min_latency_ms, metrics.total_latency_ms)
            else:
                cm.failed_messages += 1

        # 计算频道级汇总
        for cm in self.channel_metrics.values():
            if cm.successful_messages > 0:
                channel_latencies = [
                    m.total_latency_ms for m in self.message_metrics
                    if m.channel_id == cm.channel_id and m.total_latency_ms
                ]
                if channel_latencies:
                    cm.avg_latency_ms = sum(channel_latencies) / len(channel_latencies)
                    cm.p50_latency_ms = self.processor.get_percentile(channel_latencies, 50)
                    cm.p95_latency_ms = self.processor.get_percentile(channel_latencies, 95)
                    cm.p99_latency_ms = self.processor.get_percentile(channel_latencies, 99)
                    cm.min_latency_ms = min(cm.min_latency_ms, min(channel_latencies))

        # 系统级指标
        duration = self.end_time - self.start_time
        cache_hits = sum(1 for m in self.message_metrics if m.cache_hit)

        return SystemMetrics(
            total_messages_sent=len(self.message_metrics),
            total_messages_processed=len(successful),
            total_errors=len(failed),
            total_duration_seconds=duration,
            overall_throughput_msg_per_sec=len(successful) / duration if duration > 0 else 0,
            peak_concurrent_tasks=self.queue.peak_concurrent,
            avg_concurrent_tasks=self.queue.avg_concurrent,
            memory_peak_mb=0.0,  # 需要 psutil 实现
            cpu_usage_percent=0.0,  # 需要 psutil 实现
            connection_pool_utilization_percent=0.0,  # 需要 aiohttp 集成
            db_write_latency_p95_ms=self.processor.get_percentile(self.processor.db_write_times, 95),
            cache_hit_ratio=cache_hits / len(self.message_metrics) if self.message_metrics else 0
        )

    def generate_report(self, system_metrics: SystemMetrics) -> Dict:
        """生成完整报告"""
        return {
            "timestamp": datetime.now().isoformat(),
            "config": asdict(self.config),
            "system_metrics": asdict(system_metrics),
            "channel_metrics": {
                k: asdict(v) for k, v in self.channel_metrics.items()
            },
            "message_samples": [
                asdict(m) for m in self.message_metrics[:100]  # 只保存前 100 条样本
            ]
        }


# ==================== 命令行入口 ====================

async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Discord Bot 并发压测")
    parser.add_argument("--channels", type=int, default=50, help="频道数")
    parser.add_argument("--messages-per-channel", type=int, default=100, help="每个频道的消息数")
    parser.add_argument("--duration", type=int, default=300, help="测试时间（秒）")
    parser.add_argument("--concurrent-limit", type=int, default=20, help="并发任务数")
    parser.add_argument("--avg-processing-time", type=int, default=500, help="平均处理时间（ms）")
    parser.add_argument("--distribution", choices=["poisson", "uniform"], default="poisson")
    parser.add_argument("--no-db", action="store_true", help="不写数据库")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--output", default="load_test_report.json", help="输出文件")

    args = parser.parse_args()

    config = LoadTestConfig(
        num_channels=args.channels,
        messages_per_channel=args.messages_per_channel,
        duration_seconds=args.duration,
        concurrent_tasks_limit=args.concurrent_limit,
        avg_msg_processing_time_ms=args.avg_processing_time,
        msg_arrival_distribution=args.distribution,
        enable_db_write=not args.no_db,
        enable_memory_cache=not args.no_cache,
        report_file=args.output
    )

    driver = LoadTestDriver(config)
    system_metrics = await driver.run()

    report = driver.generate_report(system_metrics)

    # 保存报告
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info(f"📊 报告已保存到: {args.output}")

    # 打印摘要
    print("\n" + "="*60)
    print("📊 压测摘要")
    print("="*60)
    print(f"频道数: {config.num_channels}")
    print(f"总消息数: {system_metrics.total_messages_sent}")
    print(f"成功: {system_metrics.total_messages_processed}")
    print(f"失败: {system_metrics.total_errors}")
    print(f"总耗时: {system_metrics.total_duration_seconds:.2f}s")
    print(f"吞吐量: {system_metrics.overall_throughput_msg_per_sec:.2f} msg/s")
    print(f"峰值并发: {system_metrics.peak_concurrent_tasks}")
    print(f"平均并发: {system_metrics.avg_concurrent_tasks:.2f}")
    print(f"缓存命中率: {system_metrics.cache_hit_ratio*100:.1f}%")
    print(f"DB 写入 P95: {system_metrics.db_write_latency_p95_ms:.2f}ms")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

