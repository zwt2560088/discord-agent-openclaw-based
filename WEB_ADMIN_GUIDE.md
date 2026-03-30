# 🌐 Web 管理界面使用指南

## 快速开始

### 访问地址
```
http://你的服务器IP:8081/admin
```

**本地测试:**
```
http://localhost:8081/admin
```

### 登录
- 首次访问会弹出密码输入框
- 密码配置在 `src/.env` 文件中的 `ADMIN_PASSWORD`
- 默认密码: `admin123`

---

## 功能说明

### 1. 📚 文件列表（左侧）
- 显示 `./knowledge` 目录下所有 `.md` 和 `.txt` 文件
- 点击文件名加载内容
- 当前选中文件高亮显示

### 2. ✏️ 编辑器（右侧）
- 实时编辑知识库文件内容
- 支持所有文本格式和 Markdown

### 3. 💾 保存文件
- 编辑完成后点击 **Save File** 按钮
- 文件会立即保存到磁盘
- 底部会显示保存成功提示

### 4. 🔄 重建向量库
- 点击 **Rebuild Vector Store** 按钮
- 系统会在后台重建所有文件的向量嵌入
- 重建通常需要 10-30 秒（根据知识库大小）
- 重建完成后，新内容立即对 AI 生效
- **期间 Bot 其他功能正常，无需重启**

---

## 工作流程示例

### 更新价格表

```
1. 访问 http://localhost:8081/admin
2. 输入密码 (默认: admin123)
3. 左侧文件列表中选择 "complete-pricing.md"
4. 编辑右侧的价格内容
5. 点击 "💾 Save File"
6. 点击 "🔄 Rebuild Vector Store"
7. 等待 10-30 秒重建完成
8. 在 Discord 询问价格，应返回新内容！ ✅
```

### 更新 FAQ

```
1. 选择 "service-faq.md"
2. 编辑内容
3. 保存 → 重建
4. 完成！
```

---

## 安全提示

### 密码设置
编辑 `src/.env` 更改密码：
```env
ADMIN_PASSWORD=your_strong_password_here
```

### 生产环境推荐
- 设置强密码（至少 16 字符）
- 使用 HTTPS（配置反向代理，如 Nginx）
- 限制 IP 访问（防火墙白名单）
- 示例 Nginx 配置：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert;
    ssl_certificate_key /path/to/key;

    location /admin {
        # IP 白名单
        allow YOUR_ADMIN_IP;
        deny all;

        proxy_pass http://localhost:8081;
        proxy_set_header Authorization "Bearer $http_authorization";
    }
}
```

---

## 技术细节

### 知识库目录结构
```
./knowledge/
├── complete-pricing.md          # 完整价格表
├── service-faq.md              # 服务 FAQ
├── business-faq.md             # 商业相关
├── technical-faq.md            # 技术相关
├── prices.txt                  # 简单价格列表
└── procedures/
    └── order-procedure.md       # 订单流程
```

### 向量库位置
```
./knowledge_db/                 # 向量库目录
├── chroma.sqlite3             # 向量数据库
└── [嵌入文件]
```

### 重建流程
1. Web 界面接收重建请求
2. 后台启动异步任务
3. 删除旧向量库（`./knowledge_db/`）
4. 基于最新知识文件重建
5. RAG 智能检索自动更新

---

## 故障排查

### 问题 1: 无法访问管理界面
**原因**: 端口 8081 被占用或防火墙阻止

**解决**:
```bash
# 检查 8081 端口
lsof -i :8081

# 改用其他端口：编辑 discord_bot_final.py
WEB_PORT = 8082  # 改成其他端口
```

### 问题 2: 密码错误
**原因**: 输入了错误的密码

**解决**:
- 检查 `src/.env` 中的 `ADMIN_PASSWORD`
- 确保没有多余空格

### 问题 3: 文件保存失败
**原因**: 权限问题或磁盘满

**解决**:
```bash
# 检查权限
ls -l ./knowledge

# 增加权限
chmod 755 ./knowledge
```

### 问题 4: 向量库重建失败
**原因**: 知识库文件格式错误或磁盘问题

**解决**:
```bash
# 查看日志
tail -f /path/to/bot.log | grep "rebuild"

# 手动检查文件
head -20 ./knowledge/complete-pricing.md
```

---

## 常见操作

### 快速编辑价格
1. 打开 Web 管理界面
2. 选择 `complete-pricing.md` 或 `prices.txt`
3. 修改数字或服务名称
4. 保存 → 重建
5. **立即生效**（无需重启 Bot）

### 添加新的 FAQ
1. 保存为新文件 `new-faq.md` 在 `./knowledge/` 下
2. 刷新 Web 界面（F5）
3. 选择新文件编辑
4. 保存 → 重建
5. 完成！

### 批量更新
- 编辑多个文件后，只需点击一次 **Rebuild Vector Store**
- 所有更改会一起生效

---

## 高级配置

### 自定义端口
编辑 `src/discord_bot_final.py`:
```python
WEB_PORT = 9000  # 改成你想要的端口
```

### 禁用密码（仅本地开发）
编辑 `src/.env`:
```env
ADMIN_PASSWORD=
```

### 自定义知识库路径
编辑 `src/discord_bot_final.py`:
```python
KNOWLEDGE_DIR = "/path/to/your/knowledge"
```

---

## 监控和日志

### 查看 Web 服务日志
```bash
# 查看最近日志
tail -50 /tmp/bot.log | grep "🌐"

# 查看重建日志
tail -100 /tmp/bot.log | grep "rebuild"
```

### 监控向量库状态
```bash
# 检查向量库大小
du -sh ./knowledge_db/

# 查看文件修改时间
stat ./knowledge_db/chroma.sqlite3
```

---

## 💡 最佳实践

1. **定期备份** - 在大改动前备份 `./knowledge` 目录
2. **增量更新** - 频繁小改动比一次大改动更安全
3. **测试内容** - 重建后在 Discord 测试新内容是否有效
4. **版本管理** - 如使用 Git，提交文件变更记录
5. **定期检查** - 每周检查一次价格表是否需要更新

---

## 快速命令参考

| 操作 | 快捷键 | 说明 |
|------|--------|------|
| 保存文件 | `Ctrl+S` | 不适用，必须点击按钮 |
| 刷新文件列表 | `F5` | 重新加载页面 |
| 清除编辑 | `Ctrl+A` → `Delete` | 手动清除 |
| 撤销编辑 | `Ctrl+Z` | 浏览器标准撤销 |

---

## 支持和反馈

如有问题，请检查：
1. 日志文件（`/tmp/bot.log`）
2. 密码是否正确
3. 网络连接是否正常
4. 磁盘空间是否充足

---

**祝管理愉快！🎉**

