#!/usr/bin/env python3
"""
🔍 压测 + Prometheus 指标导出

不依赖 prometheus_client，直接生成 Prometheus 格式的指标文本
"""

import aiohttp
import asyncio
import logging
import requests
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


@dataclass
class LLMConfig:
    """LLM 配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-3.5-turbo"
    timeout: int = 30


class PrometheusMetrics:
    """Prometheus 指标容器"""

    def __init__(self):
        self.llm_calls_total = {}  # (model, status) -> count
        self.messages_processed_total = {}  # source -> count
        self.cache_hits_total = 0
        self.llm_latencies = []
        self.message_latencies = []
        self.cache_latencies = []
        self.db_latencies = []
        self.cache_hit_ratio = 0.0
        self.concurrent_current = 0
        self.concurrent_peak = 0
        self.llm_errors_total = {}  # error_type -> count
        self.throughput = 0.0

    def to_prometheus_text(self):
        """转换为 Prometheus 文本格式"""
        text = ""

        # HELP 和 TYPE
        text += "# HELP discord_bot_llm_calls_total Total LLM API calls\n"
        text += "# TYPE discord_bot_llm_calls_total counter\n"
        for (model, status), count in self.llm_calls_total.items():
            text += f'discord_bot_llm_calls_total{{model="{model}",status="{status}"}} {count}\n'

        text += "\n# HELP discord_bot_messages_processed_total Total messages processed\n"
        text += "# TYPE discord_bot_messages_processed_total counter\n"
        for source, count in self.messages_processed_total.items():
            text += f'discord_bot_messages_processed_total{{source="{source}"}} {count}\n'

        text += "\n# HELP discord_bot_cache_hits_total Total cache hits\n"
        text += "# TYPE discord_bot_cache_hits_total counter\n"
        text += f"discord_bot_cache_hits_total {self.cache_hits_total}\n"

        text += "\n# HELP discord_bot_cache_hit_ratio Cache hit ratio (0-1)\n"
        text += "# TYPE discord_bot_cache_hit_ratio gauge\n"
        text += f"discord_bot_cache_hit_ratio {self.cache_hit_ratio}\n"

        text += "\n# HELP discord_bot_concurrent_messages_current Current concurrent messages\n"
        text += "# TYPE discord_bot_concurrent_messages_current gauge\n"
        text += f"discord_bot_concurrent_messages_current {self.concurrent_current}\n"

        text += "\n# HELP discord_bot_concurrent_messages_peak Peak concurrent messages\n"
        text += "# TYPE discord_bot_concurrent_messages_peak gauge\n"
        text += f"discord_bot_concurrent_messages_peak {self.concurrent_peak}\n"

        text += "\n# HELP discord_bot_throughput_msg_per_sec Throughput (msg/s)\n"
        text += "# TYPE discord_bot_throughput_msg_per_sec gauge\n"
        text += f"discord_bot_throughput_msg_per_sec {self.throughput}\n"

        # 直方图（简化处理）
        if self.llm_latencies:
            text += "\n# HELP discord_bot_llm_call_duration_seconds_sum LLM call duration sum\n"
            text += "# TYPE discord_bot_llm_call_duration_seconds_sum counter\n"
            text += f"discord_bot_llm_call_duration_seconds_sum {sum(self.llm_latencies) / 1000}\n"

            text += "\n# HELP discord_bot_llm_call_duration_seconds_count LLM call count\n"
            text += "# TYPE discord_bot_llm_call_duration_seconds_count counter\n"
            text += f"discord_bot_llm_call_duration_seconds_count {len(self.llm_latencies)}\n"

        # 错误
        text += "\n# HELP discord_bot_llm_errors_total Total LLM errors\n"
        text += "# TYPE discord_bot_llm_errors_total counter\n"
        for error_type, count in self.llm_errors_total.items():
            text += f'discord_bot_llm_errors_total{{error_type="{error_type}"}} {count}\n'

        return text

    def push_to_pushgateway(self, pushgateway_url: str, job_name: str):
        """推送到 Prometheus PushGateway"""
        try:
            text = self.to_prometheus_text()
            response = requests.post(
                f"{pushgateway_url}/metrics/job/{job_name}",
                data=text,
                timeout=5
            )
            if response.status_code == 202:
                logger.info(f"{Colors.OKGREEN}✓ Prometheus 指标已上报到 {pushgateway_url}{Colors.ENDC}")
                return True
            else:
                logger.warning(f"{Colors.WARNING}⚠️ 上报失败，状态码: {response.status_code}{Colors.ENDC}")
                return False
        except Exception as e:
            logger.warning(f"{Colors.WARNING}⚠️ 无法上报到 Prometheus: {e}{Colors.ENDC}")
            return False


class LLMClient:
    """真实 LLM 客户端"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.call_count = 0
        self.total_time = 0.0
        self.errors = 0

    async def chat(self, message: str, session: aiohttp.ClientSession) -> Optional[str]:
        """调用 LLM API"""
        start_time = time.time()

        if not self.config.api_key:
            # 模拟模式（如果没有 API key）
            await asyncio.sleep(0.1)
            self.call_count += 1
            return "Mock response"

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": "You are a helpful Discord bot assistant."},
                {"role": "user", "content": message}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        try:
            async with session.post(
                f"{self.config.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    response = data['choices'][0]['message']['content']
                    self.call_count += 1
                    elapsed = time.time() - start_time
                    self.total_time += elapsed
                    logger.info(f"{Colors.OKGREEN}✓ LLM Call{Colors.ENDC} | {message[:30]:30s} | Response: {response[:50]:50s} | {elapsed*1000:.0f}ms")
                    return response
                else:
                    error_text = await resp.text()
                    logger.error(f"{Colors.FAIL}❌ LLM Error{Colors.ENDC} | Status: {resp.status} | {error_text[:100]}")
                    self.errors += 1
                    return None
        except asyncio.TimeoutError:
            logger.error(f"{Colors.FAIL}❌ LLM Timeout{Colors.ENDC} | {message[:30]:30s}")
            self.errors += 1
            return None
        except Exception as e:
            logger.error(f"{Colors.FAIL}❌ LLM Exception{Colors.ENDC} | {str(e)[:100]}")
            self.errors += 1
            return None


class RealLLMLoadTest:
    """真实 LLM 压测"""

    def __init__(self, num_channels=10, msgs_per_channel=5, concurrent_limit=3, llm_config: Optional[LLMConfig] = None, prometheus_pushgateway: Optional[str] = None):
        self.num_channels = num_channels
        self.msgs_per_channel = msgs_per_channel
        self.concurrent_limit = concurrent_limit
        self.prometheus_pushgateway = prometheus_pushgateway

        self.llm_config = llm_config or LLMConfig()
        self.llm_client = LLMClient(self.llm_config)

        self.semaphore = asyncio.Semaphore(concurrent_limit)
        self.queue = asyncio.Queue()

        self.cache = {}
        self.latencies = []
        self.llm_times = []
        self.db_times = []
        self.cache_hits = 0
        self.total_messages = 0
        self.errors = 0
        self.concurrent_count = 0
        self.peak_concurrent = 0

        self.metrics = PrometheusMetrics()
        self.worker_stats = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time = time.time()

    async def message_processor(self, message: Dict):
        """处理单条消息，真实调用 LLM"""
        self.concurrent_count += 1
        self.peak_concurrent = max(self.peak_concurrent, self.concurrent_count)
        self.metrics.concurrent_current = self.concurrent_count
        self.metrics.concurrent_peak = self.peak_concurrent

        try:
            msg_id = message['message_id']
            channel = message['channel']
            content = message['content']
            start_time = time.time()

            # 缓存查询
            cache_key = f"{channel}:latest"
            cache_lookup_start = time.time()

            if cache_key in self.cache:
                cache_lookup_time = (time.time() - cache_lookup_start) * 1000
                self.cache_hits += 1
                self.metrics.cache_latencies.append(cache_lookup_time)
                self.metrics.cache_hits_total += 1

                # 更新指标
                key = 'cache_hit'
                self.metrics.messages_processed_total[key] = self.metrics.messages_processed_total.get(key, 0) + 1

                await asyncio.sleep(0.005)
                total_time = (time.time() - start_time) * 1000
                self.metrics.message_latencies.append(total_time)

                logger.info(f"{Colors.OKGREEN}✓ CACHE_HIT{Colors.ENDC} | {msg_id:15s} | {cache_lookup_time:.1f}ms")
                self.latencies.append(total_time)
                return

            # 缓存未命中，真实调用 LLM
            cache_lookup_time = (time.time() - cache_lookup_start) * 1000
            self.metrics.cache_latencies.append(cache_lookup_time)

            llm_start = time.time()
            try:
                response = await self.llm_client.chat(content, self.session)
                llm_time = (time.time() - llm_start) * 1000
                self.llm_times.append(llm_time)
                self.metrics.llm_latencies.append(llm_time)

                if response is None:
                    self.errors += 1
                    key = (self.llm_config.model, 'error')
                    self.metrics.llm_calls_total[key] = self.metrics.llm_calls_total.get(key, 0) + 1
                    return

                # 更新指标
                key = (self.llm_config.model, 'success')
                self.metrics.llm_calls_total[key] = self.metrics.llm_calls_total.get(key, 0) + 1

                # 数据库写入
                db_start = time.time()
                await asyncio.sleep(0.01)  # 模拟 DB 操作
                db_time = (time.time() - db_start) * 1000
                self.db_times.append(db_time)
                self.metrics.db_latencies.append(db_time)

                # 更新缓存
                self.cache[cache_key] = {
                    'response': response,
                    'timestamp': datetime.now().isoformat()
                }

                total_time = (time.time() - start_time) * 1000

                # 更新指标
                key = 'llm_call'
                self.metrics.messages_processed_total[key] = self.metrics.messages_processed_total.get(key, 0) + 1
                self.metrics.message_latencies.append(total_time)

                logger.info(f"{Colors.OKGREEN}✓ DONE{Colors.ENDC} | {msg_id:15s} | LLM:{llm_time:7.0f}ms | DB:{db_time:5.1f}ms | Total:{total_time:7.0f}ms")
                self.latencies.append(total_time)

            except Exception as e:
                logger.error(f"{Colors.FAIL}❌ Error{Colors.ENDC} | {msg_id:15s} | {str(e)[:80]}")
                self.errors += 1
                key = (self.llm_config.model, 'error')
                self.metrics.llm_calls_total[key] = self.metrics.llm_calls_total.get(key, 0) + 1
        finally:
            self.concurrent_count -= 1
            self.metrics.concurrent_current = self.concurrent_count

    async def worker(self, worker_id: int):
        """工作线程"""
        logger.info(f"{Colors.HEADER}👷 Worker {worker_id} started{Colors.ENDC}")
        self.worker_stats[worker_id] = {'processed': 0, 'errors': 0}

        while True:
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break

            async with self.semaphore:
                try:
                    await self.message_processor(message)
                    self.worker_stats[worker_id]['processed'] += 1
                except Exception as e:
                    logger.error(f"{Colors.FAIL}Worker {worker_id} error{Colors.ENDC}: {e}")
                    self.worker_stats[worker_id]['errors'] += 1

            self.queue.task_done()

        logger.info(f"{Colors.HEADER}👷 Worker {worker_id} finished{Colors.ENDC}")

    async def run(self):
        """运行压测"""
        print(f"\n{Colors.BOLD}{Colors.HEADER}🔍 真实 LLM 压测 + Prometheus 上报{Colors.ENDC}{Colors.ENDC}")
        print(f"{Colors.BOLD}频道: {self.num_channels}, 消息/频道: {self.msgs_per_channel}, 并发: {self.concurrent_limit}")
        print(f"模式: {'真实 LLM' if self.llm_config.api_key else '模拟 LLM'}")
        if self.prometheus_pushgateway:
            print(f"Prometheus PushGateway: {self.prometheus_pushgateway}")
        print(f"{Colors.ENDC}\n")

        self.start_time = time.time()

        # 创建 HTTP 会话
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
        self.session = aiohttp.ClientSession(connector=connector)

        try:
            # 启动 Worker
            num_workers = min(self.concurrent_limit, 5)
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
                        "content": f"What is the best Discord bot strategy for channel ch_{ch_id}?"
                    }
                    await self.queue.put(message)
                    await asyncio.sleep(0.01)

            logger.info(f"✅ 已提交 {self.total_messages} 条消息到队列")
            logger.info("等待处理完成...")

            # 等待完成
            await self.queue.join()
            await asyncio.gather(*workers)

        finally:
            await self.session.close()

        end_time = time.time()
        duration = end_time - self.start_time

        # 最终统计
        self._print_summary(duration)

        # 上报到 Prometheus PushGateway
        if self.prometheus_pushgateway:
            # 更新最终指标
            if self.total_messages > 0:
                self.metrics.cache_hit_ratio = self.cache_hits / self.total_messages
            self.metrics.throughput = self.total_messages / duration if duration > 0 else 0

            # 推送
            self.metrics.push_to_pushgateway(
                f"http://{self.prometheus_pushgateway}",
                "discord_bot_load_test"
            )

    def _print_summary(self, duration):
        """打印最终统计"""
        print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*80}{Colors.ENDC}{Colors.ENDC}")
        print(f"{Colors.BOLD}📊 压测结果 + Prometheus 指标{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKGREEN}{'='*80}{Colors.ENDC}{Colors.ENDC}\n")

        print(f"【基础指标】")
        print(f"  总消息: {self.total_messages}")
        print(f"  缓存命中: {self.cache_hits}")
        print(f"  LLM 调用: {self.llm_client.call_count}")
        print(f"  错误: {self.errors}")
        print(f"  成功率: {(self.total_messages - self.errors) / self.total_messages * 100:.1f}%")

        print(f"\n【LLM 调用统计】")
        if self.llm_client.call_count > 0:
            avg_llm = self.llm_client.total_time / self.llm_client.call_count
            print(f"  总调用: {self.llm_client.call_count}")
            print(f"  平均时间: {avg_llm*1000:.0f}ms")
            print(f"  总耗时: {self.llm_client.total_time:.2f}s")
            print(f"  错误: {self.llm_client.errors}")

        if self.llm_times:
            print(f"\n【LLM 延迟分布】")
            sorted_llm = sorted(self.llm_times)
            print(f"  最小: {min(self.llm_times):.0f}ms")
            print(f"  平均: {sum(self.llm_times)/len(self.llm_times):.0f}ms")
            print(f"  最大: {max(self.llm_times):.0f}ms")
            print(f"  P95: {sorted_llm[int(len(sorted_llm)*0.95)]:.0f}ms")
            print(f"  P99: {sorted_llm[int(len(sorted_llm)*0.99)]:.0f}ms")

        if self.latencies:
            print(f"\n【总延迟分布】")
            sorted_lat = sorted(self.latencies)
            print(f"  最小: {min(self.latencies):.0f}ms")
            print(f"  平均: {sum(self.latencies)/len(self.latencies):.0f}ms")
            print(f"  最大: {max(self.latencies):.0f}ms")
            print(f"  P95: {sorted_lat[int(len(sorted_lat)*0.95)]:.0f}ms")
            print(f"  P99: {sorted_lat[int(len(sorted_lat)*0.99)]:.0f}ms")

        print(f"\n【缓存效率】")
        cache_ratio = self.cache_hits / self.total_messages * 100
        print(f"  命中率: {cache_ratio:.1f}%")
        print(f"  缓存大小: {len(self.cache)}")

        print(f"\n【吞吐量】")
        throughput = self.total_messages / duration
        print(f"  总吞吐量: {throughput:.2f} msg/s")
        print(f"  总耗时: {duration:.2f}s")

        print(f"\n【Prometheus 指标已准备好上报】")
        print(f"  discord_bot_llm_calls_total")
        print(f"  discord_bot_messages_processed_total")
        print(f"  discord_bot_cache_hits_total")
        print(f"  discord_bot_cache_hit_ratio")
        print(f"  discord_bot_concurrent_messages_current")
        print(f"  discord_bot_concurrent_messages_peak")
        print(f"  discord_bot_throughput_msg_per_sec")
        print(f"  discord_bot_llm_call_duration_seconds")
        print(f"  discord_bot_llm_errors_total")

        print(f"\n{Colors.BOLD}{Colors.OKGREEN}{'='*80}{Colors.ENDC}{Colors.ENDC}\n")


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--messages", type=int, default=5)
    parser.add_argument("--concurrent", type=int, default=3)
    parser.add_argument("--api-key", type=str, default="")
    parser.add_argument("--base-url", type=str, default="https://api.openai.com/v1")
    parser.add_argument("--model", type=str, default="gpt-3.5-turbo")
    parser.add_argument("--prometheus", type=str, default="localhost:9091", help="Prometheus PushGateway address (e.g., localhost:9091)")

    args = parser.parse_args()

    # 配置 LLM
    llm_config = LLMConfig(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model
    )

    test = RealLLMLoadTest(
        num_channels=args.channels,
        msgs_per_channel=args.messages,
        concurrent_limit=args.concurrent,
        llm_config=llm_config,
        prometheus_pushgateway=args.prometheus if args.prometheus else None
    )

    await test.run()


if __name__ == "__main__":
    asyncio.run(main())

