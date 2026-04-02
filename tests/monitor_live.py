#!/usr/bin/env python3
"""
📡 实时监控仪表板 - 监控压测日志并实时显示指标

用法:
  python tests/monitor_live.py observable_full_log.txt

实时显示:
  - 消息处理速度 (msg/s)
  - 缓存命中率变化
  - 延迟 P95/P99
  - Worker 负载
  - 队列深度
  - 并发数
"""

import re
import sys
import time
from collections import deque
from pathlib import Path


class LiveMonitor:
    def __init__(self, log_file: str, window_size=50):
        self.log_file = Path(log_file)
        self.window_size = window_size
        self.last_pos = 0

        # 指标
        self.message_times = deque(maxlen=window_size)
        self.cache_hits = 0
        self.total_messages = 0
        self.all_latencies = []
        self.worker_counts = {}
        self.errors = 0

        # 时间跟踪
        self.start_time = None
        self.last_display = time.time()
        self.display_interval = 2  # 每 2 秒刷新一次

    def read_new_lines(self):
        """读取新增的日志行"""
        if not self.log_file.exists():
            return []

        with open(self.log_file, 'rb') as f:
            f.seek(self.last_pos)
            lines = f.readlines()
            self.last_pos = f.tell()

        return [line.decode('utf-8', errors='ignore') for line in lines]

    def parse_line(self, line: str):
        """解析日志行"""

        # 缓存命中
        if "CACHE_HIT" in line:
            match = re.search(r'(\d+\.?\d*?)ms', line)
            if match:
                latency = float(match.group(1))
                self.message_times.append(latency)
                self.all_latencies.append(latency)
                self.cache_hits += 1
                self.total_messages += 1

        # 完整处理
        elif "DONE" in line:
            match = re.search(r'Total:(\d+\.?\d*?)ms', line)
            if match:
                latency = float(match.group(1))
                self.message_times.append(latency)
                self.all_latencies.append(latency)
                self.total_messages += 1

        # Worker 统计
        elif "Worker" in line and "started" in line:
            match = re.search(r'Worker (\d+)', line)
            if match:
                worker_id = int(match.group(1))
                self.worker_counts[worker_id] = {'started': True}

        # 错误
        elif "ERROR" in line or "❌" in line:
            self.errors += 1

        # 记录开始时间
        if self.start_time is None and "[INFO]" in line:
            match = re.search(r'(\d{2}):(\d{2}):(\d{2})', line)
            if match:
                self.start_time = time.time()

    def display(self):
        """显示实时仪表板"""
        now = time.time()
        if now - self.last_display < self.display_interval:
            return

        self.last_display = now

        # 清屏
        print("\033[2J\033[H", end='')

        print("=" * 80)
        print("📡 实时监控仪表板")
        print("=" * 80)

        if self.total_messages == 0:
            print("⏳ 等待数据...")
            return

        # 基本统计
        elapsed = now - self.start_time if self.start_time else 0
        throughput = self.total_messages / elapsed if elapsed > 0 else 0

        print(f"\n【处理进度】")
        print(f"  总消息数: {self.total_messages}")
        print(f"  缓存命中: {self.cache_hits}")
        print(f"  完整处理: {self.total_messages - self.cache_hits}")
        print(f"  错误: {self.errors}")
        print(f"  耗时: {elapsed:.2f}s")
        print(f"  吞吐量: {throughput:.2f} msg/s")

        # 缓存率
        cache_ratio = self.cache_hits / self.total_messages * 100 if self.total_messages > 0 else 0
        print(f"\n【缓存命中率】")
        print(f"  {cache_ratio:.1f}% ({self.cache_hits}/{self.total_messages})")
        print(f"  进度条: {'█' * int(cache_ratio/5)}{'░' * (20-int(cache_ratio/5))}")

        # 延迟分布
        if self.all_latencies:
            sorted_lat = sorted(self.all_latencies)
            avg_lat = sum(self.all_latencies) / len(self.all_latencies)
            min_lat = min(self.all_latencies)
            max_lat = max(self.all_latencies)

            p95_idx = int(len(sorted_lat) * 0.95)
            p99_idx = int(len(sorted_lat) * 0.99)
            p95 = sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else 0
            p99 = sorted_lat[p99_idx] if p99_idx < len(sorted_lat) else 0

            print(f"\n【延迟分布 (ms)】")
            print(f"  最小: {min_lat:8.2f}  平均: {avg_lat:8.2f}  最大: {max_lat:8.2f}")
            print(f"  P95:  {p95:8.2f}  P99:  {p99:8.2f}")

        # 最近的消息处理速度
        if self.message_times:
            recent_avg = sum(self.message_times) / len(self.message_times)
            recent_throughput = 1000 / recent_avg if recent_avg > 0 else 0
            print(f"\n【最近 {len(self.message_times)} 条消息】")
            print(f"  平均延迟: {recent_avg:.2f}ms")
            print(f"  吞吐量: {recent_throughput:.2f} msg/s")

        # Worker 状态
        if self.worker_counts:
            print(f"\n【Worker 状态】")
            print(f"  启动: {len(self.worker_counts)} 个")
            for wid in sorted(self.worker_counts.keys())[:10]:  # 最多显示 10 个
                print(f"    Worker {wid}: ✓")

        print("\n" + "=" * 80)
        print("(Ctrl+C 停止监控)")
        sys.stdout.flush()

    def run(self):
        """运行监控"""
        print(f"📡 监控日志: {self.log_file}")
        print("启动监控... (Ctrl+C 停止)\n")

        try:
            while True:
                new_lines = self.read_new_lines()

                for line in new_lines:
                    self.parse_line(line)

                self.display()

                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\n\n👋 监控停止\n")
            print("=" * 80)
            print("📊 最终统计")
            print("=" * 80)

            if self.total_messages > 0:
                print(f"\n总消息: {self.total_messages}")
                print(f"缓存命中: {self.cache_hits} ({self.cache_hits/self.total_messages*100:.1f}%)")
                print(f"完整处理: {self.total_messages - self.cache_hits}")
                print(f"错误: {self.errors}")

                if self.all_latencies:
                    sorted_lat = sorted(self.all_latencies)
                    print(f"\n延迟统计 (ms):")
                    print(f"  平均: {sum(self.all_latencies)/len(self.all_latencies):.2f}")
                    print(f"  最小: {min(self.all_latencies):.2f}")
                    print(f"  最大: {max(self.all_latencies):.2f}")
                    print(f"  P95: {sorted_lat[int(len(sorted_lat)*0.95)]:.2f}")
                    print(f"  P99: {sorted_lat[int(len(sorted_lat)*0.99)]:.2f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python monitor_live.py <log_file>")
        print("\n示例:")
        print("  python tests/monitor_live.py observable_full_log.txt")
        sys.exit(1)

    log_file = sys.argv[1]
    monitor = LiveMonitor(log_file, window_size=100)
    monitor.run()

