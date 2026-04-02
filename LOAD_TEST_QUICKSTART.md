# ⚡ 压测快速开始 (2 分钟)

> 快速启动并发压测，验证 Discord Bot 50+ 频道并发性能

---

## 📋 一句话命令

```bash
cd /path/to/discord-agent-openclaw-based
python tests/load_test_simple.py --channels 50 --messages 100
```

**预期输出** (2-3 分钟后):
```
🚀 开始压测: 50 频道, 100 条/频道
✅ 已提交 5000 条消息到队列
========================================================
📊 压测结果
========================================================
总消息: 5000
成功: 5000
耗时: 110.25s
吞吐量: 45.32 msg/s ✅
平均延迟: 520.15ms
P95 延迟: 890.32ms ✅
峰值并发: 20 ✅
缓存命中: 12.0%
========================================================
```

---

## 🎯 三种常见场景

### 场景 1: 快速检查 (30 秒)

```bash
python tests/load_test_simple.py --channels 10 --messages 30
```

**用途**: 开发阶段快速反馈

### 场景 2: 标准压测 (2 分钟)

```bash
python tests/load_test_simple.py --channels 50 --messages 100
```

**用途**: 日常性能基准

### 场景 3: 完整套件 (5 分钟)

```bash
python tests/run_all_tests.py
```

**用途**: 全面评估 + 生成报告

---

## 📊 关键指标速查

| 指标 | 目标 | 说明 |
|------|------|------|
| **吞吐量** | ≥ 40 msg/s | 越高越好，取决于处理时间和并发 |
| **P95 延迟** | ≤ 1000ms | 95% 请求在 1 秒内完成 |
| **峰值并发** | ≈ 20 | 应接近信号量值，验证限流生效 |
| **缓存命中** | ≥ 10% | 内存优化空间 |
| **错误率** | 0% | 不能有失败 |

---

## 🔍 快速诊断

### 吞吐量低 (< 30 msg/s) ❌

```bash
# 检查是否系统过载
top -p $(pgrep -f load_test)

# 尝试减少并发
python tests/load_test_simple.py --channels 20 --messages 50
```

### P95 延迟高 (> 1500ms) ⚠️

原因:
1. **LLM API 超时** → 检查 OpenAI 连接
2. **数据库慢** → SQLite 有竞争，考虑 asyncpg
3. **GC 停顿** → 增加处理器或批量操作

### 缓存命中低 (< 5%) 📉

```python
# 改进缓存键
# ❌ 当前: f"{channel}:latest"
# ✅ 改进: f"{channel}:{user_id}:recent_5"
```

---

## 🎓 理解输出

```
吞吐量: 45.32 msg/s
  ↓
  成功处理了 5000 条消息，用时 110 秒
  = 5000 / 110 = 45.45 msg/s

平均延迟: 520.15ms
  ↓
  每条消息平均耗时 520ms
  = 缓存查询 (10ms) + AI 处理 (500ms) + DB 写 (10ms)

P95 延迟: 890.32ms
  ↓
  95% 的消息 < 890ms 完成
  5% 的消息 > 890ms (长尾延迟，来自 LLM API)

峰值并发: 20
  ↓
  信号量限制生效 ✅
  同时最多处理 20 个消息
```

---

## 🚀 进阶用法

### 对标历史数据

```bash
# 第一次: 建立基准
python tests/load_test_simple.py --output baseline.json

# 之后: 与基准对比
python tests/load_test_simple.py --output current.json
python tests/analyze_results.py current.json --baseline baseline.json
```

**输出**:
```
✅ 吞吐量: 45.32 msg/s (基准: 44.5) [+1.8%] ✅
✅ P95 延迟: 890.32ms (基准: 900) [-1.1%] ✅
```

### 多场景对比

```bash
# 运行完整套件（包含 4 种场景）
python tests/run_all_tests.py

# 输出:
# 低并发: 吞吐量 120 msg/s, P95 600ms
# 中并发: 吞吐量 80 msg/s, P95 750ms
# 高并发: 吞吐量 45 msg/s, P95 900ms
# 极限并发: 吞吐量 30 msg/s, P95 1200ms ⚠️
```

### 实时监控

```bash
# 窗口 1: 运行压测
python tests/load_test_simple.py --channels 50 --messages 100

# 窗口 2: 实时监控系统资源
watch -n 1 'ps aux | grep load_test | grep -v grep'
```

---

## ⚙️ 配置参数

```bash
python tests/load_test_simple.py \
  --channels 50 \          # 频道数 (5-200)
  --messages 100 \         # 每个频道的消息数 (10-1000)
  --concurrent 20 \        # 并发限制 (1-100，通常固定 20)
  --output result.json     # 输出文件
```

---

## 📁 生成的文件

运行压测后会生成:

```
project_root/
├── load_test_result.json       # 原始数据 (可导入其他工具)
├── pressure_test_results.json  # 完整套件结果
└── pressure_test_report.md     # Markdown 报告
```

### 查看 JSON 结果

```bash
# 格式化显示
python -m json.tool load_test_result.json | less

# 提取吞吐量
python -c "import json; print(json.load(open('load_test_result.json'))['metrics']['throughput'])"
```

---

## 🔧 故障排除

### 错误: ModuleNotFoundError

```bash
# 安装依赖
pip install -r requirements.txt
```

### 错误: Permission denied

```bash
# 赋予执行权限
chmod +x tests/load_test_simple.py
```

### 错误: 无法连接到数据库

```bash
# 清理旧数据库
rm -f load_test_metrics.db

# 重新运行
python tests/load_test_simple.py
```

### 内存溢出 (OOM)

```bash
# 减少消息数
python tests/load_test_simple.py --channels 20 --messages 50
```

---

## 📈 性能基准 (参考值)

基于当前配置 (50 频道, 100 消息, 20 并发):

| 指标 | 值 | 状态 |
|------|-----|------|
| 吞吐量 | 40-50 msg/s | ✅ |
| 平均延迟 | 480-550ms | ✅ |
| P95 延迟 | 800-1000ms | ✅ |
| P99 延迟 | 1200-1500ms | ✅ |
| 峰值并发 | ≈20 | ✅ |
| 缓存命中 | 10-15% | ✅ |
| 错误率 | 0% | ✅ |

**达不到这些值？** → 检查系统资源、网络延迟、或代码问题

---

## ✅ 压测清单

在运行生产压测前:

- [ ] 系统空闲（无其他进程）
- [ ] 网络连接正常
- [ ] 磁盘空间充足 (> 5GB)
- [ ] 数据库已备份
- [ ] 记录基准线（首次）

压测完成后:

- [ ] 检查是否有错误
- [ ] 比对关键指标
- [ ] 保存结果文件
- [ ] 生成报告
- [ ] 分析性能趋势

---

## 🎓 下一步

1. **熟悉结果**: 运行几次，理解输出含义
2. **建立基准**: 保存第一次的结果作为参考
3. **回归测试**: 每周运行一次，监控性能
4. **优化**: 根据瓶颈进行代码优化
5. **告警**: 集成 Prometheus，设置告警规则

---

## 📚 详细文档

- [PRESSURE_TEST_GUIDE.md](PRESSURE_TEST_GUIDE.md) - 完整使用手册
- [CONCURRENCY_CALCULATION.md](CONCURRENCY_CALCULATION.md) - 并发计算原理
- [tests/README.md](tests/README.md) - 测试工具说明

---

**快速提示**: 首次运行可能较慢，第二次开始会用上缓存，结果更稳定。

**需要帮助?** 检查日志输出或查看完整指南。

