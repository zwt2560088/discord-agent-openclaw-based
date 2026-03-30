# ⚡ 快速开始（3 分钟上手）

## 🎯 核心功能一览

你的 Discord Bot 现在拥有：

| 功能 | 说明 | 命令/触发方式 |
|------|------|------------|
| 🖼️ **识图（OCR）** | 上传游戏截图自动识别等级/金额/徽章 | 发送图片 |
| 💬 **AI 智能对话** | 自动回答价格/服务相关问题 | @ Bot 或在订单频道发消息 |
| 📋 **订单管理** | 一键创建订单频道 | `!panel` |
| 🌐 **Web 管理界面** | 在线编辑知识库并热更新 | http://localhost:8081/admin |
| 📊 **订单看板** | 所有订单实时展示（隐藏价格） | `#order-board` 频道 |

---

## 🚀 启动机器人

### 方式 1：直接启动（开发）
```bash
cd /Users/zhaowentao/IdeaProjects/discord-agent-openclaw-based
export DOTENV_PATH="$(pwd)/src/.env"
python3 src/discord_bot_final.py
```

### 方式 2：Docker 启动（生产）
```bash
docker-compose up -d
docker logs -f discord-agent-nba2k26
```

### 验证启动成功
```bash
# 查看日志中的以下内容
✅ Bot logged in as Legend's Agent(Ping me question)#0564
🖼️ Image recognizer initialized successfully
🌐 Knowledge base admin UI started at http://0.0.0.0:8081/admin
```

---

## 💡 常见操作

### 1️⃣ 用户发送游戏截图

**场景：** 客户在 Discord 发送 NBA 2K26 游戏截图（包含等级/金额等）

```
用户: [拖拽截图到 Discord]
Bot: 🔍 Processing your image...
     [识图中...]
Bot: 🎯 Rookie 3 Rep Grind: $35!
     Rookie1-Starter1: $42
     Type 'order' to start! 😊
```

**Bot 能识别的内容：**
- ✅ 等级：Rookie 1-5, Starter 1-5, Veteran 1-5, Legend 1-2
- ✅ 服务：Rep Grind, Rep Sleeve, 99 Overall, Badges
- ✅ 金额：$25, $35, $40 等价格标签

### 2️⃣ 管理员创建订单

**命令：** `!panel`

```
管理员输入: !panel
Bot: [弹出订单管理面板]
   📋 Order Management Panel
   Click the button below to create a fulfillment channel.

   - 👤 Select Customer (下拉菜单，自动过滤有权限的用户)
   - 填写 Service & Amount (弹出 Modal 表单)
   - 自动创建订单频道：nba2k-{customer}-{date}-{id}
```

### 3️⃣ 编辑知识库并实时生效

**访问地址：** http://localhost:8081/admin

```
1. 打开浏览器
2. 进入 http://localhost:8081/admin
3. 左侧选择文件 (如 complete-pricing.md)
4. 编辑右侧内容
5. 点击 💾 Save File
6. 点击 🔄 Rebuild Vector Store
7. 等待 10-30 秒重建完成
8. 在 Discord 中询问价格，自动生效！
```

---

## 🔧 配置说明

### 必要配置（`.env` 文件）

```env
# Discord Token（必需）
discord_token=MTQ4MzQ0NDI0OTE0Njk0OTc0NQ.GVIj-q.tUUdxTFBE_6nzGw4reJMH0OBbj6odYqBHak_nY

# AI API Key（选一个）
deepseek_api_key=sk-f877b32ffd0a4113867a71c5d9996ee1
openai_api_key=sk-xxx

# 管理员设置
admin_user_ids=1346024374410412088

# Web 管理密码（可选）
ADMIN_PASSWORD=admin123
```

### 可选配置

```env
# 代理（中国用户）
HTTP_PROXY=http://127.0.0.1:8890

# HuggingFace 镜像
HF_ENDPOINT=https://hf-mirror.com
```

---

## 📊 实时监控

### 查看 Bot 日志
```bash
# 实时日志
tail -f /tmp/bot.log | grep -E "✅|❌|🔍|🎯"

# Docker 日志
docker logs -f discord-agent-nba2k26

# 过滤特定信息
tail -f /tmp/bot.log | grep "Image recognized"
```

### 检查 Web 界面
```
http://localhost:8081/admin
- 文件列表（左侧）
- 编辑器（右侧）
- 保存 & 重建按钮（顶部）
```

---

## ⚠️ 常见问题

### Q: 识图不工作？
**A:** 检查 Tesseract 是否安装
```bash
which tesseract
# 如果输出为空，安装：
# Mac: brew install tesseract
# Linux: sudo apt-get install tesseract-ocr
```

### Q: Bot 无法连接 Discord？
**A:** 检查 Token 是否有效
```bash
cat src/.env | grep discord_token
# 确保 Token 不为空且格式正确
```

### Q: 识图很慢？
**A:** 这是正常的，本地 Tesseract OCR < 1 秒
```
如果 > 3 秒，可能是：
1. 图片文件过大（>5MB）
2. Tesseract 未优化
3. 系统资源不足
```

### Q: Web 界面无法访问？
**A:** 检查端口 8081 是否被占用
```bash
lsof -i :8081
# 如果被占用，修改 discord_bot_final.py 的 WEB_PORT
```

---

## 🎓 工作流程示例

### 完整客户服务流程

```
第 1 步：客户发送游戏截图
        用户: [Rookie 3 等级截图]
        Bot: 🔍 Processing...
             🎯 Rookie 3 Rep Grind: $35!

第 2 步：客户下单
        用户: order
        Bot: 💬 Great! I'll create an order channel for you.

第 3 步：管理员创建订单频道
        管理: !panel
        Bot: [弹出订单面板]
             选择客户 → 填写金额 → 创建频道

第 4 步：订单自动同步
        Bot: ✅ Order created!
             📋 ORD-20260330-0001
             📢 nba2k-ruiner2000-20260330-0001

第 5 步：订单看板更新
        #order-board: [新订单卡片出现]
        📦 ORD-20260330-0001
        Customer: @ruiner2000
        Status: 🟡 Pending
        Confirmed By: @Legend2k
```

---

## 🎯 下一步（可选增强）

- [ ] 启用代理（中国用户）
- [ ] 配置 HTTPS（生产环境）
- [ ] 添加自定义识图规则
- [ ] 集成更多支付网关
- [ ] 设置自动报价系统

---

## 📞 快速参考

| 需求 | 操作 |
|------|------|
| 查看日志 | `tail -f /tmp/bot.log` |
| 重启 Bot | `pkill -f discord_bot_final && nohup python3 src/discord_bot_final.py &` |
| 访问 Web 界面 | `http://localhost:8081/admin` |
| 创建订单 | 在 Discord 发送 `!panel` |
| 编辑价格 | 访问 Web 界面，编辑 `complete-pricing.md` |
| 测试识图 | 在 Discord 发送任何游戏截图 |

---

**一切就绪！现在你可以开始为客户提供服务了！🚀**

