#!/usr/bin/env python3
"""
模拟 Discord 消息队列 + 信号量限制
"""

import asyncio
import time
from typing import Callable, Dict

from .load_test_core import MessageMetrics


class SimulatedQueue:
    """
    模拟 Discord 消息队列 + asyncio.Semaphore

    关键点:
    1. 消息进入队列（记录队列时间）
    2. 受信号量限制（最多 N 个并发任务）
    3. 工作线程从队列取消息处理
    """

    def __init__(self, max_concurrent: int):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue = asyncio.Queue()
        self.concurrent_count = 0
        self.peak_concurrent = 0
        self.total_concurrent_sum = 0
        self.concurrent_samples = 0

    async def submit(self, message: Dict) -> MessageMetrics:
        """
        提交消息到队列

        流程:
        1. 创建消息指标对象
        2. 记录进入队列时间
        3. 将消息放入异步队列
        """
        metrics = MessageMetrics(
            message_id=message["message_id"],
            channel_id=message["channel_id"],
            send_time=time.time()
        )

        metrics.queue_start_time = time.time()
        await self.queue.put((message, metrics))

        return metrics

    async def process_worker(self, worker_id: int, processor: Callable):
        """
        工作线程：从队列取消息，受信号量限制

        流程:
        1. 从队列取消息（FIFO）
        2. 获取信号量（如果已满，等待直到有可用 slot）
        3. 在信号量保护下执行处理
        4. 释放信号量，处理下一条
        """
        while True:
            try:
                # 超时后退出（用于压测完成检测）
                message, metrics = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                break

            # 计算队列等待时间
            metrics.queue_wait_time_ms = (time.time() - metrics.queue_start_time) * 1000

            # 获取信号量（核心限流点）
            async with self.semaphore:
                # 记录并发数
                self.concurrent_count += 1
                self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)
                self.total_concurrent_sum += self.concurrent_count
                self.concurrent_samples += 1

                try:
                    # 处理消息
                    metrics.processing_start_time = time.time()
                    await processor(message, metrics)
                    metrics.processing_time_ms = (time.time() - metrics.processing_start_time) * 1000
                    metrics.total_latency_ms = (time.time() - metrics.send_time) * 1000

                except Exception as e:
                    metrics.error = str(e)

                finally:
                    self.concurrent_count -= 1

            # 标记任务完成
            self.queue.task_done()

    @property
    def avg_concurrent(self) -> float:
        """平均并发任务数"""
        if self.concurrent_samples == 0:
            return 0.0
        return self.total_concurrent_sum / self.concurrent_samples

