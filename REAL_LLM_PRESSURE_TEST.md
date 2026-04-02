# 🚀 真实 LLM 调用压测方案

> 之前的压测是**模拟**的，现在提供真实调用 LLM 的方案

## 📊 两种压测对比

| 维度 | 模拟压测 | 真实 LLM 压测 |
|------|--------|------------|
| **LLM 调用** | ❌ 否 | ✅ 是 |
| **返回数据** | 模拟数据 | 真实 LLM 响应 |
| **延迟** | 固定 ~50-500ms | 真实 API 延迟 (秒级) |
| **成本** | 免费 | 需要 API 配额 |
| **调试价值** | 高 | 极高 |

---

## 🎯 真实 LLM 压测流程

```
消息队列 → Worker 1-N (并发处理)
  ↓
每条消息:
  1. 缓存查询 (5ms)
     ↓
  2. 缓存未命中 → 调用 LLM API (真实!)
     ├─ 发送请求 → OpenAI/DeepSeek
     ├─ 等待响应 (通常 1-5s)
     └─ 获取响应
     ↓
  3. 数据库写入 (10ms)
     ↓
  4. 更新缓存 (1ms)
     ↓
  5. 记录指标 (延迟、吞吐、P95 等)
```

---

## 🛠 使用方法

### 方式 1: 模拟 LLM（不需要 API Key）

```bash
# 5 频道 × 5 消息 × 3 并发 的模拟测试
python tests/load_test_real_llm.py --channels 5 --messages 5 --concurrent 3
```

**输出示例**:
```
🔍 真实 LLM 压测开始
频道: 5, 消息/频道: 5, 并发: 3
模式: 模拟 LLM

11:30:45 [INFO] ✓ LLM Call | What is the best Discord... | Response: Mock response | 100ms
11:30:45 [INFO] ✓ DONE | msg_0_0 | LLM:100ms | DB:10.1ms | Total:110.2ms
11:30:45 [INFO] ✓ CACHE_HIT | msg_1_0 | 5.0ms
...

【基础指标】
  总消息: 25
  缓存命中: 5
  LLM 调用: 20
  错误: 0
  成功率: 100.0%

【LLM 延迟分布】
  最小: 100ms
  平均: 150ms
  最大: 200ms
  P95: 180ms
  P99: 195ms

【总延迟分布】
  最小: 5ms (缓存命中)
  平均: 115ms
  最大: 210ms
  P95: 185ms
  P99: 200ms

【缓存效率】
  命中率: 20.0%
  缓存大小: 5

【吞吐量】
  总吞吐量: 1.25 msg/s
  总耗时: 20.00s
```

### 方式 2: 真实 OpenAI API

首先设置 API Key:

```bash
export OPENAI_API_KEY="sk-xxx..."
```

然后运行:

```bash
python tests/load_test_real_llm.py \
  --channels 10 \
  --messages 10 \
  --concurrent 5 \
  --api-key $OPENAI_API_KEY \
  --model "gpt-3.5-turbo"
```

**输出示例**:
```
🔍 真实 LLM 压测开始
频道: 10, 消息/频道: 10, 并发: 5
模式: 真实 LLM

11:30:45 [INFO] ✓ LLM Call | What is the best Discord... | Response: Discord bots are... | 2340ms
11:30:47 [INFO] ✓ DONE | msg_0_0 | LLM:2340ms | DB:10.5ms | Total:2351.1ms
11:30:47 [INFO] ✓ CACHE_HIT | msg_1_0 | 5.0ms
11:30:50 [INFO] ✓ LLM Call | What is the best Discord... | Response: The key to... | 2680ms
...

【基础指标】
  总消息: 100
  缓存命中: 15
  LLM 调用: 85
  错误: 2
  成功率: 98.0%

【LLM 调用统计】
  总调用: 85
  平均时间: 2456ms (2.456秒)
  总耗时: 208.8s
  错误: 2

【LLM 延迟分布】
  最小: 1850ms
  平均: 2456ms
  最大: 5230ms
  P95: 4100ms
  P99: 4800ms

【总延迟分布】
  最小: 5ms (缓存命中)
  平均: 2100ms
  最大: 5240ms
  P95: 4110ms
  P99: 4810ms

【缓存效率】
  命中率: 15.0%
  缓存大小: 10

【吞吐量】
  总吞吐量: 0.49 msg/s (注: 受 LLM 延迟限制)
  总耗时: 204.27s
```

### 方式 3: 真实 DeepSeek API

```bash
export DEEPSEEK_API_KEY="sk-xxx..."

python tests/load_test_real_llm.py \
  --channels 20 \
  --messages 20 \
  --concurrent 10 \
  --api-key $DEEPSEEK_API_KEY \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat"
```

---

## 📊 关键观测指标解释

### LLM 调用统计

```
总调用: 85 次
  └─ 这是真实调用 LLM API 的次数（不包括缓存命中）

平均时间: 2456ms (2.456秒)
  └─ 每次 API 调用平均耗时

总耗时: 208.8s
  └─ 所有 LLM 调用加起来的时间

错误: 2 次
  └─ API 超时、网络错误或限流
```

### 延迟分布理解

```
【缓存命中】 5ms
  └─ 最快的情况（直接返回缓存）

【AI 处理】 2456ms (平均)
  └─ 调用 LLM 的时间

【数据库】 10.5ms
  └─ 写入数据库的时间

【总延迟】 2467ms (平均)
  = 缓存检查 + LLM 调用 + DB 写入 + 其他开销
```

### 吞吐量理解

```
真实 LLM 吞吐量: 0.49 msg/s

为什么这么低?
  100 条消息 / 204 秒 = 0.49 msg/s

  原因分析:
  - LLM API 延迟长 (平均 2.5 秒)
  - 只有 10 个并发
  - 10 个并发 × 2.5 秒 = 最多 4 条/秒
  - 但实际受网络、处理等限制，所以 0.49 msg/s

如何提升吞吐?
  1. 增加并发数: --concurrent 50 (如果 LLM API 支持)
  2. 优化缓存: 提高缓存命中率 (减少 LLM 调用)
  3. 使用更快的 LLM: gpt-4-turbo 可能更快
  4. 增加消息数: 让系统稳定在吞吐峰值
```

---

## 🔍 真实数据流的完整观测

### 单条消息的完整生命周期

```
Message: msg_0_0
Content: "What is the best Discord bot strategy?"

T0: 11:30:45.100  消息进入队列
T1: 11:30:45.102  获得信号量 (等待时间: 2ms)
T2: 11:30:45.103  开始缓存查询
T3: 11:30:45.108  缓存未命中 (缓存查询: 5ms)

T4: 11:30:45.109  发送 LLM 请求到 OpenAI
    请求内容:
    {
      "model": "gpt-3.5-turbo",
      "messages": [
        {"role": "system", "content": "You are a helpful Discord bot..."},
        {"role": "user", "content": "What is the best Discord bot strategy?"}
      ]
    }

T5-T7: 11:30:47.450  等待 LLM 响应 (耗时: 2341ms)
    响应内容:
    {
      "choices": [{
        "message": {
          "content": "Discord bots can be enhanced with AI by using..."
        }
      }]
    }

T8: 11:30:47.451  开始数据库写入
T9: 11:30:47.461  数据库写入完成 (DB 时间: 10ms)

T10: 11:30:47.462  更新缓存
T11: 11:30:47.462  完成

总耗时: 2362ms
  = 缓存查询(5ms) + LLM调用(2341ms) + DB写入(10ms) + 开销(6ms)

日志输出:
11:30:45 [INFO] ✓ LLM Call | What is the best Discord... | Response: Discord bots can be... | 2341ms
11:30:47 [INFO] ✓ DONE | msg_0_0 | LLM:2341ms | DB:10.0ms | Total:2362.0ms
```

### 缓存命中 vs 未命中对比

```
【缓存未命中】消息 msg_0_0
T0: 11:30:45.100  进入队列
T1-T11: 2362ms   处理时间
    └─ 缓存查询: 5ms
    └─ LLM 调用: 2341ms ⭐ 最长
    └─ DB 写入: 10ms
    └─ 开销: 6ms

【缓存命中】消息 msg_1_0 (同频道的第二条)
T0: 11:30:47.500  进入队列
T1-T2: 7ms       处理时间
    └─ 缓存查询: 5ms
    └─ 直接返回

吞吐提升: 2362ms / 7ms = 337 倍!
    → 这就是为什么缓存命中率很关键
```

---

## 🎬 测试场景

### 场景 1: 冷启动 (缓存空)

```bash
python tests/load_test_real_llm.py \
  --channels 5 \
  --messages 5 \
  --concurrent 3 \
  --api-key $OPENAI_API_KEY
```

**预期结果**:
- 缓存命中率: 0% (所有消息都调用 LLM)
- 吞吐量: 较低 (受 LLM 延迟限制)
- 总耗时: 较长

### 场景 2: 热启动 (缓存热)

```bash
# 第一轮: 填充缓存
python tests/load_test_real_llm.py \
  --channels 10 \
  --messages 1 \
  --concurrent 10 \
  --api-key $OPENAI_API_KEY

# 第二轮: 缓存命中
python tests/load_test_real_llm.py \
  --channels 10 \
  --messages 10 \
  --concurrent 10 \
  --api-key $OPENAI_API_KEY
```

**预期结果**:
- 缓存命中率: ~90% (大量缓存命中)
- 吞吐量: 极高 (缓存直接返回)
- 总耗时: 极短

### 场景 3: 混合 (部分缓存)

```bash
python tests/load_test_real_llm.py \
  --channels 50 \
  --messages 10 \
  --concurrent 20 \
  --api-key $OPENAI_API_KEY
```

**预期结果**:
- 缓存命中率: ~50% (按消息顺序，第二次及以后命中)
- 吞吐量: 中等
- P95 延迟: 混合 (缓存快 + LLM 慢)

---

## 💾 数据流完整追踪

### 消息到达时的数据结构

```python
message = {
    "channel": "ch_0",
    "message_id": "msg_0_0",
    "content": "What is the best Discord bot strategy for channel ch_0?"
}
```

### 处理前的缓存查询

```python
cache_key = "ch_0:latest"
if cache_key in self.cache:
    # 缓存命中 → 直接返回
    response = self.cache[cache_key]
else:
    # 缓存未命中 → 调用 LLM
    response = await self.llm_client.chat(message['content'], session)
```

### LLM 返回的数据

```json
{
  "id": "chatcmpl-8xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-3.5-turbo",
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 120,
    "total_tokens": 145
  },
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Discord bots can leverage AI to provide better user experiences by..."
    },
    "finish_reason": "stop",
    "index": 0
  }]
}
```

### 存储到缓存和数据库

```python
# 更新缓存
self.cache[cache_key] = {
    'response': response,
    'timestamp': datetime.now().isoformat(),
    'model': 'gpt-3.5-turbo',
    'tokens': 145
}

# 数据库记录
db_record = {
    'message_id': 'msg_0_0',
    'channel': 'ch_0',
    'request': "What is the best Discord bot strategy?",
    'response': response,
    'llm_model': 'gpt-3.5-turbo',
    'processing_time_ms': 2362,
    'cache_hit': False,
    'timestamp': datetime.now()
}
```

---

## 🚨 错误和异常追踪

### 网络超时

```
Timeout 发生:
  - 等待 LLM 响应超过 30 秒
  - 系统自动记录错误
  - 继续处理下一条消息

日志输出:
❌ LLM Timeout | msg_0_5 | What is the best Discord...
  错误计数 +1
```

### API 限流 (429)

```
限流发生:
  - OpenAI 返回 429 Too Many Requests
  - 当前默认不重试，记录为错误

日志输出:
❌ LLM Error | Status: 429 | {
  "error": {
    "message": "Rate limit exceeded",
    "type": "rate_limit_error"
  }
}
  错误计数 +1
```

### 认证错误 (401)

```
认证失败:
  - API Key 无效或过期
  - 系统终止测试

日志输出:
❌ LLM Error | Status: 401 | {
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error"
  }
}
```

---

## 📈 性能对标

### 预期性能指标

| 指标 | 模拟压测 | 真实 LLM (3.5-turbo) | 真实 LLM (4-turbo) |
|------|--------|------------------|---------------|
| 平均延迟 | 200ms | 2500ms | 1800ms |
| P95 延迟 | 500ms | 4000ms | 2500ms |
| 吞吐量 | 5+ msg/s | 0.5 msg/s | 0.8 msg/s |
| 缓存命中 | 80% | 15% (取决于) | 15% (取决于) |
| 错误率 | 0% | 0-2% | 0-1% |

---

## ✅ 现在你知道

✅ 压测之前是**模拟的**
✅ 现在提供了**真实 LLM 调用**版本
✅ 可以观测每条消息的完整生命周期
✅ 可以看到 LLM 的真实延迟
✅ 可以看到缓存命中对吞吐的影响
✅ 可以追踪错误和异常
✅ 可以对标不同模型的性能

现在开始真实压测吧！ 🚀

