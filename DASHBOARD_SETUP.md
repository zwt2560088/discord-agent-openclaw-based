# 📊 Grafana Dashboard 完整设置指南

> 如果你看不到仪表板，按照这个指南一步步启动

---

## 🎯 5 分钟快速启动

### 方式 1: 自动启动脚本（推荐）

```bash
cd /Users/zhaowentao/IdeaProjects/discord-agent-openclaw-based

# 给脚本执行权限
chmod +x start-monitoring.sh

# 启动监控栈
./start-monitoring.sh
```

### 方式 2: 手动 Docker Compose

```bash
cd /Users/zhaowentao/IdeaProjects/discord-agent-openclaw-based

# 启动 Prometheus、PushGateway、Grafana、AlertManager
docker compose up -d prometheus pushgateway alertmanager grafana

# 查看日志
docker compose logs -f grafana
```

---

## 📊 访问仪表板

### Step 1: 打开 Grafana

访问 `http://localhost:3000`

**默认登陆信息:**
- 用户名: `admin`
- 密码: `admin`

### Step 2: 添加 Prometheus 数据源

1. 点击左侧菜单 → Configuration → Data Sources
2. 点击 "Add data source"
3. 选择 "Prometheus"
4. URL 设置为: `http://prometheus:9090` (Docker) 或 `http://localhost:9090` (本机)
5. 点击 "Save & Test"

### Step 3: 导入仪表板

1. 左侧菜单 → Dashboards → Import
2. 上传文件: `grafana/provisioning/dashboards/basketball-bot-dashboard.json`
3. 或者粘贴 JSON 内容
4. 选择 Prometheus 作为数据源
5. 点击 "Import"

### Step 4: 查看实时数据

现在你应该看到 "NBA 2K26 Bot 系统监控" 仪表板，包含 5 个面板：
- 🚀 吞吐量 (msg/s)
- ⏱️ LLM 调用延迟 (ms)
- 📊 消息处理分布 (缓存命中 vs LLM 调用)
- 💾 缓存命中率 (%)
- ✅ LLM 调用成功率

---

## 🧪 运行压测并查看数据

### 基础压测（模拟 LLM）

```bash
python tests/load_test_prometheus_export.py \
  --channels 5 \
  --messages 5 \
  --concurrent 3 \
  --prometheus localhost:9091
```

**预期:**
- 脚本会上报指标到 PushGateway
- Prometheus 会抓取这些指标
- Grafana 仪表板会显示实时数据

### 完整压测（50 频道）

```bash
python tests/load_test_prometheus_export.py \
  --channels 50 \
  --messages 100 \
  --concurrent 20 \
  --prometheus localhost:9091
```

### 真实 LLM 压测

```bash
export OPENAI_API_KEY="sk-..."

python tests/load_test_prometheus_export.py \
  --channels 10 \
  --messages 10 \
  --concurrent 5 \
  --api-key $OPENAI_API_KEY \
  --prometheus localhost:9091
```

---

## 🔍 验证数据流

### 1. 检查 PushGateway

```bash
curl http://localhost:9091/metrics
```

应该看到类似的输出:
```
# HELP discord_bot_llm_calls_total Total LLM API calls
# TYPE discord_bot_llm_calls_total counter
discord_bot_llm_calls_total{model="gpt-3.5-turbo",status="success"} 15

# HELP discord_bot_cache_hit_ratio Cache hit ratio (0-1)
# TYPE discord_bot_cache_hit_ratio gauge
discord_bot_cache_hit_ratio 0.6
```

### 2. 检查 Prometheus

访问 `http://localhost:9090`

在查询框输入:
```
discord_bot_throughput_msg_per_sec
```

点击 "Execute"，应该看到实时数据

### 3. 检查 Grafana

访问 `http://localhost:3000` → 打开你的仪表板

应该看到 5 个实时图表更新

---

## ⚙️ 完整的监控架构

```
【压测脚本】
  ↓
【Prometheus PushGateway】 (localhost:9091)
  ↓
【Prometheus Server】 (localhost:9090)
  ↓
【Grafana】 (localhost:3000)
  ↓
【实时仪表板】 ✅
```

---

## 🛠️ 故障排除

### 问题 1: Grafana 看不到数据

**检查清单:**
1. ✅ Docker 容器是否都启动了?
   ```bash
   docker ps | grep -E "prometheus|pushgateway|grafana"
   ```

2. ✅ Prometheus 能否连接到 PushGateway?
   ```bash
   curl http://localhost:9091/metrics
   ```

3. ✅ Grafana 数据源是否配置正确?
   - 访问 http://localhost:3000
   - Configuration → Data Sources → Prometheus
   - 检查 URL 是否正确

### 问题 2: 压测脚本上报失败

```
⚠️ 无法上报到 Prometheus: ...
```

**解决:**
```bash
# 检查 PushGateway 是否运行
docker ps | grep pushgateway

# 检查是否能访问
curl -v http://localhost:9091/metrics
```

### 问题 3: Prometheus 看不到指标

**检查:**
```bash
# 1. 访问 Prometheus UI
open http://localhost:9090

# 2. 在 Status → Targets 中查看
# 应该看到 pushgateway 和 discord_bot_load_test 的 job

# 3. 查看 Query 页面
# 输入: {job="discord_bot_load_test"}
```

### 问题 4: Docker 容器无法启动

```bash
# 查看日志
docker compose logs prometheus
docker compose logs grafana
docker compose logs pushgateway

# 尝试重启
docker compose down
docker compose up -d prometheus pushgateway alertmanager grafana
```

---

## 📈 仪表板详解

### 面板 1: 吞吐量 (msg/s)
显示每秒处理的消息数，越高越好

### 面板 2: LLM 调用延迟 (ms)
显示调用 LLM 的响应时间，越低越好

### 面板 3: 消息处理分布
显示缓存命中 vs LLM 调用的比例
- 缓存命中: 快速返回（5ms）
- LLM 调用: 完整处理（100-2000ms）

### 面板 4: 缓存命中率 (%)
显示缓存的有效性，越高越好（表示系统复用性强）

### 面板 5: LLM 调用成功率
显示 LLM 调用的成功/失败比例，应该是 100% 成功

---

## 🚀 完整的工作流程

### 场景: 我想看完整的实时压测

```bash
# Step 1: 启动监控栈
./start-monitoring.sh

# Step 2: 打开 Grafana
open http://localhost:3000
# 登陆: admin/admin
# 打开 "NBA 2K26 Bot 系统监控" 仪表板

# Step 3: 运行压测
python tests/load_test_prometheus_export.py \
  --channels 20 \
  --messages 100 \
  --concurrent 10 \
  --prometheus localhost:9091

# Step 4: 观看实时数据
# Grafana 仪表板会实时更新，显示:
# ✓ 吞吐量增长
# ✓ 延迟变化
# ✓ 缓存命中率
# ✓ LLM 调用成功率
```

---

## ✅ 现在你应该看到

✅ Grafana 登陆界面
✅ "NBA 2K26 Bot 系统监控" 仪表板
✅ 5 个实时图表
✅ 压测数据的实时更新
✅ 完整的监控链路

**如果还是看不到数据，按照「故障排除」逐项检查！**

---

## 📞 快速参考

| 组件 | 访问地址 | 用途 |
|------|--------|------|
| Prometheus | http://localhost:9090 | 查询指标 |
| PushGateway | http://localhost:9091 | 接收压测数据 |
| Grafana | http://localhost:3000 | 查看仪表板 |
| AlertManager | http://localhost:9093 | 告警管理 |

---

## 🎬 下一步

- 运行基准测试: `python tests/benchmark.py --suite all`
- 分析测试结果: `python tests/analyze_benchmark.py benchmark_results.json`
- 修改仪表板: 在 Grafana UI 中直接编辑
- 导出仪表板: 在 Grafana 中 Share → Export → Save JSON file

