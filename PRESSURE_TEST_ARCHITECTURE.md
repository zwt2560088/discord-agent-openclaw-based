# 🏗️ 完整并发压测套件架构

> 从消息模拟、信号量控制、到性能测量的完整工程设计

---

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                   压测套件总架构                             │
└─────────────────────────────────────────────────────────────┘

1️⃣ 消息生成层
   ├─ 多频道模拟 (50-100 频道)
   ├─ 消息分布 (Poisson / Uniform)
   └─ 异步提交到队列

2️⃣ 队列 + 信号量层
   ├─ asyncio.Queue (FIFO 消息队列)
   ├─ asyncio.Semaphore(20) ← 关键限流
   └─ 工作线程池 (10 个 worker)

3️⃣ 处理层
   ├─ 缓存检查 (LRU 内存缓存)
   ├─ AI 处理 (模拟 500ms Poisson 分布)
   ├─ 数据库写入 (SQLite)
   └─ 结果收集

4️⃣ 测量层
   ├─ 消息级指标 (队列等待、处理时间、延迟)
   ├─ 频道级指标 (吞吐量、P95、P99)
   ├─ 系统级指标 (峰值并发、缓存命中率)
   └─ 时间序列数据 (趋势分析)

5️⃣ 分析 + 报告层
   ├─ JSON 结果导出
   ├─ Markdown 报告生成
   ├─ 对标对比
   └─ ASCII 图表可视化
```

---

## 🔄 消息处理流程

```
时间线示意:

消息 M1 到达
├─ T0: send_time = 当前时间
├─ 进入队列
│  └─ queue_start_time = T1
│     queue_wait_time = T1 - T0
├─ 等待信号量可用 (如果已满)
│  └─ 阻塞至 T2
├─ 获得信号量 (concurrent_count++)
│  ├─ processing_start_time = T2
│  ├─ 缓存查询 (10ms, 12% 命中)
│  ├─ AI 处理 (平均 500ms, Poisson)
│  ├─ 数据库写入 (平均 10ms)
│  ├─ processing_time = T3 - T2
│  └─ total_latency = T3 - T0
└─ 释放信号量 (concurrent_count--)


关键观察:
- 信号量最多让 20 个消息同时处理
- 其他消息在 Queue 中等待
- 队列等待时间 = (所有并发任务的处理时间) / 20
```

---

## 🎯 核心组件详解

### 1. SimulatedQueue (队列 + 信号量)

```python
class SimulatedQueue:
    def __init__(self, max_concurrent: int):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.queue = asyncio.Queue()
        self.peak_concurrent = 0

    async def process_worker(self, processor):
        """
        关键步骤:
        1. 从队列获取消息 (FIFO)
        2. 获取信号量 (可能等待)
        3. 在信号量保护下处理
        4. 完成后释放

        并发控制的关键在这里!
        """
        while True:
            message, metrics = await self.queue.get()

            # 记录队列等待时间
            metrics.queue_wait_time = time.time() - metrics.queue_start

            # 关键: 信号量限流
            async with self.semaphore:
                self.concurrent_count += 1
                # ... 处理消息 ...
                self.concurrent_count -= 1

            self.queue.task_done()
```

### 2. MessageProcessor (模拟真实处理)

```python
class MessageProcessor:
    async def process(self, message, metrics):
        # 1️⃣ 缓存查询 (~10ms, 12% 命中率)
        if self.cache.get(cache_key):
            metrics.cache_hit = True
            await asyncio.sleep(0.01)
            return

        # 2️⃣ AI 处理 (~500ms, Poisson 分布)
        processing_time = random.expovariate(1.0 / 500)
        processing_time = max(50, min(processing_time, 3000))
        await asyncio.sleep(processing_time / 1000)

        # 3️⃣ 数据库写入 (~10ms)
        await self._write_to_db(message)

        # 4️⃣ 更新缓存
        self.cache[cache_key] = message
```

### 3. 指标收集

```python
@dataclass
class MessageMetrics:
    """消息级指标"""
    send_time: float              # 发送时刻
    queue_start_time: float       # 进入队列时刻
    queue_wait_time_ms: float     # 队列等待 = queue_start - send_time
    processing_start_time: float  # 处理开始时刻
    processing_time_ms: float     # 处理耗时 = processing_end - processing_start
    total_latency_ms: float       # 端到端延迟 = processing_end - send_time
    cache_hit: bool               # 是否命中缓存
    error: Optional[str]          # 错误信息

# 汇总为频道级和系统级指标
- ChannelMetrics: 平均/P95/P99 延迟
- SystemMetrics: 吞吐量、缓存命中率、并发分析
```

---

## 📈 性能指标体系

### 层次关系

```
个体延迟 (单条消息)
    ↓ 分布统计
平均延迟、P50、P95、P99
    ↓ 汇总
频道级统计 (per channel)
    ↓ 聚合
系统级指标 (system-wide)
```

### 关键公式

**吞吐量 (Throughput)**
```
Throughput = 成功消息数 / 总耗时(秒)

理论上限:
  = 信号量 × (1 / 平均处理时间)
  = 20 × (1 / 0.5s)
  = 40 msg/s
```

**端到端延迟 (E2E Latency)**
```
总延迟 = 队列等待 + 处理时间
       = (N-1) × 平均处理时间 / 20 + 平均处理时间

其中 N 是当前队列中的消息数

例: 100 条消息在队列中
  = 99 × 500ms / 20 + 500ms
  = 2475 + 500 = 2975ms
```

**百分位延迟**
```
P95 = sorted_latencies[int(0.95 × n)]

含义: 95% 的消息在 P95 时间内完成
     5% 的消息超过 P95 时间（长尾）
```

---

## 🔬 测试方法论

### 测试金字塔

```
           ┌──────────────────┐
           │  极限测试        │  <- 测试系统上限
           │  (200 频道)      │     找出崩溃点
           ├──────────────────┤
           │  压力测试        │  <- 测试实际负载
           │  (50-100 频道)   │     找出性能抖动
           ├──────────────────┤
           │  功能测试        │  <- 快速回归
           │  (10-20 频道)    │     开发阶段反馈
           ├──────────────────┤
           │  烟雾测试        │  <- 最快检查
           │  (1-5 频道)      │     30 秒内完成
           └──────────────────┘
```

### 多场景设计

```
低并发场景 (10 频道 × 50 消息 × 5 并发)
├─ 目标: 验证正确性
├─ 预期: 无延迟波动, 高吞吐
└─ 发现: 缓存效果、基准性能

中并发场景 (30 频道 × 100 消息 × 15 并发)
├─ 目标: 典型使用场景
├─ 预期: 吞吐量 60-80 msg/s
└─ 发现: 常规性能

高并发场景 (50 频道 × 100 消息 × 20 并发)
├─ 目标: 满负载运行
├─ 预期: 吞吐量 40-50 msg/s, P95 < 1000ms
└─ 发现: 性能边界

极限场景 (100 频道 × 50 消息 × 20 并发)
├─ 目标: 寻找崩溃点
├─ 预期: 吞吐量下降, P99 > 2000ms
└─ 发现: 系统上限
```

---

## 🛠️ 工具链

```
load_test_simple.py
├─ 消息生成 + 队列模拟
├─ 工作线程处理
├─ 指标收集
└─ JSON 结果导出

load_test_http.py
├─ aiohttp 连接池模拟
├─ HTTP 并发请求
├─ 连接复用测试
└─ 吞吐量/延迟测量

run_all_tests.py
├─ 协调运行多个压测
├─ 多场景执行
├─ 结果汇总
└─ 报告生成 (Markdown)

analyze_results.py
├─ 结果解析 + 美化
├─ 基准对比
├─ 趋势分析
└─ ASCII 图表可视化
```

---

## 💾 数据流

```
1️⃣ 消息生成
   ├─ 50 频道 × 100 消息 = 5000 条消息
   └─ 元数据: channel_id, message_id, content

2️⃣ 提交到队列
   ├─ 异步 Queue.put()
   └─ 记录 send_time, queue_start_time

3️⃣ 队列处理
   ├─ Worker 从 Queue.get()
   ├─ 等待 Semaphore (可能阻塞)
   └─ 记录等待时间

4️⃣ 消息处理
   ├─ 缓存查询 (命中? → 快速返回)
   ├─ AI 模拟 (500ms Poisson)
   ├─ 数据库写入
   └─ 记录 processing_time, latency_ms

5️⃣ 指标收集
   ├─ MessageMetrics (单条记录)
   ├─ 内存中积累 (List[MessageMetrics])
   └─ 统计计算 (平均、P95、P99)

6️⃣ 结果输出
   ├─ JSON 格式 (原始数据)
   ├─ Markdown 报告 (易读)
   └─ ASCII 图表 (可视化)
```

---

## ⚙️ 关键参数配置

### 信号量 (Semaphore)

```python
semaphore = asyncio.Semaphore(20)

为什么是 20?
- 经验值: 平衡吞吐量和响应时间
- 太小 (5): 吞吐量低 (~20 msg/s)
- 太大 (100): 内存溢出, P99 延迟爆炸
- 20: 最优平衡点

可调范围:
- CPU 密集: 10-20
- I/O 密集: 50-100 (但受 Discord API 限制)
```

### 消息处理时间分布

```python
# Poisson 分布 (真实场景)
base_time = random.expovariate(1.0 / 500)  # 平均 500ms
processing_time = max(50, min(base_time, 3000))

特点:
- 大多数快 (50-200ms) → 缓存命中或关键词匹配
- 部分慢 (500-2000ms) → LLM API 调用
- 少数很慢 (2000-3000ms) → RAG 查询或超时

# Uniform 分布 (理想化场景)
processing_time = random.uniform(250, 750)  # 500ms±250ms
```

### 连接池 (aiohttp)

```python
connector = aiohttp.TCPConnector(
    limit=100,              # 总连接数
    limit_per_host=30       # 单主机限制
)

为什么这个配置?
- limit=100: 50 频道 × 2 并发请求 = 100 连接足够
- limit_per_host=30: Discord API 单点不超限
- 连接复用: TCP 连接保活和复用
```

---

## 📊 输出示例

### JSON 结果

```json
{
  "timestamp": "2026-03-29T10:30:00",
  "config": {
    "channels": 50,
    "messages_per_channel": 100,
    "concurrent_limit": 20
  },
  "metrics": {
    "total_sent": 5000,
    "total_processed": 5000,
    "total_errors": 0,
    "peak_concurrent": 20,
    "throughput": 45.32,
    "avg_latency_ms": 520.15,
    "p95_latency_ms": 890.32,
    "p99_latency_ms": 1250.88,
    "cache_hit_ratio": 0.12,
    "db_p95_ms": 22.15,
    "duration_sec": 110.25
  }
}
```

### Markdown 报告

```markdown
# 🔥 Discord Bot 并发压测报告

## 📊 执行摘要

### 1️⃣ 消息处理并发压测

| 指标 | 值 |
|------|-----|
| 总消息 | 5000 |
| 吞吐量 | 45.32 msg/s ✅ |
| P95 延迟 | 890.32ms ✅ |
| 缓存命中率 | 12.0% |

## 🎯 性能分析

1. **信号量生效**: 峰值并发 ≈ 20 ✅
2. **吞吐量达标**: 45 msg/s > 理论 40 msg/s ✅
3. **缓存优化**: 命中率可提升到 30-50%
4. **长尾延迟**: P99 来自 LLM API 超时

## 🚀 优化建议

1. 扩大缓存键策略（当前仅缓存最新消息）
2. 使用 asyncpg 替代 sqlite3
3. 添加 LLM 请求超时和降级
4. 集成 Prometheus 监控
```

---

## 🔄 CI/CD 集成

### GitHub Actions 示例

```yaml
name: Load Test

on:
  schedule:
    - cron: '0 2 * * *'  # 每天 2:00 AM UTC

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run load test
        run: python tests/load_test_simple.py --channels 50 --messages 100 --output result.json

      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: load-test-results
          path: result.json

      - name: Generate report
        run: python tests/analyze_results.py result.json > report.txt

      - name: Notify on failure
        if: failure()
        uses: slack-notify@v1
        with:
          message: "❌ Load test failed!"
```

---

## 📚 扩展方向

### 1. 实时监控仪表板

```python
# Prometheus + Grafana
from prometheus_client import Counter, Histogram, Gauge

msg_processed = Counter('load_test_messages_processed', '')
latency_hist = Histogram('load_test_latency_ms', '', buckets=...)
concurrent_gauge = Gauge('load_test_concurrent_tasks', '')
```

### 2. 分布式压测

```python
# 多进程或多机压测
from multiprocessing import Pool

def run_load_test(config):
    test = LoadTest(config)
    return test.run()

with Pool(4) as p:
    results = p.map(run_load_test, [config1, config2, config3, config4])
```

### 3. 持久化历史数据

```python
# SQLite 保存历史记录
import sqlite3
conn = sqlite3.connect('load_test_history.db')
conn.execute("""
    INSERT INTO results VALUES (?, ?, ?, ...)
    (timestamp, throughput, p95_latency, ...)
""")
```

---

## ✅ 设计原则

1. **真实性**: 模拟真实的消息处理流程和分布
2. **可重复性**: 确定性的随机种子和参数配置
3. **可扩展性**: 易于添加新的测试场景和指标
4. **可观测性**: 详细的日志和多维度指标
5. **易用性**: 简单的命令行接口和自动报告

---

## 🎓 学习路径

1. **基础**: 理解单消息处理流程和各阶段延迟
2. **进阶**: 理解信号量、队列、并发控制原理
3. **优化**: 识别瓶颈，提出优化方案
4. **监控**: 集成外部监控工具，设置告警
5. **运维**: 定期压测、性能趋势分析、容量规划

---

**最后更新**: 2026-03-29

