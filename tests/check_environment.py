#!/usr/bin/env python3
"""
✅ 压测环境检查工具

验证系统和 Python 环境是否就绪
"""

import asyncio
import sys
from pathlib import Path


def check_python_version():
    """检查 Python 版本"""
    print("🐍 Python 版本检查...")

    version = sys.version_info
    min_version = (3, 8)

    if version >= min_version:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor} (需要 >= 3.8)")
        return False


def check_modules():
    """检查必需的 Python 模块"""
    print("\n📦 模块检查...")

    required_modules = [
        "asyncio",
        "json",
        "sqlite3",
        "time",
        "random",
    ]

    optional_modules = [
        "aiohttp",
        "prometheus_client",
    ]

    all_ok = True

    for module in required_modules:
        try:
            __import__(module)
            print(f"   ✅ {module}")
        except ImportError:
            print(f"   ❌ {module} (必需)")
            all_ok = False

    for module in optional_modules:
        try:
            __import__(module)
            print(f"   ✅ {module} (可选)")
        except ImportError:
            print(f"   ⚠️  {module} (可选，某些功能可能不可用)")

    return all_ok


def check_disk_space():
    """检查磁盘空间"""
    print("\n💾 磁盘空间检查...")

    try:
        import shutil
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024 ** 3)

        if free_gb > 5:
            print(f"   ✅ {free_gb:.1f} GB 可用空间")
            return True
        else:
            print(f"   ⚠️  {free_gb:.1f} GB 可用空间 (建议 > 5GB)")
            return False
    except Exception as e:
        print(f"   ⚠️  无法检查磁盘空间: {e}")
        return True


def check_file_structure():
    """检查项目文件结构"""
    print("\n📁 项目文件结构检查...")

    project_root = Path(__file__).parent.parent
    required_files = [
        "tests/load_test_simple.py",
        "tests/load_test_http.py",
        "tests/run_all_tests.py",
        "tests/analyze_results.py",
    ]

    all_ok = True
    for file in required_files:
        file_path = project_root / file
        if file_path.exists():
            print(f"   ✅ {file}")
        else:
            print(f"   ❌ {file} (缺失)")
            all_ok = False

    return all_ok


async def check_asyncio():
    """检查异步功能"""
    print("\n⚡ 异步功能检查...")

    try:
        # 测试信号量
        sem = asyncio.Semaphore(5)

        async def test_semaphore():
            async with sem:
                await asyncio.sleep(0.01)

        await asyncio.gather(*[test_semaphore() for _ in range(10)])
        print(f"   ✅ asyncio.Semaphore 正常")

        # 测试队列
        queue = asyncio.Queue()
        await queue.put("test")
        item = await queue.get()
        print(f"   ✅ asyncio.Queue 正常")

        return True
    except Exception as e:
        print(f"   ❌ 异步功能错误: {e}")
        return False


def check_network():
    """检查网络连接"""
    print("\n🌐 网络连接检查...")

    try:
        import socket

        # 检查 DNS 解析
        ip = socket.gethostbyname("discord.com")
        print(f"   ✅ DNS 解析正常 (discord.com -> {ip})")

        return True
    except Exception as e:
        print(f"   ⚠️  网络问题: {e}")
        return True  # 网络问题不是必须的，只是影响 HTTP 测试


def check_permissions():
    """检查文件权限"""
    print("\n🔐 文件权限检查...")

    project_root = Path(__file__).parent.parent

    # 检查是否可以在项目目录中写入
    try:
        test_file = project_root / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        print(f"   ✅ 项目目录可写入")
        return True
    except Exception as e:
        print(f"   ❌ 项目目录权限问题: {e}")
        return False


def run_quick_test():
    """运行快速测试"""
    print("\n🧪 快速测试 (模拟 100 条消息)...")

    try:
        # 导入压测模块
        sys.path.insert(0, str(Path(__file__).parent))
        from load_test_simple import LoadTest

        # 运行快速测试
        async def quick_test():
            test = LoadTest(num_channels=2, msgs_per_channel=50, concurrent_limit=5)
            metrics = await test.run()
            return metrics

        metrics = asyncio.run(quick_test())

        if metrics.throughput > 0:
            print(f"   ✅ 快速测试成功")
            print(f"      吞吐量: {metrics.throughput:.2f} msg/s")
            print(f"      平均延迟: {metrics.avg_latency_ms:.2f}ms")
            return True
        else:
            print(f"   ⚠️  快速测试完成但无结果")
            return False
    except Exception as e:
        print(f"   ⚠️  快速测试失败: {e}")
        return False


def print_summary(results: dict):
    """打印检查摘要"""
    print("\n" + "="*60)
    print("📊 环境检查摘要")
    print("="*60)

    all_ok = all(results.values())

    for check_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {check_name}")

    print("="*60)

    if all_ok:
        print("✅ 环境就绪！可以运行压测")
        print("\n快速开始:")
        print("  python tests/load_test_simple.py --channels 10 --messages 50")
    else:
        print("⚠️  环境有问题，请检查上面的错误信息")

    return all_ok


def main():
    print("🔧 Discord Bot 压测环境检查\n")
    print("检查项目:")
    print("-" * 60)

    results = {
        "Python 版本": check_python_version(),
        "必需模块": check_modules(),
        "磁盘空间": check_disk_space(),
        "文件结构": check_file_structure(),
        "文件权限": check_permissions(),
    }

    # 异步检查
    try:
        results["异步功能"] = asyncio.run(check_asyncio())
    except Exception as e:
        print(f"⚠️  异步检查失败: {e}")
        results["异步功能"] = False

    # 网络检查
    results["网络连接"] = check_network()

    # 快速测试 (可选)
    # results["快速测试"] = run_quick_test()

    # 打印摘要
    success = print_summary(results)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

