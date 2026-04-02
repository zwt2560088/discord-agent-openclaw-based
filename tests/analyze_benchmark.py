#!/usr/bin/env python3
"""
📊 BenchMark 分析工具 - 生成对比图表和分析报告
"""

import json
import sys
from pathlib import Path
from typing import List, Dict


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def load_results(filename: str) -> Dict:
    """加载 benchmark 结果"""
    with open(filename, 'r') as f:
        return json.load(f)


def print_header(title: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.HEADER}【{title}】{Colors.ENDC}{Colors.ENDC}")
    print("=" * 120)


def plot_simple_bar(title: str, data: Dict[str, float], unit: str = ""):
    """简单柱状图"""
    print(f"\n{Colors.BOLD}{title}{Colors.ENDC}")

    max_val = max(data.values()) if data else 1
    max_width = 40

    for label, value in sorted(data.items(), key=lambda x: x[1], reverse=True):
        width = int(value / max_val * max_width)
        bar = "█" * width + "░" * (max_width - width)
        print(f"  {label:20s} | {bar} | {value:8.2f} {unit}")


def print_concurrent_analysis(results: List[Dict]):
    """分析并发数的影响"""
    print_header("并发数对吞吐的影响")

    data = {}
    for r in results:
        if r['channels'] == 10 and r['messages_per_channel'] == 100 and 'cache' in r['name']:
            concurrent = r['concurrent_limit']
            throughput = r['throughput_msg_per_sec']
            data[f"并发{concurrent}"] = throughput

    plot_simple_bar("吞吐量 (msg/s)", data, "msg/s")

    # 分析
    if len(data) >= 2:
        vals = list(data.values())
        ratio = vals[-1] / vals[0]
        print(f"\n  {Colors.OKGREEN}✓ 最高/最低比值: {ratio:.2f}x{Colors.ENDC}")


def print_message_count_analysis(results: List[Dict]):
    """分析消息数的影响"""
    print_header("消息数对吞吐的影响")

    data = {}
    for r in results:
        if r['channels'] == 10 and r['concurrent_limit'] == 10 and 'cache' in r['name']:
            total = r['total_messages']
            throughput = r['throughput_msg_per_sec']
            data[f"消息{total}"] = throughput

    plot_simple_bar("吞吐量 (msg/s)", data, "msg/s")


def print_cache_effect_analysis(results: List[Dict]):
    """分析缓存的效果"""
    print_header("缓存对性能的影响")

    with_cache = None
    without_cache = None

    for r in results:
        if r['channels'] == 5 and r['messages_per_channel'] == 100 and r['concurrent_limit'] == 10:
            if 'cache' in r['name'] and 'nocache' not in r['name']:
                with_cache = r
            elif 'nocache' in r['name']:
                without_cache = r

    if with_cache and without_cache:
        print(f"\n  有缓存:   {with_cache['throughput_msg_per_sec']:8.2f} msg/s (命中率: {with_cache['cache_hit_ratio']*100:5.1f}%)")
        print(f"  无缓存:   {without_cache['throughput_msg_per_sec']:8.2f} msg/s")

        speedup = with_cache['throughput_msg_per_sec'] / without_cache['throughput_msg_per_sec']
        latency_reduction = without_cache['avg_latency_ms'] / with_cache['avg_latency_ms']

        print(f"\n  {Colors.OKGREEN}✓ 吞吐加速: {speedup:.2f}x{Colors.ENDC}")
        print(f"  {Colors.OKGREEN}✓ 延迟降低: {latency_reduction:.2f}x{Colors.ENDC}")


def print_latency_analysis(results: List[Dict]):
    """分析延迟分布"""
    print_header("延迟分布 (不同并发数)")

    data = {}
    for r in results:
        if r['channels'] == 10 and r['messages_per_channel'] == 100 and 'cache' in r['name']:
            concurrent = r['concurrent_limit']
            p95 = r['p95_latency_ms']
            data[f"并发{concurrent}"] = p95

    plot_simple_bar("P95 延迟 (ms)", data, "ms")


def print_throughput_comparison(results: List[Dict]):
    """吞吐量对比"""
    print_header("吞吐量排名 (Top 10)")

    sorted_results = sorted(results, key=lambda r: r['throughput_msg_per_sec'], reverse=True)

    print(f"\n  {'排名':<5} {'配置':<35} {'吞吐量':<15} {'平均延迟':<15} {'缓存命中率':<15}")
    print(f"  {'-'*5} {'-'*35} {'-'*15} {'-'*15} {'-'*15}")

    for i, r in enumerate(sorted_results[:10], 1):
        print(f"  {i:<5} {r['name']:<35} {r['throughput_msg_per_sec']:>8.2f} msg/s  {r['avg_latency_ms']:>8.2f} ms     {r['cache_hit_ratio']*100:>6.1f}%")


def print_summary_table(results: List[Dict]):
    """打印汇总表格"""
    print_header("完整对比表格")

    print(f"\n  {'配置':<30} {'吞吐(msg/s)':<15} {'P95(ms)':<12} {'缓存率':<10} {'错误率':<10}")
    print(f"  {'-'*30} {'-'*15} {'-'*12} {'-'*10} {'-'*10}")

    for r in results:
        error_rate = (r['errors'] / r['total_messages'] * 100) if r['total_messages'] > 0 else 0
        print(f"  {r['name']:<30} {r['throughput_msg_per_sec']:>10.2f}       {r['p95_latency_ms']:>8.2f}    {r['cache_hit_ratio']*100:>6.1f}%    {error_rate:>6.1f}%")


def print_key_findings(results: List[Dict]):
    """打印关键发现"""
    print_header("关键发现")

    # 最高吞吐
    best_throughput = max(results, key=lambda r: r['throughput_msg_per_sec'])
    print(f"\n  {Colors.OKGREEN}✓ 最高吞吐:{Colors.ENDC}")
    print(f"    {best_throughput['name']}: {best_throughput['throughput_msg_per_sec']:.2f} msg/s")

    # 最低延迟
    best_latency = min(results, key=lambda r: r['avg_latency_ms'])
    print(f"\n  {Colors.OKGREEN}✓ 最低延迟:{Colors.ENDC}")
    print(f"    {best_latency['name']}: {best_latency['avg_latency_ms']:.2f} ms")

    # 最高缓存命中率
    best_cache = max(results, key=lambda r: r['cache_hit_ratio'])
    print(f"\n  {Colors.OKGREEN}✓ 最高缓存命中率:{Colors.ENDC}")
    print(f"    {best_cache['name']}: {best_cache['cache_hit_ratio']*100:.1f}%")

    # 性能平衡点
    # 找到吞吐量和延迟都比较好的配置
    balanced = min(results, key=lambda r: (1 - r['throughput_msg_per_sec']/max(r['throughput_msg_per_sec'] for r in results)) +
                                            (r['avg_latency_ms']/max(r['avg_latency_ms'] for r in results)))
    print(f"\n  {Colors.OKGREEN}✓ 性能平衡点:{Colors.ENDC}")
    print(f"    {balanced['name']}: 吞吐 {balanced['throughput_msg_per_sec']:.2f} msg/s, 延迟 {balanced['avg_latency_ms']:.2f} ms")


def print_recommendations(results: List[Dict]):
    """打印建议"""
    print_header("推荐配置")

    print(f"\n  {Colors.BOLD}【场景 1：追求最大吞吐】{Colors.ENDC}")
    best = max(results, key=lambda r: r['throughput_msg_per_sec'])
    print(f"    配置: {best['name']}")
    print(f"    吞吐: {best['throughput_msg_per_sec']:.2f} msg/s")

    print(f"\n  {Colors.BOLD}【场景 2：追求低延迟】{Colors.ENDC}")
    low_latency = min((r for r in results if r['throughput_msg_per_sec'] > 100),
                      key=lambda r: r['avg_latency_ms'])
    print(f"    配置: {low_latency['name']}")
    print(f"    延迟: {low_latency['avg_latency_ms']:.2f} ms")

    print(f"\n  {Colors.BOLD}【场景 3：均衡性能】{Colors.ENDC}")
    # 吞吐和延迟的均衡
    balanced = min(results, key=lambda r: (r['avg_latency_ms']/100) + (1000/r['throughput_msg_per_sec']))
    print(f"    配置: {balanced['name']}")
    print(f"    吞吐: {balanced['throughput_msg_per_sec']:.2f} msg/s, 延迟: {balanced['avg_latency_ms']:.2f} ms")


def main():
    if len(sys.argv) < 2:
        print("用法: python analyze_benchmark.py <benchmark_results.json>")
        sys.exit(1)

    filename = sys.argv[1]

    if not Path(filename).exists():
        print(f"文件不存在: {filename}")
        sys.exit(1)

    data = load_results(filename)
    results = data['results']

    print(f"\n{Colors.BOLD}{Colors.HEADER}🏆 BenchMark 分析报告{Colors.ENDC}{Colors.ENDC}")
    print(f"时间: {data['timestamp']}")
    print(f"测试数: {len(results)} 个")

    # 分析
    print_concurrent_analysis(results)
    print_message_count_analysis(results)
    print_cache_effect_analysis(results)
    print_latency_analysis(results)
    print_throughput_comparison(results)
    print_summary_table(results)
    print_key_findings(results)
    print_recommendations(results)

    print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*120}{Colors.ENDC}{Colors.ENDC}\n")


if __name__ == "__main__":
    main()

