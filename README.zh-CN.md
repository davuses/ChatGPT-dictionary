# Glossbook

一个私有的个人长期英语词汇积累与主动回忆网页应用，基于 FastAPI 和 SQLite 构建。你可以添加单词或短语、用 Markdown 撰写自己的释义、附上真实语境和例句，并通过填空测验、音标转写与发音、关联词库同义词查询以及内置 Markdown 学习笔记浏览器不断巩固记忆。

[English README](README.md)

![词条列表](docs/screenshot-list.png)
![词条详情](docs/screenshot-entry.png)

## 功能特性

- **词条与释义** — 添加单词/短语，用 Markdown 撰写个人释义，并附上语境和例句
- **填空主动回忆与专注复习** — 首页内置填空测验卡片，并提供支持键盘快捷键的 `/review` 专注复习模式，从自己保存的语境与例句中抽题
- **实时搜索** — 跨词条、语境与例句即时搜索并高亮匹配内容
- **音标转写与发音** — 通过 [phonemizer](https://github.com/bootphon/phonemizer) 自动生成国际音标（IPA），并支持发音播放
- **同义词查询** — 从 Merriam-Webster Thesaurus API 获取同义词及释义，并自动关联你词典中已收录的词条
- **复习书签** — 标记当前复习进度，方便下次从断点继续
- **访问记录** — 每个词条自动记录访问次数和最近访问时间
- **多种视图** — 支持查看全部词条、仅词条列表、带例句列表，以及筛选尚未填写释义词条的 **Needs Definition** 视图
- **学习笔记** — 浏览并编辑个人英语学习 Markdown 笔记文件夹，自动生成目录（仅管理员可见）
- **邀请制多用户** — 管理员可在 `/admin` 生成一次性邀请链接与密码重置链接；每位用户拥有完全隔离的个人词典、测验、`/inbox`，并可在 `/account` 管理多设备 Chrome 扩展 API Token
- **Markdown 编辑** — 释义、例句和学习笔记使用 [EasyMDE](https://github.com/Ionaru/easy-markdown-editor) 进行编辑（渲染时经 `nh3` 安全过滤），词条本身使用简洁的纯文本单词与语境输入框

## 技术栈

- [FastAPI](https://fastapi.tiangolo.com/) + [Jinja2](https://jinja.palletsprojects.com/) 模板
- [SQLAlchemy](https://www.sqlalchemy.org/) ORM，配合 SQLite 数据库
- [markdown2](https://github.com/trentm/python-markdown2) 用于渲染 Markdown 内容
- [phonemizer](https://github.com/bootphon/phonemizer) 用于音标转写
- 前端使用原生 JS 与 [EasyMDE](https://github.com/Ionaru/easy-markdown-editor)

## 安装与运行

需要 Python 3.12 及以上版本。

1. 安装依赖（使用 [uv](https://github.com/astral-sh/uv) 或 pip）：

   ```bash
   uv sync
   # 或者
   pip install -r requirements.txt
   ```

   音标转写功能还需要 `espeak-ng` 后端：

   ```bash
   sudo apt-get install espeak-ng
   ```

2. 复制示例配置文件并填入你自己的值：

   ```bash
   cp config.toml.example config.toml
   ```

   - `notes_folder` — 用于在 `/notes/` 下浏览的本地 Markdown 笔记文件夹路径
   - `mw_thesaurus_api_key` — 在 [Merriam-Webster Developer Center](https://dictionaryapi.com/) 免费申请的 API key（用于同义词功能）

3. 配置个人登录账号，生成 Argon2 密码哈希和随机会话密钥：

   ```bash
   uv run python -c "from pwdlib import PasswordHash; print(PasswordHash.recommended().hash(input('Password: ')))"
   uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   将结果填入 `config.toml` 的 `[auth]` 配置段：

   ```toml
   [auth]
   admin_username = "admin"
   admin_password_hash = "$argon2id$..."
   session_secret = "the-random-session-secret"
   https_only = true
   ```

   生产环境默认使用仅限 HTTPS 的安全会话 Cookie（有效期 30 天）。如果在受信任的局域网中通过 HTTP 测试，可临时设置 `https_only = false`，但在公网部署时请务必保持为 `true`。也支持使用 `DICTIONARY_*` 环境变量覆盖对应配置。

4. 创建数据库表：

   ```bash
   python database.py create-table
   ```

5. 启动应用：

   ```bash
   uvicorn main:app --reload
   ```

   然后在浏览器中打开 `http://localhost:8000`。

   如需在同一受信任局域网内的其他设备上测试：

   ```bash
   export DICTIONARY_HTTPS_ONLY=false
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   打开 `http://<电脑局域网IP>:8000`。部署到生产环境时请恢复 `DICTIONARY_HTTPS_ONLY=true`（或移除该环境变量）。

## 访问控制与多用户

- 整个应用默认私有并采用邀请制：所有词条页面、测验、同义词、书签、`/inbox`、`/account` 和修改接口均需在 `/login` 登录后访问。
- 仅 `/login`、携带有效一次性邀请码的 `/register`、携带管理员一次性重置链接的 `/reset-password` 以及 `/static/*` 静态资源在未登录时可访问。
- 每位用户的词条、释义、测验、书签和 `/inbox` 完全隔离；本地文件学习笔记（`/notes/*`）和 `/admin` 仅限管理员访问（普通用户返回 `403`）。
- 会话使用 `HttpOnly`、`SameSite=Lax` Cookie（开启 `https_only` 时附带 `Secure`），有效期 30 天；修改密码、重置密码或禁用账号会通过 `session_version` 立即使旧会话失效。
- 所有浏览器端的状态修改请求均需携带有效的 CSRF Token，用户撰写的 Markdown 在渲染前经过 `nh3` 净化防 XSS。
- `/api/v1/*` 采集接口支持已登录的浏览器会话（修改请求需带 `X-CSRF-Token`），或用户在 `/account` 生成的独立设备 `Bearer` Token（数据库仅存 SHA-256 哈希，支持按设备吊销）。
- 已禁用 FastAPI 的 `/docs`、`/redoc` 和 `/openapi.json` 接口。
- 若部署在反向代理（Caddy/nginx/Cloudflare Tunnel）后，请给 Uvicorn 加上 `--proxy-headers --forwarded-allow-ips=...`，以便登录限流识别真实客户端 IP。
- 服务器端紧急重置密码命令：

  ```bash
  python database.py reset-password --username admin
  ```

## 说明

- 数据保存在本地的 `dictionary.db`（SQLite）文件中，未被 git 追踪。
- 从旧版单用户 `dictionary.db` 升级启动时，应用会自动创建 WAL 安全的快照备份（`dictionary.db.bak-*`），并将已有词条、书签、页面笔记及原 `api_token` 无损迁移到管理员账号下。

## Chrome 侧边栏扩展（可选）

[`extension/`](extension/) 目录包含一个可本地加载的 Manifest V3 Chrome 扩展，用于在任意网页记录按页面归档的 Markdown 随手笔记，并批量记录生词/短语（支持自动提取 YouTube 播放时间戳与完整字幕句，或抓取文章选中句子），统一导入个人词典：

1. 登录网页后打开 **Account**（`/account`），为当前设备生成一个 API Token（可为多台电脑分别生成并单独吊销）。
2. 打开 `chrome://extensions`，开启**开发者模式**，点击**加载已解压的扩展程序**，选择 `extension/` 目录。
3. 点击扩展图标打开侧边栏，进入 **Settings**，填写服务地址（如 `http://localhost:8000`）和你的 API Token，点击 **Save & test**。
4. 你也可以随时在任意设备上访问 `/inbox` 查看、编辑并批量导入已记录的词条。
