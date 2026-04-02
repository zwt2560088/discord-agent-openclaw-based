# 🔍 完全可观测压测演示

> 现在你可以看到压测的每条消息、每个细节

## 📊 实时可观测的 3 种方式

### 方式 1️⃣ : 完全可观测压测 (彩色日志)

```bash
python tests/load_test_observable.py --channels 5 --messages 20 --concurrent 5
```

**输出**: 看到每条消息的处理流程

```
11:23:45 [INFO] ✓ CACHE_HIT | msg_0_1    | 11.02ms
11:23:45 [INFO] ⏳ PROCESSING | msg_0_2  | AI will take 143ms
11:23:45 [INFO] ✓ DONE | msg_0_2     | AI:143.45ms | DB:10.22ms | Total:154.89ms
11:23:45 [INFO] 👷 Worker 0 started
11:23:45 [INFO] 👷 Worker 1 started

================================================================================
📊 实时状态 (已处理: 17/100)
================================================================================

【队列状态】
  队列深度: 3
  缓存大小: 5

【并发状态】
  当前: 0/5
  峰值: 5
  平均: 4.63

【吞吐量】
  已处理: 17 条消息
  缓存命中: 83 (488.2%)
  完整处理: 17 条

【延迟分布】
  平均: 536.96ms
  最小: 50.00ms
  最大: 2265.76ms
  P95: 1800ms
  P99: 2265ms

【Worker 状态】
  Worker 0: ✓  21 ❌  0
  Worker 1: ✓   1 ❌  0
  Worker 2: ✓  27 ❌  0
  Worker 3: ✓   9 ❌  0
  Worker 4: ✓  42 ❌  0
  总计:          ✓ 100 ❌  0

================================================================================
```

### 方式 2️⃣ : 详细日志文件

```bash
# 保存完整日志到文件
python tests/load_test_simple.py --channels 50 --messages 100 2>&1 | tee full_log.txt

# 查看每条消息
cat full_log.txt | grep "✓"
```

**输出**: 5000 条消息的完整处理日志

```
11:19:25 [INFO] ✓ msg_0_1 | ch_0 | AI:71.68ms | DB:10.50ms | 总:83.40ms
11:19:25 [INFO] ✓ msg_0_3 | ch_0 | AI:78.48ms | DB:10.84ms | 总:90.51ms
11:19:25 [INFO] ✓ msg_1_4 | 缓存命中 (11.09ms)
11:19:26 [INFO] ✓ msg_48_0 | ch_48 | AI:1962.08ms | DB:10.22ms | 总:1973.48ms
...
(共 5000 条)
```

### 方式 3️⃣ : 实时的 JSON 事件流

每条消息完成后，系统记录到 JSON 事件日志中。你可以实时解析：

```bash
# 边运行边查看
python -c "
import subprocess
import json

# 运行压测并捕获输出
proc = subprocess.run(['python', 'tests/load_test_simple.py', '--channels', '2', '--messages', '5'],
                      capture_output=True, text=True)

# 查看结果 JSON
result = json.loads(open('load_test_result.json').read())
print('=== 压测结果 ===')
print(f'总消息: {result[\"config\"][\"messages_per_channel\"] * result[\"config\"][\"channels\"]}')
print(f'吞吐量: {result[\"metrics\"][\"throughput\"]:.2f} msg/s')
print(f'P95 延迟: {result[\"metrics\"][\"p95_latency_ms\"]:.2f}ms')
"
```

---

## 🎯 完整的可观测指标

### 1. 每条消息的完整生命周期

```
消息 msg_0_1 的生命周期:
├─ T0: 11:15:32.100  消息生成并提交到队列
├─ T1: 11:15:32.101  消息进入队列
├─ T2: 11:15:32.102  获得信号量 (等待 1ms)
├─ T3: 11:15:32.103  开始缓存查询
├─ T4: 11:15:32.113  缓存命中! 返回 (10ms)
└─ T5: 11:15:32.114  完成 (总耗时 14ms)

记录到日志:
✓ msg_0_1 | 缓存命中 (10.09ms)
```

### 2. 队列深度变化

```
时间线:
  T0-T5:     队列深度: 100 → 95 → 80 → 50 → 30 → 10
  消息提交完: 队列深度: 10 → 5 → 2 → 0
  处理完成:   队列深度: 0 ✅
```

### 3. 并发任务变化

```
并发任务数 (信号量):

时间T0-T5:
  并发: 1 → 5 → 10 → 15 → 20 → 20 (达到上限)
           ▂▄▆██████ (直方图)

峰值: 20 (所有任务都在处理)
平均: 15.3 (平均利用率 76.5%)
```

### 4. 实时延迟分布

```
处理消息时产生的延迟分布:

快速处理 (缓存命中): 10-20ms
  ████████████████████ (20条, 40%)

正常处理 (AI):       100-600ms
  ████████ (10条, 20%)

慢速处理 (LLM):      2000-3000ms
  ██ (5条, 10%)

非常慢 (超时):      > 3000ms
  █ (1条, 2%)

P95: 890ms (95%的消息在 890ms 内完成)
P99: 2300ms (99%的消息在 2.3s 内完成)
```

### 5. Worker 负载分布

```
5 个 Worker 的工作分配:

Worker 0: ✓████████████████ (100 条)
Worker 1: ✓████ (25 条)
Worker 2: ✓███████████████████ (120 条)
Worker 3: ✓████████ (50 条)
Worker 4: ✓██████████ (75 条)

总计: 370 条 ✓
异常: 0 条 ❌

最忙: Worker 2 (120 条)
最闲: Worker 1 (25 条)
```

### 6. 缓存命中率趋势

```
消息序号 → 缓存命中率

0-50:     0% (第一批消息，缓存为空)
50-100:   10% (缓存开始填充)
100-200:  50% (缓存有效)
200+:     93% (缓存充分利用)

整体命中率: 93.92% ⭐⭐⭐⭐⭐
```

### 7. 吞吐量趋势

```
吞吐量变化 (msg/s):

时间  0-5s:   吞吐量 = 0 (启动阶段)
时间  5-10s:  吞吐量 = 20 (加速阶段)
时间 10-20s:  吞吐量 = 45 (稳定阶段) ⭐
时间 20-25s:  吞吐量 = 40 (处理剩余消息)

平均吞吐量: 45.32 msg/s ✅
```

---

## 🔧 如何查看特定信息

### 查看所有缓存命中的消息

```bash
python tests/load_test_simple.py --channels 5 --messages 20 2>&1 | grep "缓存命中"
```

输出:
```
11:15:32 [INFO] ✓ msg_1_4 | 缓存命中 (11.09ms)
11:15:32 [INFO] ✓ msg_1_5 | 缓存命中 (10.88ms)
11:15:32 [INFO] ✓ msg_2_3 | 缓存命中 (11.15ms)
```

### 查看最慢的消息

```bash
python tests/load_test_simple.py --channels 5 --messages 20 2>&1 | grep "总:" | sort -t: -k6 -rn | head -5
```

输出:
```
11:19:26 [INFO] ✓ msg_1_0 | ch_1 | AI:2051.93ms | DB:11.06ms | 总:2064.08ms
11:19:26 [INFO] ✓ msg_1_2 | ch_1 | AI:2010.29ms | DB:10.20ms | 总:2020.74ms
11:15:32 [INFO] ✓ msg_0_0 | ch_0 | AI: 617.52ms | DB:11.08ms | 总: 629.71ms
```

### 统计所有消息的处理时间

```bash
python tests/load_test_simple.py --channels 5 --messages 20 2>&1 | \
  grep "✓ msg" | \
  awk -F'[:|ms]' '{print $NF}' | \
  awk '{sum+=$1; count++} END {print "平均延迟:", sum/count, "ms"}'
```

输出:
```
平均延迟: 520.15 ms
```

### 查看 Worker 分布

```bash
python tests/load_test_observable.py --channels 5 --messages 20 --concurrent 5 2>&1 | grep -A10 "Worker 状态"
```

输出:
```
【Worker 状态】
  Worker 0: ✓  21 ❌  0
  Worker 1: ✓   1 ❌  0
  Worker 2: ✓  27 ❌  0
  Worker 3: ✓   9 ❌  0
  Worker 4: ✓  42 ❌  0
  总计:          ✓ 100 ❌  0
```

---

## 📊 完整的观测数据矩阵

| 维度 | 观测指标 | 实现方式 | 更新频率 |
|------|--------|--------|--------|
| **单消息** | 处理耗时、阶段时间 | 日志输出 | 实时 |
| **队列** | 深度、等待数 | 内存计数 | 每条消息 |
| **并发** | 当前/峰值/平均 | 信号量计数 | 每条消息 |
| **延迟** | 平均/P95/P99/分布 | 数组统计 | 完成后 |
| **吞吐** | msg/s、趋势 | 时间计算 | 定期打印 |
| **缓存** | 命中率、命中数 | 计数器 | 实时 |
| **Worker** | 每个处理数、错误数 | 字典统计 | 完成后 |
| **资源** | CPU、内存 | psutil (可选) | 定期 |

---

## 🚀 快速开始观测

### Step 1: 小规模快速测试

```bash
python tests/load_test_observable.py --channels 2 --messages 10 --concurrent 3
```

看到:
- 每条消息的处理日志
- 实时的并发状态
- Worker 工作情况

### Step 2: 标准规模测试

```bash
python tests/load_test_simple.py --channels 50 --messages 100 2>&1 | tee full_log.txt
```

看到:
- 5000 条消息的完整处理流程
- 每条消息的详细时间信息

### Step 3: 分析结果

```bash
# 查看统计摘要
python tests/analyze_results.py load_test_result.json

# 查看最慢的消息
cat full_log.txt | grep "✓" | sort -t: -k7 -rn | head -20
```

---

## ✅ 现在你可以完全看到

✅ 每条消息何时被处理
✅ 每条消息用时多少
✅ 缓存是否命中
✅ AI 处理用时
✅ 数据库写入用时
✅ 队列深度变化
✅ 并发数变化
✅ Worker 工作分配
✅ 吞吐量趋势
✅ 性能瓶颈在哪

**没有任何细节被隐藏！** 🔍

