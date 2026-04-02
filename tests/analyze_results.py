#!/usr/bin/env python3
"""
📊 压测结果分析工具

快速分析历史压测结果，生成对比和趋势图
"""

import json
import sys
from pathlib import Path
from typing import List


class ResultAnalyzer:
    """压测结果分析器"""

    def __init__(self, result_file: Path):
        self.result_file = result_file
        self.data = json.loads(result_file.read_text())

    def print_summary(self):
        """打印摘要"""
        print("\n" + "="*70)
        print(f"📊 压测结果摘要: {self.result_file.name}")
        print("="*70)

        config = self.data.get("config", {})
        metrics = self.data.get("metrics", {})

        print(f"\n⚙️  配置:")
        print(f"   频道数: {config.get('channels', 'N/A')}")
        print(f"   消息/频道: {config.get('messages_per_channel', 'N/A')}")
        print(f"   并发限制: {config.get('concurrent_limit', 'N/A')}")

        print(f"\n📈 性能指标:")
        print(f"   总消息: {metrics.get('total_sent', 0)}")
        print(f"   成功: {metrics.get('total_processed', 0)}")
        print(f"   失败: {metrics.get('total_errors', 0)}")
        print(f"   成功率: {(metrics.get('total_processed', 0) / max(1, metrics.get('total_sent', 1)) * 100):.1f}%")

        print(f"\n⏱️  延迟统计 (毫秒):")
        print(f"   平均: {metrics.get('avg_latency_ms', 0):.2f}ms")
        print(f"   P50 (中位数): {metrics.get('p50_latency_ms', 0):.2f}ms")
        print(f"   P95 (95分位): {metrics.get('p95_latency_ms', 0):.2f}ms")
        print(f"   P99 (99分位): {metrics.get('p99_latency_ms', 0):.2f}ms")

        print(f"\n🚀 吞吐量:")
        print(f"   {metrics.get('throughput', 0):.2f} msg/s")
        print(f"   {metrics.get('duration_sec', 0):.2f}s 耗时")

        print(f"\n👥 并发情况:")
        print(f"   峰值: {metrics.get('peak_concurrent', 0)}")
        print(f"   平均: {metrics.get('avg_concurrent_tasks', 0):.1f}")

        print(f"\n💾 缓存/存储:")
        print(f"   缓存命中率: {metrics.get('cache_hit_ratio', 0)*100:.1f}%")
        print(f"   DB P95: {metrics.get('db_p95_ms', 0):.2f}ms")

        print("="*70 + "\n")

    def compare_with_baseline(self, baseline_file: Path):
        """与基准线对比"""
        baseline_data = json.loads(baseline_file.read_text())

        print("\n" + "="*70)
        print(f"📊 对比分析: 当前 vs 基准")
        print("="*70)

        metrics = self.data.get("metrics", {})
        baseline = baseline_data.get("metrics", {})

        comparisons = [
            ("吞吐量 (msg/s)", "throughput", lambda x: f"{x:.2f}"),
            ("平均延迟 (ms)", "avg_latency_ms", lambda x: f"{x:.2f}"),
            ("P95 延迟 (ms)", "p95_latency_ms", lambda x: f"{x:.2f}"),
            ("缓存命中率 (%)", "cache_hit_ratio", lambda x: f"{x*100:.1f}"),
        ]

        for name, key, formatter in comparisons:
            current = metrics.get(key, 0)
            base = baseline.get(key, 0)

            if base == 0:
                change = "N/A"
                status = "⚠️"
            else:
                pct_change = ((current - base) / abs(base)) * 100
                change = f"{pct_change:+.1f}%"
                status = "✅" if pct_change <= 10 else "⚠️"

            print(f"{status} {name:20s}: {formatter(current):>10s} (基准: {formatter(base):>10s}) [{change}]")

        print("="*70 + "\n")

    def generate_ascii_chart(self, title: str, values: List[float], max_width: int = 50):
        """生成 ASCII 柱状图"""
        if not values:
            return

        max_val = max(values)
        print(f"\n{title}")
        print("-" * (max_width + 20))

        for i, v in enumerate(values):
            bar_width = int((v / max_val) * max_width) if max_val > 0 else 0
            bar = "█" * bar_width
            print(f"{i:3d}: {bar:50s} {v:.2f}")

    def analyze_scenarios(self):
        """分析多场景结果"""
        if "stages" not in self.data or "stress_scenarios" not in self.data["stages"]:
            print("⚠️  未找到多场景数据")
            return

        scenarios = self.data["stages"]["stress_scenarios"]

        print("\n" + "="*70)
        print("💥 多场景分析")
        print("="*70)

        # 吞吐量对比
        throughputs = []
        scenario_names = []
        for name, result in scenarios.items():
            metrics = result.get("metrics", {})
            throughputs.append(metrics.get("throughput", 0))
            scenario_names.append(name)

        print("\n🚀 吞吐量对比 (msg/s)")
        print("-" * 50)
        for name, tput in zip(scenario_names, throughputs):
            bar_width = int(tput / 2)  # 缩放以适应宽度
            bar = "▓" * bar_width
            print(f"{name:10s}: {bar:30s} {tput:.1f}")

        # 延迟对比
        print("\n⏱️  P95 延迟对比 (ms)")
        print("-" * 50)
        for name, result in scenarios.items():
            metrics = result.get("metrics", {})
            p95 = metrics.get("p95_latency_ms", 0)
            bar_width = int(p95 / 20)  # 缩放
            bar = "▒" * min(bar_width, 30)
            print(f"{name:10s}: {bar:30s} {p95:.1f}")

        print("="*70 + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="压测结果分析工具")
    parser.add_argument("result_file", type=Path, help="压测结果 JSON 文件")
    parser.add_argument("--baseline", type=Path, help="基准线文件用于对比")
    parser.add_argument("--scenarios", action="store_true", help="分析多场景数据")

    args = parser.parse_args()

    if not args.result_file.exists():
        print(f"❌ 文件不存在: {args.result_file}")
        sys.exit(1)

    analyzer = ResultAnalyzer(args.result_file)

    # 打印摘要
    analyzer.print_summary()

    # 与基准线对比
    if args.baseline:
        if args.baseline.exists():
            analyzer.compare_with_baseline(args.baseline)
        else:
            print(f"⚠️  基准线文件不存在: {args.baseline}")

    # 分析多场景
    if args.scenarios:
        analyzer.analyze_scenarios()


if __name__ == "__main__":
    main()

