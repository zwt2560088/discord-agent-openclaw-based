# 🔥 Discord Bot 并发压测套件

完整的并发性能压测工具，用于验证 Discord 机器人在 50+ 频道并发场景下的表现。

## 📦 包含内容

```
tests/
├── load_test_simple.py          # 消息处理压测（核心）
├── load_test_http.py            # HTTP 连接池压测
├── load_test_core.py            # 数据结构定义
├── run_all_tests.py             # 完整压测套件运行器
├── analyze_results.py           # 结果分析工具
└── README.md                    # 本文件
```

## 🚀 快速开始

### 1️⃣ 最简单的压测 (30 秒)

```bash
cd /path/to/discord-agent-openclaw-based
python tests/load_test_simple.py --channels 10 --messages 50
```

### 2️⃣ 标准压测 (2 分钟)

```bash
python tests/load_test_simple.py --channels 50 --messages 100 --concurrent 20
```

### 3️⃣ 完整压测套件 (5 分钟)

```bash
python tests/run_all_tests.py
```

这会生成:
- `message_load_test.json` - 消息处理结果
- `http_load_test.json` - HTTP 连接池结果
- `pressure_test_results.json` - 完整结果
- `pressure_test_report.md` - Markdown 报告

### 4️⃣ 分析结果

```bash
# 查看摘要
python tests/analyze_results.py message_load_test.json

# 与基准对比
python tests/analyze_results.py current.json --baseline baseline.json

# 分析多场景
python tests/analyze_results.py pressure_test_results.json --scenarios
```

## 🎯 三类压测说明

| 工具 | 用途 | 耗时 | 场景 |
|------|------|------|------|
| `load_test_simple.py` | 消息处理并发 | 2-5 分钟 | 50+ 频道消息 |
| `load_test_http.py` | 连接池测试 | 1-2 分钟 | Discord API 并发调用 |
| `run_all_tests.py` | 完整套件 | 5-10 分钟 | 多场景对比 |

### 消息处理压测

**模拟场景**: 50 个频道同时发送消息

```bash
python load_test_simple.py \
  --channels 50 \
  --messages 100 \
  --concurrent 20 \
  --output result.json
```

**输出**:
```
吞吐量: 45.32 msg/s
平均延迟: 520.15ms
P95 延迟: 890.32ms
峰值并发: 20
```

### HTTP 连接池压测

**模拟场景**: aiohttp 连接池在 Discord API 中的表现

```bash
python load_test_http.py \
  --channels 50 \
  --requests 20 \
  --pool-size 100 \
  --per-host 30 \
  --output http_result.json
```

## 📊 关键指标解读

### 吞吐量 (Throughput)

```
吞吐量 = 成功消息 / 总耗时

目标: ≥ 40 msg/s
理论值: 20 并发 × (1/0.5s) = 40 msg/s
```

### 延迟 (Latency)

```
平均延迟  : 大多数消息的处理时间
P95 延迟  : 95% 的消息在这个时间内完成
P99 延迟  : 99% 的消息在这个时间内完成（尾部延迟）

目标:
- 平均: ~500ms (受 AI 处理时间影响)
- P95: < 1000ms
- P99: < 1500ms
```

### 并发 (Concurrency)

```
峰值并发应该接近信号量值 (20)
说明信号量生效，防止资源耗尽
```

### 缓存命中率 (Cache Hit Ratio)

```
命中率 = 缓存命中 / 总消息 × 100%

目标: ≥ 10%
优化方向: 扩大缓存键（不仅限最新消息）
```

## 🔧 自定义压测

### 场景 1: 低并发压力测试

```bash
python load_test_simple.py --channels 10 --messages 50 --concurrent 5
```

**预期**:
- 吞吐量: ~100 msg/s (低竞争)
- 延迟: ~400ms (快速处理)

### 场景 2: 高并发压力测试

```bash
python load_test_simple.py --channels 100 --messages 100 --concurrent 20
```

**预期**:
- 吞吐量: ~30 msg/s (队列等待)
- 延迟: ~1200ms (竞争激烈)
- ⚠️ 可能出现内存问题或超时

### 场景 3: 长期稳定性测试

```bash
python load_test_simple.py --channels 30 --messages 500 --concurrent 20
```

**验证**:
- 无内存泄漏
- 吞吐量稳定
- 无僵尸进程

## 📈 解读压测报告

### 完整报告示例

```markdown
# 🔥 Discord Bot 并发压测报告

## 📊 执行摘要

### 1️⃣ 消息处理并发压测

| 指标 | 值 |
|------|-----|
| 总消息 | 5000 |
| 成功 | 5000 (100%) |
| 吞吐量 | 45.32 msg/s ✅ |
| 平均延迟 | 520.15ms |
| P95 延迟 | 890.32ms ✅ |
| 缓存命中率 | 12.0% |

### 2️⃣ HTTP 连接池压测

| 指标 | 值 |
|------|-----|
| 总请求 | 1000 |
| 成功 | 1000 (100%) |
| 吞吐量 | 85.5 req/s ✅ |
| 平均延迟 | 250.4ms |
| P99 延迟 | 650.2ms ✅ |
```

## 🐛 常见问题

### Q: 压测运行很慢？

A: 默认 Poisson 分布模拟真实请求，如果只想测速度：

```bash
python load_test_simple.py --channels 50 --messages 50 --concurrent 20
```

### Q: 内存使用过高？

A: 减少频道数或消息数：

```bash
python load_test_simple.py --channels 20 --messages 50
```

### Q: 想测试极限？

A: 逐步增加并发：

```bash
python load_test_simple.py --channels 100 --messages 200 --concurrent 50
```

⚠️ 注意: 峰值可能会失败，观察崩溃点

### Q: 如何持续监控？

A: 集成 Prometheus:

```python
# 在压测中导出指标
from prometheus_client import start_http_server
start_http_server(8000)  # 暴露 /metrics 端点
```

## ✅ 压测前检查清单

- [ ] 关闭其他应用（确保系统干净）
- [ ] 充足磁盘空间 (> 5GB)
- [ ] Python >= 3.8
- [ ] 依赖已安装: `pip install -r requirements.txt`
- [ ] 网络连接稳定
- [ ] 无系统后台任务 (更新、扫描等)

## 📚 更多资料

详见主文档:
- [PRESSURE_TEST_GUIDE.md](../PRESSURE_TEST_GUIDE.md) - 完整使用指南
- [CONCURRENCY_CALCULATION.md](../CONCURRENCY_CALCULATION.md) - 并发计算原理

## 🤝 贡献

如有改进建议，欢迎提交 PR！

---

**最后更新**: 2026-03-29

