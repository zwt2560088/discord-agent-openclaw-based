# 🚀 Discord NBA 2K26 机器人 - 完整部署指南

## 📋 概览

这个 Discord 机器人集成了以下完整功能：
- ✅ AI 智能对话（OpenAI/DeepSeek）
- ✅ 订单管理系统
- ✅ 🆕 **游戏截图 OCR 识图**
- ✅ Web 管理界面（编辑知识库 + 热更新）
- ✅ Docker 容器化部署

---

## 🎯 部分一：本地运行（开发环境）

### 前置条件
- Python 3.11+
- Mac/Linux/Windows
- Discord Token
- OpenAI/DeepSeek API Key（可选）

### 安装步骤

#### 1. 克隆项目
```bash
git clone <your-repo>
cd discord-agent-openclaw-based
```

#### 2. 安装依赖
```bash
pip install -r requirements.txt
```

#### 3. 安装 Tesseract OCR（本地识图引擎）

**Mac:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install tesseract-ocr
```

**Windows:**
下载安装包：https://github.com/UB-Mannheim/tesseract/wiki

#### 4. 配置 `.env` 文件
```bash
# src/.env
discord_token=YOUR_DISCORD_TOKEN
deepseek_api_key=sk-xxx
admin_user_ids=1346024374410412088
ADMIN_PASSWORD=your_admin_password
```

#### 5. 启动机器人
```bash
# 方式1：直接运行
python3 src/discord_bot_final.py

# 方式2：使用启动脚本
bash bin/start_final_bot.sh
```

#### 6. 验证启动成功
```
✅ Bot logged in as Legend's Agent(Ping me question)#0564
📊 Connected to 1 server(s)
🌐 Knowledge base admin UI started at http://0.0.0.0:8081/admin
🖼️ Image recognizer initialized successfully
```

---

## 🐳 部分二：Docker 部署（生产环境）

### 前置条件
- Docker >= 20.10
- Docker Compose >= 2.0
- Discord Token
- API Keys

### 快速部署（3 步）

#### 步骤 1：配置环境变量
```bash
# 编辑 src/.env
vi src/.env

# 必要配置：
discord_token=YOUR_DISCORD_TOKEN
deepseek_api_key=sk-xxx
admin_user_ids=YOUR_ADMIN_ID
ADMIN_PASSWORD=your_secure_password
```

#### 步骤 2：构建 Docker 镜像
```bash
docker-compose build
```

这个命令会：
- 拉取 Python 3.11 slim 基础镜像
- 自动安装 Tesseract OCR（识图引擎）
- 安装所有 Python 依赖
- 编译项目代码

#### 步骤 3：后台启动容器
```bash
docker-compose up -d
```

### 查看日志
```bash
# 查看实时日志
docker logs -f discord-agent-nba2k26

# 查看历史日志
docker logs discord-agent-nba2k26 | tail -50
```

### 常见命令

```bash
# 停止容器
docker-compose down

# 重启容器
docker-compose restart

# 删除容器和镜像
docker-compose down --rmi all

# 查看容器状态
docker ps | grep discord-agent

# 进入容器 shell
docker exec -it discord-agent-nba2k26 bash
```

---

## 🔍 功能演示

### 1️⃣ 识图功能（OCR）

**用户场景：** 用户在 Discord 发送游戏截图

```
用户: [发送一张显示 "Rookie 3" 的截图]
Bot: 🔍 Processing your image...
     [OCR 识别] → {"level": "rookie_3"}
Bot: 🎯 Rookie 3 Rep Grind: $35 | Rookie1-Starter1: $42! Type 'order' to proceed!
```

**支持识别的内容：**
- 🎮 等级：Rookie, Starter, Veteran, Legend (+ 数字)
- 🎯 服务类型：Rep Grind, Rep Sleeve, 99 Overall
- 🌟 徽章：Gym Rat, Legendary, Gold, HOF
- 💰 支付金额：$25, $100 等

### 2️⃣ 订单管理

**命令：** `!panel`

```
管理员发送: !panel
Bot: [发送订单管理面板]
     - 自动检测客户（频道权限过滤）
     - 弹出 Modal 填写服务和金额
     - 创建订单频道：nba2k-{customer}-{date}-{id}
```

### 3️⃣ Web 管理界面

**访问：** http://localhost:8081/admin

功能：
- 📚 在线编辑知识库文件（.md / .txt）
- 🔄 一键重建向量库（热更新）
- 💾 保存文件无需重启

---

## 📊 性能指标

| 功能 | 响应时间 | 说明 |
|------|--------|------|
| OCR 识图 | < 1s | 本地 Tesseract，无网络延迟 |
| 关键词回复 | < 500ms | 内存级快速匹配 |
| AI 智能回复 | < 2s | DeepSeek API 调用 |
| 最大并发 | 50+ 频道 | 轻量异步架构 |
| 内存占用 | ~300-400MB | Docker 轻量部署 |

---

## 🛠️ 故障排查

### 问题 1: OCR 识图不工作
**症状：** 用户发送图片，Bot 无反应

**解决：**
```bash
# 检查 Tesseract 是否安装
which tesseract

# 如果未安装，重新安装
# Mac: brew install tesseract
# Linux: sudo apt-get install tesseract-ocr

# 重启容器
docker-compose restart
```

### 问题 2: Discord Bot 无法登录
**症状：** `❌ DISCORD_TOKEN not configured!`

**解决：**
```bash
# 检查 .env 文件
cat src/.env | grep discord_token

# 确保 Token 不为空
# 重新启动
docker-compose up -d
```

### 问题 3: 知识库热更新不生效
**症状：** 修改 .md 文件后，Bot 回复仍是旧内容

**解决：**
```bash
# 访问 Web 界面
http://localhost:8081/admin

# 在界面中点击 "🔄 Rebuild Vector Store"
# 等待 10-30 秒重建完成

# 或手动重建
docker exec discord-agent-nba2k26 python3 -c "from src.image_recognizer import *; ..."
```

### 问题 4: 容器日志乱码/无日志
**症状：** Docker 日志显示乱码或不输出

**解决：**
```bash
# 重新启动并查看日志
docker-compose down && docker-compose up -d

# 强制输出日志
PYTHONUNBUFFERED=1 docker-compose up

# 查看详细日志
docker logs --follow --tail 100 discord-agent-nba2k26
```

---

## 📝 配置文件说明

### `Dockerfile`
- 基础镜像：Python 3.11-slim（轻量）
- 自动安装 Tesseract OCR（识图）
- 复制项目代码并设置权限
- 非 root 用户运行（安全）

### `.dockerignore`
防止以下文件打进 Docker 镜像：
- `.env` 密钥文件
- `knowledge_db/` 向量库（本地存储）
- `__pycache__/` 编译缓存
- `.git/` Git 配置

### `docker-compose.yml`
- 容器名称：`discord-agent-nba2k26`
- 重启策略：`always`（崩溃自动恢复）
- 数据持久化：挂载本地 `/knowledge`, `/data`, `/logs`
- 日志限制：最多保留 5 个 10MB 日志文件

---

## 🔐 安全建议

1. **密钥管理**
   - 不要将 `.env` 提交到 Git
   - 使用强密码（ADMIN_PASSWORD）
   - 定期更新 API Keys

2. **网络安全**
   - 生产环境使用反向代理（Nginx）
   - 启用 HTTPS
   - 配置 IP 白名单

3. **容器安全**
   - 定期更新基础镜像
   - 不使用 root 用户（已配置）
   - 设置资源限制（可选）

---

## 📚 进阶配置

### 自定义 Tesseract 语言
```python
# 在 src/image_recognizer.py 中修改
text = pytesseract.image_to_string(image, lang="eng+chi_sim")  # 支持中文
```

### 启用 GPU 加速
```dockerfile
# Dockerfile 中修改基础镜像
FROM nvidia/cuda:12.0-runtime-ubuntu22.04
# ... 然后安装 Python 和依赖
```

### 配置持久化存储
```yaml
# docker-compose.yml 中修改
volumes:
  knowledge:
    driver: local
  data:
    driver: local
```

---

## 🎓 开发指南

### 添加新的识图规则

编辑 `src/image_recognizer.py`：

```python
RECOGNITION_RULES = {
    "my_new_feature": ["keyword1", "keyword2"],
    # ...
}
```

### 测试识图功能

```python
from src.image_recognizer import ImageRecognizer

recognizer = ImageRecognizer()
result = await recognizer.recognize("https://your-image-url.jpg")
print(result)  # {"level": "rookie_3"}
```

---

## 📞 技术支持

如有问题，请查看：
1. 📋 日志文件：`logs/bot_*.log`
2. 🔍 此指南的故障排查部分
3. 📖 项目 README.md

---

## ✅ 完整检查清单

部署前：
- [ ] Discord Token 已配置
- [ ] API Keys 已配置
- [ ] Admin ID 已正确设置
- [ ] `.env` 文件已创建

Docker 部署：
- [ ] Docker 已安装
- [ ] Docker Compose 已安装
- [ ] Dockerfile 存在
- [ ] docker-compose.yml 存在

启动后验证：
- [ ] Bot 成功连接 Discord
- [ ] 日志显示 "✅ Bot logged in"
- [ ] Web 界面可访问（端口 8081）
- [ ] 识图功能工作正常

---

**祝部署顺利！🎉**

