# 📊 Prometheus 集成 - 完整监控方案

> 现在压测脚本可以上报指标到 Prometheus，在 Grafana 中实时展示！

## 🎯 完整的监控链路

```
压测脚本
  ↓ (每条消息处理时上报指标)
Prometheus 格式文本
  ↓ (push_to_gateway)
Prometheus PushGateway (localhost:9091)
  ↓ (scrape)
Prometheus Server (localhost:9090)
  ↓ (query)
Grafana 仪表板 (localhost:3000)
  ↓
📊 实时展示所有指标!
```

---

## 🚀 快速开始

### Step 1: 启动 Prometheus 和 Grafana（Docker）

```bash
# 启动 PushGateway、Prometheus、Grafana
docker-compose up -d prometheus pushgateway grafana
```

### Step 2: 运行带 Prometheus 上报的压测

```bash
# 基础命令（模拟 LLM）
python tests/load_test_prometheus_export.py \
  --channels 5 \
  --messages 5 \
  --concurrent 3 \
  --prometheus localhost:9091

# 真实 LLM（需要 API Key）
export OPENAI_API_KEY="sk-..."
python tests/load_test_prometheus_export.py \
  --channels 10 \
  --messages 10 \
  --concurrent 5 \
  --api-key $OPENAI_API_KEY \
  --prometheus localhost:9091
```

### Step 3: 查看 Grafana 仪表板

打开浏览器访问 `http://localhost:3000`
- 用户名: admin
- 密码: admin

选择 "NBA 2K26 Bot 系统监控" 仪表板 → 看到实时数据！

---

## 📈 压测脚本上报的指标

### 计数器 (Counter)

```
# LLM 调用计数
discord_bot_llm_calls_total{model="gpt-3.5-turbo",status="success"} 15
discord_bot_llm_calls_total{model="gpt-3.5-turbo",status="error"} 0

# 消息处理计数
discord_bot_messages_processed_total{source="cache_hit"} 10
discord_bot_messages_processed_total{source="llm_call"} 15

# 缓存命中计数
discord_bot_cache_hits_total 10

# 错误计数
discord_bot_llm_errors_total{error_type="timeout"} 0
discord_bot_llm_errors_total{error_type="exception"} 0
```

### 仪表 (Gauge)

```
# 缓存命中率
discord_bot_cache_hit_ratio 0.4

# 并发数
discord_bot_concurrent_messages_current 0
discord_bot_concurrent_messages_peak 3

# 吞吐量
discord_bot_throughput_msg_per_sec 15.59
```

### 直方图 (Histogram)

```
# LLM 调用延迟
discord_bot_llm_call_duration_seconds_sum 1.52
discord_bot_llm_call_duration_seconds_count 15

# 消息处理总延迟
discord_bot_message_processing_duration_seconds_sum 1.04
discord_bot_message_processing_duration_seconds_count 25
```

---

## 🔄 数据流

### 每条消息处理时

```
message_processor() 执行
  ├─ 并发数 +1
  ├─ 缓存查询
  │   └─ 上报: cache_lookup_duration_seconds
  │
  ├─ IF 缓存命中:
  │   ├─ 上报: cache_hits_total +1
  │   ├─ 上报: messages_processed_total{source="cache_hit"} +1
  │   └─ 上报: message_processing_duration_seconds
  │
  └─ ELSE 缓存未命中:
      ├─ 调用 LLM
      │   └─ 上报: llm_call_duration_seconds
      ├─ 上报: llm_calls_total{status="success"} +1
      ├─ DB 写入
      │   └─ 上报: db_write_duration_seconds
      ├─ 上报: messages_processed_total{source="llm_call"} +1
      └─ 上报: message_processing_duration_seconds

  最后:
  ├─ 上报: concurrent_messages_current -1
  └─ push_to_gateway() 一次性上报全部指标
```

---

## 📊 Grafana 仪表板配置

### 仪表板 4 个面板

#### 1. CPU 使用率 (%)

```promql
# PromQL 查询
rate(node_cpu_seconds_total{mode!="idle"}[5m]) * 100
```

#### 2. 内存使用 (MB)

```promql
# PromQL 查询
node_memory_MemAvailable_bytes / 1024 / 1024
```

#### 3. 消息处理数 (直方图)

```promql
# PromQL 查询
sum(discord_bot_messages_processed_total)
```

#### 4. LLM 调用延迟 (ms)

```promql
# PromQL 查询
discord_bot_llm_call_duration_seconds * 1000
```

---

## 🛠 完整的运行流程

### 方式 1: 模拟 LLM（快速测试）

```bash
cd /Users/zhaowentao/IdeaProjects/discord-agent-openclaw-based

# 运行压测（会自动上报到 PushGateway）
python tests/load_test_prometheus_export.py \
  --channels 5 \
  --messages 5 \
  --concurrent 3 \
  --prometheus localhost:9091

# 预期输出:
# ✓ Prometheus 指标已上报到 http://localhost:9091
```

### 方式 2: 真实 LLM（完整测试）

```bash
# 配置 API Key
export OPENAI_API_KEY="sk-xxx..."

# 运行压测（会上报到 PushGateway）
python tests/load_test_prometheus_export.py \
  --channels 10 \
  --messages 10 \
  --concurrent 5 \
  --api-key $OPENAI_API_KEY \
  --model "gpt-3.5-turbo" \
  --prometheus localhost:9091

# 预期输出:
# ✓ Prometheus 指标已上报到 http://localhost:9091
```

---

## 🔍 验证指标上报

### 方式 1: 直接查看 PushGateway

```bash
curl http://localhost:9091/metrics
```

**输出示例**:
```
# HELP discord_bot_llm_calls_total Total LLM API calls
# TYPE discord_bot_llm_calls_total counter
discord_bot_llm_calls_total{model="gpt-3.5-turbo",status="success"} 15
discord_bot_llm_calls_total{model="gpt-3.5-turbo",status="error"} 0

# HELP discord_bot_messages_processed_total Total messages processed
# TYPE discord_bot_messages_processed_total counter
discord_bot_messages_processed_total{source="cache_hit"} 10
discord_bot_messages_processed_total{source="llm_call"} 15

# HELP discord_bot_cache_hit_ratio Cache hit ratio (0-1)
# TYPE discord_bot_cache_hit_ratio gauge
discord_bot_cache_hit_ratio 0.4

# HELP discord_bot_throughput_msg_per_sec Throughput (msg/s)
# TYPE discord_bot_throughput_msg_per_sec gauge
discord_bot_throughput_msg_per_sec 15.59

...
```

### 方式 2: Prometheus UI

访问 `http://localhost:9090` → 选择指标查询

```
# 查询所有压测指标
{job="discord_bot_load_test"}

# 查询 LLM 调用成功率
rate(discord_bot_llm_calls_total{status="success"}[5m])

# 查询缓存命中率
discord_bot_cache_hit_ratio
```

### 方式 3: Grafana 仪表板

访问 `http://localhost:3000` → 打开 "NBA 2K26 Bot 系统监控" → 看到所有图表

---

## 📋 完整的指标清单

### 计数器

| 指标名 | 说明 | 标签 |
|------|------|------|
| `discord_bot_llm_calls_total` | LLM 总调用数 | model, status |
| `discord_bot_messages_processed_total` | 消息处理总数 | source |
| `discord_bot_cache_hits_total` | 缓存命中总数 | - |
| `discord_bot_llm_errors_total` | LLM 错误总数 | error_type |

### 仪表

| 指标名 | 说明 |
|------|------|
| `discord_bot_cache_hit_ratio` | 缓存命中率 (0-1) |
| `discord_bot_concurrent_messages_current` | 当前并发数 |
| `discord_bot_concurrent_messages_peak` | 峰值并发数 |
| `discord_bot_throughput_msg_per_sec` | 吞吐量 (msg/s) |

### 直方图

| 指标名 | 说明 |
|------|------|
| `discord_bot_llm_call_duration_seconds` | LLM 调用延迟 |
| `discord_bot_message_processing_duration_seconds` | 消息处理总延迟 |
| `discord_bot_cache_lookup_duration_seconds` | 缓存查询延迟 |
| `discord_bot_db_write_duration_seconds` | 数据库写入延迟 |

---

## 🎬 实时监控效果

运行压测后，Grafana 仪表板会显示：

### 【CPU 使用率】
```
┌─────────────────────────────────┐
│  CPU使用率(%)                   │
│                                 │
│    ▂▂▂▄▆██▆▄▂ (实时波形)       │
│    平均: 15%                    │
│    峰值: 45%                    │
└─────────────────────────────────┘
```

### 【内存使用】
```
┌─────────────────────────────────┐
│  内存使用(MB)                   │
│                                 │
│    ▁▁▂▂▃▃▄▄▅▅▆▆ (实时数据)     │
│    当前: 512MB                  │
│    峰值: 768MB                  │
└─────────────────────────────────┘
```

### 【消息处理数】
```
┌─────────────────────────────────┐
│  消息处理                       │
│                                 │
│  ✓ 缓存命中: 10 (40%)           │
│  ✓ LLM调用: 15 (60%)            │
│  ❌ 错误: 0                      │
└─────────────────────────────────┘
```

### 【LLM 调用延迟】
```
┌─────────────────────────────────┐
│  LLM调用延迟(ms)                │
│                                 │
│    100│  ▁    ▄                 │
│       │ ▄█▄  ▄█▄  ▄ ▄           │
│    50│▄█ █▄▄█ █▄▄█ █▄▄          │
│       │█                        │
│     0└─────────────────────→    │
│      时间 →                     │
│    平均: 101ms                  │
│    P95: 105ms                   │
└─────────────────────────────────┘
```

---

## ✅ 完整的 Prometheus 集成完成

✅ 压测脚本上报指标到 PushGateway
✅ Prometheus 抓取和存储指标
✅ Grafana 实时展示仪表板
✅ 所有性能指标可观测
✅ 完整的链路监控

**现在 Grafana 仪表板会显示实时的压测数据！** 📊

