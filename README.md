# wecom-batch-app-creator

企业微信批量创建自建应用工具，基于 Playwright 浏览器自动化，支持一键批量创建多个企微应用并输出完整配置信息。

## 功能特性

- **批量创建**：一次运行创建指定数量的企微自建应用，应用编号自动递增（1号openclaw、2号openclaw...）
- **Logo 自动上传**：使用 OpenClaw 小龙虾 Logo，完整处理企微 avatarEditor 弹窗（已实测验证）
- **API 接收配置**：自动随机生成 Token/EncodingAESKey，填写 OpenClaw Webhook URL
- **配置文件驱动**：CORP_ID、可见范围、数量、OpenClaw IP 均通过 `config.json` 指定
- **断点续创**：自动检测已创建的应用编号，避免重复，支持中断后继续

## 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/lewiszeng666/wecom-batch-app-creator.git
cd wecom-batch-app-creator

pip install -r requirements.txt
playwright install chromium
```

### 2. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "corp_id": "ww95aca10dfcf3d6e2",
  "visible_member": "曾君亮",
  "create_count": 3,
  "openclaw_ip": "101.35.102.240",
  "app_name_prefix": "openclaw",
  "app_description": "与openclaw通信通道",
  "logo_path": "openclaw_logo.png",
  "output_file": "output/app_configs.json",
  "headless": true,
  "browser_data_dir": "browser_data"
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `corp_id` | 企业微信 CORP_ID（我的企业页面获取）<br>命令行：`--corp-id` | `ww95aca10dfcf3d6e2` |
| `visible_member` | 应用可见范围成员名<br>命令行：`--member` | `曾君亮` |
| `create_count` | 批量创建数量<br>命令行：`--count` | `3` |
| `openclaw_ip` | **OpenClaw 公网 IP**（Webhook URL 的 IP 部分）<br>命令行：`--ip` | `101.35.102.240` |
| `app_name_prefix` | 应用名称后缀（`N号{prefix}`） | `openclaw` |
| `app_description` | 应用介绍 | `与openclaw通信通道` |
| `logo_path` | Logo 图片路径（≥150×150，RGB PNG） | `openclaw_logo.png` |
| `output_file` | 输出配置文件路径 | `output/app_configs.json` |
| `headless` | 是否无头模式（生产用 true） | `true` |
| `browser_data_dir` | 浏览器会话存储目录 | `browser_data` |

### 3. 登录预存（首次使用必做）

**此步骤需要在有显示器的环境执行（扫码登录）：**

```bash
python save_cookie.py
```

执行后浏览器打开企微登录页，扫码登录后按 Enter 保存会话。**会话有效期约 24 小时**，过期后重新执行此命令。

### 4. 批量创建

```bash
# 使用 config.json 默认配置
python main.py

# 指定 OpenClaw 公网 IP（最常用）
python main.py --ip 1.2.3.4

# 指定创建数量 + IP
python main.py --count 5 --ip 1.2.3.4

# 有头模式（可观察浏览器操作过程，调试用）
python main.py --visible

# 测试：只创建 1 个应用
python main.py --count 1 --visible

# 完整覆盖所有参数
python main.py --corp-id wwXXXXXXXX --member 张三 --count 3 --ip 1.2.3.4
```

---

## 输出格式

创建完成后，配置保存到 `output/app_configs.json`：

```json
[
  {
    "success": true,
    "app_name": "1号openclaw",
    "corp_id": "ww95aca10dfcf3d6e2",
    "agent_id": "1000010",
    "secret": "xxx",
    "token": "EoWgXD3utpLOLifS",
    "aes_key": "HeJvvgnX1GA1zcSyzpu0yz895De3qjiEPcBWwsWgHfQ",
    "webhook_url": "http://101.35.102.240:3000/wecom"
  },
  {
    "app_name": "2号openclaw",
    ...
  }
]
```

> **注意**：`secret` 字段默认为 `"xxx"`，需手工填入。

---

## Secret 获取（唯一需要人工操作的步骤）

企业微信出于安全机制，Secret 只推送到管理员企微 App，无法自动获取。

工具会在创建完每个应用后自动触发「View → Send」，你只需：

1. 在**企业微信 App** 收到「WeCom Team」消息
2. 复制 Secret 明文
3. 填入 `output/app_configs.json` 对应应用的 `"secret"` 字段

---

## Logo 上传机制说明

企微后台 Logo 上传使用 Backbone.js 事件委托，与标准 `<input type="file">` 不同，需要特殊处理：

| 步骤 | 操作 | 关键说明 |
|------|------|---------|
| 1 | 触发弹窗 | `$(input).trigger('click')`，不能用原生 click（被 preventDefault 拦截） |
| 2 | 等待弹窗 | `#__dialog__avatarEditor__` |
| 3 | 注入文件 | `set_input_files()`（CDP 方式，正确触发 change 事件） |
| 4 | 等待 cropper | `.cropper-container` 出现 |
| 5 | 验证 Save 按钮 | `$(btn).attr('disabled') === undefined`（jQuery disabled ≠ 原生 disabled） |
| 6 | 点击 Save | 不加 `force=True`，等待弹窗关闭 |

**图片要求**：≥ 150×150 像素，RGB 模式（PNG/JPG）

---

## 文件结构

```
wecom-batch-app-creator/
├── main.py               # 主入口（命令行工具）
├── batch_creator.py      # 核心批量创建模块
├── save_cookie.py        # 登录预存工具
├── config.json           # 配置文件（本地，不提交 git）
├── config.example.json   # 配置示例
├── openclaw_logo.png     # OpenClaw 小龙虾 Logo（500×500）
├── requirements.txt      # Python 依赖
├── .gitignore
├── output/               # 输出目录（gitignore）
│   └── app_configs.json  # 创建结果（含 AgentId/Token/AESKey）
└── browser_data/         # 浏览器会话（gitignore，含登录 Cookie）
```

---

## 常见问题

**Q: Logo 上传失败，提示"请上传应用logo"？**

检查 `openclaw_logo.png` 是否存在且尺寸 ≥ 150×150：
```bash
python -c "from PIL import Image; img=Image.open('openclaw_logo.png'); print(img.size, img.mode)"
```

**Q: 可见范围设置失败？**

用 `--visible` 有头模式观察，确认 `visible_member` 与企微后台成员名完全一致（包括中文）。

**Q: 创建到一半中断了怎么办？**

直接重新运行 `python main.py`，工具会自动读取 `output/app_configs.json` 中已创建的编号，从断点继续。

**Q: 会话过期了怎么办？**

重新运行 `python save_cookie.py` 扫码登录，无需修改其他配置。

---

## License

MIT
