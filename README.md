# Geek Morning Report Agent

一个单一用途的 AI 晨报智能体：自动抓取 Hacker News 热门科技新闻，整理成晨报，并通过邮件发送给指定收件人。

该项目使用 Python 实现，采用标准 LLM Function Calling 将大模型与本地工具函数连接起来。当前模型接口使用 DeepSeek 的 OpenAI 兼容 API。

## 项目功能

- 调用 DeepSeek-v4-flash 模型理解用户指令
- 使用 Hacker News 官方 API 获取热门科技新闻
- 将新闻整理为 Markdown 晨报
- 将 Markdown 转换为 HTML 邮件正文
- 使用 SMTP 发送邮件
- 支持 Gmail、QQ 邮箱、网易邮箱等 SMTP 服务商预设
- 支持 `ssl`、`starttls` 和手动 SMTP 覆盖配置
- 支持默认收件人配置
- 支持持续对话，输入 `exit` 或 `quit` 退出

## 技术栈

- Python 3.10+
- `openai>=1.0`
- `pydantic`
- `requests`
- `smtplib`
- `email.mime`
- `python-dotenv`，可选，用于读取 `.env`

### 1. 工具使用 / 技能

项目提供了两个截然不同的功能性工具：

| 工具 | 功能 | 类型 |
| --- | --- | --- |
| `fetch_hacker_news(top_n)` | 调用 Hacker News API 抓取热门新闻 | 外部 API 数据获取 |
| `send_daily_report(subject, markdown_content, target_email)` | 使用 SMTP 发送邮件报告 | 自动化邮件发送 |

这两个工具分别负责“获取信息”和“执行发送动作”，满足至少两种不同技能的要求。

### 2. 上下文集成

项目使用标准 LLM Function Calling，而不是让模型直接执行代码。

核心流程如下：

```text
用户输入
  -> LLM 判断是否需要调用工具
  -> 返回 tool_calls
  -> Python 本地执行对应函数
  -> 将工具结果以 role="tool" 放回消息历史
  -> LLM 继续推理或返回最终回复
```

相关代码包括：

- `TOOLS`：定义可供模型调用的工具 JSON schema
- `TOOL_REGISTRY`：将工具名称映射到本地 Python 函数
- `execute_tool_call()`：解析参数、校验参数、执行工具
- `run_agent()`：实现完整的工具调用编排循环

### 3. Vibe coding

项目中的样板代码由 AI 辅助生成，包括：

- Pydantic 参数模型
- Hacker News API 请求逻辑
- SMTP 邮件发送逻辑
- Function Calling 工具 schema
- 工具注册表
- Agent 编排循环
- Markdown 到 HTML 邮件的简单转换逻辑

这样开发重点可以放在系统提示词、工具设计和编排流程上。

## 文件结构

```text
.
├── morning_report_agent.py  # 主程序
├── .env                     # 本地环境变量
├── .gitignore
├── LICENSE
└── README.md
```

## 安装依赖

建议先创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
pip install "openai>=1.0" pydantic requests python-dotenv
```

如果不使用 `.env` 文件，`python-dotenv` 可以不安装。

## 环境变量配置（以 Gmail 为例）

### 方式一：PowerShell 临时配置

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
$env:MAIL_PROVIDER="gmail"
$env:MAIL_USER="你的 Gmail 地址@gmail.com"
$env:MAIL_PASSWORD="你的 Gmail 应用专用密码"
$env:REPORT_TARGET_EMAIL="默认收件人邮箱"
```

### 方式二：使用 `.env`

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
MAIL_PROVIDER=gmail
MAIL_USER=你的Gmail地址@gmail.com
MAIL_PASSWORD=你的Gmail应用专用密码
REPORT_TARGET_EMAIL=默认收件人邮箱
```

Gmail 需要使用应用专用密码，不要填写 Gmail 登录密码。通常需要先为 Google 账号开启两步验证，然后生成 App Password。

## 邮箱服务商配置

项目内置了常见邮箱服务商预设，只需要设置 `MAIL_PROVIDER`。

| 邮箱类型 | `MAIL_PROVIDER` | 默认 SMTP | 默认端口 | 加密方式 |
| --- | --- | --- | --- | --- |
| Gmail | `gmail` | `smtp.gmail.com` | `587` | `starttls` |
| QQ 邮箱 | `qq` | `smtp.qq.com` | `465` | `ssl` |
| 网易 163 邮箱 | `netease` 或 `163` | `smtp.163.com` | `465` | `ssl` |
| 网易 126 邮箱 | `126` | `smtp.126.com` | `465` | `ssl` |
| 网易 yeah.net 邮箱 | `yeah` | `smtp.yeah.net` | `465` | `ssl` |

如果你想手动覆盖服务商预设，可以额外设置：

```env
MAIL_PROVIDER=custom
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
```

`SMTP_SECURITY` 可选值：

- `ssl`：直接使用 SSL 连接，常见于 `465`
- `starttls`：先建立普通 SMTP 连接，再升级到 TLS，常见于 `587`
- `none`：不启用加密，不建议在公网使用

QQ 邮箱和网易邮箱同样需要使用授权码或客户端专用密码，而不是账号登录密码。

## 运行项目

```powershell
python morning_report_agent.py
```

启动后可以输入类似指令：

```text
发送今天的 geek morning report，抓取 Hacker News 前 5 条新闻
```

如果没有在提示词里指定收件人，程序会优先使用 `REPORT_TARGET_EMAIL`。如果该变量也没有配置，则默认发送给 `MAIL_USER` 自己。

退出程序：

```text
exit
```

或：

```text
quit
```

## 工作流程

```text
用户输入请求
  -> DeepSeek 模型读取 SYSTEM_PROMPT
  -> 模型调用 fetch_hacker_news
  -> 本地程序请求 Hacker News API
  -> 工具结果返回给模型
  -> 模型生成 Markdown 晨报
  -> 模型调用 send_daily_report
  -> 本地程序转换 HTML 并通过 SMTP 发送邮件
  -> 模型返回最终确认信息
```

## 主要模块说明

### `SYSTEM_PROMPT`

定义智能体的角色和边界：

- 只作为自动化科技晨报助手
- 必须先抓取新闻
- 只能基于工具返回的新闻内容生成报告
- 生成报告后通过邮件发送

### `FetchHackerNewsArgs`

`fetch_hacker_news` 的参数模型。

```python
top_n: int
```

限制：

- 最小值：`1`
- 最大值：`30`

### `SendDailyReportArgs`

`send_daily_report` 的参数模型。

```python
subject: str
markdown_content: str
target_email: str = ""
```

其中 `target_email` 是可选的。如果为空，程序会使用默认收件人配置。

### `fetch_hacker_news()`

使用 Hacker News 官方 Firebase API：

- `https://hacker-news.firebaseio.com/v0/topstories.json`
- `https://hacker-news.firebaseio.com/v0/item/{item_id}.json`

返回每条新闻的：

- 标题
- 原始链接
- Hacker News 讨论链接
- 分数
- 评论数

### `send_daily_report()`

负责邮件发送。

程序会先根据 `MAIL_PROVIDER` 选择 SMTP 预设：

```python
MAIL_PROVIDER=gmail
```

也可以通过 `SMTP_HOST`、`SMTP_PORT`、`SMTP_SECURITY` 手动覆盖。

当 `SMTP_SECURITY=ssl` 时，使用：

```python
smtplib.SMTP_SSL(...)
```

当 `SMTP_SECURITY=starttls` 时，使用：

```python
smtplib.SMTP(...)
server.starttls()
```

邮件使用 `multipart/alternative`，同时包含：

- `text/plain`：Markdown 原文
- `text/html`：渲染后的 HTML 正文

### `run_agent()`

实现标准 Function Calling 编排循环：

1. 将 system prompt 和用户输入发送给模型
2. 检查模型是否返回 `tool_calls`
3. 解析工具参数
4. 执行本地 Python 工具
5. 将工具结果追加回消息历史
6. 再次调用模型
7. 直到模型返回最终自然语言回复

## 常见问题

### 1. Gmail、QQ、网易邮箱如何切换？

只需要修改 `MAIL_PROVIDER`：

```env
MAIL_PROVIDER=gmail
```

```env
MAIL_PROVIDER=qq
```

```env
MAIL_PROVIDER=163
```

如果是其他邮箱服务商，可以手动设置：

```env
MAIL_PROVIDER=custom
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
```

### 2. SMTP 端口连通，但发送失败怎么办？

重点检查：

- 邮箱是否开启 SMTP 服务
- 授权码或应用专用密码是否正确
- `MAIL_USER` 是否是完整邮箱地址
- 环境变量是否在当前终端生效
- `SMTP_SECURITY` 是否和端口匹配，`465` 通常用 `ssl`，`587` 通常用 `starttls`

### 3. 邮件为什么显示 Markdown 原文？

当前版本会同时发送 HTML 和纯文本。大多数邮箱客户端会显示 HTML。如果仍显示 Markdown，可能是：

- 邮箱客户端禁用了 HTML 邮件
- 模型生成的 Markdown 格式不在内置转换器支持范围内
- 邮件客户端优先展示了纯文本部分

### 4. DeepSeek API 报错怎么办？

检查：

- `DEEPSEEK_API_KEY` 是否设置
- API Key 是否有效
- 当前模型名 `deepseek-v4-flash` 是否可用于你的账号
- 网络是否能访问 `https://api.deepseek.com`

## 可改进方向

- 增加 GitHub Trending 抓取工具
- 增加天气 API，把天气加入晨报
- 增加本地归档工具，将每天报告保存为 Markdown 或 HTML 文件
- 增加日志工具，记录每次工具调用和发送结果
- 将 Function Calling 工具迁移为 MCP Server，展示更标准的上下文协议集成
