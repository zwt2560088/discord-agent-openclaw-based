#!/usr/bin/env python3
"""
System Monitor — 指标收集 + 持久化到 SQLite + Prometheus 暴露
    
功能:
1. 定时收集 CPU/内存/磁盘等系统指标
2. 跟踪业务指标（消息数、LLM 调用、订单数）
3. 持久化到 SQLite（metrics 表）供 Web Dashboard 读取
4. 暴露 /metrics 端点（Prometheus 格式）
"""

import logging
import os
import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger("SystemMonitor")
    
# ==================== 数据库路径 ====================
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "bot_context.db")
    
        
class MetricsCollector:
    """指标收集器 — 收集系统 + 业务指标"""
        
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.start_time = time.time()
        self._init_db()
        
        # 业务计数器
        self.messages_processed = 0
        self.commands_processed = 0
        self.errors_count = 0
        self.llm_calls = 0
        self.llm_total_latency = 0.0  # 累计延迟（秒）
        self.orders_created = 0
        
        # 内存中的最近指标（用于 Prometheus 端点实时读取）
        self._recent_metrics: deque = deque(maxlen=100)
        
    def _init_db(self):
        """创建 metrics 表"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    process_cpu REAL,
                    process_memory_mb REAL,
                    system_cpu REAL,
                    system_memory_mb REAL,
                    system_disk_percent REAL,
                    messages_processed INTEGER DEFAULT 0,
                    errors_count INTEGER DEFAULT 0,
                    llm_calls INTEGER DEFAULT 0,
                    llm_avg_latency_ms REAL DEFAULT 0,
                    orders_created INTEGER DEFAULT 0
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ Failed to init metrics DB: {e}")
        
    def collect(self) -> Dict:
        """收集一次系统指标并持久化"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            process_cpu = process.cpu_percent(interval=0.1)
            process_memory = process.memory_info().rss / 1024 / 1024  # MB
            system_cpu = psutil.cpu_percent(interval=0.1)
            system_memory = psutil.virtual_memory()
            system_memory_mb = system_memory.used / 1024 / 1024
            system_disk = psutil.disk_usage('/').percent
        except ImportError:
            process_cpu = 0
            process_memory = 0
            system_cpu = 0
            system_memory_mb = 0
            system_disk = 0
        
        avg_llm_latency = (self.llm_total_latency / self.llm_calls * 1000) if self.llm_calls > 0 else 0
        
        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "process_cpu": round(process_cpu, 2),
            "process_memory_mb": round(process_memory, 2),
            "system_cpu": round(system_cpu, 2),
            "system_memory_mb": round(system_memory_mb, 2),
            "system_disk_percent": round(system_disk, 2),
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "llm_calls": self.llm_calls,
            "llm_avg_latency_ms": round(avg_llm_latency, 2),
            "orders_created": self.orders_created,
        }
        
        self._recent_metrics.append(metrics)
        self._save_to_db(metrics)
        return metrics
    
    def _save_to_db(self, metrics: Dict):
        """写入 SQLite"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO metrics (timestamp, process_cpu, process_memory_mb, system_cpu,
                    system_memory_mb, system_disk_percent, messages_processed, errors_count,
                    llm_calls, llm_avg_latency_ms, orders_created)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics["timestamp"], metrics["process_cpu"], metrics["process_memory_mb"],
                metrics["system_cpu"], metrics["system_memory_mb"], metrics["system_disk_percent"],
                metrics["messages_processed"], metrics["errors_count"],
                metrics["llm_calls"], metrics["llm_avg_latency_ms"], metrics["orders_created"]
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to save metrics: {e}")
        
    def get_recent(self, limit: int = 100) -> List[Dict]:
        """从数据库读取最近的指标"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                SELECT timestamp, process_cpu, process_memory_mb, system_cpu, system_memory_mb,
                       system_disk_percent, messages_processed, errors_count,
                       llm_calls, llm_avg_latency_ms, orders_created
                FROM metrics ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = c.fetchall()
            conn.close()
            return [self._row_to_dict(r) for r in reversed(rows)]
        except Exception as e:
            logger.warning(f"Failed to read metrics: {e}")
            return []
        
    def cleanup_old_metrics(self, days: int = 7):
        """清理旧指标（保留最近 N 天）"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            c.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
            deleted = c.rowcount
            conn.commit()
            conn.close()
            if deleted > 0:
                logger.info(f"🧹 Cleaned up {deleted} old metrics records")
        except Exception as e:
            logger.debug(f"Metrics cleanup failed: {e}")
        
    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "timestamp": row[0],
            "process_cpu": row[1],
            "process_memory_mb": row[2],
            "system_cpu": row[3],
            "system_memory_mb": row[4],
            "system_disk_percent": row[5],
            "messages_processed": row[6],
            "errors_count": row[7],
            "llm_calls": row[8],
            "llm_avg_latency_ms": row[9],
            "orders_created": row[10],
        }
        
    # ==================== 业务埋点方法 ====================
        
    def inc_message(self):
        self.messages_processed += 1
        
    def inc_command(self):
        self.commands_processed += 1
        
    def inc_error(self):
        self.errors_count += 1
        
    def record_llm_call(self, latency_seconds: float):
        self.llm_calls += 1
        self.llm_total_latency += latency_seconds
    
    def inc_order(self):
        self.orders_created += 1
        
    def inc_cache_hit(self):
        self.cache_hits = getattr(self, 'cache_hits', 0) + 1

    def inc_cache_miss(self):
        self.cache_misses = getattr(self, 'cache_misses', 0) + 1

    # ==================== Prometheus 格式输出 ====================
        
    def to_prometheus(self) -> str:
        """生成 Prometheus 格式的文本指标"""
        latest = self._recent_metrics[-1] if self._recent_metrics else {
            "process_cpu": 0, "process_memory_mb": 0, "system_cpu": 0,
            "system_memory_mb": 0, "system_disk_percent": 0,
        }
        lines = [
            "# HELP discord_bot_process_cpu_percent Process CPU usage percent",
            "# TYPE discord_bot_process_cpu_percent gauge",
            f"discord_bot_process_cpu_percent {latest['process_cpu']}",
            "",
            "# HELP discord_bot_process_memory_mb Process memory usage in MB",
            "# TYPE discord_bot_process_memory_mb gauge",
            f"discord_bot_process_memory_mb {latest['process_memory_mb']}",
            "",
            "# HELP discord_bot_system_cpu_percent System CPU usage percent",
            "# TYPE discord_bot_system_cpu_percent gauge",
            f"discord_bot_system_cpu_percent {latest['system_cpu']}",
            "",
            "# HELP discord_bot_system_memory_mb System memory usage in MB",
            "# TYPE discord_bot_system_memory_mb gauge",
            f"discord_bot_system_memory_mb {latest['system_memory_mb']}",
            "",
            "# HELP discord_bot_system_disk_percent System disk usage percent",
            "# TYPE discord_bot_system_disk_percent gauge",
            f"discord_bot_system_disk_percent {latest['system_disk_percent']}",
            "",
            "# HELP discord_bot_messages_total Total messages processed",
            "# TYPE discord_bot_messages_total counter",
            f"discord_bot_messages_total {self.messages_processed}",
            "",
            "# HELP discord_bot_commands_total Total commands processed",
            "# TYPE discord_bot_commands_total counter",
            f"discord_bot_commands_total {self.commands_processed}",
            "",
            "# HELP discord_bot_errors_total Total errors",
            "# TYPE discord_bot_errors_total counter",
            f"discord_bot_errors_total {self.errors_count}",
            "",
            "# HELP discord_bot_llm_calls_total Total LLM API calls",
            "# TYPE discord_bot_llm_calls_total counter",
            f"discord_bot_llm_calls_total {self.llm_calls}",
            "",
            "# HELP discord_bot_llm_avg_latency_ms Average LLM call latency in ms",
            "# TYPE discord_bot_llm_avg_latency_ms gauge",
            f"discord_bot_llm_avg_latency_ms {(self.llm_total_latency / self.llm_calls * 1000) if self.llm_calls > 0 else 0}",
            "",
            "# HELP discord_bot_orders_created_total Total orders created",
            "# TYPE discord_bot_orders_created_total counter",
            f"discord_bot_orders_created_total {self.orders_created}",
            "",
            "# HELP discord_bot_cache_hits_total Total cache hits",
            "# TYPE discord_bot_cache_hits_total counter",
            f"discord_bot_cache_hits_total {getattr(self, 'cache_hits', 0)}",
            "",
            "# HELP discord_bot_cache_misses_total Total cache misses",
            "# TYPE discord_bot_cache_misses_total counter",
            f"discord_bot_cache_misses_total {getattr(self, 'cache_misses', 0)}",
            "",
            "# HELP discord_bot_uptime_seconds Bot uptime in seconds",
            "# TYPE discord_bot_uptime_seconds gauge",
            f"discord_bot_uptime_seconds {int(time.time() - self.start_time)}",
        ]
        return "\n".join(lines)
        
        
# ==================== 全局单例 ====================
_metrics_collector: Optional[MetricsCollector] = None
        
        
def get_metrics_collector() -> MetricsCollector:
    """获取全局 MetricsCollector 单例"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
