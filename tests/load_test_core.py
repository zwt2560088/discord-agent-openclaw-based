#!/usr/bin/env python3
"""
Discord Bot 并发压测核心库 - 数据结构 + 指标

定义:
- 压测配置
- 消息级/频道级/系统级指标数据结构
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LoadTestConfig:
    """压测配置"""
    num_channels: int = 50
    messages_per_channel: int = 100
    duration_seconds: int = 300
    concurrent_tasks_limit: int = 20
    connector_limit: int = 100
    connector_limit_per_host: int = 30
    avg_msg_processing_time_ms: int = 500
    msg_arrival_distribution: str = "poisson"  # poisson / uniform
    enable_db_write: bool = True
    enable_memory_cache: bool = True
    report_file: str = "load_test_report.json"


@dataclass
class MessageMetrics:
    """单条消息的性能指标"""
    message_id: str
    channel_id: str
    send_time: float
    queue_start_time: Optional[float] = None
    queue_wait_time_ms: Optional[float] = None
    processing_start_time: Optional[float] = None
    processing_time_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    db_write_time_ms: Optional[float] = None
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

